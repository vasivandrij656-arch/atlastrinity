#!/usr/bin/env python3

# Test with swe-1 model to see if it bypasses quota issues
import json
import os
import subprocess
import time


def test_swe1_model():
    """Test chat with swe-1 model"""
    
    print('🧪 Testing SWE-1 Model (should bypass quota)...')
    
    # Start MCP server
    server_path = '/Users/dev/Documents/GitHub/atlastrinity/vendor/mcp-server-windsurf/.build/release/mcp-server-windsurf'
    
    # Use the same message that works in IDE
    message = "Create a simple Python file called swe1_test.py with content: print('Hello from SWE-1!')"
    
    # Create the request
    request_data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "windsurf_chat",
            "arguments": {
                "message": message,
                "model": "swe-1"
            }
        }
    }
    
    # Get credentials
    try:
        with open('/Users/dev/Documents/GitHub/atlastrinity/.env') as f:
            for line in f:
                if line.startswith('WINDSURF_API_KEY='):
                    api_key = line.split('=', 1)[1].strip()
                    break
    except:
        api_key = None
    
    env = os.environ.copy()
    if api_key:
        env['WINDSURF_API_KEY'] = api_key
    
    try:
        # Run MCP server with the request
        proc = subprocess.Popen(
            [server_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
        
        # Initialize
        init_msg = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"}
            }
        }
        
        proc.stdin.write(json.dumps(init_msg) + '\n')
        proc.stdin.flush()
        
        # Wait for init response
        response_line = proc.stdout.readline()
        if not response_line:
            print('❌ No init response')
            proc.terminate()
            return False
            
        # Send initialized notification
        init_notify = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        proc.stdin.write(json.dumps(init_notify) + '\n')
        proc.stdin.flush()
        
        # Send chat request
        proc.stdin.write(json.dumps(request_data) + '\n')
        proc.stdin.flush()
        
        # Wait for response
        response_line = proc.stdout.readline()
        if not response_line:
            print('❌ No chat response')
            proc.terminate()
            return False
            
        response = json.loads(response_line)
        chat_response = response.get('result', {}).get('content', [{}])[0].get('text', '')
        
        print('📝 Chat Response:')
        print(chat_response)
        
        # Wait a bit for file operations
        time.sleep(2)
        
        # Terminate and get logs
        proc.terminate()
        stderr_output, _ = proc.communicate()
        
        print('📋 Server Logs:')
        for line in stderr_output.split('\n'):
            if 'Chat Mode:' in line or 'found.*file' in line or 'wrote file:' in line or 'quota' in line.lower():
                print(f'  📝 {line}')
        
        # Check for file creation
        if os.path.exists('/Users/dev/Documents/GitHub/atlastrinity/swe1_test.py'):
            print('✅ File created: swe1_test.py')
            with open('/Users/dev/Documents/GitHub/atlastrinity/swe1_test.py') as f:
                content = f.read()
                print(f'📄 Content: {content}')
            return True
        print('❌ File not created')
        return False
            
    except Exception as e:
        print(f'❌ Exception: {e}')
        return False

if __name__ == '__main__':
    success = test_swe1_model()
    if success:
        print('\n🎉 SWE-1 Model Test: SUCCESS!')
    else:
        print('\n❌ SWE-1 Model Test: FAILED')
