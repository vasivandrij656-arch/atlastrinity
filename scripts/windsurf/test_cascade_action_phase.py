#!/usr/bin/env python3
"""
Automated test script for Windsurf MCP Cascade Action Phase.
Connects to the running MCP server via subprocess and verifies file creation.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def run_mcp_tool(tool_name: str, arguments: dict, timeout: int = 120) -> dict | None:
    """Run an MCP tool by sending a JSON-RPC request to the MCP server via stdio."""
    mcp_binary = (
        Path(__file__).resolve().parent.parent.parent
        / "vendor"
        / "mcp-server-windsurf"
        / ".build"
        / "release"
        / "mcp-server-windsurf"
    )

    if not mcp_binary.exists():
        # Try debug build
        mcp_binary = mcp_binary.parent.parent / "debug" / "mcp-server-windsurf"
        if not mcp_binary.exists():
            print(f"❌ MCP server binary not found. Build it first:")
            print(
                f"   cd vendor/mcp-server-windsurf && swift build --configuration release"
            )
            return None

    # JSON-RPC request for tool call
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
    }

    tool_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }

    try:
        print(f"🧪 Testing {tool_name} with arguments: {json.dumps(arguments)}")

        proc = subprocess.Popen(
            [str(mcp_binary)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ},
        )

        # Send initialize + tool call
        init_msg = json.dumps(request) + "\n"
        tool_msg = json.dumps(tool_request) + "\n"

        stdout, stderr = proc.communicate(
            input=(init_msg + tool_msg).encode(), timeout=timeout
        )

        if stderr:
            stderr_text = stderr.decode("utf-8", errors="replace")
            # Filter only important log lines
            for line in stderr_text.split("\n"):
                if "Action Phase" in line or "wrote file" in line or "Error" in line:
                    print(f"  📋 {line.strip()}")

        if stdout:
            stdout_text = stdout.decode("utf-8", errors="replace")
            # Parse last JSON-RPC response
            for line in reversed(stdout_text.strip().split("\n")):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        response = json.loads(line)
                        return response
                    except json.JSONDecodeError:
                        continue

        return None

    except subprocess.TimeoutExpired:
        print(f"⏱️ Tool call timed out after {timeout}s")
        proc.kill()
        return None
    except Exception as e:
        print(f"❌ Error running {tool_name}: {e}")
        return None


def test_cascade_action_phase():
    """Test the Cascade Action Phase functionality."""
    print("🚀 Starting Cascade Action Phase Test")
    print("=" * 50)

    # Test 1: Simple file creation request
    print("\n📋 Test 1: Simple File Creation")
    test_message = "Create a simple_calc.py file with basic arithmetic functions (add, subtract, multiply, divide)"

    result = run_mcp_tool(
        "windsurf_cascade", {"message": test_message, "model": "swe-1.5"}
    )

    if result:
        print("✅ Test 1: MCP response received")
        if "result" in result:
            content = result["result"]
            if isinstance(content, dict) and "content" in content:
                text = content["content"][0].get("text", "") if content["content"] else ""
            else:
                text = str(content)
            if "Action Phase Complete" in text:
                print("  ✅ Action Phase completed with file creation!")
            elif "Action Phase" in text:
                print("  ⚠️  Action Phase detected but files may not have been created")
            print(f"  📄 Response preview: {text[:200]}...")
        elif "error" in result:
            print(f"  ❌ Error: {result['error']}")
    else:
        print("❌ Test 1: No response from MCP server")

    return result is not None


def verify_file_creation():
    """Verify that test files were created."""
    print("\n🔍 Verifying File Creation")
    print("-" * 30)

    test_files = [
        "simple_calc.py",
        "main.py",
        "models.py",
        "requirements.txt",
        "README.md",
    ]

    created_files = []
    for file in test_files:
        if os.path.exists(file):
            size = os.path.getsize(file)
            created_files.append((file, size))
            print(f"✅ {file} ({size} bytes)")
        else:
            print(f"❌ {file} not found")

    if created_files:
        print(f"\n📊 Summary: {len(created_files)}/{len(test_files)} files created")
        return True
    print("\n📊 Summary: No files created - Action Phase may not be working")
    return False


def check_server_logs():
    """Check for Action Phase signatures in server logs."""
    print("\n📋 Checking Server Logs for Action Phase Signatures")
    print("-" * 50)

    action_signatures = [
        "Action Phase wrote file",
        "Action Phase: found",
        "Action Phase Complete",
        "CortexStep",
        "ActionSpec",
    ]

    log_dir = Path("/Users/dev/.config/atlastrinity/logs")
    found_signatures = []

    if log_dir.exists():
        import glob

        for log_file in glob.glob(str(log_dir / "*.log")):
            try:
                with open(log_file) as f:
                    content = f.read()
                    for signature in action_signatures:
                        if signature in content:
                            found_signatures.append((signature, log_file))
                            print(f"✅ Found '{signature}' in {log_file}")
            except Exception as e:
                print(f"⚠️ Could not read {log_file}: {e}")

    if found_signatures:
        print(f"\n📊 Found {len(found_signatures)} Action Phase signatures")
        return True
    print("\n📊 No Action Phase signatures found in logs")
    return False


def main():
    """Main test execution."""
    print("🌊 Windsurf MCP Cascade Action Phase Test Suite")
    print("=" * 60)

    # Check environment
    api_key = os.getenv("WINDSURF_API_KEY")
    if not api_key:
        print("❌ WINDSURF_API_KEY not set")
        print("💡 Set it with: export WINDSURF_API_KEY=sk-ws-...")
        return 1

    print(f"✅ API Key configured: {api_key[:10]}...")

    # Change to a temp workspace for test files
    project_dir = Path(__file__).parent.parent.parent
    test_workspace = project_dir / ".cascade_test_workspace"
    test_workspace.mkdir(exist_ok=True)
    print(f"📁 Test workspace: {test_workspace}")

    original_dir = os.getcwd()
    os.chdir(test_workspace)

    try:
        # Run tests
        cascade_ok = test_cascade_action_phase()

        # Wait for async operations
        print("\n⏳ Waiting for file operations...")
        time.sleep(5)

        # Verify results
        files_created = verify_file_creation()
        logs_found = check_server_logs()

        print("\n🎯 Test Results Summary")
        print("=" * 30)
        print(f"📡 Cascade Call: {'✅' if cascade_ok else '❌'}")
        print(f"📁 Files Created: {'✅' if files_created else '❌'}")
        print(f"📋 Logs Found: {'✅' if logs_found else '❌'}")

        if files_created:
            print("\n🎉 Action Phase is working! Files were created successfully!")
            return 0
        elif cascade_ok:
            print(
                "\n⚠️ Cascade call succeeded but files weren't created in test workspace"
            )
            return 1
        else:
            print("\n⚠️ Action Phase needs further refinement")
            return 1

    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        return 1
    finally:
        os.chdir(original_dir)


if __name__ == "__main__":
    sys.exit(main())
