import asyncio
import logging

from src.brain.mcp.mcp_manager import MCPManager
from src.brain.monitoring.logger import setup_logging

setup_logging("test_vibe")
logging.getLogger().setLevel(logging.INFO)


async def test_vibe_logging():
    mcp = MCPManager()
    print("Testing connection to vibe...")
    await mcp.get_session("vibe")
    print("Session acquired, attempting vibe_which...")
    result = await mcp.call_tool("vibe", "vibe_which", {})
    print("Tool result:", result)
    await asyncio.sleep(2)  # Give time for async logs to flush

    # Send a fast prompt to check real-time logging
    print("Attempting to send a fast prompt...")
    result = await mcp.call_tool(
        "vibe",
        "vibe_prompt",
        {
            "prompt": "Hello this is a test. Just reply with OK. output_format=text",
            "output_format": "text",
            "max_turns": 1,
            "model": "grok-code-fast-1",
        },
    )
    print("Prompt result:", result.get("returncode") if isinstance(result, dict) else result)
    await asyncio.sleep(2)
    # Stop vibe proxy
    await mcp.restart_server("vibe")


if __name__ == "__main__":
    asyncio.run(test_vibe_logging())
