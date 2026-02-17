import asyncio
import json
import os
import subprocess



async def test_cascade_with_code_generation_prompt():
    print("🧪 Testing Cascade with Code Generation Prompt...")

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

        assert server_proc.stdin
        server_proc.stdin.write(json.dumps(init_msg) + "\n")
        server_proc.stdin.flush()

        # Wait for init response
        assert server_proc.stdout
        response_line = server_proc.stdout.readline()
        response = json.loads(response_line)
        print("✅ Server initialized")

        # Send initialized notification
        init_notify = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        server_proc.stdin.write(json.dumps(init_notify) + "\n")
        server_proc.stdin.flush()

        # Call windsurf_cascade with explicit code generation instruction
        cascade_msg = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "windsurf_cascade",
                "arguments": {
                    "message": """You are a code generation assistant. Please generate Python code and respond ONLY with markdown code blocks.

Create a file called simple_calc.py with the following content:

```python
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    if b != 0:
        return a / b
    else:
        raise ValueError('Cannot divide by zero')

if __name__ == '__main__':
    print('Testing simple calculator:')
    print(f'2 + 3 = {add(2, 3)}')
    print(f'5 - 2 = {subtract(5, 2)}')
    print(f'4 * 3 = {multiply(4, 3)}')
    print(f'10 / 2 = {divide(10, 2)}')
```

IMPORTANT: Respond with ONLY the markdown code block above. Do not include any explanations or additional text.""",
                    "model": "swe-1.5",
                },
            },
        }

        print("🔄 Sending cascade request with code generation prompt...")
        server_proc.stdin.write(json.dumps(cascade_msg) + "\n")
        server_proc.stdin.flush()

        # Wait for response
        response_line = server_proc.stdout.readline()
        response = json.loads(response_line)
        print(
            "📝 Cascade Response:",
            response.get("result", {}).get("content", [{}])[0].get("text", "")[:200],
        )

        # Wait for file operations
        print("⏳ Waiting for file operations (10 seconds)...")
        await asyncio.sleep(10)

        # Capture stderr logs
        server_proc.terminate()
        stderr_output, _ = server_proc.communicate()

        print("📋 Server Logs:")
        for line in stderr_output.split("\n"):
            if (
                "hex:" in line
                or "Reconstructed response" in line
                or "```" in line
                or "code" in line.lower()
            ):
                print(f"  📝 {line}")

        # Check for file creation
        locations = [
            "/Users/dev/Documents/GitHub/atlastrinity/.cascade_test_workspace/simple_calc.py",
            "/Users/dev/Documents/GitHub/atlastrinity/simple_calc.py",
            "/Users/dev/Documents/GitHub/atlastrinity/src/simple_calc.py",
        ]

        for location in locations:
            if os.path.exists(location):
                print(f"✅ File created at: {location}")
                with open(location) as f:
                    content = f.read()
                    print(f"📄 Content preview: {content[:200]}...")
                return

        print("❌ File not found in any expected location")

    finally:
        if server_proc.poll() is None:
            server_proc.terminate()
            server_proc.wait()


if __name__ == "__main__":
    asyncio.run(test_cascade_with_code_generation_prompt())
