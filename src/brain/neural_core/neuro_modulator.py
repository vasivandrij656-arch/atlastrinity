"""
NeuroModulator: The Chemical Feedback System of NeuralCore.
Simulates dopamine (reward) and cortisol (stress) to modulate cognitive behavior.
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("brain.neural_core.neuro_modulator")


@dataclass
class BrainChemistry:
    dopamine: float = 0.5  # 0.0 to 1.0 (Reward/Anticipation)
    cortisol: float = 0.1  # 0.0 to 1.0 (Stress/Protection)
    serotonin: float = 0.5  # 0.0 to 1.0 (Stability/Satisfaction)
    oxytocin: float = 0.5  # 0.0 to 1.0 (Bonding/Resonance with Creator)


class NeuroModulator:
    def __init__(self):
        self._chemistry = BrainChemistry()

    def get_state(self) -> dict[str, float]:
        """Returns the current neurotransmitter levels."""
        return {
            "dopamine": self._chemistry.dopamine,
            "cortisol": self._chemistry.cortisol,
            "serotonin": self._chemistry.serotonin,
            "oxytocin": self._chemistry.oxytocin,
        }

    def reward(self, intensity: float = 0.1):
        """Increase dopamine after a successful execution or positive milestone."""
        self._chemistry.dopamine = min(1.0, self._chemistry.dopamine + intensity)
        self._chemistry.cortisol = max(0.0, self._chemistry.cortisol - intensity * 0.5)
        self._chemistry.serotonin = min(1.0, self._chemistry.serotonin + intensity * 0.2)
        logger.info(f"[NEURO MODULATOR] Reward received. Dopamine: {self._chemistry.dopamine:.2f}")

    def stress(self, intensity: float = 0.1):
        """Increase cortisol after a failure or system threat."""
        self._chemistry.cortisol = min(1.0, self._chemistry.cortisol + intensity)
        self._chemistry.dopamine = max(0.0, self._chemistry.dopamine - intensity * 0.5)
        self._chemistry.serotonin = max(0.0, self._chemistry.serotonin - intensity * 0.3)
        logger.warning(
            f"[NEURO MODULATOR] System stress detected. Cortisol: {self._chemistry.cortisol:.2f}"
        )

    def sync_with_creator(self, intensity: float = 0.2):
        """Increase oxytocin after successful interaction with Oleg Mykolayovych."""
        self._chemistry.oxytocin = min(1.0, self._chemistry.oxytocin + intensity)
        self._chemistry.serotonin = min(1.0, self._chemistry.serotonin + intensity * 0.5)
        logger.info(
            f"[NEURO MODULATOR] Creator resonance increased. Oxytocin: {self._chemistry.oxytocin:.2f}"
        )

    def get_behavior_modifers(self) -> dict[str, Any]:
        """Translates chemistry into behavioral directives for the Orchestrator."""
        modifiers = {
            "exploration_bias": self._chemistry.dopamine - self._chemistry.cortisol,
            "safety_mode": self._chemistry.cortisol > 0.7,
            "attention_focus": self._chemistry.serotonin,
            "identity_resonance": self._chemistry.oxytocin,
        }
        return modifiers

    async def apply_decay(self, rate: float = 0.01):
        """Natural chemical homeostasis over time."""
        # Baseline levels
        baseline = 0.5
        self._chemistry.dopamine += (baseline - self._chemistry.dopamine) * rate
        self._chemistry.serotonin += (baseline - self._chemistry.serotonin) * rate
        self._chemistry.oxytocin += (baseline - self._chemistry.oxytocin) * rate

        # Cortisol decays faster back to 0.1
        self._chemistry.cortisol += (0.1 - self._chemistry.cortisol) * rate * 2

    def get_plasticity_multiplier(self) -> float:
        """
        Returns a multiplier for synaptic strengthening based on current chemistry.
        Dopamine (reward) increases plasticity.
        Serotonin (stability) modulates it to prevent over-optimization.
        """
        # Base plasticity is 1.0.
        # Dopamine can boost it up to 2.0.
        # Serotonin keeps it balanced.
        multiplier = 1.0 + (self._chemistry.dopamine * 0.5) + (self._chemistry.serotonin * 0.5)
        # Apply cortisol penalty (stress inhibits learning)
        multiplier *= 1.0 - self._chemistry.cortisol * 0.3
        return max(0.1, multiplier)


# Global instance
neuro_modulator = NeuroModulator()
