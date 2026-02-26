"""
Integration tests for NeuralCore: The Living Brain.
Tests full initialization, observation, and facade methods.
"""

import asyncio
import os

import pytest

from src.brain.neural_core.core import NeuralCore


@pytest.fixture
async def neural_core_instance(monkeypatch):
    monkeypatch.setenv("COPILOT_API_KEY", "fake_copilot_key")
    monkeypatch.setenv("WINDSURF_API_KEY", "fake_windsurf_key")
    # Use a test-specific db path if needed, but for now we test the facade logic
    core = NeuralCore()
    # Mocking wait times if necessary
    yield core
    if hasattr(core.evolution, "_running"):
        core.evolution._running = False


@pytest.mark.asyncio
async def test_neural_core_awakening(neural_core_instance):
    # Test double initialization guard
    await neural_core_instance.initialize()
    assert neural_core_instance._initialized is True

    await neural_core_instance.initialize()
    assert neural_core_instance._initialized is True


@pytest.mark.asyncio
async def test_neural_core_facade_methods(neural_core_instance):
    await neural_core_instance.initialize()

    # Test get_time
    kyiv_time = neural_core_instance.get_time()
    assert "T" in kyiv_time

    # Test identity access
    postulates = neural_core_instance.identity.get_postulates()
    assert "EVOLUTIONARY_WILL" in postulates


@pytest.mark.asyncio
async def test_neural_core_evolution_trigger(neural_core_instance):
    await neural_core_instance.initialize()

    # Trigger manual evolution
    # We don't wait for the full LLM cycle in integration test to save time/cost
    # but we verify the method exists and can be called
    try:
        await asyncio.wait_for(neural_core_instance.evolve(direction="test"), timeout=10)
    except TimeoutError:
        pytest.fail("Evolution trigger timed out")
    except Exception as e:
        # LLM might fail in CI due to missing keys, but the method call should be valid
        if "API key" in str(e) or "LLM" in str(e):
            pytest.skip("LLM execution skipped in CI/Integration test")
        else:
            raise e
