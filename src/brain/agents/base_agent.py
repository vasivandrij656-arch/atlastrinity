"""BaseAgent - Shared utilities for Trinity agents

This module provides common functionality used by Atlas, Tetyana, and Grisha agents.
"""

import json
from typing import Any, cast


class BaseAgent:
    """Base class for Trinity agents with shared utilities."""

    def _parse_response(self, content: str) -> dict[str, Any]:
        """Parse JSON response from LLM with resilience."""
        text = str(content).strip()

        # 1. Try markdown JSON extraction
        if "```json" in text:
            result = self._extract_json_from_block(text, "```json")
            if result:
                return result

        # 2. Try generic code block extraction
        if "```" in text:
            result = self._extract_json_from_block(text, "```")
            if result:
                return result

        # 3. Try natural JSON extraction
        result = self._extract_json_from_text(text)
        if result:
            return result

        # 4. Fuzzy YAML parsing
        try:
            return self._parse_fuzzy_yaml(text)
        except Exception:
            pass

        return {"raw": text}

    def _extract_json_from_block(self, text: str, marker: str) -> dict[str, Any] | None:
        """Extracts JSON from a specific markdown block."""
        blocks = text.split(marker)
        for block in blocks[1:]:
            inner = block.split("`")[0].strip()
            if not inner and "```" in block:  # Handle empty marker case
                continue
            try:
                # Basic cleanup in case of nested blocks
                if inner.startswith("{") and "}" in inner:
                    return cast("dict[str, Any]", json.loads(inner))
            except json.JSONDecodeError:
                continue
        return None

    def _extract_json_from_text(self, text: str) -> dict[str, Any] | None:
        """Attempts to find and parse raw JSON within a string."""
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                candidate = text[start:end]
                return cast("dict[str, Any]", json.loads(candidate))
        except (json.JSONDecodeError, Exception):
            pass
        return None

    def _parse_fuzzy_yaml(self, text: str) -> dict[str, Any]:
        """Parse YAML-like key: value pairs."""
        data: dict[str, Any] = {}
        for line in text.strip().split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip().lower()
                value = value.strip()

                # Type conversion
                if value.lower() == "true":
                    data[key] = True
                elif value.lower() == "false":
                    data[key] = False
                elif value.replace(".", "", 1).isdigit():
                    data[key] = float(value)
                else:
                    data[key] = value

        # Valid if has expected fields
        if any(field in data for field in ["verified", "intent", "success", "steps"]):
            return data
        raise ValueError("No valid fields found")

    async def use_sequential_thinking(
        self,
        task: str,
        total_thoughts: int = 3,
        capabilities: str | None = None,
    ) -> dict[str, Any]:
        """Universal reasoning capability for any agent.
        Uses a dedicated LLM (as configured in sequential_thinking.model) to generate
        deep thoughts and stores them via the sequential-thinking MCP tool.
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        from src.brain.config.config_loader import config
        from src.brain.mcp.mcp_manager import mcp_manager
        from src.brain.monitoring.logger import logger
        from src.providers.factory import create_llm

        agent_name = self.__class__.__name__.upper()
        logger.info(f"[{agent_name}] 🤔 Thinking deeply about: {task[:60]}...")

        # 1. Get sequential thinking model from MCP config or global reasoning
        model_name = (
            config.get("mcp.sequential_thinking.model")
            or config.get("models.reasoning")
            or config.get("models.default")
        )

        if not model_name or not model_name.strip():
            raise ValueError(
                "[BASE_AGENT] Sequential thinking model not configured. "
                "Please set 'models.reasoning' or 'mcp.sequential_thinking.model' in config.yaml"
            )

        # 2. Initialize dedicated thinker
        # We need to ensure providers is in path, usually it's there via agent init overrides
        try:
            thinker_llm = create_llm(model_name=model_name)
        except ImportError:
            logger.error("Could not import LLM provider factory. Ensure 'providers' is in sys.path")
            return {"success": False, "analysis": "Reflexion failed due to import error"}

        full_analysis = ""
        current_context = ""  # Accumulate thoughts for LLM context
        thought_content = ""  # Safe initialization for structured output parsing

        # Capability context
        cap_ctx = f"\nAGENT CAPABILITIES:\n{capabilities}\n" if capabilities else ""

        try:
            for i in range(1, total_thoughts + 1):
                is_last = i == total_thoughts

                # 3. Ask LLM for the next thought
                prompt = f"""You are a deep technical reasoning engine and Strategic Architect.
TASK: {task}
{cap_ctx}
PREVIOUS THOUGHTS:
{current_context}

STEP {i}/{total_thoughts}:
Generate the next logical thought to analyze this problem. 
- Focus on root causes, technical details, and specific actionable solutions.
- **INTERNAL REASONING**: Always reason in ENGLISH for technical precision.
- **FINAL RECOMMENDATION**: If this is the final thought (Step {total_thoughts}), provide the summary/recommendation in the SAME LANGUAGE as the TASK (e.g., Ukrainian).
- Output ONLY the raw thought text. Do not wrap in JSON or Markdown blocks.
- **IMPORTANT**: If your task requires real-time data, check AGENT CAPABILITIES. 
- Never say "I don't have access" if the tools are listed.
"""
                response = await thinker_llm.ainvoke(
                    [
                        SystemMessage(
                            content="You are a Sequential Thinking Engine. Reason in English, but provide final conclusions in the task language.",
                        ),
                        HumanMessage(content=prompt),
                    ],
                )
                content_raw = response.content if hasattr(response, "content") else str(response)
                thought_content = content_raw if isinstance(content_raw, str) else str(content_raw)

                # 4. Record thought via MCP tool (records history)
                logger.debug(f"[{agent_name}] Thought cycle {i}: {thought_content[:100]}...")

                await mcp_manager.dispatch_tool(
                    "sequential-thinking.sequentialthinking",
                    {
                        "thought": thought_content,
                        "thoughtNumber": i,
                        "totalThoughts": total_thoughts,
                        "nextThoughtNeeded": not is_last,
                    },
                )

                # Update context for next iteration
                current_context += f"Thought {i}: {thought_content}\n"
                # Return full content without aggressive truncation (use 100k as safe guard)
                full_analysis += f"\n[Thought {i}]: {thought_content[:100000]}"

            logger.info(f"[{agent_name}] Reasoning complete using model {model_name}.")
            return {
                "success": True,
                "analysis": full_analysis,
                "last_thought": thought_content,  # CRITICAL: Return raw final thought for structured output extraction
            }

        except Exception as e:
            logger.warning(f"[{agent_name}] Sequential thinking unavailable/failed: {e}")
            # Do not crash the agent, just return failure so it can fallback to standard logic
            return {"success": False, "error": str(e), "analysis": full_analysis}
