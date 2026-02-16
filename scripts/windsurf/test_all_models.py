import json
import os
import subprocess
import time

# Configuration
MCP_SERVER_PATH = "/Users/dev/Documents/GitHub/atlastrinity/vendor/mcp-server-windsurf/.build/release/mcp-server-windsurf"
API_KEY = os.environ.get("WINDSURF_API_KEY")

MODELS = [
    "swe-1.5",
    "swe-1",
    "swe-1-mini",
    "swe-grep",
    "windsurf-fast",
    "llama-3.1-405b",
    "llama-3.1-70b",
    "claude-4.6-opus",
    "claude-4.6-opus-fast",
    "gpt-5.2-codex",
    "gpt-5.3-codex-spark",
    "gemini-3-pro",
    "gemini-3-flash",
    "sonnet-4.5",
    "gpt-5.1-codex",
    "gpt-5.1-codex-mini",
    "gpt-4o",
    "claude-3.5-sonnet",
    "deepseek-v3",
    "deepseek-r1",
    "grok-code-fast-1",
    "kimi-k2.5",
]


def rpc_request(process, method, params=None, req_id=1):
    msg = {"jsonrpc": "2.0", "method": method, "id": req_id}
    if params is not None:
        msg["params"] = params

    json_line = json.dumps(msg)
    if process.stdin:
        process.stdin.write(json_line + "\n")
        process.stdin.flush()


def read_response(process):
    if not process.stdout:
        return None
    line = process.stdout.readline()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def test_model(model_id):
    print(f"🧪 Testing Model: {model_id}...", end=" ", flush=True)

    process = subprocess.Popen(
        [MCP_SERVER_PATH],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
    )

    # Initialize
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
    read_response(process)

    # Initialized notification
    msg = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    if process.stdin:
        process.stdin.write(json.dumps(msg) + "\n")
        process.stdin.flush()

    # Call Chat
    chat_params = {
        "name": "windsurf_chat",
        "arguments": {"message": "Write 'OK'.", "model": model_id},
    }
    rpc_request(process, "tools/call", chat_params, req_id=2)

    resp = read_response(process)

    # Wait for process to finish
    process.terminate()
    try:
        _, stderr = process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        _, stderr = process.communicate()

    if resp and "result" in resp:
        content = resp["result"].get("content", [])
        text = "".join([c.get("text", "") for c in content if c.get("type") == "text"])
        if "Internal error" in text or "error" in text.lower():
            print("❌ FAILED (Backend Error)")
            print(f"Server Stderr: {stderr}")
            return False, text
        print("✅ WORKING!")
        return True, text
    error = resp.get("error", {}).get("message", "Unknown Error") if resp else "No Response"
    print(f"❌ ERROR: {error}")
    print(f"Server Stderr: {stderr}")
    return False, error


def main():
    if not API_KEY:
        print("❌ WINDSURF_API_KEY not found.")
        return

    results = []
    print(f"🚀 Starting sweep of {len(MODELS)} models...\n")

    for model in MODELS:
        success, info = test_model(model)
        results.append((model, success, info))
        time.sleep(1)  # Gap between tests

    print("\n📊 Final Results:")
    print("=" * 40)
    for model, success, info in results:
        status = "✅" if success else "❌"
        print(f"{status} {model}")

    working = [m for m, s, _ in results if s]
    if working:
        print(f"\n🌟 Working Models: {', '.join(working)}")
    else:
        print("\n😔 No models working for generation at this time.")


if __name__ == "__main__":
    main()
