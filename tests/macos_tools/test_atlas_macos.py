#!/usr/bin/env python3
"""
AtlasTrinity Integration Test for macOS Use MCP Tools
Tests all working tools through the AtlasTrinity MCP system
"""

import asyncio
import sys
import time

sys.path.append("src")
from src.brain.mcp_manager import MCPManager

# Working tools with correct parameters
ATLAS_TOOLS = [
    # System Info
    ("macos-use_get_time", {}, "Get current time"),
    ("macos-use_list_running_apps", {}, "List running apps"),
    ("macos-use_list_all_windows", {}, "List all windows"),
    ("macos-use_list_tools_dynamic", {}, "List tools dynamically"),
    # Clipboard
    ("macos-use_get_clipboard", {}, "Get clipboard"),
    ("macos-use_set_clipboard", {"text": "AtlasTrinity MCP Test"}, "Set clipboard"),
    # Screen Analysis
    ("macos-use_analyze_screen", {}, "Analyze screen"),
    ("ocr", {}, "OCR alias"),
    ("analyze", {}, "Analyze alias"),
    # Network
    ("macos-use_fetch_url", {"url": "https://httpbin.org/json"}, "Fetch URL"),
    # AppleScript
    (
        "macos-use_run_applescript",
        {"script": 'return "AtlasTrinity test successful"'},
        "Run AppleScript",
    ),
    # System Control
    (
        "macos-use_send_notification",
        {"title": "AtlasTrinity", "message": "MCP Test"},
        "Send notification",
    ),
    ("macos-use_window_management", {"action": "list"}, "Window management"),
    ("macos-use_spotlight_search", {"query": "AtlasTrinity"}, "Spotlight search"),
    # Interface Control
    ("macos-use_click_and_traverse", {"x": 100, "y": 100}, "Click"),
    ("macos-use_double_click_and_traverse", {"x": 100, "y": 100}, "Double click"),
    ("macos-use_right_click_and_traverse", {"x": 100, "y": 100}, "Right click"),
    ("macos-use_type_and_traverse", {"text": "test"}, "Type text"),
    ("macos-use_press_key_and_traverse", {"keyName": "return"}, "Press key"),
    ("macos-use_scroll_and_traverse", {"direction": "down", "amount": 1}, "Scroll"),
    ("macos-use_refresh_traversal", {}, "Refresh traversal"),
    (
        "macos-use_open_application_and_traverse",
        {"identifier": "com.apple.TextEdit"},
        "Open TextEdit",
    ),
    # System Commands
    ("execute_command", {"command": "echo 'AtlasTrinity MCP Test'"}, "Execute command"),
    ("terminal", {"command": "echo 'Terminal via AtlasTrinity'"}, "Terminal command"),
]


async def test_via_atlas():
    """Test tools through AtlasTrinity MCP system"""
    print("🚀 AtlasTrinity MCP Integration Test")
    print("=" * 60)
    print(f"Testing {len(ATLAS_TOOLS)} tools through AtlasTrinity system")

    manager = MCPManager()
    results = {"success": 0, "error": 0, "total": len(ATLAS_TOOLS)}

    start_time = time.time()

    for i, (tool_name, args, description) in enumerate(ATLAS_TOOLS, 1):
        print(f"\n{'=' * 20} [{i}/{len(ATLAS_TOOLS)}] {'=' * 20}")
        print(f"🔧 [{tool_name}] {description}")
        print(f"📝 Args: {args}")

        try:
            result = await manager.call_tool("macos-use", tool_name, args)
            if result and hasattr(result, "content") and result.content:
                content = result.content[0].text if result.content else ""
                # Truncate long responses
                display = content[:80] + "..." if len(content) > 80 else content
                print(f"✅ Success: {display}")
                results["success"] += 1
            else:
                print("❌ No content received")
                results["error"] += 1

        except Exception as e:
            print(f"❌ Error: {str(e)[:50]}...")
            results["error"] += 1

        # Small delay between operations
        await asyncio.sleep(0.2)

    total_time = time.time() - start_time

    print("\n" + "=" * 60)
    print("📊 ATLASTRINITY TEST RESULTS")
    print("=" * 60)
    print(f"✅ Successful: {results['success']}/{results['total']}")
    print(f"❌ Errors: {results['error']}/{results['total']}")
    print(f"⏱️  Total Time: {total_time:.1f} seconds")
    print(f"📈 Success Rate: {(results['success'] / results['total']) * 100:.1f}%")

    if results["success"] >= results["total"] * 0.9:
        print("\n🎉 EXCELLENT! AtlasTrinity MCP integration working perfectly!")
    elif results["success"] >= results["total"] * 0.7:
        print("\n👍 GOOD! AtlasTrinity MCP integration working well!")
    else:
        print("\n⚠️  Some issues with AtlasTrinity MCP integration")

    print(f"\n🌟 AtlasTrinity confirmed working: {results['success']}/{len(ATLAS_TOOLS)} tools")


if __name__ == "__main__":
    try:
        asyncio.run(test_via_atlas())
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
