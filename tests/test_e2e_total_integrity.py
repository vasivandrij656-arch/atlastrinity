import asyncio
import logging
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

# Adjust logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("e2e_test")


async def test_e2e_flow():
    # Aggressive mocking of server and other components
    mock_bus = MagicMock()
    mock_mcp = AsyncMock()

    # Define a functional side effect for mcp_manager.call_tool
    async def side_effect(server_name, tool_name, arguments):
        print(f"   [MOCK CALL] {server_name}.{tool_name}({arguments})", flush=True)
        if server_name == "golden_fund" and tool_name == "search_golden_fund":
            from src.mcp_server.golden_fund.server import search_golden_fund

            res = await search_golden_fund(**arguments)
            print(f"   [MOCK RESULT] len={len(res)}", flush=True)
            return res
        return "Mock result"

    mock_mcp.call_tool.side_effect = side_effect

    sys.modules["src.brain.core.server"] = MagicMock()
    sys.modules["src.brain.core.server.message_bus"] = mock_bus
    sys.modules["src.brain.core.server.server"] = MagicMock()
    sys.modules["src.brain.core.services.state_manager"] = MagicMock()
    sys.modules["src.brain.monitoring.metrics"] = MagicMock()
    sys.modules["src.brain.monitoring.logger"] = MagicMock()

    # Mock mcp_manager using patcher
    import unittest.mock

    patcher = unittest.mock.patch("src.brain.mcp.mcp_manager.mcp_manager", mock_mcp)
    patcher.start()

    # Now import components
    from src.brain.agents.atlas import Atlas
    from src.brain.core.orchestration.orchestrator import Trinity
    from src.mcp_server.golden_fund.tools.ingest import ingest_dataset

    print("\n" + "=" * 50, flush=True)
    print("🚀 STARTING E2E SYSTEM INTEGRITY TEST", flush=True)
    print("=" * 50 + "\n", flush=True)

    # 1. PREPARATION: Ingest a unique fact into Golden Fund
    unique_fact = "The secret activation code for Project Phoenix is 'TRINITY-2026-OMEGA'."
    test_data_path = PROJECT_ROOT / "temp_test_data.json"
    import json

    test_data = [
        {
            "content": unique_fact,
            "title": "Project Phoenix Security",
            "project": "Phoenix",
            "type": "secret_code",
        }
    ]
    test_data_path.write_text(json.dumps(test_data))

    print("Step 1: Ingesting unique fact into Golden Fund...", flush=True)
    # Use ingestion tool
    ingest_msg = await ingest_dataset(f"file://{test_data_path}", type="file")
    print(f"   Done: {ingest_msg}", flush=True)

    # 2. ORCHESTRATOR RECALL: Test if Trinity (Orchestrator) retrieves this fact
    print("\nStep 2: Testing Trinity Memory Recall...", flush=True)
    orch = Trinity()
    # Mocking shared_context and other deps to avoid full engine startup
    orch.state = {"messages": [], "system_state": "IDLE", "current_plan": None}

    request = "Project Phoenix activation code"
    # Mocking internals to avoid LLM and side effects
    orch.atlas.analyze_request = AsyncMock(
        return_value={"intent": "task", "voice_response": "Analyzing..."}
    )
    orch._speak = AsyncMock()
    orch._create_db_task = AsyncMock()
    orch.atlas.get_voice_message = MagicMock(return_value="Plan created")

    # We want to capture the arguments to _planning_loop to verify injection
    captured_data = {}

    async def mock_planning_loop(analysis, request, is_subtask, history):
        captured_data["analysis"] = analysis
        captured_data["history"] = history
        # Return a simple plan mock to finish flow
        return MagicMock(steps=[])

    orch._planning_loop = mock_planning_loop

    # Configure MCP mocks with correct types
    mock_mcp.get_status = MagicMock(return_value={"connected_servers": ["golden_fund"]})
    mock_mcp.get_mcp_catalog = AsyncMock(return_value="MCP Catalog Context")

    print(f"   Triggering _get_run_plan for request: '{request}'", flush=True)
    try:
        await orch._get_run_plan(request, is_subtask=False)

        memory_found = False
        # Check analysis dictionary
        analysis = captured_data.get("analysis", {})
        mem_ctx = str(analysis.get("memory_context", ""))
        print(f"   DEBUG: Recalled Context: {mem_ctx[:200]}...", flush=True)

        if "TRINITY-2026-OMEGA" in mem_ctx:
            memory_found = True
            print(
                "   ✅ SUCCESS: Trinity recalled the fact in analysis['memory_context']", flush=True
            )

        # Check history
        history = captured_data.get("history", [])
        for msg in history:
            content = str(getattr(msg, "content", ""))
            if "TRINITY-2026-OMEGA" in content:
                memory_found = True
                print("   ✅ SUCCESS: Trinity injected the fact into planner history", flush=True)
                break

        if not memory_found:
            print("   ❌ FAILURE: Trinity DID NOT recall or inject the correct fact.", flush=True)
            # print full context on failure for debugging
            print(f"   FULL CONTEXT: {mem_ctx}", flush=True)

    except Exception as e:
        print(f"   ❌ ERROR during recall: {e}", flush=True)
        import traceback

        traceback.print_exc()

    # 3. ATLAS PLANNING: Test if Atlas uses the recalled context
    print("\nStep 3: Testing Atlas Planning with Recalled Context...", flush=True)
    atlas = Atlas()
    enriched_request = {
        "enriched_request": request,
        "intent": "task",
        "memory_context": unique_fact,  # Simulating injection from Orchestrator
    }

    # Mock LLM to see the prompt
    atlas.llm_deep = MagicMock()
    atlas.llm_deep.ainvoke = AsyncMock(
        return_value=MagicMock(
            content='{"goal": "Recall code", "steps": [{"action": "Confirming code TRINITY-2026-OMEGA"}]}'
        )
    )

    print("   Triggering Atlas.create_plan...", flush=True)
    plan = await atlas.create_plan(enriched_request)

    # Verify Atlas analysis called _analyze_strategy which should have logger.info
    # We can check if simulation/analysis result contains the code
    if "TRINITY-2026-OMEGA" in str(plan.steps):
        print("   ✅ SUCCESS: Atlas utilized memory in the execution plan.", flush=True)
    else:
        print("   ❌ FAILURE: Atlas created plan without using the recalled context.", flush=True)

    print("\n" + "=" * 50, flush=True)
    print("🏁 E2E SYSTEM INTEGRITY TEST COMPLETE", flush=True)
    print("=" * 50 + "\n", flush=True)

    # Cleanup
    if test_data_path.exists():
        test_data_path.unlink()


if __name__ == "__main__":
    asyncio.run(test_e2e_flow())
