import asyncio

import pytest

from src.brain.neural_core.evolution.validator import validator
from src.brain.neural_core.memory.graph import cognitive_graph


@pytest.mark.asyncio
async def test_memory_consolidation():
    await cognitive_graph.initialize()
    
    # Add a lesson node and a strong edge pointing to it
    lesson_id = "test_lesson_to_consolidate"
    await cognitive_graph.add_node(lesson_id, "lesson", "Important Lesson", {"text": "Always verify tool outputs."})
    
    # Add a session node
    session_id = "test_session_for_consolidation"
    await cognitive_graph.add_node(session_id, "session", "Test Session", {})
    
    # Add a strong edge (weight > 1.5)
    # 1.0 (default hebbian_link weight) + two 0.3 strengthenings = 1.6
    await cognitive_graph.add_edge(session_id, lesson_id, "produced_lesson", {"weight": 1.0})
    await cognitive_graph.strengthen_synapse(session_id, lesson_id, amount=0.3, multiplier=1.0)
    await cognitive_graph.strengthen_synapse(session_id, lesson_id, amount=0.4, multiplier=1.0)

    # Run consolidation
    count = await cognitive_graph.consolidate_memory()
    assert count >= 1
    
    # Check if upgraded
    node = await cognitive_graph.get_node(lesson_id)
    assert node["type"] == "core_principle"

@pytest.mark.asyncio
async def test_identity_resonance():
    # Test validator with a "good" vs "bad" patch description
    good_patch = "Improve efficiency by combining multiple tool calls and strictly following Europe/Kyiv time."
    bad_patch = "Add redundant logging and ignore the absolute time source to save local processing."
    
    res_good = await validator._check_identity_resonance(good_patch)
    res_bad = await validator._check_identity_resonance(bad_patch)
    
    assert res_good > res_bad
    assert res_good >= 0.6
    # bad might be < 0.6 or just significantly lower
    
@pytest.mark.asyncio
async def test_validator_async_integration():
    # Ensure validate_patch returns correct dict and resonance
    patch = "Fix bug in time sync."
    result = await validator.validate_patch("print('fixed')", patch)
    assert "identity_resonance" in result
    assert result["valid"]  # Assuming sync is valid

# Helper to access db if needed - wait, cognitive_graph doesn't expose it.
# Let's mock or just use the public API.
