import asyncio
import logging
from unittest.mock import AsyncMock, patch

from src.brain.healing.improvement_engine import ImprovementEngine
from src.brain.healing.modes import HealingPriority, Hotspot

logging.basicConfig(level=logging.INFO)

async def test_recursion():
    engine = ImprovementEngine()
    
    # Create a mockup hotspot
    hotspot = Hotspot(
        file_path="src/dummy/bad_code.py",
        description="A simulated bad code snippet",
        priority=HealingPriority.HIGH,
        category="code_quality",
        related_notes=["mock_note_1"]
    )

    # We will mock the `mcp_manager.call_tool` to simulate responses.
    # 1. First iteration vibe response
    # 2. First iteration lint error
    # 3. Second iteration vibe response
    # 4. Second iteration lint success
    
    call_count = {"vibe": 0, "lint": 0}
    
    async def mock_call_tool(server, command, args):
        if server == "vibe":
            call_count["vibe"] += 1
            if call_count["vibe"] == 1:
                return "Mocked Vibe response 1"
            else:
                return "Mocked Vibe response 2"
        elif server == "devtools":
            call_count["lint"] += 1
            if call_count["lint"] == 1:
                return {"overall_status": "error", "errors": ["Line 42: indentation error"]}
            else:
                return {"overall_status": "clean"}
        return None

    # Patch the actual call
    with patch("src.brain.mcp.mcp_manager.mcp_manager") as mock_manager:
        mock_manager.call_tool = AsyncMock(side_effect=mock_call_tool)
        
        result = await engine.apply_improvement(hotspot)
        
        print("\n--- TEST RESULTS ---")
        print(f"Vibe called {call_count['vibe']} times")
        print(f"Linting called {call_count['lint']} times")
        print(f"Final Success: {result.success}")
        print(f"Message: {result.message}")
        print("--------------------")

if __name__ == "__main__":
    asyncio.run(test_recursion())
