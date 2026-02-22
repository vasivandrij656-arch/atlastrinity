import asyncio
import os
import sys

# Ensure project root is in path
sys.path.append(os.getcwd())

from src.brain.neural_core.memory.graph import cognitive_graph


async def record_verification_milestone():
    await cognitive_graph.initialize()

    milestone_id = "milestone_phase_6_verified"
    await cognitive_graph.add_node(
        milestone_id,
        "verification",
        "Phase 6 (NeuralCore Expansion) Verified",
        {
            "status": "PASSED",
            "verifier": "Antigravity",
            "date": "2026-02-23",
            "details": "All unit and integration tests passed. Orchestrator integration confirmed.",
        },
    )
    print(f"✅ Milestone {milestone_id} recorded in CognitiveGraph.")


if __name__ == "__main__":
    asyncio.run(record_verification_milestone())
