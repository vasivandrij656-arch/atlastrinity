import asyncio
import json
import os
import subprocess
import sys


async def test_model(model_name, test_name, message):
    print(f"🧪 Testing {model_name} - {test_name}...")

    # Start MCP server
    server_path = "/Users/dev/Documents/GitHub/atlastrinity/vendor/mcp-server-windsurf/.build/release/mcp-server-windsurf"
    server_proc = subprocess.Popen(
        [server_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Initialize
        init_msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        }

        server_proc.stdin.write(json.dumps(init_msg) + "\n")
        server_proc.stdin.flush()

        # Wait for init response
        response_line = server_proc.stdout.readline()
        response = json.loads(response_line)
        print(f"✅ Server initialized for {model_name}")

        # Send initialized notification
        init_notify = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        server_proc.stdin.write(json.dumps(init_notify) + "\n")
        server_proc.stdin.flush()

        # Call windsurf_chat
        chat_msg = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "windsurf_chat",
                "arguments": {"message": message, "model": model_name},
            },
        }

        print(f"🔄 Sending chat request for {model_name}...")
        server_proc.stdin.write(json.dumps(chat_msg) + "\n")
        server_proc.stdin.flush()

        # Wait for response
        response_line = server_proc.stdout.readline()
        response = json.loads(response_line)
        chat_response = response.get("result", {}).get("content", [{}])[0].get("text", "")

        if "❌ Chat error" in chat_response:
            print(f"❌ {model_name} Chat Error: {chat_response}")
            success = False
        else:
            print(f"✅ {model_name} Chat Success: {chat_response[:100]}...")
            success = True

        # Wait a bit for file operations
        await asyncio.sleep(3)

        # Capture stderr logs
        server_proc.terminate()
        stderr_output, _ = server_proc.communicate()

        print(f"📋 {model_name} Server Logs:")
        for line in stderr_output.split("\n"):
            if (
                "Chat Mode:" in line
                or "found.*file" in line
                or "Action:" in line
                or "Created" in line
                or "Modified" in line
            ):
                print(f"  📝 {line}")

        return success, chat_response

    finally:
        if server_proc.poll() is None:
            server_proc.terminate()
            server_proc.wait()


async def test_dual_models():
    print("🚀 Testing Dual Models: swe-1.5 and deepseek-v3")
    print("=" * 60)

    # Test 1: swe-1.5 (working model mentioned by user)
    success1, response1 = await test_model(
        "swe-1.5", "Working Model", 'Create test_swe.txt with content "swe-1.5 works"'
    )

    print("\n" + "-" * 60 + "\n")

    # Test 2: deepseek-v3 (second model)
    success2, response2 = await test_model(
        "deepseek-v3", "DeepSeek V3", 'Create test_deepseek.txt with content "deepseek-v3 works"'
    )

    print("\n" + "=" * 60)
    print("📊 Final Results:")
    print(f"swe-1.5: {'✅ SUCCESS' if success1 else '❌ FAILED'}")
    print(f"deepseek-v3: {'✅ SUCCESS' if success2 else '❌ FAILED'}")

    # Check for created files
    files_to_check = [
        "/Users/dev/Documents/GitHub/atlastrinity/test_swe.txt",
        "/Users/dev/Documents/GitHub/atlastrinity/test_deepseek.txt",
    ]

    for file_path in files_to_check:
        if os.path.exists(file_path):
            with open(file_path) as f:
                content = f.read()
            print(f'✅ File found: {os.path.basename(file_path)} - "{content}"')
        else:
            print(f"❌ File not found: {os.path.basename(file_path)}")


if __name__ == "__main__":
    asyncio.run(test_dual_models())
