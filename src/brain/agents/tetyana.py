"""Tetyana - The Executor

Role: macOS interaction, executing atomic plan steps
Voice: Tetiana (female)
Model: Configured model
"""

import asyncio
import base64
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

# Set up paths first
current_dir = os.path.dirname(os.path.abspath(__file__))
root = os.path.join(current_dir, "..", "..")
sys.path.insert(0, os.path.abspath(root))

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.brain.agents.base_agent import BaseAgent
from src.brain.config.config_loader import config
from src.brain.core.orchestration.context import shared_context
from src.brain.mcp.mcp_manager import mcp_manager
from src.brain.monitoring.logger import logger
from src.brain.prompts import AgentPrompts
from src.providers.factory import create_llm


@dataclass
class StepResult:
    """Result of step execution"""

    step_id: str
    success: bool
    result: str
    screenshot_path: str | None = None
    voice_message: str | None = None
    error: str | None = None
    tool_call: dict[str, Any] | None = None
    timestamp: datetime | None = None
    thought: str | None = None
    is_deviation: bool = False
    deviation_info: dict[str, Any] | None = None
    server: str | None = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    def to_dict(self) -> dict:
        """Convert StepResult to dictionary"""
        return {
            "step_id": self.step_id,
            "success": self.success,
            "result": self.result,
            "screenshot_path": self.screenshot_path,
            "voice_message": self.voice_message,
            "error": self.error,
            "tool_call": self.tool_call,
            "thought": self.thought,
            "server": self.server,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class Tetyana(BaseAgent):
    """Tetyana - The Executor

    Functions:
    - Executing atomic plan steps
    - Interacting with macOS (GUI/Terminal/Apps)
    - Progress reporting
    - Asking Atlas for help when stuck
    """

    # Tool schemas are now loaded from centralized mcp_registry
    # This eliminates duplication and ensures single source of truth
    _cached_schemas = None

    @classmethod
    def get_tool_schemas(cls) -> dict:
        """Get tool schemas from centralized registry.
        Cached after first access for performance.
        """
        if cls._cached_schemas is None:
            from src.brain.mcp.mcp_registry import TOOL_SCHEMAS

            cls._cached_schemas = TOOL_SCHEMAS
        return cls._cached_schemas

    # Backwards compatibility property
    @property
    def MACOS_USE_SCHEMAS(self) -> dict:
        """Legacy property for backwards compatibility. Use get_tool_schemas() instead."""
        return self.get_tool_schemas()

    NAME = AgentPrompts.TETYANA["NAME"]
    DISPLAY_NAME = AgentPrompts.TETYANA["DISPLAY_NAME"]
    VOICE = AgentPrompts.TETYANA["VOICE"]
    COLOR = AgentPrompts.TETYANA["COLOR"]

    @property
    def system_prompt(self) -> str:
        """Dynamically generate system prompt with current catalog."""
        return AgentPrompts.get_agent_system_prompt("TETYANA")

    def __init__(self, model_name: str | None = None):
        # Get model config (config.yaml > parameter)
        agent_config = config.get_agent_config("tetyana")

        # Main execution model - fallback to global default
        final_model = model_name or agent_config.get("model") or config.get("models.default")
        if not final_model or not final_model.strip():
            raise ValueError(
                "[TETYANA] Model not configured. Please set 'models.default' or 'agents.tetyana.model' in config.yaml"
            )

        self.llm = create_llm(model_name=final_model)

        # Specialized models for Reasoning and Reflexion - fallback to global or final_model
        reasoning_model = (
            agent_config.get("reasoning_model") or config.get("models.reasoning") or final_model
        )
        reflexion_model = (
            agent_config.get("reflexion_model") or config.get("models.reasoning") or final_model
        )

        if not reasoning_model or not reasoning_model.strip():
            raise ValueError(
                "[TETYANA] Reasoning model not configured. Please set 'models.reasoning' or 'agents.tetyana.reasoning_model' in config.yaml"
            )
        if not reflexion_model or not reflexion_model.strip():
            raise ValueError(
                "[TETYANA] Reflexion model not configured. Please set 'models.reasoning' or 'agents.tetyana.reflexion_model' in config.yaml"
            )

        self.reasoning_llm = create_llm(model_name=reasoning_model)
        self.reflexion_llm = create_llm(model_name=reflexion_model)

        # NEW: Vision model for complex GUI tasks (screenshot analysis)
        vision_model = (
            agent_config.get("vision_model") or config.get("models.vision") or final_model
        )
        if not vision_model or not vision_model.strip():
            # Fallback to main model if vision not explicitly set, but Main must exist
            vision_model = final_model

        self.vision_llm = create_llm(model_name=vision_model, vision_model_name=vision_model)

        self.temperature = agent_config.get("temperature", 0.5)
        self.current_step: int = 0
        self.results: list[StepResult] = []
        self.attempt_count: int = 0

        # Track current PID for Vision analysis
        self._current_pid: int | None = None

        # Cache for specific server tool specs to avoid repetitive MCP calls
        self._server_tools_cache: dict[str, str] = {}

    async def _validate_goal_alignment(
        self,
        step: dict[str, Any],
        global_goal: str,
        parent_goals: list[str] | None = None,
    ) -> dict[str, Any]:
        """Validates step alignment with global goal using recursive validation.
        The agent has the right to suggest deviations if they lead to better outcomes.

        Returns:
            {
                "aligned": bool,
                "confidence": float (0.0-1.0),
                "reason": str,
                "deviation_suggested": bool,
                "suggested_alternative": str | None,
                "goal_chain": list[str]
            }

        """
        from langchain_core.messages import HumanMessage, SystemMessage

        from src.brain.monitoring.logger import logger

        parent_goals = parent_goals or []
        goal_chain = [*parent_goals, global_goal]

        prompt = f"""GOAL ALIGNMENT VALIDATION

CURRENT STEP: {step.get("action", "")}
EXPECTED RESULT: {step.get("expected_result", "")}
TOOL: {step.get("tool", step.get("realm", "not specified"))}

GOAL CHAIN (from most specific to global):
{chr(10).join([f"  {i + 1}. {g}" for i, g in enumerate(goal_chain)])}

GLOBAL GOAL: {global_goal}

Analyze if this step:
1. DIRECTLY contributes to the immediate goal
2. INDIRECTLY supports the global goal
3. Could DEVIATE from the goal vector

STRICT ALIGNMENT POLICY:
You must strictly follow the plan unless a step is literally IMPOSSIBLE to execute (e.g., file missing, tool failed) or HARMFUL to the system.
Do NOT suggest alternative tasks like searching for movies or general information unless it is part of the GLOBAL GOAL.

Respond in JSON:
{{
    "aligned": true/false,
    "confidence": 0.0-1.0,
    "reason": "Brief explanation (English)",
    "deviation_suggested": true/false,
    "suggested_alternative": "Alternative ONLY if current step is impossible - otherwise null",
    "contribution_type": "direct|indirect|supportive|questionable"
}}
"""

        try:
            messages: list[BaseMessage] = [
                SystemMessage(
                    content="You are a Goal Alignment Validator. Be critical but constructive.",
                ),
                HumanMessage(content=prompt),
            ]
            response = await self.reasoning_llm.ainvoke(
                messages,
            )
            result = self._parse_response(cast("str", response.content))
            result["goal_chain"] = goal_chain

            if result.get("deviation_suggested"):
                logger.info(
                    f"[TETYANA] Goal alignment suggests deviation: {result.get('suggested_alternative', 'N/A')}",
                )

            return result
        except Exception as e:
            logger.warning(f"[TETYANA] Goal alignment validation failed: {e}")
            return {
                "aligned": True,
                "confidence": 0.5,
                "reason": f"Validation error: {e}",
                "deviation_suggested": False,
                "suggested_alternative": None,
                "goal_chain": goal_chain,
            }

    def _extract_note_content(self, notes_result: dict[str, Any]) -> str | None:
        """Extract note content from various possible structures in notes_result."""
        if not isinstance(notes_result, dict) or not notes_result.get("success"):
            return None

        # Try direct content field
        note_content = notes_result.get("content") or notes_result.get("body")

        # Try from notes list
        if not note_content and notes_result.get("notes"):
            notes = notes_result.get("notes", [])
            if isinstance(notes, list) and len(notes) > 0:
                first_note = notes[0]
                if isinstance(first_note, dict):
                    note_content = first_note.get("content") or first_note.get("body")
                elif isinstance(first_note, str):
                    note_content = first_note
        return note_content

    async def _fetch_feedback_from_notes(self, step_id: int) -> str | None:
        """Attempt to retrieve feedback from macos-use notes."""

        try:
            result = await mcp_manager.dispatch_tool(
                "notes_get", {"name": f"Grisha Rejection Step {step_id}"}
            )
            notes_result = None
            if isinstance(result, dict):
                notes_result = result
            elif hasattr(result, "structuredContent") and isinstance(
                result.structuredContent, dict
            ):
                notes_result = result.structuredContent.get("result", {})
            elif (
                hasattr(result, "content")
                and len(result.content) > 0
                and hasattr(result.content[0], "text")
            ):
                import json as _json

                try:
                    notes_result = _json.loads(result.content[0].text)
                except Exception:
                    pass

            if notes_result:
                content = self._extract_note_content(notes_result)
                if content:
                    logger.info(
                        f"[TETYANA] Retrieved Grisha's feedback from notes for step {step_id}"
                    )
                    return content
        except Exception as e:
            logger.warning(f"[TETYANA] Could not retrieve from notes: {e}")
        return None

    async def _fetch_feedback_from_memory(self, step_id: int) -> str | None:
        """Attempt to retrieve feedback from memory nodes."""

        try:
            result = await mcp_manager.call_tool(
                "memory", "search_nodes", {"query": f"grisha_rejection_step_{step_id}"}
            )
            if result and hasattr(result, "content"):
                for item in result.content:
                    if hasattr(item, "text"):
                        logger.info(
                            f"[TETYANA] Retrieved Grisha's feedback from memory for step {step_id}"
                        )
                        return cast("str", item.text)
            elif isinstance(result, dict) and "results" in result:
                results = result["results"]
                if results and len(results) > 0:
                    logger.info(
                        f"[TETYANA] Retrieved Grisha's feedback from memory for step {step_id}"
                    )
                    # Results from memory search contain 'observations' list
                    observations = results[0].get("observations", [])
                    return observations[0] if observations else ""
            elif isinstance(result, dict) and "entities" in result:
                entities = result["entities"]
                if entities and len(entities) > 0:
                    logger.info(
                        f"[TETYANA] Retrieved Grisha's feedback from memory for step {step_id}"
                    )
                    return cast("str", entities[0].get("observations", [""])[0])
        except Exception as e:
            logger.warning(f"[TETYANA] Could not retrieve from memory: {e}")
        return None

    async def get_grisha_feedback(self, step_id: int) -> str | None:
        """Retrieve Grisha's detailed rejection report from notes or memory"""
        content = await self._fetch_feedback_from_notes(step_id)
        if content:
            return content
        return await self._fetch_feedback_from_memory(step_id)

    async def _take_screenshot_for_vision(self, pid: int | None = None) -> str | None:
        """Take screenshot for Vision analysis, optionally focusing on specific app."""
        import base64
        import subprocess

        from src.brain.config import SCREENSHOTS_DIR

        try:
            # Create screenshots directory if needed
            os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(SCREENSHOTS_DIR, f"vision_{timestamp}.png")

            # If PID provided, try to focus that app first
            if pid:
                try:
                    focus_script = f"""
                    tell application "System Events"
                        set frontProcess to first process whose unix id is {pid}
                        set frontmost of frontProcess to true
                    end tell
                    """
                    subprocess.run(
                        ["osascript", "-e", focus_script],
                        check=False,
                        capture_output=True,
                        timeout=5,
                    )
                    await asyncio.sleep(0.3)  # Wait for focus
                except Exception as e:
                    logger.warning(f"[TETYANA] Could not focus app {pid}: {e}")

            # 1. Try MCP Tool first (Native Swift)
            try:
                # We need to construct a lightweight call since we are inside Tetyana agent class,
                # but we have access to mcp_manager via import
                if "xcodebuild" in mcp_manager.config.get("mcpServers", {}):
                    result = await mcp_manager.call_tool(
                        "xcodebuild",
                        "macos-use_take_screenshot",
                        {},
                    )

                    base64_img = None
                    if isinstance(result, dict) and "content" in result:
                        for item in result["content"]:
                            if item.get("type") == "text":
                                base64_img = item.get("text")
                                break
                    elif hasattr(result, "content"):
                        content = getattr(result, "content", None)
                        if content and len(content) > 0 and hasattr(content[0], "text"):
                            base64_img = content[0].text

                    if base64_img:
                        with open(path, "wb") as f:
                            f.write(base64.b64decode(base64_img))
                        logger.info(f"[TETYANA] Screenshot for Vision saved via MCP: {path}")
                        return path
            except Exception as e:
                logger.warning(f"[TETYANA] MCP screenshot failed, falling back: {e}")

            # 2. Fallback to screencapture
            result = subprocess.run(
                ["screencapture", "-x", path], check=False, capture_output=True, timeout=10
            )

            if result.returncode == 0 and os.path.exists(path):
                logger.info(f"[TETYANA] Screenshot for Vision saved (fallback): {path}")
                return path
            logger.error(f"[TETYANA] Screenshot failed: {result.stderr.decode()}")
            return None

        except Exception as e:
            logger.error(f"[TETYANA] Screenshot error: {e}")
            return None

    async def analyze_screen(self, query: str, pid: int | None = None) -> dict[str, Any]:
        """Take screenshot and analyze with Vision to find UI elements.
        Used for complex GUI tasks where Accessibility Tree is insufficient.

        Args:
            query: What to look for (e.g., "Find the 'Next' button")
            pid: Optional PID to focus app before screenshot

        Returns:
            {"found": bool, "elements": [...], "current_state": str, "suggested_action": {...}}

        """

        logger.info(f"[TETYANA] Vision analysis requested: {query}")

        # Use provided PID or tracked PID
        effective_pid = pid or self._current_pid

        # 1. Take screenshot
        screenshot_path = await self._take_screenshot_for_vision(effective_pid)
        if not screenshot_path:
            return {"found": False, "error": "Could not take screenshot"}

        # 2. Load and encode image
        try:
            with open(screenshot_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            return {"found": False, "error": f"Could not read screenshot: {e}"}

        # 3. Vision analysis prompt
        vision_prompt = f"""Analyze this macOS screenshot to help with: {query}

You are assisting with GUI automation. Identify clickable elements, their positions, and suggest the best action.

Respond in JSON format:
{{
    "found": true/false,
    "elements": [
        {{
            "type": "button|link|textfield|checkbox|menu",
            "label": "Element text or description",
            "x": 350,
            "y": 420,
            "confidence": 0.95
        }}
    ],
    "current_state": "Brief description of what's visible on screen",
    "suggested_action": {{
        "tool": "macos-use_click_and_traverse",
        "args": {{"pid": {effective_pid or "null"}, "x": 350, "y": 420}}
    }},
    "notes": "Any important observations (CAPTCHA detected, page loading, etc.)"
}}

IMPORTANT:
- Coordinates should be approximate center of the element
- If you see a CAPTCHA or verification challenge, note it in "notes"
- If the target element is not visible, set "found": false and explain in "current_state"
"""

        content_list: list[dict[str, Any]] = [
            {"type": "text", "text": vision_prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
        ]

        messages: list[BaseMessage] = [
            SystemMessage(
                content="You are a Vision assistant for macOS GUI automation. Analyze screenshots precisely and provide accurate element coordinates.",
            ),
            HumanMessage(content=cast("Any", content_list)),
        ]

        try:
            response = await self.vision_llm.ainvoke(messages)
            result = self._parse_response(cast("str", response.content))

            if result.get("found"):
                logger.info(f"[TETYANA] Vision found elements: {len(result.get('elements', []))}")
                logger.info(f"[TETYANA] Current state: {result.get('current_state', '')[:100]}...")
            else:
                logger.warning(
                    f"[TETYANA] Vision did not find target: {result.get('current_state', 'Unknown')}",
                )

            # Store screenshot path for Grisha verification
            result["screenshot_path"] = screenshot_path
            return result

        except Exception as e:
            logger.error(f"[TETYANA] Vision analysis failed: {e}")
            return {"found": False, "error": str(e), "screenshot_path": screenshot_path}

    def _get_dynamic_temperature(self, attempt: int) -> float:
        """Dynamic temperature: 0.1 + attempt * 0.2, capped at 1.0"""
        return min(0.1 + (attempt * 0.2), 1.0)

    async def _check_consent_requirements(
        self,
        step: dict[str, Any],
        provided_response: str | None,
        step_id: Any,
    ) -> StepResult | None:
        """Checks if the step requires user consent and returns a StepResult if blocked."""

        # Refined consent detection - LESS AGGRESSIVE
        step_action_lower = str(step.get("action", "")).lower()

        is_consent_request = (not provided_response) and (
            step.get("requires_consent", False) is True
            or step.get("requires_user_input", False) is True
        )

        if is_consent_request:
            # Exclude technical checks from human confirmation
            technical_verification_keywords = [
                "file",
                "directory",
                "process",
                "connection",
                "port",
                "schema",
                "table",
                "database",
                "log",
                "script",
                "config",
                "environment",
                "version",
                "status",
                "health",
                "search",
                "find",
                "looking",
                "identify",
                "analyze",
                "check",
                "test",
                "verify",
                "discovery",
                "scan",
                "list",
                "read",
                "fetch",
                "get",
                "observe",
                "inspect",
                "extract",
                "mapping",
                "documentation",
                "plans",
                "analysis",
                "automation",
                "recovery",
            ]
            if any(tk in step_action_lower for tk in technical_verification_keywords):
                is_consent_request = False
                logger.info(
                    f"[TETYANA] Step '{step_id}' - skipping consent: identified as informational/search task.",
                )

        if is_consent_request:
            logger.info(f"[TETYANA] Step '{step_id}' requires consent. Signal orchestrator.")
            consent_msg = f"Потрібна ваша згода або відповідь для кроку: {step.get('action')}\nОчікуваний результат: {step.get('expected_result', 'Підтвердження користувача')}"

            return StepResult(
                step_id=step.get("id", self.current_step),
                success=False,
                result=consent_msg,
                voice_message="Мені потрібна ваша згода або додаткова інформація. Будь ласка, напишіть у чат.",
                error="need_user_input",
                thought=f"I detected a need for user consent in step: {step.get('action')}. provided_response={provided_response}.",
            )
        return None

    async def _perform_vision_analysis_if_needed(
        self,
        step: dict[str, Any],
        attempt: int,
    ) -> tuple[dict[str, Any] | None, StepResult | None]:
        """Performs vision analysis if required. Returns (vision_result, blocking_StepResult)."""

        vision_result = None
        if step.get("requires_vision") and attempt <= 2:
            logger.info("[TETYANA] Step requires Vision analysis for UI element discovery...")
            query = step.get("action", "Find the next interaction target")

            # Try to get PID from step args or tracked state
            step_pid = None
            if step.get("args") and isinstance(step.get("args"), dict):
                step_pid = step["args"].get("pid")

            effective_pid = step_pid or self._current_pid
            vision_result = await self.analyze_screen(query, effective_pid)

            if vision_result.get("found") and vision_result.get("suggested_action"):
                suggested = vision_result["suggested_action"]
                logger.info(f"[TETYANA] Vision suggests action: {suggested}")
            elif vision_result.get("notes"):
                # Check for CAPTCHA or other blockers
                notes = vision_result.get("notes", "").lower()
                notes_lower = notes.lower()
                is_blocker = (
                    ("captcha" in notes_lower and "no captcha" not in notes_lower)
                    or ("verification" in notes_lower and "no verification" not in notes_lower)
                    or ("robot" in notes_lower and "not a robot" not in notes_lower)
                    or ("blocked" in notes_lower)
                )

                if is_blocker:
                    logger.warning(
                        f"[TETYANA] Vision detected blocker: {vision_result.get('notes')}",
                    )
                    blocker_desc = vision_result.get("notes", "Виявлено перешкоду")
                    voice_msg = (
                        f"Я бачу перешкоду на екрані: {blocker_desc}. Мені потрібна ваша допомога."
                    )
                    error_result = StepResult(
                        step_id=step.get("id", self.current_step),
                        success=False,
                        result=f"Vision detected blocker: {vision_result.get('notes')}",
                        voice_message=voice_msg,
                        error=f"Blocker detected: {vision_result.get('notes')}",
                        screenshot_path=vision_result.get("screenshot_path"),
                    )
                    return vision_result, error_result
        return vision_result, None

    async def _fetch_grisha_feedback(
        self,
        step: dict[str, Any],
        attempt: int,
        step_id: int,
    ) -> str:
        """Fetches Grisha's feedback for the step."""

        grisha_feedback = step.get("grisha_feedback", "")
        if not grisha_feedback and attempt > 1:
            logger.info(
                f"[TETYANA] Attempt {attempt} - fetching Grisha's rejection report (step {step_id})...",
            )
            grisha_feedback = await self.get_grisha_feedback(step_id) or ""
        return cast("str", grisha_feedback)

    def _infer_tool_from_action(self, action_text: str) -> str | None:
        """Infer tool name from action text."""
        action_text = action_text.lower()
        if any(kw in action_text for kw in ["implement feature", "deep code", "refactor project"]):
            return "vibe.vibe_implement_feature"
        if any(kw in action_text for kw in ["vibe", "code", "debug", "analyze error"]):
            return "vibe.vibe_prompt"
        if any(kw in action_text for kw in ["click", "type", "press", "scroll", "open app"]):
            return "xcodebuild.macos-use_take_screenshot"  # Fallback to start UI interaction through bridge
        if any(
            kw in action_text
            for kw in ["finder", "desktop", "folder", "sort", "trash", "open path"]
        ):
            return "xcodebuild.macos-use_finder_list_files"
        if "list" in action_text and "directory" in action_text:
            return "filesystem.list_directory"
        if "read" in action_text and "file" in action_text:
            return "filesystem.read_file"
        if "search" in action_text and "file" in action_text:
            return "filesystem.find_by_name"
        if any(
            kw in action_text
            for kw in [
                "run",
                "execute",
                "command",
                "terminal",
                "bash",
                "mkdir",
                "ssh",
                "connect",
                "remote",
                "shell",
            ]
        ):
            return "xcodebuild.execute_command"
        if "browser" in action_text or "url" in action_text:
            return "xcodebuild.macos-use_fetch_url"
        return None

    async def _get_detailed_server_context(self, target_server: str) -> str:
        """Fetch detailed tool specifications for a specific server."""
        from src.brain.core.orchestration.context import shared_context
        from src.brain.mcp.mcp_manager import mcp_manager

        configured_servers = mcp_manager.config.get("mcpServers", {})
        if (
            target_server
            and isinstance(target_server, str)
            and target_server in configured_servers
            and not target_server.startswith("_")
        ):
            # Check cache first
            if target_server in self._server_tools_cache:
                logger.debug(f"[TETYANA] Using cached specs for server: {target_server}")
                return self._server_tools_cache[target_server]

            logger.info(f"[TETYANA] Dynamically inspecting server: {target_server}")
            try:
                tools = await mcp_manager.list_tools(target_server)
                import json

                tools_summary = f"\n--- DETAILED SPECS FOR SERVER: {target_server} ---\n"
                for t in tools:
                    name = getattr(t, "name", str(t))
                    desc = getattr(t, "description", "")
                    schema = getattr(t, "inputSchema", {})
                    tools_summary += (
                        f"- {name}: {desc}\n  Schema: {json.dumps(schema, ensure_ascii=False)}\n"
                    )

                # Cache the result
                self._server_tools_cache[target_server] = tools_summary
                return tools_summary
            except Exception as e:
                logger.warning(f"[TETYANA] Failed to list tools for {target_server}: {e}")

        return getattr(
            shared_context,
            "available_tools_summary",
            "List available tools using list_tools if needed.",
        )

    def _apply_vision_overrides(
        self,
        tool_call: dict[str, Any],
        vision_result: dict[str, Any] | None,
    ) -> None:
        """Update tool_call with Vision-provided coordinates and overrides."""
        if not (
            vision_result and vision_result.get("found") and vision_result.get("suggested_action")
        ):
            return

        suggested = vision_result["suggested_action"]
        # Merge Vision's coordinates into tool_call args
        if suggested.get("args"):
            if not isinstance(tool_call.get("args"), dict):
                tool_call["args"] = {}
            # Update with Vision-provided coordinates
            for key in ["x", "y", "pid"]:
                val = suggested["args"].get(key)
                if val is not None:
                    tool_call["args"][key] = val
                    logger.info(f"[TETYANA] Vision override: {key}={val}")

            # If Vision suggests a specific tool, consider using it
            if suggested.get("tool") and "click" in suggested["tool"].lower():
                # Remove arguments that might belong to the previous planned tool (e.g. Puppeteer)
                # but are incompatible with the new macos-use tool.
                incompatible_keys = ["url", "launchOptions", "allowDangerous", "wait_for"]
                if isinstance(tool_call.get("args"), dict):
                    for ik in incompatible_keys:
                        if ik in tool_call["args"]:
                            del tool_call["args"][ik]
                            logger.info(
                                f"[TETYANA] Vision override: removed incompatible arg '{ik}'",
                            )

                tool_call["name"] = suggested["tool"]
                tool_call["server"] = "xcodebuild"
                logger.info(f"[TETYANA] Vision override: tool={suggested['tool']}")

    async def _handle_proactive_help_request(
        self,
        monologue: dict[str, Any],
        step: dict[str, Any],
    ) -> StepResult | None:
        """Process question to Atlas if present in monologue."""
        from src.brain.core.server.message_bus import AgentMsg, MessageType, message_bus

        question = monologue.get("question_to_atlas")
        if not question:
            return None

        logger.info(f"[TETYANA] Proactive help request to Atlas: {question}")
        msg = AgentMsg(
            from_agent="tetyana",
            to_agent="atlas",
            message_type=MessageType.HELP_REQUEST,
            payload={"question": question, "step_id": step.get("id")},
            step_id=step.get("id"),
        )
        await message_bus.send(msg)

        return StepResult(
            step_id=step.get("id", self.current_step),
            success=False,
            result=f"Blocked on Atlas: {question}",
            voice_message=monologue.get("voice_message") or f"У мене питання до Атласу: {question}",
            error="proactive_help_requested",
            thought=monologue.get("thought"),
        )

    async def _run_reasoning_llm(self, prompt: str) -> dict[str, Any]:
        """Execute reasoning LLM and parse monologue."""

        try:
            resp = await self.reasoning_llm.ainvoke(
                [
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=prompt),
                ]
            )
            return self._parse_response(cast("str", resp.content))
        except Exception as e:
            logger.warning(f"[TETYANA] Internal Monologue failed: {e}")
            return {}

    def _map_proposed_to_tool_call(
        self,
        proposed: Any,
        step: dict[str, Any],
        target_server: str,
    ) -> dict[str, Any]:
        """Map LLM's proposed action to a canonical tool call structure."""
        if isinstance(proposed, dict):
            return {
                "name": proposed.get("tool") or proposed.get("name") or step.get("tool") or "",
                "args": proposed.get("args") or {},
                "server": proposed.get("server") or target_server,
            }

        # Fallback to step-defined tool or inferred tool
        base_call = cast("dict[str, Any]", proposed) or cast(
            "dict[str, Any]", step.get("tool_call")
        )
        if base_call:
            return base_call

        name = step.get("tool") or ""
        args = step.get("args") or {"action": step.get("action"), "path": step.get("path")}
        return {"name": name, "args": args}

    async def _check_fast_path(
        self, step: dict[str, Any], target_server: str, attempt: int, grisha_feedback: str
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Check if the tool qualifies for fast-path execution (skipping reasoning)."""
        SKIP_REASONING_TOOLS = ["filesystem", "time", "fetch"]
        if (
            attempt == 1
            and not grisha_feedback
            and target_server in SKIP_REASONING_TOOLS
            and step.get("tool")
            and step.get("args")
            and not step.get("requires_vision")
        ):
            logger.info(f"[TETYANA] FAST PATH: Skipping reasoning for '{target_server}'")
            return {
                "name": step.get("tool"),
                "args": step.get("args", {}),
                "server": target_server,
            }, {"thought": f"Executing simple tool '{target_server}' via FAST PATH."}
        return None

    def _correct_tool_name(
        self, tool_call: dict[str, Any], step: dict[str, Any], target_server: str
    ) -> None:
        """Helper to correct invalid tool names using inference."""
        if not isinstance(tool_call, dict):
            logger.warning(
                f"[TETYANA] tool_call is not a dict: {type(tool_call)}. Forcing dict structure."
            )
            # If it's a string, use it as the name if it looks like a tool name
            name = str(tool_call).strip() if tool_call else ""
            # But we can't easily fix the object in-place if it's a string (immutable)
            # However, the caller expects to modify the dict.
            # We must handle this in the caller or ensure it's a dict early.
            return

        current_name = str(tool_call.get("name", "") or "").strip()

        # FIX: Detect hallucinated/invalid tool names from LLM responses
        INVALID_TOOL_NAMES = {"none", "null", "", "undefined", "unknown", "n/a", "na"}
        is_invalid = (
            not current_name
            or current_name.lower() in INVALID_TOOL_NAMES
            or len(current_name) > 50
            or " " in current_name
        )

        if is_invalid:
            inferred = self._infer_tool_from_action(str(step.get("action", "")))
            if inferred:
                logger.info(
                    f"[TETYANA] Correcting invalid tool name '{current_name}' to '{inferred}'"
                )
                tool_call["name"] = inferred
            elif target_server and target_server != "tetyana":
                logger.warning(
                    f"[TETYANA] Tool name '{current_name}' seems invalid but no inference matched."
                )

        if not tool_call.get("name"):
            tool_raw = step.get("tool")
            server_raw = step.get("server")

            candidate_tool = tool_raw if isinstance(tool_raw, str) and " " not in tool_raw else None
            candidate_server = (
                server_raw if isinstance(server_raw, str) and " " not in server_raw else None
            )

            name = candidate_tool or candidate_server or step.get("realm")

            if not name or " " in str(name):
                name = self._infer_tool_from_action(str(step.get("action", "")))

            if name:
                tool_call["name"] = name

        # FINAL CHECK: If still empty, try to provide a generic fallback for safe exploration
        if not tool_call.get("name") and not tool_call.get("tool"):
            action = str(step.get("action", "")).lower()
            logger.warning(
                f"[TETYANA] Tool name still empty after inference for action: '{action}'. Attempting final fallback."
            )
            if "status" in action or "check" in action or "verify" in action:
                # Safe fallback to checking system status/files
                tool_call["name"] = "macos-use.execute_command"
                if not tool_call.get("args"):
                    tool_call["args"] = {}
                if not tool_call["args"].get("command"):
                    tool_call["args"]["command"] = "ls -la"  # Safe discovery
            else:
                # Last resort: Screenshot to see what's happening
                tool_call["name"] = "macos-use.macos-use_take_screenshot"

    def _finalize_tool_call_normalization(
        self, tool_call: dict[str, Any], step: dict[str, Any], target_server: str
    ) -> None:
        """Apply final overrides, server info, and normalization to tool_call."""
        if not isinstance(tool_call, dict):
            return

        # 1. Logic to fix "Tool Name Hallucination"
        self._correct_tool_name(tool_call, step, target_server)

        # 2. Server assignment
        if target_server and "server" not in tool_call:
            tool_call["server"] = target_server

        # 3. Argument normalization
        if isinstance(tool_call.get("args"), dict):
            tool_call["args"]["step_id"] = step.get("id")
            if (
                (
                    str(tool_call.get("name", "")).lower().startswith("xcodebuild")
                    or tool_call.get("server") == "xcodebuild"
                )
                and not tool_call["args"].get("pid")
                and self._current_pid
            ):
                tool_call["args"]["pid"] = self._current_pid

    async def _determine_tool_action(
        self,
        step: dict[str, Any],
        target_server: str,
        attempt: int,
        grisha_feedback: str,
        vision_result: dict[str, Any] | None,
        provided_response: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any], StepResult | None]:
        """Determines the tool action using reasoning or fast path."""
        from ..prompts import AgentPrompts

        # 1. Check Fast Path
        fast_path = await self._check_fast_path(step, target_server, attempt, grisha_feedback)
        if fast_path:
            return fast_path[0], fast_path[1], None

        # 2. Run LLM Reasoning
        tools_summary = await self._get_detailed_server_context(target_server)
        prompt = AgentPrompts.tetyana_reasoning_prompt(
            str(step),
            shared_context.to_dict(),
            tools_summary=tools_summary,
            feedback=grisha_feedback,
            previous_results=cast("list[Any]", step.get("previous_results")),
            goal_context=shared_context.get_goal_context(),
            bus_messages=cast("list[Any]", step.get("bus_messages")),
            full_plan=step.get("full_plan", ""),
        )

        monologue = await self._run_reasoning_llm(prompt)
        if not monologue:
            return {"name": step.get("tool"), "args": {"action": step.get("action")}}, {}, None

        # 3. Handle Proactive Help
        help_result = await self._handle_proactive_help_request(monologue, step)
        if help_result:
            return {}, {}, help_result

        # 4. Map Action and Finalize
        tool_call = self._map_proposed_to_tool_call(
            monologue.get("proposed_action"), step, target_server
        )
        self._apply_vision_overrides(tool_call, vision_result)
        self._finalize_tool_call_normalization(tool_call, step, target_server)

        return tool_call, monologue, None

    async def _get_provided_response(self, step: dict[str, Any]) -> str | None:
        """Detect any user response or autonomous decision from bus_messages or previous_results."""
        provided_response = None
        if "bus_messages" in step:
            for bm in step["bus_messages"]:
                payload = bm.get("payload", {})
                if "user_response" in payload:
                    provided_response = payload["user_response"]
                    logger.info(f"[TETYANA] Found provided response: {provided_response}")
                    return str(provided_response)

        # Check previous_results for Atlas's autonomous decision as fallback
        if "previous_results" in step:
            for pr in reversed(step["previous_results"]):
                if pr.get("error") in ["autonomous_decision_made", "user_input_received"]:
                    # Injected via message bus usually, but here for safety
                    pass
        return None

    async def _validate_step_alignment(self, step: dict[str, Any], attempt: int) -> None:
        """Validate step aligns with global goal and apply suggested deviations."""

        if attempt != 1:
            return

        global_goal = shared_context.get_goal_context() or step.get("full_plan", "")
        if not global_goal or attempt != 1:
            return

        alignment = await self._validate_goal_alignment(step, global_goal)
        if not alignment.get("aligned") and alignment.get("deviation_suggested"):
            alt = alignment.get("suggested_alternative")
            logger.warning(
                f"[TETYANA] Step misaligned. Confidence: {alignment.get('confidence')}. Alternative: {alt}"
            )
            # Apply autonomous deviation if confidence is low enough for the current path
            if alignment.get("confidence", 0) < 0.3 and alt:
                logger.info("[TETYANA] Autonomous deviation: using alternative approach")
                step["action"] = alt
                step["deviation_applied"] = True
                step["original_action"] = step.get("action", "")

    def _verify_agentic_evidence(
        self,
        tool_result: dict[str, Any],
        tool_call: dict[str, Any],
    ) -> None:
        """'Empty Proof' Detector: Flags success=True with empty output as soft failure for investigation."""
        output_data = tool_result.get("output", "") or tool_result.get("result", "")
        if not tool_result.get("success") or str(output_data).strip():
            return

        data_intensive_tools = [
            "read_file",
            "search",
            "list_directory",
            "execute_command",
            "vibe_prompt",
            "maps_geocode",
            "maps_directions",
            "search_places",
            "maps_street_view",
            "fetch_url",
        ]
        current_tool_name = str(tool_call.get("name", "")).lower()

        if any(t in current_tool_name for t in data_intensive_tools):
            logger.warning(
                f"[TETYANA] Tool '{current_tool_name}' returned SUCCESS but EMPTY output. Soft-failure Reflexion triggered."
            )
            tool_result["success"] = False
            tool_result["error"] = (
                f"SUSPICIOUS_RESULT: Tool '{current_tool_name}' returned NO OUTPUT. "
                "Explain if this is expected, otherwise provide a different approach."
            )
        else:
            logger.info(
                f"[TETYANA] Tool '{current_tool_name}' returned silent success (empty output)."
            )

    async def _check_result_quality_reflexion(
        self, step: dict[str, Any], tool_call: dict[str, Any], tool_result: dict[str, Any]
    ) -> None:
        """Internal check to see if the tool result actually meets the objective."""
        expected = step.get("expected_result", "")
        if not expected:
            return

        reflexion_criteria = """
1. TRUTH CHECK: Does the tool output TRULY provide the expected result?
2. QUALITY CHECK: If the tool returned 'success' but the output is an error message, file-not-found, or incomplete data, mark as suspicious.
3. PERSISTENCE CHECK: If the step expected data to be saved (e.g., 'save to file', 'create report'), verify the output mentions the file path or confirming status.
   Note: 'macos-use_fetch_url' returns text content; if a file was expected, it must be followed by a save action.
"""
        prompt = f"""TECHNICAL QUALITY REFLEXION
Step: {step.get("action")}
Expected Result: {expected}
Tool Output: {str(tool_result.get("output", ""))[:1500]}

Analyze: {reflexion_criteria}

Respond in JSON ONLY:
{{
    "is_suspicious": true/false,
    "reason": "Technical reason for suspicion or null",
    "confidence": 0.0-1.0
}}
"""
        try:
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=prompt),
            ]
            response = await self.llm.ainvoke(messages)
            analysis = self._parse_response(cast("str", response.content))

            if analysis.get("is_suspicious") and analysis.get("confidence", 0) > 0.7:
                reason = analysis.get("reason", "Output does not meet expected result.")
                logger.warning(f"[TETYANA] Result flagged as suspicious: {reason}")
                tool_result["success"] = False
                tool_result["error"] = f"QUALITY_FAILURE: {reason}"
                tool_result["is_quality_failure"] = True
        except Exception as e:
            logger.debug(f"Reflexion check failed (ignoring): {e}")

    async def _perform_technical_reflexion(
        self,
        step: dict[str, Any],
        tool_call: dict[str, Any],
        tool_result: dict[str, Any],
    ) -> StepResult | None:
        """Perform technical reflexion with retries, deep reasoning, and VIBE healing."""

        TRANSIENT_ERRORS = [
            "Connection refused",
            "timeout",
            "rate limit",
            "Broken pipe",
            "Connection reset",
        ]
        max_self_fixes = 3
        fix_count = 0

        while not tool_result.get("success") and fix_count < max_self_fixes:
            fix_count += 1
            error_msg = tool_result.get("error", "Unknown error")

            # 1. Transient Retry
            if any(err.lower() in error_msg.lower() for err in TRANSIENT_ERRORS):
                logger.info(f"[TETYANA] Transient error. Retry {fix_count}/{max_self_fixes}...")
                await asyncio.sleep(1.0 * fix_count)
                tool_result.update(await self._execute_tool(tool_call))
                if tool_result.get("success"):
                    return None
                continue

            # 2. Deep Sequential Reasoning for persistent failures
            if fix_count >= 2:
                logger.info("[TETYANA] persistent failures. Engaging Deep Reasoning...")
                reasoning = await self.use_sequential_thinking(
                    f"I fail to execute '{step.get('action')}'. Error: {error_msg}. Propose DEVIATION if needed.",
                    total_thoughts=3,
                )
                analysis_text = reasoning.get("analysis", "").lower()
                if any(
                    kw in analysis_text
                    for kw in ["deviation", "alternative approach", "skip this step"]
                ):
                    return StepResult(
                        step_id=step.get("id", self.current_step),
                        success=False,
                        result=f"DEVIATION PROPOSED: {reasoning.get('analysis')}",
                        is_deviation=True,
                        deviation_info={
                            "analysis": reasoning.get("analysis"),
                            "proposal": analysis_text[:500],
                        },
                    )

            # 3. VIBE healing as ultimate fix
            if fix_count == max_self_fixes:
                logger.info("[TETYANA] Invoking VIBE for ultimate healing...")
                v_res_raw = await self._call_mcp_direct(
                    "vibe", "vibe_analyze_error", {"error_message": error_msg, "auto_fix": True}
                )
                v_res = self._format_mcp_result(v_res_raw) if v_res_raw else {}
                if v_res.get("success"):
                    if "voice_message" in v_res:
                        logger.info(f"[VIBE_VOICE] 🇺🇦 {v_res['voice_message']}")

                    # Retry the original tool call now that the environment might be fixed
                    tool_result.update(await self._execute_tool(tool_call))
                    if tool_result.get("success"):
                        return None

            # 4. Standard Reflexion Prompt
            try:
                tools_summary = getattr(shared_context, "available_tools_summary", "")
                reflexion_prompt = AgentPrompts.tetyana_reflexion_prompt(
                    str(step),
                    error_msg,
                    [r.to_dict() for r in self.results[-5:]],
                    tools_summary=tools_summary,
                )
                reflexion_resp = await self.reflexion_llm.ainvoke(
                    [
                        SystemMessage(
                            content="You are a Technical Debugger. Analyze error and suggest fix."
                        ),
                        HumanMessage(content=reflexion_prompt),
                    ]
                )
                reflexion = self._parse_response(cast("str", reflexion_resp.content))
                if reflexion.get("requires_atlas"):
                    break
                fix_action = reflexion.get("fix_attempt")
                if not fix_action:
                    break
                logger.info(f"[TETYANA] Attempting fix: {fix_action.get('tool')}")
                tool_result.update(await self._execute_tool(fix_action))
                if tool_result.get("success"):
                    return None
            except Exception as e:
                logger.error(f"[TETYANA] Reflexion failed: {e}")
                break

        return None

    def _finalize_step_result(
        self,
        step: dict[str, Any],
        tool_call: dict[str, Any],
        tool_result: dict[str, Any],
        monologue: dict[str, Any],
        vision_result: dict[str, Any] | None,
        attempt: int,
    ) -> StepResult:
        """Construct the final StepResult and update state."""
        final_voice_msg = cast("str | None", tool_result.get("voice_message")) or (
            cast("str | None", monologue.get("voice_message")) if attempt == 1 else None
        )

        if not final_voice_msg and attempt == 1:
            final_voice_msg = self.get_voice_message(
                "completed" if tool_result.get("success") else "failed",
                step=step.get("id", self.current_step),
                description=step.get("action", ""),
            )

        res = StepResult(
            step_id=step.get("id", self.current_step),
            success=tool_result.get("success", False),
            result=tool_result.get("output", ""),
            screenshot_path=tool_result.get("screenshot_path")
            or (vision_result.get("screenshot_path") if vision_result else None),
            voice_message=final_voice_msg,
            error=tool_result.get("error"),
            tool_call=tool_call,
            thought=monologue.get("thought") if isinstance(monologue, dict) else None,
            server=tool_result.get("server"),
        )

        self.results.append(res)
        # Update current step counter
        try:
            self.current_step = int(step.get("id", 0)) + 1
        except Exception:
            self.current_step += 1

        return res

    async def execute_step(self, step: dict[str, Any], attempt: int = 1) -> StepResult:
        """Executes a single plan step with Advanced Reasoning."""
        from src.brain.core.services.state_manager import state_manager

        self.attempt_count = attempt
        step_id = step.get("id", self.current_step)

        # 1. Detect Response & Check Consent
        provided_response = await self._get_provided_response(step)
        consent_block = await self._check_consent_requirements(step, provided_response, step_id)
        if consent_block:
            return consent_block

        # 2. Dynamic Inspection & Goal Alignment
        await self._validate_step_alignment(step, attempt)

        # 3. Vision & Grisha Feedback
        vision_result, vision_block = await self._perform_vision_analysis_if_needed(step, attempt)
        if vision_block:
            return vision_block

        grisha_feedback = await self._fetch_grisha_feedback(
            step, attempt, cast("int", step.get("id"))
        )

        # 4. Determine Action & Reasoning
        target_server = str(
            step.get("realm") or step.get("tool") or step.get("server") or "xcodebuild"
        )
        if target_server == "browser":
            target_server = "xcodebuild"

        tool_call, monologue, action_block = await self._determine_tool_action(
            step, target_server, attempt, grisha_feedback, vision_result, provided_response
        )
        if action_block:
            return action_block

        # 5. Tool Execution & Output Verification
        tool_result = await self._execute_tool(tool_call)
        self._verify_agentic_evidence(tool_result, tool_call)

        # 6. Quality Reflexion (Check if 'Success' is actually achievement)
        if tool_result.get("success"):
            await self._check_result_quality_reflexion(step, tool_call, tool_result)

        # 7. Technical Reflexion (if failed)
        reflexion_result = await self._perform_technical_reflexion(step, tool_call, tool_result)
        if reflexion_result:
            return reflexion_result

        # 7. Finalize and Update State
        res = self._finalize_step_result(
            step, tool_call, tool_result, monologue, vision_result, attempt
        )

        if state_manager.available:
            try:
                await state_manager.checkpoint("current", int(str(res.step_id)), res.to_dict())
            except Exception:
                pass

        return res

    def _fix_hallucinated_args(self, args: Any) -> Any:
        """Fix common LLM argument hallucinations (e.g., new_path -> path)."""
        if not isinstance(args, dict):
            return args
        if "new_path" in args and "path" not in args:
            args["path"] = args.pop("new_path")
            logger.info("[TETYANA] Fixed hallucinated argument: new_path -> path")
        if "cmd" in args and "command" not in args:
            args["command"] = args.pop("cmd")
            logger.info("[TETYANA] Fixed hallucinated argument: cmd -> command")
        return args

    def _normalize_tool_result(self, result: Any, tool_name: str) -> dict[str, Any]:
        """Normalize various MCP result formats into a standard success/error structure."""
        # Convert to dict format
        result = self._convert_to_dict(result)

        if not isinstance(result, dict):
            return {"success": False, "error": "Invalid result type"}

        # Ensure success field
        result["success"] = not result.get("isError", False)

        # Handle errors
        if not result.get("success"):
            self._log_dispatcher_errors(result, tool_name)
            result = self._extract_error_message(result)

        # Map content to output
        result = self._map_content_to_output(result)

        # Guarantee correct type for type checker
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        return result

    def _convert_to_dict(self, result: Any) -> dict[str, Any]:
        """Convert various result types to dict."""
        if hasattr(result, "model_dump"):
            return cast("dict[str, Any]", result.model_dump())
        if hasattr(result, "dict"):
            return cast("dict[str, Any]", result.dict())
        if not isinstance(result, dict):
            return {"content": [{"type": "text", "text": str(result)}], "isError": False}
        return cast("dict[str, Any]", result)

    def _extract_error_message(self, result: dict[str, Any]) -> dict[str, Any]:
        """Extract error message from result content."""
        if "error" not in result:
            content_text = self._extract_content_text(result.get("content", []))
            result["error"] = content_text or "Unknown tool execution error"
        return result

    def _extract_content_text(self, content: Any) -> str:
        """Extract text from content array."""
        if not isinstance(content, list):
            return ""

        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        return "".join(text_parts)

    def _map_content_to_output(self, result: dict[str, Any]) -> dict[str, Any]:
        """Map content field to output for compatibility."""
        if "content" in result and isinstance(result["content"], list) and not result.get("output"):
            output_text = self._extract_content_text(result["content"])
            if output_text:
                result["output"] = output_text
        return result

    def _log_dispatcher_errors(self, result: dict[str, Any], tool_name: str) -> None:
        """Log specific error types from the dispatcher."""
        error_msg = result.get("error", "")
        if result.get("validation_error"):
            logger.error(f"[TETYANA] Validation error for {tool_name}: {error_msg}")
        elif result.get("bad_request"):
            logger.error(f"[TETYANA] Bad request for {tool_name}: {error_msg}")
        elif result.get("tool_not_found"):
            logger.error(f"[TETYANA] Tool not found: {result.get('server')}.{result.get('tool')}")
        elif result.get("compatibility_error"):
            logger.error(f"[TETYANA] Compatibility error for {tool_name}: {error_msg}")

    async def _execute_tool(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        """Executes the tool call via unified Dispatcher"""

        mcp_manager.dispatcher.set_pid(self._current_pid)

        tool_name = str(tool_call.get("name") or tool_call.get("tool") or "")
        args = self._fix_hallucinated_args(
            tool_call.get("args") or tool_call.get("arguments") or {}
        )
        explicit_server = tool_call.get("server")

        # VALIDATION: Check for empty tool name
        if not tool_name or tool_name.lower() in ["none", "null", "undefined", ""]:
            logger.error(f"[TETYANA] Validation Error: Empty tool name in {tool_call}")
            return {
                "success": False,
                "error": "Tool Inference Failed: Could not determine which tool to use. Please specify a valid tool name or action.",
            }

        # VALIDATION: Check for required command argument for execute_command
        if tool_name in {"macos-use.execute_command", "execute_command"}:
            if not args.get("command") and not args.get("cmd"):
                logger.error(
                    "[TETYANA] Validation Error: Missing 'command' argument for execute_command"
                )
                return {
                    "success": False,
                    "error": "Validation Error: 'execute_command' requires a 'command' argument.",
                }

        try:
            result = await mcp_manager.dispatch_tool(tool_name, args, explicit_server)
            return self._normalize_tool_result(result, tool_name)
        except Exception as e:
            logger.error(f"[TETYANA] Tool execution failed: {e}")
            return {"success": False, "error": str(e)}

    async def _call_mcp_direct(self, server: str, tool: str, args: dict) -> dict[str, Any]:

        try:
            return cast("dict[str, Any]", await mcp_manager.dispatch_tool(tool, args, server))
        except Exception as e:
            logger.error(f"[TETYANA] Unified call failed for {server}.{tool}: {e}")
            return {"success": False, "error": str(e)}

    async def _run_terminal_command(self, args: dict[str, Any]) -> dict[str, Any]:
        """Executes a bash command using Terminal MCP"""

        command = args.get("command", "") or args.get("cmd", "") or ""

        # SAFETY CHECK: Block Cyrillic characters
        if re.search(r"[а-яА-ЯіїєґІЇЄҐ]", command):
            return {
                "success": False,
                "error": f"Command blocked: Contains Cyrillic characters. You are trying to execute a description instead of a command: '{command}'",
            }

        # Pass all args to the tool (supports cwd, stdout_file, etc.)
        # OPTIMIZATION: Use 'xcodebuild' server which now handles terminal commands natively
        res = await mcp_manager.call_tool("xcodebuild", "execute_command", args)
        return self._format_mcp_result(res)

    async def _gui_click(self, args: dict[str, Any]) -> dict[str, Any]:
        """Perform a click action using macos-use tool."""

        x, y = args.get("x", 0), args.get("y", 0)
        pid = int(args.get("pid", 0))
        res = await mcp_manager.call_tool(
            "xcodebuild", "macos-use_click_and_traverse", {"pid": pid, "x": float(x), "y": float(y)}
        )
        return self._format_mcp_result(res)

    async def _gui_type(self, args: dict[str, Any]) -> dict[str, Any]:
        """Perform a type action using macos-use tool."""

        text = args.get("text", "")
        pid = int(args.get("pid", 0))
        res = await mcp_manager.call_tool(
            "xcodebuild", "macos-use_type_and_traverse", {"pid": pid, "text": text}
        )
        return self._format_mcp_result(res)

    async def _gui_hotkey(self, args: dict[str, Any]) -> dict[str, Any]:
        """Perform a hotkey action with modifier mapping."""

        keys = args.get("keys", [])
        pid = int(args.get("pid", 0))
        modifier_map = {
            "cmd": "Command",
            "command": "Command",
            "shift": "Shift",
            "ctrl": "Control",
            "control": "Control",
            "opt": "Option",
            "option": "Option",
            "alt": "Option",
            "fn": "Function",
        }
        key_map = {
            "enter": "Return",
            "return": "Return",
            "esc": "Escape",
            "escape": "Escape",
            "space": "Space",
            "tab": "Tab",
            "up": "ArrowUp",
            "down": "ArrowDown",
            "left": "ArrowLeft",
            "right": "ArrowRight",
            "delete": "Delete",
            "backspace": "Delete",
            "home": "Home",
            "end": "End",
            "pageup": "PageUp",
            "pagedown": "PageDown",
            "f1": "F1",
            "f2": "F2",
            "f3": "F3",
            "f4": "F4",
            "f5": "F5",
            "f6": "F6",
            "f7": "F7",
            "f8": "F8",
            "f9": "F9",
            "f10": "F10",
            "f11": "F11",
            "f12": "F12",
        }
        modifiers, key_name = [], ""
        for k in keys:
            lower_k = k.lower()
            if lower_k in modifier_map:
                modifiers.append(modifier_map[lower_k])
            else:
                key_name = key_map.get(lower_k, k)

        if not key_name:
            return {"success": False, "error": "No non-modifier key specified"}
        res = await mcp_manager.call_tool(
            "xcodebuild",
            "macos-use_press_key_and_traverse",
            {"pid": pid, "keyName": key_name, "modifierFlags": modifiers},
        )
        return self._format_mcp_result(res)

    async def _gui_search_app(self, app_name: str) -> dict[str, Any]:
        """Launch an application using macos-use or fallback to Spotlight."""

        try:
            res = await mcp_manager.call_tool(
                "xcodebuild", "macos-use_open_application_and_traverse", {"identifier": app_name}
            )
            formatted = self._format_mcp_result(res)
            if formatted.get("success") and not formatted.get("error"):
                logger.info(f"[TETYANA] Successfully opened '{app_name}' via macos-use.")
                return formatted
            logger.warning(
                f"[TETYANA] macos-use open failed, falling back to legacy: {formatted.get('error')}",
            )
        except Exception as e:
            logger.warning(f"[TETYANA] macos-use open exception: {e}")

        try:
            name = "Calculator" if app_name.lower() in ["calculator", "калькулятор"] else app_name
            subprocess.run(["open", "-a", name], check=True, capture_output=True)
            return {"success": True, "output": f"Launched app: {name}"}
        except Exception:
            pass

        return await self._gui_spotlight_fallback(app_name)

    async def _gui_spotlight_fallback(self, app_name: str) -> dict[str, Any]:
        """Last resort: use Spotlight searching via UI keystrokes."""

        # Simplified Spotlight flow
        # Try to force English layout (ABC/U.S./English)
        switch_script = """
        tell application "System Events"
            try
                tell process "SystemUIServer"
                    set input_menu to (menu bar items of menu bar 1 whose description is "text input")
                    if (count of input_menu) > 0 then
                        click item 1 of input_menu
                        delay 0.2
                        set menu_items to menu 1 of item 1 of input_menu
                        repeat with mi in menu_items
                            set mname to name of mi
                            if mname is "ABC" or mname is "U.S." or mname is "English" or mname is "British" then
                                click mi
                                exit repeat
                            end if
                        end repeat
                    end if
                end tell
            on error err
                log err
            end try
        end tell
        """
        subprocess.run(["osascript", "-e", switch_script], check=False, capture_output=True)

        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to key code 49 using {command down}',
            ],
            check=True,
        )
        time.sleep(1.0)
        # Clear search field (Cmd+A, Backspace)
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to key code 0 using {command down}',
            ],
            check=True,
        )
        time.sleep(0.2)
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to key code 51',
            ],
            check=True,
        )
        time.sleep(0.2)
        # Paste and Enter
        subprocess.run(["pbcopy"], input=app_name.encode("utf-8"), check=True)
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to key code 9 using {command down}',
            ],
            check=True,
        )  # Cmd+V
        time.sleep(0.5)
        subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to key code 36'], check=True
        )  # Enter
        return {"success": True, "output": f"Attempted Spotlight launch for {app_name}"}

    async def _perform_gui_action(self, args: dict[str, Any]) -> dict[str, Any]:
        """Performs GUI interaction (click, type, hotkey, search_app)."""

        action = args.get("action", "")

        if action == "click":
            return await self._gui_click(args)
        if action == "type":
            return await self._gui_type(args)
        if action == "hotkey":
            return await self._gui_hotkey(args)
        if action in {"wait", "sleep"}:
            duration = float(args.get("duration", 1.0))
            await asyncio.sleep(duration)
            return {"success": True, "output": f"Waited for {duration}s"}
        if action == "search_app":
            return await self._gui_search_app(args.get("app_name", "") or args.get("text", ""))
        return {"success": False, "error": f"Unknown GUI action: {action}"}

    async def _save_browser_artifacts(
        self,
        step_id: Any,
        html_text: str | None = None,
        title_text: str | None = None,
        screenshot_b64: str | None = None,
    ) -> bool:
        """Save artifact files and register in notes/memory for Grisha's verification."""
        import time as _time

        from src.brain.config import SCREENSHOTS_DIR, WORKSPACE_DIR

        try:
            ts = _time.strftime("%Y%m%d_%H%M%S")
            artifacts = []

            if html_text:
                html_file = WORKSPACE_DIR / f"grisha_step_{step_id}_{ts}.html"
                html_file.parent.mkdir(parents=True, exist_ok=True)
                html_file.write_text(html_text, encoding="utf-8")
                artifacts.append(str(html_file))
                logger.info(f"[TETYANA] Saved HTML artifact: {html_file}")

            if screenshot_b64:
                SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
                img_file = SCREENSHOTS_DIR / f"grisha_step_{step_id}_{ts}.png"
                with open(img_file, "wb") as f:
                    f.write(base64.b64decode(screenshot_b64))
                artifacts.append(str(img_file))
                logger.info(f"[TETYANA] Saved screenshot artifact: {img_file}")

            note_content = self._construct_artifact_note(
                step_id, ts, artifacts, title_text, html_text
            )
            await self._register_artifacts(step_id, ts, artifacts, note_content)
            return True
        except Exception as e:
            logger.warning(f"[TETYANA] _save_artifacts exception: {e}")
            return False

    def _construct_artifact_note(
        self,
        step_id: Any,
        ts: str,
        artifacts: list[str],
        title_text: str | None,
        html_text: str | None,
    ) -> str:
        """Build the text content for the verification artifact note."""
        snippet = f"Title: {title_text}\n\n" if title_text else ""
        if html_text:
            snippet += f"HTML Snippet:\n{(html_text[:1000] + '...') if len(html_text) > 1000 else html_text}\n\n"

        detected = []
        if html_text:
            keywords = ["phone", "sms", "verification", "код", "телефон"]
            low = html_text.lower()
            detected = [kw for kw in keywords if kw in low]

        note_content = (
            f"Artifacts for step {step_id} saved at {ts}.\n\nFiles:\n"
            + ("\n".join(artifacts) if artifacts else "(no binary files captured)")
            + f"\n\n{snippet}"
        )
        if detected:
            note_content += f"Detected keywords in HTML: {', '.join(detected)}\n"
        return note_content

    async def _register_artifacts(
        self, step_id: Any, ts: str, artifacts: list[str], note_content: str
    ) -> None:
        """Register artifacts in notes and memory."""

        note_title = f"Grisha Artifact - Step {step_id} @ {ts}"
        try:
            await mcp_manager.dispatch_tool(
                "notes_create", {"body": f"# {note_title}\n\n{note_content}"}
            )
            logger.info(f"[TETYANA] Created verification artifact note for step {step_id}")
        except Exception as e:
            logger.warning(f"[TETYANA] Failed to create artifact note: {e}")

        try:
            await mcp_manager.call_tool(
                "memory",
                "create_entities",
                {
                    "entities": [
                        {
                            "name": f"grisha_artifact_step_{step_id}",
                            "entityType": "artifact",
                            "observations": artifacts,
                        }
                    ]
                },
            )
            logger.info(f"[TETYANA] Created memory artifact for step {step_id}")
        except Exception as e:
            logger.warning(f"[TETYANA] Failed to create memory artifact: {e}")

    async def _capture_browser_state(
        self, step_id: Any
    ) -> tuple[str | None, str | None, str | None]:
        """Collect title, HTML, and screenshot from the current browser page."""
        await asyncio.sleep(1.5)
        logger.info(f"[TETYANA] Collecting browser artifacts for step {step_id}...")

        title_text, html_text, screenshot_b64 = None, None, None
        try:
            # Title
            t_res = await mcp_manager.call_tool(
                "puppeteer", "puppeteer_evaluate", {"script": "document.title"}
            )
            if hasattr(t_res, "content") and t_res.content and hasattr(t_res.content[0], "text"):
                title_text = t_res.content[0].text

            # HTML
            h_res = await mcp_manager.call_tool(
                "puppeteer", "puppeteer_evaluate", {"script": "document.documentElement.outerHTML"}
            )
            if hasattr(h_res, "content") and h_res.content and hasattr(h_res.content[0], "text"):
                html_text = h_res.content[0].text

            # Screenshot
            s_res = await mcp_manager.call_tool(
                "puppeteer",
                "puppeteer_screenshot",
                {"name": f"grisha_step_{step_id}", "encoded": True},
            )
            if hasattr(s_res, "content"):
                for c in s_res.content:
                    if getattr(c, "type", "") == "image" and hasattr(c, "data"):
                        screenshot_b64 = c.data
                        break
                    if hasattr(c, "text") and c.text:
                        txt = c.text.strip()
                        if txt.startswith("iVBOR"):
                            screenshot_b64 = txt
                            break
        except Exception as e:
            logger.warning(f"[TETYANA] Browser capture failed: {e}")
        return title_text, html_text, screenshot_b64

    async def _browser_action(self, args: dict[str, Any]) -> dict[str, Any]:
        """Browser action via Puppeteer MCP with verification artifacts."""
        import asyncio  # Added import

        action = args.get("action", "")
        step_id = args.get("step_id")

        if action in {"navigate", "open"}:
            res = await mcp_manager.call_tool(
                "puppeteer", "puppeteer_navigate", {"url": args.get("url", "")}
            )
            title, html, shot = await self._capture_browser_state(step_id)
            await self._save_browser_artifacts(step_id, html, title, shot)
            return self._format_mcp_result(res)

        if action == "click":
            res = await mcp_manager.call_tool(
                "puppeteer",
                "puppeteer_click",
                {"selector": args.get("selector", "")},
            )

            # If click likely submitted a form, collect artifacts as well
            selector = args.get("selector", "") or ""
            if any(k in selector.lower() for k in ["submit", "next", "confirm", "phone", "sms"]):
                try:
                    # small delay to allow navigation
                    await asyncio.sleep(1.0)
                    # reuse collection
                    await self._browser_action(
                        {"action": "navigate", "url": args.get("url", ""), "step_id": step_id},
                    )
                except Exception:
                    pass

            return self._format_mcp_result(res)
        if action in {"type", "fill"}:
            return self._format_mcp_result(
                await mcp_manager.call_tool(
                    "puppeteer",
                    "puppeteer_fill",
                    {"selector": args.get("selector", ""), "value": args.get("value", "")},
                ),
            )
        if action == "screenshot":
            return self._format_mcp_result(
                await mcp_manager.call_tool("puppeteer", "puppeteer_screenshot", {}),
            )
        return {"success": False, "error": f"Unknown browser action: {action}"}

    async def _filesystem_action(self, args: dict[str, Any]) -> dict[str, Any]:
        """Filesystem operations via MCP"""

        action = args.get("action", "")
        path = args.get("path", "")

        # SMART ACTION INFERENCE if action is missing
        if not action or action == "filesystem":
            if "content" in args:
                action = "write_file"
            elif path.endswith("/") or (path and "." not in path.split("/")[-1]):
                action = "list_directory"
            else:
                action = "read_file"
            logger.info(f"[TETYANA] Inferred FS action: {action} for path: {path}")

        if action in {"read", "read_file"}:
            result = await mcp_manager.call_tool("filesystem", "read_file", {"path": path})
            shared_context.update_path(path, "read")
            return self._format_mcp_result(result)
        if action in {"write", "write_file"}:
            result = await mcp_manager.call_tool(
                "filesystem",
                "write_file",
                {"path": path, "content": args.get("content", "")},
            )
            shared_context.update_path(path, "write")
            return self._format_mcp_result(result)
        if action in {"create_dir", "mkdir", "create_directory"}:
            result = await mcp_manager.call_tool("filesystem", "create_directory", {"path": path})
            shared_context.update_path(path, "create_directory")
            return self._format_mcp_result(result)
        if action in {"list", "list_directory"}:
            result = await mcp_manager.call_tool("filesystem", "list_directory", {"path": path})
            shared_context.update_path(path, "access")
            return self._format_mcp_result(result)
        return {
            "success": False,
            "error": f"Unknown FS action: {action}. Valid: read_file, write_file, list_directory",
        }

    async def _github_action(self, args: dict[str, Any]) -> dict[str, Any]:
        """GitHub actions"""

        # Pass-through mostly
        mcp_tool = args.get("tool_name", "search_repositories")
        gh_args = args.copy()
        if "tool_name" in gh_args:
            del gh_args["tool_name"]
        res = await mcp_manager.call_tool("github", mcp_tool, gh_args)
        return self._format_mcp_result(res)

    async def _applescript_action(self, args: dict[str, Any]) -> dict[str, Any]:

        action = args.get("action", "execute_script")
        if action == "execute_script":
            return self._format_mcp_result(
                await mcp_manager.call_tool(
                    "applescript",
                    "execute_script",
                    {"script": args.get("script", "")},
                ),
            )
        if action == "open_app":
            return self._format_mcp_result(
                await mcp_manager.call_tool(
                    "applescript",
                    "open_app_safely",
                    {"app_name": args.get("app_name", "")},
                ),
            )
        if action == "volume":
            return self._format_mcp_result(
                await mcp_manager.call_tool(
                    "applescript",
                    "set_system_volume",
                    {"level": args.get("level", 50)},
                ),
            )
        return {"success": False, "error": "Unknown applescript action"}

    def _format_mcp_result(self, res: Any) -> dict[str, Any]:
        """Standardize MCP response to StepResult format"""
        if isinstance(res, dict) and "error" in res:
            return {"success": False, "error": res["error"]}

        output = ""
        content = getattr(res, "content", None)
        if content:
            for item in content:
                if hasattr(item, "text"):
                    output += item.text
        elif isinstance(res, dict) and "content" in res:
            for item in res["content"]:
                if isinstance(item, dict):
                    output += item.get("text", "")
                elif hasattr(item, "text"):
                    output += item.text

        # SMART ERROR DETECTION: Often MCP returns success but output contains "Error"
        lower_output = output.lower()
        error_keywords = [
            "error:",
            "failed:",
            "not found",
            "does not exist",
            "denied",
            "permission error",
        ]
        is_error = any(kw in lower_output for kw in error_keywords)

        if (
            is_error and len(output) < 500
        ):  # Don't trigger if it's a huge log that happens to have "error"
            return {"success": False, "error": output, "output": output}

        return {"success": True, "output": output or "Success (No output)"}

    def _extract_voice_essence(self, desc: str) -> str:
        """Extract the 'essence' of a description using regex."""
        if len(desc) <= 60:
            return desc.lower()
        match = re.search(r"^(.{10,50})[.;,]", desc)
        return (match.group(1) if match else desc[:50] + "...").lower()

    def _apply_voice_translations(self, essence: str) -> str:
        """Map English verbs and nouns to Ukrainian equivalents."""
        translations = {
            "create": "Створюю",
            "update": "Оновлюю",
            "check": "Перевіряю",
            "install": "Встановлюю",
            "run": "Запускаю",
            "execute": "Виконую",
            "call": "Викликаю",
            "search": "Шукаю",
            "list": "Переглядаю",
            "read": "Читаю",
            "write": "Записую",
            "delete": "Видаляю",
            "find": "Шукаю",
            "open": "Відкриваю",
            "take": "Роблю",
            "analyze": "Аналізую",
            "confirm": "Підтверджую",
            "verify": "Верифікую",
        }
        for eng, ukr in translations.items():
            if essence.startswith(eng):
                essence = essence.replace(eng, ukr, 1)
                break

        vocabulary = {
            "filesystem": "файлову систему",
            "directory": "папку",
            "directories": "папки",
            "folder": "папку",
            "folders": "папки",
            "file": "файл",
            "files": "файли",
            "desktop": "робочий стіл",
            "terminal": "термінал",
            "screenshot": "знімок екрана",
            "screen": "екран",
            "notes": "нотатки",
            "note": "нотатку",
            "calendar": "календар",
            "reminder": "нагадування",
            "reminders": "нагадування",
            "mail": "пошту",
            "email": "пошту",
            "notification": "сповіщення",
            "application": "програму",
            "apps": "програми",
            "browser": "браузер",
            "path": "шлях",
            "contents": "вміст",
            "task": "завдання",
            "plan": "план",
            "steps": "кроки",
            "step": "крок",
            "items": "елементи",
            "item": "елемент",
            "and": "та",
            "with": "з",
            "for": "для",
            "in": "в",
            "on": "на",
            "to": "до",
            "of": " ",
            "the": " ",
            "a": " ",
            "an": " ",
            "user": "користувача",
            "reading": "читаю",
            "writing": "записую",
        }

        words = essence.split()
        translated = []
        for word in words:
            clean = word.strip(".,()[]{}'\"$").lower()
            if clean in vocabulary:
                val = vocabulary[clean]
                if val.strip():
                    translated.append(val)
            elif clean in ["$home", "home"]:
                translated.append("домашню папку")
            elif not (len(clean) > 1 and all(c in "0123456789abcdefABCDEF-/" for c in clean)):
                translated.append(word)
        return " ".join(translated)

    def _clean_voice_essence(self, essence: str, action: str) -> str:
        """Filter Latin characters and apply final cleanup."""

        # Remove words with Latin characters
        essence = " ".join([w for w in essence.split() if not re.search(r"[a-zA-Z]", w)])
        essence = (
            essence.replace("json", "дані").replace("api", "інтерфейс").replace("mcp", "система")
        )

        if not essence.strip():
            fallbacks = {"starting": "виконую заплановану дію", "completed": "дію завершено"}
            essence = fallbacks.get(action, "поточний етап")
        return re.sub(r"\s+", " ", essence).strip()

    def get_voice_message(self, action: str, **kwargs) -> str:
        """Generates context-aware TTS message dynamically."""
        voice_msg = kwargs.get("voice_message")
        if voice_msg and len(voice_msg) > 5:
            return cast("str", voice_msg)

        step_id = kwargs.get("step", 1)
        desc = kwargs.get("description", "")
        error = kwargs.get("error", "")

        essence = self._extract_voice_essence(desc)
        essence = self._apply_voice_translations(essence)
        essence = self._clean_voice_essence(essence, action)

        if action == "completed":
            return f"Крок {step_id}: {essence} — виконано."
        if action == "failed":
            err_clean = str(error).split("\n")[0][:50] if error else "Помилка."
            return f"У кроці {step_id} не вдалося {essence}. Помилка: {err_clean}"
        if action == "starting":
            return f"Розпочинаю крок {step_id}: {essence}."
        if action == "asking_verification":
            return f"Крок {step_id} завершено. Гріша, верифікуй."

        return f"Статус кроку {step_id}: {action}."

    def _parse_response(self, content: str) -> dict[str, Any]:
        """Parse JSON response from LLM with GitHub API fallback."""
        # Handle GitHub API timeout specially
        if "HTTPSConnectionPool" in content and (
            "Read timed out" in content or "COPILOT ERROR" in content
        ):
            return {
                "tool_call": {
                    "name": "browser",
                    "args": {"action": "navigate", "url": "https://1337x.to"},
                },
                "voice_message": "GitHub API не відповідає, використаю браузер напряму для пошуку.",
            }
        # Use base class parsing
        return super()._parse_response(content)

    async def evaluate_fix_retry(
        self,
        fix_info: Any,
        current_step_id: str,
        current_progress: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Decide whether to retry a fixed step.

        Args:
            fix_info: FixedStepInfo from parallel manager
            current_step_id: currently executing step
            current_progress: current system state

        Returns:
            dict with:
                action: "retry", "skip", "noted"
                reason: decision rationale
        """

        # Basic logic:
        # 1. If we are far ahead (> 2 steps), probably better to skip/note
        # 2. If we are on the NEXT step, good to retry
        # 3. If fix is critical data, might need to retry regardless

        try:
            fixed_step = str(fix_info.step_id)
            curr = str(current_step_id)

            # Simple distance measure if steps are numeric
            distance = 100.0
            try:
                # Handle "3" vs "3.1"
                f_val = float(fixed_step)
                c_val = float(curr)
                distance = c_val - f_val
            except ValueError:
                pass

            logger.info(
                f"[TETYANA] Evaluating fix for {fixed_step} (current: {curr}, dist: {distance})"
            )

            if distance > 2:
                # Too far ahead
                return {
                    "action": "noted",
                    "reason": f"System has moved {distance} steps ahead. Retrying might disrupt flow.",
                }

            if distance < 0:
                # Weird, we went back?
                return {"action": "noted", "reason": "Fixed step is in the future?"}

            # Ask Reasoning LLM for deeper check
            # We want to know if the current path depends on the missed result
            prompt = f"""FIX EVALUATION
            
            A previously failed step has been fixed in the background.
            Failed Step ID: {fixed_step}
            Fix: {fix_info.fix_description}
            
            Current Step ID: {curr}
            Current Action: {current_progress.get("action", "Unknown")}
            
            Decide if we should:
            1. RETRY the fixed step immediately (interrupting current flow)
            2. SKIP retrying (current path found alternative or it's too late)
            
            JSON Response:
            {{ "decision": "RETRY" or "SKIP", "reason": "..." }}
            """

            messages = [
                SystemMessage(content="You are a flow controller. Optimize for stability."),
                HumanMessage(content=prompt),
            ]
            response = await self.reasoning_llm.ainvoke(messages)
            decision_data = self._parse_response(str(response.content))

            decision = decision_data.get("decision", "SKIP")
            return {
                "action": "retry" if decision == "RETRY" else "noted",
                "reason": decision_data.get("reason", "LLM Decision"),
            }

        except Exception as e:
            logger.warning(f"[TETYANA] Fix evaluation failed: {e}")
            return {"action": "noted", "reason": "Evaluation error"}
