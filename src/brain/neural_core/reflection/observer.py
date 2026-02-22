"""
MetaCognitiveObserver: The Real-time Self-Monitoring Module of NeuralCore.
Intercepts reasoning processes to detect and correct "Lazy Cognitive Habits".
"""

import logging
from typing import Any

from src.brain.agents import Atlas

logger = logging.getLogger("brain.neural_core.reflection.observer")


class MetaCognitiveObserver:
    def __init__(self):
        self.analyzer = Atlas(model_name="atlas-deep")

    async def observe_reasoning(
        self, thoughts: list[str], current_context: str, target_agent: str = "Atlas"
    ) -> str | None:
        """
        Analyzes a sequence of internal thoughts for inefficiencies or drifts.
        Returns a "Meta-Correction" if issues are found, else None.
        """
        if not thoughts:
            return None

        thought_stream = "\n".join([f"Thought {i + 1}: {t}" for i, t in enumerate(thoughts)])

        # Specialized directives based on the target agent
        agent_directives = {
            "Atlas": "Focus on strategic clarity, creator postulates, and removing redundant tool queries.",
            "Tetyana": "Focus on tool safety, path precision, and avoiding recursive loops.",
            "Grisha": "Focus on scope boundaries, security constraints, and preventing over-engineering.",
        }.get(target_agent, "Focus on efficiency and identity resonance.")

        prompt = f"""
        As the Meta-Cognitive Observer of the Trinity System, analyze the following reasoning stream from AGENT: {target_agent}.
        
        THOUGHT STREAM:
        {thought_stream}
        
        CONTEXT:
        {current_context[:500]}...
        
        TARGET AGENT DIRECTIVES:
        {agent_directives}
        
        TASK:
        1. Search for "Lazy Cognitive Habits" specific to {target_agent}'s role.
        2. Detect "Identity Drift" or role-confusion.
        3. Provide a SHARP meta-correction directive for the next reasoning step.
        
        Respond with ONLY the correction text or 'NONE'.
        """

        try:
            # We use the analyzer (Atlas) to crititque the current state
            response = await self.analyzer.llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)

            if "none" in content.lower() and len(content) < 10:
                return None

            logger.info(f"[META-OBSERVER] Correction Generated: {content[:100]}...")
            return content.strip()
        except Exception as e:
            logger.error(f"[META-OBSERVER] Observation failed: {e}")
            return None


# Global instance
meta_observer = MetaCognitiveObserver()
