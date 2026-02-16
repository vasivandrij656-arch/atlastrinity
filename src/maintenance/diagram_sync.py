"""
Wrapper script to call devtools_update_architecture_diagrams via MCP.
This is used by npm scripts to trigger automatic diagram updates.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.brain.mcp_manager import mcp_manager


async def main():
    """Call devtools MCP to update architecture diagrams."""
    manager = mcp_manager

    try:
        # Call the tool
        result = await manager.call_tool(
            server_name="devtools",
            tool_name="devtools_update_architecture_diagrams",
            arguments={
                "project_path": None,  # None = AtlasTrinity internal
                "commits_back": 1,
                "target_mode": "internal",
            },
        )

        if hasattr(result, "structuredContent") and result.structuredContent:
            res_data = result.structuredContent
        elif isinstance(result, dict):
            res_data = result
        elif hasattr(result, "content") and result.content:
            # Try to parse text content as JSON if it's a list of TextContent
            import json

            try:
                res_data = json.loads(result.content[0].text)
            except (IndexError, AttributeError, json.JSONDecodeError):
                sys.exit(1)
        else:
            sys.exit(1)

        if res_data.get("success"):
            if res_data.get("files_updated"):
                for _ in res_data["files_updated"]:
                    pass
            if not res_data.get("updates_made"):
                pass
        else:
            res_data.get("error", "Unknown error")
            sys.exit(1)

    except Exception:
        sys.exit(1)
    finally:
        await manager.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
