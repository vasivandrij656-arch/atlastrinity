"""Self-Healing Hypermodule — Unified Self-Sufficiency System.

Consolidates all scattered self-healing, maintenance, and diagnostic logic into a
single orchestrator with 4 operating modes:

- HEAL:     Reactive error fixing (wraps HealingOrchestrator + ParallelHealingManager)
- DIAGNOSE: System health diagnostics (SystemFixer + health_checks + MCP health)
- PREVENT:  Preventive maintenance (log rotation, cache cleanup, config sync, CI/CD)
- IMPROVE:  Proactive code improvements (log analysis → hotspots → Vibe fix → commit)

Usage:
    from src.brain.healing.hypermodule import healing_hypermodule, HealingMode

    # Reactive healing
    result = await healing_hypermodule.run(HealingMode.HEAL, context={"error": "...", ...})

    # Full diagnostics
    result = await healing_hypermodule.run(HealingMode.DIAGNOSE)

    # Preventive maintenance
    result = await healing_hypermodule.run(HealingMode.PREVENT)

    # Proactive improvement cycle
    result = await healing_hypermodule.run(HealingMode.IMPROVE)
"""

import logging
import time
from typing import Any

from src.brain.healing.ci_bridge import CIBridge, ci_bridge
from src.brain.healing.improvement_engine import ImprovementEngine, improvement_engine
from src.brain.healing.log_analyzer import LogAnalyzer, log_analyzer
from src.brain.healing.modes import (
    DiagnosticReport,
    HealingMode,
    HealingResult,
)
from src.brain.healing.server_manager import ServerManager, server_manager

logger = logging.getLogger("brain.healing.hypermodule")


class SelfHealingHypermodule:
    """Unified self-healing orchestrator.

    Consolidates all healing/maintenance logic into a single entry point.
    Dispatches to mode-specific handlers, manages component lifecycle,
    and coordinates cross-cutting concerns (state preservation, CI/CD, commits).
    """

    def __init__(
        self,
        analyzer: LogAnalyzer | None = None,
        bridge: CIBridge | None = None,
        srv_manager: ServerManager | None = None,
        imp_engine: ImprovementEngine | None = None,
    ):
        self.log_analyzer = analyzer or log_analyzer
        self.ci_bridge = bridge or ci_bridge
        self.server_manager = srv_manager or server_manager
        self.improvement_engine = imp_engine or improvement_engine

        self._initialized = False
        self._running = False

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize the hypermodule and start background services."""
        if self._initialized:
            return

        logger.info("[Hypermodule] Initializing self-healing system...")

        # Start background log analyzer
        self.log_analyzer.start()

        # Check for pending recovery snapshots
        if self.server_manager.has_pending_snapshot():
            state = await self.server_manager.restore_task_state()
            if state:
                logger.info(
                    f"[Hypermodule] Found pending recovery state, "
                    f"task can resume from: {state.get('current_step', 'unknown')}"
                )

        self._initialized = True
        self._running = True
        logger.info("[Hypermodule] Self-healing system initialized")

    async def shutdown(self) -> None:
        """Gracefully shut down all healing services."""
        logger.info("[Hypermodule] Shutting down self-healing system...")
        self._running = False
        self.log_analyzer.stop()
        self._initialized = False
        logger.info("[Hypermodule] Self-healing system stopped")

    # ─── Main Entry Point ─────────────────────────────────────────────────────

    async def run(
        self,
        mode: HealingMode,
        context: dict[str, Any] | None = None,
    ) -> HealingResult:
        """Main entry point. Dispatches to mode-specific handler.

        Args:
            mode: Operating mode (HEAL, DIAGNOSE, PREVENT, IMPROVE).
            context: Mode-specific context dict.

        Returns:
            HealingResult with operation outcome.
        """
        if not self._initialized:
            await self.initialize()

        ctx = context or {}
        start_time = time.monotonic()
        logger.info(f"[Hypermodule] Running mode: {mode.value}")

        try:
            if mode == HealingMode.HEAL:
                result = await self.heal(
                    error=ctx.get("error", ""),
                    step_context=ctx.get("step_context", {}),
                    step_id=ctx.get("step_id", ""),
                    step_result=ctx.get("step_result"),
                    depth=ctx.get("depth", 0),
                )
            elif mode == HealingMode.DIAGNOSE:
                result = await self.diagnose(targets=ctx.get("targets"))
            elif mode == HealingMode.PREVENT:
                result = await self.prevent()
            elif mode == HealingMode.IMPROVE:
                result = await self.improve(
                    focus_areas=ctx.get("focus_areas"),
                    max_improvements=ctx.get("max_improvements"),
                )
            else:
                result = HealingResult(
                    mode=mode,
                    success=False,
                    message=f"Unknown healing mode: {mode}",
                )

            result.duration_seconds = time.monotonic() - start_time
            logger.info(
                f"[Hypermodule] Mode {mode.value} completed: "
                f"success={result.success}, duration={result.duration_seconds:.1f}s"
            )
            return result

        except Exception as e:
            logger.error(f"[Hypermodule] Mode {mode.value} failed: {e}")
            return HealingResult(
                mode=mode,
                success=False,
                message=f"Hypermodule error in {mode.value}: {e}",
                duration_seconds=time.monotonic() - start_time,
            )

    # ─── Mode: HEAL ───────────────────────────────────────────────────────────

    async def heal(
        self,
        error: str,
        step_context: dict[str, Any],
        step_id: str = "",
        step_result: Any = None,
        depth: int = 0,
    ) -> HealingResult:
        """HEAL mode — reactive error fixing.

        Delegates to existing HealingOrchestrator and ParallelHealingManager,
        adding server restart and state resumption capabilities.

        Args:
            error: The error message to heal.
            step_context: Context of the failing step.
            step_id: ID of the failing step.
            step_result: Previous result from the failed step, if any.
            depth: Recursion depth for nested healing.

        Returns:
            HealingResult.
        """
        logger.info(f"[Hypermodule:HEAL] Healing error in step '{step_id}': {error[:120]}")

        # Save state before healing attempt
        await self.server_manager.save_task_state(
            {
                "mode": "heal",
                "step_id": step_id,
                "error": error,
                "depth": depth,
            }
        )

        try:
            # Try parallel healing first (non-blocking)
            from src.brain.healing.parallel_healing import parallel_healing_manager

            try:
                recent_logs = await self._get_recent_logs(50)
                task_id = await parallel_healing_manager.submit_healing_task(
                    step_id=step_id,
                    error=error,
                    step_context=step_context,
                    log_context=recent_logs,
                )
                logger.info(f"[Hypermodule:HEAL] Parallel healing task submitted: {task_id}")
                return HealingResult(
                    mode=HealingMode.HEAL,
                    success=True,
                    message=f"Healing task {task_id} submitted (parallel)",
                    details={"task_id": task_id, "method": "parallel"},
                )
            except RuntimeError as e:
                logger.warning(
                    f"[Hypermodule:HEAL] Parallel healing unavailable: {e}, trying blocking"
                )
            except Exception as e:
                logger.warning(f"[Hypermodule:HEAL] Parallel healing failed: {e}, trying blocking")

            # Fallback to blocking healing via HealingOrchestrator
            try:
                from src.brain.healing.system_healing import HealingOrchestrator

                orchestrator = HealingOrchestrator()
                recent_logs = await self._get_recent_logs(30)
                result_task = await orchestrator.handle_error(
                    step_id=step_id,
                    error=error,
                    context=step_context,
                    log_context=recent_logs,
                )
                success = result_task is not None and getattr(result_task, "status", "") != "failed"
                return HealingResult(
                    mode=HealingMode.HEAL,
                    success=success,
                    message=f"Blocking heal {'succeeded' if success else 'failed'}",
                    details={"method": "blocking"},
                )
            except ImportError:
                logger.debug("[Hypermodule:HEAL] HealingOrchestrator not available")
            except Exception as e:
                logger.warning(f"[Hypermodule:HEAL] Blocking healing failed: {e}")

            return HealingResult(
                mode=HealingMode.HEAL,
                success=False,
                message="All healing methods exhausted",
            )

        finally:
            # Clear snapshot on completion (success or failure)
            self.server_manager.clear_snapshot()

    # ─── Mode: DIAGNOSE ───────────────────────────────────────────────────────

    async def diagnose(self, targets: list[str] | None = None) -> HealingResult:
        """DIAGNOSE mode — run comprehensive system diagnostics.

        Calls SystemFixer, health_checks, MCP health, and diagnostics in sequence.
        Returns a unified DiagnosticReport.

        Args:
            targets: Optional list of specific targets to diagnose.
                     None = run all checks.
        """
        logger.info(f"[Hypermodule:DIAGNOSE] Running diagnostics: {targets or 'all'}")
        report = DiagnosticReport()
        auto_fixed = 0

        # 1. SystemFixer checks (run_all returns None, exceptions = issues)
        try:
            from src.maintenance.system_fixer import SystemFixer

            fixer = SystemFixer()
            fixer.run_all()
            report.checks["system_fixer"] = {
                "status": "ok",
                "message": "All system fixers executed",
            }
        except ImportError:
            report.checks["system_fixer"] = {"status": "skipped", "reason": "not available"}
        except Exception as e:
            report.checks["system_fixer"] = {"status": "error", "error": str(e)}
            report.issues_found += 1

        # 2. Health checks (individual functions returning status dicts)
        try:
            from src.maintenance.health_checks import (
                check_database,
                check_mcp_servers,
                check_memory_usage,
                check_python_deps,
                check_recent_errors,
                check_vibe_server,
                check_yaml_syntax,
            )

            check_funcs = {
                "yaml": check_yaml_syntax,
                "mcp_config": check_mcp_servers,
                "database": check_database,
                "python_deps": check_python_deps,
                "vibe_server": check_vibe_server,
                "memory": check_memory_usage,
                "recent_errors": check_recent_errors,
            }

            health_results: dict[str, Any] = {}
            failed = 0
            for name, func in check_funcs.items():
                try:
                    result = func()
                    health_results[name] = result
                    if isinstance(result, dict) and result.get("status") in ("error", "warning"):
                        failed += 1
                except Exception as e:
                    health_results[name] = {"status": "error", "message": str(e)}
                    failed += 1

            report.checks["health_checks"] = {
                "status": "ok" if failed == 0 else "degraded",
                "results": health_results,
                "failed": failed,
            }
            report.issues_found += failed
        except ImportError:
            report.checks["health_checks"] = {"status": "skipped", "reason": "not available"}
        except Exception as e:
            report.checks["health_checks"] = {"status": "error", "error": str(e)}
            report.issues_found += 1

        # 3. MCP health
        try:
            from src.maintenance.mcp_health import check_mcp

            await check_mcp(output_json=False)
            report.checks["mcp_health"] = {
                "status": "ok",
                "message": "MCP health check executed",
            }
        except ImportError:
            report.checks["mcp_health"] = {"status": "skipped", "reason": "not available"}
        except Exception as e:
            report.checks["mcp_health"] = {"status": "error", "error": str(e)}

        # 4. CI/CD status
        try:
            ci_results = await self.ci_bridge.check_workflow_status()
            failed_workflows = [r for r in ci_results if r.conclusion == "failure"]
            report.checks["ci_cd"] = {
                "status": "ok" if not failed_workflows else "degraded",
                "workflows_checked": len(ci_results),
                "failed": len(failed_workflows),
                "failed_names": [r.name for r in failed_workflows],
            }
            report.issues_found += len(failed_workflows)
        except Exception as e:
            report.checks["ci_cd"] = {"status": "error", "error": str(e)}

        # 5. Log analyzer stats
        report.checks["log_analyzer"] = self.log_analyzer.get_stats()

        # Determine overall status
        report.auto_fixed = auto_fixed
        if report.issues_found == 0:
            report.overall_status = "healthy"
        elif report.issues_found <= 3:
            report.overall_status = "degraded"
        else:
            report.overall_status = "critical"

        # Build recommendations
        if report.overall_status != "healthy":
            report.recommendations = self._build_recommendations(report)

        logger.info(
            f"[Hypermodule:DIAGNOSE] Complete: {report.overall_status}, "
            f"{report.issues_found} issues, {auto_fixed} auto-fixed"
        )

        return HealingResult(
            mode=HealingMode.DIAGNOSE,
            success=True,
            message=f"Diagnostics: {report.overall_status} ({report.issues_found} issues)",
            details=report.to_dict(),
        )

    # ─── Mode: PREVENT ────────────────────────────────────────────────────────

    async def prevent(self) -> HealingResult:
        """PREVENT mode — proactive maintenance.

        Performs scheduled maintenance tasks:
        - Log rotation and cleanup
        - Config sync verification
        - Cache cleanup
        - CI/CD failure analysis
        - Dependency freshness check
        """
        logger.info("[Hypermodule:PREVENT] Starting preventive maintenance")
        actions: list[str] = []
        issues: list[str] = []

        # 1. Log rotation
        try:
            from src.maintenance.system_fixer import SystemFixer

            fixer = SystemFixer()
            fixer.fix_log_rotation()
            actions.append("Log rotation checked")
        except Exception as e:
            issues.append(f"Log rotation failed: {e}")

        # 2. Config sync verification
        try:
            from src.maintenance.watch_config import (
                CONFIG_DST_ROOT,
                CONFIG_SRC,
                MAPPINGS,
                process_template,
            )

            synced = 0
            for tpl, dst in MAPPINGS.items():
                src = CONFIG_SRC / tpl
                if src.exists():
                    process_template(src, CONFIG_DST_ROOT / dst)
                    synced += 1
            if synced:
                actions.append(f"Config sync verified ({synced} templates)")
        except Exception as e:
            issues.append(f"Config sync failed: {e}")

        # 3. CI/CD failure analysis
        try:
            ci_results = await self.ci_bridge.check_workflow_status()
            ci_notes = await self.ci_bridge.analyze_failures(ci_results)
            if ci_notes:
                actions.append(f"CI/CD analysis: {len(ci_notes)} failures noted")
                # Feed back into log_analyzer for improvement cycle
                for note in ci_notes:
                    self.log_analyzer._upsert_note(
                        category=note.category,
                        description=note.description,
                        source_file=None,
                        source_line=None,
                    )
        except Exception as e:
            issues.append(f"CI/CD analysis failed: {e}")

        # 4. Memory/cache cleanup
        try:
            from src.maintenance.system_fixer import SystemFixer

            fixer = SystemFixer()
            fixer.fix_memory_usage()
            actions.append("Memory check completed")
        except Exception as e:
            issues.append(f"Memory cleanup failed: {e}")

        # 5. Stale improvement notes cleanup
        try:
            notes = self.log_analyzer.get_all_notes()
            from datetime import datetime, timedelta

            stale_cutoff = datetime.now() - timedelta(days=30)
            stale = [n for n in notes if n.addressed and n.last_seen < stale_cutoff]
            if stale:
                # Remove stale notes (they're addressed and old)
                with self.log_analyzer._lock:
                    self.log_analyzer._notes = [
                        n for n in self.log_analyzer._notes if n not in stale
                    ]
                self.log_analyzer._save_notes()
                actions.append(f"Cleaned {len(stale)} stale notes")
        except Exception as e:
            issues.append(f"Note cleanup failed: {e}")

        message = f"Prevention complete: {len(actions)} actions"
        if issues:
            message += f", {len(issues)} issues"

        return HealingResult(
            mode=HealingMode.PREVENT,
            success=len(issues) == 0,
            message=message,
            details={"actions": actions, "issues": issues},
        )

    # ─── Mode: IMPROVE ────────────────────────────────────────────────────────

    async def improve(
        self,
        focus_areas: list[str] | None = None,
        max_improvements: int | None = None,
    ) -> HealingResult:
        """IMPROVE mode — proactive code improvements.

        Reads improvement notes from LogAnalyzer, finds code hotspots,
        applies fixes via Vibe, and auto-commits with [Self-Healing] tags.

        Args:
            focus_areas: Optional list of categories to focus on.
            max_improvements: Maximum improvements to apply per cycle.
        """
        logger.info(
            f"[Hypermodule:IMPROVE] Starting improvement cycle, focus: {focus_areas or 'all'}"
        )

        # Get pending notes
        notes = self.log_analyzer.get_pending_notes()

        # Filter by focus areas if specified
        if focus_areas:
            notes = [n for n in notes if n.category in focus_areas]

        if not notes:
            return HealingResult(
                mode=HealingMode.IMPROVE,
                success=True,
                message="No improvement notes pending",
            )

        # Run improvement cycle
        results = await self.improvement_engine.run_improvement_cycle(
            notes=notes,
            max_improvements=max_improvements,
        )

        # Mark addressed notes
        for result in results:
            if result.success and result.details.get("hotspot"):
                hotspot = result.details["hotspot"]
                for note_id in hotspot.get("related_notes", []):
                    self.log_analyzer.mark_addressed(note_id, result.message)

        successes = sum(1 for r in results if r.success)
        committed = sum(1 for r in results if r.committed)

        return HealingResult(
            mode=HealingMode.IMPROVE,
            success=True,
            message=f"Improvement cycle: {successes}/{len(results)} succeeded, {committed} committed",
            details={
                "results": [r.to_dict() for r in results],
                "notes_processed": len(notes),
            },
        )

    # ─── Server Management ────────────────────────────────────────────────────

    async def restart_server(self, server_name: str, preserve_state: bool = True) -> bool:
        """Restart an MCP server with optional state preservation.

        Args:
            server_name: Name of the MCP server.
            preserve_state: Whether to save/restore task state.

        Returns:
            True if the restart succeeded.
        """
        if preserve_state:
            await self.server_manager.save_task_state()

        success = await self.server_manager.restart_server(
            server_name, reason="Hypermodule-initiated restart"
        )

        if success and preserve_state:
            state = await self.server_manager.restore_task_state()
            if state:
                logger.info(f"[Hypermodule] State restored after {server_name} restart")
            self.server_manager.clear_snapshot()

        return success

    # ─── Utilities ────────────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Get overall hypermodule status."""
        return {
            "initialized": self._initialized,
            "running": self._running,
            "log_analyzer": self.log_analyzer.get_stats(),
            "pending_snapshot": self.server_manager.has_pending_snapshot(),
        }

    async def _get_recent_logs(self, n: int = 50) -> str:
        """Get recent log lines for context."""
        try:
            from pathlib import Path

            log_file = Path.home() / ".config" / "atlastrinity" / "logs" / "brain.log"
            if log_file.exists():
                with open(log_file, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                return "\n".join(lines[-n:])
        except Exception:
            pass
        return ""

    def _build_recommendations(self, report: DiagnosticReport) -> list[str]:
        """Build actionable recommendations from diagnostic report."""
        recs: list[str] = []
        checks = report.checks

        if checks.get("system_fixer", {}).get("status") == "error":
            recs.append("Run system_fixer manually: python -m src.maintenance.system_fixer")

        mcp = checks.get("mcp_health", {})
        if mcp.get("unhealthy", 0) > 0:
            recs.append(f"Restart unhealthy MCP servers ({mcp.get('unhealthy')} down)")

        ci = checks.get("ci_cd", {})
        if ci.get("failed", 0) > 0:
            names = ", ".join(ci.get("failed_names", []))
            recs.append(f"Investigate CI failures: {names}")

        analyzer = checks.get("log_analyzer", {})
        pending = analyzer.get("pending", 0)
        if pending > 10:
            recs.append(f"Run IMPROVE mode: {pending} improvement notes pending")

        return recs


# Singleton
healing_hypermodule = SelfHealingHypermodule()
