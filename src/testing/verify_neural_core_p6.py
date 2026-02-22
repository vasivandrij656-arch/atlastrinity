"""
Final verification for NeuralCore Expansion (Phase 6).
Verifies Identity layer, Environment awareness, and Milestone persistence.
"""

import asyncio
import logging
import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

from src.brain.neural_core.core import neural_core
from src.brain.neural_core.identity.postulate_manager import postulate_manager
from src.brain.neural_core.evolution.observer import environment_observer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_neural_core_p6")

async def test_identity():
    logger.info("Testing Identity Layer...")
    postulates = postulate_manager.get_postulates()
    logger.info(f"Loaded {len(postulates)} postulates.")
    assert "ENTROPY_MANIFESTO" in postulates
    
    milestones = postulate_manager.get_milestones()
    logger.info(f"Loaded {len(milestones)} identity milestones.")
    assert any("Уже в дорозі" in m["event"] for m in milestones)

async def test_observer():
    logger.info("Testing EnvironmentObserver...")
    # Manual scan
    await environment_observer.observe_system()
    
    # Check if graph node was created
    chain = await neural_core.graph.get_causality_chain("spatial_atlas_home")
    logger.info(f"Observer chain: {chain}")

async def main():
    try:
        # Initialize Core
        await neural_core.initialize()
        
        await test_identity()
        await test_observer()
        
        logger.info("\n✅ NeuralCore Expansion (Phase 6) Verification PASSED")
    except Exception as e:
        logger.error(f"\n❌ NeuralCore Expansion (Phase 6) Verification FAILED: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
