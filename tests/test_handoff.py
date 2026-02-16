import asyncio
import os
import sys
from unittest.mock import MagicMock

sys.modules["langchain_core"] = MagicMock()
sys.modules["langchain_core.messages"] = MagicMock()
sys.modules["langgraph"] = MagicMock()
sys.modules["langgraph.graph"] = MagicMock()
# Mock TTS availability
sys.modules["ukrainian_tts"] = MagicMock()
sys.modules["ukrainian_tts.tts"] = MagicMock()

# Add src path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from src.brain.core.orchestration.orchestrator import Trinity


# Mock Agents
class MockAtlas:
    async def analyze_request(self, user_request: str, context=None, history=None):
        return {"intent": "task", "reason": "Test reason"}

    async def create_plan(self, analysis):
        mock_step = {
            "id": 1,
            "action": "test",
            "tool": "terminal",
            "requires_verification": True,
        }
        mock_plan = MagicMock()
        mock_plan.steps = [mock_step]
        mock_plan.goal = "Test Goal"
        return mock_plan

    def get_voice_message(self, *args, **kwargs):
        return "test message"


class MockTetyana:
    async def execute_step(self, step):
        mock_result = MagicMock()
        mock_result.step_id = 1
        mock_result.success = True
        mock_result.result = "Success"
        mock_result.error = None
        return mock_result

    def get_voice_message(self, *args, **kwargs):
        return "test message"


class MockGrisha:
    async def verify_step(self, step, result):
        raise RuntimeError("Simulated Crash in Grisha")


async def test_handoff_crash():
    print("Testing Handoff Crash Resilience...")

    trinity = Trinity()
    # Inject mocks
    trinity.atlas = MockAtlas()  # type: ignore
    trinity.tetyana = MockTetyana()  # type: ignore
    trinity.grisha = MockGrisha()  # type: ignore
    trinity.voice = MagicMock()

    # Run
    try:
        result = await trinity.run("Test Request")
        print(f"Result Status: {result['status']}")

        # Check if error was logged in state
        logs = trinity.state.get("logs", [])
        crash_log = next((l for l in logs if "Verification crashed" in l["message"]), None)  # type: ignore

        if crash_log:
            print("SUCCESS: Orchestrator caught the crash and logged it.")
        else:
            print("FAILURE: Orchestrator did not log the crash.")

        if result["status"] == "completed":  # It completes the run, even if step failed
            print("SUCCESS: System remained stable (did not raise exception).")
        else:
            print(f"FAILURE: System returned status {result['status']}")

    except Exception as e:
        print(f"FAILURE: System crashed with exception: {e}")


if __name__ == "__main__":
    asyncio.run(test_handoff_crash())
