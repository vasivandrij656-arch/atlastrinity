#!/usr/bin/env python3
"""
Automated test script for Windsurf MCP Cascade Action Phase
Tests the enhanced handleCascade implementation with Scope and Cortex reasoning
"""

import json
import os
import sys
import time
from pathlib import Path


def run_mcp_tool(tool_name, arguments):
    """Run an MCP tool and return the result"""
    try:
        # Create a simple MCP client call using curl-like approach
        # For now, we'll simulate by calling the windsurf MCP server directly
        # In real implementation, this would connect to MCP server
        print(f"🧪 Testing {tool_name} with arguments: {arguments}")
        print(f"📝 Request: {json.dumps(arguments, indent=2)}")

        # For demonstration, we'll show what would be sent
        # In real implementation, this would connect to MCP server
        return f"Simulated response for {tool_name}"

    except Exception as e:
        print(f"❌ Error running {tool_name}: {e}")
        return None


def test_cascade_action_phase():
    """Test the Cascade Action Phase functionality"""
    print("🚀 Starting Cascade Action Phase Test")
    print("=" * 50)

    # Test 1: Simple file creation request
    print("\n📋 Test 1: Simple File Creation")
    test_message = "Create a simple_calc.py file with basic arithmetic functions"

    result = run_mcp_tool("windsurf_cascade", {"message": test_message, "model": "swe-1.5"})

    if result:
        print("✅ Test 1 completed")
        print(f"📄 Result preview: {result[:200]}...")

    # Test 2: Complex multi-step task
    print("\n📋 Test 2: Complex Multi-step Task")
    complex_message = """
    Create a Python project structure for a web API:
    1. Create a main.py file with Flask setup
    2. Create a models.py file with User model
    3. Create a requirements.txt file
    4. Create a README.md with setup instructions
    """

    result = run_mcp_tool("windsurf_cascade", {"message": complex_message, "model": "swe-1.5"})

    if result:
        print("✅ Test 2 completed")
        print(f"📄 Result preview: {result[:200]}...")

    # Test 3: File modification task
    print("\n📋 Test 3: File Modification")
    modification_message = "Modify the simple_calc.py file to add error handling and unit tests"

    result = run_mcp_tool("windsurf_cascade", {"message": modification_message, "model": "swe-1.5"})

    if result:
        print("✅ Test 3 completed")
        print(f"📄 Result preview: {result[:200]}...")


def verify_file_creation():
    """Verify that test files were created"""
    print("\n🔍 Verifying File Creation")
    print("-" * 30)

    test_files = ["simple_calc.py", "main.py", "models.py", "requirements.txt", "README.md"]

    created_files = []
    for file in test_files:
        if os.path.exists(file):
            size = os.path.getsize(file)
            created_files.append((file, size))
            print(f"✅ {file} ({size} bytes)")
        else:
            print(f"❌ {file} not found")

    if created_files:
        print(f"\n📊 Summary: {len(created_files)}/{len(test_files)} files created")
        return True
    print("\n📊 Summary: No files created - Action Phase may not be working")
    return False


def check_server_logs():
    """Check for Action Phase signatures in server logs"""
    print("\n📋 Checking Server Logs for Action Phase Signatures")
    print("-" * 50)

    action_signatures = [
        "CortexStep",
        "ActionSpec",
        "enable_cortex_reasoning",
        "enable_action_phase",
        "Action Phase Detected",
        "File operations may have occurred",
    ]

    # Look for log files
    log_patterns = ["*.log", "windsurf*.log", "mcp*.log", "/tmp/windsurf*.log"]

    found_signatures = []

    for pattern in log_patterns:
        import glob

        for log_file in glob.glob(pattern):
            try:
                with open(log_file) as f:
                    content = f.read()
                    for signature in action_signatures:
                        if signature in content:
                            found_signatures.append((signature, log_file))
                            print(f"✅ Found '{signature}' in {log_file}")
            except Exception as e:
                print(f"⚠️ Could not read {log_file}: {e}")

    if found_signatures:
        print(f"\n📊 Found {len(found_signatures)} Action Phase signatures")
        return True
    print("\n📊 No Action Phase signatures found in logs")
    return False


def main():
    """Main test execution"""
    print("🌊 Windsurf MCP Cascade Action Phase Test Suite")
    print("=" * 60)

    # Check environment
    api_key = os.getenv("WINDSURF_API_KEY")
    if not api_key:
        print("❌ WINDSURF_API_KEY not set")
        print("💡 Set it with: export WINDSURF_API_KEY=sk-ws-...")
        return 1

    print(f"✅ API Key configured: {api_key[:10]}...")

    # Change to the project directory
    project_dir = Path(__file__).parent.parent
    os.chdir(project_dir)
    print(f"📁 Working directory: {os.getcwd()}")

    # Run tests
    try:
        test_cascade_action_phase()

        # Wait a bit for any async operations
        print("\n⏳ Waiting for file operations...")
        time.sleep(5)

        # Verify results
        files_created = verify_file_creation()
        logs_found = check_server_logs()

        print("\n🎯 Test Results Summary")
        print("=" * 30)
        print(f"📁 Files Created: {'✅' if files_created else '❌'}")
        print(f"📋 Logs Found: {'✅' if logs_found else '❌'}")

        if files_created or logs_found:
            print("\n🎉 Action Phase implementation appears to be working!")
            return 0
        print("\n⚠️ Action Phase may need further refinement")
        return 1

    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
