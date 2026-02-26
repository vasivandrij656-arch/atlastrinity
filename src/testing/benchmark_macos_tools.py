# ruff: noqa: T201
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from src.brain.mcp_manager import MCPManager


async def test_tool(mcp_manager, tool_name, arguments):
    print(f"Testing Tool: {tool_name:30}", end=" ", flush=True)
    try:
        # Use dispatch_tool which handles resolution and execution
        result = await mcp_manager.dispatch_tool(tool_name, arguments)

        # Check success
        success = False
        if (
            (isinstance(result, dict) and result.get("success"))
            or (not isinstance(result, dict | list) and getattr(result, "is_error", False) is False)
            or (isinstance(result, list) and len(result) > 0)
        ):
            success = True

        if success:
            print("[\033[92mPASS\033[0m]")
            return True, result
        print("[\033[91mFAIL\033[0m]")
        return False, str(result)
    except Exception as e:
        print("[\033[91mEXCEPTION\033[0m]")
        return False, str(e)


async def main():
    # Initialize MCPManager
    mcp_manager = MCPManager()

    # Optional: wait a bit for config loading
    await asyncio.sleep(1)

    test_cases = [
        # --- UI Automation ---
        ("macos-use_click_and_traverse", {"x": 100, "y": 100, "showAnimation": True}),
        ("macos-use_type_and_traverse", {"text": "Hello World"}),
        ("macos-use_press_key_and_traverse", {"keyName": "Return"}),
        ("macos-use_scroll_and_traverse", {"direction": "down", "amount": 3}),
        # --- System ---
        ("macos-use_get_storage_info", {}),
        ("macos-use_get_time", {"format": "iso"}),
        ("macos-use_list_running_apps", {}),
        ("macos-use_list_all_windows", {}),
        # --- Media & System ---
        ("macos-use_system_control", {"action": "get_system_info"}),
        ("macos-use_system_monitoring", {"metric": "disk"}),
        ("notify", {"title": "Ultimate Interaction", "message": "Verification Complete"}),
        # --- Notifications ---
        (
            "macos-use_send_notification",
            {"title": "Test Notification", "message": "Atlas Trinity Testing Phase 8"},
        ),
        # --- Finder ---
        ("macos-use_finder_list_files", {"path": os.getcwd(), "limit": 5}),
        ("macos-use_finder_get_selection", {}),
        # --- Clipboard ---
        ("macos-use_set_clipboard", {"text": "Atlas Trinity Test Content", "showAnimation": True}),
        ("macos-use_get_clipboard", {}),
        ("macos-use_clipboard_history", {"list": True}),
        # --- Personal Info ---
        (
            "macos-use_calendar_events",
            {"start": "2026-01-01T00:00:00Z", "end": "2026-12-31T23:59:59Z"},
        ),
        ("macos-use_reminders", {"list": "Reminders"}),
        ("macos-use_notes_list_folders", {}),
        ("macos-use_mail_read_inbox", {"limit": 2}),
        # --- Search/Discovery ---
        ("macos-use_spotlight_search", {"query": "Atlas"}),
        ("macos-use_list_tools_dynamic", {}),
        # --- Vision ---
        ("macos-use_take_screenshot", {"format": "png", "ocr": True}),
        ("macos-use_analyze_screen", {"format": "text"}),
        # --- Synonyms check ---
        ("screenshot", {}),
        ("ocr", {}),
        ("applescript", {"script": 'display notification "Hello from AppleScript"'}),
        ("ls", {"path": "/"}),
        ("notify", {"title": "Synonym Test", "message": "Works!"}),
    ]

    results = []
    print("=" * 60)
    print("STARTING EXHAUSTIVE TOOL TEST")
    print("=" * 60)

    for tool, args in test_cases:
        success, output = await test_tool(mcp_manager, tool, args)
        results.append({"tool": tool, "success": success, "error": output if not success else None})
        print("-" * 40)

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = len([r for r in results if r["success"]])
    failed = len(results) - passed
    print(f"Total: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        print("\nFailed Tools:")
        for r in results:
            if not r["success"]:
                print(f"- {r['tool']}: {r['error']}")


if __name__ == "__main__":
    asyncio.run(main())
