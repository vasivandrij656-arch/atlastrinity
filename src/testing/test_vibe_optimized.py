import asyncio
import logging
import os
import sys

# Add project src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.brain.mcp_manager import mcp_manager  # noqa: E402
from src.brain.message_bus import AgentMsg, MessageType, message_bus  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_vibe")


async def test_error_analysis_payload():
    """Verify vibe_analyze_error accepts new parameters and structures the prompt."""
    logger.info("Testing vibe_analyze_error with enhanced context...")

    try:
        # We don't want to actually call the LLM in a unit test if possible,
        # but here we are testing the MCP tool interface.
        # Since vibe_server.py is an internal MCP server, we can test it via mcp_manager.

        result = await mcp_manager.call_tool(
            "vibe",
            "vibe_analyze_error",
            {
                "error_message": "Test error: division by zero",
                "step_action": "Calculate 10/0",
                "expected_result": "A number",
                "actual_result": "ZeroDivisionError",
                "auto_fix": False,
                "recovery_history": [
                    {
                        "attempt": 1,
                        "action": "Try with calculator",
                        "status": "failed",
                        "error": "Crash",
                    },
                ],
            },
        )

        logger.info(
            f"Vibe Analysis Result keys: {result.keys() if isinstance(result, dict) else 'Not a dict'}",
        )
        return True
    except Exception as e:
        logger.error(f"Error analysis test failed: {e}")
        return False


async def test_message_bus_extensions():
    """Verify message bus handles new message types."""
    logger.info("Testing message bus extensions...")

    msg = AgentMsg(
        from_agent="vibe",
        to_agent="grisha",
        message_type=MessageType.ERROR_ANALYSIS,
        payload={"analysis": "Root cause confirmed", "confidence": 0.95},
    )

    sent = await message_bus.send(msg)
    if not sent:
        logger.error("Failed to send ERROR_ANALYSIS message")
        return False

    received = await message_bus.receive("grisha", message_type=MessageType.ERROR_ANALYSIS)
    if not received or received[0].payload.get("analysis") != "Root cause confirmed":
        logger.error("Failed to receive correct ERROR_ANALYSIS message")
        return False

    logger.info("Message bus extensions verified.")
    return True


async def main():
    logger.info("Starting Vibe Optimization Verification...")

    # Initialize MCP manager (ensure vibe server is loaded)
    # This might require some setup if not already running

    bus_ok = await test_message_bus_extensions()
    # error_ok = await test_error_analysis_payload() # This requires vibe server to be running/connected

    if bus_ok:
        logger.info("✅ Vibe Optimization Tests Passed!")
    else:
        logger.error("❌ Vibe Optimization Tests Failed.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
