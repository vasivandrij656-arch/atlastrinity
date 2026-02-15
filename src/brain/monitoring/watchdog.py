import asyncio
import time
from datetime import datetime
from typing import Any

import psutil  # pyre-ignore

from src.brain.monitoring import get_monitoring_system  # pyre-ignore
from src.brain.monitoring.logger import logger  # pyre-ignore


class ProcessWatchdog:
    """
    AtlasTrinity Process Watchdog.
    Monitors child processes (Vibe, MCP servers) and provides auto-healing capabilities.
    """

    def __init__(self, check_interval: int = 15):
        self.check_interval = check_interval
        self.mon = get_monitoring_system()
        self.processes: dict[int, dict[str, Any]] = {}  # pid -> info
        self._running = False
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self):
        """Start the watchdog background loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("[WATCHDOG] Process monitoring started.")
        self.mon.log_for_grafana("Watchdog started", level="info")

    async def stop(self):
        """Stop the watchdog."""
        self._running = False
        if self._task:
            self._task.cancel()  # pyre-ignore
            try:
                await self._task  # pyre-ignore
            except asyncio.CancelledError:
                pass
        logger.info("[WATCHDOG] Process monitoring stopped.")

    async def _monitor_loop(self):
        # Initial wait to let system start up
        await asyncio.sleep(5)
        while self._running:
            try:
                await self.reconcile_processes()
                await self.check_health()
            except Exception as e:
                logger.error(f"[WATCHDOG] Loop error: {e}")
            await asyncio.sleep(self.check_interval)

    async def reconcile_processes(self):
        """Find all child processes and update tracking."""
        try:
            current_proc = psutil.Process()
            # Get all child processes recursively
            children = current_proc.children(recursive=True)

            async with self._lock:
                active_pids = set()
                for child in children:
                    try:
                        pid = child.pid
                        active_pids.add(pid)

                        if pid not in self.processes:
                            # New process detected
                            try:
                                cmdline = child.cmdline()
                                proc_name = child.name()
                                proc_type = self._classify_process(child)

                                self.processes[pid] = {
                                    "pid": pid,
                                    "name": proc_name,
                                    "cmdline": " ".join(cmdline),
                                    "started": datetime.fromtimestamp(
                                        child.create_time()
                                    ).isoformat(),
                                    "type": proc_type,
                                    "last_seen": time.time(),
                                    "stuck_count": 0,
                                    "cpu_history": [],
                                    "status": child.status(),
                                }
                                if proc_type in ["unknown", "mcp_external"]:
                                    logger.debug(
                                        f"[WATCHDOG] New process tracked: {proc_type} (PID: {pid}, Name: {proc_name})"
                                    )
                                else:
                                    logger.info(
                                        f"[WATCHDOG] New process tracked: {proc_type} (PID: {pid}, Name: {proc_name})"
                                    )
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                continue
                        else:
                            # Update existing info
                            self.processes[pid]["last_seen"] = time.time()
                            self.processes[pid]["status"] = child.status()

                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                # Remove stale processes
                stale_pids = set(self.processes.keys()) - active_pids
                for pid in stale_pids:
                    info = self.processes[pid]
                    logger.debug(f"[WATCHDOG] Process {pid} ({info.get('type')}) exited.")
                    del self.processes[pid]  # pyre-ignore

        except Exception as e:
            logger.error(f"[WATCHDOG] Reconcile failed: {e}")

    def _classify_process(self, proc: psutil.Process) -> str:
        try:
            cmd = " ".join(proc.cmdline()).lower()
            if "vibe_server" in cmd:
                return "mcp_vibe"
            if "src.mcp_server" in cmd:
                return "mcp_server"
            if "devtools_server" in cmd:
                return "mcp_devtools"
            if "vibe" in cmd and "-p" in cmd:
                return "vibe_cli"
            if "copilot_proxy" in cmd:
                return "proxy"
            if "npx" in cmd or "node" in cmd:
                return "mcp_external"
            if "python" in cmd:
                return "python_sub"
            return "unknown"
        except Exception:
            return "unknown"

    async def check_health(self):
        """Check the health of tracked processes."""
        async with self._lock:
            for pid, info in list(self.processes.items()):
                try:
                    proc = psutil.Process(pid)

                    # 1. CPU Usage Tracking
                    cpu_percent = proc.cpu_percent(interval=None)
                    info["cpu_history"].append(cpu_percent)
                    if len(info["cpu_history"]) > 20:
                        info["cpu_history"].pop(0)

                    # 2. Logic to detect "HUNG" state
                    # For Vibe CLI: 0% CPU for > 5 min while running is suspect
                    if info["type"] == "vibe_cli":
                        uptime = time.time() - proc.create_time()
                        # If running > 2 min AND cpu is 0 for last 5 checks
                        if uptime > 120 and all(c < 0.1 for c in info["cpu_history"][-5:]):
                            info["stuck_count"] += 1
                        else:
                            info["stuck_count"] = 0

                        # If stuck for ~3 minutes (check_interval * 12)
                        if info["stuck_count"] >= 12:
                            logger.warning(
                                f"[WATCHDOG] Process {pid} ({info['type']}) seems STUCK (0% CPU for long time)."
                            )
                            await self.handle_stuck_process(pid)

                    # 3. Memory Leak detection
                    mem_info = proc.memory_info()
                    info["memory_mb"] = mem_info.rss / (1024 * 1024)

                    if info["memory_mb"] > 2048:  # > 2GB
                        logger.warning(
                            f"[WATCHDOG] Process {pid} ({info['type']}) high memory: {info['memory_mb']:.1f} MB"
                        )
                        self.mon.log_for_grafana(
                            f"High memory process detected: {pid}",
                            level="warning",
                            memory=info["memory_mb"],
                        )

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

    async def handle_stuck_process(self, pid: int):
        info = self.processes.get(pid)
        if not info:
            return

        logger.error(
            f"[WATCHDOG] 🚨 PROCESS STUCK: {pid} ({info['type']}). Requesting Healing Orchestrator..."
        )

        # New: Delegate to HealingOrchestrator
        try:
            from src.brain.healing.system_healing import healing_orchestrator  # pyre-ignore

            # Construct context for analysis
            context = {
                "process_info": info,
                "pid": pid,
                "stuck_count": info.get("stuck_count", 0),
                "step_id": f"watchdog_kill_{pid}",
            }

            # Call orchestrator (it will analyze -> decide -> act)
            # We treat this as a "STEP" failure where the step is keeping the process alive
            await healing_orchestrator.handle_error(
                step_id=f"watchdog_process_{pid}",
                error=f"Process {pid} ({info['name']}) is stuck (0% CPU for extended period).",
                context=context,
                log_context=f"Process Info: {info}",
            )

        except Exception as e:
            logger.error(f"[WATCHDOG] Failed to call Healing Orchestrator: {e}")
            # Fallback to old behavior if orchestrator fails
            await self.terminate_process(pid, hard=True)

    async def terminate_process(self, pid: int, hard: bool = False) -> bool:
        """Kill a process either gracefully or hard."""
        try:
            proc = psutil.Process(pid)
            if hard:
                logger.info(f"[WATCHDOG] Hard killing PID {pid}")
                proc.kill()
            else:
                logger.info(f"[WATCHDOG] Terminating PID {pid} (graceful)")
                proc.terminate()
                # Wait a bit for graceful exit
                _, alive = psutil.wait_procs([proc], timeout=3)
                if alive:
                    logger.warning(f"[WATCHDOG] PID {pid} didn't exit gracefully, killing.")
                    proc.kill()
            return True
        except psutil.NoSuchProcess:
            return True
        except Exception as e:
            logger.error(f"[WATCHDOG] Error killing PID {pid}: {e}")
            return False

    def _extract_server_name(self, info: dict) -> str | None:
        """Try to guess server name from cmdline."""
        cmd = info["cmdline"]
        if "src.mcp_server." in cmd:
            import re

            m = re.search(r"src\.mcp_server\.([a-zA-Z0-9_]+)", cmd)
            if m:
                return m.group(1).replace("_server", "")

        # Check against mcp catalog if needed
        return None

    def get_status(self) -> dict[str, Any]:
        """Return full status of tracked processes."""
        return {
            "timestamp": datetime.now().isoformat(),
            "process_count": len(self.processes),
            "processes": list(self.processes.values()),
        }


# Singleton
watchdog = ProcessWatchdog()
