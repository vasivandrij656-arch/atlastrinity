#!/usr/bin/env python3

# Test if IDE session authentication works
import json
import os
import subprocess
import time


def test_ide_session():
    """Test chat with IDE session authentication"""

    print("🧪 Testing IDE Session Authentication...")

    # Get credentials
    api_key = os.getenv("WINDSURF_API_KEY")
    if not api_key:
        # Try to get from .env
        try:
            with open("/Users/dev/Documents/GitHub/atlastrinity/.env") as f:
                for line in f:
                    if line.startswith("WINDSURF_API_KEY="):
                        api_key = line.split("=", 1)[1].strip()
                        break
        except:
            pass

    if not api_key:
        print("❌ No API key found")
        return False

    print(f"✅ API Key: {api_key[:20]}...")

    # Start MCP server
    server_path = "/Users/dev/Documents/GitHub/atlastrinity/vendor/mcp-server-windsurf/.build/release/mcp-server-windsurf"

    # Use the same message that works in IDE
    message = "Create a simple Python file called ide_test.py with content: print('Hello from IDE session!')"

    # Create the request
    request_data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "windsurf_chat", "arguments": {"message": message, "model": "swe-1.5"}},
    }

    env = os.environ.copy()
    env["WINDSURF_API_KEY"] = api_key

    try:
        # Run MCP server with the request
        proc = subprocess.Popen(
            [server_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        # Initialize
        init_msg = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        }

        proc.stdin.write(json.dumps(init_msg) + "\n")
        proc.stdin.flush()

        # Wait for init response
        response_line = proc.stdout.readline()
        if not response_line:
            print("❌ No init response")
            proc.terminate()
            return False

        # Send initialized notification
        init_notify = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        proc.stdin.write(json.dumps(init_notify) + "\n")
        proc.stdin.flush()

        # Send chat request
        proc.stdin.write(json.dumps(request_data) + "\n")
        proc.stdin.flush()

        # Wait for response
        response_line = proc.stdout.readline()
        if not response_line:
            print("❌ No chat response")
            proc.terminate()
            return False

        response = json.loads(response_line)
        chat_response = response.get("result", {}).get("content", [{}])[0].get("text", "")

        print("📝 Chat Response:")
        print(chat_response)

        # Wait a bit for file operations
        time.sleep(2)

        # Terminate and get logs
        proc.terminate()
        stderr_output, _ = proc.communicate()

        print("📋 Server Logs:")
        for line in stderr_output.split("\n"):
            if (
                "Chat Mode:" in line
                or "found.*file" in line
                or "wrote file:" in line
                or "IDE" in line
            ):
                print(f"  📝 {line}")

        # Check for file creation
        if os.path.exists("/Users/dev/Documents/GitHub/atlastrinity/ide_test.py"):
            print("✅ File created: ide_test.py")
            with open("/Users/dev/Documents/GitHub/atlastrinity/ide_test.py") as f:
                content = f.read()
                print(f"📄 Content: {content}")
            return True
        print("❌ File not created")
        return False

    except Exception as e:
        print(f"❌ Exception: {e}")
        return False


if __name__ == "__main__":
    success = test_ide_session()
    if success:
        print("\n🎉 IDE Session Authentication: SUCCESS!")
    else:
        print("\n❌ IDE Session Authentication: FAILED")
