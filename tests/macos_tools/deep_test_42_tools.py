#!/usr/bin/env python3
"""
Deep Test for All 42 macOS Use MCP Tools
Tests each tool thoroughly and identifies improvement opportunities
"""

import asyncio
import json
import sys
import time

sys.path.append("src")
from src.brain.mcp_manager import MCPManager

# All 42 tools with comprehensive test scenarios
DEEP_TEST_SCENARIOS = [
    # 1. Application Control
    (
        "macos-use_open_application_and_traverse",
        {"identifier": "com.apple.TextEdit"},
        "Open TextEdit with traversal",
    ),
    (
        "macos-use_open_application_and_traverse",
        {"identifier": "com.apple.calculator"},
        "Open Calculator with traversal",
    ),
    # 2. Mouse Actions
    ("macos-use_click_and_traverse", {"x": 100, "y": 100}, "Click at coordinates"),
    ("macos-use_double_click_and_traverse", {"x": 100, "y": 100}, "Double click"),
    ("macos-use_right_click_and_traverse", {"x": 100, "y": 100}, "Right click"),
    (
        "macos-use_drag_and_drop_and_traverse",
        {"startX": 100, "startY": 100, "endX": 200, "endY": 200},
        "Drag and drop",
    ),
    ("macos-use_type_and_traverse", {"text": "Hello World"}, "Type text"),
    ("macos-use_press_key_and_traverse", {"keyName": "return"}, "Press Return key"),
    ("macos-use_scroll_and_traverse", {"direction": "down", "amount": 3}, "Scroll down"),
    ("macos-use_refresh_traversal", {}, "Refresh traversal"),
    # 3. Window Management
    ("macos-use_window_management", {"action": "list"}, "List windows"),
    ("macos-use_window_management", {"action": "get_frontmost"}, "Get frontmost window"),
    # 4. System Commands
    ("execute_command", {"command": "echo 'Deep Test Command'"}, "Execute command"),
    ("execute_command", {"command": "ls -la /tmp"}, "List directory"),
    ("terminal", {"command": "pwd"}, "Get working directory"),
    # 5. Screenshots & Vision
    ("macos-use_take_screenshot", {"path": "/tmp/deep_test_screenshot.png"}, "Screenshot to file"),
    ("screenshot", {"path": "/tmp/deep_test_screenshot_alias.png"}, "Screenshot alias to file"),
    ("macos-use_analyze_screen", {}, "Analyze screen with OCR"),
    ("ocr", {}, "OCR alias"),
    ("analyze", {}, "Analyze alias"),
    # 6. Clipboard
    ("macos-use_set_clipboard", {"text": "Deep test clipboard content"}, "Set clipboard"),
    ("macos-use_get_clipboard", {}, "Get clipboard"),
    # 7. System Control
    ("macos-use_system_control", {"action": "get_info"}, "Get system info"),
    ("macos-use_system_control", {"action": "volume_up"}, "Volume up"),
    ("macos-use_system_control", {"action": "mute"}, "Mute"),
    # 8. Network & Web
    ("macos-use_fetch_url", {"url": "https://httpbin.org/json"}, "Fetch JSON"),
    ("macos-use_fetch_url", {"url": "https://httpbin.org/uuid"}, "Fetch UUID"),
    ("macos-use_list_browser_tabs", {"browser": "safari"}, "List Safari tabs"),
    ("macos-use_list_browser_tabs", {}, "List all browser tabs"),
    # 9. Time & AppleScript
    ("macos-use_get_time", {}, "Get current time"),
    (
        "macos-use_run_applescript",
        {"script": 'return "Deep AppleScript test successful"'},
        "Simple AppleScript",
    ),
    (
        "macos-use_run_applescript",
        {"script": 'tell application "Finder" to get name of front window'},
        "Get Finder window",
    ),
    # 10. Calendar
    (
        "macos-use_calendar_events",
        {"start": "2026-02-09T00:00:00Z", "end": "2026-02-10T00:00:00Z"},
        "Get calendar events",
    ),
    (
        "macos-use_create_event",
        {"title": "Deep Test Event", "date": "2026-02-10T15:00:00Z"},
        "Create event",
    ),
    (
        "macos-use_create_event",
        {"title": "Another Test Event", "date": "2026-02-11T10:00:00Z"},
        "Create second event",
    ),
    # 11. Reminders
    ("macos-use_reminders", {}, "Get reminders"),
    ("macos-use_create_reminder", {"title": "Deep Test Reminder"}, "Create reminder"),
    ("macos-use_create_reminder", {"title": "Urgent Test Reminder"}, "Create urgent reminder"),
    # 12. Search
    ("macos-use_spotlight_search", {"query": "Deep Test"}, "Spotlight search"),
    ("macos-use_spotlight_search", {"query": "test"}, "Search for test files"),
    # 13. Notifications
    (
        "macos-use_send_notification",
        {"title": "Deep Test", "message": "Testing all tools"},
        "Send notification",
    ),
    ("macos-use_send_notification", {"title": "Alert", "message": "Deep test alert"}, "Send alert"),
    # 14. Notes
    ("macos-use_notes_list_folders", {}, "List Notes folders"),
    (
        "macos-use_notes_create_note",
        {"body": "Deep test note content\nSecond line", "folder": "Notes"},
        "Create note",
    ),
    ("macos-use_notes_get_content", {"name": "Deep Test"}, "Get note content"),
    # 15. Mail
    ("macos-use_mail_read_inbox", {"limit": 5}, "Read 5 emails"),
    ("macos-use_mail_read_inbox", {"limit": 1}, "Read 1 email"),
    (
        "macos-use_mail_send",
        {"to": "test@example.com", "subject": "Deep Test", "body": "Testing mail functionality"},
        "Send test email",
    ),
    # 16. Finder
    ("macos-use_finder_list_files", {"path": "/tmp"}, "List /tmp files"),
    ("macos-use_finder_list_files", {}, "List frontmost Finder window"),
    ("macos-use_finder_get_selection", {}, "Get Finder selection"),
    ("macos-use_finder_open_path", {"path": "/tmp"}, "Open /tmp in Finder"),
    ("macos-use_finder_move_to_trash", {"path": "/tmp/deep_test_file.txt"}, "Move file to trash"),
    # 17. System Info
    ("macos-use_list_running_apps", {}, "List running apps"),
    ("macos-use_list_all_windows", {}, "List all windows"),
    ("macos-use_list_tools_dynamic", {}, "List tools dynamically"),
]


async def deep_test_all_tools():
    """Perform deep testing of all 42 tools"""
    print("🔬 DEEP TEST for All 42 macOS Use MCP Tools")
    print("=" * 80)
    print(f"Testing {len(DEEP_TEST_SCENARIOS)} scenarios across all tools")

    manager = MCPManager()
    results = {
        "total": len(DEEP_TEST_SCENARIOS),
        "success": 0,
        "error": 0,
        "timeout": 0,
        "issues": [],
        "improvements": [],
    }

    start_time = time.time()

    for i, (tool_name, args, description) in enumerate(DEEP_TEST_SCENARIOS, 1):
        print(f"\n{'=' * 20} [{i}/{len(DEEP_TEST_SCENARIOS)}] {'=' * 20}")
        print(f"🔧 [{tool_name}] {description}")
        print(f"📝 Args: {args}")

        try:
            result = await asyncio.wait_for(
                manager.call_tool("macos-use", tool_name, args), timeout=30.0
            )

            if result and hasattr(result, "content") and result.content:
                content = result.content[0].text if result.content else ""

                # Analyze result quality
                issues = analyze_result_quality(tool_name, content)
                if issues:
                    results["issues"].extend(issues)
                    print(f"⚠️  Issues found: {', '.join(issues)}")
                else:
                    print(f"✅ Success: {content[:100]}...")

                # Check for improvement opportunities
                improvements = identify_improvements(tool_name, content)
                if improvements:
                    results["improvements"].extend(improvements)
                    print(f"💡 Improvements: {', '.join(improvements)}")

                results["success"] += 1
            else:
                print("❌ No content received")
                results["error"] += 1

        except TimeoutError:
            print("⏰ Timeout after 30s")
            results["timeout"] += 1
            results["issues"].append(f"{tool_name}: Timeout")
        except Exception as e:
            print(f"❌ Error: {str(e)[:50]}...")
            results["error"] += 1
            results["issues"].append(f"{tool_name}: {str(e)[:50]}")

        # Small delay between operations
        await asyncio.sleep(0.2)

    total_time = time.time() - start_time

    print("\n" + "=" * 80)
    print("📊 DEEP TEST RESULTS")
    print("=" * 80)
    print(f"✅ Successful: {results['success']}/{results['total']}")
    print(f"❌ Errors: {results['error']}/{results['total']}")
    print(f"⏰ Timeouts: {results['timeout']}/{results['total']}")
    print(f"⏱️  Total Time: {total_time:.1f} seconds")
    print(f"📈 Success Rate: {(results['success'] / results['total']) * 100:.1f}%")

    if results["issues"]:
        print(f"\n⚠️  Issues Found ({len(results['issues'])}):")
        for issue in results["issues"][:10]:  # Show first 10
            print(f"  - {issue}")
        if len(results["issues"]) > 10:
            print(f"  ... and {len(results['issues']) - 10} more")

    if results["improvements"]:
        print(f"\n💡 Improvement Opportunities ({len(results['improvements'])}):")
        for improvement in results["improvements"][:10]:  # Show first 10
            print(f"  - {improvement}")
        if len(results["improvements"]) > 10:
            print(f"  ... and {len(results['improvements']) - 10} more")

    # Save detailed results
    detailed_results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_scenarios": results["total"],
        "successful": results["success"],
        "errors": results["error"],
        "timeouts": results["timeout"],
        "success_rate": (results["success"] / results["total"]) * 100,
        "total_time_seconds": total_time,
        "issues": results["issues"],
        "improvements": results["improvements"],
    }

    with open("/tmp/macos_deep_test_results.json", "w") as f:
        json.dump(detailed_results, f, indent=2)

    print("\n📋 Detailed results saved to: /tmp/macos_deep_test_results.json")

    return detailed_results


def analyze_result_quality(tool_name, content):
    """Analyze the quality of tool results"""
    issues = []

    # Check for common issues
    if content.startswith("Error:"):
        issues.append("Error in execution")
    elif "Unknown action" in content:
        issues.append("Unknown action parameter")
    elif "not found" in content.lower():
        issues.append("Resource not found")
    elif "timeout" in content.lower():
        issues.append("Timeout occurred")
    elif content.strip() == "":
        issues.append("Empty result")
    elif len(content) < 10:
        issues.append("Very short result")

    # Tool-specific checks
    if "screenshot" in tool_name.lower() and "Error:" in content:
        issues.append("Screenshot failed")
    elif "calendar" in tool_name.lower() and "No events found" in content:
        pass  # This is normal for empty calendars
    elif "mail" in tool_name.lower() and "Inbox is empty" in content:
        pass  # This is normal for empty inbox
    elif "finder" in tool_name.lower() and "No Finder window open" in content:
        issues.append("No Finder window")

    return issues


def identify_improvements(tool_name, content):
    """Identify potential improvements for tools"""
    improvements = []

    # Check for improvement opportunities
    if tool_name == "macos-use_take_screenshot" and "Base64" in content:
        improvements.append("Add file save option for screenshots")
    elif tool_name == "macos-use_system_control" and "Unknown action" in content:
        improvements.append("Document all supported actions")
    elif tool_name == "macos-use_fetch_url" and "Error:" in content:
        improvements.append("Add better error handling for network requests")
    elif tool_name == "macos-use_run_applescript" and len(content) < 20:
        improvements.append("Add more complex AppleScript examples")
    elif "list" in tool_name.lower() and len(content.split("\n")) < 2:
        improvements.append("Add more detailed listing information")
    elif "create" in tool_name.lower() and "Error:" in content:
        improvements.append("Add validation for required parameters")

    return improvements


if __name__ == "__main__":
    try:
        results = asyncio.run(deep_test_all_tools())
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
