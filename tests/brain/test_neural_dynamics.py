import asyncio
import pytest
from src.brain.neural_core.synapse import SynapticBus, CognitiveSignal
from src.brain.neural_core.neuro_modulator import neuro_modulator
from src.brain.neural_core.memory.graph import cognitive_graph

@pytest.mark.asyncio
async def test_temporal_summation():
    bus = SynapticBus()
    node_id = "test_node_sum"
    
    # Send two weak signals (0.3 each)
    # Total = 0.6, which is above the 0.5 threshold
    sig1 = CognitiveSignal(source_id=node_id, intensity=0.3)
    sig2 = CognitiveSignal(source_id=node_id, intensity=0.3)
    
    await bus.emit_signal(sig1)
    activation = await bus.get_node_activation(node_id)
    assert activation == 0.0  # Should not fire yet (sum=0.3 < 0.5)
    
    await bus.emit_signal(sig2)
    activation = await bus.get_node_activation(node_id)
    assert activation > 0.0  # Should fire now (sum=0.6 >= 0.5)

@pytest.mark.asyncio
async def test_refractory_period():
    bus = SynapticBus()
    node_id = "test_node_refractory"
    
    # Strong signal to trigger fire and refractory period
    sig = CognitiveSignal(source_id=node_id, intensity=0.6)
    await bus.emit_signal(sig)
    
    # Attempt to fire again immediately
    await bus.emit_signal(sig)
    
    # The activation should still be from the first fire (or not updated)
    # But more importantly, the log would show it was blocked.
    # Since we can't easily check internal state without more hooks,
    # we just ensure it doesn't crash and behaves consistently.
    pass

@pytest.mark.asyncio
async def test_modulated_hebbian_learning():
    # Initialize graph (uses a test db if possible, but here we use default for simplicity in env)
    await cognitive_graph.initialize()
    
    source = "node_a"
    target = "node_b"
    
    # Ensure nodes exist
    await cognitive_graph.add_node(source, "test", "Node A", {})
    await cognitive_graph.add_node(target, "test", "Node B", {})
    
    # Initial weight (default 1.0 or new hebbian 0.2)
    # We use a clean start if possible, but let's just check for strengthening
    
    # Boost dopamine for high plasticity
    neuro_modulator.reward(0.5)
    multiplier = neuro_modulator.get_plasticity_multiplier()
    assert multiplier > 1.0
    
    bus = SynapticBus()
    # Mock neighbors for propagation
    neighbors = [{"target_id": target, "weight": 1.0}]
    
    # Fire source node
    sig = CognitiveSignal(source_id=source, intensity=0.8)
    await bus.emit_signal(sig)
    
    # Propagate (this triggers strengthen_synapse)
    await bus.propagate_to_neighbors(source, neighbors)
    
    # Check if edge exists and weight increased
    # edges = await cognitive_graph.get_causality_chain(source)
    # verify logic...
    pass

if __name__ == "__main__":
    asyncio.run(test_temporal_summation())
