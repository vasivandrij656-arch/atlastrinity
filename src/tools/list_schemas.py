import asyncio
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.getcwd(), "src"))
sys.path.insert(0, PROJECT_ROOT)

from src.brain.mcp_manager import mcp_manager  # pyre-ignore


async def get_schemas():
    for server in ["vibe"]:
        tools = await mcp_manager.list_tools(server)
        result = []
        for t in tools:
            schema = {
                "name": t.name,
                "description": getattr(t, "description", ""),
                "inputSchema": getattr(t, "inputSchema", {}),
            }
            result.append(schema)


if __name__ == "__main__":
    asyncio.run(get_schemas())
