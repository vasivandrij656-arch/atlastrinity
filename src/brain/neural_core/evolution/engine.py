"""
EvolutionEngine: The Autonomous Growth Mechanism of NeuralCore.
Analyzes cognitive patterns and optimizes the system during idle periods.
"""

import asyncio
import logging
from typing import Optional

from src.brain.agents import Atlas
from src.brain.neural_core.chronicle import kyiv_chronicle
from src.brain.neural_core.memory.graph import cognitive_graph

from .prompt_tuner import prompt_tuner

logger = logging.getLogger("brain.neural_core.evolution")


class EvolutionEngine:
    def __init__(self):
        self.optimizer = Atlas(model_name="atlas-deep")
        self._running = False

    async def run_optimization_cycle(self, direction: str | None = None, deep_dive: bool = False):
        """
        Runs a comprehensive optimization cycle.
        1. Syncs absolute time (Kyiv).
        2. Analyzes recent cognitive patterns or follows a specific direction.
        3. Proposes evolutionary patches or prompt migrations.
        4. If deep_dive is True, performs a thorough research cycle.
        """
        logger.info(
            f"[EVOLUTION] Starting growth cycle (Direction: {direction or 'Autonomous'}, DeepDive: {deep_dive})..."
        )

        # 1. Aura of Presence (Time Sync)
        await kyiv_chronicle.sync_time()

        # 2. Pattern Analysis
        try:
            target_focus = (
                f"Focus on: {direction}"
                if direction
                else """Focus on:
            - Reducing "Cognitive Friction" (redundant tool calls).
            - Strengthening the "Entropy Manifesto" adherence.
            - Improving response latency for the Creator (Oleg Mykolayovych)."""
            )

            prompt = f"""
            Analyze current cognitive state:
            Current Kyiv Time: {kyiv_chronicle.get_iso_now()}
            
            Based on recent lessons, behaviors, or the specific direction provided, what structural optimizations can be made to ATLAS?
            
            {target_focus}
            
            Respond with a "Cognitive Insight" and a proposed action (e.g., a Vibe patch or a behavioral shift).
            """

            response = await self.optimizer.llm.ainvoke(prompt)
            insight = response.content if hasattr(response, "content") else str(response)

            logger.info(f"[EVOLUTION] Cognitive Insight Generated: {insight[:100]}...")

            # Record insight in graph
            await cognitive_graph.add_node(
                f"insight_{kyiv_chronicle.get_iso_now()}",
                "insight",
                "Evolutionary Insight",
                {"text": insight, "direction": direction or "autonomous", "is_deep": deep_dive},
            )

            # 3. Reflexive Prompt Tuning (RPT)
            if not direction or "prompt" in direction.lower():
                proposal = await prompt_tuner.analyze_and_propose()
                if proposal:
                    # Save proposal as a system-generated artifact or log
                    logger.info("[EVOLUTION] Prompt tuning proposal generated. Review required.")
                    # In a real scenario, this would create a file for user review

            # 4. Deep Dive (AKI)
            if deep_dive:
                await self._perform_deep_dive(insight)

        except Exception as e:
            logger.error(f"[EVOLUTION] Growth cycle failed: {e}")

    async def _perform_deep_dive(self, context: str):
        """AKI: Autonomous Knowledge Ingestion."""
        logger.info("[EVOLUTION] Performing AKI Deep Dive...")
        # Placeholder for complex tool-driven research (e.g. searching docs, analyzing new repos)
        # This will be fully implemented as specific research tasks are identified.

    async def propose_system_patch(self, issue_description: str) -> str:
        """Generates a Vibe-targeted patch for a system issue."""
        prompt = f"""
        As the EvolutionEngine of ATLAS, analyze the following system issue and propose a high-precision code patch.
        ISSUE: {issue_description}
        
        Provide the patch in Vibe-implementation format (instruction + target file + diff).
        """
        response = await self.optimizer.llm.ainvoke(prompt)
        return response.content if hasattr(response, "content") else str(response)

    def start_background_loop(self, interval_hours: int = 6):
        """Starts the background evolution loop."""
        if self._running:
            return

        self._running = True

        async def loop():
            while self._running:
                await self.run_optimization_cycle()
                await asyncio.sleep(interval_hours * 3600)

        asyncio.create_task(loop())
        logger.info(f"[EVOLUTION] Background growth loop started (interval: {interval_hours}h).")


# Global instance
evolution_engine = EvolutionEngine()
