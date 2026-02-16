#!/usr/bin/env python3
"""
Complete Test for All 42 macOS Use MCP Tools via AtlasTrinity DevTools
Tests every tool with correct parameters through the native devtools system
"""

import asyncio
import json
import sys
import time

sys.path.append("src")
from src.brain.mcp_manager import MCPManager

# All 42 tools with correct parameters
ALL_42_TOOLS = [
    # System Info (4)
    ("macos-use_get_time", {}, "Get current system time"),
    ("macos-use_list_running_apps", {}, "List running applications"),
    ("macos-use_list_all_windows", {}, "List all windows"),
    ("macos-use_list_tools_dynamic", {}, "List all tools dynamically"),
    # Finder (4)
    ("macos-use_finder_list_files", {"path": "/tmp"}, "List files in /tmp"),
    ("macos-use_finder_get_selection", {}, "Get current Finder selection"),
    ("macos-use_finder_open_path", {"path": "/tmp"}, "Open /tmp in Finder"),
    ("macos-use_finder_move_to_trash", {"path": "/tmp/test_file.txt"}, "Move file to trash"),
    # Clipboard (2)
    ("macos-use_get_clipboard", {}, "Get clipboard content"),
    ("macos-use_set_clipboard", {"text": "AtlasTrinity Complete Test"}, "Set clipboard content"),
    # Screenshots & OCR (5)
    (
        "macos-use_take_screenshot",
        {"path": "/tmp/complete_test_screenshot.png"},
        "Take screenshot to file",
    ),
    ("screenshot", {"path": "/tmp/alias_screenshot.png"}, "Screenshot alias to file"),
    ("macos-use_analyze_screen", {}, "Analyze screen content"),
    ("ocr", {}, "OCR alias"),
    ("analyze", {}, "Analyze alias"),
    # Web & Network (2)
    ("macos-use_fetch_url", {"url": "https://httpbin.org/json"}, "Fetch JSON from URL"),
    ("macos-use_list_browser_tabs", {"browser": "safari"}, "List Safari tabs"),
    # Notes (3)
    ("macos-use_notes_list_folders", {}, "List Notes folders"),
    ("macos-use_notes_get_content", {"name": "Test Note"}, "Get Notes content"),
    (
        "macos-use_notes_create_note",
        {"body": "Complete test note content", "folder": "Notes"},
        "Create note",
    ),
    # Calendar (2)
    (
        "macos-use_calendar_events",
        {"start": "2026-02-09T00:00:00Z", "end": "2026-02-10T00:00:00Z"},
        "Get calendar events",
    ),
    (
        "macos-use_create_event",
        {"title": "Complete Test Event", "date": "2026-02-10T12:00:00Z"},
        "Create event",
    ),
    # Reminders (2)
    ("macos-use_reminders", {}, "Get reminders"),
    ("macos-use_create_reminder", {"title": "Complete Test Reminder"}, "Create reminder"),
    # Mail (2)
    ("macos-use_mail_read_inbox", {"limit": 3}, "Read mail inbox"),
    (
        "macos-use_mail_send",
        {"to": "test@example.com", "subject": "Complete Test", "body": "Complete test email"},
        "Send test email",
    ),
    # AppleScript (1)
    (
        "macos-use_run_applescript",
        {"script": 'return "Complete test successful"'},
        "Run AppleScript",
    ),
    # System Control (1)
    ("macos-use_system_control", {"action": "get_info"}, "System control get_info"),
    # Search (1)
    ("macos-use_spotlight_search", {"query": "AtlasTrinity"}, "Spotlight search"),
    # Notifications (1)
    (
        "macos-use_send_notification",
        {"title": "Complete Test", "message": "Testing all 42 tools"},
        "Send notification",
    ),
    # Traversal & Interaction (8)
    ("macos-use_click_and_traverse", {"x": 100, "y": 100}, "Click and traverse"),
    ("macos-use_double_click_and_traverse", {"x": 100, "y": 100}, "Double click and traverse"),
    ("macos-use_right_click_and_traverse", {"x": 100, "y": 100}, "Right click and traverse"),
    ("macos-use_type_and_traverse", {"text": "test"}, "Type and traverse"),
    ("macos-use_press_key_and_traverse", {"keyName": "return"}, "Press key and traverse"),
    ("macos-use_scroll_and_traverse", {"direction": "down", "amount": 1}, "Scroll and traverse"),
    ("macos-use_refresh_traversal", {}, "Refresh traversal"),
    (
        "macos-use_open_application_and_traverse",
        {"identifier": "com.apple.TextEdit"},
        "Open app and traverse",
    ),
    # Window Management (1)
    ("macos-use_window_management", {"action": "list"}, "Window management"),
    # System Commands (2)
    ("execute_command", {"command": "echo 'Complete AtlasTrinity Test'"}, "Execute system command"),
    ("terminal", {"command": "echo 'Terminal Complete Test'"}, "Terminal command"),
]


async def test_all_42_tools():
    """Test all 42 macOS Use MCP tools via AtlasTrinity"""
    print("🚀 COMPLETE TEST for All 42 macOS Use MCP Tools")
    print("=" * 80)
    print(f"Testing ALL {len(ALL_42_TOOLS)} tools via AtlasTrinity DevTools")

    manager = MCPManager()
    results = {"success": 0, "error": 0, "timeout": 0, "total": len(ALL_42_TOOLS)}

    start_time = time.time()

    for i, (tool_name, args, description) in enumerate(ALL_42_TOOLS, 1):
        print(f"\n{'=' * 25} [{i}/{len(ALL_42_TOOLS)}] {'=' * 25}")
        print(f"🔧 [{tool_name}] {description}")
        print(f"📝 Args: {args}")

        try:
            # Use shorter timeout for faster testing
            result = await asyncio.wait_for(
                manager.call_tool("macos-use", tool_name, args), timeout=20.0
            )

            if result and hasattr(result, "content") and result.content:
                content = result.content[0].text if result.content else ""
                # Truncate long responses
                display = content[:100] + "..." if len(content) > 100 else content
                print(f"✅ Success: {display}")
                results["success"] += 1
            else:
                print("❌ No content received")
                results["error"] += 1

        except TimeoutError:
            print("⏰ Timeout after 20s")
            results["timeout"] += 1
        except Exception as e:
            print(f"❌ Error: {str(e)[:50]}...")
            results["error"] += 1

        # Small delay between operations
        await asyncio.sleep(0.3)

    total_time = time.time() - start_time

    print("\n" + "=" * 80)
    print("📊 COMPLETE TEST RESULTS - ALL 42 TOOLS")
    print("=" * 80)
    print(f"✅ Successful: {results['success']}/{results['total']}")
    print(f"❌ Errors: {results['error']}/{results['total']}")
    print(f"⏰ Timeouts: {results['timeout']}/{results['total']}")
    print(f"⏱️  Total Time: {total_time:.1f} seconds")
    print(f"📈 Success Rate: {(results['success'] / results['total']) * 100:.1f}%")

    if results["success"] == results["total"]:
        print("\n🎉 PERFECT! ALL 42 TOOLS WORKING!")
    elif results["success"] >= results["total"] * 0.9:
        print("\n🏆 EXCELLENT! 90%+ tools working!")
    elif results["success"] >= results["total"] * 0.8:
        print("\n👍 GREAT! 80%+ tools working!")
    elif results["success"] >= results["total"] * 0.7:
        print("\n✅ GOOD! Majority of tools working!")
    else:
        print("\n⚠️  NEEDS IMPROVEMENT")

    print(f"\n🌟 Final Status: {results['success']}/42 tools working")

    # Create test summary
    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_tools": results["total"],
        "successful": results["success"],
        "errors": results["error"],
        "timeouts": results["timeout"],
        "success_rate": (results["success"] / results["total"]) * 100,
        "total_time_seconds": total_time,
    }

    with open("/tmp/macos_complete_test_results.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\n📋 Results saved to: /tmp/macos_complete_test_results.json")


if __name__ == "__main__":
    try:
        asyncio.run(test_all_42_tools())
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
