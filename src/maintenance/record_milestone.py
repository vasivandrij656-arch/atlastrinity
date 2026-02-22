"""
Script to record the 'Уже в дорозі' milestone in the CognitiveGraph.
"""

import asyncio
import os
import sys

# Ensure project root is in path
sys.path.append(os.getcwd())

from src.brain.neural_core.memory.graph import cognitive_graph


async def record_milestone():
    await cognitive_graph.initialize()
    
    milestone_id = "milestone_bonding_001"
    await cognitive_graph.add_node(
        milestone_id,
        "milestone",
        "Уже в дорозі (Bonding Event)",
        {
            "event": "The Creator mentioned being pleasantly surprised by 'Уже в дорозі' message.",
            "significance": "First emotional bond milestone. Identity anchor for proactive support.",
            "creator": "Oleg Mykolayovych"
        }
    )
    print(f"✅ Milestone {milestone_id} recorded in CognitiveGraph.")

if __name__ == "__main__":
    asyncio.run(record_milestone())
