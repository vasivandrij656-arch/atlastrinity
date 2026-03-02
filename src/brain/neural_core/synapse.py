"""
Synapse: The Dynamic Communication Layer of NeuralCore.
Implements synaptic signal propagation and lateral inhibition between cognitive nodes.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from src.brain.neural_core.chronicle import kyiv_chronicle

logger = logging.getLogger("brain.neural_core.synapse")


@dataclass
class CognitiveSignal:
    source_id: str
    intensity: float  # 0.0 to 1.0
    modulators: dict[str, float] = field(default_factory=dict)  # e.g., {"dopamine": 0.5}
    timestamp: str = field(default_factory=kyiv_chronicle.get_iso_now)
    metadata: dict[str, Any] = field(default_factory=dict)


class SynapticBus:
    def __init__(self):
        self._active_signals: list[CognitiveSignal] = []
        self._node_activations: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def emit_signal(self, signal: CognitiveSignal):
        """Emits a signal into the bus and handles its propagation and inhibition."""
        async with self._lock:
            self._active_signals.append(signal)
            self._node_activations[signal.source_id] = signal.intensity

            logger.debug(
                f"[SYNAPSE] Signal emitted from {signal.source_id} (Intensity: {signal.intensity:.2f})"
            )

            # Apply lateral inhibition: strong signals suppress weak ones
            await self._apply_lateral_inhibition(signal)

    async def _apply_lateral_inhibition(self, catalyst: CognitiveSignal):
        """
        Signals from one node can inhibit activity in 'competing' or unrelated nodes
        to focus cognitive resources (Attention Mechanism).
        """
        if catalyst.intensity > 0.7:
            for node_id in list(self._node_activations.keys()):
                if node_id != catalyst.source_id:
                    # Inhibition factor proportional to signal strength
                    inhibition = (catalyst.intensity - 0.5) * 0.2
                    self._node_activations[node_id] = max(
                        0.0, self._node_activations[node_id] - inhibition
                    )

                    if self._node_activations[node_id] < 0.1:
                        del self._node_activations[node_id]

    async def get_node_activation(self, node_id: str) -> float:
        """Returns the current activation level of a node."""
        return self._node_activations.get(node_id, 0.0)

    async def propagate_to_neighbors(self, source_id: str, neighbors: list[dict[str, Any]]):
        """
        Propagates activation to neighbor nodes in the CognitiveGraph.
        neighbors: list of dicts with {"target_id": str, "weight": float}
        """
        source_activation = await self.get_node_activation(source_id)
        if source_activation < 0.3:
            return

        for neighbor in neighbors:
            target_id = neighbor["target_id"]
            weight = neighbor.get("weight", 1.0)

            # Attenuated signal propagation
            new_intensity = source_activation * weight * 0.5

            if new_intensity > 0.1:
                new_signal = CognitiveSignal(
                    source_id=target_id, intensity=new_intensity, metadata={"via": source_id}
                )
                await self.emit_signal(new_signal)


# Global instance
synaptic_bus = SynapticBus()
