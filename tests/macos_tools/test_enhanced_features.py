#!/usr/bin/env python3
"""
Test Enhanced macOS Use MCP Tools
Tests all the new enhanced features
"""

import asyncio
import sys

sys.path.append("src")
from src.brain.mcp_manager import MCPManager


async def test_enhanced_features():
    manager = MCPManager()

    print("🚀 Testing Enhanced macOS Use MCP Tools")
    print("=" * 80)

    # Test 1: Enhanced Screenshot with region and quality
    print("\n📸 Testing Enhanced Screenshot...")
    try:
        result = await manager.call_tool(
            "macos-use",
            "macos-use_take_screenshot",
            {
                "path": "/tmp/enhanced_screenshot.jpg",
                "quality": "medium",
                "format": "jpg",
                "ocr": True,
            },
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ Enhanced screenshot: {content[:100]}...")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 2: Enhanced OCR with region and confidence
    print("\n🔍 Testing Enhanced OCR...")
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
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 3: Enhanced System Control with new actions
    print("\n🔧 Testing Enhanced System Control...")
    try:
        result = await manager.call_tool(
            "macos-use", "macos-use_system_control", {"action": "get_performance"}
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ System performance: {content[:100]}...")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 4: Enhanced Calendar with attendees and location
    print("\n📅 Testing Enhanced Calendar...")
    try:
        result = await manager.call_tool(
            "macos-use",
            "macos-use_create_event",
            {
                "title": "Enhanced Test Event",
                "date": "2026-02-10T15:00:00Z",
                "location": "Test Location",
                "notes": "Test notes with enhanced features",
                "reminder": 15,
            },
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ Enhanced calendar: {content[:100]}...")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 5: Enhanced Mail with HTML and attachments
    print("\n📧 Testing Enhanced Mail...")
    try:
        result = await manager.call_tool(
            "macos-use",
            "macos-use_mail_send",
            {
                "to": "test@example.com",
                "subject": "Enhanced Test Email",
                "body": "<h1>HTML Test</h1><p>This is an enhanced email with HTML formatting.</p>",
                "html": True,
                "draft": True,
            },
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ Enhanced mail: {content[:100]}...")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 6: Enhanced Finder with filtering and metadata
    print("\n🗂️ Testing Enhanced Finder...")
    try:
        result = await manager.call_tool(
            "macos-use",
            "macos-use_finder_list_files",
            {"path": "/tmp", "filter": "*.txt", "sort": "name", "limit": 5, "metadata": True},
        )
        if result and hasattr(result, "content") and result.content:
            content = result.content[0].text if result.content else ""
            print(f"✅ Enhanced finder: {content[:100]}...")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Test 7: Test all new system control actions
    print("\n🔧 Testing All New System Actions...")
    new_actions = ["get_info", "get_system_info", "get_performance", "get_network", "get_storage"]
    for action in new_actions:
        try:
            result = await manager.call_tool(
                "macos-use", "macos-use_system_control", {"action": action}
            )
            if result and hasattr(result, "content") and result.content:
                content = result.content[0].text if result.content else ""
                print(f"✅ {action}: {content[:50]}...")
        except Exception as e:
            print(f"❌ {action}: {e}")

    print("\n" + "=" * 80)
    print("🎉 Enhanced Features Test Complete!")
    print("=" * 80)


asyncio.run(test_enhanced_features())
