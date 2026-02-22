"""
Verification script for NeuralCore (Atlas Brain).
Checks time synchronization, graph persistence, and integration.
"""

import asyncio
import logging
import os
import sys

# Ensure project root is in path
sys.path.append(os.getcwd())

from src.brain.neural_core.chronicle import kyiv_chronicle
from src.brain.neural_core.core import neural_core

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_neural_core")


async def test_chronicle():
    logger.info("Testing KyivChronicle...")
    now = kyiv_chronicle.get_now()
    logger.info(f"Local Kyiv Time: {now}")
    assert "Europe/Kyiv" in str(now.tzinfo)

    success = await kyiv_chronicle.sync_time()
    if success:
        logger.info("External sync successful.")
    else:
        logger.warning("External sync failed (possibly network), but falling back to system.")


async def test_graph():
    logger.info("Testing CognitiveGraph...")
    # Using a test DB path
    from src.brain.neural_core.memory.graph import CognitiveGraph

    test_graph = CognitiveGraph(
        db_path="/Users/dev/Documents/GitHub/atlastrinity/src/testing/test_cognitive_graph.db"
    )
    await test_graph.initialize()

    node_id = "test_node_1"
    await test_graph.add_node(node_id, "test", "Test Node", {"meta": "data"})
    logger.info(f"Added node {node_id}")

    chain = await test_graph.get_causality_chain(node_id)
    # Since we didn't add edges, expect empty or just node
    logger.info(f"Chain for {node_id}: {chain}")

    # Cleanup
    if os.path.exists(
        "/Users/dev/Documents/GitHub/atlastrinity/src/testing/test_cognitive_graph.db"
    ):
        os.remove("/Users/dev/Documents/GitHub/atlastrinity/src/testing/test_cognitive_graph.db")


async def test_neural_core_init():
    logger.info("Testing NeuralCore Awakening...")
    await neural_core.initialize()
    logger.info("NeuralCore initialized successfully.")


async def main():
    try:
        await test_chronicle()
        await test_graph()
        await test_neural_core_init()
        logger.info("\n✅ NeuralCore Verification PASSED")
    except Exception as e:
        logger.error(f"\n❌ NeuralCore Verification FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
