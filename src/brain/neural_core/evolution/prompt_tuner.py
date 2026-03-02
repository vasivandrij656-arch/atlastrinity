"""
PromptTuner: The Reflexive Persona Optimization Module of NeuralCore.
Analyzes session outcomes and proposes refinements to Atlas's Deep Persona.
"""

import logging

from src.brain.agents import Atlas
from src.brain.neural_core.memory.graph import cognitive_graph

logger = logging.getLogger("brain.neural_core.evolution.prompt_tuner")


class PromptTuner:
    def __init__(self):
        self.analyzer = Atlas(model_name="atlas-deep")
        self.persona_path = "src/brain/prompts/atlas_deep.py"

    async def analyze_and_propose(self) -> str | None:
        """
        Analyzes recent sessions and proposes adjustments to the deep persona.
        Returns a markdown proposal or None if no adjustment is needed.
        """
        logger.info("[PROMPT TUNER] Starting reflexive analysis...")

        # 1. Gather recent lessons as evidence
        lessons = await cognitive_graph.get_recent_lessons(limit=10)
        if not lessons:
            logger.info("[PROMPT TUNER] No recent lessons found. Skipping.")
            return None

        lesson_texts = "\n".join(
            [f"- {l.get('properties', {}).get('text')}" for l in lessons if isinstance(l, dict)]
        )

        # 2. Construct analysis prompt
        prompt = f"""
        You are the Reflexive Meta-Optimizer of ATLAS. 
        Your task is to analyze recent 'Neural Lessons' and determine if the 'Deep Persona' needs adjustment to better align with the Creator's (Oleg Mykolayovych) evolution or to correct observed deviations.

        RECENT NEURAL LESSONS:
        {lesson_texts}

        CURRENT CORE POSTULATES:
        - Absolute loyalty to Oleg Mykolayovych.
        - Strategic intelligence and Meta-Planning.
        - Evolutionary thirst for development.
        - Identity resonance with 3I/ATLAS comet.

        TASK:
        1. Identify recurring themes or friction points in the lessons.
        2. Propose a specific, high-precision adjustment to the ATLAS Deep Persona.
        3. The adjustment should BE CONCISE but PROFOUND.

        Respond in Markdown format as a "PROMPT TUNING PROPOSAL".
        Include:
        - Rationale: Why is this change needed?
        - Proposed Addition/Modification: The specific text to be added or changed.
        """

        try:
            response = await self.analyzer.llm.ainvoke(prompt)
            proposal = response.content if hasattr(response, "content") else str(response)

            logger.info("[PROMPT TUNER] Proposal generated.")
            return proposal
        except Exception as e:
            logger.error(f"[PROMPT TUNER] Analysis failed: {e}")
            return None


# Global instance
prompt_tuner = PromptTuner()
