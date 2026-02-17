import asyncio
import json
import os
import subprocess
import sys


async def test_chat_file_creation():
    print('🧪 Testing Chat Mode File Creation with Direct API Fallback...')
    
    # Start MCP server
    server_path = '/Users/dev/Documents/GitHub/atlastrinity/vendor/mcp-server-windsurf/.build/release/mcp-server-windsurf'
    server_proc = subprocess.Popen([server_path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    try:
        # Initialize
        init_msg = {
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'initialize',
            'params': {
                'protocolVersion': '2024-11-05',
                'capabilities': {},
                'clientInfo': {'name': 'test', 'version': '1.0'}
            }
        }
        
        server_proc.stdin.write(json.dumps(init_msg) + '\n')
        server_proc.stdin.flush()
        
        # Wait for init response
        response_line = server_proc.stdout.readline()
        response = json.loads(response_line)
        print('✅ Server initialized')
        
        # Send initialized notification
        init_notify = {
            'jsonrpc': '2.0',
            'method': 'notifications/initialized'
        }
        server_proc.stdin.write(json.dumps(init_notify) + '\n')
        server_proc.stdin.flush()
        
        # Call windsurf_chat with explicit file creation request
        chat_msg = {
            'jsonrpc': '2.0',
            'id': 2,
            'method': 'tools/call',
            'params': {
                'name': 'windsurf_chat',
                'arguments': {
                    'message': '''Create a Python file called chat_test.py with the following content:

```python chat_test.py
def hello_world():
    """A simple hello world function."""
    print("Hello from Chat Mode!")
    return "Success!"

def add_numbers(a, b):
    """Add two numbers and return the result."""
    return a + b

if __name__ == "__main__":
    # Test the functions
    result = hello_world()
    numbers = add_numbers(10, 5)
    print(f"10 + 5 = {numbers}")
    print("Chat mode file creation test completed!")
```

Please create this file in the current directory with working Python code.''',
                    'model': 'windsurf-fast'
                }
            }
        }
        
        print('🔄 Sending chat request with explicit file creation...')
        server_proc.stdin.write(json.dumps(chat_msg) + '\n')
        server_proc.stdin.flush()
        
        # Wait for response
        response_line = server_proc.stdout.readline()
        response = json.loads(response_line)
        chat_response = response.get('result', {}).get('content', [{}])[0].get('text', '')
        print('📝 Chat Response:')
        print(chat_response)
        
        # Wait for file operations
        print('⏳ Waiting for file operations (5 seconds)...')
        await asyncio.sleep(5)
        
        # Capture stderr logs
        server_proc.terminate()
        stderr_output, _ = server_proc.communicate()
        
        print('📋 Server Logs:')
        for line in stderr_output.split('\n'):
            if 'Chat Mode:' in line or 'found.*file' in line or 'wrote file:' in line or 'Direct API' in line:
                print(f'  📝 {line}')
        
        # Check for file creation
        file_path = '/Users/dev/Documents/GitHub/atlastrinity/chat_test.py'
        if os.path.exists(file_path):
            print(f'✅ File created at: {file_path}')
            with open(file_path) as f:
                content = f.read()
                print(f'📄 File content ({len(content)} chars):')
                print('─' * 40)
                print(content)
                print('─' * 40)
            return True
        print('❌ File not found')
        # Check entire project
        result = subprocess.run(['find', '/Users/dev/Documents/GitHub/atlastrinity', '-name', 'chat_test.py', '-type', 'f'], capture_output=True, text=True)
        if result.stdout.strip():
            print(f'🔍 File found at: {result.stdout.strip()}')
            return True
        return False
        
    finally:
        if server_proc.poll() is None:
            server_proc.terminate()
            server_proc.wait()

if __name__ == '__main__':
    success = asyncio.run(test_chat_file_creation())
    if success:
        print('\n🎉 Chat Mode File Creation: SUCCESS!')
    else:
        print('\n❌ Chat Mode File Creation: FAILED')
