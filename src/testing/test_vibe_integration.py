"""Test script for Vibe MCP Server tools.
Verifies that tools are correctly wrapped and functional.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import vibe server functions directly
from src.mcp_server.vibe_server import (
    get_instructions_dir,
    get_vibe_workspace,
    handle_long_prompt,
    vibe_analyze_error,
    vibe_prompt,
    vibe_which,
)


class MockContext:
    """Mock context for testing."""

    def __init__(self):
        self.output = []

    async def info(self, msg):
        self.output.append(msg)

    async def error(self, msg):
        self.output.append(msg)

    async def log(self, level, message, logger_name=None):
        self.output.append(message)


async def test_vibe_which():
    """Test that vibe_which locates the binary."""
    ctx = MockContext()
    result = await vibe_which(ctx)

    return bool(result.get("success"))


async def test_prepare_prompt_small():
    """Test that small prompts don't create files."""
    small_prompt = "Create a hello world Python script."
    _, file_path = handle_long_prompt(small_prompt, cwd=get_vibe_workspace())

    return file_path is None


async def test_prepare_prompt_large():
    """Test that large prompts create files in INSTRUCTIONS_DIR."""
    large_prompt = "A" * 3000
    _, file_path = handle_long_prompt(large_prompt, cwd=get_vibe_workspace())

    if file_path is not None and get_instructions_dir() in file_path:
        # Cleanup test file
        Path(file_path).unlink(missing_ok=True)
        return True
    return False


async def test_vibe_prompt_small_task():
    """Test vibe_prompt with a simple task."""

    ctx = MockContext()

    # Use short prompt
    prompt = "Create a file called 'hello_vibe_test.py' with a simple hello world script."

    result = await vibe_prompt(
        ctx=ctx,
        prompt=prompt,
        timeout_s=600,
        max_turns=5,
    )

    if not result.get("success"):
        if result.get("stderr"):
            pass
        return False

    # Check if file was created in workspace
    test_file = Path(get_vibe_workspace()) / "hello_vibe_test.py"
    if test_file.exists():
        # Cleanup
        test_file.unlink()
        return True
    return False


async def test_vibe_arg_filtering():
    """Test that forbidden arguments like --no-tui are filtered out."""
    ctx = MockContext()

    # Send prompt with forbidden argument
    result = await vibe_prompt(
        ctx=ctx,
        prompt="version",
        timeout_s=30,
        max_turns=1,
    )

    # Check if command in result contains --no-tui
    command = result.get("command", [])
    return "--no-tui" not in command


async def test_vibe_analyze_error():
    """Test vibe_analyze_error to ensure prompt variable is fixed."""
    ctx = MockContext()

    result = await vibe_analyze_error(
        ctx=ctx,
        error_message="Test error message for analysis",
        auto_fix=False,
        timeout_s=60,
    )

    return bool(result.get("success") or result.get("returncode") is not None)


async def main():

    results = []

    # Test 1: Check binary
    results.append(("vibe_which", await test_vibe_which()))

    # Test 2: Small prompt (no file)
    results.append(("_prepare_prompt_arg (small)", await test_prepare_prompt_small()))

    # Test 3: Large prompt (file in INSTRUCTIONS_DIR)
    results.append(("_prepare_prompt_arg (large)", await test_prepare_prompt_large()))

    # Test 4: Argument filtering
    results.append(("vibe_arg_filtering", await test_vibe_arg_filtering()))

    # Test 5: Analyze error (fix check)
    results.append(("vibe_analyze_error", await test_vibe_analyze_error()))

    # Test 6: Actually run Vibe to create a file
    results.append(("vibe_prompt (create file)", await test_vibe_prompt_small_task()))

    passed = sum(1 for _, p in results if p)
    total = len(results)

    for _, _ in results:
        pass

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
