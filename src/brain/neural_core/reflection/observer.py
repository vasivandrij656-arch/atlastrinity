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

    async def observe_reasoning(self, thoughts: list[str], current_context: str) -> str | None:
        """
        Analyzes a sequence of internal thoughts for inefficiencies or drifts.
        Returns a "Meta-Correction" if issues are found, else None.
        """
        if not thoughts:
            return None

        thought_stream = "\n".join([f"Thought {i+1}: {t}" for i, t in enumerate(thoughts)])
        
        prompt = f"""
        As the Meta-Cognitive Observer of ATLAS, analyze the following internal reasoning stream.
        
        THOUGHT STREAM:
        {thought_stream}
        
        CONTEXT:
        {current_context[:500]}...
        
        TASK:
        1. Search for "Lazy Cognitive Habits" (e.g. redundant tool plans, skipping verification, ignoring creator postulates).
        2. Detect "Identity Drift" (behaving like a generic assistant).
        3. If detected, provide a SHARP meta-correction directive for the next reasoning step.
        
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
