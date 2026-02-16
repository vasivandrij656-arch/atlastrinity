import json
import os
import subprocess
import sys
import time

# Configuration
MCP_SERVER_PATH = "/Users/dev/Documents/GitHub/atlastrinity/vendor/mcp-server-windsurf/.build/release/mcp-server-windsurf"
API_KEY = os.environ.get("WINDSURF_API_KEY")

if not API_KEY:
    print("❌ WINDSURF_API_KEY not found in environment.")
    # Try to find it from the user's running processes if possible, or just ask.
    # For now, we'll dummy it if check failed, but the MCP server checks it.
    # Actually, let's just warn.


def rpc_request(process, method, params=None, req_id=1):
    msg = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        msg["params"] = params

    json_line = json.dumps(msg)
    process.stdin.write(json_line + "\n")
    process.stdin.flush()


def read_response(process):
    line = process.stdout.readline()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        print(f"Failed to decode: {line}")
        return None


def main():
    print(f"🚀 Starting MCP Server: {MCP_SERVER_PATH}")

    # Start the MCP server process
    try:
        process = subprocess.Popen(
            [MCP_SERVER_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,  # Capture stderr to see logs
            text=True,
            env=os.environ.copy(),
        )
    except FileNotFoundError:
        print(f"❌ Executable not found at {MCP_SERVER_PATH}")
        return

    # 1. Initialize
    print("Sending initialize...")
    rpc_request(
        process,
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
        req_id=1,
    )

    resp = read_response(process)
    print(f"Initialize Response: {json.dumps(resp, indent=2)}")

    # 2. List Tools (to confirm we are connected)
    rpc_request(process, "tools/list", {}, req_id=2)
    resp = read_response(process)
    # print(f"Tools Response: {json.dumps(resp, indent=2)}") # Verbose

    # 3. Call Chat
    print("\n🧪 Testing initialized. Attempting initialization notification...")
    # Send as notification (no id)
    msg = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    process.stdin.write(json.dumps(msg) + "\n")
    process.stdin.flush()

    # Give the server a moment to process the notification
    time.sleep(0.5)

    print("\n📨 Sending Chat Request (windsurf_chat) for Code Generation...")
    chat_params = {
        "name": "windsurf_chat",
        "arguments": {
            "message": "Write a short Python function to calculate the N-th Fibonacci number. Provide only the code.",
            "model": "swe-1.5",
        },
    }
    rpc_request(process, "tools/call", chat_params, req_id=3)

    # Wait for response
    resp = read_response(process)
    print(f"\n📝 Chat Response:\n{json.dumps(resp, indent=2)}")

    print("\n📨 Requesting Models (windsurf_get_models)...")
    rpc_request(
        process,
        "tools/call",
        {"name": "windsurf_get_models", "arguments": {"tier": "free"}},
        req_id=4,
    )
    resp = read_response(process)
    print(f"\n📦 Models Response:\n{json.dumps(resp, indent=2)}")

    print("\n📨 Requesting Status (windsurf_status)...")
    rpc_request(process, "tools/call", {"name": "windsurf_status", "arguments": {}}, req_id=5)
    resp = read_response(process)
    print(f"\n📡 Status Response:\n{json.dumps(resp, indent=2)}")

    if resp and "error" in resp:
        print("\n❌ TEST FAILED: Server returned error.")
    elif resp and "result" in resp:
        content = resp["result"].get("content", [])
        text = "".join([c.get("text", "") for c in content if c.get("type") == "text"])
        print(f"\nRecieved Text: {text}")
        if "Internal Error" in text or "internal error" in text:
            print("\n⚠️  Possible Internal Error detected in text content.")
        else:
            print("\n✅ TEST PASSED: valid response received.")

    print("\n📨 Sending Cascade Request (windsurf_cascade)...")
    rpc_request(
        process,
        "tools/call",
        {
            "name": "windsurf_cascade",
            "arguments": {
                "message": "Create a file named fib.py with a Fibonacci function.",
                "model": "swe-1.5",
            },
        },
        req_id=6,
    )
    resp = read_response(process)
    print(f"\n🌊 Cascade Response:\n{json.dumps(resp, indent=2)}")
    process.terminate()
    try:
        outs, errs = process.communicate(timeout=2)
        if errs:
            print(f"\nServer Stderr:\n{errs}")
    except:
        pass


if __name__ == "__main__":
    main()
