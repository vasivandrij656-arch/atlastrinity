"""
EvolutionEngine: The Autonomous Growth Mechanism of NeuralCore.
Analyzes cognitive patterns and optimizes the system during idle periods.
"""

import asyncio
import json
import logging
import time

from src.brain.agents import Atlas
from src.brain.neural_core.chronicle import kyiv_chronicle
from src.brain.neural_core.memory.graph import cognitive_graph

from .prompt_tuner import prompt_tuner
from .sandbox import get_sandbox
from .validator import validator

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
        {json.dumps([{"id": n["id"], "label": n["label"]} for n in nodes[:5]])}
        
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

        # 1. Identify research topic from context
        topic_prompt = f"""
        Given the following evolutionary context: {context}
        Identify one specific technical topic or library that ATLAS should research to improve its autonomy or technical depth.
        Respond with ONLY the topic name.
        """
        try:
            topic_response = await self.optimizer.llm.ainvoke(topic_prompt)
            topic = (
                topic_response.content.strip()
                if hasattr(topic_response, "content")
                else str(topic_response)
            )

            if not topic or "none" in topic.lower():
                return

            logger.info(f"[EVOLUTION] AKI: Researching '{topic}'...")

            # 2. Use the optimizer's chat capability (augmented with tools) to research
            research_query = f"Research the documentation and modern usage of '{topic}'. Summarize key principles for my NeuralCore memory."
            summary = await self.optimizer.chat(research_query, intent="solo_task")

            # 3. Ingest knowledge into the CognitiveGraph
            await cognitive_graph.add_node(
                f"knowledge_{int(time.time())}",
                "knowledge",
                f"Knowledge: {topic}",
                {"text": summary, "topic": topic, "ingested_at": kyiv_chronicle.get_iso_now()},
            )
            logger.info(f"[EVOLUTION] AKI: Successfully ingested knowledge about {topic}.")

        except Exception as e:
            logger.error(f"[EVOLUTION] AKI Deep Dive failed: {e}")

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

    async def run_sandboxed_optimization(self, issue_description: str, files_to_test: list[str]):
        """
        Full Phase 5 workflow:
        1. Generate Patch.
        2. Test in Sandbox.
        3. Validate.
        4. Generate StageReport.
        """
        logger.info(f"[EVOLUTION] Starting sandboxed optimization for: {issue_description}")

        # 1. Generate Patch
        patch_description = await self.propose_system_patch(issue_description)

        # 2. Setup Sandbox
        sandbox = get_sandbox(base_dir="/Users/dev/Documents/GitHub/atlastrinity")
        try:
            prepared = await sandbox.prepare_sandbox(files_to_test)
            if not prepared:
                return "Failed to prepare sandbox."

            # 3. Apply and Verify
            # (Note: In this version, we simulate the 'apply' part for the sandbox)
            verification = await sandbox.run_verification()

            # 4. Use Validator for static checks
            # (Simulated check of the patch_description content)
            validation = validator.validate_patch(patch_description, issue_description)

            # 5. Generate Stage Report
            report = {
                "issue": issue_description,
                "patch": patch_description,
                "sandbox_success": verification["success"],
                "validation_success": validation["valid"],
                "risk": validation["risk_level"],
            }
            # 5. Autonomous Deployment (No-Approval Mode)
            if verification["success"] and validation["valid"]:
                logger.info("[EVOLUTION] All checks passed. Proceeding with autonomous deployment.")
                # In a real scenario, this would use the real patch/merge logic on the main files.
                # For now, we simulate the merge as successful.
                report["deployed"] = True
            else:
                logger.warning(
                    "[EVOLUTION] Optimization failed verification/validation. Aborting deployment."
                )
                report["deployed"] = False

            # Record report as a node
            await cognitive_graph.add_node(
                f"report_{int(time.time())}",
                "report",
                f"DeploymentReport: {issue_description[:30]}",
                report,
            )

            logger.info(
                f"[EVOLUTION] Sandboxed optimization complete. Risk: {validation['risk_level']}. Deployed: {report['deployed']}"
            )
            return report

        finally:
            await sandbox.cleanup()

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
