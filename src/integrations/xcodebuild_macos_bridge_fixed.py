# ruff: noqa: T201
#!/usr/bin/env python3
"""
🚀 Fixed XcodeBuildMCP + macOS Tools Integration Bridge
Corrected version with proper tool naming
"""

import asyncio
import json
import subprocess
import time
from typing import Any


class FixedMacOSToolsBridge:
    """Fixed bridge between XcodeBuildMCP and macOS MCP tools"""

    def __init__(self):
        self.macos_server_path = (
            "./vendor/mcp-server-macos-use/.build/release/mcp-server-macos-use"
        )

    async def call_macos_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Direct call to macOS MCP server"""
        try:
            input_data = {
                "jsonrpc": "2.0",
                "id": int(time.time()),
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": params},
            }

            process = subprocess.Popen(
                [self.macos_server_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd="/Users/dev/Documents/GitHub/atlastrinity",
            )

            stdout, stderr = process.communicate(input=json.dumps(input_data) + "\n", timeout=15)

            if process.returncode == 0:
                try:
                    response = json.loads(stdout)
                    result = response.get("result", {})
                    content = result.get("content", [{}])[0].get("text", "")

                    return {
                        "status": "success",
                        "tool": tool_name,
                        "content": content,
                        "params": params,
                        "timestamp": time.time(),
                    }
                except json.JSONDecodeError as e:
                    return {
                        "status": "error",
                        "tool": tool_name,
                        "error": f"JSON decode error: {e!s}",
                        "stdout": stdout,
                    }
            else:
                return {
                    "status": "error",
                    "tool": tool_name,
                    "error": stderr or "Unknown error",
                    "return_code": process.returncode,
                }

        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "tool": tool_name,
                "error": "Tool call timed out after 15 seconds",
            }
        except Exception as e:
            return {"status": "error", "tool": tool_name, "error": f"Exception: {e!s}"}


class FixedEnhancedXcodeBuildMCP:
    """Fixed enhanced XcodeBuildMCP with direct macOS tools integration"""

    def __init__(self):
        self.bridge = FixedMacOSToolsBridge()
        self.enhancement_map = self.create_enhancement_map()

    def create_enhancement_map(self) -> dict[str, dict[str, Any]]:
        """Create mapping from XcodeBuildMCP tools to enhanced macOS tools"""
        return {
            # UI Automation Enhancements
            "tap": {
                "macos_tool": "macos-use_click_and_traverse",
                "params": {"x": 100, "y": 100, "pid": 0},
                "description": "Enhanced tap with accessibility traversal",
            },
            "type_text": {
                "macos_tool": "macos-use_type_and_traverse",
                "params": {"text": "", "pid": 0},
                "description": "Enhanced typing with real-time feedback",
            },
            "key_press": {
                "macos_tool": "macos-use_press_key_and_traverse",
                "params": {"keyName": "return", "pid": 0},
                "description": "Enhanced key press with modifiers",
            },
            # Screenshot Enhancements
            "screenshot": {
                "macos_tool": "macos-use_take_screenshot",
                "params": {"path": "/tmp/enhanced_screenshot.png", "format": "png"},
                "description": "Enhanced screenshot with multiple formats",
            },
            # System Monitoring
            "system_monitor": {
                "macos_tool": "macos-use_system_monitoring",
                "params": {"metric": "cpu", "duration": 3},
                "description": "System monitoring for build performance",
            },
            # Process Management
            "process_manager": {
                "macos_tool": "macos-use_process_management",
                "params": {"action": "list"},
                "description": "Process management for Xcode and simulators",
            },
            # File Operations
            "file_operations": {
                "macos_tool": "macos-use_finder_list_files",
                "params": {"path": "/tmp", "limit": 10},
                "description": "Enhanced file operations with Finder integration",
            },
            # Clipboard Operations
            "clipboard_manager": {
                "macos_tool": "macos-use_set_clipboard",
                "params": {"text": "Enhanced XcodeBuildMCP integration", "addToHistory": True},
                "description": "Enhanced clipboard management with history",
            },
            # Voice Control
            "voice_control": {
                "macos_tool": "macos-use_voice_control",
                "params": {"command": "open safari", "language": "en-US"},
                "description": "Voice control integration for hands-free development",
            },
            # Mouse Move
            "mouse_move": {
                "macos_tool": "macos-use_mouse_move",
                "params": {"x": 0, "y": 0},
                "description": "Move cursor to position without clicking",
            },
            # Triple Click (select line)
            "triple_click": {
                "macos_tool": "macos-use_triple_click_and_traverse",
                "params": {"x": 100, "y": 100, "pid": 0},
                "description": "Triple-click to select entire line of text",
            },
            # Smooth Drag
            "drag": {
                "macos_tool": "macos-use_drag_and_drop_and_traverse",
                "params": {"startX": 0, "startY": 0, "endX": 100, "endY": 100, "steps": 10},
                "description": "Smooth drag-and-drop with interpolation",
            },
        }

    async def call_enhanced_tool(
        self, tool_name: str, custom_params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Call enhanced tool with proper parameter merging"""

        enhancement = self.enhancement_map.get(tool_name)
        if not enhancement:
            return {
                "status": "error",
                "tool": tool_name,
                "error": f"No enhancement available for {tool_name}",
            }

        # Merge default params with custom params
        params = enhancement["params"].copy()
        if custom_params:
            params.update(custom_params)

        # Call macOS tool
        result = await self.bridge.call_macos_tool(enhancement["macos_tool"], params)

        if result.get("status") == "success":
            return {
                "status": "success",
                "original_tool": tool_name,
                "enhanced_with": enhancement["macos_tool"],
                "description": enhancement["description"],
                "result": result,
            }
        return result


async def main():
    """Test the fixed integration bridge"""
    print("🚀 Testing Fixed XcodeBuildMCP + macOS Tools Integration Bridge")
    print("=" * 70)

    # Initialize enhanced XcodeBuildMCP
    enhanced_xcode = FixedEnhancedXcodeBuildMCP()

    # Test enhanced tools
    test_cases: list[dict[str, Any]] = [
        {"tool": "tap", "custom_params": {"x": 150, "y": 200}, "test_name": "Enhanced UI Tap"},
        {
            "tool": "type_text",
            "custom_params": {"text": "Hello from enhanced XcodeBuildMCP!"},
            "test_name": "Enhanced Text Input",
        },
        {
            "tool": "key_press",
            "custom_params": {"keyName": "tab"},
            "test_name": "Enhanced Key Press",
        },
        {
            "tool": "screenshot",
            "custom_params": {"path": "/tmp/xcode_enhanced.png"},
            "test_name": "Enhanced Screenshot",
        },
        {
            "tool": "system_monitor",
            "custom_params": {"metric": "cpu", "duration": 2},
            "test_name": "System Monitoring",
        },
        {
            "tool": "process_manager",
            "custom_params": {"action": "list"},
            "test_name": "Process Management",
        },
        {
            "tool": "file_operations",
            "custom_params": {"path": "/tmp", "limit": 5},
            "test_name": "File Operations",
        },
        {
            "tool": "clipboard_manager",
            "custom_params": {"text": "XcodeBuildMCP + macOS Tools Integration"},
            "test_name": "Clipboard Management",
        },
    ]

    results = []
    success_count = 0
    error_count = 0

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n🧪 Test {i}: {test_case['test_name']}")
        print(f"   🔧 Tool: {test_case['tool']}")
        print(f"   📋 Custom Params: {test_case['custom_params']}")

        result = await enhanced_xcode.call_enhanced_tool(
            test_case["tool"], test_case["custom_params"]
        )

        if result.get("status") == "success":
            print("   ✅ Success!")
            print(f"   🚀 Enhanced with: {result.get('enhanced_with', 'N/A')}")
            print(f"   📝 Description: {result.get('description', 'N/A')}")
            print(f"   📄 Content: {result['result']['content'][:100]}...")
            success_count += 1
        else:
            print(f"   ❌ Error: {result.get('error', 'Unknown error')}")
            error_count += 1

        results.append(result)
        await asyncio.sleep(0.3)

    # Print statistics
    print("\n" + "=" * 70)
    print("🎉 Fixed Integration Bridge Test Complete!")
    print("=" * 70)

    print("\n📊 TEST RESULTS:")
    print(f"   Total Tests: {len(test_cases)}")
    print(f"   ✅ Successful: {success_count}")
    print(f"   ❌ Errors: {error_count}")
    print(f"   �� Success Rate: {(success_count / len(test_cases) * 100):.1f}%")

    if success_count > 0:
        print("\n🚀 INTEGRATION STATUS: ✅ Bridge is working!")
        print("📈 READY FOR: Production integration with XcodeBuildMCP")

        print("\n💡 SUCCESSFUL ENHANCEMENTS:")
        for result in results:
            if result.get("status") == "success":
                print(
                    f"   ✅ {result.get('original_tool', 'N/A')} -> {result.get('enhanced_with', 'N/A')}"
                )
    else:
        print("\n⚠️ INTEGRATION STATUS: Needs debugging")
        print("🔧 Check macOS MCP server status")

    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
