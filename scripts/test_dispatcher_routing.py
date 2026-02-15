import asyncio
import sys
import os
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.path.abspath("/Users/dev/Documents/GitHub/atlastrinity"))

from src.brain.core.orchestration.tool_dispatcher import ToolDispatcher

async def test_routing():
    # Mock MCPManager
    mock_mcp = MagicMock()
    dispatcher = ToolDispatcher(mock_mcp)
    
    test_cases = [
        ("macos-use.execute_command", {"command": "ls"}, "xcodebuild", "execute_command"),
        ("macos-use_take_screenshot", {}, "xcodebuild", "macos-use_take_screenshot"),
        ("execute_command", {"command": "pwd"}, "xcodebuild", "execute_command"),
        ("macos-use.macos-use_get_time", {}, "xcodebuild", "macos-use_get_time"),
    ]
    
    print("Running Routing Tests...")
    all_passed = True
    for tool_name, args, expected_server, expected_tool in test_cases:
        server, resolved_tool, normalized_args = dispatcher._resolve_routing(tool_name, args, None)
        passed = (server == expected_server and resolved_tool == expected_tool)
        print(f"[{'PASS' if passed else 'FAIL'}] {tool_name} -> {server}.{resolved_tool} (Expected: {expected_server}.{expected_tool})")
        if not passed:
            all_passed = False
            
    if all_passed:
        print("\nAll routing tests PASSED!")
    else:
        print("\nSome routing tests FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_routing())
