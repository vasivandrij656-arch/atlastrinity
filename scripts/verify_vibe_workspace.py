import asyncio
import sys
from pathlib import Path

# Add src to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from src.mcp_server.vibe_server import get_instructions_dir, get_vibe_workspace, vibe_prompt


async def verify_vibe_workspace():
    print(f"Active Workspace: {get_vibe_workspace()}")
    print(f"Instructions Dir: {get_instructions_dir()}")

    # Trigger a long prompt (> 2000 chars)
    long_prompt = (
        "Verify that you can read this file and it is within your workspace boundary. " * 30
    )

    print("Sending long prompt to Vibe...")
    # We mock the Context since we are running standalone
    from unittest.mock import MagicMock

    mock_ctx = MagicMock()

    # Mocking is_network_available because we only care about the path generation and command building here
    from src.mcp_server import vibe_server

    async def mock_is_network(*args, **kwargs):
        return True

    vibe_server.is_network_available = mock_is_network  # type: ignore[assignment]

    # We want to see the command being built, so we'll mock run_vibe_subprocess too
    original_run = vibe_server.run_vibe_subprocess
    captured_argv = []
    captured_cwd = ""

    async def mock_run(argv, cwd, timeout_s=0, **kwargs):
        nonlocal captured_argv, captured_cwd
        captured_argv = argv
        captured_cwd = cwd
        print(f"CAPTURED ARGV: {argv}")
        print(f"CAPTURED CWD: {cwd}")
        return {"success": True, "stdout": "Mocked success", "stderr": "", "returncode": 0}

    vibe_server.run_vibe_subprocess = mock_run  # type: ignore[assignment]

    try:
        result = await vibe_prompt(ctx=mock_ctx, prompt=long_prompt)
        print(f"Result: {result['success']}")

        # Check if the instruction file is in the captured_argv
        instr_file = None
        for arg in captured_argv:
            if "vibe_instructions_" in arg:
                instr_file = arg
                break

        if instr_file:
            print(f"Instruction file path passed to Vibe: {instr_file}")
            workspace = captured_cwd
            if instr_file.startswith(workspace):
                print("SUCCESS: Instruction file is WITHIN the workspace boundary!")
            else:
                print("FAILURE: Instruction file is OUTSIDE the workspace boundary!")
                print(f"File: {instr_file}")
                print(f"Workspace: {workspace}")
        else:
            print("FAILURE: Instruction file not found in argv!")

    finally:
        vibe_server.run_vibe_subprocess = original_run


if __name__ == "__main__":
    asyncio.run(verify_vibe_workspace())
