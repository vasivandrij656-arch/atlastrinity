#!/usr/bin/env python3
"""
Test script for verifying Vibe MCP Server tool execution and log visibility.
"""

import asyncio
import sys

from src.mcp_server.vibe_server import (
    vibe_get_config,
    vibe_implement_feature,
    vibe_prompt,
    vibe_smart_plan,
)


# We need a mock Context object for the MCP tool handlers
class MockContext:
    def __init__(self):
        self.session_id = "test_vibe_session_123"


async def test_vibe_get_config():
    print("--- [TEST] vibe_get_config ---")
    ctx = MockContext()
    result = await vibe_get_config(ctx)  # type: ignore
    print(f"[RESULT] Success: {result.get('success', False)}")
    if not result.get("success"):
        print(f"Error: {result.get('error')}")
    else:
        cfg = result.get("config", {})
        print(f"Config loaded. Keys: {list(cfg.keys()) if cfg else 'None'}")
    print("\n" + "=" * 50 + "\n")


async def test_vibe_prompt():
    print("--- [TEST] vibe_prompt ---")
    ctx = MockContext()

    # We ask a simple math question or logic question that doesn't need external tools to just test communication
    result = await vibe_prompt(
        ctx=ctx,  # type: ignore
        prompt="Reply with the exact word 'PONG_SUCCESS'. Do not use any tools.",
        max_turns=1,
    )
    print(f"[RESULT] Success: {result.get('success', False)}")
    if not result.get("success"):
        print(f"Error: {result.get('error')}")
    print(f"Response:\n{result.get('response', '')}")
    print("\n" + "=" * 50 + "\n")


async def test_vibe_smart_plan():
    print("--- [TEST] vibe_smart_plan ---")
    ctx = MockContext()

    result = await vibe_smart_plan(
        ctx=ctx,  # type: ignore
        objective="Create a hello world python script",
    )
    print(f"[RESULT] Success: {result.get('success', False)}")
    if not result.get("success"):
        print(f"Error: {result.get('error')}")
    else:
        print("Plan was successfully generated.")
    print("\n" + "=" * 50 + "\n")


async def test_vibe_implement_feature():
    print("--- [TEST] vibe_implement_feature ---")
    ctx = MockContext()

    import os
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = os.path.join(tmp_dir, "hello_world.py")

        result = await vibe_implement_feature(
            ctx=ctx,  # type: ignore
            goal=f"Create a python script at precisely '{test_file}' that prints exactly 'vibe_implementation_works'.",
            cwd=tmp_dir,
            quality_checks=False,
            iterative_review=False,
        )
        print(f"[RESULT] Success: {result.get('success', False)}")

        # Verify file
        if os.path.exists(test_file):
            with open(test_file) as f:
                content = f.read()
            print(f"[VERIFICATION] File exists! Content:\n{content}")
        else:
            print("[VERIFICATION] File DOES NOT EXIST.")

    print("\n" + "=" * 50 + "\n")


async def main():
    print("Starting Vibe MCP Tools Integration Test...\n")

    await test_vibe_get_config()
    await test_vibe_prompt()
    await test_vibe_smart_plan()
    await test_vibe_implement_feature()

    print("Testing complete.")


if __name__ == "__main__":
    asyncio.run(main())
