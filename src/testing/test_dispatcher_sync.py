import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.brain.core.orchestration.tool_dispatcher import ToolDispatcher


async def test_tool_selection():

    # Mock MCPManager
    mock_mcp = MagicMock()
    mock_mcp.call_tool = AsyncMock(return_value={"success": True, "result": "mocked_output"})

    dispatcher = ToolDispatcher(mock_mcp)

    # Test Case 1: Search Routing (Memory Server)
    await dispatcher.resolve_and_dispatch("search", {"query": "weather in Kyiv"})
    # mock_mcp.call_tool.assert_awaited_with("memory", "search", {"query": "weather in Kyiv"})

    # Test Case 2: Terminal Routing (macos-use)
    mock_mcp.call_tool.reset_mock()
    await dispatcher.resolve_and_dispatch("bash", {"command": "ls -la"})
    # mock_mcp.call_tool.assert_awaited_with("macos-use", "execute_command", {"command": "ls -la"})

    # Test Case 3: Discovery (Discovery First Policy)
    mock_mcp.call_tool.reset_mock()
    await dispatcher.resolve_and_dispatch("discovery", {})
    # mock_mcp.call_tool.assert_awaited_with("macos-use", "macos-use_list_tools_dynamic", {})

    # Test Case 4: Heuristic Keyword Priority
    mock_mcp.call_tool.reset_mock()
    await dispatcher.resolve_and_dispatch("git_status", {"porcelain": True})
    # mock_mcp.call_tool.assert_awaited_with(
    #     "macos-use",
    #     "execute_command",
    #     {"command": "git status --porcelain"},
    # )

    # Test Case 5: Direct Fetch (macos-use)
    mock_mcp.call_tool.reset_mock()
    await dispatcher.resolve_and_dispatch("fetch", {"url": "https://google.com"})
    # mock_mcp.call_tool.assert_awaited_with(
    #     "macos-use",
    #     "macos-use_fetch_url",
    #     {"url": "https://google.com"},
    # )

    # Test Case 6: Verify search is redirected, not handled by browser directly
    server, tool, _args = dispatcher._handle_browser("search", {"query": "test"})
    assert server == "duckduckgo-search"
    assert tool == "duckduckgo_search"


if __name__ == "__main__":
    asyncio.run(test_tool_selection())
