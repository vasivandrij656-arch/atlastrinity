"""AtlasTrinity MCP Server Health Check

Enhanced CLI tool for checking MCP server status with:
- Colored terminal output (green/yellow/red)
- Tier information for each server
- Response time and tool count
- JSON output for automation (--json flag)
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

# Add src to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
sys.path.insert(0, PROJECT_ROOT)  # Ensure src.brain etc works if imported as src.brain


class Colors:
    """ANSI color codes for terminal output."""

    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ENDC = "\033[0m"


async def check_mcp(
    output_json: bool = False,
    show_tools: bool = False,
    check_all: bool = False,
    verify_tools: bool = False,
):
    """Run MCP health checks for all servers."""
    from src.brain.config import ensure_dirs
    from src.brain.mcp.mcp_manager import mcp_manager
    from src.brain.mcp.mcp_registry import SERVER_CATALOG, get_tool_names_for_server

    ensure_dirs()

    config_servers = mcp_manager.config.get("mcpServers", {})
    results = {}

    if check_all:
        # Use full catalog as source
        servers_to_check = []
        for name in SERVER_CATALOG:
            if name.startswith("_"):
                continue
            # Use data from config if available, else catalog info
            cfg = config_servers.get(name, {"disabled": False, "tier": 2})
            if "name" not in cfg:
                cfg["name"] = name
            servers_to_check.append((name, cfg))
    else:
        # Filter out comment keys and disabled servers
        servers_to_check = [
            (name, cfg)
            for name, cfg in config_servers.items()
            if not name.startswith("_") and not cfg.get("disabled", False)
        ]

    if not output_json:
        status_msg = "Перевірка здоров'я MCP серверів"
        if verify_tools:
            status_msg += " з верифікацією інструментів"
        print(f"\n{Colors.CYAN}{Colors.BOLD}🔍 {status_msg}...{Colors.ENDC}")
        print(f"{Colors.DIM}{'=' * 60}{Colors.ENDC}")

    # Tool verification registry: server_name -> (tool_name, arguments)
    VERIFY_REGISTRY = {
        "filesystem": ("list_allowed_directories", {}),
        "memory": ("list_entities", {}),
        "vibe": ("vibe_get_config", {}),
        "duckduckgo-search": ("duckduckgo_search", {"query": "AtlasTrinity", "max_results": 1}),
        "sequential-thinking": (
            "sequentialthinking",
            {"thought": "Health check probe", "thoughtNumber": 1, "totalThoughts": 1},
        ),
        "github": ("search_repositories", {"query": "AtlasTrinity", "per_page": 1}),
        "devtools": ("devtools_validate_config", {}),
        "chrome-devtools": ("browser_inspect", {}),
        "puppeteer": ("puppeteer_navigate", {"url": "https://google.com"}),
    }

    for server_name, server_config in servers_to_check:
        tier = server_config.get("tier", 4)

        # Special case for internal services
        if server_name in ["system", "tour-guide"]:
            tools = get_tool_names_for_server(server_name)
            note = "Internal Trinity System" if server_name == "system" else "Internal Tour Control"
            results[server_name] = {
                "status": "online",
                "tier": tier,
                "tools_count": len(tools),
                "response_time_ms": 0,
                "note": note,
            }
            if not output_json:
                print(
                    f"  {Colors.GREEN}✅ {server_name:<20}{Colors.ENDC} [Tier {tier}] {Colors.BOLD}{len(tools):>3} tools{Colors.ENDC} (Internal)"
                )
                if show_tools:
                    for name in sorted(tools):
                        print(f"      {Colors.DIM}•{Colors.ENDC} {name}")
            continue

        try:
            import time

            start = time.time()

            # list_tools will automatically call get_session and connect if needed
            tools = await asyncio.wait_for(mcp_manager.list_tools(server_name), timeout=30.0)

            elapsed = (time.time() - start) * 1000  # ms

            if tools:
                tool_names = sorted([t.name if hasattr(t, "name") else str(t) for t in tools])
                results[server_name] = {
                    "status": "online",
                    "tier": tier,
                    "tools_count": len(tools),
                    "response_time_ms": round(elapsed, 1),
                }
                if not output_json:
                    print(
                        f"  {Colors.GREEN}✅ {server_name:<20}{Colors.ENDC} [Tier {tier}] {Colors.BOLD}{len(tools):>3} tools{Colors.ENDC} ({elapsed:>.1f}ms)"
                    )
                    if show_tools:
                        for name in tool_names:
                            print(f"      {Colors.DIM}•{Colors.ENDC} {name}")

                # Deep verification
                if verify_tools and server_name in VERIFY_REGISTRY:
                    tool_name, tool_args = VERIFY_REGISTRY[server_name]
                    try:
                        v_start = time.time()
                        v_result = await mcp_manager.call_tool(server_name, tool_name, tool_args)
                        v_elapsed = (time.time() - v_start) * 1000

                        if v_result:  # Assume success if we got a result
                            results[server_name]["verified"] = True
                            results[server_name]["verify_tool"] = tool_name
                            results[server_name]["verify_time_ms"] = round(v_elapsed, 1)
                            if not output_json:
                                print(
                                    f"      {Colors.GREEN}↳ Verified: {tool_name}{Colors.ENDC} ({v_elapsed:>.1f}ms)"
                                )
                        else:
                            results[server_name]["verified"] = False
                            results[server_name]["status"] = "degraded"
                            if not output_json:
                                print(
                                    f"      {Colors.RED}↳ Verification Failed: {tool_name} (No result){Colors.ENDC}"
                                )
                    except Exception as ve:
                        results[server_name]["verified"] = False
                        results[server_name]["status"] = "degraded"
                        results[server_name]["verify_error"] = str(ve)
                        if not output_json:
                            print(
                                f"      {Colors.RED}↳ Verification Error: {tool_name} ({str(ve)[:40]}){Colors.ENDC}"
                            )
            # check if it's connected
            elif server_name in mcp_manager.sessions:
                results[server_name] = {
                    "status": "degraded",
                    "tier": tier,
                    "tools_count": 0,
                    "response_time_ms": round(elapsed, 1),
                    "note": "Connected but no tools",
                }
                if not output_json:
                    print(
                        f"  {Colors.YELLOW}⚠️  {server_name:<20}{Colors.ENDC} [Tier {tier}] {Colors.BOLD}Degraded{Colors.ENDC} (Connected, no tools)"
                    )
            else:
                results[server_name] = {
                    "status": "offline",
                    "tier": tier,
                    "error": "Failed to get session",
                }
                if not output_json:
                    print(
                        f"  {Colors.RED}❌ {server_name:<20}{Colors.ENDC} [Tier {tier}] {Colors.BOLD}Offline{Colors.ENDC} (Failed to get session)"
                    )

            # Special check for xcodebuild bridge
            if server_name == "xcodebuild" and results[server_name]["status"] == "online":
                # Check for bridged backends
                bridged = []
                # Check config or predefined list
                if config_servers.get("macos-use", {}).get("disabled"):
                    bridged.append("macos-use (63 tools)")
                if config_servers.get("googlemaps", {}).get("disabled"):
                    bridged.append("googlemaps (11 tools)")

                if bridged and not output_json:
                    print(f"      {Colors.DIM}↳ Bridging: {', '.join(bridged)}{Colors.ENDC}")
                    results[server_name]["note"] = f"Bridges: {', '.join(bridged)}"

        except TimeoutError:
            results[server_name] = {
                "status": "offline",
                "tier": tier,
                "error": "Connection timeout (30s)",
            }
            if not output_json:
                print(
                    f"  {Colors.RED}❌ {server_name:<20}{Colors.ENDC} [Tier {tier}] {Colors.BOLD}Timeout{Colors.ENDC} (30s)"
                )

        except Exception as e:
            results[server_name] = {
                "status": "offline",
                "tier": tier,
                "error": str(e)[:100],
            }
            if not output_json:
                print(
                    f"  {Colors.RED}❌ {server_name:<20}{Colors.ENDC} [Tier {tier}] {Colors.BOLD}Error{Colors.ENDC} ({str(e)[:40]}...)"
                )

    if output_json:
        print(
            json.dumps(
                {
                    "timestamp": datetime.now().isoformat(),
                    "total_servers": len(results),
                    "online": sum(1 for r in results.values() if r["status"] == "online"),
                    "offline": sum(1 for r in results.values() if r["status"] == "offline"),
                    "degraded": sum(1 for r in results.values() if r["status"] == "degraded"),
                    "servers": results,
                },
                indent=2,
            )
        )
    else:
        # Summary
        online = sum(1 for r in results.values() if r["status"] == "online")
        offline = sum(1 for r in results.values() if r["status"] == "offline")
        degraded = sum(1 for r in results.values() if r["status"] == "degraded")
        total = len(results)

        print(f"\n{Colors.CYAN}{Colors.BOLD}Підсумок:{Colors.ENDC}")
        print(f"  Всього:    {total}")
        print(
            f"  Online:   {Colors.GREEN if online == total else Colors.YELLOW}{online}{Colors.ENDC}"
        )
        if degraded > 0:
            print(f"  Degraded: {Colors.YELLOW}{degraded}{Colors.ENDC}")
        if offline > 0:
            print(f"  Offline:  {Colors.RED}{offline}{Colors.ENDC}")

        health_pct = (online / total * 100) if total > 0 else 0
        print(
            f"  Здоров'я: {Colors.GREEN if health_pct > 90 else Colors.YELLOW if health_pct > 50 else Colors.RED}{health_pct:>.1f}%{Colors.ENDC}"
        )
        print(f"{Colors.DIM}{'=' * 60}{Colors.ENDC}\n")


def main():
    parser = argparse.ArgumentParser(description="Check MCP server health")
    parser.add_argument("--json", action="store_true", help="Output in JSON format for automation")
    parser.add_argument("--tools", action="store_true", help="List all tools for each server")
    parser.add_argument(
        "--all", action="store_true", help="Probe all servers in registry, even if disabled"
    )
    parser.add_argument(
        "--verify", action="store_true", help="Perform deep tool execution verification"
    )
    args = parser.parse_args()

    asyncio.run(
        check_mcp(
            output_json=args.json,
            show_tools=args.tools,
            check_all=args.all,
            verify_tools=args.verify,
        )
    )


if __name__ == "__main__":
    main()
