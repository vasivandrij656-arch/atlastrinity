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
        self._refractory_nodes: dict[str, float] = {}  # node_id -> expiry_timestamp
        self._accumulation_buffer: dict[str, float] = {}  # node_id -> accumulated_intensity
        self._lock = asyncio.Lock()

    async def emit_signal(self, signal: CognitiveSignal):
        """Emits a signal into the bus and handles its propagation and inhibition."""
        async with self._lock:
            now = asyncio.get_event_loop().time()

            # 1. Check Refractory Period
            if signal.source_id in self._refractory_nodes:
                if now < self._refractory_nodes[signal.source_id]:
                    logger.debug(f"[SYNAPSE] Node {signal.source_id} is in refractory period.")
                    return
                else:
                    del self._refractory_nodes[signal.source_id]

            # 2. Temporal Summation (Buffer)
            current_sum = self._accumulation_buffer.get(signal.source_id, 0.0)
            new_sum = current_sum + signal.intensity

            if new_sum < 0.5:  # Threshold for firing
                self._accumulation_buffer[signal.source_id] = new_sum
                logger.debug(
                    f"[SYNAPSE] Signal accumulated for {signal.source_id} ({new_sum:.2f})"
                )
                return

            # Reset buffer on fire
            self._accumulation_buffer[signal.source_id] = 0.0
            
            # Fire signal
            actual_intensity = min(1.0, new_sum)
            self._active_signals.append(signal)
            self._node_activations[signal.source_id] = actual_intensity

            logger.info(
                f"[SYNAPSE] Node {signal.source_id} FIRED (Intensity: {actual_intensity:.2f})"
            )

            # Set refractory period (0.5s baseline)
            self._refractory_nodes[signal.source_id] = now + 0.5

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
        Includes Real-time Hebbian Learning integration.
        """
        from src.brain.neural_core.memory.graph import cognitive_graph
        from src.brain.neural_core.neuro_modulator import neuro_modulator

        source_activation = await self.get_node_activation(source_id)
        if source_activation < 0.3:
            return

        # Get chemical plasticity multiplier
        multiplier = neuro_modulator.get_plasticity_multiplier()

        for neighbor in neighbors:
            target_id = neighbor["target_id"]
            weight = neighbor.get("weight", 1.0)

            # Attenuated signal propagation
            new_intensity = source_activation * weight * 0.5

            if new_intensity > 0.1:
                # 1. Trigger Hebbian Learning (Real-time weight strengthening)
                await cognitive_graph.strengthen_synapse(
                    source_id, target_id, amount=0.05, multiplier=multiplier
                )

                # 2. Emit signal to neighbor
                new_signal = CognitiveSignal(
                    source_id=target_id, intensity=new_intensity, metadata={"via": source_id}
                )
                await self.emit_signal(new_signal)


# Global instance
synaptic_bus = SynapticBus()
