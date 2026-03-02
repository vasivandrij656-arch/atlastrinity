"""AtlasTrinity Consolidation Module

Sleep & Consolidation - Nightly learning process that:
1. Reads audit logs
2. Extracts patterns using LLM
3. Compresses into lessons for ChromaDB
"""

import os
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from src.brain.agents.atlas import Atlas
from src.brain.memory import long_term_memory
from src.brain.memory.db.manager import db_manager
from src.brain.monitoring.logger import logger


class ConsolidationModule:
    """Handles nightly learning and memory consolidation.

    Based on TDD spec:
    - Trigger: Scheduled (03:00 AM) or idle > 2 hours
    - Process: Read logs -> LLM analysis -> Extract rules -> Update ChromaDB
    """

    def __init__(self) -> None:
        self.last_consolidation: datetime | None = None
        self.idle_threshold = timedelta(hours=2)
        self.log_path = os.path.join(os.path.expanduser("~/.config/atlastrinity/logs"), "brain.log")

    async def consolidate_immediate(self, task_state: dict[str, Any]) -> dict[str, Any] | None:
        """Immediately distills a lesson from a critical failure (triggered by high cortisol)."""
        logger.info("[CONSOLIDATION] Triggering immediate consolidation for critical failure...")
        
        try:
            from src.brain.agents.atlas import Atlas
            from src.brain.config.config_loader import config

            consolidation_model = config.get("models", {}).get("consolidation") or config.get(
                "models", {}
            ).get("default", "")
            
            atlas = Atlas(model_name=consolidation_model)
            llm = atlas.llm
            
            # Prepare recent task data from state for context
            steps = task_state.get("step_results", [])
            recent_steps = steps[-3:] if steps else []
            
            task_data = {
                "goal": task_state.get("_theme", "Current Task"),
                "status": "FAILED",
                "steps": [
                    {
                        "action": s.get("action") or s.get("tool", "unknown"),
                        "status": s.get("status", "FAILED"),
                        "error": s.get("error", "Unknown error")
                    } for s in recent_steps
                ]
            }
            
            lesson = await self._distill_lesson_via_llm(llm, task_data)
            if lesson:
                success = long_term_memory.remember_error(
                    error=lesson["error"],
                    solution=lesson["rule"],
                    context=task_data,
                    task_description=str(task_data["goal"]),
                )
                if success:
                    logger.info(f"[CONSOLIDATION] Immediate lesson learned: {lesson['error']}")
                    return lesson
        except Exception as e:
            logger.error(f"[CONSOLIDATION] Immediate consolidation failed: {e}")
        return None

    async def run_consolidation(self, llm=None) -> dict[str, Any]:
        """Main consolidation process using DB data and LLM."""
        from src.brain.memory.db.manager import db_manager

        if not db_manager.available:
            logger.warning("[CONSOLIDATION] DB unavailable, skipping.")
            return {"error": "DB unavailable"}

        logger.info("[CONSOLIDATION] Starting structured memory consolidation...")

        try:
            # 1. Fetch recent tasks (last 24h)
            cutoff = datetime.now(UTC) - timedelta(hours=24)
            tasks_data = await self._fetch_tasks_from_db(cutoff)
            logger.info(f"[CONSOLIDATION] Fetched {len(tasks_data)} tasks from DB")

            if not tasks_data:
                return {"message": "No new tasks to consolidate"}

            # 2. LLM Analysis (Batch or individual)
            # We'll use the provided LLM or a default Atlas instance
            if llm:
                atlas = Atlas(model_name=llm)
            else:
                # Use consolidation model from config (fallback to default)
                from src.brain.config.config_loader import config

                consolidation_model = config.get("models", {}).get("consolidation") or config.get(
                    "models",
                    {},
                ).get("default", "")
                atlas = Atlas(model_name=consolidation_model)
                llm = atlas.llm

            # 2. LLM Analysis for Failures
            lessons_added = 0
            for task in [t for t in tasks_data if t["status"] == "FAILED"]:
                lesson = await self._distill_lesson_via_llm(llm, task)
                if lesson and long_term_memory.remember_error(
                    error=lesson["error"],
                    solution=lesson["rule"],
                    context=task,
                    task_description=task["goal"],
                ):
                    lessons_added += 1

            # 3. SUCCESS SYNTHESIS (HOCE Upgrade)
            strategies_added = 0
            successful_tasks = [t for t in tasks_data if t["status"] == "COMPLETED"]
            if len(successful_tasks) >= 3:
                # Group by similar goals to find patterns
                new_strategies = await self._synthesize_strategies_via_llm(llm, successful_tasks)
                for strategy in new_strategies:
                    if long_term_memory.remember_strategy(
                        task=strategy["goal_pattern"],
                        plan_steps=strategy["steps"],
                        outcome=strategy["impact"],
                        success=True,
                    ):
                        strategies_added += 1

            self.last_consolidation = datetime.now(UTC)

            stats = {
                "timestamp": self.last_consolidation.isoformat(),
                "tasks_processed": len(tasks_data),
                "lessons_added": lessons_added,
                "strategies_synthesized": strategies_added,
                "memory_stats": long_term_memory.get_stats(),
            }

            logger.info(
                f"[CONSOLIDATION] Complete: {lessons_added} lessons, {strategies_added} strategies synthesized.",
            )
            return stats

        except Exception as e:
            logger.error(f"[CONSOLIDATION] Failed: {e}")
            return {"error": str(e)}

    async def _fetch_tasks_from_db(self, cutoff: datetime) -> list[dict[str, Any]]:
        """Fetch tasks and their steps from the configured SQL database (SQLite by default)."""
        from sqlalchemy import select

        from src.brain.memory.db.schema import Task as DBTask
        from src.brain.memory.db.schema import TaskStep as DBStep

        results = []
        async with await db_manager.get_session() as session:
            stmt = select(DBTask).where(DBTask.created_at > cutoff)
            res = await session.execute(stmt)
            tasks = res.scalars().all()

            for task in tasks:
                # Load steps
                step_stmt = (
                    select(DBStep).where(DBStep.task_id == task.id).order_by(DBStep.sequence_number)
                )
                step_res = await session.execute(step_stmt)
                steps = step_res.scalars().all()

                results.append(
                    {
                        "id": str(task.id),
                        "goal": task.goal,
                        "status": task.status,
                        "steps": [
                            {
                                "action": s.action,
                                "status": s.status,
                                "error": s.error_message,
                            }
                            for s in steps
                        ],
                    },
                )
        return results

    async def _synthesize_strategies_via_llm(
        self,
        llm,
        successful_tasks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Uses LLM to find common patterns in successful tasks and create reusable strategies."""
        import json

        from langchain_core.messages import HumanMessage, SystemMessage

        task_summaries = "\n".join(
            [f"- {t['goal']}: {len(t['steps'])} steps taken" for t in successful_tasks]
        )

        prompt = f"""Review these successful tasks and identify 1-2 'High-Level Strategies' (sequences of actions) that can be generalized.
        
        SUCCESSFUL TASKS:
        {task_summaries}

        Respond in JSON (a list of objects):
        [
            {{
                "goal_pattern": "Generalized description of the task type (English)",
                "steps": ["Step 1 description", "Step 2 description"],
                "impact": "Why this sequence is efficient (English)"
            }}
        ]
        """

        try:
            response = await llm.ainvoke(
                [
                    SystemMessage(content="You are a Strategy Synthesis Expert for ATLAS."),
                    HumanMessage(content=prompt),
                ],
            )
            content = response.content if hasattr(response, "content") else str(response)
            start = content.find("[")
            end = content.rfind("]") + 1
            return cast("list[dict[str, Any]]", json.loads(content[start:end]))
        except Exception as e:
            logger.warning(f"Strategy synthesis failed: {e}")
            return []

    async def _distill_lesson_via_llm(
        self,
        llm,
        task_data: dict[str, Any],
    ) -> dict[str, str] | None:
        """Uses LLM to turn a failure into a generalized rule/lesson."""
        import json

        from langchain_core.messages import HumanMessage, SystemMessage

        "\n".join(
            [f"- {s['action']}: {s['status']} (Error: {s['error']})" for s in task_data["steps"]],
        )

        prompt = """Analyze this failed task and extract a general 'Lesson' to prevent this in the future.

        TASK: {task_data['goal']}
        EXECUTION:
        {history}

        Respond in JSON:
        {
            "error": "The core technical reason for failure (English)",
            "rule": "Generalized rule or best practice to avoid this next time (English)",
            "analysis": "Technical analysis in English",
            "identity_resonance": "Brief reflection on how ATLAS's persona or worldview evolved during this task (English)"
        }
        """

        try:
            response = await llm.ainvoke(
                [
                    SystemMessage(content="You are a Memory Consolidation Expert."),
                    HumanMessage(content=prompt),
                ],
            )
            content = response.content if hasattr(response, "content") else str(response)
            # Basic JSON extraction
            start = content.find("{")
            end = content.rfind("}") + 1
            return cast("dict[str, str] | None", json.loads(content[start:end]))
        except Exception as e:
            logger.warning(f"LLM Lesson distillation failed: {e}")
            return None

    def should_consolidate(self, last_activity: datetime | None = None) -> bool:
        """Check if consolidation should run."""
        now = datetime.now(UTC)

        # Never consolidated
        if not self.last_consolidation:
            return True

        # Been more than 24 hours
        if now - self.last_consolidation > timedelta(hours=24):
            return True

        # Idle for 2+ hours
        if last_activity and now - last_activity > self.idle_threshold:
            return True

        # Nighttime (3 AM)
        return bool(now.hour == 3 and (now - self.last_consolidation).total_seconds() > 3600)


# Singleton instance
consolidation_module = ConsolidationModule()
