"""Server Manager for Self-Healing System.

Manages MCP server lifecycle with state preservation for seamless task resumption.
Handles server restart, graceful shutdown, and state snapshot/restore.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("brain.healing.server_manager")

STATE_DIR = Path.home() / ".config" / "atlastrinity" / "memory"


class ServerManager:
    """Manages MCP server restarts with state preservation.

    When a server needs to restart (crash recovery, config reload, etc.),
    this manager:
    1. Snapshots the current task state
    2. Performs the restart
    3. Restores state for seamless resumption
    """

    def __init__(self, state_dir: Path | None = None):
        self.state_dir = state_dir or STATE_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._snapshot_path = self.state_dir / "healing_state_snapshot.json"

    async def restart_server(self, server_name: str, reason: str = "") -> bool:
        """Restart an MCP server, preserving state for task resumption.

        Args:
            server_name: Name of the MCP server to restart (e.g., "vibe", "devtools").
            reason: Human-readable reason for the restart.

        Returns:
            True if the server was restarted successfully.
        """
        logger.info(f"[ServerManager] Restarting server '{server_name}': {reason}")

        try:
            # Import here to avoid circular dependency
            from src.brain.mcp.mcp_manager import mcp_manager

            # Phase 1 & 2: Restart via MCP manager
            success = await mcp_manager.restart_server(server_name)
            if not success:
                logger.warning(f"[ServerManager] MCP manager could not restart {server_name}")
                return False

            logger.info(f"[ServerManager] Server '{server_name}' restarted successfully")
            return True

        except Exception as e:
            logger.error(f"[ServerManager] Failed to restart {server_name}: {e}")
            return False

    async def save_task_state(self, state: dict[str, Any] | None = None) -> bool:
        """Snapshot current task state for resumption.

        Args:
            state: Optional explicit state dict. If None, auto-captures from orchestrator.

        Returns:
            True if the state was saved successfully.
        """
        try:
            if state is None:
                state = await self._capture_current_state()

            snapshot = {
                "timestamp": datetime.now().isoformat(),
                "state": state,
                "version": 1,
            }

            self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._snapshot_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, ensure_ascii=False, default=str)

            logger.info(f"[ServerManager] Task state saved: {len(state)} keys")
            return True

        except Exception as e:
            logger.error(f"[ServerManager] Failed to save task state: {e}")
            return False

    async def restore_task_state(self) -> dict[str, Any] | None:
        """Load saved task state for resumption.

        Returns:
            Restored state dict, or None if no snapshot exists.
        """
        try:
            if not self._snapshot_path.exists():
                logger.debug("[ServerManager] No state snapshot found")
                return None

            with open(self._snapshot_path, encoding="utf-8") as f:
                snapshot = json.load(f)

            state = snapshot.get("state", {})
            timestamp = snapshot.get("timestamp", "unknown")
            logger.info(f"[ServerManager] Task state restored from {timestamp}: {len(state)} keys")
            return state

        except Exception as e:
            logger.error(f"[ServerManager] Failed to restore task state: {e}")
            return None

    def clear_snapshot(self) -> None:
        """Clear saved snapshot after successful resumption."""
        try:
            if self._snapshot_path.exists():
                self._snapshot_path.unlink()
                logger.debug("[ServerManager] State snapshot cleared")
        except Exception as e:
            logger.warning(f"[ServerManager] Failed to clear snapshot: {e}")

    def has_pending_snapshot(self) -> bool:
        """Check if there's a pending state snapshot to resume from."""
        return self._snapshot_path.exists()

    # --- Private helpers ---

    async def _capture_current_state(self) -> dict[str, Any]:
        """Auto-capture state from the orchestrator context."""
        state: dict[str, Any] = {}

        try:
            from src.brain.core.services.state_manager import state_manager

            if state_manager.available:
                state["session_id"] = getattr(state_manager, "session_id", None)
                state["current_step"] = getattr(state_manager, "current_step", None)
                history = getattr(state_manager, "interaction_history", [])
                state["interaction_count"] = len(history) if history else 0
        except ImportError:
            logger.debug("[ServerManager] state_manager not available for capture")

        try:
            from src.brain.healing.parallel_healing import parallel_healing_manager

            active_tasks = {
                tid: {
                    "step_id": t.step_id,
                    "status": t.status.value if hasattr(t.status, "value") else str(t.status),
                    "error": t.error,
                }
                for tid, t in parallel_healing_manager._tasks.items()
            }
            state["healing_tasks"] = active_tasks
        except ImportError:
            pass

        return state


# Singleton
server_manager = ServerManager()
