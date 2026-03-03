#!/usr/bin/env python3
"""
Comprehensive test script for verifying all 19 Vibe MCP Server tools.
"""

import asyncio
import json
import os
import sys
import tempfile
import time

# Need to ensure we can import from the project root
if ".." not in sys.path:
    sys.path.insert(0, "..")
    sys.path.insert(0, ".")

from src.mcp_server.vibe_server import (
    vibe_analyze_error,
    vibe_ask,
    vibe_check_db,
    vibe_code_review,
    vibe_configure_model,
    vibe_configure_provider,
    vibe_execute_subcommand,
    vibe_get_config,
    vibe_get_system_context,
    vibe_implement_feature,
    vibe_list_sessions,
    vibe_prompt,
    vibe_reload_config,
    vibe_session_details,
    vibe_session_resume,
    vibe_set_mode,
    vibe_smart_plan,
    vibe_test_in_sandbox,
    vibe_which,
)


# Mock Context
class MockContext:
    def __init__(self):
        self.session_id = "test_vibe_full_verification_" + str(int(time.time()))

    async def report_progress(self, progress: float, total: float):
        pass


async def test_tool(test_name, tool_func, **kwargs):
    print(f"--- [TEST] {test_name} ---")
    ctx = MockContext()
    try:
        # Pass ctx and then all other kwargs
        result = await tool_func(ctx=ctx, **kwargs)
        success = result.get("success", False)
        print(f"[RESULT] Success: {success}")
        if not success:
            print(f"Error: {result.get('error') or result.get('stderr') or 'Unknown error'}")
        if "stdout" in result:
            print(f"Stdout: {result['stdout'].strip()}")
        return result
    except Exception as e:
        print(f"[EXCEPTION] {e}")
        return {"success": False, "error": str(e)}
    finally:
        print("\n" + "=" * 50 + "\n")


async def main():
    print("Starting COMPREHENSIVE Vibe MCP Tools Verification (19 Tools)...\n")

    # 1. vibe_which
    await test_tool("vibe_which", vibe_which)

    # 2. vibe_get_config
    await test_tool("vibe_get_config", vibe_get_config)

    # 3. vibe_set_mode
    await test_tool("vibe_set_mode", vibe_set_mode, mode="auto-approve")

    # 4. vibe_reload_config
    await test_tool("vibe_reload_config", vibe_reload_config)

    # 5. vibe_ask
    await test_tool("vibe_ask", vibe_ask, question="Reply with 'OK'", model="gpt-4o")

    # 6. vibe_prompt
    await test_tool("vibe_prompt", vibe_prompt, prompt="Say 'READY'", max_turns=1)

    # 7. vibe_smart_plan
    await test_tool("vibe_smart_plan", vibe_smart_plan, objective="Test plan generation")

    # 8. vibe_list_sessions
    await test_tool("vibe_list_sessions", vibe_list_sessions, limit=5)

    # 9. vibe_get_system_context
    await test_tool("vibe_get_system_context", vibe_get_system_context)

    # 10. vibe_check_db (SQL Mode)
    await test_tool("vibe_check_db", vibe_check_db, query="SELECT 1")

    # 11. vibe_check_db (Verify Mode)
    # Note: README.md exists in current directory but vibe_check_db looks for it relative to CWD.
    await test_tool(
        "vibe_check_db", vibe_check_db, action="verify", expected_files=["README.md"], cwd="."
    )

    # 12. vibe_execute_subcommand
    await test_tool("vibe_execute_subcommand", vibe_execute_subcommand, subcommand="list-modules")

    # 13. vibe_code_review
    await test_tool(
        "vibe_code_review", vibe_code_review, file_path="README.md", focus_areas="layout"
    )

    # 14. vibe_analyze_error
    await test_tool("vibe_analyze_error", vibe_analyze_error, error_message="Test error context")

    # 15. vibe_test_in_sandbox
    # Fix: use vibe_test_runner.py as command or match it in script
    test_script = "print('sandbox_works')"
    await test_tool(
        "vibe_test_in_sandbox",
        vibe_test_in_sandbox,
        test_script=test_script,
        target_files={},
        command="python3 vibe_test_runner.py",
    )

    # 16. vibe_configure_model
    await test_tool("vibe_configure_model", vibe_configure_model, model_alias="gpt-4o")

    # 17. vibe_configure_provider
    # Dummy provider to verify argument handling
    await test_tool(
        "vibe_configure_provider",
        vibe_configure_provider,
        name="test_prov",
        api_base="http://localhost:9999",
        api_key_env_var="TEST_KEY_DUMMY",
    )

    # 18. vibe_implement_feature
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = os.path.join(tmp_dir, "test_vibe_imp_comp.py")
        await test_tool(
            "vibe_implement_feature",
            vibe_implement_feature,
            goal=f"Create a python script at {test_file} that prints 'hello'",
            cwd=tmp_dir,
            quality_checks=False,
            iterative_review=False,
        )

    # 19. vibe_session_details & vibe_session_resume
    sessions_result = await vibe_list_sessions(MockContext())
    if sessions_result.get("success") and sessions_result.get("sessions"):
        sid = sessions_result["sessions"][0]["session_id"]
        await test_tool("vibe_session_details", vibe_session_details, session_id_or_file=sid)
        await test_tool(
            "vibe_session_resume", vibe_session_resume, session_id=sid, prompt="ping", timeout_s=60
        )

    print("Comprehensive testing complete.")


if __name__ == "__main__":
    asyncio.run(main())
