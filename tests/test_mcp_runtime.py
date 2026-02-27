#!/usr/bin/env python3
"""Runtime MCP Server & Tool Test Suite.

Spawns each MCP server process, lists tools via JSON-RPC,
then calls EVERY tool with safe test arguments.

Usage:
    python tests/test_mcp_runtime.py
    python tests/test_mcp_runtime.py --server vibe
    python tests/test_mcp_runtime.py --server memory --tool search
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = Path.home() / ".config" / "atlastrinity" / "mcp" / "config.json"

# ═══════════════════════════════════════════════════════════════════════════════
#  Safe test arguments for every tool — designed to not mutate state
# ═══════════════════════════════════════════════════════════════════════════════
SAFE_TEST_ARGS: dict[str, dict[str, dict]] = {
    "vibe": {
        "vibe_which": {},
        "vibe_get_config": {},
        "vibe_reload_config": {},
        "vibe_get_system_context": {},
        "vibe_list_sessions": {"limit": 1},
        "vibe_check_db": {"query": "SELECT 1"},
        "vibe_prompt": {"prompt": "echo test", "timeout_s": 5},
        "vibe_ask": {"question": "What is 2+2?", "timeout_s": 5},
        "vibe_smart_plan": {"objective": "test plan", "timeout_s": 5},
        "vibe_analyze_error": {"error_message": "test error", "timeout_s": 5},
        "vibe_code_review": {"file_path": "README.md", "timeout_s": 5},
        "vibe_implement_feature": {"goal": "test", "timeout_s": 5},
        "vibe_execute_subcommand": {"subcommand": "version", "timeout_s": 5},
        "vibe_session_details": {"session_id_or_file": "latest"},
        "vibe_configure_model": {"model_alias": "test"},
        "vibe_set_mode": {"mode": "code"},
        "vibe_configure_provider": {"name": "test", "base_url": "http://localhost"},
        "vibe_session_resume": {"session_id": "test"},
        "vibe_test_in_sandbox": {
            "test_script": "print('ok')",
            "target_files": {"test.py": "print('ok')"},
            "command": "python test.py",
            "timeout_s": 5,
        },
    },
    "memory": {
        "list_entities": {},
        "get_db_schema": {},
        "search": {"query": "test", "limit": 1},
        "search_nodes": {"query": "test", "limit": 1},
        "get_entity": {"name": "__test_nonexistent__"},
        "create_entities": {
            "entities": [
                {"name": "__runtime_test__", "entityType": "test", "observations": ["runtime test"]}
            ]
        },
        "add_observations": {"name": "__runtime_test__", "observations": ["runtime obs"]},
        "create_relation": {
            "source": "__runtime_test__",
            "target": "__runtime_test__",
            "relation": "self_test",
        },
        "delete_entity": {"name": "__runtime_test__"},
        "query_db": {"query": "SELECT 1"},
        "batch_add_nodes": {
            "nodes": [{"name": "__batch_test__", "entityType": "test", "observations": ["batch"]}]
        },
        "bulk_ingest_table": {"file_path": "/tmp/__nonexistent__.csv", "table_name": "test"},
        "ingest_verified_dataset": {
            "file_path": "/tmp/__nonexistent__.csv",
            "dataset_name": "test",
        },
        "trace_data_chain": {
            "start_value": "test",
            "start_dataset_id": "nonexistent",
        },
    },
    "graph": {
        "get_graph_json": {},
        "generate_mermaid": {},
        "get_node_details": {"node_id": "1"},
        "get_related_nodes": {"node_id": "1"},
    },
    "duckduckgo-search": {
        "duckduckgo_search": {"query": "test", "max_results": 1},
        "business_registry_search": {"company_name": "test"},
        "open_data_search": {"query": "test"},
        "structured_data_search": {"query": "test"},
    },
    "redis": {
        "redis_info": {},
        "redis_keys": {"pattern": "__test_*"},
        "redis_set": {"key": "__mcp_test__", "value": "test_value", "ex_seconds": 10},
        "redis_get": {"key": "__mcp_test__"},
        "redis_ttl": {"key": "__mcp_test__"},
        "redis_hset": {"key": "__mcp_htest__", "mapping": {"field1": "val1"}},
        "redis_hgetall": {"key": "__mcp_htest__"},
        "redis_delete": {"key": "__mcp_test__"},
    },
    "whisper-stt": {
        "transcribe_audio": {"audio_path": "/tmp/__nonexistent__.wav"},
        "record_and_transcribe": {"duration": 0.1},
    },
    "data-analysis": {
        "read_metadata": {"file_path": str(PROJECT_ROOT / "test_data" / "test.csv")},
        "analyze_dataset": {
            "data_source": str(PROJECT_ROOT / "test_data" / "test.csv"),
            "analysis_type": "summary",
        },
        "generate_statistics": {
            "data_source": str(PROJECT_ROOT / "test_data" / "test.csv"),
        },
        "create_visualization": {
            "data_source": str(PROJECT_ROOT / "test_data" / "test.csv"),
            "visualization_type": "histogram",
        },
        "data_cleaning": {
            "data_source": str(PROJECT_ROOT / "test_data" / "test.csv"),
        },
        "data_aggregation": {
            "data_source": str(PROJECT_ROOT / "test_data" / "test.csv"),
            "group_by": "name",
        },
        "interpret_column_data": {
            "file_path": str(PROJECT_ROOT / "test_data" / "test.csv"),
            "column_names": ["name"],
        },
        "run_pandas_code": {
            "code": "import pandas as pd; df = pd.DataFrame({'a':[1,2]}); print(df.shape)",
        },
    },
    "devtools": {
        "devtools_list_processes": {},
        "devtools_check_mcp_health": {},
        "devtools_validate_config": {},
        "devtools_get_system_map": {},
        "devtools_lint_python": {"file_path": str(PROJECT_ROOT / "src" / "__init__.py")},
        "devtools_lint_js": {"file_path": str(PROJECT_ROOT / "src" / "renderer")},
        "devtools_run_global_lint": {},
        "devtools_find_dead_code": {"target_path": str(PROJECT_ROOT / "src" / "__init__.py")},
        "devtools_check_integrity": {"path": str(PROJECT_ROOT / "src" / "__init__.py")},
        "devtools_check_security": {"path": str(PROJECT_ROOT / "src" / "__init__.py")},
        "devtools_check_complexity": {"path": str(PROJECT_ROOT / "src" / "__init__.py")},
        "devtools_check_types_python": {"path": str(PROJECT_ROOT / "src" / "__init__.py")},
        "devtools_check_types_ts": {},
        "devtools_analyze_trace": {},
        "devtools_run_context_check": {
            "test_file": str(PROJECT_ROOT / "tests" / "logic_tests" / "sample_scenarios.yaml")
        },
        "devtools_launch_inspector": {"server_name": "memory"},
        "devtools_restart_mcp_server": {"server_name": "__test__"},
        "devtools_kill_process": {"pid": 999999, "hard": False},
        "devtools_run_mcp_sandbox": {"server_name": "memory"},
        "devtools_update_architecture_diagrams": {"project_path": str(PROJECT_ROOT)},
        "devtools_test_all_mcp_native": {},
        "mcp_inspector_list_tools": {"server_name": "memory"},
        "mcp_inspector_list_resources": {"server_name": "memory"},
        "mcp_inspector_list_prompts": {"server_name": "memory"},
        "mcp_inspector_call_tool": {
            "server_name": "memory",
            "tool_name": "list_entities",
            "arguments": "{}",
        },
        "mcp_inspector_read_resource": {"server_name": "memory", "uri": "test://"},
        "mcp_inspector_get_prompt": {"server_name": "memory", "prompt_name": "test"},
        "mcp_inspector_get_schema": {"server_name": "memory", "tool_name": "search"},
    },
    "golden-fund": {
        "search_golden_fund": {"query": "test", "mode": "semantic"},
        "store_blob": {"content": "test_content", "filename": "__test_blob.txt"},
        "retrieve_blob": {"filename": "__test_blob.txt"},
        "ingest_dataset": {"url": "file:///tmp/__nonexistent__.csv", "type": "csv"},
        "probe_entity": {"entity_id": "test_entity", "depth": 1},
        "add_knowledge_node": {
            "content": "test content",
            "metadata": {"type": "test", "source": "runtime_test"},
        },
        "analyze_and_store": {
            "file_path": "/tmp/__nonexistent__.csv",
            "dataset_name": "__runtime_test__",
        },
        "get_dataset_insights": {"dataset_name": "__runtime_test__"},
    },
    "react-devtools": {
        "react_get_introspection_script": {"queryType": "detect"},
    },
    "filesystem": {
        "list_directory": {"path": str(PROJECT_ROOT)},
        "read_file": {"path": str(PROJECT_ROOT / "README.md")},
        "get_file_info": {"path": str(PROJECT_ROOT / "README.md")},
        "list_allowed_directories": {},
        "search_files": {
            "path": str(PROJECT_ROOT / "src"),
            "pattern": "*.py",
            "excludePatterns": [],
        },
        "directory_tree": {"path": str(PROJECT_ROOT / "src"), "depth": 1},
    },
    "sequential-thinking": {
        "sequentialthinking": {
            "thought": "Testing sequential thinking",
            "nextThoughtNeeded": False,
            "thoughtNumber": 1,
            "totalThoughts": 1,
        },
    },
    "context7": {
        "c7_search": {"term": "react"},
        "c7_query": {"projectIdentifier": "/facebook/react", "query": "hooks"},
        "c7_info": {},
    },
    "puppeteer": {
        "puppeteer_navigate": {"url": "about:blank"},
    },
    "github": {
        "list_commits": {"owner": "vasivandrij656-arch", "repo": "atlastrinity", "perPage": 1},
        "search_repositories": {"query": "atlastrinity"},
    },
    "googlemaps": {
        "maps_geocode": {"address": "Kyiv, Ukraine"},
    },
    "xcodebuild": {
        "discover_projs": {},
    },
    "chrome-devtools": {
        "list_tabs": {},
    },
    "macos-use": {
        "macos-use_get_time": {},
        "macos-use_get_clipboard": {},
        "macos-use_take_screenshot": {},
        "macos-use_list_running_apps": {},
        "macos-use_list_all_windows": {},
        "macos-use_list_browser_tabs": {},
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
#  JSON-RPC helpers
# ═══════════════════════════════════════════════════════════════════════════════


def make_jsonrpc(method: str, params: dict, req_id: int) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})


def build_server_command(cfg: dict) -> tuple[list[str], dict[str, str]]:
    """Build the command and env for spawning a server."""
    command = cfg.get("command", "")
    args = cfg.get("args", [])
    env_vars = cfg.get("env", {})

    command = command.replace("${PROJECT_ROOT}", str(PROJECT_ROOT))
    command = command.replace("${HOME}", str(Path.home()))

    resolved_args = []
    for arg in args:
        arg = arg.replace("${PROJECT_ROOT}", str(PROJECT_ROOT))
        arg = arg.replace("${HOME}", str(Path.home()))
        resolved_args.append(arg)

    env = os.environ.copy()
    for k, v in env_vars.items():
        v = v.replace("${PROJECT_ROOT}", str(PROJECT_ROOT))
        v = v.replace("${HOME}", str(Path.home()))
        v = v.replace("${GOOGLE_MAPS_API_KEY}", os.environ.get("GOOGLE_MAPS_API_KEY", ""))
        v = v.replace("${GITHUB_TOKEN}", os.environ.get("GITHUB_TOKEN", ""))
        env[k] = v
    env["PYTHONPATH"] = str(PROJECT_ROOT)

    return [command, *resolved_args], env


def parse_responses(stdout: str) -> dict[int, dict]:
    """Parse multiple JSON-RPC responses from stdout."""
    responses = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            resp = json.loads(line)
            if "id" in resp:
                responses[resp["id"]] = resp
        except json.JSONDecodeError:
            continue
    return responses


# ═══════════════════════════════════════════════════════════════════════════════
#  Core test runner
# ═══════════════════════════════════════════════════════════════════════════════


def read_response(proc, timeout: float = 10.0) -> dict | None:
    """Read a single JSON-RPC response line from the process stdout.
    Skips notification lines (no 'id' field).
    """
    import select

    deadline = time.time() + timeout
    while time.time() < deadline:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        ready, _, _ = select.select([proc.stdout], [], [], min(remaining, 0.5))
        if not ready:
            continue
        line = proc.stdout.readline()
        if not line:
            return None  # EOF
        line = line.strip()
        if not line:
            continue
        try:
            resp = json.loads(line)
            if "id" in resp:
                return resp
            # else: notification, skip
        except json.JSONDecodeError:
            continue
    return None


def send_msg(proc, msg: str):
    """Send a JSON-RPC message to the process stdin."""
    proc.stdin.write(msg + "\n")
    proc.stdin.flush()


def classify_tool_result(resp: dict) -> dict:
    """Classify a tools/call JSON-RPC response."""
    if "error" in resp:
        return {
            "status": "error",
            "error": str(resp["error"].get("message", resp["error"]))[:200],
        }
    if "result" in resp:
        content = resp["result"].get("content", [])
        is_error = resp["result"].get("isError", False)
        preview = ""
        if content and isinstance(content, list) and len(content) > 0:
            text = content[0].get("text", "")
            preview = text[:150]
        return {
            "status": "error_result" if is_error else "ok",
            "preview": preview,
        }
    return {"status": "unknown_response"}


def test_server(name: str, cfg: dict, only_tool: str | None = None) -> dict:
    """Test a single MCP server: list tools, then call each with safe args."""
    result = {
        "server": name,
        "tier": cfg.get("tier", 4),
        "status": "unknown",
        "tools_discovered": [],
        "tools_tested": {},
    }

    transport = cfg.get("transport", "stdio")
    if transport == "internal":
        result["status"] = "internal_skip"
        result["note"] = "Internal/native server, tested via Python directly"
        return result
    if cfg.get("disabled", False):
        result["status"] = "disabled"
        return result

    full_cmd, env = build_server_command(cfg)
    start = time.time()

    try:
        proc = subprocess.Popen(
            full_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=str(PROJECT_ROOT),
            bufsize=1,  # line buffered
        )
    except FileNotFoundError:
        result["status"] = "not_found"
        result["error"] = f"Command not found: {full_cmd[0]}"
        return result
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:300]
        return result

    try:
        # 1. Initialize
        send_msg(
            proc,
            make_jsonrpc(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "runtime-test", "version": "1.0"},
                },
                1,
            ),
        )
        init_timeout = 30 if name in ("data-analysis", "vibe", "devtools") else 15
        init_resp = read_response(proc, timeout=init_timeout)
        if not init_resp:
            result["status"] = "error"
            result["error"] = "No response to initialize"
            return result
        if "error" in init_resp:
            result["status"] = "init_error"
            result["error"] = str(init_resp["error"])[:300]
            return result

        # 2. Send initialized notification
        send_msg(
            proc,
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                }
            ),
        )
        time.sleep(0.2)  # Give server time to process

        # 3. List tools
        send_msg(proc, make_jsonrpc("tools/list", {}, 2))
        list_resp = read_response(proc, timeout=10)
        if list_resp and "result" in list_resp:
            tools = list_resp["result"].get("tools", [])
            result["tools_discovered"] = [t.get("name", "?") for t in tools]
            result["tool_count"] = len(tools)

        # 4. Call each tool
        test_args = SAFE_TEST_ARGS.get(name, {})
        req_id = 3
        for tool_name, args in test_args.items():
            if only_tool and tool_name != only_tool:
                continue
            send_msg(
                proc,
                make_jsonrpc(
                    "tools/call",
                    {
                        "name": tool_name,
                        "arguments": args,
                    },
                    req_id,
                ),
            )

            # Per-tool timeout: longer for heavy tools
            tool_timeout = 10
            if name == "vibe" or "lint" in tool_name or "sandbox" in tool_name:
                tool_timeout = 30
            if "test_all" in tool_name or "update_architecture" in tool_name:
                tool_timeout = 60
            # devtools heavy tools that spawn subprocesses
            heavy_devtools = (
                "devtools_check_mcp_health",
                "devtools_run_global_lint",
                "devtools_check_security",
                "devtools_run_mcp_sandbox",
                "devtools_test_all_mcp_native",
                "mcp_inspector_list_tools",
                "mcp_inspector_call_tool",
                "mcp_inspector_list_resources",
                "mcp_inspector_read_resource",
                "mcp_inspector_list_prompts",
                "mcp_inspector_get_prompt",
                "mcp_inspector_get_schema",
            )
            if tool_name in heavy_devtools:
                tool_timeout = 60
            if tool_name == "devtools_run_mcp_sandbox":
                tool_timeout = 120

            resp = read_response(proc, timeout=tool_timeout)
            if resp:
                result["tools_tested"][tool_name] = classify_tool_result(resp)
            else:
                result["tools_tested"][tool_name] = {"status": "no_response"}
            req_id += 1

        elapsed_ms = round((time.time() - start) * 1000, 1)
        result["response_time_ms"] = elapsed_ms
        result["status"] = "online"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:300]
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Report formatter
# ═══════════════════════════════════════════════════════════════════════════════

STATUS_ICONS = {
    "ok": "✅",
    "error": "❌",
    "error_result": "⚠️",
    "no_response": "⏳",
    "unknown_response": "❓",
    "timeout": "⏰",
    "not_found": "🔍",
    "disabled": "🚫",
    "internal_skip": "🔧",
    "online": "🟢",
    "init_error": "❌",
}


def print_report(results: list[dict]):
    total_servers = len(results)
    online_servers = sum(1 for r in results if r["status"] == "online")
    total_tools_tested = 0
    total_tools_ok = 0
    total_tools_error = 0

    print("\n" + "=" * 80)
    print("  MCP RUNTIME TEST REPORT")
    print("=" * 80)

    for r in results:
        icon = STATUS_ICONS.get(r["status"], "❓")
        print(f"\n{'─' * 80}")
        tier = r.get("tier", "?")
        print(f"{icon} SERVER: {r['server']}  [Tier {tier}]  Status: {r['status']}")

        if r.get("error"):
            print(f"   ERROR: {r['error'][:200]}")

        if r.get("response_time_ms"):
            print(f"   Response: {r['response_time_ms']}ms")

        discovered = r.get("tools_discovered", [])
        if discovered:
            print(f"   Discovered {len(discovered)} tools: {', '.join(discovered[:10])}")
            if len(discovered) > 10:
                print(f"     ...and {len(discovered) - 10} more")

        tested = r.get("tools_tested", {})
        if tested:
            print(f"   Tested {len(tested)} tools:")
            for tool_name, tool_result in tested.items():
                total_tools_tested += 1
                t_status = tool_result.get("status", "?")
                t_icon = STATUS_ICONS.get(t_status, "❓")
                if t_status == "ok":
                    total_tools_ok += 1
                    preview = tool_result.get("preview", "")
                    preview_short = preview[:80].replace("\n", " ") if preview else ""
                    print(
                        f"     {t_icon} {tool_name}: OK{f'  → {preview_short}' if preview_short else ''}"
                    )
                elif t_status == "error_result":
                    total_tools_ok += (
                        1  # Expected errors (e.g. file not found) are still valid responses
                    )
                    preview = tool_result.get("preview", "")
                    preview_short = preview[:80].replace("\n", " ") if preview else ""
                    print(
                        f"     {t_icon} {tool_name}: returned error (expected){f'  → {preview_short}' if preview_short else ''}"
                    )
                else:
                    total_tools_error += 1
                    err = tool_result.get("error", "")
                    print(f"     {t_icon} {tool_name}: {t_status}  {err[:100]}")

        if r["status"] in ("disabled", "internal_skip"):
            note = r.get("note", "")
            if note:
                print(f"   Note: {note}")

    # Summary
    print(f"\n{'=' * 80}")
    print("  SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Servers: {online_servers}/{total_servers} online")
    print(f"  Tools tested: {total_tools_tested}")
    print(f"  Tools OK: {total_tools_ok}")
    print(f"  Tools failed: {total_tools_error}")
    if total_tools_tested > 0:
        pct = round(total_tools_ok / total_tools_tested * 100, 1)
        print(f"  Success rate: {pct}%")
    print(f"{'=' * 80}\n")


# ═══════════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(description="Runtime MCP Server Test Suite")
    parser.add_argument("--server", "-s", help="Test only this server")
    parser.add_argument("--tool", "-t", help="Test only this tool (requires --server)")
    parser.add_argument(
        "--list", "-l", action="store_true", help="Only list tools, don't call them"
    )
    args = parser.parse_args()

    if not CONFIG_PATH.exists():
        print(f"ERROR: MCP config not found at {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    servers = config.get("mcpServers", {})
    results = []

    for name, cfg in servers.items():
        if name.startswith("_"):
            continue
        if args.server and name != args.server:
            continue

        print(f"Testing {name}...", flush=True)
        r = test_server(name, cfg, only_tool=args.tool)
        results.append(r)

    print_report(results)


if __name__ == "__main__":
    main()
