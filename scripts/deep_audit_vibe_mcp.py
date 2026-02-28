"""
Vibe MCP Deep Audit — Comprehensive Testing
=============================================
Tests ALL Vibe MCP tools, config template sync, proxy readiness,
and VibeConfig model integrity.

Run:
    cd /Users/dev/Documents/GitHub/atlastrinity
    PYTHONPATH=. .venv/bin/python scripts/verify_vibe_mcp_all_tools.py --deep
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("vibe_deep_audit")

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

PASS = 0
WARN = 0
FAIL = 0


def ok(msg: str):
    global PASS
    PASS += 1
    print(f"  {GREEN}✅ {msg}{RESET}")


def warn(msg: str):
    global WARN
    WARN += 1
    print(f"  {YELLOW}⚠️  {msg}{RESET}")


def fail(msg: str):
    global FAIL
    FAIL += 1
    print(f"  {RED}❌ {msg}{RESET}")


def section(title: str):
    print(f"\n{BOLD}{CYAN}{'─' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 60}{RESET}")


def make_mock_ctx():
    ctx = MagicMock()
    ctx.log = AsyncMock()
    ctx.request_context = MagicMock()
    ctx.request_context.session = MagicMock()
    return ctx


async def test_config_template_sync():
    """Test 1: Template vs Active Config Synchronization."""
    section("TEST 1: Config Template ↔ Active Config Sync")

    template_path = PROJECT_ROOT / "config" / "vibe_config.toml.template"
    active_path = Path.home() / ".config" / "atlastrinity" / "vibe_config.toml"

    if not template_path.exists():
        fail(f"Template not found: {template_path}")
        return
    ok(f"Template exists: {template_path.name}")

    if not active_path.exists():
        fail(f"Active config not found: {active_path}")
        return
    ok(f"Active config exists: {active_path.name}")

    # Compare line counts
    t_lines = template_path.read_text().splitlines()
    a_lines = active_path.read_text().splitlines()
    if len(t_lines) == len(a_lines):
        ok(f"Line count matches: {len(t_lines)} lines")
    else:
        warn(f"Line count differs: template={len(t_lines)}, active={len(a_lines)}")

    # Check key fields
    a_text = active_path.read_text()
    t_text = template_path.read_text()

    # Verify variables are expanded in active
    if "${PROJECT_ROOT}" in a_text or "${CONFIG_ROOT}" in a_text:
        fail("Active config still contains unexpanded ${} placeholders!")
    else:
        ok("All placeholders expanded in active config")

    # Verify template HAS placeholders
    if "${PROJECT_ROOT}" in t_text:
        ok("Template correctly uses ${PROJECT_ROOT} placeholders")
    else:
        warn("Template missing ${PROJECT_ROOT} — may be hardcoded")

    # Key structural checks
    for key in ["active_model", "fallback_chain", "default_mode", "timeout_s"]:
        if key in a_text:
            ok(f"Key '{key}' present in active config")
        else:
            fail(f"Key '{key}' MISSING in active config")


async def test_agent_profiles():
    """Test 2: Agent Profile Templates."""
    section("TEST 2: Agent Profile Templates")

    agents_dir = PROJECT_ROOT / "config" / "vibe" / "agents"
    if not agents_dir.exists():
        fail(f"Agents dir not found: {agents_dir}")
        return

    expected_profiles = ["auto-approve.toml.template", "plan.toml.template", "accept-edits.toml.template"]
    for profile in expected_profiles:
        path = agents_dir / profile
        if path.exists():
            content = path.read_text()
            if "permission" in content:
                ok(f"{profile}: exists, has tool permissions")
            else:
                warn(f"{profile}: exists but NO tool permissions defined")
        else:
            fail(f"{profile}: NOT FOUND")

    # Check cognitive profiles
    cognitive = list(agents_dir.glob("cognitive*"))
    if cognitive:
        ok(f"Found {len(cognitive)} cognitive profile(s)")
    else:
        warn("No cognitive profiles found")


async def test_vibe_config_model():
    """Test 3: VibeConfig Pydantic Model Integrity."""
    section("TEST 3: VibeConfig Model Integrity")

    from src.mcp_server.vibe_config import AgentMode, VibeConfig

    # Load from active config
    config = VibeConfig.load()

    # Active model
    if config.active_model:
        ok(f"active_model: '{config.active_model}'")
    else:
        fail("active_model is empty!")

    # Providers
    if len(config.providers) >= 2:
        ok(f"Providers: {len(config.providers)} ({', '.join(p.name for p in config.providers)})")
    else:
        fail(f"Only {len(config.providers)} provider(s) configured (expected ≥ 2)")

    # Each provider has valid fields
    for p in config.providers:
        if p.name and p.api_base and p.api_key_env_var:
            ok(f"Provider '{p.name}': api_base={p.api_base[:30]}..., key_var={p.api_key_env_var}")
        else:
            fail(f"Provider '{p.name}' has missing fields")

    # Models
    if len(config.models) >= 10:
        ok(f"Models: {len(config.models)} configured")
    else:
        warn(f"Only {len(config.models)} model(s) (expected ≥ 10)")

    # Check active model exists in model list
    model_aliases = [m.alias for m in config.models]
    model_names = [m.name for m in config.models]
    if config.active_model in model_aliases or config.active_model in model_names:
        ok(f"Active model '{config.active_model}' found in model list")
    else:
        fail(f"Active model '{config.active_model}' NOT in model list!")

    # Fallback chain
    if config.fallback_chain:
        ok(f"Fallback chain: {config.fallback_chain}")
        for alias in config.fallback_chain:
            if alias in model_aliases or alias in model_names:
                ok(f"  Fallback '{alias}' → found in models")
            else:
                warn(f"  Fallback '{alias}' → NOT found in models list")
    else:
        warn("No fallback chain configured")

    # MCP Servers
    if config.mcp_servers:
        ok(f"MCP servers: {len(config.mcp_servers)} ({', '.join(s.name for s in config.mcp_servers)})")
    else:
        warn("No MCP servers configured for Vibe")

    # Mode
    ok(f"Default mode: {config.default_mode}")

    # Expand vars test
    test_str = "${PROJECT_ROOT}/test"
    expanded = VibeConfig.expand_vars(test_str)
    if "${PROJECT_ROOT}" not in expanded and "/test" in expanded:
        ok(f"expand_vars works: '{test_str}' → '{expanded}'")
    else:
        fail(f"expand_vars broken: '{test_str}' → '{expanded}'")


async def test_proxy_ports():
    """Test 4: Provider Proxy Port Status."""
    section("TEST 4: Proxy Port Status")

    ports = {"copilot": 8086, "windsurf": 8085}
    for name, port in ports.items():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                result = s.connect_ex(("127.0.0.1", port))
                if result == 0:
                    ok(f"{name} proxy port {port}: ACTIVE (listening)")
                else:
                    warn(f"{name} proxy port {port}: NOT listening (will start on-demand)")
        except Exception as e:
            warn(f"{name} proxy port {port}: check error — {e}")


async def test_all_mcp_tools():
    """Test 5: All MCP Tool Registrations and Safe Invocations."""
    section("TEST 5: MCP Tool Registrations & Safe Invocations")

    from src.mcp_server import vibe_server

    server = vibe_server.server

    # Enumerate tools
    tool_names = []
    if hasattr(server, "_tool_manager") and hasattr(server._tool_manager, "_tools"):
        tool_names = list(server._tool_manager._tools.keys())

    if len(tool_names) >= 18:
        ok(f"Registered tools: {len(tool_names)}")
    else:
        fail(f"Only {len(tool_names)} tools registered (expected ≥ 18)")

    # Expected tool list
    expected_tools = [
        "vibe_which", "vibe_prompt", "vibe_analyze_error",
        "vibe_implement_feature", "vibe_code_review", "vibe_smart_plan",
        "vibe_get_config", "vibe_configure_model", "vibe_set_mode",
        "vibe_configure_provider", "vibe_session_resume",
        "vibe_ask", "vibe_execute_subcommand", "vibe_list_sessions",
        "vibe_session_details", "vibe_reload_config",
        "vibe_check_db", "vibe_get_system_context", "vibe_test_in_sandbox",
    ]

    for tool in expected_tools:
        if tool in tool_names:
            ok(f"Tool registered: {tool}")
        else:
            fail(f"Tool MISSING: {tool}")

    # Run safe tools
    safe_tests = {
        "vibe_which": {},
        "vibe_get_config": {},
        "vibe_reload_config": {},
        "vibe_list_sessions": {"limit": 3},
        "vibe_get_system_context": {},
        "vibe_check_db": {"query": "SELECT 1", "action": "query"},
    }

    print(f"\n  {BOLD}Running safe tool invocations:{RESET}")
    for tool_name, kwargs in safe_tests.items():
        ctx = make_mock_ctx()
        t0 = time.monotonic()
        try:
            func = getattr(vibe_server, tool_name)
            result = await func(ctx=ctx, **kwargs)
            elapsed = time.monotonic() - t0

            if isinstance(result, dict) and result.get("error"):
                warn(f"  {tool_name} ({elapsed:.2f}s): {result['error'][:60]}")
            else:
                ok(f"  {tool_name} ({elapsed:.2f}s): OK")

                # Extra assertions for specific tools
                if tool_name == "vibe_which" and isinstance(result, dict):
                    binary = result.get("binary", "")
                    if binary and os.path.exists(binary):
                        ok(f"    Binary verified: {binary}")
                    else:
                        warn(f"    Binary path issue: {binary}")

                    model = result.get("model", "")
                    if model:
                        ok(f"    Current model: {model}")

                if tool_name == "vibe_get_config" and isinstance(result, dict):
                    providers = result.get("providers", [])
                    models = result.get("models", [])
                    if providers:
                        ok(f"    Config reports {len(providers)} providers, {len(models)} models")

        except Exception as e:
            elapsed = time.monotonic() - t0
            fail(f"  {tool_name} ({elapsed:.2f}s): EXCEPTION — {str(e)[:80]}")


async def test_configure_tools():
    """Test 6: Configuration MCP Tools."""
    section("TEST 6: Configuration Tools (Runtime)")

    from src.mcp_server import vibe_server

    ctx = make_mock_ctx()

    # Test vibe_set_mode
    try:
        result = await vibe_server.vibe_set_mode(ctx=ctx, mode="auto-approve")
        if isinstance(result, dict) and not result.get("error"):
            ok(f"vibe_set_mode('auto-approve'): OK — {result.get('mode', 'unknown')}")
        else:
            warn(f"vibe_set_mode: {result}")
    except Exception as e:
        fail(f"vibe_set_mode: {e}")

    # Test vibe_configure_model
    try:
        result = await vibe_server.vibe_configure_model(ctx=ctx, model_alias="gpt-4o")
        if isinstance(result, dict) and not result.get("error"):
            ok(f"vibe_configure_model('gpt-4o'): OK — active={result.get('active_model', '?')}")
        else:
            warn(f"vibe_configure_model: {result}")
    except Exception as e:
        fail(f"vibe_configure_model: {e}")


async def test_logging_pipeline():
    """Test 7: Verify logging reaches terminal (INFO level)."""
    section("TEST 7: Logging Pipeline Check")

    from src.mcp_server import vibe_server

    vibe_logger = logging.getLogger("vibe_mcp")

    # Check handlers
    stream_handlers = [h for h in vibe_logger.handlers if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)]
    file_handlers = [h for h in vibe_logger.handlers if isinstance(h, logging.FileHandler)]

    if stream_handlers:
        sh = stream_handlers[0]
        if sh.level <= logging.INFO:
            ok(f"StreamHandler level: {logging.getLevelName(sh.level)} (≤ INFO)")
        else:
            fail(f"StreamHandler level: {logging.getLevelName(sh.level)} (> INFO — logs won't show!)")
    else:
        fail("No StreamHandler on vibe_mcp logger!")

    if file_handlers:
        ok(f"FileHandler: writing to {file_handlers[0].baseFilename}")
    else:
        warn("No FileHandler on vibe_mcp logger")

    # Verify _format_and_emit_vibe_log uses logger.info
    import inspect

    source = inspect.getsource(vibe_server._format_and_emit_vibe_log)
    if "logger.info(" in source:
        ok("_format_and_emit_vibe_log uses logger.info() ✓")
    elif "logger.debug(" in source:
        fail("_format_and_emit_vibe_log still uses logger.debug() — logs won't show in terminal!")
    else:
        warn("Unexpected logger call pattern in _format_and_emit_vibe_log")


async def test_vibe_binary():
    """Test 8: Vibe CLI Binary."""
    section("TEST 8: Vibe CLI Binary")

    from src.mcp_server.vibe_server import resolve_vibe_binary

    binary = resolve_vibe_binary()
    if binary:
        ok(f"Binary found: {binary}")
        if os.access(binary, os.X_OK):
            ok("Binary is executable")
        else:
            fail("Binary is NOT executable!")
    else:
        fail("Vibe binary NOT FOUND in PATH or ~/.local/bin/vibe")


async def test_workspace_and_dirs():
    """Test 9: Workspace and Required Directories."""
    section("TEST 9: Workspace & Directories")

    from src.mcp_server.vibe_server import CONFIG_ROOT, get_vibe_workspace

    ws = get_vibe_workspace()
    if os.path.isdir(ws):
        ok(f"Workspace: {ws}")
    else:
        fail(f"Workspace MISSING: {ws}")

    required_dirs = [
        CONFIG_ROOT / "logs",
        CONFIG_ROOT / "vibe" / "logs" / "session",
        CONFIG_ROOT / "data",
    ]
    for d in required_dirs:
        if d.exists():
            ok(f"Dir exists: {d.name}/")
        else:
            warn(f"Dir missing: {d}")


async def main():
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  🔍 VIBE MCP DEEP AUDIT{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")

    await test_config_template_sync()
    await test_agent_profiles()
    await test_vibe_config_model()
    await test_proxy_ports()
    await test_all_mcp_tools()
    await test_configure_tools()
    await test_logging_pipeline()
    await test_vibe_binary()
    await test_workspace_and_dirs()

    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  📊 FINAL RESULTS{RESET}")
    print(f"{'=' * 60}")
    print(f"  {GREEN}✅ PASS: {PASS}{RESET}")
    print(f"  {YELLOW}⚠️  WARN: {WARN}{RESET}")
    print(f"  {RED}❌ FAIL: {FAIL}{RESET}")
    total = PASS + WARN + FAIL
    score = (PASS / total * 100) if total else 0
    color = GREEN if score >= 90 else YELLOW if score >= 70 else RED
    print(f"  {color}Score: {score:.0f}% ({PASS}/{total}){RESET}")
    print(f"{'=' * 60}\n")

    return FAIL == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
