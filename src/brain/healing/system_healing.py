"""Unified Self-Healing System (The Phoenix Protocol)

This module implements the advanced self-healing architecture:
1. Deep Analysis: Uses Vibe to understand root causes.
2. Strategy Engine: Decides on Hot Patch vs Service Restart vs System Restart.
3. Healing Orchestrator: Manages the lifecycle of the fix.
"""

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from src.brain.mcp.mcp_manager import mcp_manager  # pyre-ignore

logger = logging.getLogger("brain.healing")


class HealingStrategy(Enum):
    HOT_PATCH = "hot_patch"  # Apply code fix, no restart
    SERVICE_RESTART = "service_restart"  # Restart specific component (e.g. MCP)
    PHOENIX_RESTART = "phoenix_restart"  # Full system pause -> save -> restart -> resume
    USER_INTERVENTION = "user_intervention"  # Too complex/risky for auto-heal


@dataclass
class AnalysisResult:
    root_cause: str
    severity: str  # MINOR, SERVICE_CRITICAL, SYSTEM_CRITICAL
    suggested_strategy: HealingStrategy
    fix_plan: str
    confidence: float


@dataclass
class HealingTask:
    task_id: str
    error_context: str
    step_id: str
    status: str = "pending"
    strategy: HealingStrategy = HealingStrategy.HOT_PATCH
    analysis: AnalysisResult | None = None
    created_at: datetime = field(default_factory=datetime.now)


class DeepAnalysis:
    """Analyzes errors using system context and Vibe."""

    async def analyze(
        self, error: str, log_context: str, step_context: dict[str, Any]
    ) -> AnalysisResult:
        """
        Perform deep analysis of the error.
        """
        try:
            from src.brain.mcp.mcp_manager import mcp_manager  # pyre-ignore

            logger.info(
                f"[HEALING] Starting Deep Analysis for error: {error[:100]}..."
            )  # pyre-ignore

            # Construct a rich prompt for Vibe
            prompt = f"""
            CRITICAL SYSTEM ERROR ANALYSIS REQUIRED.
            
            ERROR:
            {error}
            
            CONTEXT:
            Step ID: {step_context.get("step_id", "unknown")}
            Action: {step_context.get("action", "unknown")}
            
            LOGS (Last 20 lines):
            {log_context[-2000:]}  # pyre-ignore
            
            TASK:
            1. Identify the ROOT CAUSE only.
            2. Determine SEVERITY:
               - MINOR: logic error, handled by code change.
               - SERVICE_CRITICAL: Specific tool/service is dead/stuck.
               - SYSTEM_CRITICAL: Memory leak, deadlock, corrupted state.
            3. Recommend STRATEGY: HOT_PATCH, SERVICE_RESTART, or PHOENIX_RESTART.
            
            Output JSON only:
            {{
                "root_cause": "...",
                "severity": "...",
                "strategy": "...",
                "fix_plan": "...",
                "confidence": 0.0 to 1.0
            }}
            """

            # Call Vibe (fast reasoning mode if possible, but standard is fine)
            result = await mcp_manager.call_tool(
                "vibe",
                "vibe_analyze_error",
                {
                    "error_message": error,
                    "log_context": prompt,
                    "auto_fix": False,  # We just want analysis first
                },
            )

            # Parse result (assuming Vibe returns text that might contain JSON)
            # This is a simplified parser, in prod we'd make Vibe return struct data
            text_result = self._extract_text(result)
            parsed = self._parse_json_from_text(text_result)

            strategy_map = {
                "HOT_PATCH": HealingStrategy.HOT_PATCH,
                "SERVICE_RESTART": HealingStrategy.SERVICE_RESTART,
                "PHOENIX_RESTART": HealingStrategy.PHOENIX_RESTART,
                "USER_INTERVENTION": HealingStrategy.USER_INTERVENTION,
            }

            strategy_key = str(parsed.get("strategy", "HOT_PATCH"))
            return AnalysisResult(
                root_cause=parsed.get("root_cause", "Unknown"),
                severity=parsed.get("severity", "MINOR"),
                suggested_strategy=strategy_map.get(strategy_key, HealingStrategy.HOT_PATCH),
                fix_plan=parsed.get("fix_plan", ""),
                confidence=float(parsed.get("confidence", 0.5)),
            )

        except Exception as e:
            logger.error(f"[HEALING] Deep analysis failed: {e}")
            # Fallback
            return AnalysisResult(
                root_cause=f"Analysis failed: {e}",
                severity="MINOR",
                suggested_strategy=HealingStrategy.HOT_PATCH,
                fix_plan="Attempt generic retry",
                confidence=0.1,
            )

    def _extract_text(self, result: Any) -> str:
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            return str(result.get("text") or result.get("content") or result)
        return str(result)

    def _parse_json_from_text(self, text: str) -> dict:
        try:
            # Try finding JSON block
            import re

            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return json.loads(text)
        except:
            return {}


class StrategyEngine:
    """Decides on the best course of action."""

    def decide(self, analysis: AnalysisResult) -> HealingStrategy:
        # Policy: If confidence is low, downgrade to USER_INTERVENTION
        if (
            analysis.confidence < 0.6
            and analysis.suggested_strategy == HealingStrategy.PHOENIX_RESTART
        ):
            logger.warning(
                "[HEALING] Low confidence on Phoenix Restart, downgrading to User Intervention."
            )
            return HealingStrategy.USER_INTERVENTION

        return analysis.suggested_strategy


class HealingOrchestrator:
    """Manages the Healing Lifecycle."""

    def __init__(self):
        self.analyzer = DeepAnalysis()
        self.strategy_engine = StrategyEngine()
        self._active_tasks = {}

    async def anticipatory_patching(self):
        """HOCE: Proactively check system health and apply pre-emptive patches.

        This logic runs during orchestrator warmup to ensure a clean execution environment.
        """
        logger.info("[HOCE HEALING] Engaging Anticipatory Patching...")

        try:
            # 1. Check MCP Health for all available servers
            unhealthy_servers = []

            # Check currently connected ones first
            connected = mcp_manager.get_connected_servers()
            for server in connected:
                if not await mcp_manager.health_check(server):
                    unhealthy_servers.append(server)

            if unhealthy_servers:
                logger.warning(
                    f"[HOCE HEALING] Found {len(unhealthy_servers)} unhealthy servers: {unhealthy_servers}"
                )
                for server in unhealthy_servers:
                    logger.info(f"[HOCE HEALING] Proactively restarting {server}...")
                    await mcp_manager.restart_server(server)
            else:
                logger.info("[HOCE HEALING] All active servers are healthy.")

        except Exception as e:
            logger.error(f"[HOCE HEALING] Anticipatory patching failed: {e}")

    async def handle_error(
        self, step_id: str, error: str, context: dict[str, Any], log_context: str
    ):
        task_id = f"heal_{uuid4().hex[:8]}"  # pyre-ignore
        task = HealingTask(task_id=task_id, step_id=step_id, error_context=error)
        self._active_tasks[task_id] = task

        # 1. Analyze
        analysis = await self.analyzer.analyze(error, log_context, context)
        task.analysis = analysis

        # 2. Decide
        strategy = self.strategy_engine.decide(analysis)
        task.strategy = strategy

        logger.info(f"[HEALING] Strategy selected: {strategy.value} for {step_id}")

        # 3. Execute
        if strategy == HealingStrategy.HOT_PATCH:
            await self._run_hot_patch(task)
        elif strategy == HealingStrategy.SERVICE_RESTART:
            await self._run_service_restart(task)
        elif strategy == HealingStrategy.PHOENIX_RESTART:
            await self._run_phoenix_protocol(task)
        else:
            await self._notify_user(task)

    async def _run_hot_patch(self, task: HealingTask):
        # Delegate to existing parallel healing logic (Vibe Fix)
        # For now, we import the singleton to avoid code duplication
        from src.brain.healing.parallel_healing import parallel_healing_manager  # pyre-ignore

        # Translate back to parallel manager format
        await parallel_healing_manager.submit_healing_task(
            step_id=task.step_id,
            error=task.error_context,
            step_context={},  # Passed context would go here
            log_context="",
            priority=1,
        )

    async def _run_service_restart(self, task: HealingTask):
        """Restart a specific service (usually an MCP server)."""

        # Try to infer service name from analysis
        root_cause = task.analysis.root_cause if task.analysis else "unknown"  # pyre-ignore
        target_service = self._infer_service_name(root_cause)
        if target_service:
            logger.info(f"[HEALING] Restarting service: {target_service}")
            await mcp_manager.restart_server(target_service)
        else:
            logger.warning("[HEALING] Could not infer service to restart.")

    async def _run_phoenix_protocol(self, task: HealingTask):
        """
        The Phoenix Protocol:
        1. Pause Orchestrator
        2. Snapshot State
        3. Trigger Restart
        """
        logger.critical(f"[HEALING] 🦅 INITIATING PHOENIX PROTOCOL for task {task.task_id}")

        from src.brain.core.server.server import trinity  # pyre-ignore
        from src.brain.tools.recovery import recovery_manager  # pyre-ignore

        # 1. Pause
        # We need to access the orchestrator instance.
        # Ideally passed in or accessed via singleton if available.
        # Assuming 'trinity' global is providing access to orchestrator logic.

        # 2. Snapshot
        # We need the current orchestrator state.
        state = trinity.get_state() if trinity else {}
        success = await recovery_manager.save_snapshot(
            orchestrator_state=state,
            task_context={
                "task_id": task.task_id,
                "current_step_id": task.step_id,
                "reason": task.error_context,
            },
        )

        if success:
            logger.critical("[HEALING] Snapshot saved. RESTARTING SYSTEM...")
            # 3. Restart
            # We use a special exit code or restart script
            import os

            # If running via a supervisor (like npm or a loop script), exit(1) might restart.
            # But let's look for a dedicated restart script or allow the parent process to handle it.
            # For now, we'll try to re-exec the python process.

            # NOTE: In a real deploy, 'restart_vibe_clean.sh' or similar might be better.
            # But re-executing python is a standard "soft" restart.
            os.execl(sys.executable, sys.executable, *sys.argv)  # nosec B606 # pyre-ignore
        else:
            logger.error("[HEALING] Snapshot failed! Aborting Phoenix Protocol.")

    async def _notify_user(self, task: HealingTask):
        # Use message bus to alert user
        pass

    def _infer_service_name(self, text: str) -> str | None:
        text = text.lower()
        if "vibe" in text:
            return "vibe"
        if "google" in text or "maps" in text:
            return "xcodebuild"
        if "fs" in text or "filesystem" in text:
            return "filesystem"
        return None


# Singleton
healing_orchestrator = HealingOrchestrator()
