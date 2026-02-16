import asyncio
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from src.brain.mcp.mcp_manager import mcp_manager  # pyre-ignore


async def test_restart():
    """Test the restart_mcp_server functionality.
    We will target a less critical server like 'filesystem' or 'memory'.
    """
    target_server = "filesystem"
    manager = mcp_manager
    # Ensure server is running
    await manager.get_session(target_server)

    # 1. Check if it's running
    await manager.health_check(target_server)

    if target_server not in manager.sessions and target_server not in manager._connection_tasks:
        # Note: sessions might be empty if connected but not used, but connection task should be there
        pass

    # We grab the session object if possible
    original_client = await manager.get_session(target_server)

    # 2. Restart
    success = await manager.restart_server(target_server)

    if success:
        pass
    else:
        await manager.cleanup()
        return

    # 3. Check new state
    new_client = await manager.get_session(target_server)

    if id(new_client) != id(original_client):
        pass
    else:
        pass

    # 4. Cleanup
    await manager.cleanup()


if __name__ == "__main__":
    asyncio.run(test_restart())
