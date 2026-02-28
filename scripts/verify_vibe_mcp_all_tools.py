"""
Vibe MCP Tools — Comprehensive Diagnostics
============================================
Проверяет все MCP инструменты Vibe сервера:
1. Импорт модуля и перечисление всех зарегистрированных инструментов
2. Запуск безопасных read-only инструментов с mock-контекстом
3. Генерация отчёта о состоянии каждого инструмента

Запуск:
    cd /Users/dev/Documents/GitHub/atlastrinity
    PYTHONPATH=. .venv/bin/python scripts/verify_vibe_mcp_all_tools.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Setup logging to see Vibe output in terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("vibe_diag")

# ---- ANSI colors for terminal output -----
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Tools that are safe to call with minimal/mock args (read-only)
SAFE_TOOLS = {
    "vibe_which": {},
    "vibe_get_config": {},
    "vibe_list_sessions": {"limit": 5},
    "vibe_reload_config": {},
}

# Tools that need a DB (may fail if DB is not initialized — still informative)
DB_TOOLS = {
    "vibe_get_system_context": {},
    "vibe_check_db": {"query": "SELECT 1", "action": "query"},
}


def make_mock_ctx():
    """Create a mock MCP context that records log calls."""
    ctx = MagicMock()
    ctx.log = AsyncMock()
    ctx.request_context = MagicMock()
    ctx.request_context.session = MagicMock()
    return ctx


async def run_diagnostics():
    """Run full Vibe MCP diagnostics."""
    print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  🔧 Vibe MCP Tools — Comprehensive Diagnostics{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 60}{RESET}\n")

    # --------------------------------------------------------
    # Phase 1: Import and list all registered tools
    # --------------------------------------------------------
    print(f"{BOLD}Phase 1: Importing Vibe MCP server module...{RESET}")
    try:
        from src.mcp_server import vibe_server

        server = vibe_server.server
        print(f"  {GREEN}✅ Module imported successfully{RESET}")
    except Exception as e:
        print(f"  {RED}❌ IMPORT FAILED: {e}{RESET}")
        return

    # List tools via FastMCP's internal registry
    print(f"\n{BOLD}Phase 2: Enumerating registered MCP tools...{RESET}")
    tool_names: list[str] = []
    try:
        # FastMCP stores tools in _tool_manager._tools dict
        if hasattr(server, "_tool_manager") and hasattr(server._tool_manager, "_tools"):
            tool_names = list(server._tool_manager._tools.keys())
        elif hasattr(server, "list_tools"):
            # Try the async list
            tools_result = await server.list_tools()
            tool_names = [t.name for t in tools_result]
        else:
            # Fallback: scan for @server.tool() decorated functions
            for attr_name in dir(vibe_server):
                obj = getattr(vibe_server, attr_name)
                if callable(obj) and attr_name.startswith("vibe_"):
                    tool_names.append(attr_name)

        print(f"  Found {BOLD}{len(tool_names)}{RESET} tools:\n")
        for i, name in enumerate(sorted(tool_names), 1):
            print(f"    {i:2d}. {name}")
    except Exception as e:
        print(f"  {YELLOW}⚠️  Could not enumerate tools: {e}{RESET}")
        # Fallback to known list
        tool_names = [
            "vibe_which",
            "vibe_prompt",
            "vibe_analyze_error",
            "vibe_implement_feature",
            "vibe_code_review",
            "vibe_smart_plan",
            "vibe_get_config",
            "vibe_configure_model",
            "vibe_set_mode",
            "vibe_configure_provider",
            "vibe_session_resume",
            "vibe_ask",
            "vibe_execute_subcommand",
            "vibe_list_sessions",
            "vibe_session_details",
            "vibe_reload_config",
            "vibe_check_db",
            "vibe_get_system_context",
            "vibe_test_in_sandbox",
        ]
        print(f"  Using known tool list ({len(tool_names)} tools)")

    # --------------------------------------------------------
    # Phase 3: Run safe read-only tools
    # --------------------------------------------------------
    print(f"\n{BOLD}Phase 3: Running safe (read-only) tools...{RESET}\n")
    results: dict[str, dict] = {}

    for tool_name, kwargs in {**SAFE_TOOLS, **DB_TOOLS}.items():
        ctx = make_mock_ctx()
        print(f"  ▶ {tool_name}...", end=" ", flush=True)
        t0 = time.monotonic()
        try:
            func = getattr(vibe_server, tool_name, None)
            if func is None:
                print(f"{YELLOW}SKIP (not found){RESET}")
                results[tool_name] = {"status": "skip", "reason": "function not found"}
                continue

            result = await func(ctx=ctx, **kwargs)
            elapsed = time.monotonic() - t0

            # Check result
            if isinstance(result, dict):
                if result.get("error"):
                    print(f"{YELLOW}WARN ({elapsed:.2f}s) — {result['error'][:80]}{RESET}")
                    results[tool_name] = {
                        "status": "warn",
                        "elapsed": elapsed,
                        "detail": result.get("error", "")[:200],
                    }
                elif result.get("success") is False:
                    print(f"{YELLOW}WARN ({elapsed:.2f}s) — success=False{RESET}")
                    results[tool_name] = {
                        "status": "warn",
                        "elapsed": elapsed,
                        "detail": str(result)[:200],
                    }
                else:
                    print(f"{GREEN}OK ({elapsed:.2f}s){RESET}")
                    results[tool_name] = {"status": "ok", "elapsed": elapsed}
            else:
                print(f"{GREEN}OK ({elapsed:.2f}s){RESET}")
                results[tool_name] = {"status": "ok", "elapsed": elapsed}

        except Exception as e:
            elapsed = time.monotonic() - t0
            err_msg = str(e)[:100]
            print(f"{RED}FAIL ({elapsed:.2f}s) — {err_msg}{RESET}")
            results[tool_name] = {"status": "fail", "elapsed": elapsed, "detail": err_msg}

    # --------------------------------------------------------
    # Phase 4: Check key configurations
    # --------------------------------------------------------
    print(f"\n{BOLD}Phase 4: Configuration checks...{RESET}\n")

    # Binary
    binary = vibe_server.resolve_vibe_binary()
    if binary:
        print(f"  Vibe binary: {GREEN}{binary}{RESET}")
    else:
        print(f"  Vibe binary: {RED}NOT FOUND{RESET}")

    # Workspace
    ws = vibe_server.get_vibe_workspace()
    ws_exists = os.path.isdir(ws)
    status = GREEN + "exists" + RESET if ws_exists else RED + "MISSING" + RESET
    print(f"  Workspace:   {ws} [{status}]")

    # Config
    try:
        config = vibe_server.get_vibe_config()
        print(f"  Active model: {CYAN}{config.active_model}{RESET}")
        print(f"  Providers:    {len(config.providers)}")
        print(f"  Models:       {len(config.models)}")
        print(f"  MCP servers:  {len(config.mcp_servers)}")
        print(f"  Default mode: {config.default_mode}")
        print(f"  Timeout:      {config.timeout_s}s")
    except Exception as e:
        print(f"  {RED}Config load failed: {e}{RESET}")

    # Log file
    log_file = Path(vibe_server.LOG_DIR) / "vibe_server.log"
    if log_file.exists():
        size_kb = log_file.stat().st_size / 1024
        print(f"  Log file:     {log_file} ({size_kb:.1f} KB)")
    else:
        print(f"  Log file:     {RED}NOT FOUND{RESET}")

    # --------------------------------------------------------
    # Phase 5: Summary
    # --------------------------------------------------------
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  📊 SUMMARY{RESET}")
    print(f"{'=' * 60}")

    total = len(tool_names)
    tested = len(results)
    ok = sum(1 for r in results.values() if r["status"] == "ok")
    warn = sum(1 for r in results.values() if r["status"] == "warn")
    fail = sum(1 for r in results.values() if r["status"] == "fail")
    skip = sum(1 for r in results.values() if r["status"] == "skip")

    print(f"  Total tools registered: {total}")
    print(f"  Tools tested:           {tested}")
    print(f"  {GREEN}✅ OK:     {ok}{RESET}")
    print(f"  {YELLOW}⚠️  WARN:   {warn}{RESET}")
    print(f"  {RED}❌ FAIL:   {fail}{RESET}")
    print(f"  ⏭️  SKIP:   {skip}")

    untested = total - tested
    if untested > 0:
        print(f"\n  🔒 {untested} tools not tested (require live Vibe CLI / write operations)")

    # Show details for non-OK items
    non_ok = {k: v for k, v in results.items() if v["status"] not in ("ok", "skip")}
    if non_ok:
        print(f"\n  {BOLD}Details:{RESET}")
        for name, info in non_ok.items():
            detail = info.get("detail", "no details")
            print(f"    {name}: {detail}")

    print(f"\n{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(run_diagnostics())
