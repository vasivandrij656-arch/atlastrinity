import asyncio
import json
import os
import subprocess
import sys
import time


async def run_mcp_server():
    # Path to release binary
    binary_path = "./vendor/mcp-server-windsurf/.build/release/mcp-server-windsurf"

    # Environment variables
    env = os.environ.copy()

    # Start server process
    process = subprocess.Popen(
        [binary_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=0,
    )
    return process


def rpc_request(process, method, params, req_id):
    req = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
    json_req = json.dumps(req)
    if process.stdin:
        process.stdin.write(json_req + "\n")
        process.stdin.flush()


def read_response(process):
    if not process.stdout:
        return None
    try:
        line = process.stdout.readline()
        if not line:
            return None
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def main():
    print("🚀 Starting Windsurf MCP Cascade Test...")
    process = asyncio.run(run_mcp_server())
    if not process:
        print("❌ Failed to start server")
        return

    # Initialize
    print("📋 Sending Initialize...")
    rpc_request(
        process,
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
        1,
    )
    resp = read_response(process)
    print(f"Initialize Resp: {json.dumps(resp)[:100]}...")

    # Initialized notification
    rpc_request(process, "notifications/initialized", {}, None)

    # Call windsurf_cascade
    print("\n🌊 Calling windsurf_cascade (swe-1.5)...")
    chat_params = {
        "name": "windsurf_cascade",
        "arguments": {"message": "Hello from MCP Cascade Test!", "model": "swe-1.5"},
    }
    rpc_request(process, "tools/call", chat_params, 2)

    # Wait for response (Cascade might take time)
    start_time = time.time()
    while time.time() - start_time < 30:
        if process.poll() is not None:
            print("❌ Server exited unexpectedly")
            _, stderr = process.communicate()
            print(f"Stderr: {stderr}")
            break

        if process.stdout:
            line = process.stdout.readline()
        else:
            line = None
        if line:
            try:
                resp = json.loads(line)
                if resp.get("id") == 2:
                    print(f"✅ Cascade Response: {json.dumps(resp, indent=2)}")
                    if "error" in resp:
                        print("❌ RPC Error returned.")
                    elif resp.get("result", {}).get("isError"):
                        print("❌ Tool Execution Error.")
                    else:
                        print("✅ Success!")
                    break
            except:
                print(f"Raw Output: {line.strip()}")
        else:
            time.sleep(0.1)

    process.terminate()
    try:
        _, stderr = process.communicate(timeout=2)
        print(f"Server Internal Log:\n{stderr}")
    except subprocess.TimeoutExpired:
        process.kill()


if __name__ == "__main__":
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
    main()
