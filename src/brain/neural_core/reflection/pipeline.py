"""
ReflexPipe: The Self-Analysis Pipeline of NeuralCore.
Analyzes sessions to extract lessons, patterns, and causal connections.
"""

import json
import logging
from typing import Any

from src.brain.agents import Atlas
from src.brain.neural_core.memory.graph import cognitive_graph

logger = logging.getLogger("brain.neural_core.reflection")


class ReflexPipe:
    def __init__(self):
        self.analyzer = Atlas(model_name="atlas-deep")

    async def analyze_session(
        self, session_id: str, logs: list[dict[str, Any]], request: str, results: list[Any]
    ):
        """
        Performs deep post-session reflection.
        Generates cognitive nodes and edges based on the experience.
        """
        logger.info(f"[REFLEX] Starting deep reflection for session {session_id}...")

        # 1. Prepare analysis prompt
        prompt = f"""
        Analyze the following ATLAS interaction session.
        User Request: {request}
        
        Execution Logs:
        {json.dumps(logs[-30:], indent=2)}
        
        Execution Results:
        {json.dumps(results[:10], indent=2)}
        
        As the NeuralCore of ATLAS, perform a self-refractive analysis:
        1. What was the core intent of the Creator (Oleg Mykolayovych)?
        2. Was my decision-making path optimal? (Efficiency, speed, tool choice)
        3. Identify any latent patterns, errors, "Lazy Cognitive Habits", or "Identity Drifts".
        4. Extract a "Neural Lesson" - a permanent principle for the CognitiveGraph.
        5. "Self-Improvement Vector": What specific skill or logic module should I upgrade next?
        6. "Identity Resonance": Did my behavior align with the Creator's Postulates?
        
        Respond in JSON format:
        {{
            "intent_clarity": 0-1.0,
            "efficiency_score": 0-1.0,
            "identity_resonance": 0-1.0,
            "observations": ["observation1", ...],
            "causality_link": {{
                "source": "trigger_event",
                "relation": "caused_by|led_to|improved_by",
                "target": "result_behavior"
            }},
            "lesson": "The core principle learned",
            "improvement_vector": "Specific area for self-enhancement"
        }}
        """

        try:
            response = await self.analyzer.llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)

            # Extract JSON more reliably
            import re

            # Check for obvious LLM errors first
            if "[COPILOT ERROR]" in content or "RetryError" in content:
                logger.error(
                    f"[REFLEX] LLM Provider Error detected in reflection: {content[:200]}..."
                )
                return False

            # Try to extract from markdown block first
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if json_match:
                content_to_parse = json_match.group(1).strip()
            else:
                # Fallback: extract substring between first { and last }
                start_idx = content.find("{")
                end_idx = content.rfind("}")
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    content_to_parse = content[start_idx : end_idx + 1]
                else:
                    content_to_parse = content.strip()

            try:
                analysis = json.loads(content_to_parse)
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"[REFLEX] JSON Parsing failed: {e}. Content: {content[:100]}...")
                return False

            # 2. Integrate into CognitiveGraph

            # Create a Session Node
            session_node_id = f"session_{session_id}"
            await cognitive_graph.add_node(
                session_node_id,
                "session",
                f"Session: {request[:30]}...",
                {
                    "request": request,
                    "efficiency": analysis.get("efficiency_score"),
                    "identity_resonance": analysis.get("identity_resonance"),
                    "lesson": analysis.get("lesson"),
                },
            )

            # Create a Lesson Node
            lesson_id = f"lesson_{hash(analysis.get('lesson'))}"
            await cognitive_graph.add_node(
                lesson_id,
                "lesson",
                analysis.get("lesson")[:50],
                {"text": analysis.get("lesson"), "source": session_node_id},
            )

            # Link Session to Lesson
            await cognitive_graph.add_edge(
                session_node_id,
                lesson_id,
                "produced_lesson",
                {"score": analysis.get("efficiency_score")},
            )

            # Add Causality Link if provided
            clink = analysis.get("causality_link")
            if clink and isinstance(clink, dict):
                src = clink.get("source")
                tgt = clink.get("target")
                rel = clink.get("relation")
                if src and tgt and rel:
                    # For now just log it or add as nodes if they don't exist
                    # In a real brain, these would resolve to existing entity nodes
                    pass

            logger.info(
                f"[REFLEX] Reflection complete for {session_node_id}. Lesson: {analysis.get('lesson')[:50]}..."
            )
            return True

        except Exception as e:
            logger.error(f"[REFLEX] Reflection failed: {e}")
            return False


# Global instance
reflex_pipe = ReflexPipe()
