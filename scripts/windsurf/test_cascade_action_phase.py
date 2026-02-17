#!/usr/bin/env python3
"""
Automated test script for Windsurf MCP Cascade Action Phase.
Connects to the running MCP server via subprocess and verifies file creation.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def _mcp_encode(msg: dict) -> bytes:
    """Encode a JSON-RPC message with Content-Length header (MCP stdio framing)."""
    body = json.dumps(msg).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


def _mcp_read_response(stdout, timeout: float = 120) -> dict | None:
    """Read a Content-Length framed JSON-RPC response from stdout."""
    import threading

    result = [None]

    def _read():
        try:
            # Read header
            header = b""
            while b"\r\n\r\n" not in header:
                ch = stdout.read(1)
                if not ch:
                    return
                header += ch

            # Parse Content-Length
            for line in header.decode("ascii").split("\r\n"):
                if line.lower().startswith("content-length:"):
                    length = int(line.split(":")[1].strip())
                    body = stdout.read(length)
                    result[0] = json.loads(body.decode("utf-8"))
                    return
        except Exception:
            pass

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout=timeout)
    return result[0]


def run_mcp_tool(tool_name: str, arguments: dict, timeout: int = 120) -> dict | None:
    """Run an MCP tool by sending a JSON-RPC request to the MCP server via stdio."""
    mcp_binary = (
        PROJECT_ROOT
        / "vendor"
        / "mcp-server-windsurf"
        / ".build"
        / "release"
        / "mcp-server-windsurf"
    )

    if not mcp_binary.exists():
        mcp_binary = mcp_binary.parent.parent / "debug" / "mcp-server-windsurf"
        if not mcp_binary.exists():
            print("❌ MCP server binary not found. Build it first:")
            print("   cd vendor/mcp-server-windsurf && swift build --configuration release")
            return None

    try:
        print(f"🧪 Testing {tool_name} with arguments: {json.dumps(arguments)}")

        proc = subprocess.Popen(
            [str(mcp_binary)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ},
            bufsize=0,
        )

        # Step 1: Send initialize request
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
            },
        }
        assert proc.stdin is not None
        proc.stdin.write(_mcp_encode(init_request))
        proc.stdin.flush()

        # Read initialize response
        assert proc.stdout is not None
        init_resp = _mcp_read_response(proc.stdout, timeout=15)
        if init_resp:
            print("  ✅ MCP initialized (protocol ok)")
        else:
            print("  ❌ MCP initialization timed out")
            # Try to read stderr to see what happened
            proc.terminate()
            try:
                assert proc.stderr is not None
                stderr_output = proc.stderr.read()
                if stderr_output:
                    print(f"  🔴 Server stderr:\n{stderr_output.decode('utf-8', errors='replace')}")
            except Exception:
                pass
            return None

        # Step 2: Send initialized notification
        initialized_notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
        assert proc.stdin is not None
        proc.stdin.write(_mcp_encode(initialized_notif))
        proc.stdin.flush()

        # Step 3: Send tool call
        tool_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        proc.stdin.write(_mcp_encode(tool_request))
        proc.stdin.flush()

        # Read tool response (may take a while for cascade)
        assert proc.stdout is not None
        tool_resp = _mcp_read_response(proc.stdout, timeout=timeout)

        # Check stderr for action phase logs
        proc.kill()
        try:
            assert proc.stderr is not None
            stderr_data = proc.stderr.read()
            if stderr_data:
                stderr_text = stderr_data.decode("utf-8", errors="replace")
                for line in stderr_text.split("\n"):
                    if "Action Phase" in line or "wrote file" in line:
                        print(f"  📋 {line.strip()}")
        except Exception:
            pass

        return tool_resp

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

    result = run_mcp_tool("windsurf_cascade", {"message": test_message, "model": "swe-1.5"})

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
        if cascade_ok:
            print("\n⚠️ Cascade call succeeded but files weren't created in test workspace")
            return 1
        print("\n⚠️ Action Phase needs further refinement")
        return 1

    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        return 1
    finally:
        os.chdir(original_dir)


if __name__ == "__main__":
    sys.exit(main())
