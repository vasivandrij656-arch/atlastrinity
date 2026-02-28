"""Constraint Monitor

Periodically checks system logs against user-defined constraints.
Triggers priority parallel healing if violations are detected.
"""

import os

from src.brain.config import BRAIN_DIR
from src.brain.healing.parallel_healing import parallel_healing_manager
from src.brain.monitoring.logger import logger

CONSTRAINTS_FILE = os.path.join(BRAIN_DIR, "data", "user_constraints.txt")


class ConstraintMonitor:
    """Monitors system behavior against user constraints."""

    def __init__(self):
        self._last_check_logs: list[dict] = []
        self._is_running = False

    async def check_compliance(self, log_context: str, recent_logs: list[dict]) -> None:
        """
        Check if recent logs violate any user constraints.
        This is a non-blocking check.
        """
        if self._is_running:
            return

        try:
            self._is_running = True

            # 1. Read and filter constraints
            constraints = self._read_constraints()
            if not constraints or not recent_logs or recent_logs == self._last_check_logs:
                return

            self._last_check_logs = recent_logs[-20:]
            filtered_constraints = self._filter_constraints(constraints)

            if not filtered_constraints:
                logger.debug("[CONSTRAINT_MONITOR] No applicable constraints after filtering")
                return

            # 2. Analyze with LLM
            result_text = await self._audit_logs(log_context, filtered_constraints)

            # 3. Handle Violations
            if "VIOLATION:" in result_text:
                violation = self._extract_violation(result_text)
                logger.warning(f"[CONSTRAINT_MONITOR] Violation detected: {violation[:100]}...")

                await parallel_healing_manager.submit_healing_task(
                    step_id="constraint_monitor",
                    error=f"User Constraint Violation: {violation}",
                    step_context={"action": "monitor_constraints", "constraint": violation},
                    log_context=log_context,
                    priority=2,
                )

        except Exception as e:
            logger.warning(f"[CONSTRAINT_MONITOR] Check failed: {e}")
        finally:
            self._is_running = False

    def _filter_constraints(self, constraints: list[str]) -> list[str]:
        """Filters out constraints that are irrelevant based on current config."""
        from src.brain.config.config_loader import config

        voice_lang = config.get("voice.language", "uk")

        filtered = []
        for c in constraints:
            # Skip language constraints if Ukrainian voice is configured
            if voice_lang == "uk" and "language" in c.lower() and "ukrainian" in c.lower():
                continue
            filtered.append(c)
        return filtered

    async def _audit_logs(self, log_context: str, constraints: list[str]) -> str:
        """Sends logs and constraints to an LLM for auditing."""
        from src.brain.agents.atlas import Atlas

        audit_agent = Atlas()

        constraints_str = "\n".join([f"- {c}" for c in constraints])
        prompt = f"""CONSTRAINT CHECK
Analyze these recent system logs against the following strict user constraints.

USER CONSTRAINTS:
{constraints_str}

RECENT LOGS:
{log_context[-3000:]}

If any constraint is VIOLATED, report it. If all adhere, reply "COMPLIANT".
If violated, format response as:
VIOLATION: [Constraint description]
EVIDENCE: [Log line or observation]
"""
        response = await audit_agent.llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return str(content)

    def _extract_violation(self, text: str) -> str:
        """Parses the LLM response to extract the specific violation."""
        for line in text.split("\n"):
            if "VIOLATION:" in line:
                return line.split("VIOLATION:")[1].strip()

        # Fallback: extract anything suspicious
        for line in text.split("\n"):
            if any(k in line.lower() for k in ["violation", "constraint", "error"]):
                return line.strip()[:100]

        return "Unknown Violation"

    def _read_constraints(self) -> list[str]:
        """Read constraints from file."""
        if not os.path.exists(CONSTRAINTS_FILE):
            return []

        try:
            with open(CONSTRAINTS_FILE) as f:
                lines = f.readlines()
            # Filter comments and empty lines
            return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
        except Exception:
            return []


constraint_monitor = ConstraintMonitor()
