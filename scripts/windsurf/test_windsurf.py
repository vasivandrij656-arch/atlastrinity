import json
import os
import subprocess
import sys

# Test MCP server
server_path = "/Users/dev/Documents/GitHub/atlastrinity/vendor/mcp-server-windsurf/.build/release/mcp-server-windsurf"
env = os.environ.copy()
env["WINDSURF_API_KEY"] = "sk-ws-01-3vQio5mXnK7kZ2fJ8rT9pLqRsVuYwNx"

print("🔑 API Key configured")
print("🌊 Testing MCP Windsurf Server...")

# Simple status check first
request = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {"name": "windsurf_status", "arguments": {}},
}

print("📝 Sending status check...")
proc = subprocess.Popen(
    [server_path],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    env=env,
)

# Send request
proc.stdin.write(json.dumps(request) + "\n")
proc.stdin.flush()

# Read response
try:
    # Read initialization response
    init_line = proc.stdout.readline()
    print("📡 Init:", init_line[:100] if init_line else "No response")

    # Read actual response
    response_line = proc.stdout.readline()
    print("📥 Status Response:", response_line[:200] if response_line else "No response")

    # Try to parse JSON
    if response_line:
        try:
            response = json.loads(response_line)
            if "result" in response:
                print("✅ Success! Got result:")
                print(response["result"]["content"][0]["text"][:300])
            elif "error" in response:
                print("❌ Error:", response["error"])
            else:
                print("❓ Unknown response format")
        except json.JSONDecodeError as e:
            print("⚠️ JSON decode error:", e)
            print("Raw response:", response_line)
except Exception as e:
    print("⚠️ Error:", e)

proc.terminate()
