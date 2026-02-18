import asyncio
import json
import sys
from pathlib import Path

from src.brain.config import PROJECT_ROOT
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_ROOT))

# Mock MCP connection behavior or use a real client if available.
# Since I'm the agent, I'll use the 'run_command' to execute the binary directly
# or simulate the JSON-RPC calls if I had an MCP client library.
# However, the most effective way to test the bridge is to run the binary with 'mcp' command
# and send JSON-RPC via stdin/stdout.


async def test_mcp_tool(tool_name: str, arguments: dict | None = None):
    """
    Test a Windsurf MCP tool by running the binary directly and simulating JSON-RPC.
    """
    if arguments is None:
        arguments = {}

    binary_path = f"{PROJECT_ROOT}/vendor/mcp-server-windsurf/.build/release/mcp-server-windsurf"

    # Construct JSON-RPC request
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }

    request_str = json.dumps(request) + "\n"
    print(f"\n[CALLING TOOL] {tool_name} with {arguments}")

    process = await asyncio.create_subprocess_exec(
        binary_path,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate(input=request_str.encode())

    if stderr:
        print(f"[STDERR] {stderr.decode()}")

    try:
        response = json.loads(stdout.decode())
        print(f"[RESPONSE] {json.dumps(response, indent=2)}")
        return response
    except Exception as e:
        print(f"[ERROR] Failed to parse response: {e}")
        print(f"[RAW STDOUT] {stdout.decode()}")
        return None


async def main():
    print("=== WINDSURF MCP BRIDGE EVALUATION ===")

    # 1. Test Status
    await test_mcp_tool("windsurf_status")

    # 2. Test Get Models
    await test_mcp_tool("windsurf_get_models", {"tier": "free"})

    # 3. Test Chat (Simple)
    # Note: Requires WINDSURF_API_KEY in env
    await test_mcp_tool(
        "windsurf_chat",
        {
            "message": "Hello! Reply with 'Windsurf status: Active' if you hear me.",
            "model": "swe-1.5",
        },
    )

    # 4. Test Cascade (Optional/Careful)
    # await test_mcp_tool("windsurf_cascade", {
    #     "message": "List files in the current directory",
    #     "model": "swe-1.5"
    # })


if __name__ == "__main__":
    asyncio.run(main())
