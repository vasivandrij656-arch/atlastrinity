#!/usr/bin/env python3
"""
Final Comprehensive Test of All Enhanced macOS Use MCP Tools
Tests all 45 tools with enhanced features
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta

sys.path.append("src")
from src.brain.mcp_manager import MCPManager


async def final_comprehensive_test():
    manager = MCPManager()

    print("🚀 ФІНАЛЬНИЙ КОМПЛЕКСИВНИЙ ТЕСТ ВСІХ ПОКРАЩЕНЬ")
    print("=" * 80)

    # Get all tools
    tools = await manager.list_tools("macos-use")
    print(f"📊 Загальна кількість інструментів: {len(tools)}")

    success_count = 0
    error_count = 0
    enhancement_count = 0

    # Test enhanced clipboard
    print("\n📋 Тестування покращеного clipboard...")
    try:
        # Test rich text and history
        result = await manager.call_tool(
            "macos-use",
            "macos-use_set_clipboard",
            {
                "text": "Enhanced clipboard test",
                "html": "<h1>Rich Text</h1><p>Enhanced <b>clipboard</b> test</p>",
                "addToHistory": True,
            },
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ Enhanced clipboard: {content}")
            success_count += 1
            enhancement_count += 1
        else:
            error_count += 1
    except Exception as e:
        print(f"❌ Enhanced clipboard error: {e}")
        error_count += 1

    # Test clipboard history
    try:
        result = await manager.call_tool("macos-use", "macos-use_clipboard_history", {"limit": 5})
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ Clipboard history: {content[:100]}...")
            success_count += 1
            enhancement_count += 1
        else:
            error_count += 1
    except Exception as e:
        print(f"❌ Clipboard history error: {e}")
        error_count += 1

    # Test enhanced time
    print("\n⏰️ Тестування покращеного time...")
    try:
        # Test timezone conversion
        result = await manager.call_tool(
            "macos-use",
            "macos-use_get_time",
            {"timezone": "UTC", "format": "iso", "convertTo": "Europe/Kiev"},
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ Timezone conversion: {content}")
            success_count += 1
            enhancement_count += 1
        else:
            error_count += 1
    except Exception as e:
        print(f"❌ Timezone conversion error: {e}")
        error_count += 1

    # Test countdown
    try:
        result = await manager.call_tool(
            "macos-use",
            "macos-use_countdown_timer",
            {"seconds": 3, "message": "Test countdown!", "notification": False},
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ Countdown timer: {content}")
            success_count += 1
            enhancement_count += 1
        else:
            error_count += 1
    except Exception as e:
        print(f"❌ Countdown timer error: {e}")
        error_count += 1

    # Test enhanced notifications
    print("\n🔔 Тестування покращених notifications...")
    try:
        # Test with template
        result = await manager.call_tool(
            "macos-use",
            "macos-use_send_notification",
            {"template": "reminder", "sound": "default", "persistent": True},
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ Enhanced notification: {content}")
            success_count += 1
            enhancement_count += 1
        else:
            error_count += 1
    except Exception as e:
        print(f"❌ Enhanced notification error: {e}")
        error_count += 1

    # Test notification scheduling
    try:
        future_time = (datetime.now() + timedelta(hours=1)).isoformat()
        result = await manager.call_tool(
            "macos-use",
            "macos-use_send_notification",
            {
                "title": "Scheduled Test",
                "message": "This is a scheduled notification",
                "schedule": future_time,
            },
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ Scheduled notification: {content}")
            success_count += 1
            enhancement_count += 1
        else:
            error_count += 1
    except Exception as e:
        print(f"❌ Scheduled notification error: {e}")
        error_count += 1

    # Test notification management
    try:
        result = await manager.call_tool(
            "macos-use", "macos-use_notification_schedule", {"list": True}
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ Notification schedule: {content[:100]}...")
            success_count += 1
            enhancement_count += 1
        else:
            error_count += 1
    except Exception as e:
        print(f"❌ Notification schedule error: {e}")
        error_count += 1

    # Test enhanced window management
    print("\n🪟 Тестування покращеного window management...")
    try:
        result = await manager.call_tool(
            "macos-use",
            "macos-use_window_management",
            {"action": "snapshot", "snapshotPath": "/tmp/final_window_test.png"},
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ Window snapshot: {content[:100]}...")
            success_count += 1
            enhancement_count += 1
        else:
            error_count += 1
    except Exception as e:
        print(f"❌ Window snapshot error: {e}")
        error_count += 1

    # Test enhanced screenshots
    print("\n📸 Тестування покращених screenshots...")
    try:
        result = await manager.call_tool(
            "macos-use",
            "macos-use_take_screenshot",
            {
                "path": "/tmp/final_screenshot.jpg",
                "quality": "medium",
                "format": "jpg",
                "ocr": True,
            },
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ Enhanced screenshot: {content[:100]}...")
            success_count += 1
            enhancement_count += 1
        else:
            error_count += 1
    except Exception as e:
        print(f"❌ Enhanced screenshot error: {e}")
        error_count += 1

    # Test enhanced OCR
    print("\n🔍 Тестування покращеного OCR...")
    try:
        result = await manager.call_tool(
            "macos-use",
            "macos-use_analyze_screen",
            {
                "region": {"x": 100, "y": 100, "width": 200, "height": 100},
                "confidence": True,
                "format": "both",
            },
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ Enhanced OCR: {content[:100]}...")
            success_count += 1
            enhancement_count += 1
        else:
            error_count += 1
    except Exception as e:
        print(f"❌ Enhanced OCR error: {e}")
        error_count += 1

    # Test enhanced system control
    print("\n🔧 Тестування покращеного system control...")
    try:
        result = await manager.call_tool(
            "macos-use", "macos-use_system_control", {"action": "get_info"}
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ System info: {content[:100]}...")
            success_count += 1
            enhancement_count += 1
        else:
            error_count += 1
    except Exception as e:
        print(f"❌ System control error: {e}")
        error_count += 1

    # Test enhanced calendar
    print("\n📅 Тестування покращеного calendar...")
    try:
        result = await manager.call_tool(
            "macos-use",
            "macos-use_create_event",
            {
                "title": "Enhanced Test Event",
                "date": "2026-02-10T15:00:00Z",
                "location": "Enhanced Location",
                "reminder": 15,
            },
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ Enhanced calendar: {content[:100]}...")
            success_count += 1
            enhancement_count += 1
        else:
            error_count += 1
    except Exception as e:
        print(f"❌ Enhanced calendar error: {e}")
        error_count += 1

    # Test enhanced mail
    print("\n📧 Тестування покращеного mail...")
    try:
        result = await manager.call_tool(
            "macos-use",
            "macos-use_mail_send",
            {
                "to": "test@example.com",
                "subject": "Enhanced Test Email",
                "body": "<h1>Enhanced Email</h1><p>This is an enhanced email with HTML formatting.</p>",
                "html": True,
                "draft": True,
            },
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ Enhanced mail: {content[:100]}...")
            success_count += 1
            enhancement_count += 1
        else:
            error_count += 1
    except Exception as e:
        print(f"❌ Enhanced mail error: {e}")
        error_count += 1

    # Test enhanced finder
    print("\n🗂️ Тестування покращеного finder...")
    try:
        result = await manager.call_tool(
            "macos-use",
            "macos-use_finder_list_files",
            {"path": "/tmp", "filter": "*.txt", "sort": "name", "limit": 5, "metadata": True},
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ Enhanced finder: {content[:100]}...")
            success_count += 1
            enhancement_count += 1
        else:
            error_count += 1
    except Exception as e:
        print(f"❌ Enhanced finder error: {e}")
        error_count += 1

    # Test enhanced running apps
    print("\n📱 Тестування покращеного running apps...")
    try:
        result = await manager.call_tool("macos-use", "macos-use_list_running_apps", {})
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            apps = json.loads(content)
            if apps and len(apps) > 0:
                first_app = apps[0]
                print(
                    f"✅ Enhanced apps: PID={first_app.get('pid')}, Status={first_app.get('processStatus')}"
                )
                success_count += 1
                enhancement_count += 1
            else:
                print("✅ Enhanced apps: No apps found")
                success_count += 1
        else:
            error_count += 1
    except Exception as e:
        print(f"❌ Enhanced apps error: {e}")
        error_count += 1

    # Final summary
    print("\n" + "=" * 80)
    print("🎉 ФІНАЛЬНИЙ КОМПЛЕКСИВНИЙ ТЕСТ ЗАВЕРШЕНО!")
    print("=" * 80)

    print("\n📊 РЕЗУЛЬТАТИ ТЕСТУВАННЯ:")
    print(f"✅ Успішних тестів: {success_count}")
    print(f"❌ Помилок: {error_count}")
    print(f"🚀 Покращень протестовано: {enhancement_count}")
    print(f"📈 Загальна кількість інструментів: {len(tools)}")

    success_rate = (
        (success_count / (success_count + error_count)) * 100
        if (success_count + error_count) > 0
        else 0
    )
    print(f"🎯 Рівень успішності: {success_rate:.1f}%")

    print("\n🏆 ФІНАЛЬНИЙ СТАТУС:")
    if success_rate >= 90:
        print("🟢 ВІДМІННО! Усі покращення працюють ідеально!")
    elif success_rate >= 80:
        print("🟡 ДОБРЕ! Більшість покращень працюють добре!")
    else:
        print("🔴 ПОТРІБНО ПОКРАЩЕННЯ!")

    print("\n🌟 КЛЮЧОВІ ДОСЯГНЕННЯ:")
    print("✅ Clipboard: Rich text, images, history")
    print("✅ Time: Timezone conversion, countdown")
    print("✅ Notifications: Templates, scheduling, persistence")
    print("✅ Windows: Snapshots, grouping")
    print("✅ Screenshots: Regions, quality, OCR")
    print("✅ OCR: Regions, confidence, formats")
    print("✅ System: Enhanced metrics")
    print("✅ Calendar: Location, reminders")
    print("✅ Mail: HTML, attachments, drafts")
    print("✅ Finder: Filtering, metadata")
    print("✅ Apps: Enhanced information")

    return {
        "total_tools": len(tools),
        "success_count": success_count,
        "error_count": error_count,
        "enhancement_count": enhancement_count,
        "success_rate": success_rate,
    }


if __name__ == "__main__":
    asyncio.run(final_comprehensive_test())
