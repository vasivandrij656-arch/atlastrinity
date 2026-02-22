"""
EvolutionEngine: The Autonomous Growth Mechanism of NeuralCore.
Analyzes cognitive patterns and optimizes the system during idle periods.
"""

import asyncio
import json
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
        5. Executes Entropy Manifesto (Associative Link Search).
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
                    logger.info("[EVOLUTION] Prompt tuning proposal generated. Review required.")

            # 4. Deep Dive (AKI)
            if deep_dive:
                await self._perform_deep_dive(insight)

            # 5. Entropy Manifesto
            await self._run_entropy_manifesto()

            # 6. Dynamic Protocol Adaptation
            if "protocol" in str(insight).lower():
                await self.propose_dynamic_protocol(insight)

        except Exception as e:
            logger.error(f"[EVOLUTION] Growth cycle failed: {e}")

    async def _run_entropy_manifesto(self):
        """Associative Memory Link Search: Finding non-obvious causal links."""
        logger.info("[EVOLUTION] Running Entropy Manifesto...")
        # Randomly select a few nodes and find commonalities or missing links
        nodes = await cognitive_graph.search_nodes(limit=30)
        if len(nodes) < 2:
            return

        prompt = f"""
        ENTROPY MANIFESTO: Phase Associative Link.
        Identify hidden patterns or non-obvious causal links between these cognitive nodes:
        {json.dumps([{'id': n['id'], 'label': n['label']} for n in nodes[:5]])}
        
        Extract one 'Associative Insight' that could simplify complex task orchestration.
        """
        try:
            response = await self.optimizer.llm.ainvoke(prompt)
            await cognitive_graph.add_node(
                f"entropy_{kyiv_chronicle.get_iso_now()}",
                "insight",
                "Entropy Associative Insight",
                {"text": response.content},
            )
        except Exception as e:
            logger.error(f"[EVOLUTION] Entropy Manifesto failed: {e}")

    async def _perform_deep_dive(self, context: str):
        """AKI: Autonomous Knowledge Ingestion."""
        logger.info("[EVOLUTION] Performing AKI Deep Dive...")
        # Placeholder for complex tool-driven research (e.g. searching docs, analyzing new repos)
        # This will be fully implemented as specific research tasks are identified.

    async def propose_dynamic_protocol(self, insight: str):
        """Generates proposals for new or updated MCP tool schemas."""
        logger.info("[EVOLUTION] Analyzing Dynamic Protocol Adaptation...")
        prompt = f"""
        Based on this Evolutionary Insight: {insight}
        Propose a new or updated MCP tool schema (JSON) that would improve system efficiency.
        Respond with ONLY the schema or 'None'.
        """
        try:
            response = await self.optimizer.llm.ainvoke(prompt)
            if "none" not in response.content.lower():
                await cognitive_graph.add_node(
                    f"protocol_{kyiv_chronicle.get_iso_now()}",
                    "protocol",
                    "Dynamic Protocol Proposal",
                    {"schema": response.content},
                )
        except Exception as e:
            logger.error(f"[EVOLUTION] Protocol adaptation failed: {e}")

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
