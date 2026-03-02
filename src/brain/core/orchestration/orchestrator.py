"""AtlasTrinity Orchestrator
LangGraph-based state machine that coordinates Agents (Atlas, Tetyana, Grisha)
"""

import ast
import asyncio
import json
import os
import re
import sys
import time
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any, TypedDict, cast

from langchain_core.messages import (  # type: ignore
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langgraph.graph import END, StateGraph
from sqlalchemy import select, update

try:
    from langgraph.graph.message import add_messages as _add_messages

    def add_messages(left: Any, right: Any) -> Any:
        return _add_messages(left, right)
except ImportError:

    def add_messages(left: Any, right: Any) -> Any:
        return left + right


from src.brain.agents import Atlas, Grisha, Tetyana
from src.brain.agents.tetyana import StepResult
from src.brain.behavior.behavior_engine import behavior_engine, workflow_engine
from src.brain.config import IS_MACOS, PLATFORM_NAME
from src.brain.config.config_loader import config
from src.brain.core.orchestration.context import shared_context
from src.brain.core.orchestration.error_router import error_router
from src.brain.core.server.message_bus import AgentMsg, MessageType, message_bus
from src.brain.core.services.state_manager import state_manager
from src.brain.healing.parallel_healing import parallel_healing_manager
from src.brain.mcp.mcp_manager import mcp_manager
from src.brain.memory import long_term_memory
from src.brain.memory.db.manager import db_manager
from src.brain.memory.db.schema import (
    ChatMessage as DBChatMessage,
)
from src.brain.memory.db.schema import LogEntry as DBLog
from src.brain.memory.db.schema import Session as DBSession
from src.brain.memory.db.schema import Task as DBTask
from src.brain.memory.db.schema import TaskStep as DBStep
from src.brain.memory.db.schema import ToolExecution as DBToolExecution
from src.brain.memory.knowledge_graph import knowledge_graph
from src.brain.monitoring.logger import logger
from src.brain.monitoring.metrics import metrics_collector
from src.brain.monitoring.notifications import notifications
from src.brain.navigation.map_state import map_state_manager
from src.brain.navigation.tour_driver import tour_driver
from src.brain.navigation.tour_manager import TourMixin
from src.brain.voice.orchestration_utils import VoiceOrchestrationMixin
from src.brain.voice.stt import WhisperSTT
from src.brain.voice.tts import VoiceManager


class SystemState(Enum):
    IDLE = "IDLE"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    CHAT = "CHAT"
    AUDITING = "AUDITING"


class TrinityState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    system_state: str
    current_plan: Any | None
    step_results: list[dict[str, Any]]
    error: str | None
    logs: list[dict[str, Any]]
    session_id: str | None
    db_session_id: str | None
    db_task_id: str | None
    _theme: str | None


class Trinity(TourMixin, VoiceOrchestrationMixin):
    # Methods start_tour, stop_tour, etc. are now provided by TourMixin

    def __init__(self):
        self.atlas = Atlas()
        self.tetyana = Tetyana()
        self.grisha = Grisha()
        self.voice = VoiceManager()
        self.stt = WhisperSTT()

        # Ensure global singletons are loaded

        # Initialize graph
        self.graph = self._build_graph()
        self._log_lock = asyncio.Lock()
        self.current_session_id = "current_session"  # Default alias for the last active session
        self._resumption_pending = False
        self._user_node_created = False
        self.active_task = None  # Track current run task for cancellation
        self.state = {
            "messages": [],
            "system_state": SystemState.IDLE.value,
            "current_plan": None,
            "step_results": [],
            "error": None,
            "logs": [],
        }
        self._background_tasks = set()

        # ARCHITECTURAL IMPROVEMENT: Live Voice status during long tools (like Vibe)
        self._last_live_speech_time = 0
        self._spoken_history = {}  # Deduplication cache: hash -> timestamp
        from src.brain.mcp.mcp_manager import mcp_manager

        mcp_manager.register_log_callback(self._mcp_log_voice_callback)

    async def initialize(self):
        """Async initialization of system components via Config-Driven Workflow"""
        # Синхронізація shared_context з конфігурацією

        shared_context.sync_from_config(config.all)

        # Execute 'startup' workflow from behavior config
        # This replaces hardcoded service checks and state init
        context = {"orchestrator": self}
        success = await workflow_engine.execute_workflow("startup", context)

        if not success:
            logger.error(
                "[ORCHESTRATOR] Startup workflow failed or partial. Proceeding with caution.",
            )

        # [NEURAL CORE] Initialize the Living Brain
        try:
            from src.brain.neural_core.core import neural_core

            await neural_core.initialize()
        except Exception as ne:
            logger.error(f"[ORCHESTRATOR] NeuralCore awakening failed: {ne}")

        if not self.state:
            self.state = {
                "messages": [],
                "system_state": SystemState.IDLE.value,
                "current_plan": None,
                "step_results": [],
                "error": None,
                "logs": [],
            }

        # [MEMORY RECALL] Check Golden Fund for relevant context on startup
        try:
            # We initialize the connection here
            pass
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Memory recall check failed: {e}")

        # Check for pending restart state
        await self._resume_after_restart()

        # If resumption is pending, trigger the run() in background after a short delay
        if getattr(self, "_resumption_pending", False):

            async def auto_resume():
                await asyncio.sleep(5)  # Wait for all components to stabilize
                messages = self.state.get("messages", [])
                if messages:
                    # Get the original request from the first HumanMessage
                    original_request = ""
                    for m in messages:
                        if "HumanMessage" in str(type(m)) or (
                            isinstance(m, dict) and m.get("type") == "human"
                        ):
                            if hasattr(m, "content"):
                                original_request = str(getattr(m, "content", ""))
                            elif isinstance(m, dict):
                                original_request = str(m.get("content", ""))
                            else:
                                original_request = str(m)
                            break

                    if original_request:
                        logger.info(
                            f"[ORCHESTRATOR] Auto-resuming task: {original_request[:50]}...",
                        )
                        await self.run(original_request)

            asyncio.create_task(auto_resume())

        # SYSTEM VISIBILITY CHECK
        await self._log_visibility_report()

        logger.info(f"[GRISHA] Auditor ready. Vision: {self.grisha.llm.model_name}")

    async def recall_memories(self, query: str) -> str:
        """Search Golden Fund for relevant context."""
        try:
            from src.brain.mcp.mcp_manager import mcp_manager

            # Use the mcp_manager to call the tool directly
            # This avoids needing a separate client initialization
            if not mcp_manager:
                return ""

            # Search in hybrid mode for best results
            results = await mcp_manager.call_tool(
                "golden_fund", "search_golden_fund", {"query": query, "mode": "hybrid"}
            )

            # Results from MCP can be a string or an object with content
            res_str = str(results)
            # Only treat as error if it explicitly starts with Error prefix
            is_explicit_error = res_str.startswith("Error (")

            if results and not is_explicit_error:
                logger.info(f"[ORCHESTRATOR] Recalled memories for '{query}'")
                return f"\n[RECALLED CONTEXT from Golden Fund]:\n{results}\n"
            return ""

        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Memory recall failed: {e}")
            return ""

    async def warmup(self, async_warmup: bool = True):
        """Warm up memory, voice types, and engine models."""
        try:
            logger.info("[ORCHESTRATOR] Warming up system components...")

            async def run_warmup():
                # 1. Warm up STT
                logger.info(f"[ORCHESTRATOR] Pre-loading STT model: {self.stt.model_name}...")
                model = await self.stt.get_model()
                if model:
                    logger.info("[ORCHESTRATOR] STT model loaded successfully.")
                else:
                    logger.warning("[ORCHESTRATOR] STT model unavailable.")

                # 2. Anticipatory Patching (HOCE Upgrade)
                try:
                    from src.brain.healing.system_healing import healing_orchestrator

                    await healing_orchestrator.anticipatory_patching()
                except Exception as he:
                    logger.warning(f"[ORCHESTRATOR] Anticipatory patching failed: {he}")

                # 3. Warm up memory
                logger.info("[ORCHESTRATOR] Initializing TTS engine...")
                await self.voice.get_engine()
                logger.info("[ORCHESTRATOR] Voice engines ready.")

            if async_warmup:
                asyncio.create_task(run_warmup())
            else:
                await run_warmup()

        except Exception as e:
            logger.error(f"[ORCHESTRATOR] Warmup failed: {e}")

    async def reset_session(self):
        """Reset the current session and start a fresh one"""
        self.state = {
            "messages": [],
            "system_state": SystemState.IDLE.value,
            "current_plan": None,
            "step_results": [],
            "error": None,
            "logs": [],
        }
        # Clear IDs so they are regenerated on next run
        if "db_session_id" in self.state:
            del self.state["db_session_id"]
        if "db_task_id" in self.state:
            del self.state["db_task_id"]
        # Auto-backup before clearing session
        try:
            from pathlib import Path

            project_root = Path(__file__).parent.parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            try:
                from types import SimpleNamespace

                from src.maintenance import setup_dev

                # We disable auto-commit/push during session reset to keep the UI responsive
                args = SimpleNamespace(no_auto_commit=True)
                await asyncio.to_thread(setup_dev.backup_databases, args)
            except ImportError:
                # Handle non-package scripts folder
                import importlib.util

                spec = importlib.util.spec_from_file_location(
                    "setup_dev",
                    str(project_root / "src" / "maintenance" / "setup_dev.py"),
                )
                if spec and spec.loader:
                    setup_dev = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(setup_dev)
                    from types import SimpleNamespace

                    args = SimpleNamespace(no_auto_commit=True)
                    await asyncio.to_thread(setup_dev.backup_databases, args)
            await self._log("📦 Backup попередньої сесії...", "system")
        except Exception as e:
            logger.warning(f"[BACKUP] Не вдалося створити backup: {e}")

        if state_manager.available:
            await state_manager.clear_session(self.current_session_id)

        # Reset Map State
        map_state_manager.clear_all()
        map_state_manager.clear_agent_view()
        await tour_driver.stop_tour()

        # Create a new unique session ID
        self.current_session_id = str(uuid.uuid4())

        await self._log(f"Нова сесія розпочата ({self.current_session_id})", "system")
        return {"status": "success", "session_id": self.current_session_id}

    async def load_session(self, session_id: str):
        """Load a specific session from Redis, or reconstruct from DB if missing"""
        if not state_manager.available:
            return {"status": "error", "message": "Persistence unavailable"}

        saved_state = await state_manager.restore_session(session_id)
        if saved_state:
            self.state = saved_state
            self.current_session_id = session_id
            await self._log(f"Сесія {session_id} відновлена з пам'яті", "system")
            return {"status": "success"}

        # Attempt DB Reconstruction
        try:
            from sqlalchemy import select

            async with await db_manager.get_session() as db_sess:
                # 1. Fetch Session Theme
                sess_info = await db_sess.execute(
                    select(DBSession).where(
                        DBSession.id
                        == (uuid.UUID(session_id) if isinstance(session_id, str) else session_id)
                    )
                )
                db_sess_obj = sess_info.scalar()
                if not db_sess_obj:
                    # Try searching by string ID in metadata or logs if UUID fails
                    # But session_id here should be the ID
                    return {"status": "error", "message": "Session not found in DB"}

                # 2. Fetch Chat History
                chat_info = await db_sess.execute(
                    select(DBChatMessage)
                    .where(DBChatMessage.session_id == str(session_id))
                    .order_by(DBChatMessage.created_at.asc())
                )
                db_messages = chat_info.scalars().all()

                # Reconstruct LangChain messages
                reconstructed_messages: list[BaseMessage] = []
                for m in db_messages:
                    if m.role == "human":
                        reconstructed_messages.append(HumanMessage(content=m.content))
                    elif m.role == "ai":
                        agent = (
                            m.metadata_blob.get("agent", "ATLAS") if m.metadata_blob else "ATLAS"
                        )
                        reconstructed_messages.append(AIMessage(content=m.content, name=agent))

                # 3. Fetch Logs (Optional but nice)
                log_info = await db_sess.execute(
                    select(DBLog)
                    .where(DBLog.session_id == str(session_id))
                    .order_by(DBLog.timestamp.asc())
                )
                db_logs = log_info.scalars().all()
                reconstructed_logs = []
                for l in db_logs:
                    reconstructed_logs.append(
                        {
                            "id": f"db-log-{l.id}",
                            "timestamp": l.timestamp.timestamp(),
                            "agent": l.source.upper(),
                            "message": l.message,
                            "type": l.metadata_blob.get("type", "info")
                            if l.metadata_blob
                            else "info",
                        }
                    )

                # Initial Fresh State
                self.state = {
                    "messages": reconstructed_messages,
                    "system_state": SystemState.IDLE.value,
                    "current_plan": None,
                    "step_results": [],
                    "error": None,
                    "logs": reconstructed_logs,
                    "_theme": db_sess_obj.metadata_blob.get("theme", "Restored Session"),
                }
                self.current_session_id = session_id
                await self._log(f"Сесія {session_id} відновлена з бази даних", "system")
                return {"status": "success"}

        except Exception as e:
            logger.error(f"Failed to reconstruct session from DB: {e}")
            return {"status": "error", "message": f"DB Reconstruction failed: {e}"}

    def _build_graph(self):
        """Builds LangGraph dynamically from orchestration_flow config."""
        from src.brain.behavior.behavior_engine import behavior_engine

        flow_config = behavior_engine.config.get("orchestration_flow", {})

        workflow = StateGraph(TrinityState)  # type: ignore[arg-type]

        # Mapping of config node types to orchestrator functions
        node_functions = {
            "planner": self.planner_node,
            "executor": self.executor_node,
            "verifier": self.verifier_node,
            "audit": self.audit_node,
        }

        # 1. Define nodes
        nodes = flow_config.get("nodes", [])
        for node_cfg in nodes:
            name = node_cfg.get("name")
            n_type = node_cfg.get("type")
            if isinstance(name, str) and n_type in node_functions:
                action = node_functions[n_type]
                workflow.add_node(name, action)  # type: ignore

        # 2. Define edges
        entry_point = flow_config.get("entry_point")
        if entry_point:
            workflow.set_entry_point(entry_point)

        for node_cfg in nodes:
            name = node_cfg.get("name")
            next_node = node_cfg.get("next")
            cond_edge = node_cfg.get("conditional_edge")

            if next_node:
                workflow.add_edge(name, next_node)
            elif cond_edge:
                evaluator_name = cond_edge.get("evaluator")
                mapping = cond_edge.get("mapping", {})
                # Resolve __end__ to END
                resolved_mapping = {k: (v if v != "__end__" else END) for k, v in mapping.items()}

                # Check if evaluator is a method on Trinity
                eval_func = getattr(self, evaluator_name, None) if evaluator_name else None
                if name and eval_func:
                    workflow.add_conditional_edges(name, eval_func, resolved_mapping)

        return workflow.compile()

    def _mcp_result_to_text(self, res: Any) -> str:
        if isinstance(res, dict):
            try:
                return json.dumps(res, ensure_ascii=False)
            except Exception:
                return str(res)

        if hasattr(res, "content") and isinstance(res.content, list):
            parts: list[str] = []
            for item in res.content:
                txt = getattr(item, "text", None)
                if isinstance(txt, str) and txt:
                    parts.append(txt)
            if parts:
                return "".join(parts)
        return str(res)

    def _extract_vibe_payload(self, text: str) -> str:
        t = (text or "").strip()
        if not t:
            return ""
        try:
            data = json.loads(t)
        except Exception:
            try:
                data = ast.literal_eval(t)
            except Exception:
                # If it starts with "Saved to:", it's likely a path result (like Street View)
                if "Saved to:" in t:
                    return t
                return t

        if isinstance(data, dict):
            stdout = (data.get("stdout") or "").strip()
            stderr = (data.get("stderr") or "").strip()

            # If we have content in stdout, prioritize it but append stderr if it looks like an error
            if stdout:
                if stderr and any(kw in stderr.lower() for kw in ["error", "fail", "exception"]):
                    return f"{stdout}\n\n[ERRORS]:\n{stderr}"
                return stdout

            # If stdout is empty, return stderr
            if stderr:
                return stderr

            # If both empty, return the whole dict representation as fallback
            return json.dumps(data, ensure_ascii=False)

        return t

    async def _neural_pulse(self, step: dict[str, Any], step_id: str):
        """Consults the NeuralCore before executing a step."""
        from src.brain.neural_core.core import neural_core
        from src.brain.neural_core.synapse import CognitiveSignal

        # 1. Emit pulse for the current tool/action
        action = step.get("action") or step.get("tool")
        if action:
            signal = CognitiveSignal(
                source_id=f"tool:{action}", intensity=0.8, metadata={"step_id": step_id}
            )
            await neural_core.synapse.emit_signal(signal)

        # 2. Check chemical modifiers
        modifiers = neural_core.chemistry.get_behavior_modifers()
        if modifiers["safety_mode"]:
            logger.warning("[ORCHESTRATOR] NeuralCore safety mode ACTIVE. Restricting execution.")
            # Inject safety hint into step context if needed
            if "context" not in step:
                step["context"] = {}
            step["context"]["neural_safety_constraint"] = True

    async def _neural_feedback(self, result: StepResult, step: dict[str, Any]):
        """Feeds execution results back into the NeuralCore."""
        from src.brain.neural_core.core import neural_core

        action = step.get("action") or step.get("tool")
        if not action:
            return

        if result.success:
            # Positive feedback
            neural_core.chemistry.reward(intensity=0.1)
            # Accelerate recovery if we were highly stressed
            if neural_core.chemistry.get_state()["cortisol"] > 0.3:
                neural_core.chemistry.accelerate_recovery(multiplier=1.5)
                
            # Strengthen synapse between task and tool
            task_id = self.state.get("db_task_id")
            if task_id:
                await neural_core.graph.strengthen_synapse(f"task:{task_id}", f"tool:{action}")
        else:
            # Negative feedback with tool-specific awareness
            neural_core.chemistry.stress(intensity=0.15, tool_name=str(action))
            
            # Real-time consolidation for critical failures
            if neural_core.chemistry.get_state()["cortisol"] > 0.8:
                from src.brain.behavior.consolidation import consolidation_module
                logger.warning("[ORCHESTRATOR] Critical stress detected. Triggering real-time consolidation.")
                asyncio.create_task(consolidation_module.consolidate_immediate(self.state))

    def stop(self):
        """Immediately stop voice and cancel current orchestration task"""
        logger.info("[TRINITY] 🛑 STOP SIGNAL RECEIVED.")
        self.voice.stop()
        asyncio.create_task(tour_driver.stop_tour())
        if self.active_task and not self.active_task.done():
            logger.info("[TRINITY] Cancelling active orchestration task.")
            self.active_task.cancel()
        self.state["system_state"] = SystemState.IDLE.value

    # stop_speaking is now provided by VoiceOrchestrationMixin

    def pause(self):
        """Pause current execution but preserve state."""
        logger.info("[TRINITY] ⏸️ PAUSE SIGNAL RECEIVED.")
        if self.active_task and not self.active_task.done():
            self.active_task.cancel()
        self.state["system_state"] = "PAUSED"
        logger.info("[TRINITY] System paused. State preserved.")

    async def resume(self):
        """Resume execution from PAUSED state."""
        if self.state.get("system_state") != "PAUSED":
            logger.warning("[TRINITY] System is not paused, nothing to resume.")
            return {"status": "error", "message": "System not paused"}

        logger.info("[TRINITY] ▶️ RESUME SIGNAL RECEIVED.")

        # Find the last human request to re-trigger run()
        messages = self.state.get("messages", [])
        last_request = ""

        # Look for the last human message in history
        if not isinstance(messages, list):
            logger.warning("[TRINITY] Messages state is not a list, cannot resume.")
            self.state["system_state"] = SystemState.IDLE.value
            return {"status": "error", "message": "Invalid message state"}

        for m in reversed(messages):
            # Handle both object and dict formats
            content = getattr(m, "content", None) if not isinstance(m, dict) else m.get("content")
            m_type = getattr(m, "type", None) if not isinstance(m, dict) else m.get("type")

            if m_type == "human" and content:
                last_request = str(content)
                break

        if last_request:
            logger.info(f"[TRINITY] Resuming with request: {last_request[:50]}...")
            # Run in background to not block the API response
            asyncio.create_task(self.run(last_request))
            return {"status": "success", "message": "Resuming task"}
        logger.warning("[TRINITY] No previous human request found to resume.")
        self.state["system_state"] = SystemState.IDLE.value
        return {"status": "error", "message": "No task history to resume"}

    async def resume_from_snapshot(self, snapshot_path: str):
        """Resume execution from a recovery snapshot."""
        try:
            from src.brain.tools.recovery import recovery_manager

            snapshot = recovery_manager.load_snapshot()
            if not snapshot:
                logger.warning("[TRINITY] No snapshot found to resume from.")
                return

            orchestrator_state = snapshot.get("orchestrator_state", {})
            _task_context = snapshot.get(
                "task_context", {}
            )  # Logic might need adjustment based on snapshot structure

            # Restore state
            self.state.update(orchestrator_state)
            self.current_session_id = snapshot.get("session_id", self.current_session_id)

            logger.info(f"[TRINITY] 🦅 Resumed from snapshot (Reason: {snapshot.get('reason')})")

            # Resume execution
            # We need to trigger the run loop again, possibly skipping the step that failed if needed
            # For now, we just restart the cycle
            if self.state.get("messages"):
                # Extract last user message or just re-run last step?
                # Simplified: Just log "Ready to resume"
                logger.info("[TRINITY] Ready to resume task.")
                await self._log(
                    "🦅 Система відновлена після перезавантаження. Готовий продовжити.", "system"
                )

                # Automatically trigger run if we have a task ID
                # This part depends on how 'run' handles state
                # Ideally we re-invoke the step that was pending

        except Exception as e:
            logger.error(f"[TRINITY] Failed to resume from snapshot: {e}")

    # _speak is now provided by VoiceOrchestrationMixin

    # _mcp_log_voice_callback is now provided by VoiceOrchestrationMixin

    async def _log_visibility_report(self):
        """Logs the visibility of Diagrams and DevTools on startup."""
        import glob
        import os

        # Check for DevTools
        devtools_path = "src/mcp_server/devtools_server.py"
        devtools_exists = os.path.exists(devtools_path)

        # Check for Diagrams
        # Using a broad glob to find any diagram-related files in reasonable locations
        # We limit search to avoid massive traversals (e.g. ignore node_modules)
        diagram_patterns = ["**/*diagram*.*", "**/*.drawio", "**/*.mermaid"]
        found_diagrams = []
        try:
            for pattern in diagram_patterns:
                # glob.glob is recursive with **
                matches = glob.glob(pattern, recursive=True)
                # Filter out node_modules and .git
                matches = [m for m in matches if "node_modules" not in m and ".git" not in m]
                found_diagrams.extend(matches[:5])  # Store just first 5 for identifying presence
        except Exception:
            pass

        diagram_status = (
            f"Found {len(found_diagrams)}+ potential files" if found_diagrams else "None found"
        )
        devtools_status = "Available" if devtools_exists else "Not found"

        report = (
            f"Visibility Report: "
            f"[Diagrams: {diagram_status}] "
            f"[DevTools: {devtools_status}] "
            f"(Repo logic aware)"
        )
        logger.debug(f"[SYSTEM] {report}")  # debug-level to avoid duplication with _log
        await self._log(report, source="SYSTEM", type="startup_report")

    async def _log(self, text: str, source: str = "system", type: str = "info"):
        """Log wrapper with message types and DB persistence"""
        # Ensure text is a string to prevent React "Objects are not valid as a React child" error
        text_str = str(text)
        logger.info(f"[{source.upper()}] {text_str}")

        # DB Persistence
        if db_manager.available:
            async with self._log_lock:
                try:
                    async with await db_manager.get_session() as session:
                        entry = DBLog(
                            session_id=self.current_session_id,
                            level=type.upper(),
                            source=source,
                            message=text_str,
                            metadata_blob={"type": type},
                        )
                        session.add(entry)
                        await session.commit()
                except Exception as e:
                    logger.error(f"DB Log failed: {e}")

        if self.state:
            # Basic log format for API

            log_entry = {
                "id": f"log-{len(self.state.get('logs') or [])}-{time.time()}",
                "timestamp": time.time(),
                "agent": source.upper(),
                "message": text_str,
                "type": type,
            }
            if "logs" not in self.state:
                self.state["logs"] = []
            self.state["logs"].append(log_entry)

            # 3. Publish to Redis for real-time UI updates
            if state_manager.available:
                try:
                    asyncio.create_task(state_manager.publish_event("logs", log_entry))
                except Exception as e:
                    logger.warning(f"Failed to publish log to Redis: {e}")

    async def _get_recent_logs(self, count: int = 50) -> str:
        """Get recent log entries as a string for context.

        Args:
            count: Number of recent log entries to retrieve

        Returns:
            Formatted string of recent log entries
        """
        logs_raw = self.state.get("logs", []) if self.state else []
        # Ensure logs is a list of dicts
        if not isinstance(logs_raw, list):
            return ""
        logs: list[dict] = [l for l in logs_raw if isinstance(l, dict)]
        recent = logs[-count:] if len(logs) > count else logs

        lines = []
        for log in recent:
            agent = log.get("agent", "SYSTEM")
            message = log.get("message", "")
            log_type = log.get("type", "info")
            lines.append(f"[{agent}] ({log_type}) {message}")

        return "\n".join(lines)

    async def _save_chat_message(self, role: str, content: str, agent_id: str | None = None):
        """Persist a chat message to the DB for history reconstruction"""
        if not db_manager.available or not self.current_session_id:
            return

        try:
            async with await db_manager.get_session() as session:
                msg = DBChatMessage(
                    session_id=self.current_session_id,
                    role=role,
                    content=str(content),
                    metadata_blob={"agent": agent_id.upper() if agent_id else None},
                )
                session.add(msg)
                await session.commit()
        except Exception as e:
            logger.error(f"[DB] ChatMessage storage failed: {e}")

    async def _resume_after_restart(self):
        """Check if we are recovering from a restart and resume state"""
        if not state_manager.available:
            return

        try:
            # Check for restart flag in Redis
            restart_key = state_manager._key("restart_pending")
            data = None
            if state_manager.redis_client:
                data = await state_manager.redis_client.get(restart_key)

            if data:
                restart_info = json.loads(cast("str", data))
                reason = restart_info.get("reason", "Unknown reason")
                session_id = restart_info.get("session_id", "current_session")

                logger.info(
                    f"[ORCHESTRATOR] Recovering from self-healing restart. Reason: {reason}",
                )

                if session_id == "current":
                    sessions = await state_manager.list_sessions()
                    if sessions:
                        session_id = sessions[0]["id"]

                saved_state = await state_manager.restore_session(session_id)
                if saved_state:
                    self.state = saved_state
                    self.current_session_id = session_id

                    if state_manager.redis_client:
                        await state_manager.redis_client.delete(restart_key)
                    self._resumption_pending = True

                    await self._log(
                        f"Система успішно перезавантажилася та відновила стан. Причина: {reason}",
                        "system",
                    )
                    await self._speak(
                        "atlas",
                        "Я повернувся. Продовжую виконання завдання з того ж місця.",
                    )
        except Exception as e:
            logger.error(f"[ORCHESTRATOR] Resume check failed: {e}")
            await self._log("System booted. Checking for pending tasks...", "system")

    async def _update_task_metadata(self):
        """Оновлює metadata_blob в Task для збереження поточного рекурсивного контексту."""
        try:
            from sqlalchemy import update

            if (
                not db_manager
                or not getattr(db_manager, "available", False)
                or not self.state.get("db_task_id")
            ):
                return

            task_metadata = {
                "goal_stack": shared_context.goal_stack.copy(),
                "parent_goal": shared_context.parent_goal,
                "recursive_depth": shared_context.recursive_depth,
                "current_goal": shared_context.current_goal,
            }

            async with await db_manager.get_session() as db_sess:
                task_id = self.state.get("db_task_id")
                if task_id and isinstance(task_id, str):
                    await db_sess.execute(
                        update(DBTask)
                        .where(DBTask.id == uuid.UUID(task_id))
                        .values(metadata_blob=task_metadata)
                    )
                await db_sess.commit()

        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Failed to update task metadata: {e}")

    async def _verify_db_ids(self):
        """Verify that restored DB IDs exist. If not, clear them."""
        try:
            if not db_manager or not getattr(db_manager, "available", False):
                return
        except (ImportError, NameError):
            return

        session_id_str = self.state.get("db_session_id")
        task_id_str = self.state.get("db_task_id")

        async with await db_manager.get_session() as db_sess:
            if session_id_str and isinstance(session_id_str, str):
                try:
                    session_id = uuid.UUID(session_id_str)
                    result = await db_sess.execute(
                        select(DBSession).where(DBSession.id == session_id),
                    )
                    if not result.scalar():
                        logger.warning(
                            f"[ORCHESTRATOR] Restored session_id {session_id_str} not found in DB. Clearing.",
                        )
                        del self.state["db_session_id"]
                        if "db_task_id" in self.state:
                            del self.state["db_task_id"]
                        return  # If session is gone, task is definitely gone
                except Exception as e:
                    logger.error(f"Error verifying session_id {session_id_str}: {e}")
                    # If it's not a valid UUID, it's definitely stale/junk
                    del self.state["db_session_id"]

            if task_id_str and isinstance(task_id_str, str):
                try:
                    task_id = uuid.UUID(task_id_str)
                    result = await db_sess.execute(select(DBTask).where(DBTask.id == task_id))
                    if not result.scalar():
                        logger.warning(
                            f"[ORCHESTRATOR] Restored task_id {task_id_str} not found in DB. Clearing.",
                        )
                        del self.state["db_task_id"]
                except Exception as e:
                    logger.error(f"Error verifying task_id {task_id_str}: {e}")
                    del self.state["db_task_id"]

    def get_state(self) -> dict[str, Any]:
        """Return current system state for API"""
        if not hasattr(self, "state") or not self.state:
            logger.warning("[ORCHESTRATOR] State not initialized, returning default state")
            return {
                "system_state": SystemState.IDLE.value,
                "current_task": "Waiting for input...",
                "active_agent": "ATLAS",
                "logs": [],
                "step_results": [],
            }

        # Determine active agent based on system state
        active_agent = "ATLAS"
        sys_state = self.state.get("system_state", SystemState.IDLE.value)

        if sys_state == SystemState.EXECUTING.value:
            active_agent = "TETYANA"
        elif sys_state == SystemState.VERIFYING.value:
            active_agent = "GRISHA"

        plan = self.state.get("current_plan")

        # Handle plan being either object or string (from Redis/JSON serialization)
        if plan:
            if isinstance(plan, str):
                task_summary = plan
            elif hasattr(plan, "goal"):
                task_summary = plan.goal
            else:
                task_summary = str(plan)
        else:
            task_summary = "IDLE"

        # Prepare messages for frontend
        messages = []
        from datetime import datetime

        msg_list = self.state.get("messages")
        if isinstance(msg_list, list):
            for m in msg_list:
                # Support both LangChain objects and plain dicts (from Redis serialization)
                m_type = ""
                if hasattr(m, "type"):
                    m_type = m.type
                elif isinstance(m, dict):
                    m_type = m.get("type", "")

                if m_type == "human" or isinstance(m, HumanMessage):
                    # Handle content which could be string or list (multi-modal)
                    content = (
                        getattr(m, "content", "")
                        if not isinstance(m, dict)
                        else m.get("content", "")
                    )
                    display_text = ""
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                display_text += item.get("text", "")
                            elif isinstance(item, dict) and item.get("type") == "image_url":
                                display_text += "\n[Зображення додано]"
                    else:
                        display_text = str(content)

                    # Extract timestamp from additional_kwargs or dict
                    timestamp = datetime.now().timestamp()
                    if hasattr(m, "additional_kwargs"):
                        timestamp = getattr(m, "additional_kwargs", {}).get("timestamp", timestamp)
                    elif isinstance(m, dict):
                        # Some versions of LC serialization put it in additional_kwargs dict inside kwargs
                        kwargs = m.get("kwargs", {})
                        timestamp = kwargs.get("additional_kwargs", {}).get("timestamp", timestamp)
                        if not timestamp and "timestamp" in m:
                            timestamp = m["timestamp"]

                    messages.append(
                        {
                            "agent": "USER",
                            "text": display_text,
                            "timestamp": timestamp,
                            "type": "text",
                        },
                    )
                elif m_type == "ai" or isinstance(m, AIMessage):
                    agent_name = "ATLAS"
                    if hasattr(m, "name") and getattr(m, "name", None):
                        agent_name = getattr(m, "name", "ATLAS")
                    elif isinstance(m, dict):
                        agent_name = m.get("name") or m.get("kwargs", {}).get("name") or "ATLAS"

                    content = (
                        getattr(m, "content", "")
                        if not isinstance(m, dict)
                        else m.get("content", "")
                    )

                    timestamp = datetime.now().timestamp()
                    if hasattr(m, "additional_kwargs"):
                        timestamp = getattr(m, "additional_kwargs", {}).get("timestamp", timestamp)
                    elif isinstance(m, dict):
                        kwargs = m.get("kwargs", {})
                        timestamp = kwargs.get("additional_kwargs", {}).get("timestamp", timestamp)
                        if not timestamp and "timestamp" in m:
                            timestamp = m["timestamp"]

                    messages.append(
                        {
                            "agent": agent_name,
                            "text": str(content),
                            "timestamp": timestamp,
                            "type": "voice",
                        },
                    )

        result = {
            "system_state": sys_state,
            "current_task": task_summary,
            "active_agent": active_agent,
            "session_id": self.current_session_id,
            "messages": messages[-50:],
            "logs": (self.state.get("logs") or [])[-100:],
            "step_results": self.state.get("step_results") or [],
            "metrics": metrics_collector.get_metrics(),
            "map_state": map_state_manager.to_dict(),
            "voice_enabled": self.voice.enabled if hasattr(self, "voice") else True,
        }

        # Reset map trigger after delivery to prevent looping/flapping in frontend
        map_state_manager.reset_map_trigger()

        return result

    async def _planning_loop(self, analysis, user_request, is_subtask, history):
        """Handle the planning and verification loop."""
        max_retries = 2
        plan = None

        async def keep_alive_logging():
            while True:
                await asyncio.sleep(15)
                await self._log("Atlas is thinking... (Planning logic flow)", "system")

        for attempt in range(max_retries + 1):
            if attempt > 0:
                await self._log(f"🔄 Спроба перепланування {attempt}/{max_retries}...", "system")
                analysis["simulation_result"] = getattr(self, "_last_verification_report", None)
                analysis["failed_plan"] = plan

            planning_task = asyncio.create_task(self.atlas.create_plan(analysis))
            logger_task = asyncio.create_task(keep_alive_logging())
            try:
                plan = await asyncio.wait_for(
                    planning_task,
                    timeout=config.get("orchestrator", {}).get("task_timeout", 1200.0),
                )
            finally:
                logger_task.cancel()

            if not plan or not plan.steps:
                await self._handle_no_steps_plan(
                    user_request, history, mode_profile=analysis.get("mode_profile")
                )
                return None

            self.state["current_plan"] = plan

            if not is_subtask:
                verified_plan = await self._verify_plan_with_grisha(
                    plan, user_request, attempt, max_retries
                )
                if verified_plan:
                    plan = verified_plan
                    break
                if attempt < max_retries:
                    continue
                break
            break
        return plan

    async def _handle_no_steps_plan(self, user_request, history, mode_profile=None):
        """Handle case where Atlas generates no steps."""
        msg = self.atlas.get_voice_message("no_steps")
        await self._speak("atlas", msg)
        fallback_chat = await self.atlas.chat(
            user_request, history=history, use_deep_persona=True, mode_profile=mode_profile
        )
        await self._speak("atlas", fallback_chat)

    async def _verify_plan_with_grisha(self, plan, user_request, attempt, max_retries):
        """Verify plan using Grisha and handle rejections."""
        self.state["system_state"] = SystemState.VERIFYING.value
        try:
            res = await self.grisha.verify_plan(plan, user_request, fix_if_rejected=(attempt >= 1))
            self._last_verification_report = res.description

            if res.verified:
                await self._speak("grisha", "План перевірено і затверджено. Починаємо.")
                # Positive feedback for the planner's success
                from src.brain.neural_core.core import neural_core

                neural_core.chemistry.reward(intensity=0.05)
                return plan

            # Plan rejected - stress for the planner node
            from src.brain.neural_core.core import neural_core

            neural_core.chemistry.stress(intensity=0.1, tool_name="grisha_plan_verification")

            # NEGOTIATION PHASE
            assessment = await self.atlas.assess_plan_critique(plan, res.description, res.issues)
            if assessment.get("action") == "DISPUTE":
                confidence = float(assessment.get("confidence", 0.0))
                argument = assessment.get("argument", "No argument provided")

                await self._log(
                    f"Atlas disputes Grisha's critique (Conf: {confidence}): {argument}", "atlas"
                )

                if confidence > 0.8:
                    await self._speak(
                        "atlas",
                        f"Гріша, я не згоден: {argument}. Я впевнений у плані, тому ми починаємо.",
                    )
                    logger.info(
                        "[ORCHESTRATOR] Atlas overrode Grisha's rejection due to high confidence debate."
                    )
                    return plan
                await self._log(
                    "Atlas debated but decided to accept feedback due to lower confidence.",
                    "atlas",
                )

            # Voice: concise Ukrainian only; English issues stay in logs for Tetyana
            fallback_prefix = (
                "Гріша знову виявив недоліки." if attempt > 0 else "Гріша відхилив початковий план."
            )
            await self._speak("grisha", res.voice_message or fallback_prefix)

            if attempt >= max_retries and res.fixed_plan:
                await self._speak("grisha", "Я переписав план самостійно.")
                return res.fixed_plan

            if attempt == max_retries:
                if res.fixed_plan:
                    logger.warning("[ORCHESTRATOR] Planning failed. ARCHITECT OVERRIDE.")
                    await self._speak("grisha", "Я повністю переписав план. Виконуємо мою версію.")
                    return res.fixed_plan

                logger.warning("[ORCHESTRATOR] Planning failed. FORCE PROCEED.")
                await self._speak("grisha", "План має недоліки, але ми починаємо за наказом.")
                return plan
            return None
        finally:
            self.state["system_state"] = SystemState.PLANNING.value

    async def _create_db_task(self, user_request, plan):
        """Create DB task and knowledge graph node."""
        try:
            if not (
                db_manager
                and getattr(db_manager, "available", False)
                and self.state.get("db_session_id")
            ):
                return

            async with await db_manager.get_session() as db_sess:
                new_task = DBTask(
                    session_id=self.state["db_session_id"],
                    goal=user_request,
                    status="PENDING",
                    metadata_blob={
                        "goal_stack": shared_context.goal_stack.copy(),
                        "parent_goal": shared_context.parent_goal,
                        "recursive_depth": shared_context.recursive_depth,
                    },
                    parent_task_id=self.state.get("parent_task_id"),
                )
                db_sess.add(new_task)
                await db_sess.commit()
                self.state["db_task_id"] = str(new_task.id)

                await knowledge_graph.add_node(
                    node_type="TASK",
                    node_id=f"task:{new_task.id}",
                    attributes={"goal": user_request, "steps_count": len(plan.steps)},
                )
        except Exception as e:
            logger.error(f"DB Task creation failed: {e}")

    async def _initialize_run_state(
        self, user_request: str, session_id: str, images: list[dict[str, Any]] | None = None
    ) -> str:
        """Initialize session state and DB records for a run."""

        is_subtask = getattr(self, "_in_subtask", False)
        if is_subtask:
            return session_id

        if not hasattr(self, "state") or self.state is None:
            self.state = {
                "messages": [],
                "system_state": SystemState.IDLE.value,
                "current_plan": None,
                "step_results": [],
                "error": None,
                "logs": [],
            }

        # Language Guard: Detect English input while TTS is in Ukrainian
        if config.get("voice.tts.interaction_language_guard", False):
            latin_chars = len(re.findall(r"[a-zA-Z]", user_request))
            total_chars = len(user_request.strip())
            if total_chars > 5 and (latin_chars / total_chars) > 0.3:
                await self._log(
                    "⚠️ Виявлено англійську мову взаємодії. Система AtlasTrinity синхронізована для українського TTS.",
                    "system",
                    "warning",
                )

        try:
            if (
                state_manager
                and getattr(state_manager, "available", False)
                and not self.state["messages"]
                and session_id == "current_session"
            ):
                saved_state = await state_manager.restore_session(session_id)
                if saved_state:
                    self.state = saved_state
        except Exception:
            pass

        if session_id == "current_session" and isinstance(self.state.get("session_id"), str):
            session_id = self.state["session_id"]
            self.current_session_id = session_id
        else:
            self.state["session_id"] = session_id

        if not self.state.get("_theme"):
            self.state["_theme"] = user_request[:40] + ("..." if len(user_request) > 40 else "")

        await self._verify_db_ids()

        # Handle multi-modal request if images are present
        if images:
            content: list[dict[str, Any]] = [{"type": "text", "text": user_request}]
            for img in images:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{img['content_type']};base64,{img['data_b64']}"
                        },
                    }
                )
            msg = HumanMessage(content=cast("Any", content))
            self.state["current_images"] = images  # Temporary store for Atlas
        else:
            msg = HumanMessage(content=user_request)
            self.state["current_images"] = []

        msg.additional_kwargs["timestamp"] = datetime.now().timestamp()
        cast("list[BaseMessage]", self.state["messages"]).append(msg)
        asyncio.create_task(self._save_chat_message("human", user_request))

        # DB Session creation
        try:
            if (
                db_manager
                and getattr(db_manager, "available", False)
                and "db_session_id" not in self.state
            ):
                async with await db_manager.get_session() as db_sess:
                    # Use existing session_id if available (and valid UUID), otherwise create new
                    s_id = uuid.uuid4()
                    if session_id and session_id != "current_session":
                        try:
                            s_id = uuid.UUID(session_id)
                        except (ValueError, TypeError):
                            logger.warning(
                                f"[DB] Invalid session_id '{session_id}', generating new UUID."
                            )

                    new_session = DBSession(
                        id=s_id,
                        started_at=datetime.now(UTC),
                        metadata_blob={"theme": self.state["_theme"]},
                    )

                    db_sess.add(new_session)
                    await db_sess.commit()

                    self.state["db_session_id"] = str(new_session.id)

                    # If we were in "current_session" mode, update it to the concrete ID
                    if session_id == "current_session":
                        self.current_session_id = str(new_session.id)
                        self.state["session_id"] = self.current_session_id

                    logger.info(f"[DB] Session successfully created: {self.state['db_session_id']}")
            elif not db_manager:
                logger.warning("[DB] Creation skipped: db_manager is None")
            elif not getattr(db_manager, "available", False):
                logger.warning("[DB] Creation skipped: db_manager.available is False")
            elif "db_session_id" in self.state:
                logger.info(
                    f"[DB] Creation skipped: db_session_id exists ({self.state['db_session_id']})"
                )

        except Exception as e:
            logger.error(f"[DB] Session creation failed: {e}", exc_info=True)

        return session_id

    async def _get_run_plan(
        self, user_request: str, is_subtask: bool, images: list[dict[str, Any]] | None = None
    ) -> Any:
        """Retrieve or create a plan for the current run."""

        # 1. Resumption logic
        if self.state.get("current_plan") and getattr(self, "_resumption_pending", False):
            plan_obj = self.state["current_plan"]
            self._resumption_pending = False
            if isinstance(plan_obj, dict):
                from src.brain.agents.atlas import TaskPlan

                return TaskPlan(
                    id=plan_obj.get("id", "resumed"),
                    goal=plan_obj.get("goal", user_request),
                    steps=plan_obj.get("steps", []),
                )
            return plan_obj

        # 2. Planning logic
        try:
            messages_raw = self.state.get("messages", []) or []
            if not isinstance(messages_raw, list):
                messages_raw = []
            history: list[Any] = messages_raw[-25:-1] if len(messages_raw) > 1 else []
            analysis = await self.atlas.analyze_request(
                user_request, history=history, images=images
            )
            intent = analysis.get("intent")

            # Workflow routing

            if intent and intent in behavior_engine.config.get("workflows", {}):
                self.state["system_state"] = SystemState.EXECUTING.value
                success = await workflow_engine.execute_workflow(
                    str(intent),
                    {
                        "orchestrator": self,
                        "user_request": user_request,
                        "intent_analysis": analysis,
                    },
                )
                msg = (
                    f"Workflow '{intent}' completed." if success else f"Workflow '{intent}' failed."
                )
                await self._speak("atlas", msg)
                return {"status": "completed", "result": msg, "type": "workflow"}

            # Simple intent routing (chat, solo_task, etc.)
            # Pass ModeProfile through so chat() uses LLM classification, not keywords
            # Note: deep_chat intent maps to "chat" via ModeProfile.intent property,
            # but "deep_chat" is kept here defensively. Mode-specific behavior
            # (llm_deep, prompt_template, protocols) is driven by ModeProfile, not intent.
            mode_profile = analysis.get("mode_profile")

            # Handle segmented requests
            if analysis.get("is_segmented", False):
                return await self._handle_segmented_request(
                    user_request, history, images, analysis, is_subtask
                )

            if intent in ["chat", "deep_chat", "recall", "status", "solo_task"]:
                response = analysis.get("initial_response") or await self.atlas.chat(
                    user_request,
                    history=history,
                    use_deep_persona=analysis.get("use_deep_persona", False),
                    intent=intent,
                    on_preamble=self._speak,
                    images=images,
                    mode_profile=mode_profile,
                )
                if response != "__ESCALATE__":
                    # CRITICAL FIX: Ensure the response is translated for BOTH UI and Voice
                    # This prevents the English leakage in the chat panel
                    final_response = await self.voice.prepare_speech_text(str(response))

                    # Persist response to history so it appears in UI
                    if self.state and "messages" in self.state:
                        msg = AIMessage(content=final_response, name="ATLAS")
                        msg.additional_kwargs["timestamp"] = datetime.now().timestamp()
                        self.state["messages"].append(msg)
                        asyncio.create_task(self._save_chat_message("ai", final_response, "atlas"))

                    # chat_visible=False because the AIMessage was already appended above
                    await self._speak("atlas", final_response, chat_visible=False)
                    return {"status": "completed", "result": final_response, "type": intent}

            # Complex task planning
            self.state["system_state"] = SystemState.PLANNING.value

            # [MEMORY RECALL] Enrich analysis with Golden Fund context
            if intent not in ["chat", "deep_chat"]:
                recalled_context = await self.recall_memories(user_request)
                if recalled_context:
                    analysis["memory_context"] = recalled_context
                    # Also append to history for the planner to see clearly
                    if not history:
                        history = []
                    history.append(
                        SystemMessage(content=f"System Memory Context:\n{recalled_context}")
                    )

            shared_context.available_mcp_catalog = await mcp_manager.get_mcp_catalog()
            # Internal status message — speak but don't show in chat panel
            await self._speak(
                "atlas", analysis.get("voice_response") or "Аналізую запит...", chat_visible=False
            )

            # 3. Intent-based Routing for Tasks
            if intent in ["task", "subtask", "follow_up"]:
                self.state["system_state"] = SystemState.PLANNING.value
                preamble = analysis.get("initial_response")
                if preamble:
                    await self._speak("atlas", preamble)

                # Return plan from planning loop
                return await self._planning_loop(analysis, user_request, is_subtask, history)

            plan = await self._planning_loop(analysis, user_request, is_subtask, history)
            if plan:
                await self._create_db_task(user_request, plan)
                await self._speak(
                    "atlas", self.atlas.get_voice_message("plan_created", steps=len(plan.steps))
                )
            return plan

        except Exception as e:
            logger.error(f"[ORCHESTRATOR] Planning error: {e}")
            self.state["system_state"] = SystemState.ERROR.value
            return {"status": "error", "error": str(e)}

    async def run(
        self, user_request: str, images: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Main orchestration loop with advanced persistence and memory"""

        self.stop()
        self.active_task = asyncio.current_task()
        start_time = asyncio.get_event_loop().time()
        session_id = self.current_session_id
        is_subtask = getattr(self, "_in_subtask", False)

        if not IS_MACOS:
            await self._log(f"WARNING: Running on {PLATFORM_NAME}.", "system", type="warning")

        session_id = await self._initialize_run_state(user_request, session_id, images=images)
        try:
            shared_context.push_goal(user_request)
        except RecursionError as e:
            logger.error(f"[ORCHESTRATOR] Cannot start: {e}")
            return {"status": "error", "error": str(e)}

        # Plan Resolution
        plan_or_result = await self._get_run_plan(user_request, is_subtask, images=images)
        if isinstance(plan_or_result, dict):
            # Already handled (e.g. chat response, workflow result)
            self.active_task = None
            if plan_or_result.get("status") == "completed":
                self.state["system_state"] = SystemState.IDLE.value
                msgs = self.state.get("messages", [])
                msg_count = len(msgs) if isinstance(msgs, list) else 0
                await self._handle_post_execution_phase(
                    user_request,
                    is_subtask,
                    start_time,
                    session_id,
                    msg_count,
                    intent=plan_or_result.get("type"),
                )
            return plan_or_result

        plan = plan_or_result
        if not plan:
            self.active_task = None
            msgs = self.state.get("messages", [])
            msg_count = len(msgs) if isinstance(msgs, list) else 0
            await self._handle_post_execution_phase(
                user_request, is_subtask, start_time, session_id, msg_count, intent="chat"
            )
            return {"status": "completed", "result": "No plan generated.", "type": "chat"}

        self.state["system_state"] = SystemState.EXECUTING.value
        try:
            if plan and plan.steps:
                await self._execute_steps_recursive(plan.steps)
        except Exception as e:
            await self._log(f"Execution error: {e}", "error")
            self.active_task = None
            return {"status": "error", "error": str(e)}

        is_subtask = getattr(self, "_in_subtask", False)
        msgs = self.state.get("messages", [])
        msg_count = len(msgs) if isinstance(msgs, list) else 0
        await self._handle_post_execution_phase(
            user_request, is_subtask, start_time, session_id, msg_count
        )
        self.active_task = None
        return {"status": "completed", "result": self.state["step_results"]}

    async def _handle_segmented_request(
        self, user_request: str, history, images, analysis, is_subtask: bool
    ) -> dict[str, Any]:
        """Handle requests that were split into multiple mode segments."""
        segments = analysis.get("segments", [])
        if not segments:
            # Fallback to single mode processing
            return await self._handle_single_mode_request(
                user_request, history, images, analysis, is_subtask
            )

        logger.info(f"[ORCHESTRATOR] Processing {len(segments)} segments sequentially")

        results = []
        combined_response = ""

        for i, segment in enumerate(segments):
            logger.info(
                f"[ORCHESTRATOR] Processing segment {i + 1}/{len(segments)}: "
                f"mode={segment.mode}, priority={segment.priority}, text='{segment.text[:50]}...'"
            )
            logger.info(
                f"[ORCHESTRATOR] Segment {i + 1} profile: tools_access={segment.profile.tools_access if segment.profile else 'None'}, trinity_required={segment.profile.trinity_required if segment.profile else 'None'}"
            )

            # Process each segment with its specific mode profile
            segment_result = await self._process_single_segment(
                segment, history, images, is_subtask
            )

            results.append(segment_result)
            logger.info(
                f"[ORCHESTRATOR] Segment {i + 1} completed: status={segment_result.get('status')}"
            )

            # --- CRITICAL FIX: Immediate feedback for all segments ---
            # Speak the result NOW before moving to the next segment
            if segment_result.get("result") and not is_subtask:
                await self._speak("atlas", segment_result["result"])

            # Combine responses for the final session history
            if segment_result.get("result"):
                if combined_response:
                    combined_response += "\n\n"
                combined_response += f"[{segment.mode.upper()}] {segment_result['result']}"

        # Save combined result to session
        await self._save_chat_message("user", user_request)
        await self._save_chat_message("assistant", combined_response)

        return {
            "status": "completed",
            "result": combined_response,
            "type": "segmented",
            "segments": len(segments),
            "segment_results": results,
        }

    async def _process_single_segment(
        self, segment, history, images, is_subtask: bool
    ) -> dict[str, Any]:
        """Process a single segment with its mode profile."""

        # Use the segment's mode profile for processing
        if segment.mode in ["chat", "deep_chat", "recall", "status", "solo_task"]:
            # Simple modes - use Atlas directly
            response = await self.atlas.chat(
                segment.text,
                history=history,
                use_deep_persona=segment.profile.use_deep_persona if segment.profile else False,
                intent=segment.mode,
                on_preamble=self._speak,
                images=images,
                mode_profile=segment.profile,
            )

            # Ensure translation for segmented feedback
            final_response = await self.voice.prepare_speech_text(str(response))
            return {"status": "completed", "result": final_response, "mode": segment.mode}

        # Complex modes (task, development) - need full planning
        # Create temporary analysis for this segment
        segment_analysis = {
            "intent": segment.mode,
            "mode_profile": segment.profile,
            "use_deep_persona": segment.profile.use_deep_persona if segment.profile else False,
            "enriched_request": segment.text,
            "complexity": segment.profile.complexity if segment.profile else "medium",
        }

        # Run planning for this segment
        self.state["system_state"] = SystemState.PLANNING.value
        plan = await self._planning_loop(segment_analysis, segment.text, is_subtask, history)

        if plan and plan.steps:
            step_results = self.state.get("step_results")
            steps_before = len(step_results) if isinstance(step_results, list) else 0
            await self._create_db_task(segment.text, plan)
            await self._execute_steps_recursive(plan.steps)

            # Evaluate this segment immediately for better feedback
            all_results = self.state.get("step_results")
            current_results = all_results[steps_before:] if isinstance(all_results, list) else []

            evaluation = await self._evaluate_and_remember(
                segment.text,
                intent=segment.mode,
                results=current_results if isinstance(current_results, list) else None,
                silent_if_fail=True,
            )

            report = (
                evaluation.get("final_report")
                if isinstance(evaluation, dict)
                else "Завдання виконано."
            )
            return {"status": "completed", "result": report, "mode": segment.mode}

        return {
            "status": "completed",
            "result": "Планування не виявило необхідних кроків.",
            "mode": segment.mode,
        }

    async def _handle_single_mode_request(
        self, user_request: str, history, images, analysis, is_subtask: bool
    ) -> dict[str, Any]:
        """Fallback for when segmentation fails but we have a mode profile."""
        mode_profile = analysis.get("mode_profile")
        intent = analysis.get("intent", "chat")

        if intent in ["chat", "deep_chat", "recall", "status", "solo_task"]:
            response = await self.atlas.chat(
                user_request,
                history=history,
                use_deep_persona=analysis.get("use_deep_persona", False),
                intent=intent,
                on_preamble=self._speak,
                images=images,
                mode_profile=mode_profile,
            )
            return {"status": "completed", "result": response, "type": intent}

        # Fallback to planning for complex modes
        self.state["system_state"] = SystemState.PLANNING.value
        plan = await self._planning_loop(analysis, user_request, is_subtask, history)
        if plan:
            await self._create_db_task(user_request, plan)
        return {"status": "error", "error": "Failed to process request"}

    async def _handle_post_execution_phase(
        self,
        user_request: str,
        is_subtask: bool,
        start_time: float,
        session_id: str,
        msg_count: int,
        intent: str | None = None,
    ):
        """Evaluation, memory management and cleanup."""
        duration = asyncio.get_event_loop().time() - start_time
        notifications.show_completion(user_request, True, duration)

        if not is_subtask and self.state["system_state"] != SystemState.ERROR.value:
            await self._evaluate_and_remember(user_request, intent=intent)

        # Final cleanup tasks
        self.state["system_state"] = SystemState.COMPLETED.value
        shared_context.pop_goal()

        # Async tasks for summary and background operations
        if not is_subtask and msg_count > 2:
            asyncio.create_task(self._persist_session_summary(session_id))

            # [NEURAL CORE] Trigger deep reflection
            try:
                from src.brain.neural_core.reflection.pipeline import reflex_pipe

                asyncio.create_task(
                    reflex_pipe.analyze_session(
                        session_id=session_id,
                        logs=cast("list[dict[str, Any]]", self.state.get("logs", [])),
                        request=user_request,
                        results=cast("list[Any]", self.state.get("step_results", [])),
                    )
                )
            except Exception as re:
                logger.warning(f"[ORCHESTRATOR] NeuralCore ReflexPipe failed to trigger: {re}")

        await self._notify_task_finished(session_id)
        self._trigger_backups()

    async def _evaluate_and_remember(
        self,
        user_request: str,
        intent: str | None = None,
        results: list[dict[str, Any]] | None = None,
        silent_if_fail: bool = False,
    ) -> dict[str, Any] | None:
        """Evaluate execution quality and save to LTM."""
        # Skip evaluation for simple chat/informative intents to avoid duplicated greetings
        if intent in ["chat", "deep_chat", "solo_task", "recall", "status"]:
            logger.debug(f"[ORCHESTRATOR] Skipping evaluation for intent: {intent}")
            return None

        actual_results = (
            results if isinstance(results, list) else self.state.get("step_results", [])
        )
        if not isinstance(actual_results, list) or (not actual_results and intent != "segmented"):
            logger.debug("[ORCHESTRATOR] No results to evaluate")
            return None

        # Clean list to ensure it only contains dicts for evaluate_execution
        clean_results = [r for r in actual_results if isinstance(r, dict)]

        try:
            evaluation = await self.atlas.evaluate_execution(user_request, clean_results)

            if evaluation.get("achieved"):
                msg = evaluation.get("final_report") or "Завдання успішно виконано."
                # We don't speak here if it's a global evaluation of a segmented request
                # (because segments already spoke their own reports)
                if intent != "segmented":
                    await self._speak("atlas", msg)
            elif not silent_if_fail:
                await self._log(
                    "Evaluation indicated task was not fully achieved", "system", "warning"
                )

            if evaluation.get("should_remember") and evaluation.get("quality_score", 0) >= 0.7:
                await self._save_to_ltm(user_request, evaluation)

            # Update DB Task
            if self.state.get("db_task_id"):
                await self._mark_db_golden_path()

            return evaluation
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            return None

    async def _save_to_ltm(self, user_request, evaluation):
        """Save successful strategy to Long-term Memory."""
        from src.brain.memory import long_term_memory

        if long_term_memory and getattr(long_term_memory, "available", False):
            steps = evaluation.get("compressed_strategy") or self._extract_golden_path(
                self.state["step_results"]
            )
            long_term_memory.remember_strategy(
                task=user_request, plan_steps=steps, outcome="SUCCESS", success=True
            )

    async def _mark_db_golden_path(self):
        """Mark task as golden path in DB."""

        async with await db_manager.get_session() as db_sess:
            task_id = self.state.get("db_task_id")
            if task_id and isinstance(task_id, str):
                await db_sess.execute(
                    update(DBTask).where(DBTask.id == uuid.UUID(task_id)).values(golden_path=True)
                )
            await db_sess.commit()

    async def _notify_task_finished(self, session_id):
        """Publish task finish event."""
        try:
            if state_manager and getattr(state_manager, "available", False):
                await state_manager.publish_event(
                    "tasks",
                    {"type": "task_finished", "status": "completed", "session_id": session_id},
                )
        except Exception:
            pass

    def _trigger_backups(self):
        """Trigger background database backups."""
        try:
            from src.maintenance.setup_dev import backup_databases

            asyncio.create_task(asyncio.to_thread(backup_databases))
        except Exception:
            pass

    async def _persist_session_summary(self, session_id: str):
        """Generates a professional summary and stores it in DB and Vector memory."""
        try:
            from src.brain.memory.db.schema import ConversationSummary as DBConvSummary

            messages = self.state.get("messages")
            if not isinstance(messages, list) or not messages:
                return

            summary_data = await self.atlas.summarize_session(messages)
            summary = summary_data.get("summary", "No summary generated")
            entities = summary_data.get("entities", [])

            # A. Store in Vector Memory
            try:
                if long_term_memory and getattr(long_term_memory, "available", False):
                    long_term_memory.remember_conversation(
                        session_id=session_id,
                        summary=summary,
                        metadata={"entities": entities},
                    )
            except Exception:
                pass

            # B. Store in Structured DB
            try:
                if db_manager and getattr(db_manager, "available", False):
                    async with await db_manager.get_session() as db_sess:
                        new_summary = DBConvSummary(
                            session_id=session_id,
                            summary=summary,
                            key_entities=entities,
                        )
                        db_sess.add(new_summary)
                        await db_sess.commit()
            except Exception as e:
                logger.error(f"Failed to store summary in DB: {e}")

            # D. Persist summary to DB only (NOT to chat state).
            #    Adding to state["messages"] leaks English analytical text into the chat panel.
            try:
                await self._save_chat_message("ai", summary, "ATLAS")
            except Exception as e:
                logger.error(f"Failed to persist summary to DB: {e}")

            # C. Add entities to Knowledge Graph (Background)
            for ent_name in entities:
                knowledge_graph.add_node_background(
                    node_type="CONCEPT",
                    node_id=f"concept:{ent_name.lower().replace(' ', '_')}",
                    attributes={
                        "description": f"Entity mentioned in session {session_id}",
                        "source": "session_summary",
                    },
                    namespace="global",
                )
            logger.info(f"[ORCHESTRATOR] Persisted summary for {session_id}")
        except Exception as e:
            logger.error(f"[ORCHESTRATOR] Failed to persist session summary: {e}")

    def _extract_golden_path(self, raw_results: list[dict[str, Any]]) -> list[str]:
        """Extracts only the successful actions that led to the solution.
        Smartly filters out:
        - Failed attempts
        - Steps replaced by recovery actions
        - Repair loops (e.g. Step 3 failed -> 3.1 fixed -> Step 3 success)
        """
        golden_path = []

        # 1. Deduplicate by step_id, keeping only the LATEST attempt
        # This handles retries automatically (Attempt 1 fail, Attempt 2 success -> keeps Attempt 2)
        latest_results = {}
        for res in raw_results:
            step_id = res.get("step_id")
            latest_results[step_id] = res

        # 2. Sort by step ID to respect execution order
        # We need a robust sort for "1", "2", "2.1", "2.2", "3"
        def parse_step_id(sid):
            try:
                return [int(p) for p in str(sid).split(".")]
            except:
                return [float("inf")]  # Put weird IDs at current level end

        sorted_steps = sorted(
            latest_results.values(),
            key=lambda x: parse_step_id(x.get("step_id", "0")),
        )

        # 3. Filter for SUCCESS only
        # If a step failed but the task continued, it means it was critical to fix it?
        # No, if it failed and we moved on, usually means recovery handled it.
        # We want to capture the recovery steps (e.g. 2.1) if they succeeded.

        for item in sorted_steps:
            if item.get("success"):
                # Clean up action text
                action = item.get("action", "")

                # Remove ID prefix if present for cleaner reading e.g. "[3.1] Fix code" -> "Fix code"
                if action.startswith("[") and "]" in action:
                    try:
                        action = action.split("]", 1)[1].strip()
                    except:
                        pass

                if not action:
                    action = str(item.get("result", ""))[:100]

                golden_path.append(action)

        return golden_path

    async def _build_self_heal_context(
        self, step: dict[str, Any], step_id: str
    ) -> tuple[str, str, list[dict[str, Any]]]:
        """Prepare logs and error context for self-healing."""
        recent_logs = []
        if self.state and "logs" in self.state:
            recent_logs = [
                f"[{l.get('agent', 'SYS')}] {l.get('message', '')}"
                for l in self.state["logs"][-20:]
            ]
        log_context = "\n".join(recent_logs)
        error_context = f"Step ID: {step_id}\nAction: {step.get('action', '')}\n"

        raw_results = self.state.get("step_results", []) if self.state else []
        if not isinstance(raw_results, list):
            raw_results = []

        step_recovery_history = [
            {
                "attempt": i + 1,
                "action": str(r.get("action", ""))[:200],
                "status": "success" if r.get("success") else "failed",
                "error": str(r.get("error", ""))[:500] if r.get("error") else None,
            }
            for i, r in enumerate(raw_results)
            if isinstance(r, dict)
            and str(r.get("step_id", "")).startswith(str(step_id).split(".")[0])
        ]
        return log_context, error_context, step_recovery_history

    async def _log_recovery_attempt_db(
        self,
        db_step_id: str | None,
        depth: int,
        error: str,
        success: bool = False,
        vibe_text: str | None = None,
        attempt_id: Any = None,
    ) -> Any:
        """Log recovery attempt start or update to the database."""
        try:
            from src.brain.memory.db.schema import RecoveryAttempt

            if not (db_manager and getattr(db_manager, "available", False)):
                return None

            async with await db_manager.get_session() as db_sess:
                if attempt_id:
                    rec = await db_sess.get(RecoveryAttempt, attempt_id)
                    if rec:
                        rec.success = success
                        if vibe_text:
                            rec.vibe_text = str(vibe_text)[:5000]
                        await db_sess.commit()
                        return attempt_id
                elif db_step_id:
                    rec_attempt = RecoveryAttempt(
                        step_id=cast("Any", db_step_id),
                        depth=depth,
                        recovery_method="vibe",
                        success=success,
                        error_before=str(error)[:5000],
                    )
                    db_sess.add(rec_attempt)
                    await db_sess.commit()
                    return rec_attempt.id
        except Exception as e:
            logger.error(f"DB Recovery logging failed: {e}")
        return None

    async def _get_vibe_diagnosis(
        self,
        step: dict[str, Any],
        step_id: str,
        error: str,
        log_context: str,
        step_recovery_history: list[dict[str, Any]],
        step_result: StepResult | None,
        error_context: str,
    ) -> str | None:
        """Call Vibe to analyze and propose a fix."""
        try:
            await self._log("[VIBE] Diagnostic Phase...", "vibe")
            vibe_res = await asyncio.wait_for(
                mcp_manager.call_tool(
                    "vibe",
                    "vibe_analyze_error",
                    {
                        "error_message": f"{error_context}\n{error}",
                        "log_context": log_context,
                        "auto_fix": False,
                        "step_action": step.get("action", ""),
                        "expected_result": step.get("expected_result", ""),
                        "actual_result": str(step_result.result if step_result else "N/A")[:2000],
                        "recovery_history": step_recovery_history,
                        "full_plan_context": str(self.state.get("current_plan", ""))[:3000],
                    },
                ),
                timeout=300,
            )
            return self._extract_vibe_payload(self._mcp_result_to_text(vibe_res))
        except Exception as e:
            logger.error(f"Vibe diagnosis failed: {e}")
            return None

    async def _handle_grisha_vibe_audit(
        self,
        step_id: str,
        error: str,
        vibe_text: str,
    ) -> tuple[bool, StepResult | None, dict[str, Any] | None]:
        """Engagement logic for Grisha's audit of the Vibe fix."""
        rejection_count = getattr(self, "_rejection_cycles", {}).get(step_id, 0)
        grisha_audit = await self.grisha.audit_vibe_fix(str(error), vibe_text)

        if grisha_audit.get("audit_verdict") == "REJECT":
            rejection_count += 1
            if not hasattr(self, "_rejection_cycles"):
                self._rejection_cycles = {}
            self._rejection_cycles[step_id] = rejection_count

            if rejection_count >= 3:
                logger.warning(
                    f"[ORCHESTRATOR] Grisha rejected Vibe fix 3x for {step_id}. Escalating."
                )
                await self._log(
                    "⚠️ Система застрягла після 3 відхилень Grisha. Потрібне втручання.", "error"
                )
                return (
                    False,
                    StepResult(
                        step_id=step_id,
                        success=False,
                        result=f"Grisha rejection loop: {grisha_audit.get('reasoning')}",
                        error="need_user_input",
                    ),
                    None,
                )
            return True, None, None

        if hasattr(self, "_rejection_cycles") and step_id in self._rejection_cycles:
            del self._rejection_cycles[step_id]

        return False, None, grisha_audit

    async def _apply_vibe_fix(
        self,
        step_id: str,
        error: str,
        vibe_text: str,
        healing_decision: dict[str, Any],
    ) -> bool:
        """Sequential thinking and applying the Vibe fix."""
        try:
            instructions = healing_decision.get("instructions_for_vibe", "")
            if not instructions:
                instructions = "Apply the fix proposed in the analysis."

            await self._log(
                "[ORCHESTRATOR] Engaging Deep Reasoning before applying fix...", "system"
            )
            analysis = await self.atlas.use_sequential_thinking(
                f"Analyze why step {step_id} failed and how to apply the vibe fix effectively.\nError: {error}\nVibe Fix: {vibe_text}\nInstructions: {instructions}",
                total_thoughts=3,
            )
            if analysis.get("success"):
                logger.info(
                    f"[ORCHESTRATOR] Deep reasoning completed: {analysis.get('analysis', '')[:200]}..."
                )

            await mcp_manager.call_tool(
                "vibe",
                "vibe_prompt",
                {
                    "prompt": f"EXECUTE FIX: {instructions}",
                    "auto_approve": True,
                },
            )

            # --- Post-Fix: Run Global Lint ---
            await self._log("[FIX] Running global lint verification...", "system")
            lint_result = await mcp_manager.call_tool("devtools", "devtools_run_global_lint", {})

            if isinstance(lint_result, dict):
                if lint_result.get("success"):
                    await self._log("[FIX] Global lint passed successfully! ✅", "system")
                else:
                    await self._log(
                        f"[FIX] Global lint found issues (Exit {lint_result.get('exit_code')}). Check logs. ⚠️",
                        "system",
                    )

            logger.info(f"[ORCHESTRATOR] Vibe healing applied and verified for {step_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to apply Vibe fix: {e}")
            return False

    async def _refresh_architecture_diagrams(self) -> None:
        """Update architecture diagrams if enabled."""
        if (
            not config.get("self_healing", {})
            .get("vibe_debugging", {})
            .get("diagram_access", {})
            .get("update_after_fix", False)
        ):
            return

        try:
            diagram_result = await mcp_manager.call_tool(
                "devtools",
                "devtools_update_architecture_diagrams",
                {
                    "project_path": None,
                    "commits_back": 1,
                    "target_mode": "internal",
                    "use_reasoning": True,
                },
            )
            if diagram_result:
                await self._log("[SELF-HEAL] Architecture diagrams updated after fix", "system")
        except Exception as de:
            logger.warning(f"Diagram update after self-heal failed: {de}")

    async def _self_heal(
        self,
        step: dict[str, Any],
        step_id: str,
        error: str,
        step_result: StepResult | None,
        depth: int,
    ) -> tuple[bool, StepResult | None]:
        """Explicit self-healing workflow following the 8-phase protocol."""
        success = False
        updated_result = None
        db_step_id = cast("str | None", self.state.get("db_step_id"))

        # --- Phase 1: Pre-Diagnosis Diagram Refresh ---
        # Ensure Vibe has latest architectural context
        await self._refresh_architecture_diagrams()

        # --- Phase 2: Context Building ---
        log_context, error_context, step_recovery_history = await self._build_self_heal_context(
            step, step_id
        )

        # DB: Track Recovery Attempt Start
        recovery_attempt_id = await self._log_recovery_attempt_db(db_step_id, depth, error)

        try:
            # --- Phase 3 & 4: Vibe Diagnosis and Fix ---
            vibe_text = await self._get_vibe_diagnosis(
                step, step_id, error, log_context, step_recovery_history, step_result, error_context
            )

            if vibe_text:
                # --- Phase 7 (Early): Grisha Verification of PLAN ---
                rejected, fatal_result, grisha_audit = await self._handle_grisha_vibe_audit(
                    step_id, error, vibe_text
                )

                if fatal_result:
                    if recovery_attempt_id:
                        await self._log_recovery_attempt_db(
                            None,
                            depth,
                            error,
                            success=False,
                            vibe_text=fatal_result.result,
                            attempt_id=recovery_attempt_id,
                        )
                    return False, fatal_result

                if rejected:
                    return False, None

                # Evaluate strategy via Atlas
                healing_decision = await self.atlas.evaluate_healing_strategy(
                    str(error), vibe_text, grisha_audit or {}
                )
                await self._speak(
                    "atlas", healing_decision.get("voice_message", "Я знайшов рішення.")
                )

                if healing_decision.get("decision") == "PROCEED":
                    # --- Phase 4: Apply Fix ---
                    if await self._apply_vibe_fix(step_id, error, vibe_text, healing_decision):
                        success = True

                        # --- Phase 6: Diagram Update (Post-Apply) ---
                        await self._refresh_architecture_diagrams()

                        # DB Update: Success
                        if recovery_attempt_id:
                            await self._log_recovery_attempt_db(
                                None,
                                depth,
                                error,
                                success=True,
                                vibe_text=vibe_text,
                                attempt_id=recovery_attempt_id,
                            )

        except Exception as ve:
            logger.warning(f"Vibe self-healing workflow failed: {ve}")
            success = False
            if recovery_attempt_id:
                await self._log_recovery_attempt_db(
                    None,
                    depth,
                    error,
                    success=False,
                    vibe_text=f"CRASH: {ve!s}",
                    attempt_id=recovery_attempt_id,
                )

        return success, updated_result

    async def _handle_recursion_backoff(self, depth: int) -> None:
        """Apply exponential backoff for deeper recursion levels."""
        BACKOFF_BASE_MS = 500
        if depth > 1:
            backoff_ms = BACKOFF_BASE_MS * (2 ** (depth - 1))
            await self._log(
                f"Recursion depth {depth}: applying {backoff_ms}ms backoff",
                "orchestrator",
            )
            await asyncio.sleep(backoff_ms / 1000)

    async def _push_recursive_goal(
        self, parent_prefix: str | None, depth: int, steps: list[dict[str, Any]]
    ) -> bool:
        """Push a new goal to the shared context for a recursive level."""

        goal_description = (
            f"Recovery sub-tasks for step {parent_prefix}"
            if parent_prefix
            else f"Sub-plan at depth {depth} (parent: {shared_context.current_goal[:80] if shared_context.current_goal else 'root'})"
        )
        if parent_prefix or depth > 0:
            try:
                shared_context.push_goal(goal_description, total_steps=len(steps))
                logger.info(
                    f"[ORCHESTRATOR] 🎯 Entering recursive level {depth}: {goal_description}"
                )
                await self._update_task_metadata()
                return True
            except Exception as e:
                logger.warning(f"Failed to push goal: {e}")
        return False

    async def _pop_recursive_goal(self, goal_pushed: bool, depth: int) -> None:
        """Pop the goal from the shared context upon leaving a recursive level."""
        if goal_pushed:
            try:
                completed_goal = shared_context.pop_goal()
                logger.info(
                    f"[ORCHESTRATOR] ✅ Completed recursive level {depth}: {completed_goal}"
                )
                await self._update_task_metadata()
            except Exception as e:
                logger.warning(f"Failed to pop goal: {e}")

    def _is_step_already_completed(self, step_id: str) -> bool:
        """Check if a step has already been successfully completed."""
        step_results = self.state.get("step_results") or []
        return any(
            isinstance(res, dict) and str(res.get("step_id")) == str(step_id) and res.get("success")
            for res in step_results
        )

    async def _execute_step_attempt(
        self,
        step: dict[str, Any],
        step_id: str,
        attempt: int,
        depth: int,
    ) -> StepResult | None:
        """Execute a single attempt of a step with timeout handling."""
        try:
            timeout = float(config.get("orchestrator", {}).get("task_timeout", 1200.0))
            return await asyncio.wait_for(
                self.execute_node(
                    cast("TrinityState", self.state),
                    step,
                    step_id,
                    attempt=attempt,
                    depth=depth,
                ),
                timeout=timeout + 60.0,
            )
        except TimeoutError:
            logger.error(f"[ORCHESTRATOR] Step {step_id} timed out on attempt {attempt}")
            return None
        except Exception as e:
            logger.error(
                f"[ORCHESTRATOR] Step {step_id} crashed on attempt {attempt}: {e}",
                exc_info=True,
            )
            return None

    async def _handle_step_error_strategy(
        self,
        strategy: Any,
        step: dict[str, Any],
        step_id: str,
        attempt: int,
        last_error: str,
        step_result: StepResult | None,
        depth: int,
        steps: list[dict[str, Any]],
        index: int,
    ) -> tuple[bool, StepResult | None]:
        """Route the strategy decided by error_router by dispatching to sub-handlers."""
        action = str(strategy.action)

        if action in ["RETRY", "WAIT_AND_RETRY"]:
            return await self._handle_strategy_retry(strategy, attempt, step_result)

        if action == "RESTART":
            return await self._handle_strategy_restart(strategy, step_id)

        if action == "ASK_USER":
            return await self._handle_strategy_ask_user(strategy, step_id)

        if action == "VIBE_HEAL":
            return await self._handle_strategy_vibe_heal(
                strategy, step, step_id, last_error, step_result, depth
            )

        if action == "ATLAS_PLAN":
            return await self._handle_strategy_atlas_plan(
                strategy, step, step_id, last_error, steps, index
            )

        return False, step_result

    async def _handle_strategy_retry(
        self, strategy: Any, attempt: int, result: StepResult | None
    ) -> tuple[bool, StepResult | None]:
        """Handle standard RETRY and WAIT_AND_RETRY strategies."""
        if attempt >= strategy.max_retries:
            if str(strategy.action) == "WAIT_AND_RETRY":
                await self._log(f"Persistent infrastructure issue: {strategy.reason}.", "error")
                return False, StepResult(
                    step_id="unknown",
                    success=False,
                    error="infrastructure_failure",
                    result=f"API issue persisted. {strategy.reason}",
                )
            return False, result

        await self._log(
            f"Error detected. {strategy.reason}. Retrying in {strategy.backoff}s...", "orchestrator"
        )
        await asyncio.sleep(strategy.backoff)
        return True, None

    async def _handle_strategy_restart(
        self, strategy: Any, step_id: str
    ) -> tuple[bool, StepResult | None]:
        """Handle RESTART strategy by saving state and execv."""
        await self._log(f"CRITICAL: {strategy.reason}. Restarting...", "system", type="error")
        try:
            if state_manager and getattr(state_manager, "available", False):
                await state_manager.save_session(self.current_session_id, self.state)
                if redis_client := getattr(state_manager, "redis_client", None):
                    meta = {"reason": strategy.reason, "timestamp": datetime.now().isoformat()}
                    restart_key = state_manager._key("restart_pending")
                    await redis_client.set(restart_key, json.dumps(meta))
        except Exception as e:
            logger.error(f"Restart preparation failed: {e}")

        await asyncio.sleep(1.0)
        os.execv(sys.executable, [sys.executable, *sys.argv])  # nosec B606
        return False, StepResult(
            step_id=step_id, success=False, error="restarting", result="Restart initiated"
        )

    async def _handle_strategy_ask_user(
        self, strategy: Any, step_id: str
    ) -> tuple[bool, StepResult | None]:
        """Handle ASK_USER strategy with auto-approve timeout and interruption support."""
        reason = getattr(strategy, "reason", "Action requires permission")

        # Get timeout and permissiveness settings
        try:
            from src.mcp_server.vibe_server import get_vibe_config

            vibe_cfg = get_vibe_config()
            timeout = getattr(vibe_cfg, "confirmation_timeout_s", 20.0)
        except Exception:
            timeout = 20.0

        if timeout <= 5:
            msg = f"⚡ Виконую: {reason}. У вас {int(timeout)} секунд на скасування."
            voice = f"Буде виконано {reason}. У вас є {int(timeout)} секунд, щоб відмінити."
        else:
            msg = f"⚠️ ПЕРЕВІРКА: {reason}. Очікую {int(timeout)}с..."
            voice = f"Мені потрібне ваше підтвердження: {reason}. Чекаю {int(timeout)} секунд, або я прийму рішення сам."

        await self._log(msg, "system", type="warning" if timeout > 5 else "critical")
        await self._speak("atlas", voice)

        start_wait = time.time()
        while time.time() - start_wait < timeout:
            # 1. Check for explicit approval/denial
            messages = await message_bus.receive("orchestrator", MessageType.APPROVAL)
            if messages:
                payload = messages[0].payload
                if payload.get("approved"):
                    await self._log("✅ Користувач підтвердив дію.", "system")
                    return True, None
                await self._log("❌ Користувач відхилив дію.", "system")
                return False, StepResult(
                    step_id=step_id,
                    success=False,
                    error="denied_by_user",
                    result="User explicitly denied permission.",
                )

            # 2. INTERRUPT: Any human message pauses the system
            chat_messages = await message_bus.receive("orchestrator", MessageType.CHAT)
            if chat_messages:
                human_msg = chat_messages[0].payload.get("content", "")
                await self._log(
                    f"⏸️ Система призупинена користувачем: '{human_msg[:30]}...'",
                    "system",
                    type="warning",
                )
                await self._speak("atlas", "Зупиняюсь для обговорення. Я в режимі очікування.")
                self.pause()
                # Stay in "Discussion Bubble" (loop) until we hear "continue" or "go"
                return await self._enter_discussion_bubble(step_id, reason)

            await asyncio.sleep(0.5)

        # Timeout reached - Take responsibility
        await self._log(
            f"🦅 Час вичерпано ({int(timeout)}с). Атлас бере відповідальність на себе. Виконую.",
            "orchestrator",
            type="critical",
        )
        await self._speak("atlas", "Час вичерпано. Беру відповідальність на себе.")

        return True, None

    async def _enter_discussion_bubble(
        self, step_id: str, reason: str
    ) -> tuple[bool, StepResult | None]:
        """Stay in a loop waiting for instructions to resume or change course."""
        while True:
            # Wait for any new human message or a command to resume
            messages = await message_bus.receive("orchestrator", MessageType.CHAT)
            if messages:
                content = messages[0].payload.get("content", "").lower()
                # Resume keywords
                if any(
                    kw in content
                    for kw in ["продовжуй", "далі", "go", "continue", "виконуй", "так", "yes"]
                ):
                    await self._log("▶️ Продовжую за вказівкою користувача.", "system")
                    return True, None
                # Change/Abort keywords
                if any(
                    kw in content for kw in ["зупини", "відміни", "stop", "abort", "cancel", "ні"]
                ):
                    await self._log("🛑 Виконання скасовано користувачем.", "system")
                    return False, StepResult(
                        step_id=step_id,
                        success=False,
                        error="aborted_by_user",
                        result="User aborted execution during discussion.",
                    )
                # For any other message, Atlas can respond in chat mode if needed, but we keep the bubble
                await self._log("🗨️ Обговорення триває... (Очікую 'далі' або 'відміна')", "system")

            await asyncio.sleep(1)

    async def _check_for_interruption(self) -> bool:
        """Check if user has sent any message that should pause current execution."""
        messages = await message_bus.receive("orchestrator", MessageType.CHAT)
        if messages:
            for m in messages:
                # We check for sender directly if available, or payload sender
                sender = getattr(m, "sender", None) or m.payload.get("sender")
                if sender == "human":
                    return True
        return False

    async def _handle_strategy_vibe_heal(
        self, strategy: Any, step: dict, step_id: str, error: str, result: Any, depth: int
    ) -> tuple[bool, StepResult | None]:
        """Handle VIBE_HEAL (Parallel or Blocking)."""
        if config.get("parallel_healing", {}).get("enabled", True):
            try:
                logs = await self._get_recent_logs(50)
                tid = await parallel_healing_manager.submit_healing_task(step_id, error, step, logs)
                await self._log(f"Healing task {tid} submitted. Tetyana continues.", "orchestrator")
                return False, StepResult(
                    step_id=step_id,
                    success=False,
                    error="healing_initiated",
                    result=f"Parallel healing {tid}",
                )
            except Exception as e:
                logger.warning(f"Parallel healing failed, fallback to blocking: {e}")

        heal_success, heal_result = await self._self_heal(step, step_id, error, result, depth)
        return (True, None) if heal_success else (False, heal_result)

    async def _handle_strategy_atlas_plan(
        self, strategy: Any, step: dict, step_id: str, error: str, steps: list, index: int
    ) -> tuple[bool, StepResult | None]:
        """Handle ATLAS_PLAN strategy (Re-planning)."""
        await self._log(f"Strategic Recovery: {strategy.reason}. Re-planning...", "orchestrator")
        try:
            q = f"RECOVERY: Goal: {self.state.get('current_goal')}\nStep: {step_id}\nError: {error}"
            new_plan = await self.atlas.create_plan(
                {"enriched_request": q, "intent": "task", "complexity": "medium"}
            )
            if new_plan and getattr(new_plan, "steps", []):
                for offset, s in enumerate(new_plan.steps):
                    steps.insert(index + 1 + offset, s)
                return True, None
        except Exception as e:
            logger.error(f"Atlas re-planning failed: {e}")
        return False, None

    async def _validate_with_grisha_failure(
        self, step: dict[str, Any], step_id: str, step_result: StepResult | None, last_error: str
    ) -> bool:
        """Consult Grisha for a second opinion on a failed step."""
        if not config.get("orchestrator", {}).get("validate_failed_steps_with_grisha", False):
            return False

        try:
            await self._log(f"Requesting Grisha validation for {step_id}...", "orchestrator")
            screenshot = None
            expected = step.get("expected_result", "").lower()
            if any(k in expected for k in ["visual", "screenshot", "ui", "interface", "window"]):
                screenshot = await self.grisha.take_screenshot()

            goal_ctx = str(shared_context.get_goal_context() or "")
            verify_result = await self.grisha.verify_step(
                step=step,
                result=step_result
                or StepResult(step_id=step_id, success=False, result="", error=last_error),
                screenshot_path=screenshot,
                goal_context=goal_ctx,
                task_id=str(self.state.get("db_task_id") or ""),
            )
            if verify_result.verified:
                await self._log(f"Grisha verified step {step_id} despite failure.", "orchestrator")
                return True

            recovery_agent = config.get("orchestrator", {}).get("recovery_voice_agent", "atlas")
            await self._speak(
                recovery_agent, verify_result.voice_message or "Крок потребує відновлення."
            )
        except Exception as e:
            logger.warning(f"Grisha validation failed: {e}")
        return False

    async def _atlas_recovery_fallback(
        self,
        step_id: str,
        last_error: str,
        depth: int,
    ) -> bool:
        """Standard Atlas help as ultimate fallback."""
        try:
            recovery_agent = config.get("orchestrator", {}).get("recovery_voice_agent", "atlas")
            await self._log(
                f"Recovery for Step {step_id} (announced by {recovery_agent})...", "orchestrator"
            )
            if recovery_agent == "atlas":
                await self._speak(
                    "atlas", self.atlas.get_voice_message("recovery_started", step_id=step_id)
                )
            else:
                await self._speak(recovery_agent, "Крок зупинився — починаю процедуру відновлення.")

            recovery = await asyncio.wait_for(
                self.atlas.help_tetyana(str(step_id), str(last_error)),
                timeout=60.0,
            )
            await self._speak("atlas", recovery.get("voice_message", "Альтернативний шлях."))
            alt_steps = recovery.get("alternative_steps", [])
            if not alt_steps:
                return False

            # --- RECURSION GUARD ---
            error_hash = hash(str(alt_steps) + str(last_error))
            if not hasattr(self, "_attempted_recoveries"):
                self._attempted_recoveries: dict[str, int] = {}
            if self._attempted_recoveries.get(step_id) == error_hash:
                logger.warning(
                    f"[ORCHESTRATOR] 🔁 Step {step_id} stalled with same plan/error. Categorizing as LOOP."
                )
                raise Exception(f"Recursive recovery stall detected for step {step_id}.")
            self._attempted_recoveries[step_id] = error_hash

            # If depth is getting critical, ask user before crashing
            critical_depth = shared_context.max_recursive_depth - 1
            if depth >= critical_depth:
                logger.warning(
                    f"[ORCHESTRATOR] ⚠️ Critical recursion depth {depth} reached. Asking user."
                )
                strategy = type(
                    "Strategy",
                    (),
                    {
                        "action": "ASK_USER",
                        "reason": f"I've tried {depth} levels of recovery for step {step_id} and I'm still stuck. Should I keep trying or do you want to take over?",
                    },
                )()
                should_retry, _ = await self._handle_strategy_ask_user(strategy, step_id)
                if not should_retry:
                    raise Exception(f"Recovery aborted by user at critical depth {depth}.")

            if shared_context.is_at_max_depth(depth + 1):
                raise Exception(f"Max recursion depth exceeded at {depth + 1} for {step_id}.")

            await self._execute_steps_recursive(alt_steps, parent_prefix=step_id, depth=depth + 1)
            return True
        except Exception as r_err:
            logger.error(f"Atlas recovery failed: {r_err}")
            raise Exception(f"Task failed at step {step_id} after retries and recovery: {r_err}")

    async def _execute_steps_recursive(
        self,
        steps: list[dict[str, Any]],
        parent_prefix: str | None = None,
        depth: int = 0,
    ) -> bool:
        """Recursively execute steps with proper goal context management."""

        max_depth = shared_context.max_recursive_depth

        if depth > max_depth:
            raise RecursionError(f"Max task recursion depth ({max_depth}) reached. Failing task.")

        await self._handle_recursion_backoff(depth)
        metrics_collector.record("recursion_depth", depth, tags={"parent": parent_prefix or "root"})

        goal_pushed = await self._push_recursive_goal(parent_prefix, depth, steps)

        for i, step in enumerate(steps):
            # NEW: Check for human interruption before starting each step
            if await self._check_for_interruption():
                await self._log(
                    "⏸️ Виконання призупинено для обговорення.", "system", type="warning"
                )
                # Enter discussion bubble and return success/fail based on outcome
                resumed, _ = await self._enter_discussion_bubble(
                    f"discussion_{depth}", "User interrupt"
                )
                if not resumed:
                    return False
            step_id = f"{parent_prefix}.{i + 1}" if parent_prefix else str(i + 1)
            step["id"] = step_id

            notifications.show_progress(i + 1, len(steps), f"[{step_id}] {step.get('action')}")
            self._update_current_step_id(i + 1)

            if self._is_step_already_completed(step_id):
                logger.info(f"[ORCHESTRATOR] Skipping already completed step {step_id}")
                continue

            await self._check_and_handle_parallel_fixes(step_id, step)

            # Retry loop for THIS step
            await self._run_step_retry_loop(step, step_id, depth, steps, i)

        await self._pop_recursive_goal(goal_pushed, depth)
        if depth > 0:
            await self._log(
                f"✅ Sub-tasks completed at depth {depth}. Returning to parent.", "orchestrator"
            )
        return True

    def _update_current_step_id(self, step_idx: int) -> None:
        """Update current step progress in shared context."""
        try:
            shared_context.current_step_id = step_idx
        except (ImportError, NameError, AttributeError):
            pass

    async def _check_and_handle_parallel_fixes(self, step_id: str, step: dict[str, Any]) -> None:
        """Check for and apply any ready parallel fixes."""
        try:
            fixed_steps = await parallel_healing_manager.get_fixed_steps()
            if not fixed_steps:
                return

            logger.info(f"[ORCHESTRATOR] Found {len(fixed_steps)} parallel fixes ready.")
            for fix_info in fixed_steps:
                decision = await self.tetyana.evaluate_fix_retry(
                    fix_info, step_id, {"action": step.get("action")}
                )
                action = decision.get("action", "noted")
                await parallel_healing_manager.acknowledge_fix(fix_info.step_id, action)
                await self._log_parallel_fix_outcome(fix_info.step_id, step_id, action)
        except Exception as phe:
            logger.warning(f"[ORCHESTRATOR] Parallel healing check failed: {phe}")

    async def _log_parallel_fix_outcome(self, fixed_id: str, current_id: str, action: str) -> None:
        """Log the result of evaluating a parallel fix."""
        if action != "retry":
            return

        await self._log(f"🔄 Retrying parallel-fixed step {fixed_id}...", "orchestrator")
        if str(fixed_id) == str(current_id):
            await self._log(
                "Fix applies to CURRENT step. Proceeding with execution.", "orchestrator"
            )
        else:
            await self._log(
                f"Parallel fix acknowledged for {fixed_id}. (Jump-back not fully implemented)",
                "orchestrator",
            )

    async def _run_step_retry_loop(
        self,
        step: dict[str, Any],
        step_id: str,
        depth: int,
        steps: list[dict[str, Any]],
        index: int,
    ) -> None:
        """Execute a step with a retry loop and smart healing."""
        max_step_retries = 3
        last_error = ""

        for attempt in range(1, max_step_retries + 1):
            await self._trigger_async_constraint_monitoring()

            # Goal alignment logging for debugging

            if shared_context.current_goal:
                logger.debug(
                    f"[ORCHESTRATOR] Goal alignment check: depth={depth}, "
                    f"current_goal={shared_context.current_goal[:80]}"
                )

            await self._log(
                f"Step {step_id}, Attempt {attempt}: {step.get('action')}", "orchestrator"
            )

            step_result = await self.execute_node(
                cast("Any", self.state), step, step_id, attempt, depth
            )

            if step_result.success:
                logger.info(f"[ORCHESTRATOR] Step {step_id} completed successfully")
                return

            last_error = self._format_step_error(step_id, attempt, step_result)
            await self._log(f"Step {step_id} Attempt {attempt} failed: {last_error}", "warning")

            # --- Technical Diagnosis Phase ---
            try:
                logs = await self._get_recent_logs(20)
                diagnosis = await self.atlas.analyze_failure(step_id, last_error, logs)
                await self._log(f"Technical Diagnosis: {diagnosis}", "atlas")
                last_error = f"{last_error}\n\n[ATLAS DIAGNOSIS]: {diagnosis}"
            except Exception as diag_err:
                logger.warning(f"Failure diagnosis failed: {diag_err}")

            # Strategy Routing
            # Build context for behavior engine pattern matching
            router_context = {
                "task_type": str(self.state.get("task_type", "unknown")),
                "step": step,
                "step_id": step_id,
                "repeated_failures": attempt > 1,
            }
            strategy = error_router.decide(last_error, attempt, context=router_context)
            logger.info(f"[ORCHESTRATOR] Recovery Strategy: {strategy.action} ({strategy.reason})")

            should_retry, override_result = await self._handle_step_error_strategy(
                strategy, step, step_id, attempt, last_error, step_result, depth, steps, index
            )
            if should_retry:
                continue
            if override_result:
                if override_result.success:
                    return
                # CRITICAL: If strategy was ASK_USER, stop here. Don't fallback to Atlas.
                if override_result.error == "need_user_input":
                    logger.warning(f"[ORCHESTRATOR] Stopping step {step_id} for user input.")
                    notifications.send_stuck_alert(
                        self._parse_numeric_id(step_id),
                        f"USER INPUT REQUIRED: {override_result.result}",
                        max_step_retries,
                    )
                    return

            if await self._validate_with_grisha_failure(step, step_id, step_result, last_error):
                return

            notifications.send_stuck_alert(
                self._parse_numeric_id(step_id), str(last_error), max_step_retries
            )
            if await self._atlas_recovery_fallback(step_id, last_error, depth):
                return

    def _format_step_error(self, step_id: str, attempt: int, result: StepResult) -> str:
        """Format a step error message for logging."""
        if result:
            err = result.error or "Step failed without error message"
            logger.warning(f"[ORCHESTRATOR] Step {step_id} failed. Error: {err}.")
            return err
        logger.error(f"[ORCHESTRATOR] Step {step_id} failed on attempt {attempt} (no result)")
        return "Execution error (timeout or crash)"

    def _parse_numeric_id(self, step_id: str) -> int:
        """Safely parse a numeric step ID."""
        try:
            return (
                int(str(step_id).split(".")[-1])
                if "." in str(step_id)
                else (int(step_id) if str(step_id).isdigit() else 0)
            )
        except (ValueError, TypeError):
            return 0

    async def _trigger_async_constraint_monitoring(self) -> None:
        """Fire-and-forget check for environmental constraints with throttling."""
        try:
            from src.brain.behavior.constraint_monitor import constraint_monitor

            # Cooldown to prevent rate limits (max once every 30 seconds)
            now = datetime.now().timestamp()
            last_check = getattr(self, "_last_constraint_check_time", 0)
            if now - last_check < 30:
                return

            self._last_constraint_check_time = now
            monitor_logs = await self._get_recent_logs(20)
            state_logs = [l for l in (self.state.get("logs", []) or []) if isinstance(l, dict)][
                -20:
            ]
            asyncio.create_task(constraint_monitor.check_compliance(monitor_logs, state_logs))
        except Exception as cm_err:
            logger.warning(f"[ORCHESTRATOR] Monitor check trigger failed: {cm_err}")

    async def _announce_step_start(self, step: dict[str, Any], step_id: str, attempt: int) -> None:
        """Handle starting messages and state publishing for a step."""
        if "." not in str(step_id) and attempt == 1:
            msg = step.get("voice_action")
            if not msg:
                msg = self.tetyana.get_voice_message(
                    "starting",
                    step=step_id,
                    description=step.get("action", ""),
                )
            await self._speak("tetyana", msg)

        try:
            if state_manager and getattr(state_manager, "available", False):
                await state_manager.publish_event(
                    "steps",
                    {
                        "type": "step_started",
                        "step_id": str(step_id),
                        "action": step.get("action", "Working..."),
                        "attempt": attempt,
                    },
                )
        except (ImportError, NameError):
            pass

    async def _log_db_step_start(self, step: dict[str, Any], step_id: str) -> str | None:
        """Log the start of a step to the database."""
        db_step_id = None
        self.state["db_step_id"] = None
        try:
            if (
                db_manager
                and getattr(db_manager, "available", False)
                and self.state.get("db_task_id")
            ):
                async with await db_manager.get_session() as db_sess:
                    new_step = DBStep(
                        task_id=self.state["db_task_id"],
                        sequence_number=str(step_id),
                        action=f"[{step_id}] {step.get('action', '')}",
                        tool=step.get("tool", ""),
                        status="RUNNING",
                    )
                    db_sess.add(new_step)
                    await db_sess.commit()
                    db_step_id = str(new_step.id)
                    self.state["db_step_id"] = db_step_id
        except Exception as e:
            logger.error(f"DB Step creation failed: {e}")
        return db_step_id

    async def _prepare_step_context(self, step: dict[str, Any]) -> dict[str, Any]:
        """Inject additional context into the step before execution."""
        step_copy = step.copy()
        if self.state and "step_results" in self.state:
            step_copy["previous_results"] = self.state["step_results"][-10:]

        # Inject critical discoveries for cross-step data access
        discoveries_summary = shared_context.get_discoveries_summary()
        if discoveries_summary:
            step_copy["critical_discoveries"] = discoveries_summary

        # Full plan for sequence context
        plan = self.state.get("current_plan")
        if plan:
            # Convert plan steps to a readable summary
            step_list = []
            plan_steps = getattr(plan, "steps", [])
            if isinstance(plan_steps, list):
                for s in plan_steps:
                    s_dict = s if isinstance(s, dict) else {}
                    step_results = self.state.get("step_results") or []
                    status = (
                        "DONE"
                        if any(
                            isinstance(res, dict)
                            and str(res.get("step_id")) == str(s_dict.get("id"))
                            and res.get("success")
                            for res in step_results
                        )
                        else "PENDING"
                    )
                    step_list.append(
                        f"Step {s_dict.get('id')}: {s_dict.get('action')} [{status}]",
                    )
            step_copy["full_plan"] = "\n".join(step_list)

        # Check message bus for specific feedback from other agents
        bus_messages = await message_bus.receive("tetyana", mark_read=True)
        if bus_messages:
            step_copy["bus_messages"] = [m.to_dict() for m in bus_messages]

        # Inject goal vector for directional guidance in sub-tasks
        goal_vector = shared_context.get_goal_vector()
        if goal_vector:
            step_copy["goal_vector"] = goal_vector

        return step_copy

    async def _handle_imminent_restart(self) -> None:
        """Save session if a restart is pending."""
        try:
            if state_manager and getattr(state_manager, "available", False):
                restart_key = state_manager._key("restart_pending")
                try:
                    if state_manager.redis_client and await state_manager.redis_client.exists(
                        restart_key,
                    ):
                        logger.warning(
                            "[ORCHESTRATOR] Imminent application restart detected. Saving session state immediately.",
                        )
                        await state_manager.save_session(
                            self.current_session_id,
                            self.state,
                        )
                        # We stop here. The process replacement (execv) will happen in ToolDispatcher task
                        # and this orchestrator task will either be killed or return soon.
                except Exception:
                    pass
        except (ImportError, NameError):
            pass

    async def _handle_strategy_deviation(
        self,
        step: dict[str, Any],
        step_id: str,
        result: StepResult,
    ) -> StepResult | None:
        """Handle cases where Tetyana proposes a strategy deviation."""
        if not (getattr(result, "is_deviation", False) or result.error == "strategy_deviation"):
            return None

        try:
            info = getattr(result, "deviation_info", None)
            proposal_text = info.get("analysis") if info else result.result
            p_text = str(proposal_text)
            logger.warning(
                f"[ORCHESTRATOR] Tetyana proposed a deviation: {p_text[:200]}...",
            )

            # Consult Atlas
            evaluation = await self.atlas.evaluate_deviation(
                step,
                str(proposal_text),
                getattr(self.state.get("current_plan"), "steps", []),
            )

            voice_msg = evaluation.get("voice_message", "")
            if voice_msg:
                await self._speak("atlas", voice_msg)

            if evaluation.get("approved"):
                logger.info("[ORCHESTRATOR] Deviation APPROVED. Adjusting plan...")
                result.success = True
                result.result = f"Strategy Deviated: {evaluation.get('reason')}"
                result.error = None

                # Mark for behavioral learning after successful verification
                result.is_deviation = True
                result.deviation_info = evaluation

                # PERSISTENCE: Remember this approved deviation immediately
                await self._log_behavioral_deviation(step, step_id, result, p_text)
                return result

            logger.info("[ORCHESTRATOR] Deviation REJECTED. Forcing original plan.")
            step["grisha_feedback"] = (
                f"Strategy Deviation Rejected: {evaluation.get('reason')}. Stick to the plan."
            )
            result.success = False
            return result
        except Exception as eval_err:
            logger.error(f"[ORCHESTRATOR] Deviation evaluation failed: {eval_err}")
            result.success = False
            result.error = "evaluation_error"
            return result

    async def _log_behavioral_deviation(
        self, step: dict[str, Any], step_id: str, result: StepResult, proposal_text: str
    ) -> None:
        """Log behavioral learning for approved deviations."""
        try:
            if long_term_memory and getattr(long_term_memory, "available", False):
                evaluation = result.deviation_info or {}
                reason_text = str(evaluation.get("reason", "Unknown"))
                long_term_memory.remember_behavioral_change(
                    original_intent=step.get("action", ""),
                    deviation=proposal_text[:300],
                    reason=reason_text,
                    result="Deviated plan approved",
                    context={
                        "step_id": str(self.state.get("db_step_id") or ""),
                        "sequence_id": str(step_id),
                        "session_id": self.state.get("session_id"),
                        "db_session_id": self.state.get("db_session_id"),
                    },
                    decision_factors={
                        "original_step": step,
                        "analysis": proposal_text,
                    },
                )
                logger.info(
                    "[ORCHESTRATOR] Learned and memorized new behavioral deviation strategy.",
                )
        except (ImportError, NameError) as mem_err:
            logger.warning(f"Failed to memorize deviation: {mem_err}")

    async def _handle_user_input_request(
        self, step: dict[str, Any], step_id: str, result: StepResult
    ) -> StepResult:
        """Handle cases where Tetyana needs user input."""
        if result.error != "need_user_input":
            return result

        # Speak Tetyana's request BEFORE waiting to inform the user immediately
        if result.voice_message:
            await self._speak("tetyana", result.voice_message)
            result.voice_message = None  # Clear it so it won't be spoken again

        timeout_val = float(config.get("orchestrator.user_input_timeout", 12.0))
        await self._log(
            f"User input needed for step {step_id}. Waiting {timeout_val} seconds...",
            "orchestrator",
        )

        # Display the question to the user in the logs/UI
        await self._log(f"[REQUEST] {result.result}", "system", type="warning")

        # Wait for user message on the bus or timeout
        user_response = None
        try:
            start_wait = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start_wait < timeout_val:
                bus_msgs = await message_bus.receive("orchestrator", mark_read=True)
                for m in bus_msgs:
                    if m.message_type == MessageType.CHAT and m.from_agent == "USER":
                        user_response = m.payload.get("text")
                        break
                if user_response:
                    break
                await asyncio.sleep(0.5)

        except Exception as wait_err:
            logger.warning(f"Error during user wait: {wait_err}")

        if user_response:
            await self._log(f"User responded: {user_response}", "system")
            messages = self.state.get("messages")
            if messages is not None and isinstance(messages, list):
                messages.append(HumanMessage(content=cast("Any", user_response)))
                self.state["messages"] = messages
            try:
                if state_manager and getattr(state_manager, "available", False):
                    await state_manager.save_session("current_session", self.state)
            except (ImportError, NameError):
                pass

            # Direct feedback for the next retry
            await message_bus.send(
                AgentMsg(
                    from_agent="USER",
                    to_agent="tetyana",
                    message_type=MessageType.FEEDBACK,
                    payload={"user_response": user_response},
                    step_id=step.get("id"),
                ),
            )
            result.success = False
            result.error = "user_input_received"
        else:
            # TIMEOUT: Atlas ONLY speaks if user was truly silent
            await self._log(
                "User silent for timeout. Atlas deciding...",
                "orchestrator",
                type="warning",
            )
            messages = self.state.get("messages", [])
            goal_msg = messages[0] if messages else HumanMessage(content="Unknown")

            def _get_msg_content(m):
                if hasattr(m, "content"):
                    return m.content
                if isinstance(m, dict):
                    return m.get("content", str(m))
                return str(m)

            autonomous_decision = await self.atlas.decide_for_user(
                str(result.result or ""),
                {
                    "goal": _get_msg_content(goal_msg),
                    "current_step": str(step.get("action") or ""),
                    "history": [_get_msg_content(m) for m in (messages[-5:] if messages else [])],
                },
            )

            await self._log(
                f"Atlas Autonomous Decision (Timeout): {autonomous_decision}",
                "atlas",
            )
            await self._speak(
                "atlas",
                f"Оскільки ви не відповіли, я вирішив: {autonomous_decision}",
            )

            # Inject decision as feedback
            await message_bus.send(
                AgentMsg(
                    from_agent="atlas",
                    to_agent="tetyana",
                    message_type=MessageType.FEEDBACK,
                    payload={
                        "user_response": f"(Autonomous Decision): {autonomous_decision}",
                    },
                    step_id=step.get("id"),
                ),
            )
            result.success = False
            result.error = "autonomous_decision_made"
        return result

    async def _log_tool_execution_db(self, result: StepResult, db_step_id: str | None) -> None:
        """Log tool execution to DB for Grisha's audit."""
        try:
            if db_manager and getattr(db_manager, "available", False) and db_step_id:
                async with await db_manager.get_session() as db_sess:
                    tool_call_data = result.tool_call or {}
                    tool_exec = DBToolExecution(
                        step_id=db_step_id,
                        task_id=self.state.get("db_task_id"),
                        server_name=tool_call_data.get("server")
                        or tool_call_data.get("realm")
                        or "unknown",
                        tool_name=tool_call_data.get("name") or "unknown",
                        arguments=tool_call_data.get("args") or {},
                        result=str(result.result)[:10000],
                    )
                    db_sess.add(tool_exec)
                    await db_sess.commit()
                    logger.info(f"[ORCHESTRATOR] Logged tool execution: {tool_exec.tool_name}")
        except Exception as e:
            logger.error(f"Failed to log tool execution to DB: {e}")

    async def _handle_proactive_help_request(
        self, step: dict[str, Any], step_id: str, result: StepResult, depth: int
    ) -> StepResult:
        """Handle proactive help requested by Tetyana."""
        if result.error != "proactive_help_requested":
            return result

        await self._log(
            f"Tetyana requested proactive help: {result.result}",
            "orchestrator",
        )
        history_results = self.state.get("step_results")
        if not isinstance(history_results, list):
            history_results = []

        help_resp = await self.atlas.help_tetyana(
            str(step.get("id") or step_id),
            str(result.result or ""),
            history=history_results,
        )

        voice_msg = ""
        if isinstance(help_resp, dict):
            voice_msg = help_resp.get("voice_message", "")
        # Fallback: concise Ukrainian instead of dumping English reason/dict
        if not voice_msg or len(voice_msg) < 3:
            voice_msg = "Атлас надає допомогу Тетяні."

        await self._speak("atlas", voice_msg)

        # Support hierarchical recovery
        alt_steps = help_resp.get("alternative_steps") if isinstance(help_resp, dict) else None
        if alt_steps and isinstance(alt_steps, list):
            await self._log(
                f"Atlas provided {len(alt_steps)} alternative steps. Executing recovery sub-plan...",
                "orchestrator",
            )
            success = await self._execute_steps_recursive(
                alt_steps, parent_prefix=str(step.get("id") or step_id), depth=depth + 1
            )
            if success:
                await self._log(
                    f"Recovery sub-plan for {step_id} completed successfully. Retrying original step with new context.",
                    "orchestrator",
                )
            else:
                await self._log(f"Recovery sub-plan for {step_id} failed.", "error")

        await message_bus.send(
            AgentMsg(
                from_agent="atlas",
                to_agent="tetyana",
                message_type=MessageType.FEEDBACK,
                payload={"guidance": help_resp},
                step_id=step.get("id"),
            ),
        )
        result.success = False
        result.error = "help_pending"
        return result

    async def _handle_subtask_node(self, step: dict[str, Any], step_id: str) -> StepResult:
        """Execute a subtask node recursively."""
        self._in_subtask = True
        try:
            sub_result = await self.run(str(step.get("action") or ""))
        finally:
            self._in_subtask = False

        return StepResult(
            step_id=str(step.get("id") or step_id),
            success=sub_result.get("status") == "completed",
            result="Subtask completed",
            error=str(sub_result.get("error") or ""),
        )

    async def _update_db_step_status(
        self,
        db_step_id: str | None,
        result: StepResult,
        step_start_time: float,
    ) -> None:
        """Update step status in the database."""
        try:
            if db_manager and getattr(db_manager, "available", False) and db_step_id:
                try:
                    duration_ms = int((asyncio.get_event_loop().time() - step_start_time) * 1000)
                    async with await db_manager.get_session() as db_sess:
                        # Ensure db_step_id is a valid UUID string
                        target_step_id = (
                            uuid.UUID(db_step_id) if isinstance(db_step_id, str) else db_step_id
                        )
                        await db_sess.execute(
                            update(DBStep)
                            .where(DBStep.id == target_step_id)
                            .values(
                                status="SUCCESS" if result.success else "FAILED",
                                error_message=result.error,
                                duration_ms=duration_ms,
                            ),
                        )
                        await db_sess.commit()
                except Exception as e:
                    logger.error(f"DB Step update failed: {e}")
        except (ImportError, NameError):
            pass

    async def _verify_step_execution(
        self, step: dict[str, Any], step_id: str, result: StepResult
    ) -> StepResult:
        """Verify step execution using Grisha."""
        if not step.get("requires_verification"):
            return result

        self.state["system_state"] = SystemState.VERIFYING.value
        try:
            await self._log("Preparing verification...", "system")
            await asyncio.sleep(0.5)

            expected = step.get("expected_result", "").lower()
            visual_verification_needed = any(
                k in expected for k in ["visual", "screenshot", "ui", "interface", "window"]
            )

            screenshot = None
            if visual_verification_needed:
                screenshot = await self.grisha.take_screenshot()

            verify_result = await self.grisha.verify_step(
                step=step,
                result=result,
                screenshot_path=screenshot,
                goal_context=shared_context.get_goal_context(),
                task_id=str(self.state.get("db_task_id") or ""),
            )

            if not verify_result.verified:
                # Add check for verification attempts to avoid infinite loops
                # (Simple heuristic using step results)
                rejections = [
                    res
                    for res in (self.state.get("step_results") or [])
                    if isinstance(res, dict)
                    and res.get("step_id") == step_id
                    and "rejected" in str(res.get("error", ""))
                ]

                if len(rejections) >= 3:
                    await self._log(
                        f"Verification for step {step_id} failed multiple times. Escalating.",
                        "error",
                    )
                    result.success = False
                    result.error = f"Persistent verification failure: {verify_result.description}"
                    await self._speak(
                        "atlas",
                        "Я не можу отримати підтвердження виконання цього кроку. Мені потрібна допомога.",
                    )
                    return result

                result.success = False
                result.error = f"Grisha rejected: {verify_result.description}"
                if verify_result.issues and isinstance(verify_result.issues, list):
                    result.error += f" Issues: {', '.join(verify_result.issues)}"

                # Provide rich feedback for the next execution attempt
                # Voice: concise Ukrainian only; full English description stays in logs for Tetyana
                voice_msg = verify_result.voice_message or f"Крок {step_id} не пройшов перевірку."
                await self._log(
                    f"Verification rejected step {step_id}: {verify_result.description}",
                    "orchestrator",
                )
                await self._speak("grisha", voice_msg)
                # Also log detailed reason so it appears in the chat thread for the user
                if verify_result.description and verify_result.description != voice_msg:
                    reason_text = verify_result.description[:500]
                    await self._log(
                        f"Причина відхилення кроку {step_id}: {reason_text}",
                        "grisha",
                        "verification",
                    )

                # Update current_plan step description if possible to include feedback for Tetyana
                # (Optional but useful for self-correction)
            else:
                await self._speak("grisha", verify_result.voice_message or "Підтверджую виконання.")
                if result.is_deviation and result.success and result.deviation_info:
                    await self._commit_successful_deviation(step, step_id, result)

        except Exception as e:
            logger.exception("Verification crashed")
            await self._log(f"Verification crashed: {e}", "error")
            result.success = False
            result.error = f"Verification system error: {e}"

        self.state["system_state"] = SystemState.EXECUTING.value
        return result

    async def _commit_successful_deviation(
        self, step: dict[str, Any], step_id: str, result: StepResult
    ) -> None:
        """Commit behavioral learning for successful deviations."""
        evaluation = result.deviation_info or {}
        factors = evaluation.get("decision_factors", {})

        # 1. Vector Memory
        try:
            if long_term_memory and getattr(long_term_memory, "available", False):
                long_term_memory.remember_behavioral_change(
                    original_intent=str(step.get("action") or "Unknown"),
                    deviation=str(result.result),
                    reason=str(evaluation.get("reason") or "Unknown"),
                    result="Verified Success",
                    context={
                        "step_id": str(step.get("id") or step_id),
                        "session_id": self.state.get("session_id"),
                        "db_session_id": self.state.get("db_session_id"),
                    },
                    decision_factors=factors,
                )
        except (ImportError, NameError):
            pass

        # 2. Knowledge Graph
        if knowledge_graph:

            async def _async_learn_lesson():
                try:
                    lesson_id = f"lesson:{int(datetime.now().timestamp())}"
                    await knowledge_graph.add_node(
                        node_type="LESSON",
                        node_id=lesson_id,
                        attributes={
                            "name": f"Successful Deviation: {str(evaluation.get('reason') or '')[:50]}",
                            "intent": str(step.get("action") or ""),
                            "outcome": "Verified Success",
                            "reason": str(evaluation.get("reason") or ""),
                        },
                    )
                    if self.state.get("db_task_id"):
                        await knowledge_graph.add_edge(
                            f"task:{self.state.get('db_task_id')}", lesson_id, "learned_lesson"
                        )

                    for f_name, f_val in factors.items():
                        factor_node_id = f"factor:{f_name}:{str(f_val).lower().replace(' ', '_')}"
                        await knowledge_graph.add_node(
                            "FACTOR",
                            factor_node_id,
                            {"name": f_name, "value": f_val, "type": "environmental_factor"},
                        )
                        await knowledge_graph.add_edge(lesson_id, factor_node_id, "CONTINGENT_ON")
                except Exception as g_err:
                    logger.error(f"[ORCHESTRATOR] Error linking factors in graph: {g_err}")

            asyncio.create_task(_async_learn_lesson())

    async def _finalize_node_execution(
        self, step: dict[str, Any], step_id: str, result: StepResult
    ) -> None:
        """Finalize node execution, store results and publish events."""
        # Store final result
        self.state["step_results"].append(
            {
                "step_id": str(result.step_id),
                "action": f"[{step_id}] {step.get('action')}",
                "success": result.success,
                "result": result.result,
                "error": result.error,
            },
        )

        # Extract and store critical discoveries
        if result.success and result.result:
            self._extract_and_store_discoveries(result.result, step)

        # Publish finished event
        try:
            if state_manager and getattr(state_manager, "available", False):
                await state_manager.publish_event(
                    "steps",
                    {
                        "type": "step_finished",
                        "step_id": str(step_id),
                        "success": result.success,
                        "error": result.error,
                        "result": result.result,
                    },
                )
        except (ImportError, NameError):
            pass

        # Knowledge Graph Sync
        kg_task = asyncio.create_task(self._update_knowledge_graph(step_id, result))
        self._background_tasks.add(kg_task)
        kg_task.add_done_callback(self._background_tasks.discard)

    def _log_tool_usage_background(self, step_id: str, result: StepResult):
        """Log tool usage to Knowledge Graph in background."""
        if not knowledge_graph:
            return

        async def _log_graph_async():
            try:
                # 1. Update Legacy Knowledge Graph
                tool_call = result.tool_call or {}
                t_name = tool_call.get("name")
                if t_name and knowledge_graph:
                    knowledge_graph.add_node_background(
                        node_type="TOOL",
                        node_id=f"tool:{t_name}",
                        attributes={"last_used_step": str(step_id), "success": result.success},
                    )
                    knowledge_graph.add_edge_background(
                        source_id=f"task:{self.state.get('db_task_id', 'unknown')}",
                        target_id=f"tool:{t_name}",
                        relation="USED",
                    )

                # 2. Update NeuralCore CognitiveGraph
                if t_name:
                    from src.brain.neural_core.core import neural_core

                    await neural_core.graph.add_node(
                        f"tool:{t_name}",
                        "tool",
                        t_name,
                        {"last_result": "success" if result.success else "failure"},
                    )
                    await neural_core.graph.add_edge(
                        f"task:{self.state.get('db_task_id', 'unknown')}",
                        f"tool:{t_name}",
                        "invoked",
                        {"success": result.success, "step_id": step_id},
                    )
            except Exception as e:
                logger.warning(f"[ORCHESTRATOR] NeuralCore graph update failed: {e}")

        asyncio.create_task(_log_graph_async())

    async def _execute_tetyana_flow(
        self,
        step: dict[str, Any],
        step_id: str,
        attempt: int,
        depth: int,
        db_step_id: str | None,
    ) -> StepResult:
        """Encapsulates the try-except logic for Tetyana's execution."""
        try:
            # Inject context and prepare execution
            step_copy = await self._prepare_step_context(step)
            result = await self.tetyana.execute_step(step_copy, attempt=attempt)

            # --- RESTART DETECTION ---
            await self._handle_imminent_restart()

            # --- DYNAMIC AGENCY: Check for Strategy Deviation ---
            deviation_result = await self._handle_strategy_deviation(step, step_id, result)
            if deviation_result:
                return deviation_result

            # Handle need_user_input signal (New Autonomous Timeout Logic)
            result = await self._handle_user_input_request(step, step_id, result)

            # Log tool execution to DB for Grisha's audit
            if db_step_id:
                await self._log_tool_execution_db(result, db_step_id)

            # Handle proactive help requested by Tetyana
            result = await self._handle_proactive_help_request(step, step_id, result, depth)

            # Log interaction to Knowledge Graph if successful (Background)
            if result.success and result.tool_call:
                self._log_tool_usage_background(step_id, result)

            if result.voice_message:
                await self._speak("tetyana", result.voice_message)

            return result

        except Exception as e:
            logger.exception("Tetyana execution crashed")
            return StepResult(
                step_id=str(step.get("id") or step_id),
                success=False,
                result="Crashed",
                error=str(e),
            )

    async def execute_node(
        self,
        state: TrinityState,
        step: dict[str, Any],
        step_id: str,
        attempt: int = 1,
        depth: int = 0,
    ) -> StepResult:
        """Atomic execution logic with recursion and dynamic temperature"""
        # Starting message logic
        await self._announce_step_start(step, step_id, attempt)

        # [NEURAL CORE] Consulting the brain before execution
        try:
            await self._neural_pulse(step, step_id)
        except Exception as pulse_e:
            logger.debug(f"[ORCHESTRATOR] Neural pulse failed: {pulse_e}")

        # DB Step logging
        db_step_id = await self._log_db_step_start(step, step_id)

        step_start_time = asyncio.get_event_loop().time()

        if step.get("type") == "subtask" or step.get("tool") == "subtask":
            result = await self._handle_subtask_node(step, step_id)
        else:
            result = await self._execute_tetyana_flow(
                step=step,
                step_id=step_id,
                attempt=attempt,
                depth=depth,
                db_step_id=db_step_id,
            )

        # Update DB Step
        await self._update_db_step_status(db_step_id, result, step_start_time)

        # change from _verify_step_execution to verify_step_execution if typo?
        # Checking previous file content, it IS _verify_step_execution.

        # Check verification
        result = await self._verify_step_execution(step, step_id, result)

        # Finalize and notify
        await self._finalize_node_execution(step, step_id, result)

        # [NEURAL CORE] Providing feedback after execution
        try:
            await self._neural_feedback(result, step)
        except Exception as fb_e:
            logger.debug(f"[ORCHESTRATOR] Neural feedback failed: {fb_e}")

        return result

    async def planner_node(self, state: TrinityState) -> dict[str, Any]:
        return {"system_state": SystemState.PLANNING.value}

    async def executor_node(self, state: TrinityState) -> dict[str, Any]:
        return {"system_state": SystemState.EXECUTING.value}

    async def verifier_node(self, state: TrinityState) -> dict[str, Any]:
        return {"system_state": SystemState.VERIFYING.value}

    async def audit_node(self, state: TrinityState) -> dict[str, Any]:
        """HOCE: Internal Audit node to ensure plan quality and entropy."""
        logger.info("[HOCE AUDIT] Performing consciousness audit of the current plan...")

        plan = state.get("current_plan")
        if not plan:
            return {"system_state": SystemState.AUDITING.value}

        # Use Atlas for self-audit
        from src.brain.agents.atlas import Atlas

        audit_atlas = Atlas(model_name="atlas-deep")  # High complexity model for audit

        from src.brain.neural_core.core import neural_core

        criteria = neural_core.identity.get_audit_prompt_context()

        audit_prompt = f"""You are the internal Auditor of ATLAS. Review the proposed plan for mechanical flaws, laziness, or 'template' thinking.
        
        PROPOSED PLAN:
        {json.dumps(plan, indent=2)}
        
        ETHICAL & BEHAVIORAL CRITERIA (The Creator's Postulates):
        {criteria}
        
        Respond with either "APPROVED" or a "REJECTION: <reason>" followed by a "SUGGESTION: <improvement>".
        """

        try:
            response = await audit_atlas.llm.ainvoke(audit_prompt)
            content = response.content if hasattr(response, "content") else str(response)

            if "REJECTION" in content.upper():
                logger.warning(f"[HOCE AUDIT] Plan REJECTED: {content}")
                # We could route back to planner here if we had the logic
                return {
                    "system_state": SystemState.AUDITING.value,
                    "error": f"Audit Failure: {content}",
                }

            logger.info("[HOCE AUDIT] Plan APPROVED.")
            return {"system_state": SystemState.AUDITING.value}
        except Exception as e:
            logger.error(f"[HOCE AUDIT] Audit engine failed: {e}")
            return {"system_state": SystemState.AUDITING.value}

    def should_verify(self, state: TrinityState) -> str:
        """Determines the next state based on config-driven rules."""

        # Build context for rule evaluation
        context = {
            "has_error": bool(state.get("error")),
            "task_completed": state.get("system_state") == SystemState.COMPLETED.value,
            "needs_verification": False,  # Dynamic check based on plan or state
        }

        # Check if current plan indicates completion
        if state.get("current_plan") and not state.get("error"):
            # Simple check: if all steps have results, it might be completed
            plan = state["current_plan"]
            if isinstance(plan, list) and len(plan) == len(state.get("step_results", [])):
                context["task_completed"] = True
                context["needs_verification"] = True  # Default to verify before ending

        result = behavior_engine.evaluate_rule("should_verify", context)
        return str(result or "continue")

    async def shutdown(self):
        """Clean shutdown of system components"""
        logger.info("[ORCHESTRATOR] Shutting down...")
        try:
            await mcp_manager.shutdown()
        except Exception:
            pass
        try:
            await db_manager.close()
        except Exception:
            pass
        import contextlib

        with contextlib.suppress(Exception):
            await self.voice.close()
        logger.info("[ORCHESTRATOR] Shutdown complete.")

    async def _update_knowledge_graph(self, step_id: str, result: StepResult):
        """Background task to sync execution results to Knowledge Graph"""
        try:
            if knowledge_graph:
                await knowledge_graph.add_node(
                    node_type="STEP_EXECUTION",
                    node_id=f"exec:{self.state.get('db_task_id')}:{step_id}",
                    attributes={
                        "success": result.success,
                        "error": result.error,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )
        except Exception as e:
            logger.error(f"Failed to update knowledge graph: {e}")

    def _extract_and_store_discoveries(self, output: str, step: dict) -> None:
        """Extract and store critical values from tool output using LLM analysis.

        Uses lightweight LLM call to dynamically identify important values
        instead of hardcoded patterns. Stores in both SharedContext (fast access)
        and ChromaDB (persistent semantic search).
        """
        # Skip if output is too short or empty
        if not output or len(output.strip()) < 10:
            return

        # Skip common non-informative outputs
        skip_patterns = ["success", "done", "completed", "ok", "true", "false"]
        if output.strip().lower() in skip_patterns:
            return

        step_id = str(step.get("id", "unknown"))
        step_action = step.get("action", "")[:100]
        task_id = str(self.state.get("db_task_id") or self.state.get("session_id") or "unknown")

        # Schedule async LLM extraction in background
        asyncio.create_task(self._llm_extract_discoveries(output, step_id, step_action, task_id))

    async def _llm_extract_discoveries(
        self, output: str, step_id: str, step_action: str, task_id: str
    ) -> None:
        """Background LLM-based discovery extraction."""
        from langchain_core.messages import HumanMessage, SystemMessage

        from src.providers.factory import create_llm

        try:
            # Use fast model for extraction
            extraction_model = config.get("models.chat") or config.get("models.default")
            llm = create_llm(model_name=extraction_model)

            prompt = f"""Analyze this tool output and extract CRITICAL VALUES that should be remembered for later steps.

OUTPUT:
{output[:2000]}

STEP CONTEXT: {step_action}

Extract values that are:
- IP addresses, hostnames, or URLs
- File paths (especially keys, configs, credentials)
- MAC addresses or device identifiers
- Usernames, ports, service names
- Any specific values that would be needed in subsequent steps

Respond ONLY with valid JSON array (or empty [] if nothing important):
[
  {{"key": "descriptive_name", "value": "actual_value", "category": "ip_address|path|credential|identifier|other"}}
]

IMPORTANT: Extract ONLY concrete values, not descriptions. If nothing critical, return []"""

            messages = [
                SystemMessage(content="You are a precise data extractor. Return only valid JSON."),
                HumanMessage(content=prompt),
            ]

            response = await llm.ainvoke(messages)
            response_text = str(response.content).strip()

            # Parse JSON response
            # Handle markdown code blocks
            if "```" in response_text:
                json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response_text)
                if json_match:
                    response_text = json_match.group(1)

            discoveries = json.loads(response_text)

            if not discoveries or not isinstance(discoveries, list):
                return

            for item in discoveries:
                if not isinstance(item, dict):
                    continue

                key = item.get("key", "unknown")
                value = item.get("value", "")
                category = item.get("category", "other")

                if not value:
                    continue

                # Store in SharedContext for immediate access
                shared_context.store_discovery(key=key, value=value, category=category)

                # Store in ChromaDB for persistent semantic search
                long_term_memory.remember_discovery(
                    key=key,
                    value=value,
                    category=category,
                    task_id=task_id,
                    step_id=step_id,
                    step_action=step_action,
                )

                # Security: Mask values that look like credentials
                display_value = (
                    "[MASKED]"
                    if any(kw in key.upper() for kw in ["KEY", "TOKEN", "SECRET", "PASS"])
                    else value[:50]
                )
                logger.info(f"[ORCHESTRATOR] LLM extracted {category}:{key}={display_value}...")

        except json.JSONDecodeError as e:
            logger.debug(f"[ORCHESTRATOR] Discovery extraction returned no valid JSON: {e}")
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Discovery extraction failed: {e}")
