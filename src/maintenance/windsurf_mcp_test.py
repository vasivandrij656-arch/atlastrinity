
import subprocess
import json
import sys
import time

def call_mcp_tool(tool_name, arguments):
    binary = "/Users/dev/Documents/GitHub/atlastrinity/vendor/mcp-server-windsurf/.build/release/mcp-server-windsurf"
    env = {
        "WINDSURF_API_KEY": "sk-ws-01-3vQio5CLce8beK1OqKX1zvWmP-nTjOV3JpO3O5v3tI6Yy7SIRWJyanWHnCpjDnCKIOd1JVKFww8DKfmu5yRqVqGbazlrug",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin"
    }
    
    process = subprocess.Popen(
        [binary],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
    )
    
    def send_and_wait(method, params, request_id):
        req = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }
        process.stdin.write(json.dumps(req) + "\n")
        process.stdin.flush()
        
        # Read until we get a response with the same ID
        start_time = time.time()
        while time.time() - start_time < 20: # 20s timeout per call
            line = process.stdout.readline()
            if not line: break
            if line.startswith("{"):
                try:
                    resp = json.loads(line)
                    if resp.get("id") == request_id:
                        return resp
                except:
                    pass
        return None

    # 1. Initialize
    init_resp = send_and_wait("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0.0"}
    }, 1)
    
    if not init_resp:
        process.terminate()
        return {"error": "Initialization failed"}
    
    # 2. Call initialized (notification)
    process.stdin.write(json.dumps({
        "jsonrpc": "2.0",
        "method": "notifications/initialized"
    }) + "\n")
    process.stdin.flush()
    
    # 3. Call Tool
    tool_resp = send_and_wait("tools/call", {
        "name": tool_name,
        "arguments": arguments
    }, 2)
    
    process.terminate()
    return tool_resp

def test_models():
    models = ["swe-1.5", "claude-4.6-opus", "gpt-5.2-codex", "deepseek-v3"]
    results = {}
    
    print("--- SWIFT MCP SERVER TESTING ---")
    
    print("\n[TOOL] windsurf_status")
    status = call_mcp_tool("windsurf_status", {})
    if status and "result" in status:
        print("Status Received OK")
    else:
        print(f"Status Failed: {status}")
    
    for m in models:
        print(f"\n[TOOL] windsurf_chat (model: {m})")
        resp = call_mcp_tool("windsurf_chat", {"message": "Say 'OK' and nothing else.", "model": m})
        
        content = ""
        if resp and "result" in resp and "content" in resp["result"]:
            content = resp["result"]["content"][0].get("text", "")
        
        if "OK" in content.upper():
            results[m] = "✅ Working"
            print(f"  > RESPONSE: {content.strip()}")
        elif "RESOURCE_EXHAUSTED" in content.upper() or "ERROR" in content.upper():
            results[m] = f"⚠️ Quota Exhausted / API Error: {content.strip()[:100]}"
            print(f"  > INFO: {content.strip()[:100]}")
        else:
            results[m] = f"❌ Failed: {content or json.dumps(resp)}"
            print(f"  > ERROR: {content or json.dumps(resp)}")
            
    print("\n" + "="*60)
    print("SWIFT MCP MODEL DIAGNOSTIC REPORT")
    print("="*60)
    for m, res in results.items():
        print(f"{m:<20}: {res}")
    print("="*60)

if __name__ == "__main__":
    test_models()
