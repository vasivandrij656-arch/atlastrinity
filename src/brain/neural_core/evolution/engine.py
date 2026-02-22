"""
EvolutionEngine: The Autonomous Growth Mechanism of NeuralCore.
Analyzes cognitive patterns and optimizes the system during idle periods.
"""

import asyncio
import logging
from typing import Any, Optional

from src.brain.agents import Atlas
from src.brain.neural_core.chronicle import kyiv_chronicle
from src.brain.neural_core.memory.graph import cognitive_graph

logger = logging.getLogger("brain.neural_core.evolution")


class EvolutionEngine:
    def __init__(self):
        self.optimizer = Atlas(model_name="atlas-deep")
        self._running = False

    async def run_optimization_cycle(self):
        """
        Runs a comprehensive optimization cycle.
        1. Syncs absolute time (Kyiv).
        2. Analyzes recent cognitive patterns.
        3. Proposes evolutionary patches.
        """
        logger.info("[EVOLUTION] Starting autonomous growth cycle...")

        # 1. Aura of Presence (Time Sync)
        await kyiv_chronicle.sync_time()

        # 2. Pattern Analysis
        # We fetch nodes from the CognitiveGraph (recent sessions/lessons)
        try:
            # For now, let's just simulate the analysis as we need more graph data
            # In a mature system, this would query causality chains
            prompt = f"""
            Analyze current cognitive state:
            Current Kyiv Time: {kyiv_chronicle.get_iso_now()}
            
            Based on recent lessons and behaviors, what structural optimizations can be made to ATLAS?
            Focus on:
            - Reducing "Cognitive Friction" (redundant tool calls).
            - Strengthening the "Entropy Manifesto" adherence.
            - Improving response latency for the Creator (Oleg Mykolayovych).
            
            Respond with a "Cognitive Insight" and a proposed action.
            """

            response = await self.optimizer.llm.ainvoke(prompt)
            insight = response.content if hasattr(response, "content") else str(response)

            logger.info(f"[EVOLUTION] Cognitive Insight Generated: {insight[:100]}...")

            # 3. Future: Integration with Vibe-MCP for automatic patching
            # await mcp_manager.call_tool("vibe", "apply_optimization", {"insight": insight})

        except Exception as e:
            logger.error(f"[EVOLUTION] Growth cycle failed: {e}")

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
