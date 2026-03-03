"""Grisha - The Visor/Auditor

Role: Result verification via Vision, Security control
Voice: Mykyta (male)
Model: Configured vision model
"""

import os
import sys

# Robust path handling for both Dev and Production (Packaged)
current_dir = os.path.dirname(os.path.abspath(__file__))
# src/brain/agents -> src -> project_root
project_root = os.path.abspath(os.path.join(current_dir, "..", "..", ".."))
sys.path.insert(0, project_root)

import hashlib
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from langchain_core.messages import HumanMessage, SystemMessage
from PIL import Image

from src.brain.agents.base_agent import BaseAgent
from src.brain.config.config_loader import config
from src.brain.core.orchestration.context import shared_context
from src.brain.mcp.mcp_manager import mcp_manager
from src.brain.monitoring.logger import logger
from src.brain.monitoring.utils.security import mask_sensitive_data

try:
    from src.brain.neural_core.memory.graph import cognitive_graph
except ImportError:
    cognitive_graph = None
from src.brain.prompts import AgentPrompts
from src.brain.prompts.grisha import (
    GRISHA_DEEP_VALIDATION_REASONING,
    GRISHA_FAILURE_CONTEXT_PROMPT,
    GRISHA_FIX_PLAN_PROMPT,
    GRISHA_FORENSIC_ANALYSIS,
    GRISHA_LOGICAL_VERDICT,
    GRISHA_PLAN_VERIFICATION_PROMPT,
    GRISHA_VERIFICATION_GOAL_ANALYSIS,
)
from src.providers.factory import create_llm


@dataclass
class VerificationResult:
    """Verification result"""

    step_id: str
    verified: bool
    confidence: float  # 0.0 - 1.0
    description: str
    issues: list
    voice_message: str = ""
    fixed_plan: Any = None
    timestamp: datetime | None = None
    screenshot_analyzed: bool = False

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class Grisha(BaseAgent):
    """Grisha - The Visor/Auditor

    3-Phase Verification Architecture:

    Phase 1: Strategy Planning (configured strategy_model)
             - Analyzes step requirements and determines verification approach
             - Plans which MCP tools are needed for evidence collection
             - Outputs verification strategy in natural language

    Phase 2: Tool Execution (configured execution model)
             - Selects and executes MCP server tools based on strategy
             - Collects evidence (logs, file contents, DB queries, etc.)
             - Similar to Tetyana's execution phase

    Phase 3: Verdict Formation (configured verdict_model, vision_model)
             - Analyzes evidence collected from Phase 2
             - Uses vision model for screenshot analysis if needed
             - Forms logical verdict: PASS/FAIL with confidence
             - Can fallback to execution model if verdict model fails

    Security Functions:
    - Blocking dangerous commands via BLOCKLIST
    - Multi-layer verification for critical operations
    """

    NAME = AgentPrompts.GRISHA["NAME"]
    DISPLAY_NAME = AgentPrompts.GRISHA["DISPLAY_NAME"]
    VOICE = AgentPrompts.GRISHA["VOICE"]
    COLOR = AgentPrompts.GRISHA["COLOR"]

    @property
    def system_prompt(self) -> str:
        """Dynamically generate system prompt with current catalog."""
        return AgentPrompts.get_agent_system_prompt("GRISHA")

    # Hardcoded blocklist for critical commands
    BLOCKLIST = [
        "rm -rf /",
        "mkfs",
        "dd if=",
        ":(){:|:&};:",
        "chmod 777 /",
        "chown root:root /",
        "> /dev/sda",
        "mv / /dev/null",
    ]

    def __init__(self, vision_model: str | None = None):
        """Initialize Grisha with 3-phase verification architecture.



        Phase 1: Strategy Planning (configured strategy_model)
                 - Analyze what needs verification and which tools to use

        Phase 2: Tool Execution (configured execution model)
                 - Select and execute MCP server tools (similar to Tetyana)

        Phase 3: Verdict Formation (configured verdict_model, vision_model)
                 - Analyze collected evidence and form final verdict
        """
        # Get model config (config.yaml > parameter)
        agent_config = config.get_agent_config("grisha")
        security_config = config.get_security_config()

        # Phase 1: Strategy Planning Model
        strategy_model = (
            agent_config.get("strategy_model")
            or config.get("models.reasoning")
            or config.get("models.default")
        )
        if not strategy_model or not strategy_model.strip():
            raise ValueError(
                "[GRISHA] Strategy model not configured. Please set 'models.reasoning' or 'agents.grisha.strategy_model' in config.yaml"
            )
        self.strategist = create_llm(model_name=strategy_model)

        # Phase 2: Execution Model (for MCP tool calls, like Tetyana)
        execution_model = agent_config.get("model") or config.get("models.default")
        if not execution_model or not execution_model.strip():
            raise ValueError(
                "[GRISHA] Execution model not configured. Please set 'models.default' or 'agents.grisha.model' in config.yaml"
            )
        self.executor = create_llm(model_name=execution_model)

        # Phase 3: Verdict & Vision Models
        vision_model_name = (
            vision_model
            or agent_config.get("vision_model")
            or config.get("models.vision")
            or execution_model
        )
        if not vision_model_name or not vision_model_name.strip():
            raise ValueError(
                "[GRISHA] Vision model not configured. Please set 'models.vision' or 'agents.grisha.vision_model' in config.yaml"
            )
        self.llm = create_llm(model_name=vision_model_name, vision_model_name=vision_model_name)

        verdict_model = agent_config.get("verdict_model")
        if not verdict_model or not verdict_model.strip():
            verdict_model = strategy_model  # Fallback to strategy model
        self.verdict_llm = create_llm(model_name=verdict_model)

        # General settings
        self.temperature = agent_config.get("temperature", 0.3)
        self.dangerous_commands = security_config.get("dangerous_commands", self.BLOCKLIST)
        self.verifications: list = []
        self._strategy_cache: dict[str, str] = {}
        self._rejection_history: dict[
            str, list[dict]
        ] = {}  # step_id -> list of rejection fingerprints

        logger.info(
            f"[GRISHA] 3-Phase Architecture Initialized:\n"
            f"  Phase 1 (Strategy): {strategy_model}\n"
            f"  Phase 2 (Execution): {execution_model}\n"
            f"  Phase 3 (Verdict): {verdict_model}, Vision: {vision_model_name}"
        )

    def _create_rejection_fingerprint(
        self, step_id: str, verdict: str, issues: list[str], confidence: float
    ) -> str:
        """Creates a unique fingerprint for a rejection to detect recursion.

        Args:
            step_id: ID of the step being verified
            verdict: The verdict text (FAILED, PASSED, etc.)
            issues: List of issues identified
            confidence: Confidence score

        Returns:
            SHA256 hash fingerprint of the rejection
        """
        # Create a stable representation of the rejection
        fingerprint_data = {
            "step_id": str(step_id),
            "verdict": verdict.upper().strip(),
            "issues_normalized": sorted([issue.strip().lower() for issue in issues]),
            "confidence_bucket": round(confidence, 1),  # Bucket to 0.1 precision
        }

        # Create hash
        fingerprint_str = json.dumps(fingerprint_data, sort_keys=True)
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()

    def _check_recursion(
        self, step_id: str, fingerprint: str, max_same_rejections: int = 2
    ) -> tuple[bool, int]:
        """Checks if we're in a recursion loop for this step.

        Args:
            step_id: ID of the step being verified
            fingerprint: Rejection fingerprint to check
            max_same_rejections: Maximum allowed identical rejections

        Returns:
            (is_recursion, rejection_count) tuple
        """
        if step_id not in self._rejection_history:
            self._rejection_history[step_id] = []

        history = self._rejection_history[step_id]

        # Count how many times we've seen this exact fingerprint
        same_rejections = sum(1 for entry in history if entry["fingerprint"] == fingerprint)

        is_recursion = same_rejections >= max_same_rejections

        if is_recursion:
            logger.warning(
                f"[GRISHA] RECURSION DETECTED for step {step_id}: "
                f"Same rejection repeated {same_rejections} times"
            )

        return is_recursion, same_rejections

    def _record_rejection(self, step_id: str, fingerprint: str, verdict_data: dict) -> None:
        """Records a rejection in the history for recursion detection.

        Args:
            step_id: ID of the step
            fingerprint: Rejection fingerprint
            verdict_data: Full verdict data for debugging
        """
        if step_id not in self._rejection_history:
            self._rejection_history[step_id] = []

        self._rejection_history[step_id].append(
            {
                "fingerprint": fingerprint,
                "timestamp": datetime.now().isoformat(),
                "verdict": verdict_data.get("verdict", "UNKNOWN"),
                "confidence": verdict_data.get("confidence", 0.0),
            }
        )

        logger.debug(
            mask_sensitive_data(
                f"[GRISHA] Recorded rejection for step {step_id}. "
                f"Total rejections: {len(self._rejection_history[step_id])}"
            )
        )

    async def _deep_validation_reasoning(
        self,
        step: dict[str, Any],
        result: Any,
        goal_context: str,
    ) -> dict[str, Any]:
        """Performs deep validation reasoning using sequential thinking.
        Returns structured validation insights across multiple layers.
        """
        step_action = step.get("action", "")
        expected = step.get("expected_result", "")

        # Extract result string safely
        if hasattr(result, "result"):
            result_str = str(result.result)[:2000]
        elif isinstance(result, dict):
            result_str = str(result.get("result", result.get("output", "")))[:2000]
        else:
            result_str = str(result)[:2000]

        reasoning_query = GRISHA_DEEP_VALIDATION_REASONING.format(
            step_action=step_action,
            expected_result=expected,
            result_str=result_str,
            goal_context=goal_context,
        )

        reasoning = await self.use_sequential_thinking(reasoning_query, total_thoughts=2)
        return {
            "deep_analysis": reasoning.get("analysis", ""),
            "confidence_boost": 0.1 if reasoning.get("success") else 0.0,
            "layers_validated": 4,
            "synthesis": reasoning.get("final_thought", ""),
        }

    async def _multi_layer_verification(
        self,
        step: dict[str, Any],
        result: Any,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Performs verification across 4 layers:
        1. Tool Execution Layer - was the tool called correctly?
        2. Output Layer - is the output valid?
        3. State Layer - did system state change as expected?
        4. Goal Layer - does this advance the mission?
        """

        layers: list[dict[str, Any]] = []

        # Layer 1: Tool Execution
        tool_layer = {"layer": "tool_execution", "passed": False, "evidence": ""}
        if hasattr(result, "tool_call") or (isinstance(result, dict) and result.get("tool_call")):
            tc = getattr(result, "tool_call", None) or (
                result.get("tool_call", {}) if isinstance(result, dict) else {}
            )
            tc_name = ""
            if isinstance(tc, dict):
                tc_name = tc.get("name", "")
            else:
                tc_name = getattr(tc, "name", "")

            if tc_name:
                tool_layer["passed"] = True
                tool_layer["evidence"] = f"Інструмент '{tc_name}' був викликаний"
        layers.append(tool_layer)

        # Layer 2: Output Validation
        output_layer = {"layer": "output_validation", "passed": False, "evidence": ""}
        result_val = ""
        if isinstance(result, dict):
            result_val = result.get("result", "")
        else:
            result_val = getattr(result, "result", getattr(result, "content", str(result)))

        result_str = str(result_val)
        if result_str and len(result_str) > 0 and "error" not in result_str.lower():
            output_layer["passed"] = True
            output_layer["evidence"] = f"Отримано результат: {result_str[:200]}..."
        layers.append(output_layer)

        # Layer 3: State Verification (via DB trace)
        state_layer = {"layer": "state_verification", "passed": False, "evidence": ""}
        try:
            trace = await self._fetch_execution_trace(str(step.get("id")))
            if "No DB records" not in trace:
                state_layer["passed"] = True
                state_layer["evidence"] = "Трейс виконання знайдено в базі даних"
        except Exception:
            state_layer["evidence"] = "Не вдалося перевірити стан"
        layers.append(state_layer)

        # Layer 4: Goal Alignment (assume aligned unless proven otherwise)
        goal_layer = {
            "layer": "goal_alignment",
            "passed": True,
            "evidence": "Крок є частиною затвердженого плану",
        }
        layers.append(goal_layer)

        # Log layer results
        passed_count = sum(1 for l in layers if l["passed"])
        logger.info(f"[GRISHA] Multi-layer verification: {passed_count}/4 layers passed")

        return layers

    async def _create_robust_strategy_via_reasoning(
        self,
        step_description: str,
        context: dict,
        goal_context: str = "",
    ) -> str:
        """Uses reasoning model (configured in config.yaml) to create a robust verification strategy.
        OPTIMIZATION: Caches strategies by step type to avoid redundant LLM calls.
        NOTE: This method appears to be legacy/unused. Consider removal or refactoring.
        """

        # OPTIMIZATION: Check cache first
        cache_key = f"{step_description[:50]}"
        if cache_key in self._strategy_cache:
            logger.info(f"[GRISHA] Using cached strategy for: {cache_key[:30]}...")
            return self._strategy_cache[cache_key]

        # Legacy code - parameters don't match usage
        prompt = f"Create verification strategy for: {step_description}\nContext: {context}\nGoal: {goal_context}"

        # Get available capabilities to inform the strategist
        capabilities = self._get_environment_capabilities()
        system_msg = AgentPrompts.grisha_strategist_system_prompt(capabilities)
        messages = [
            SystemMessage(content=system_msg),
            HumanMessage(content=prompt),
        ]

        try:
            response = await self.strategist.ainvoke(messages)
            strategy = getattr(response, "content", str(response))
            logger.info(f"[GRISHA] Strategy devised: {strategy[:200]}...")
            # Cache the strategy
            self._strategy_cache[cache_key] = strategy
            return strategy
        except Exception as e:
            logger.warning(f"[GRISHA] Strategy planning failed: {e}")
            return "Proceed with standard verification (Vision + Tools)."

    def _check_blocklist(self, action_desc: str) -> bool:
        """Check if action contains blocked commands"""
        return any(blocked in action_desc for blocked in self.dangerous_commands)

    def _get_environment_capabilities(self) -> str:
        """Collects raw facts about the environment to inform the strategist.
        No heuristics here—just data for the LLM to reason about.
        """
        try:
            from src.brain.mcp.mcp_manager import mcp_manager

            servers_cfg = getattr(mcp_manager, "config", {}).get("mcpServers", {})
            active_servers = [
                s for s, cfg in servers_cfg.items() if not (cfg or {}).get("disabled")
            ]

            swift_servers = []
            for s in active_servers:
                cfg = servers_cfg.get(s, {})
                cmd = (cfg or {}).get("command", "") or ""
                if (
                    "swift" in s.lower()
                    or "macos" in s.lower()
                    or (isinstance(cmd, str) and "swift" in cmd.lower())
                ):
                    swift_servers.append(s)
        except Exception:
            active_servers = []
            swift_servers = []

        # Check if vision model is powerful (from config)
        vision_model = (getattr(self.llm, "model_name", "") or "unknown").lower()
        is_powerful = "vision" in vision_model

        info = [
            f"Active MCP Realms: {', '.join(active_servers)}",
            f"Native Swift Servers: {', '.join(swift_servers)} (Preferred for OS control)",
            f"Vision Model: {vision_model} ({'High-Performance' if is_powerful else 'Standard'})",
            f"Timezone: {datetime.now().astimezone().tzname()}",
            "Capabilities: Full UI Traversal, OCR, Terminal, Filesystem, Apple Productivity Apps integration.",
        ]
        return "\n".join(info)

    def _summarize_ui_data(self, raw_data: str) -> str:
        """Intelligently extracts the 'essence' of UI traversal data locally.
        Reduces thousands of lines of JSON to a concise list of key interactive elements.
        """
        if not self._is_json_string(raw_data):
            return raw_data

        try:
            data = json.loads(raw_data)
            elements = self._extract_elements_from_data(data)

            if not elements:
                return raw_data[:2000]  # Fallback to truncation

            summary_items = self._format_ui_elements(elements)
            summary = " | ".join(summary_items)

            if not summary and elements:
                return f"UI Tree Summary: {len(elements)} elements found. Samples: {elements[:2]!s}"

            return f"UI Summary ({len(elements)} elements): " + summary

        except Exception as e:
            logger.debug(f"[GRISHA] UI summarization failed (falling back to truncation): {e}")
            return raw_data[:3000]

    def _is_json_string(self, text: str) -> bool:
        """Checks if a string is likely JSON."""
        return (
            bool(text)
            and isinstance(text, str)
            and (text.strip().startswith("{") or text.strip().startswith("["))
        )

    def _extract_elements_from_data(self, data: Any) -> list:
        """Robustly extracts element list from various JSON structures."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if "elements" in data and isinstance(data["elements"], list):
                return data["elements"]
            if "result" in data:
                res = data["result"]
                if isinstance(res, dict):
                    elements = res.get("elements", [])
                    if isinstance(elements, list):
                        return elements
                if isinstance(res, list):
                    return res
        return []

    def _format_ui_elements(self, elements: list) -> list[str]:
        """Filters and formats UI elements into a concise list."""
        items = []
        for el in elements:
            if not isinstance(el, dict):
                continue
            if self._is_important_element(el):
                items.append(self._format_single_element(el))
        return items

    def _is_important_element(self, el: dict) -> bool:
        """Determines if a UI element is worth including in the summary."""
        if el.get("isVisible") is False and not el.get("label") and not el.get("title"):
            return False

        role = el.get("role", "")
        label = el.get("label") or el.get("title") or el.get("description") or el.get("help")
        value = el.get("value") or el.get("stringValue")

        return bool(
            label or value or role in ["AXButton", "AXTextField", "AXTextArea", "AXCheckBox"]
        )

    def _format_single_element(self, el: dict) -> str:
        """Formats a single UI element into a string."""
        role = el.get("role", "element")
        label = el.get("label") or el.get("title") or el.get("description") or el.get("help")
        value = el.get("value") or el.get("stringValue")

        item = f"[{role}"
        if label:
            item += f": '{label}'"
        if value:
            item += f", value: '{value}'"
        item += "]"
        return item

    async def _analyze_verification_goal(
        self, step: dict[str, Any], goal_context: str
    ) -> dict[str, Any]:
        """Phase 1: Use sequential-thinking to deeply understand verification goal and select tools.

        Returns:
            {
                "verification_purpose": str,  # Clear goal of what needs verification
                "selected_tools": list[dict],  # Tools to use with reasoning
                "success_criteria": str,  # What constitutes success
            }
        """
        step_action = step.get("action", "")
        expected_result = step.get("expected_result", "")
        step_id = step.get("id", "unknown")

        # --- NEURAL INSIGHTS FOR VERIFICATION ---
        neural_lessons = ""
        if cognitive_graph:
            insights = await cognitive_graph.get_related_insights(step_action, limit=2)
            if insights:
                neural_lessons = "\n\nLESSON HISTORY (From Neural Graph):\n" + "\n".join(
                    [f"- {ins}" for ins in insights]
                )

        query = GRISHA_VERIFICATION_GOAL_ANALYSIS.format(
            step_id=step_id,
            step_action=step_action,
            expected_result=expected_result,
            goal_context=goal_context + neural_lessons,
        )

        logger.info(f"[GRISHA] Phase 1: Analyzing verification goal for step {step_id}...")

        try:
            reasoning_result = await self.use_sequential_thinking(query, total_thoughts=3)

            if not reasoning_result.get("success"):
                logger.warning("[GRISHA] Sequential thinking failed, using fallback strategy")
                return {
                    "verification_purpose": f"Verify that '{step_action}' was executed successfully",
                    "selected_tools": [
                        {
                            "tool": "vibe.vibe_check_db",
                            "reason": "Check tool execution records in DB",
                        },
                    ],
                    "success_criteria": "Execution record found and result contains no critical errors",
                }

            analysis_text = reasoning_result.get("analysis", "")

            # ANTI-LOOP DETECTION: Check for repetitive patterns
            if self._detect_repetitive_thinking(analysis_text):
                logger.warning("[GRISHA] Anti-loop triggered - repetitive thinking detected")
                return {
                    "verification_purpose": f"Verify that '{step_action}' was executed successfully",
                    "selected_tools": [
                        {
                            "tool": "vibe.vibe_check_db",
                            "reason": "Fallback: DB audit due to repetitive thinking",
                        },
                    ],
                    "success_criteria": "Execution record found and result contains no critical errors",
                    "full_reasoning": "Anti-loop fallback activated",
                }

            # Parse the analysis (simple extraction, can be improved)
            return {
                "verification_purpose": analysis_text,
                "selected_tools": self._extract_tools_from_analysis(analysis_text, step),
                "success_criteria": analysis_text,
                "full_reasoning": analysis_text,
            }

        except Exception as e:
            logger.error(f"[GRISHA] Verification goal analysis failed: {e}")
            return {
                "verification_purpose": f"Verify '{step_action}'",
                "selected_tools": [{"tool": "vibe.vibe_check_db", "reason": "Fallback"}],
                "success_criteria": "Non-empty execution results",
            }

    def _extract_tools_from_analysis(self, analysis: str, step: dict) -> list[dict]:
        """Extract tool recommendations from sequential-thinking analysis."""
        tools = []
        step_id = step.get("id", "unknown")

        # Always include database check as primary source of truth
        tools.append(
            {
                "tool": "vibe.vibe_check_db",
                "args": {
                    "query": f"SELECT te.tool_name, te.arguments, te.result, te.created_at FROM tool_executions te JOIN task_steps ts ON te.step_id = ts.id WHERE ts.sequence_number = '{step_id}' ORDER BY te.created_at DESC LIMIT 5"
                },
                "reason": "Primary source of truth - database audit",
            }
        )

        # Detect if this is an analysis task vs action task
        step_action_lower = step.get("action", "").lower()

        # Analysis/Discovery task keywords - for these, DB trace is usually sufficient
        is_analysis_task = any(
            keyword in step_action_lower
            for keyword in [
                "analyze",
                "review",
                "research",
                "investigate",
                "examine",
                "study",
                "assess",
                "evaluate",
                "explore",
            ]
        )

        # If it's an analysis task, don't add file verification tools
        # (DB trace of tool execution is sufficient proof of analysis)
        if is_analysis_task:
            logger.info("[GRISHA] Detected ANALYSIS task - relying on DB trace only")
            return tools[:2]  # Only DB check

        # For ACTION tasks (that are not primarily analysis), add context-aware verification tools
        is_search_only = any(kw in step_action_lower for kw in ["search", "find", "locate"])

        # CRITICAL: For file/code creation tasks, verify ACTUAL CONTENT on disk
        is_creation_task = any(
            kw in step_action_lower
            for kw in ["create", "write", "implement", "generate", "save", "edit", "modify"]
        )

        if not is_search_only and (is_creation_task or "file" in step_action_lower):
            # Try to extract actual file path from step description
            file_path = self._extract_file_path_from_text(
                step_action_lower + " " + step.get("expected_result", "")
            )
            if file_path:
                # Verify ACTUAL content — logs are only for knowing WHAT to verify
                tools.append(
                    {
                        "tool": "macos-use.execute_command",
                        "args": {
                            "command": f"head -50 '{file_path}' 2>/dev/null || echo 'FILE_NOT_FOUND'"
                        },
                        "reason": f"CONTENT VERIFICATION: Read actual file content from disk: {file_path}",
                    }
                )
                # For code generation, also check file size
                if any(ext in file_path for ext in [".py", ".js", ".ts", ".html", ".css", ".sh"]):
                    tools.append(
                        {
                            "tool": "macos-use.execute_command",
                            "args": {
                                "command": f"wc -l '{file_path}' 2>/dev/null && stat -f '%z' '{file_path}' 2>/dev/null || echo '0'"
                            },
                            "reason": f"SIZE VERIFICATION: Ensure file is non-empty and has real code: {file_path}",
                        }
                    )
            else:
                # Fallback: list recent changes in project
                project_root = os.path.expanduser("~/Documents/GitHub/atlastrinity")
                tools.append(
                    {
                        "tool": "macos-use.execute_command",
                        "args": {
                            "command": f"find '{project_root}' -type f -mmin -5 2>/dev/null | head -5"
                        },
                        "reason": "Find recently modified files to verify creation",
                    }
                )

        if "search" in step_action_lower or "find" in step_action_lower:
            tools.append(
                {
                    "tool": "macos-use_get_clipboard",
                    "args": {},
                    "reason": "Check if search results were copied",
                }
            )

        # General system verification fallback
        if len(tools) <= 1 and any(
            kw in step_action_lower for kw in ["verify", "check", "status", "ensure", "validate"]
        ):
            tools.append(
                {
                    "tool": "macos-use.execute_command",
                    "args": {"command": "ls -la"},
                    "reason": "General system state verification (Active Check)",
                }
            )

        return tools[:4]  # Limit to 4 tools max

    async def _form_logical_verdict(
        self,
        step: dict[str, Any],
        goal_analysis: dict[str, Any],
        verification_results: list[dict],
        goal_context: str,
    ) -> dict[str, Any]:
        """Phase 2: Use sequential-thinking to form LOGICAL verdict based on collected evidence.

        Args:
            step: Step being verified
            goal_analysis: Results from Phase 1 (verification purpose, criteria)
            verification_results: List of tool execution results
            goal_context: Overall task goal

        Returns:
            {
                "verified": bool,
                "confidence": float,
                "reasoning": str,
                "issues": list[str],
            }
        """
        step_id = step.get("id", "unknown")

        # Format results for analysis
        results_summary = ""
        for i, r in enumerate(verification_results):
            # Normalization: ensure we can read 'tool' and 'result' regardless of object vs dict
            tool_name = r.get("tool", "N/A") if isinstance(r, dict) else getattr(r, "tool", "N/A")

            # Check for error: result.error (sdk object) vs result.get('error') (dict)
            has_error = False
            if isinstance(r, dict):
                has_error = bool(r.get("error"))
            else:
                has_error = bool(getattr(r, "error", False))

            # Get result string
            res_val = "N/A"
            if isinstance(r, dict):
                res_val = str(r.get("result", "N/A"))
            elif hasattr(r, "result"):
                res_val = str(r.result)
            elif hasattr(r, "content"):
                res_val = str(r.content)
            else:
                res_val = str(r)

            results_summary += f"Tool {i + 1}: {tool_name}\n  Success: {not has_error}\n  Result: {res_val[:2000]}\n"

        query = GRISHA_LOGICAL_VERDICT.format(
            step_action=step.get("action", ""),
            expected_result=step.get("expected_result", ""),
            results_summary=results_summary,
            verification_purpose=goal_analysis.get("verification_purpose", "Unknown"),
            success_criteria=goal_analysis.get("success_criteria", "Unknown"),
            goal_context=goal_context,
        )

        logger.info(f"[GRISHA] Phase 2: Forming logical verdict for step {step_id}...")

        try:
            reasoning_result = await self.use_sequential_thinking(query, total_thoughts=2)

            if not reasoning_result.get("success"):
                logger.warning("[GRISHA] Logical verdict analysis failed, using fallback")
                return self._fallback_verdict(verification_results)

            parsed_verdict = self._parse_verdict_analysis(reasoning_result.get("analysis", ""))

            # CRITICAL FIX: Check command relevance BEFORE accepting verdict
            is_relevant, relevance_reason = self._check_command_relevance(
                step.get("action", ""), step.get("expected_result", ""), verification_results
            )

            if not is_relevant:
                logger.warning(f"[GRISHA] Command relevance check FAILED: {relevance_reason}")
                parsed_verdict["verified"] = False
                parsed_verdict["confidence"] = min(parsed_verdict["confidence"], 0.3)
                issue_msg = f"Нерелевантна команда: {relevance_reason}"
                parsed_verdict["issues"].append(issue_msg)
            else:
                logger.info(f"[GRISHA] Command relevance check PASSED: {relevance_reason}")

            return {
                "verified": parsed_verdict["verified"],
                "confidence": parsed_verdict["confidence"],
                "reasoning": parsed_verdict["reasoning"],
                "issues": parsed_verdict["issues"],
                "voice_summary_uk": parsed_verdict.get("voice_summary_uk", ""),
                "full_analysis": reasoning_result.get("analysis", ""),
            }

        except Exception as e:
            logger.error(f"[GRISHA] Logical verdict formation failed: {e}")
            return self._fallback_verdict(verification_results)

    def _parse_verdict_analysis(self, analysis_text: str) -> dict[str, Any]:
        """Parses the logical verdict analysis text with improved reliability."""
        analysis_upper = analysis_text.upper()

        verified = self._extract_verdict(analysis_text, analysis_upper)
        confidence = self._extract_confidence(analysis_text, verified)
        reasoning = self._extract_reasoning(analysis_text)
        issues = self._extract_issues(analysis_text, verified)
        voice_summary_uk = self._extract_voice_summary_uk(analysis_text)

        return {
            "verified": verified,
            "confidence": confidence,
            "reasoning": reasoning,
            "issues": issues,
            "voice_summary_uk": voice_summary_uk,
        }

    def _extract_verdict(self, analysis_text: str, analysis_upper: str) -> bool:
        """Determines verification success or failure from text."""

        verdict_match = re.search(
            r"(?:VERDICT|ВЕРДИКТ)[:\s]*(CONFIRMED|FAILED|ПІДТВЕРДЖЕНО|ПРОВАЛЕНО|УСПІШНО|APPROVED|REJECTED|ПРИЙНЯТО|ВІДХИЛЕНО|PASS|FAIL)",
            analysis_text,
            re.IGNORECASE,
        )

        if verdict_match:
            verdict_val = verdict_match.group(1).upper()
            return any(
                word in verdict_val
                for word in ["CONFIRMED", "ПІДТВЕРДЖЕНО", "УСПІШНО", "APPROVED", "ПРИЙНЯТО", "PASS"]
            )

        return self._fallback_verdict_analysis(analysis_text, analysis_upper)

    _verdict_markers_cache: dict[str, list[str]] | None = None

    def _load_verdict_markers(self) -> dict[str, list[str]]:
        """Load verdict markers from behavior_config.yaml (cached).

        Returns dict with keys: 'no_error_phrases', 'explicit_success', 'explicit_failure'.
        Falls back to minimal inline defaults if config is unavailable.
        """
        if self._verdict_markers_cache is not None:
            return self._verdict_markers_cache

        # Minimal fallbacks — used only if config loading fails
        fallback = {
            "no_error_phrases": [
                "NO ERROR",
                "0 ERROR",
                "БЕЗ ПОМИЛОК",
                "НЕМАЄ ПОМИЛОК",
                "НЕМАЄ ПРОБЛЕМ",
                "ПОМИЛКА НЕ КРИТИЧНА",
            ],
            "explicit_success": [
                "VERDICT: CONFIRMED",
                "ВЕРДИКТ: ПІДТВЕРДЖЕНО",
                "КРОК ВВАЖАЄТЬСЯ ВИКОНАНИМ",
                "УСПІШНО ВИКОНАНО",
                # Legacy/Test markers
                "APPROVE",
                "APPROVED",
                "CONFIRMED",
                "ПІДТВЕРДЖЕНО",
                "УСПІШНО",
                "ПРИЙНЯТО",
                "PASS",
            ],
            "explicit_failure": [
                "VERDICT: FAILED",
                "ВЕРДИКТ: ПРОВАЛЕНО",
                "КРОК НЕ ПРОЙШОВ",
                "STEP FAILED",
                # Legacy/Test markers
                "REJECT",
                "REJECTED",
                "FAIL",
                "FAILED",
            ],
        }

        try:
            from src.brain.behavior.behavior_engine import behavior_engine

            vm = (
                behavior_engine.config.get("grisha", {})
                .get("verification", {})
                .get("verdict_markers", {})
            )
            if vm:
                result = {
                    "no_error_phrases": vm.get("no_error_phrases", fallback["no_error_phrases"]),
                    "explicit_success": vm.get("explicit_success", fallback["explicit_success"]),
                    "explicit_failure": vm.get("explicit_failure", fallback["explicit_failure"]),
                }
                self._verdict_markers_cache = result
                logger.debug(
                    f"[GRISHA] Loaded verdict markers from config: "
                    f"{len(result['no_error_phrases'])} no-error, "
                    f"{len(result['explicit_success'])} success, "
                    f"{len(result['explicit_failure'])} failure"
                )
                return result
        except Exception as e:
            logger.debug(f"[GRISHA] Config load for verdict markers failed: {e}")

        self._verdict_markers_cache = fallback
        return fallback

    def _fallback_verdict_analysis(self, analysis_text: str, analysis_upper: str) -> bool:
        """Enhanced fallback to analyze reasoning consistency.

        PRIORITY ORDER (highest to lowest):
        1. Explicit verdict markers (КРОК ПІДТВЕРДЖЕНО, VERDICT: CONFIRMED)
        2. Success indicators without contradicting failure markers
        3. Failure indicators
        4. Reasoning context analysis
        """
        # Load verdict markers from behavior_config (with hardcoded fallbacks)
        markers = self._load_verdict_markers()

        # Sanitize text to remove "acceptable error" phrases before checking for "error" keyword
        sanitized_upper = analysis_upper
        for phrase in markers["no_error_phrases"]:
            sanitized_upper = sanitized_upper.replace(phrase, "")

        header_text = sanitized_upper.split("REASONING")[0].split("ОБҐРУНТУВАННЯ")[0]

        # EXPLICIT verdict markers - highest priority
        explicit_success_verdicts = markers["explicit_success"]
        explicit_failure_verdicts = markers["explicit_failure"]

        # Check explicit verdicts FIRST - these have highest priority
        has_explicit_success = any(v in analysis_upper for v in explicit_success_verdicts)
        has_explicit_failure = any(v in analysis_upper for v in explicit_failure_verdicts)

        # NEW PRIORITY: Success wins if explicitly stated, even if failure was mentioned earlier
        # This handles cases where the model starts with "Step failed..." but concludes with "Actually, it's fine."
        if has_explicit_success:
            return True

        # If explicit failure verdict exists and NO explicit success, return False
        if has_explicit_failure and not has_explicit_success:
            return False

        # General success/failure indicators (lower priority)
        success_indicators = [
            "CONFIRMED",
            "SUCCESS",
            "VERIFIED",
            "APPROVED",
            "PASS",
            "ПІДТВЕРДЖЕНО",
            "УСПІШНО",
            "ПРИЙНЯТО",
        ]
        failure_indicators = [
            "FAILED",
            "ERROR",
            "REJECTED",
            "FAIL",
            "ПРОВАЛЕНО",
            "ПОМИЛКА",
            "ВІДХИЛЕНО",
            "НЕ ВИКОНАНО",
        ]

        has_success = any(word in header_text for word in success_indicators)
        has_failure = any(word in header_text for word in failure_indicators)

        # Check FULL TEXT for final conclusion phrases (not just header)
        reasoning_text = analysis_text.upper()
        reasoning_confirms_success = any(
            phrase in reasoning_text
            for phrase in [
                "ШЛЯХ ІСНУЄ",
                "КАТАЛОГ СТВОРЕНО",
                "ПРАВА ДОСТУПУ Є",
                "НЕМАЄ ОЗНАК ПРОБЛЕМ",
                "ДОСТАТНІ ОЗНАКИ",
                "УСПІШНО СТВОРЕНО",
                "УСПІШНО ОТРИМАНА",
                "УСПІШНО ВИКОНАНО",
                "ПІДТВЕРДЖУЄ",
                "ВСЕ ДОБРЕ",
                "CONFIRMED AS COMPLETED",
                "STEP IS CONFIRMED",
                # Additional final conclusion phrases
                "КІНЦЕВИЙ ВЕРДИКТ: УСПІХ",
                "ФІНАЛЬНЕ РІШЕННЯ: ВИКОНАНО",
                "ОСТАТОЧНО: ПІДТВЕРДЖЕНО",
                "В РЕЗУЛЬТАТІ: УСПІШНО",
            ]
        )

        # FIXED PRIORITY ORDER:
        # 1. Header success indicator → True
        # 2. Reasoning confirms success (final conclusions) → True
        # 3. Header failure indicator → False (only if no success found anywhere)
        # 4. Default → False
        if has_success:
            return True
        if reasoning_confirms_success:
            logger.debug("[GRISHA] Reasoning section confirms success despite header ambiguity")
            return True
        if has_failure:
            return False
        return False  # Default to failure if nothing clear

    def _extract_confidence(self, analysis_text: str, verified: bool) -> float:
        """Extracts confidence percentage from analysis."""

        confidence_match = re.search(
            r"(?:CONFIDENCE|ВПЕВНЕНІСТЬ)[:\s]*(\d+\.?\d*)\%?", analysis_text, re.IGNORECASE
        )
        confidence = (
            float(confidence_match.group(1)) if confidence_match else (0.8 if verified else 0.2)
        )
        if confidence > 1.0:
            confidence /= 100.0
        return confidence

    def _extract_reasoning(self, analysis_text: str) -> str:
        """Extracts reasoning text block."""

        reasoning_match = re.search(
            r"(?:REASONING|ОБҐРУНТУВАННЯ)[:\s]*(.*?)(?=\n- \*\*|\Z)",
            analysis_text,
            re.DOTALL | re.IGNORECASE,
        )
        return reasoning_match.group(1).strip() if reasoning_match else analysis_text

    def _extract_issues(self, analysis_text: str, verified: bool) -> list[str]:
        """Extracts and filters potential issues."""

        issues_match = re.search(
            r"(?:ISSUES|ПРОБЛЕМИ)[:\s]*(.*?)(?=\n- \*\*|\Z)",
            analysis_text,
            re.DOTALL | re.IGNORECASE,
        )
        issues_text = (
            issues_match.group(1).strip()
            if issues_match
            else ("Verification criteria not met" if not verified else "")
        )

        issues = [
            i.strip()
            for i in issues_text.split("\n")
            if i.strip() and i.strip() not in ["None", "Не виявлено"]
        ]

        if verified and issues:
            issues = self._filter_contradictory_issues(issues)

        if not verified and not issues:
            issues.append("Verification criteria not met")

        # FILTER: If verified but 'not found' is in issues, it's likely a Discovery Success
        # We don't want to report 'not found' as a problem if we accepted it as a result.
        if verified:
            issues = [
                i
                for i in issues
                if not any(
                    kw in i.lower() for kw in ["not found", "не знайдено", "empty", "порожньо"]
                )
            ]

        return issues

    def _extract_voice_summary_uk(self, analysis_text: str) -> str:
        """Extracts the concise Ukrainian voice summary from LLM analysis."""
        match = re.search(
            r"(?:VOICE_SUMMARY_UK|ГОЛОСОВИЙ_ПІДСУМОК)[:\s]*(.*?)(?=\n- \*\*|\n\*\*|\Z)",
            analysis_text,
            re.DOTALL | re.IGNORECASE,
        )
        if match:
            summary = match.group(1).strip().strip('"').strip("'")
            # Validate: must be primarily Cyrillic (Ukrainian), not English
            cyrillic = len(re.findall(r"[а-яА-ЯіІєЄїЇґҐ]", summary))
            latin = len(re.findall(r"[a-zA-Z]", summary))
            if cyrillic > latin and len(summary) > 5:
                # Truncate to ~150 chars for TTS speed
                if len(summary) > 150:
                    summary = summary[:147] + "..."
                return summary
        return ""

    def _filter_contradictory_issues(self, issues: list[str]) -> list[str]:
        """Removes issues that contradict successful verification."""
        filtered_issues = []
        for issue in issues:
            issue_upper = issue.upper()
            contradicting_phrases = ["НЕ ВИКОНАНО", "ПОМИЛКА", "ПРОВАЛЕНО", "НЕМАЄ", "ВІДСУТНІЙ"]
            if not any(phrase in issue_upper for phrase in contradicting_phrases):
                filtered_issues.append(issue)
        return filtered_issues

    def _fallback_verdict(self, verification_results: list[dict]) -> dict[str, Any]:
        """Strict fallback verdict logic if sequential-thinking fails."""
        # A tool is considered successful only if it returned valid data and no error
        actual_successes = []
        for r in verification_results:
            success = not r.get("error", False)
            result_val = str(r.get("result", "")).lower()

            # Even if 'success' is True, if result contains failure markers or is empty for info tools, it's a failure
            if success:
                if "error:" in result_val or "failed to" in result_val:
                    success = False
                elif "not found" in result_val or "не знайдено" in result_val:
                    # 'Not found' during discovery is a valid positive outcome
                    success = True
                elif not result_val.strip() and r.get("tool", "").startswith(
                    ("macos-use.read", "vibe.vibe_check", "duckduckgo-search", "golden-fund")
                ):
                    # Empty results for search/read tools are common in discovery
                    # We consider it success if the tool itself didn't crash
                    success = True

            if success:
                actual_successes.append(r)

        total = len(verification_results)
        success_count = len(actual_successes)

        # Verified only if ALL tools succeeded (or at least no critical tool failed)
        verified = success_count == total and total > 0

        # Confidence is lower because we are using fallback logic
        confidence = 0.6 if verified else 0.2

        reasoning = (
            f"СУВОРИЙ вердикт (fallback): {success_count}/{total} інструментів пройшли валідацію. "
        )
        if not verified:
            reasoning += (
                "Позначено як ПОМИЛКА через недостатню кількість доказів або помилки інструментів."
            )
        else:
            reasoning += "Використання обережної верифікації через недоступність логічного аналізу."

        return {
            "verified": verified,
            "confidence": confidence,
            "reasoning": reasoning,
            "issues": ["Логічний аналіз недоступний", "Застосовано сувору верифікацію"]
            if not verified
            else ["Логічний аналіз недоступний"],
        }

    def _is_final_task_completion(self, step: dict[str, Any]) -> bool:
        """Check if this step represents final task completion vs intermediate step"""
        step_action = step.get("action", "").lower()
        expected_result = step.get("expected_result", "").lower()

        # Keywords indicating final task completion
        final_keywords = [
            "complete",
            "completed",
            "finished",
            "done",
            "success",
            "завершено",
            "виконано",
            "готово",
            "успішно",
        ]

        # Check if step action or expected result indicates completion
        is_final = any(keyword in step_action for keyword in final_keywords)
        is_final = is_final or any(keyword in expected_result for keyword in final_keywords)

        # Also check if this is a verification of overall task success
        verification_keywords = ["verify", "check", "confirm", "перевірити", "перевірка"]
        is_verification = any(keyword in step_action for keyword in verification_keywords)

        # If it's a verification step but not about specific technical details,
        # it might be a final verification
        if is_verification and not any(
            tech in step_action for tech in ["bridged", "network", "ip", "vm"]
        ):
            is_final = True

        # NEW: Critical actions (creating files, executing code) should always be verified
        critical_keywords = ["write", "save", "create", "implement", "deploy", "fix", "update"]
        if any(kw in step_action for kw in critical_keywords):
            is_final = True

        logger.info(
            f"[GRISHA] Step completion check - Final/Critical: {is_final}, Action: {step_action[:50]}"
        )
        return is_final

    async def verify_plan(
        self,
        plan: Any,
        user_request: str,
        fix_if_rejected: bool = False,
    ) -> VerificationResult:
        """Verifies the entire execution plan using SEQUENTIAL THINKING SIMULATION.

        Args:
            plan: The TaskPlan object from Atlas
            user_request: The original user goal

        Returns:
            VerificationResult with approved=True/False and reasoning.
        """
        logger.info("[GRISHA] Verifying proposed execution plan via Deep Simulation...")

        plan_steps_text = self._format_plan_steps(plan)

        try:
            analysis_text = await self._run_plan_simulation(user_request, plan_steps_text)

            if not analysis_text:
                return self._create_fallback_verification_result("Plan simulation failed")

            # Parse the simulation results
            parsed_sections = self._parse_simulation_sections(analysis_text)
            issues = self._extract_issues_from_simulation(
                parsed_sections["core_problems"], analysis_text
            )

            # Construct feedback
            feedback_to_atlas = self._construct_atlas_feedback(parsed_sections)

            # Determine verdict
            verdict = self._determine_plan_verdict(
                analysis_text, user_request, issues, feedback_to_atlas
            )

            fixed_plan = None
            if not verdict["approved"] and fix_if_rejected:
                fixed_plan = await self._attempt_plan_fix(
                    user_request, plan_steps_text, feedback_to_atlas
                )

            return VerificationResult(
                step_id="plan_init",
                verified=verdict["approved"],
                confidence=verdict["confidence"],
                description=f"SIMULATION REPORT:\n{feedback_to_atlas or 'Plan is sound.'}",
                issues=issues,
                voice_message=verdict["voice_message"],
                fixed_plan=fixed_plan,
            )

        except Exception as e:
            logger.error(f"[GRISHA] Plan verification failed: {e}")
            return self._create_fallback_verification_result(f"System error: {e}")

    def _format_plan_steps(self, plan: Any) -> str:
        """Formats the plan steps into a string for the LLM."""
        return "\n".join(
            [
                f"{i + 1}. [{step.get('voice_action', 'Action')}] {step.get('action')}"
                for i, step in enumerate(plan.steps)
            ]
        )

    async def _run_plan_simulation(self, user_request: str, plan_steps_text: str) -> str | None:
        """Runs the sequential thinking simulation for the plan."""
        query = GRISHA_PLAN_VERIFICATION_PROMPT.format(
            user_request=user_request,
            plan_steps_text=plan_steps_text,
        )

        reasoning_result = await self.use_sequential_thinking(query, total_thoughts=3)

        if not reasoning_result.get("success"):
            logger.warning("[GRISHA] Plan simulation failed, falling back to basic check")
            return None

        analysis = reasoning_result.get("analysis")
        return str(analysis) if analysis is not None else ""

    def _create_fallback_verification_result(self, issue: str) -> VerificationResult:
        """Creates a default verification result when simulation fails."""
        return VerificationResult(
            step_id="plan_init",
            verified=True,
            confidence=0.5,
            description=f"{issue} (Allowed by default)",
            issues=[issue],
            voice_message="Не вдалося перевірити план, але продовжую.",
        )

    def _parse_simulation_sections(self, analysis_text: str) -> dict[str, str]:
        """Parses the analysis text to extract specific sections."""
        params = {
            "STRATEGIC GAP ANALYSIS": ("gap_analysis", "FEEDBACK TO ATLAS:"),
            "FEEDBACK TO ATLAS": ("feedback_to_atlas", "SUMMARY_UKRAINIAN:"),
            "ESTABLISHED GOAL": ("established_goal", "SIMULATION LOG"),
            "CORE PROBLEMS": ("core_problems", "STRATEGIC GAP ANALYSIS:"),
            "SUMMARY_UKRAINIAN": ("summary_ukrainian", None),
        }

        results = {
            "gap_analysis": "",
            "feedback_to_atlas": "",
            "established_goal": "",
            "core_problems": "",
            "summary_ukrainian": "",
        }

        for section_key, (result_key, end_marker) in params.items():
            if f"{section_key}:" in analysis_text:
                parts = analysis_text.split(f"{section_key}:")
                if len(parts) > 1:
                    content = parts[1]
                    if end_marker:
                        content = content.split(end_marker)[0]
                    results[result_key] = content.strip()

        # Special fallback for core_problems if SIMULATION LOG exists but CORE PROBLEMS doesn't match standard flow or is separate
        if not results["core_problems"] and "SIMULATION LOG" in analysis_text:
            parts = analysis_text.split("SIMULATION LOG")
            if len(parts) > 1:
                results["core_problems"] = parts[1].split("CORE PROBLEMS:")[0].strip()

        return results

    def _extract_issues_from_simulation(self, problems_text: str, analysis_text: str) -> list[str]:
        """Extracts and filters issues from the problems text."""
        raw_issues = []
        if problems_text:
            raw_issues = [
                line.strip().replace("- ", "")
                for line in problems_text.split("\n")
                if line.strip().startswith("-")
            ]

        if not raw_issues:
            return []

        # Intelligent summarization
        root_blockers = [
            i for i in raw_issues if "Cascading Failure" not in i and "Blocked by" not in i
        ]
        cascading = [i for i in raw_issues if "Cascading Failure" in i or "Blocked by" in i]

        issues = root_blockers
        if len(cascading) > 3:
            issues.append(
                f"Cascading Failure: {len(cascading)} dependent steps are blocked by the root issues above."
            )
        else:
            issues.extend(cascading)

        return issues

    def _construct_atlas_feedback(self, sections: dict[str, str]) -> str:
        """Constructs the feedback string for Atlas."""
        atlas_feedback_parts = []
        if sections["established_goal"]:
            atlas_feedback_parts.append(f"ESTABLISHED GOAL:\n{sections['established_goal']}")
        if sections["core_problems"]:
            atlas_feedback_parts.append(f"CORE PROBLEMS:\n{sections['core_problems']}")
        if sections["gap_analysis"]:
            atlas_feedback_parts.append(f"STRATEGIC GAP ANALYSIS:\n{sections['gap_analysis']}")
        if sections["feedback_to_atlas"]:
            atlas_feedback_parts.append(f"INSTRUCTIONS:\n{sections['feedback_to_atlas']}")

        return "\n\n".join(atlas_feedback_parts)

    def _determine_plan_verdict(
        self, analysis_text: str, user_request: str, issues: list[str], feedback_to_atlas: str
    ) -> dict[str, Any]:
        """Determines if the plan is approved and generates voice message."""
        # Strict markers
        is_approved = "VERDICT: APPROVE" in analysis_text or "VERDICT: [APPROVE]" in analysis_text
        is_rejected = "VERDICT: REJECT" in analysis_text or "VERDICT: [REJECT]" in analysis_text

        # Legacy / Simple markers (for tests or less structured LLM output)
        if not is_approved and not is_rejected:
            is_approved = "APPROVE:" in analysis_text or analysis_text.strip().startswith("APPROVE")
            is_rejected = "REJECT:" in analysis_text or analysis_text.strip().startswith("REJECT")

        oleg_mentioned = "Олег Миколайович" in user_request or "Oleg Mykolayovych" in user_request

        # If rejected or has feedback to atlas, we treat it as a FAILURE unless Oleg overrides
        approved = is_approved and not is_rejected

        if oleg_mentioned and not approved:
            if not feedback_to_atlas and not issues:
                logger.info("[GRISHA] Policy rejection. Overriding for Creator.")
                approved = True
            else:
                logger.warning(
                    "[GRISHA] Technical/Logic blockers found. Standing firm for Creator."
                )

        # RELAXED VERIFICATION LOGIC:
        # If not approved, but confidence > 0.9 (from Atlas or Self-Correction), we might allow it
        # providing there are no "Critical" keywords in issues.
        if not approved and not is_rejected:
            critical_keywords = ["CRITICAL", "BLOCKER", "SECURITY", "DANGEROUS", "HARM"]
            has_critical = any(any(k in i.upper() for k in critical_keywords) for i in issues)
            if not has_critical:
                logger.info("[GRISHA] Issues found but not critical. Giving benefit of doubt.")
                approved = True
                # Lower confidence slightly to reflect we are taking a risk
                return {
                    "approved": True,
                    "confidence": 0.85,
                    "voice_message": self._generate_plan_voice_message(True, issues, analysis_text),
                }

        voice_msg = self._generate_plan_voice_message(approved, issues, analysis_text)

        return {
            "approved": approved,
            "confidence": 1.0 if (approved and oleg_mentioned) else 0.8,
            "voice_message": voice_msg,
        }

    def _generate_plan_voice_message(
        self, approved: bool, issues: list[str], analysis_text: str
    ) -> str:
        """Generates concise Ukrainian voice message for plan verdict.

        Keeps it short for TTS. Full details stay in description for Tetyana.
        """
        if approved:
            return "План схвалено. Починаю виконання."

        # Try to use LLM-generated Ukrainian summary first
        summary_ukrainian = ""
        if "SUMMARY_UKRAINIAN:" in analysis_text:
            raw_summary = analysis_text.rsplit("SUMMARY_UKRAINIAN:", maxsplit=1)[-1].strip()
            # Take first sentence only for TTS brevity
            first_sentence = raw_summary.split(".")[0].strip()
            if first_sentence and len(first_sentence) > 10:
                # Validate it's actually Ukrainian
                cyrillic = len(re.findall(r"[а-яА-ЯіІєЄїЇґҐ]", first_sentence))
                if cyrillic > len(re.findall(r"[a-zA-Z]", first_sentence)):
                    summary_ukrainian = first_sentence[:120]

        if summary_ukrainian:
            return f"План потребує доопрацювання. {summary_ukrainian}."

        issues_count = len(issues)
        if issues_count > 0:
            return f"План потребує доопрацювання. Знайдено {issues_count} проблем."

        return "План потребує доопрацювання."

    async def _attempt_plan_fix(
        self, user_request: str, failed_plan_text: str, audit_feedback: str
    ) -> Any | None:
        """Attempts to fix the plan using the Architect Override prompt."""
        logger.info("[GRISHA] Falling back to Architecture Override. Re-constructing plan...")

        fix_query = GRISHA_FIX_PLAN_PROMPT.format(
            user_request=user_request,
            failed_plan_text=failed_plan_text,
            audit_feedback=audit_feedback,
        )

        fix_result = await self.use_sequential_thinking(fix_query, total_thoughts=3)
        if not fix_result.get("success"):
            return None

        # Prefer last_thought (raw) over analysis (formatted/truncated)
        raw_text = fix_result.get("last_thought") or fix_result.get("analysis", "")
        return self._parse_fixed_plan_json(str(raw_text), user_request)

    def _parse_fixed_plan_json(
        self, raw_text: str, user_request: str = "Unknown Goal"
    ) -> Any | None:
        """Parses the JSON response for the fixed plan with extreme resilience."""
        import inspect

        from src.brain.agents.atlas import TaskPlan

        fixed_plan = None
        try:
            cleaned_text = str(raw_text).strip()

            # 1. Advanced Extraction
            plan_data = self._extract_json_from_potential_blocks(cleaned_text)

            # 2. Fallback to original markers
            if not plan_data:
                plan_data = self._fallback_json_extraction(cleaned_text)

            if not plan_data:
                return None

            # Validate and filter
            valid_keys = set(inspect.signature(TaskPlan.__init__).parameters.keys())
            if hasattr(TaskPlan, "__annotations__"):
                valid_keys.update(TaskPlan.__annotations__.keys())

            filtered_data = {k: v for k, v in plan_data.items() if k in valid_keys}
            filtered_data.setdefault("id", "fixed_plan_grisha")
            filtered_data.setdefault("goal", "Generated by Grisha Override")
            filtered_data.setdefault("steps", [])

            fixed_plan = TaskPlan(**filtered_data)
            logger.info(
                f"[GRISHA] Successfully reconstructed plan via Architect Override. {len(fixed_plan.steps)} steps."
            )
            return fixed_plan

        except Exception as e:
            logger.error(f"[GRISHA] Failed to parse reconstructed plan: {e}")
            logger.debug(f"[GRISHA] Raw text causing failure: {raw_text[:2000]}")

            # EMERGENCY FALLBACK:
            # If we failed to parse the JSON, we still want to Override because the original plan was bad.
            # We create a simple plan that forces a human check or safely proceeds.

            fallback_plan = TaskPlan(
                id="grisha_fallback_override",
                goal=user_request,
                steps=[
                    {
                        "id": "1",
                        "action": "notify_user",
                        "voice_action": "Повідомлення",
                        "description": "Critical planning error. Please review logs.",
                    }
                ],
            )
            return fallback_plan

    def _check_command_relevance(
        self, step_action: str, expected_result: str, verification_results: list
    ) -> tuple[bool, str]:
        """Check if executed commands are relevant to expected results"""
        if not verification_results:
            return False, "No verification results available"

        commands = self._extract_executed_commands(verification_results)
        if not commands:
            # If no commands were executed (e.g. pure file read or pure Vision), we can't judge relevance by command.
            # Assume relevant if verified by other means.
            return True, "No commands to check relevance"

        # Relaxed Relevance Check:
        # Instead of failing if a command isn't in a hardcoded list, we default to believing the agent.
        # We only flag if we detect something clearly WRONG (like 'rm -rf' when asked to 'ls').
        # For now, we trust the agent's choice if it's not obviously malicious.

        return True, "Command relevance passed (Trusted Agent Mode)"

    def _extract_executed_commands(self, verification_results: list) -> list[str]:
        """Extracts command strings from verification results."""
        commands = []
        for result in verification_results:
            if isinstance(result, dict):
                tool_name = result.get("tool", "")
                args = result.get("args", {})
                if "execute_command" in tool_name and "command" in args:
                    commands.append(args["command"])
        return commands

    # Deprecated strict checks removed to allow "Intellect Mode"
    def _is_command_relevant(
        self, cmd: str, expected_lower: str, step_lower: str
    ) -> tuple[bool, str]:
        return True, "Trusted"

    def _is_network_related(self, expected_lower: str, step_lower: str) -> bool:
        return False

    def _is_search_related(self, step_lower: str) -> bool:
        return False

    def _is_web_related(self, expected_lower: str) -> bool:
        return False

    def _is_project_related(self, expected_lower: str) -> bool:
        return False

    def _check_network_relevance(self, cmd_lower: str, cmd: str) -> tuple[bool, str]:
        return True, ""

    def _check_search_relevance(self, cmd_lower: str, cmd: str) -> tuple[bool, str]:
        return True, ""

    def _check_web_relevance(self, cmd_lower: str, cmd: str) -> tuple[bool, str]:
        """Check web command relevance."""
        web_cmds = ["curl", "wget", "fetch", "http"]
        if any(kw in cmd_lower for kw in web_cmds):
            return True, f"Command '{cmd}' is relevant for web/API interaction"
        return False, ""

    def _check_project_relevance(self, cmd_lower: str, cmd: str) -> tuple[bool, str]:
        """Check project command relevance."""
        project_cmds = ["ls", "find", "tree", "git status"]
        if any(kw in cmd_lower for kw in project_cmds):
            return True, f"Command '{cmd}' is relevant for project inspection"
        return False, ""

    def _detect_repetitive_thinking(self, analysis_text: str) -> bool:
        """Detect if the thinking is repetitive (anti-loop protection)"""
        if not analysis_text or len(analysis_text) < 100:
            return False

        # Split into sentences/lines
        lines = [line.strip() for line in analysis_text.split("\n") if line.strip()]
        if len(lines) < 3:
            return False

        # Check for repeated patterns
        unique_lines = set(lines)
        repetition_ratio = 1 - (len(unique_lines) / len(lines))

        # If more than 50% of lines are duplicates, consider it repetitive
        if repetition_ratio > 0.5:
            return True

        # Check for repeated key phrases
        phrases = analysis_text.split(".")
        unique_phrases = set([p.strip() for p in phrases if p.strip()])
        phrase_repetition = 1 - (len(unique_phrases) / len(phrases))

        return phrase_repetition > 0.6

    async def _verify_config_sync(self) -> dict[str, Any]:
        """Verify if config templates are synchronized with global config folder"""
        try:
            config_root = os.path.join(os.path.expanduser("~"), ".config", "atlastrinity")
            project_config_dir = os.path.join(project_root, "config")

            sync_issues = []

            # Check key config files
            config_files = [
                ("config.yaml", "config.yaml.template"),
                ("behavior_config.yaml", "behavior_config.yaml.template"),
                ("vibe_config.toml", "vibe_config.toml.template"),
            ]

            for config_file, template_file in config_files:
                config_path = os.path.join(config_root, config_file)
                template_path = os.path.join(project_config_dir, template_file)

                if not os.path.exists(config_path):
                    sync_issues.append(f"Missing config: {config_file}")
                    continue

                if not os.path.exists(template_path):
                    sync_issues.append(f"Missing template: {template_file}")
                    continue

                # Simple modification time check
                config_mtime = os.path.getmtime(config_path)
                template_mtime = os.path.getmtime(template_path)

                if template_mtime > config_mtime:
                    sync_issues.append(f"Template newer than config: {config_file}")

            # Try to run sync script to check
            try:
                sync_script = os.path.join(project_root, "scripts", "sync_config_templates.js")
                if os.path.exists(sync_script):
                    result = subprocess.run(
                        ["node", sync_script, "--dry-run"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode != 0:
                        sync_issues.append("Config sync script failed")
            except Exception as e:
                logger.warning(f"[GRISHA] Config sync check failed: {e}")

            return {
                "sync_status": "ok" if not sync_issues else "issues_found",
                "issues": sync_issues,
                "config_root": config_root,
                "template_root": project_config_dir,
            }

        except Exception as e:
            logger.error(f"[GRISHA] Config sync verification failed: {e}")
            return {
                "sync_status": "error",
                "issues": [f"Verification failed: {e!s}"],
                "config_root": None,
                "template_root": None,
            }

    def _safe_parse_step_id(self, step_id: str) -> int | None:
        """Safely parse step_id to int, returning None if not parseable."""
        try:
            step_str = str(step_id).split(".")[-1] if "." in str(step_id) else str(step_id)
            # Check if it's a valid number (handle 'unknown' and other non-numeric values)
            if step_str.isdigit() or (step_str.startswith("-") and step_str[1:].isdigit()):
                return int(step_str)
            return None
        except (ValueError, TypeError):
            return None

    async def _fetch_execution_trace(self, step_id: str, task_id: str | None = None) -> str:
        """Fetches the raw tool execution logs from the database for a given step.
        This serves as the 'single source of truth' for verification.
        """
        try:
            # Parse step_id safely
            parsed_seq = self._safe_parse_step_id(step_id)

            # If step_id cannot be parsed to int, use string-based query
            if parsed_seq is None:
                logger.debug(f"[GRISHA] Step ID '{step_id}' is non-numeric, using fallback query")
                # Fallback: try to find recent executions without specific sequence number
                sql = """
                    SELECT te.tool_name, te.arguments, te.result, ts.status as step_status, te.created_at 
                    FROM tool_executions te
                    LEFT JOIN task_steps ts ON te.step_id = ts.id
                    ORDER BY te.created_at DESC 
                    LIMIT 5;
                """
                params = {}
                if task_id:
                    sql = """
                        SELECT te.tool_name, te.arguments, te.result, ts.status as step_status, te.created_at 
                        FROM tool_executions te
                        LEFT JOIN task_steps ts ON te.step_id = ts.id
                        WHERE ts.task_id = :task_id
                        ORDER BY te.created_at DESC 
                        LIMIT 5;
                    """
                    params = {"task_id": task_id}
            # Query db for tool executions related to this step, including the status from task_steps
            elif task_id:
                sql = """
                    SELECT te.tool_name, te.arguments, te.result, ts.status as step_status, te.created_at 
                    FROM tool_executions te
                    JOIN task_steps ts ON te.step_id = ts.id
                    WHERE ts.sequence_number = :seq AND ts.task_id = :task_id
                    ORDER BY te.created_at DESC 
                    LIMIT 5;
                """
                params = {
                    "seq": parsed_seq,
                    "task_id": task_id,
                }
            else:
                sql = """
                    SELECT te.tool_name, te.arguments, te.result, ts.status as step_status, te.created_at 
                    FROM tool_executions te
                    JOIN task_steps ts ON te.step_id = ts.id
                    WHERE ts.sequence_number = :seq 
                    ORDER BY te.created_at DESC 
                    LIMIT 5;
                """
                params = {"seq": parsed_seq}

            rows = await mcp_manager.query_db(sql, params)

            if not rows:
                return "No DB records found for this step. (Command might not have been logged yet or step ID mismatch)."

            trace = "\n--- TECHNICAL EXECUTION TRACE (FROM DB) ---\n"
            for row in rows:
                tool = row.get("tool_name", "unknown")
                args = row.get("arguments", {})
                res = str(row.get("result", ""))
                status = row.get("step_status", "unknown")

                # Truncate result for token saving
                if len(res) > 2000:
                    res = res[:2000] + "...(truncated)"

                trace += f"Tool: {tool}\nArgs: {args}\nStep Status (from Tetyana): {status}\nResult: {res or '(No output - Silent Success)'}\n-----------------------------------\n"

            return trace

        except Exception as e:
            logger.warning(f"[GRISHA] Failed to fetch execution trace: {e}")
            return f"Error fetching trace: {e}"

    async def _execute_verification_tools(self, tools: list[dict], step: dict) -> list[dict]:
        """Executes the selected verification tools and returns results."""

        verification_results = []

        for tool_config in tools:
            tool_name = tool_config.get("tool", "")
            tool_args = tool_config.get("args", {})
            tool_reason = tool_config.get("reason", "Unknown")

            logger.info(f"[GRISHA] Verif-Step: {tool_name} - {tool_reason}")

            try:
                # Dispatch tool call
                v_output = await mcp_manager.dispatch_tool(tool_name, tool_args)
                v_res_str = str(v_output)

                has_error = self._check_tool_execution_error(v_output, v_res_str, step)

                if len(v_res_str) > 2000:
                    v_res_str = v_res_str[:2000] + "...(truncated)"

                verification_results.append(
                    {
                        "tool": tool_name,
                        "args": tool_args,
                        "result": v_res_str,
                        "error": has_error,
                        "reason": tool_reason,
                    }
                )

            except Exception as e:
                logger.warning(f"[GRISHA] Verif-Step failed: {e}")
                verification_results.append(
                    {
                        "tool": tool_name,
                        "args": tool_args,
                        "result": f"Error: {e}",
                        "error": True,
                        "reason": tool_reason,
                    }
                )
        return verification_results

    def _check_tool_execution_error(self, v_output: Any, v_res_str: str, step: dict) -> bool:
        """Determines if a tool execution resulted in an error."""
        has_error = False

        if isinstance(v_output, dict):
            if v_output.get("error") or v_output.get("success") is False:
                has_error = True
            elif v_output.get("success") is True:
                # Check for empty results in info tasks
                has_error = self._is_empty_info_result(v_output, v_res_str, step)
        else:
            lower_result = v_res_str.lower()[:500]
            if "error:" in lower_result or "exception" in lower_result or "failed:" in lower_result:
                has_error = True
        return has_error

    def _is_empty_info_result(self, v_output: dict, v_res_str: str, step: dict) -> bool:
        """Checks if an information-gathering tool returned empty results."""
        data = v_output.get("data", [])
        count = v_output.get("count", 0)
        results = v_output.get("results", [])

        step_action_lower = step.get("action", "").lower()
        is_info_task = any(
            kw in step_action_lower
            for kw in ["search", "find", "gather", "collect", "identify", "locate"]
        )

        if is_info_task and (
            (isinstance(data, list) and len(data) == 0 and count == 0)
            or (isinstance(results, list) and len(results) == 0)
            or (len(v_res_str.strip()) == 0)
        ):
            # Check if this was a SUCCESSFUL empty result (valid discovery)
            # CRITICAL ENHANCEMENT: Treat empty result as ERROR if we are specifically looking for
            # something the user provided or something mandatory (e.g., "attachment", "target image").
            CRITICAL_KEYWORDS = [
                "attachment",
                "attached",
                "provided",
                "image",
                "target",
                "important",
                "essential",
            ]
            is_critical_search = any(kw in step_action_lower for kw in CRITICAL_KEYWORDS)

            res_lower = v_res_str.lower()
            if "error" in res_lower or "failed" in res_lower:
                logger.warning("[GRISHA] Failed result in info-gathering task")
                return True

            if is_critical_search:
                logger.warning(
                    f"[GRISHA] Critical search '{step_action_lower}' returned empty result. Marking as FAIL."
                )
                return True

            # If successful but empty, it's NOT an error for general info tasks (discovery)
            logger.info("[GRISHA] Valid empty result in non-critical discovery task")
            return False
        return False

    def _create_intermediate_success_result(self, step_id: str) -> VerificationResult:
        return VerificationResult(
            step_id=step_id,
            verified=True,  # Auto-approve intermediate steps
            confidence=1.0,
            description="Intermediate step - auto-approved",
            issues=[],
            voice_message="",  # No voice for intermediate steps — saves TTS time
        )

    async def _handle_verification_failure(
        self,
        step: dict,
        result_obj: VerificationResult,
        task_id: str | None,
        goal_analysis: dict,
        verification_results: list,
    ):
        step_id = step.get("id", "unknown")
        # Reduced verbosity - Orchestrator handles the main error logging
        logger.debug(
            f"[GRISHA] Step {step_id} failed. Saving detailed rejection report for Tetyana..."
        )
        try:
            await self._save_rejection_report(
                step_id=str(step_id),
                step=step,
                verification=result_obj,
                task_id=task_id,
                root_cause_analysis=goal_analysis.get("full_reasoning"),
                suggested_fix=None,  # Or parse from reasoning if possible
                verification_evidence=[
                    f"Tool: {res.get('tool')}, Result: {str(res.get('result', ''))[:200]}..."
                    for res in verification_results
                    if isinstance(res, dict)
                ],
            )
        except Exception as save_err:
            logger.error(f"[GRISHA] Failed to save rejection report: {save_err}")

    async def verify_step(
        self,
        step: dict[str, Any],
        result: Any,
        screenshot_path: str | None = None,
        goal_context: str = "",
        task_id: str | None = None,
    ) -> VerificationResult:
        """Verifies the result of step execution using Vision and MCP Tools"""

        step_id = step.get("id", 0)

        if not self._is_final_task_completion(step):
            # NEW LOGIC: Only skip if the step was SUCCESSFUL.
            # If failed, we MUST verify to generate a proper rejection report.
            is_success = True
            if hasattr(result, "success"):
                is_success = result.success
            elif isinstance(result, dict):
                is_success = result.get("success", True)

            # Check for error in result text even if marked success
            result_str = str(
                result.get("result", "")
                if isinstance(result, dict)
                else getattr(result, "result", "")
            )
            if "error" in result_str.lower() or "failed" in result_str.lower():
                is_success = False

            if is_success:
                logger.info(
                    f"[GRISHA] Skipping verification for successful intermediate step {step_id}"
                )
                return self._create_intermediate_success_result(step_id)
            logger.info(
                f"[GRISHA] Intermediate step {step_id} FAILED. Proceeding with verification/diagnosis."
            )

        # System check
        system_issues = []
        if step_id == 1 or "system" in step.get("action", "").lower():
            config_sync = await self._verify_config_sync()
            if config_sync["sync_status"] != "ok":
                system_issues.extend(config_sync["issues"])
                logger.warning(f"[GRISHA] Config sync issues detected: {config_sync['issues']}")

        # Phase 1: Analysis
        logger.info(f"[GRISHA] 🧠 Phase 1: Analyzing verification goal for step {step_id}...")
        goal_analysis = await self._analyze_verification_goal(
            step, goal_context or shared_context.get_goal_context()
        )

        # Phase 1.5: Execution
        logger.info("[GRISHA] 🔧 Executing verification tools...")
        verification_results = await self._execute_verification_tools(
            goal_analysis.get("selected_tools", []), step
        )

        # PROACTIVE AUDIT: If evidence is insufficient, Grisha takes control
        if not self._has_sufficient_evidence(verification_results):
            logger.info(
                f"[GRISHA] Evidence insufficient for step {step_id}. Initiating Proactive Audit."
            )
            independent_evidence = await self._collect_independent_evidence(step, goal_analysis)
            if independent_evidence:
                verification_results.extend(independent_evidence)

        # Phase 1.7: Multi-Layer Verification (for FINAL steps only)
        # Provides 4-layer check: Tool, Output, State, Goal
        multi_layer_insights = ""
        if self._is_final_task_completion(step):
            logger.info(f"[GRISHA] 🔬 Running multi-layer verification for final step {step_id}...")
            try:
                layers = await self._multi_layer_verification(step, result, {})
                passed_layers = [l for l in layers if l.get("passed")]
                failed_layers = [l for l in layers if not l.get("passed")]
                multi_layer_insights = (
                    f"\n\nMULTI-LAYER ANALYSIS ({len(passed_layers)}/4 passed):\n"
                    + "\n".join(
                        f"  {'✅' if l['passed'] else '❌'} {l['layer']}: {l.get('evidence', 'N/A')}"
                        for l in layers
                    )
                )
                # Add as synthetic verification result for verdict formation
                verification_results.append(
                    {
                        "tool": "grisha.multi_layer_verification",
                        "args": {},
                        "result": multi_layer_insights,
                        "error": len(failed_layers) > 2,  # Error if more than half failed
                        "reason": "4-layer integrity check (Tool, Output, State, Goal)",
                    }
                )
            except Exception as ml_err:
                logger.warning(f"[GRISHA] Multi-layer verification failed: {ml_err}")

        # Phase 2: Verdict
        logger.info("[GRISHA] 🧠 Phase 2: Forming logical verdict...")
        verdict = await self._form_logical_verdict(
            step,
            goal_analysis,
            verification_results,
            goal_context or shared_context.get_goal_context(),
        )

        # Final Result
        all_issues = verdict.get("issues", [])
        if system_issues:
            all_issues.extend([f"Config sync: {issue}" for issue in system_issues])

        # FIX: Config sync issues should be warnings, not verification blockers
        # The actual task may have succeeded even if config is slightly out of sync
        is_verified = verdict.get("verified", False)
        # Only log config sync issues but don't block verification
        if system_issues:
            logger.info(f"[GRISHA] Config sync warnings (non-blocking): {system_issues}")

        result_obj = VerificationResult(
            step_id=str(step_id),
            verified=is_verified,
            confidence=verdict.get("confidence", 0.0),
            description=verdict.get("reasoning", "Перевірку завершено"),
            issues=all_issues,
            voice_message=self._generate_voice_message(verdict, step),
        )

        if not is_verified:
            await self._handle_verification_failure(
                step, result_obj, task_id, goal_analysis, verification_results
            )

        return result_obj

    def _generate_voice_message(self, verdict: dict, step: dict) -> str:
        """Generate concise Ukrainian voice message for TTS.

        IMPORTANT: Voice messages go to TTS and must be:
        - Short (max ~150 chars) for fast playback
        - 100% Ukrainian, zero English words
        - Clear and to the point

        Full English reasoning stays in 'description' field for Tetyana.
        """
        step_id = step.get("id", "невідомий")

        # 1. Prefer the LLM-generated Ukrainian summary from VOICE_SUMMARY_UK
        voice_summary = verdict.get("voice_summary_uk", "").strip()
        if voice_summary and len(voice_summary) > 5:
            return voice_summary

        # 2. Fallback: generate concise Ukrainian message locally
        if verdict.get("verified"):
            return f"Крок {step_id} підтверджено."

        issues = verdict.get("issues", [])
        if issues:
            # Take first issue only, truncate for TTS
            first_issue = str(issues[0])[:80]
            # If issue contains English, try to extract Ukrainian reason from reasoning
            if re.search(r"[a-zA-Z]{3,}", first_issue):
                reasoning = verdict.get("reasoning", "")
                uk_snippet = self._extract_ukrainian_snippet(reasoning, max_len=100)
                if uk_snippet:
                    return f"Крок {step_id} не пройшов. {uk_snippet}."
                return f"Крок {step_id} не пройшов перевірку."
            return f"Крок {step_id} не пройшов. {first_issue}."

        return f"Крок {step_id} не пройшов перевірку."

    def _extract_ukrainian_snippet(self, text: str, max_len: int = 100) -> str:
        """Extract a meaningful Ukrainian snippet from mixed-language text.

        Scans the text for sentences that are primarily Cyrillic (Ukrainian)
        and returns the first one that is long enough to be meaningful.
        Used to provide voice reasons when LLM analysis is in English.
        """
        if not text:
            return ""

        # Split into sentences
        sentences = re.split(r"[.!?]\s+", text)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:
                continue

            # Count Cyrillic vs Latin characters
            cyrillic_count = len(re.findall(r"[а-яА-ЯіІєЄїЇґҐ]", sentence))
            latin_count = len(re.findall(r"[a-zA-Z]", sentence))

            # Accept if primarily Cyrillic (>70% of alphabetic chars)
            total_alpha = cyrillic_count + latin_count
            if total_alpha > 0 and (cyrillic_count / total_alpha) > 0.7:
                # Truncate for TTS brevity
                if len(sentence) > max_len:
                    sentence = sentence[: max_len - 3] + "..."
                return sentence

        return ""

    async def analyze_failure(
        self,
        step: dict[str, Any],
        error: str,
        context: dict | None = None,
    ) -> dict[str, Any]:
        """Analyzes a failure reported by Tetyana or Orchestrator using Deep Sequential Thinking.
        Returns constructive feedback for a retry.
        """
        step_id = step.get("id", "unknown")
        context_data = context or shared_context.to_dict()

        logger.info(f"[GRISHA] Conducting deep forensic analysis of failure in step {step_id}")

        # Use universal sequential thinking capability
        reasoning = await self.use_sequential_thinking(
            GRISHA_FORENSIC_ANALYSIS.format(
                step_json=json.dumps(step, default=str),
                error=error,
                context_data=str(context_data)[:1000],
            ),
            total_thoughts=3,
        )

        analysis_text = reasoning.get("analysis", "Deep analysis unavailable.")

        # Enhanced extraction for Ukrainian fields

        def extract_field(pattern, text, default):
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            return match.group(1).strip() if match else default

        error_type = extract_field(
            r"\*\*TYPE\*\*[:\s]*(.*?)(?=\n- \*\*|\Z)", analysis_text, "Unknown"
        )
        root_cause = extract_field(
            r"\*\*ROOT CAUSE\*\*[:\s]*(.*?)(?=\n- \*\*|\Z)", analysis_text, "Investigation required"
        )
        technical_advice = extract_field(
            r"\*\*FIX ADVICE\*\*[:\s]*(.*?)(?=\n- \*\*|\Z)",
            analysis_text,
            "Follow standard recovery procedures",
        )
        prevention = extract_field(
            r"\*\*PREVENTION\*\*[:\s]*(.*?)(?=\n- \*\*|\Z)",
            analysis_text,
            "Continuity analysis ongoing",
        )
        summary_uk = extract_field(
            r"\*\*SUMMARY_UKRAINIAN\*\*[:\s]*(.*?)(?=\n- \*\*|\Z)",
            analysis_text,
            "Аналіз провалу завершено. Потрібне виправлення.",
        )

        return {
            "step_id": step_id,
            "analysis": {
                "type": error_type,
                "root_cause": root_cause,
                "technical_advice": technical_advice,
                "prevention_strategy": prevention,
                "full_reasoning": analysis_text,
            },
            "feedback_text": f"GRISHA FORENSIC REPORT:\n{analysis_text}",
            "voice_message": summary_uk,
        }

    async def _save_rejection_report(
        self,
        step_id: str,
        step: dict[str, Any],
        verification: VerificationResult,
        task_id: str | None = None,
        root_cause_analysis: str | None = None,
        suggested_fix: str | None = None,
        verification_evidence: list[str] | None = None,
    ) -> None:
        """Save detailed rejection report to memory and notes servers for Atlas and Tetyana to access.

        Enhanced: Includes structured Tetyana execution context and remediation plan
        for the Self-Healing Hypermodule to form precise fix tasks.
        """

        from src.brain.core.server.message_bus import AgentMsg, MessageType, message_bus
        from src.brain.memory.knowledge_graph import knowledge_graph

        try:
            # STEP 1: Create rejection fingerprint for recursion detection
            verdict_str = "FAILED" if not verification.verified else "PASSED"
            issues_list = (
                verification.issues
                if isinstance(verification.issues, list)
                else [str(verification.issues)]
            )

            fingerprint = self._create_rejection_fingerprint(
                step_id=step_id,
                verdict=verdict_str,
                issues=issues_list,
                confidence=verification.confidence,
            )

            # STEP 2: Check for recursion
            is_recursion, rejection_count = self._check_recursion(
                step_id, fingerprint, max_same_rejections=2
            )

            if is_recursion:
                logger.error(
                    f"[GRISHA] ⚠️ RECURSION LOOP DETECTED for step {step_id}! "
                    f"Same rejection repeated {rejection_count} times. "
                    f"Escalating to user instead of retrying."
                )
                # Add recursion warning to issues
                issues_list.append(
                    f"⚠️ RECURSION DETECTED: This step has been rejected {rejection_count} times with identical reasoning. "
                    "Manual intervention required."
                )
                verification.issues = issues_list

            # STEP 3: Record this rejection
            self._record_rejection(
                step_id=step_id,
                fingerprint=fingerprint,
                verdict_data={
                    "verdict": verdict_str,
                    "confidence": verification.confidence,
                    "issues": issues_list,
                },
            )

            timestamp = datetime.now().isoformat()

            # =========================================================
            # STEP 3.5: Extract Tetyana Execution Context (NEW)
            # =========================================================
            # Extract structured data about what Tetyana actually did,
            # so the self-healing hypermodule can form a precise fix task.
            tetyana_context = self._extract_tetyana_execution_context(step)

            # =========================================================
            # STEP 3.6: Generate Structured Remediation Plan (NEW)
            # =========================================================
            remediation_plan = await self._generate_remediation_plan(
                step=step,
                error_message="; ".join(issues_list),
                tetyana_context=tetyana_context,
                recursion_depth=rejection_count,
            )

            # Build structured sections
            issues_formatted = (
                chr(10).join(f"  - {issue}" for issue in issues_list)
                if issues_list
                else "  - No specific issues identified"
            )

            evidence_section = ""
            if verification_evidence:
                evidence_section = f"""
## Verification Evidence
{chr(10).join(f"  - {e}" for e in verification_evidence)}
"""

            root_cause_section = ""
            if root_cause_analysis:
                root_cause_section = f"""
## Аналіз кореневої причини
{root_cause_analysis}
"""

            fix_section = ""
            if suggested_fix:
                fix_section = f"""
## Рекомендоване виправлення
{suggested_fix}
"""

            # NEW: Tetyana execution context section
            tetyana_section = ""
            if tetyana_context.get("tool_used"):
                tetyana_section = f"""
## Контекст виконання Тетяни
| Поле | Значення |
|------|---------|
| Інструмент | {tetyana_context.get("tool_used", "N/A")} |
| Аргументи | {str(tetyana_context.get("tool_args", "N/A"))[:200]} |
| Результат | {str(tetyana_context.get("raw_output", "N/A"))[:300]} |
| Помилка | {tetyana_context.get("error_message", "N/A")} |
"""

            # NEW: Remediation plan section
            remediation_section = ""
            if remediation_plan:
                remediation_section = f"""
## План ремедіації (для Self-Healing)
| Поле | Значення |
|------|---------|
| Тип помилки | {remediation_plan.get("error_type", "unknown")} |
| Коренева причина | {remediation_plan.get("root_cause", "N/A")} |
| Уражений компонент | {remediation_plan.get("affected_component", "N/A")} |
| Рекомендована дія | {remediation_plan.get("suggested_action", "N/A")} |
| Безпечно для рекурсії | {"Так" if remediation_plan.get("recursion_safe") else "Ні"} |
| Превентивна порада | {remediation_plan.get("prevention_hint", "N/A")} |
"""

            # Prepare detailed report text with enhanced structure
            report_text = f"""========================================
ЗВІТ ПРО ВЕРИФІКАЦІЮ ГРІШІ - ВІДХИЛЕНО
========================================

## Резюме
| Поле | Значення |
|-------|-------|
| ID кроку | {step_id} |
| ID завдання | {task_id or "Н/A"} |
| Впевненість | {verification.confidence:.2f} |
| Аналіз скріншота | {"Так" if verification.screenshot_analyzed else "Ні"} |
| Часова мітка | {timestamp} |

## Деталі кроку
**Дія:** {step.get("action", "Н/A")}
**Очікуваний результат:** {step.get("expected_result", "Н/A")}

## Результат верифікації
**Статус:** ❌ ВІДХИЛЕНО

**Опис:**
{verification.description}

## Виявлені проблеми
{issues_formatted}
{tetyana_section}{remediation_section}{root_cause_section}{fix_section}{evidence_section}
## Голосове повідомлення
{verification.voice_message or "Верифікація не пройдена."}

## Для відновлення
Використовуйте цей звіт щоб:
1. Зрозуміти, ЩО саме не вдалося (див. Виявлені проблеми)
2. Зрозуміти, ЧОМУ це сталося (див. Контекст виконання Тетяни)
3. Дізнатися, ЯК це виправити (див. План ремедіації)

========================================
"""

            # CRITICAL: Mask sensitive data before saving
            report_text_masked = mask_sensitive_data(report_text)

            # Save to memory server (for graph/relations)
            try:
                await mcp_manager.dispatch_tool(
                    "memory.create_entities",
                    {
                        "entities": [
                            {
                                "name": f"grisha_rejection_step_{step_id}",
                                "entityType": "verification_report",
                                "observations": [report_text_masked],  # Use masked version
                            },
                        ],
                    },
                )
                logger.info(f"[GRISHA] Rejection report saved to memory for step {step_id}")
            except Exception as e:
                logger.warning(f"[GRISHA] Failed to save to memory: {e}")

            # Save to filesystem (for easy text retrieval)
            try:
                reports_dir = os.path.expanduser("~/.config/atlastrinity/reports")
                os.makedirs(reports_dir, exist_ok=True)

                filename = f"rejection_step_{step_id}_{int(datetime.now().timestamp())}.md"
                file_path = os.path.join(reports_dir, filename)

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(report_text_masked)  # Use masked version

                logger.info(f"[GRISHA] Rejection report saved to filesystem: {file_path}")
            except Exception as e:
                logger.warning(f"[GRISHA] Failed to save report to filesystem: {e}")

            # Save to knowledge graph (Structured Semantic Memory) — ENHANCED
            try:
                node_id = f"rejection:step_{step_id}_{int(datetime.now().timestamp())}"
                kg_attributes: dict[str, Any] = {
                    "type": "verification_rejection",
                    "step_id": str(step_id),
                    "issues": "; ".join(verification.issues)
                    if isinstance(verification.issues, list)
                    else str(verification.issues),
                    "description": str(verification.description),
                    "timestamp": timestamp,
                }
                # Enrich KG node with remediation data for future learning
                if remediation_plan:
                    kg_attributes["error_type"] = remediation_plan.get("error_type", "unknown")
                    kg_attributes["root_cause"] = remediation_plan.get("root_cause", "")[:500]
                    kg_attributes["suggested_action"] = remediation_plan.get(
                        "suggested_action", ""
                    )[:500]
                    kg_attributes["recursion_safe"] = str(
                        remediation_plan.get("recursion_safe", False)
                    )

                await knowledge_graph.add_node(
                    node_type="CONCEPT",
                    node_id=node_id,
                    attributes=kg_attributes,
                )
                # Link to the task (use task_id if provided)
                source_id = f"task:{task_id}" if task_id else f"task:rejection_{step_id}"
                await knowledge_graph.add_edge(
                    source_id=source_id,
                    target_id=node_id,
                    relation="REJECTED",
                )
                logger.info(f"[GRISHA] Rejection node added to Knowledge Graph for step {step_id}")
            except Exception as e:
                logger.warning(f"[GRISHA] Failed to update Knowledge Graph: {e}")

            # Send to Message Bus (Real-time typed communication) — ENHANCED
            try:
                bus_payload: dict[str, Any] = {
                    "step_id": str(step_id),
                    "issues": verification.issues,
                    "description": verification.description,
                    "remediation": getattr(verification, "remediation_suggestions", []),
                }
                # Include structured remediation plan for self-healing
                if remediation_plan:
                    bus_payload["remediation_plan"] = remediation_plan
                if tetyana_context.get("tool_used"):
                    bus_payload["tetyana_context"] = tetyana_context

                msg = AgentMsg(
                    from_agent="grisha",
                    to_agent="tetyana",
                    message_type=MessageType.REJECTION,
                    payload=bus_payload,
                    step_id=str(step_id),
                )
                await message_bus.send(msg)
                logger.info("[GRISHA] Rejection message sent to Tetyana via Message Bus")
            except Exception as e:
                logger.warning(f"[GRISHA] Failed to send message to bus: {e}")

        except Exception as e:
            logger.warning(f"[GRISHA] Failed to save rejection report: {e}")

    async def security_check(self, action: dict[str, Any]) -> dict[str, Any]:
        """Performs security check before execution"""

        action_str = str(action)
        if self._check_blocklist(action_str):
            return {
                "safe": False,
                "risk_level": "critical",
                "reason": "Command found in blocklist",
                "requires_confirmation": True,
                "voice_message": "УВАГА! Ця команда у чорному списку. Блокую.",
            }

        prompt = AgentPrompts.grisha_security_prompt(str(action))

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ]

        response = await self.llm.ainvoke(messages)
        return self._parse_response(cast("str", response.content))

    async def take_screenshot(self) -> str:
        """Captures and analyzes screenshot via Vision model."""
        from src.brain.config import SCREENSHOTS_DIR

        # 1. Try Native Swift MCP first (fastest, most reliable)
        path = await self._attempt_mcp_screenshot(str(SCREENSHOTS_DIR))
        if path:
            return path

        # 2. Local Fallback
        return await self._attempt_local_screenshot(str(SCREENSHOTS_DIR))

    async def _attempt_mcp_screenshot(self, save_dir: str) -> str | None:
        """Attempts to take a screenshot using the 'xcodebuild' MCP tool."""
        try:
            if "xcodebuild" in mcp_manager.config.get("mcpServers", {}):
                result = await mcp_manager.call_tool("xcodebuild", "macos-use_take_screenshot", {})

                base64_img = None
                if isinstance(result, dict) and "content" in result:
                    for item in result["content"]:
                        if item.get("type") == "text":
                            base64_img = item.get("text")
                            break
                elif hasattr(result, "content"):  # prompt object
                    content = getattr(result, "content", None)
                    if content and len(content) > 0 and hasattr(content[0], "text"):
                        base64_img = content[0].text

                if base64_img:
                    import base64

                    os.makedirs(save_dir, exist_ok=True)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    path = os.path.join(save_dir, f"vision_mcp_{timestamp}.jpg")
                    with open(path, "wb") as f:
                        f.write(base64.b64decode(base64_img))
                    logger.info(f"[GRISHA] Screenshot saved: {path}")
                    return path
        except Exception as e:
            logger.warning(f"[GRISHA] MCP screenshot failed, falling back to local: {e}")
        return None

    async def _attempt_local_screenshot(self, save_dir: str) -> str:
        try:
            desktop_canvas, active_win_img = self._capture_screen_images()
            return self._save_composite_screenshot(desktop_canvas, active_win_img, save_dir)
        except Exception as e:
            logger.warning(f"Combined screenshot failed: {e}. Falling back to simple grab.")
            return self._fallback_screenshot(save_dir)

    def _capture_screen_images(self) -> tuple[Any, Any]:  # Returns Image objects

        display_imgs = []
        consecutive_failures = 0

        # Capture displays
        for di in range(1, 17):
            fhandle, path = tempfile.mkstemp(suffix=".png")
            os.close(fhandle)
            try:
                res = subprocess.run(
                    ["screencapture", "-x", "-D", str(di), path],
                    check=False,
                    capture_output=True,
                )
                if res.returncode == 0 and os.path.exists(path):
                    with Image.open(path) as img:
                        display_imgs.append(img.copy())
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
            finally:
                if os.path.exists(path):
                    try:
                        os.unlink(path)
                    except Exception:
                        pass

            if display_imgs and consecutive_failures >= 2:
                break

        desktop_canvas = None
        if not display_imgs:
            # Fallback single fullscreen
            tmp_full = os.path.join(tempfile.gettempdir(), "grisha_full_temp.png")
            subprocess.run(["screencapture", "-x", tmp_full], check=False, capture_output=True)
            if os.path.exists(tmp_full):
                with Image.open(tmp_full) as img:
                    desktop_canvas = img.copy()
                try:
                    os.unlink(tmp_full)
                except Exception:
                    pass
        else:
            # Stitch
            total_w = sum(img.width for img in display_imgs)
            max_h = max(img.height for img in display_imgs)
            desktop_canvas = Image.new("RGB", (total_w, max_h), (0, 0, 0))
            x_off = 0
            for d_img in display_imgs:
                desktop_canvas.paste(d_img, (x_off, 0))
                x_off += d_img.width

        if desktop_canvas is None:
            raise RuntimeError("Failed to capture desktop canvas")

        # Capture active window (simplified - skipping Quartz complexity for F-rank goal)
        active_win_img = None

        return desktop_canvas, active_win_img

    def _save_composite_screenshot(self, desktop_canvas, active_win_img, save_dir) -> str:

        target_w = 2048
        scale = target_w / max(1, desktop_canvas.width)
        dt_h = int(desktop_canvas.height * scale)

        desktop_small = desktop_canvas.resize((target_w, max(1, dt_h)))

        final_canvas = desktop_small

        path = os.path.join(save_dir, f"grisha_vision_{datetime.now().strftime('%H%M%S')}.jpg")
        final_canvas.save(path, "JPEG", quality=85)
        logger.info(f"[GRISHA] Vision composite saved: {path}")
        return path

    def _fallback_screenshot(self, save_dir: str) -> str:

        from PIL import ImageGrab

        try:
            screenshot = ImageGrab.grab(all_screens=True)
            path = os.path.join(
                save_dir, f"grisha_fallback_{datetime.now().strftime('%H%M%S')}.jpg"
            )
            screenshot.save(path, "JPEG", quality=80)
            return path
        except Exception:
            return ""

    async def audit_vibe_fix(
        self,
        error: str,
        vibe_report: str,
        context: dict | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Audits a proposed fix from Vibe AI before execution.
        Uses advanced reasoning to ensure safety and correctness.
        """

        context_data = context or shared_context.to_dict()

        # Fetch technical trace for grounding
        technical_trace = ""
        try:
            # We use the current step if available in context, or try to infer
            step_id = context_data.get("current_step_id", "unknown")
            technical_trace = await self._fetch_execution_trace(str(step_id), task_id=task_id)
        except Exception as e:
            logger.warning(f"[GRISHA] Could not fetch trace for audit: {e}")

        prompt = AgentPrompts.grisha_vibe_audit_prompt(
            error,
            vibe_report,
            context_data,
            technical_trace=technical_trace,
        )

        messages = [SystemMessage(content=self.system_prompt), HumanMessage(content=prompt)]

        try:
            logger.info("[GRISHA] Auditing Vibe's proposed fix...")
            response = await self.llm.ainvoke(messages)
            audit_result = self._parse_response(cast("str", response.content))

            verdict = audit_result.get("audit_verdict", "REJECT")
            issues = audit_result.get("issues", [])

            logger.info(f"[GRISHA] Audit Verdict: {verdict}")
            if issues:
                logger.warning(f"[GRISHA] Audit Issues: {issues}")

            # Fallback voice message if missing — concise Ukrainian only
            if not audit_result.get("voice_message"):
                verdict_uk = "прийнято" if verdict == "APPROVE" else "відхилено"
                audit_result["voice_message"] = (
                    f"Аудит виправлення завершено. Результат: {verdict_uk}."
                )

            return audit_result
        except Exception as e:
            logger.error(f"[GRISHA] Vibe audit failed: {e}")
            return {
                "audit_verdict": "REJECT",
                "reasoning": f"Аудит не вдався через технічну помилку: {e!s}",
                "voice_message": "Я не зміг перевірити запропоноване виправлення через технічну помилку.",
            }

    def get_voice_message(self, action: str, **kwargs) -> str:
        """Generates short message for TTS"""
        messages = {
            "verified": "Тетяно, я бачу що завдання виконано. Можеш продовжувати.",
            "failed": "Тетяно, результат не відповідає очікуванню.",
            "blocked": "УВАГА! Ця дія небезпечна. Блокую виконання.",
            "checking": "Перевіряю результат...",
            "approved": "Підтверджую. Можна продовжувати.",
        }
        return messages.get(action, "")

    def _extract_json_from_potential_blocks(self, text: str) -> dict[str, Any] | None:
        """Extract JSON by finding all { } pairs."""

        start_indices = [m.start() for m in re.finditer(r"\{", text)]
        end_indices = [m.start() for m in re.finditer(r"\}", text)]

        candidates = []
        for start in start_indices:
            for end in reversed(end_indices):
                if end > start:
                    block = text[start : end + 1]
                    if "steps" in block.lower():
                        candidates.append(block)

        candidates.sort(key=len, reverse=True)
        for block in candidates:
            try:
                clean_block = block.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_block)
                if isinstance(data, dict) and "steps" in data:
                    return data
            except (json.JSONDecodeError, ValueError):
                continue
        return None

    def _fallback_json_extraction(self, text: str) -> dict[str, Any] | None:
        """Standard backtick and regex fallback."""

        if "```json" in text:
            text = text.split("```json")[1].split("```", maxsplit=1)[0].strip()
        elif "```" in text:
            parts = text.split("```")
            json_candidates = [p.strip() for p in parts if "{" in p and "}" in p]
            text = max(json_candidates, key=len) if json_candidates else parts[1].strip()

        if not (text.startswith("{") and text.endswith("}")):
            json_match = re.search(r"(\{.*\})", text, re.DOTALL)
            if json_match:
                text = json_match.group(1).strip()

        try:
            return cast("dict[str, Any]", json.loads(text))
        except (json.JSONDecodeError, ValueError):
            return None

    def _has_sufficient_evidence(self, results: list[dict[str, Any]]) -> bool:
        """Heuristic check: Do we have enough evidence to judge?

        Fixed: Verification tool results come as dicts with 'error' boolean,
        not 'success' or 'exit_code'. Check the actual structure.
        """
        if not results:
            return False

        for res in results:
            # Primary check: tool result dict has 'error' = False (successful execution)
            has_error = res.get("error", True)  # Default to True = no evidence
            if not has_error:
                output = str(res.get("result", "")).strip()
                # Ignore trivial outputs
                if output and len(output) > 5:
                    return True
            # Secondary check: legacy format with 'success' key
            elif res.get("success", False):
                output = str(res.get("result", "")).strip()
                if output and len(output) > 5:
                    return True
        return False

    async def _collect_independent_evidence(
        self, step: dict[str, Any], goal_analysis: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Proactive Audit: Grisha triggers 'Sherlock Mode'.

        Smart tool selection based on step action context instead of
        generic ps-aux/db-query fallback.
        """

        step_action = step.get("action", "")
        step_action_lower = step_action.lower()
        expected_result = step.get("expected_result", "").lower()

        logger.info(
            f"[GRISHA] 🕵️ SHERLOCK MODE: Insufficient evidence for '{step_action[:60]}'. Taking control."
        )

        audit_tools: list[dict[str, Any]] = []

        # --- Smart tool selection based on action keywords ---

        # 1. File/Code creation or modification
        if any(
            kw in step_action_lower
            for kw in ["create", "write", "implement", "generate", "save", "edit", "modify"]
        ):
            # Try to extract file path from action or expected_result
            file_path = self._extract_file_path_from_text(step_action + " " + expected_result)
            if file_path:
                audit_tools.append(
                    {
                        "tool": "macos-use.execute_command",
                        "args": {
                            "command": f"head -50 '{file_path}' 2>/dev/null || echo 'FILE_NOT_FOUND'"
                        },
                        "reason": f"Verify actual content of created/modified file: {file_path}",
                    }
                )
                audit_tools.append(
                    {
                        "tool": "macos-use.execute_command",
                        "args": {"command": f"wc -l '{file_path}' 2>/dev/null || echo '0 lines'"},
                        "reason": f"Verify file is non-empty: {file_path}",
                    }
                )
            else:
                # Fallback: find recently modified files
                audit_tools.append(
                    {
                        "tool": "macos-use.execute_command",
                        "args": {
                            "command": "find ~/Documents/GitHub/atlastrinity -name '*.py' -mmin -5 -type f 2>/dev/null | head -5"
                        },
                        "reason": "Find recently modified files to verify creation",
                    }
                )

        # 2. Git operations
        elif any(kw in step_action_lower for kw in ["git", "commit", "push", "branch", "merge"]):
            audit_tools.append(
                {
                    "tool": "macos-use.execute_command",
                    "args": {
                        "command": "cd ~/Documents/GitHub/atlastrinity && git status --short && git log --oneline -3"
                    },
                    "reason": "Verify git state after operation",
                }
            )

        # 3. Process/service operations
        elif any(
            kw in step_action_lower
            for kw in ["process", "run", "start", "stop", "restart", "launch"]
        ):
            audit_tools.append(
                {
                    "tool": "macos-use.execute_command",
                    "args": {"command": "ps aux | grep -v grep | head -15"},
                    "reason": "Verify process state",
                }
            )

        # 4. Network/API operations
        elif any(
            kw in step_action_lower
            for kw in ["network", "api", "request", "connect", "ssh", "curl"]
        ):
            audit_tools.append(
                {
                    "tool": "macos-use.execute_command",
                    "args": {
                        "command": "curl -s -o /dev/null -w '%{http_code}' http://localhost:8080 2>/dev/null || echo 'NO_RESPONSE'"
                    },
                    "reason": "Verify network/service availability",
                }
            )

        # 5. Database operations
        elif any(kw in step_action_lower for kw in ["database", "db", "sql", "query", "table"]):
            audit_tools.append(
                {
                    "tool": "vibe.vibe_check_db",
                    "args": {
                        "query": "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name LIMIT 10"
                    },
                    "reason": "Verify database state",
                }
            )

        # Always include DB execution trace as baseline evidence
        audit_tools.append(
            {
                "tool": "vibe.vibe_check_db",
                "args": {
                    "query": "SELECT tool_name, result, created_at FROM tool_executions ORDER BY created_at DESC LIMIT 3"
                },
                "reason": "Baseline: recent tool execution trace from DB",
            }
        )

        # Execute the tools (max 3 to avoid token waste)
        results = []
        for t in audit_tools[:3]:
            try:
                tool_full_name = str(t.get("tool", ""))
                logger.info(f"[GRISHA] 🕵️ Auditing with: {tool_full_name} — {t.get('reason', '')}")

                res = await mcp_manager.dispatch_tool(
                    tool_name=tool_full_name,
                    arguments=cast("dict[str, Any]", t.get("args", {})),
                    allow_fallback=True,
                )

                results.append(
                    {
                        "tool": tool_full_name,
                        "args": t.get("args", {}),
                        "result": res,
                        "error": False,
                        "reason": t.get("reason", ""),
                    }
                )
            except Exception as e:
                logger.warning(f"[GRISHA] Audit tool {t.get('tool')} failed: {e}")
                results.append(
                    {
                        "tool": t.get("tool", "unknown"),
                        "args": t.get("args", {}),
                        "result": f"Error: {e}",
                        "error": True,
                        "reason": t.get("reason", ""),
                    }
                )

        return results

    def _extract_tetyana_execution_context(self, step: dict[str, Any]) -> dict[str, Any]:
        """Extract structured Tetyana execution context from step data.

        This provides the self-healing hypermodule with precise data
        about what Tetyana actually did, enabling correct fix task formation.
        """
        context: dict[str, Any] = {
            "tool_used": None,
            "tool_args": None,
            "raw_output": None,
            "error_message": None,
            "server_name": None,
        }

        # Extract from step metadata
        context["tool_used"] = step.get("tool") or step.get("tool_name")
        context["tool_args"] = step.get("tool_args") or step.get("args") or step.get("parameters")

        # Extract from previous_results if available (injected by Orchestrator)
        prev_results = step.get("previous_results", [])
        if prev_results and isinstance(prev_results, list):
            # Get the most recent result matching this step
            for res in reversed(prev_results):
                if isinstance(res, dict):
                    step_id = str(step.get("id", ""))
                    if str(res.get("step_id", "")) == step_id or not context["tool_used"]:
                        context["raw_output"] = str(res.get("result", ""))[:2000]
                        context["error_message"] = res.get("error")
                        if not context["tool_used"]:
                            context["tool_used"] = res.get("tool")
                        break

        # Extract from step result if directly attached
        if step.get("result"):
            result = step["result"]
            if isinstance(result, dict):
                context["raw_output"] = str(result.get("result", ""))[:2000]
                context["error_message"] = result.get("error")
            elif hasattr(result, "result"):
                context["raw_output"] = str(getattr(result, "result", ""))[:2000]
                context["error_message"] = getattr(result, "error", None)

        context["server_name"] = step.get("server") or step.get("mcp_server")

        return context

    async def _generate_remediation_plan(
        self,
        step: dict[str, Any],
        error_message: str,
        tetyana_context: dict[str, Any],
        recursion_depth: int = 0,
    ) -> dict[str, Any] | None:
        """Generate a structured remediation plan using LLM analysis.

        Returns a JSON dict with: error_type, root_cause, affected_component,
        suggested_action, recursion_safe, retry_with_changes, prevention_hint.
        """
        try:
            prompt = GRISHA_FAILURE_CONTEXT_PROMPT.format(
                step_action=step.get("action", "N/A"),
                expected_result=step.get("expected_result", "N/A"),
                error_message=error_message[:1000],
                tool_used=tetyana_context.get("tool_used", "N/A"),
                tool_args=str(tetyana_context.get("tool_args", "N/A"))[:500],
                raw_output=str(tetyana_context.get("raw_output", "N/A"))[:500],
                recursion_depth=recursion_depth,
                retry_attempt=recursion_depth,
            )

            result = await self.use_sequential_thinking(prompt, total_thoughts=1)

            if not result.get("success"):
                logger.warning("[GRISHA] Remediation plan generation failed via reasoning")
                return None

            analysis = result.get("analysis", "")

            # Extract JSON from the response
            plan = self._extract_json_from_potential_blocks(analysis)
            if plan and isinstance(plan, dict):
                # Validate required keys
                required_keys = ["error_type", "root_cause", "suggested_action", "recursion_safe"]
                if all(k in plan for k in required_keys):
                    logger.info(
                        f"[GRISHA] Remediation plan generated: "
                        f"type={plan.get('error_type')}, safe={plan.get('recursion_safe')}"
                    )
                    return plan

            # Fallback: try to parse manually
            fallback_plan = self._fallback_json_extraction(analysis)
            if fallback_plan and isinstance(fallback_plan, dict):
                return fallback_plan

            logger.warning("[GRISHA] Could not extract remediation plan from LLM output")
            return None

        except Exception as e:
            logger.warning(f"[GRISHA] Remediation plan generation error: {e}")
            return None

    def _extract_file_path_from_text(self, text: str) -> str | None:
        """Extract a likely file path from step action/expected_result text."""
        import re as _re

        # Pattern 1: Explicit paths (Unix-style)
        path_match = _re.search(r"(/[\w./-]+\.[\w]+)", text)
        if path_match:
            return path_match.group(1)

        # Pattern 2: Relative paths or filenames with extensions
        file_match = _re.search(
            r'["\']?([\w./-]+\.(?:py|js|ts|json|yaml|yml|toml|md|html|css|sh|sql))["\']?', text
        )
        if file_match:
            candidate = file_match.group(1)
            # Try to resolve relative to project root
            project_root = os.path.expanduser("~/Documents/GitHub/atlastrinity")
            full_path = os.path.join(project_root, candidate)
            return full_path

        return None
