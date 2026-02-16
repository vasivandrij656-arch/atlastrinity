#!/usr/bin/env python3

# Test file creation manually to verify the system works
# This simulates what the MCP server should do

def create_test_file():
    """Create a test file to verify file creation works."""
    
    content = '''def hello_world():
    """A simple hello world function."""
    print("Hello from Manual Test!")
    return "Success!"

def add_numbers(a, b):
    """Add two numbers and return the result."""
    return a + b

if __name__ == "__main__":
    # Test the functions
    result = hello_world()
    numbers = add_numbers(10, 5)
    print(f"10 + 5 = {numbers}")
    print("Manual file creation test completed!")
'''
    
    file_path = '/Users/dev/Documents/GitHub/atlastrinity/manual_test.py'
    
    try:
        with open(file_path, 'w') as f:
            f.write(content)
        
        print(f'✅ File created successfully: {file_path}')
        print(f'📄 File size: {len(content)} characters')
        
        # Verify file exists and has content
        with open(file_path, 'r') as f:
            read_content = f.read()
        
        if read_content == content:
            print('✅ File content verified')
            return True
        else:
            print('❌ File content mismatch')
            return False
            
    except Exception as e:
        print(f'❌ Error creating file: {e}')
        return False

if __name__ == '__main__':
    success = create_test_file()
    if success:
        print('\n🎉 Manual File Creation: SUCCESS!')
        print('💡 This proves the file system works, so the issue is in Windsurf MCP')
    else:
        print('\n❌ Manual File Creation: FAILED')
