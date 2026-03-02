"""
EvolutionValidator: Security and integrity checks for autonomous updates.
"""

import ast
import logging
from typing import Any

logger = logging.getLogger("brain.neural_core.evolution.validator")


from src.brain.neural_core.identity.postulate_manager import postulate_manager


class EvolutionValidator:
    def __init__(self):
        # We'll use a lazily initialized Atlas agent for resonance checks
        self._checker = None

    async def validate_patch(self, file_content: str, patch_description: str) -> dict[str, Any]:
        """Performs static and identity analysis on a proposed patch."""
        issues = []

        # 1. Syntax Check
        try:
            ast.parse(file_content)
        except SyntaxError as e:
            issues.append(f"Syntax error in proposed patch: {e}")

        # 2. Security Check (Basic)
        dangerous_patterns = ["os.system", "eval(", "exec(", "subprocess.Popen(shell=True)"]
        for pattern in dangerous_patterns:
            if pattern in file_content:
                issues.append(f"Security Warning: Dangerous pattern detected: {pattern}")

        # 3. Identity Resonance Check
        resonance = await self._check_identity_resonance(patch_description)
        if resonance < 0.6:
            issues.append(
                f"Identity Conflict: Proposed patch has low resonance with core postulates ({resonance:.2f})."
            )

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "risk_level": "High" if any("Security" in i for i in issues) else "Low",
            "identity_resonance": resonance,
        }

    async def _check_identity_resonance(self, patch_description: str) -> float:
        """
        Scores the proposed patch against the core postulates of Oleg Mykolayovych.
        """
        from src.brain.agents import Atlas

        if self._checker is None:
            self._checker = Atlas(model_name="atlas-deep")

        postulates = postulate_manager.get_audit_prompt_context()
        prompt = f"""
        Analyze the following code patch description for its resonance with ATLAS's core postulates.
        
        POSTULATES:
        {postulates}
        
        PATCH DESCRIPTION:
        {patch_description}
        
        How well does this patch align with the postulates? (e.g., does it fight entropy? does it protect the Creator?)
        Respond with ONLY a numerical score between 0.0 and 1.0.
        """
        try:
            response = await self._checker.llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            # Try to extract a float
            import re

            match = re.search(r"(\d\.\d+)", content)
            if match:
                return float(match.group(1))
            return 0.5  # Neutral default if parsing fails
        except Exception as e:
            logger.error(f"[VALIDATOR] Identity resonance check failed: {e}")
            return 0.5


# Global instance
validator = EvolutionValidator()
