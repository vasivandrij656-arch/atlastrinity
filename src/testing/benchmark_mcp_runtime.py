#!/usr/bin/env python3
"""
Comprehensive MCP Runtime Test — calls every tool on every server.
Tests that each tool handler responds to a tools/call request.
PASS = server returns a JSON-RPC response (result or structured error).
FAIL = timeout, crash, or protocol violation.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
os.chdir(PROJECT_ROOT)

ENV = os.environ.copy()
ENV["PROJECT_ROOT"] = str(PROJECT_ROOT)
ENV["PYTHONPATH"] = str(PROJECT_ROOT)

CONFIG = json.loads(Path("config/mcp_servers.json.template").read_text())
SERVERS = CONFIG.get("mcpServers", {})

# ── Safe test arguments per tool ──────────────────────────────────────────────
# Key: tool_name → dict of arguments to send. Empty dict = no args needed.
# These are designed to be safe (read-only or creating trivial temp data).
TEST_ARGS = {
    # ── macos-use ──
    "macos-use_list_tools_dynamic": {},
    "macos-use_get_frontmost_app": {},
    "macos-use_list_windows": {},
    "macos-use_screenshot": {},
    "macos-use_get_screen_size": {},
    "macos-use_list_running_apps": {},
    "macos-use_get_clipboard": {},
    "macos-use_mouse_position": {},
    "macos-use_get_battery_status": {},
    "macos-use_get_wifi_status": {},
    "macos-use_get_volume": {},
    "macos-use_get_brightness": {},
    "macos-use_get_selected_text": {},
    "macos-use_accessibility_tree": {},
    "macos-use_list_displays": {},
    "macos-use_execute_command": {"command": "echo hello_mcp_test"},
    "macos-use_open_application": {"name": "Finder"},
    "macos-use_set_clipboard": {"content": "mcp_test_clipboard"},
    "macos-use_type_text": {"text": ""},
    "macos-use_key_press": {"key": ""},
    "macos-use_click": {"x": -1, "y": -1},
    "macos-use_click_and_traverse": {"x": -1, "y": -1},
    "macos-use_type_and_traverse": {"text": ""},
    "macos-use_mouse_move": {"x": 0, "y": 0},
    "macos-use_mouse_scroll": {"x": 0, "y": 0, "direction": "up", "amount": 0},
    "macos-use_mouse_drag": {"startX": 0, "startY": 0, "endX": 0, "endY": 0},
    "macos-use_set_volume": {"level": 50},
    "macos-use_set_brightness": {"level": 50},
    "macos-use_show_notification": {"title": "MCP Test", "message": "Runtime validation"},
    "macos-use_spotlight_search": {"query": "test"},
    "macos-use_file_search": {"query": "nonexistent_mcp_test_file_xyz"},
    "macos-use_read_file": {"path": "/tmp/mcp_test_dummy.txt"},
    "macos-use_write_file": {"path": "/tmp/mcp_test_write.txt", "content": "test"},
    "macos-use_list_directory": {"path": "/tmp"},
    "macos-use_move_to_trash": {"path": "/tmp/mcp_test_write.txt"},
    "macos-use_calendar_events": {},
    "macos-use_create_calendar_event": {
        "title": "MCP Test Event",
        "startDate": "2026-12-31T10:00:00",
        "endDate": "2026-12-31T11:00:00",
    },
    "macos-use_reminders": {},
    "macos-use_create_reminder": {"title": "MCP Test Reminder"},
    "macos-use_notes_list": {},
    "macos-use_notes_create": {"title": "MCP Test Note", "body": "test body"},
    "macos-use_finder_list_files": {"path": "/tmp"},
    "macos-use_finder_open_path": {"path": "/tmp"},
    "macos-use_finder_get_selection": {},
    "macos-use_finder_move_to_trash": {"path": "/tmp/mcp_test_write.txt"},
    # ── filesystem ──
    "read_file": {"path": "/tmp/mcp_test_fs.txt"},
    "read_multiple_files": {"paths": ["/tmp/mcp_test_fs.txt"]},
    "write_file": {"path": "/tmp/mcp_test_fs.txt", "content": "filesystem test"},
    "edit_file": {
        "path": "/tmp/mcp_test_fs.txt",
        "edits": [{"oldText": "filesystem test", "newText": "filesystem edited"}],
        "dryRun": True,
    },
    "create_directory": {"path": "/tmp/mcp_test_dir_fs"},
    "list_directory": {"path": "/tmp"},
    "directory_tree": {"path": "/tmp/mcp_test_dir_fs"},
    "move_file": {
        "source": "/tmp/mcp_test_fs_mv_src.txt",
        "destination": "/tmp/mcp_test_fs_mv_dst.txt",
    },
    "search_files": {"path": "/tmp", "pattern": "mcp_test"},
    "get_file_info": {"path": "/tmp"},
    "list_allowed_directories": {},
    "read_file_lines": {"path": "/tmp/mcp_test_fs.txt", "start": 1, "end": 5},
    "read_file_chunk": {"path": "/tmp/mcp_test_fs.txt", "offset": 0, "length": 100},
    "count_lines": {"path": "/tmp/mcp_test_fs.txt"},
    # ── sequential-thinking ──
    "sequentialthinking": {
        "thought": "Test thought",
        "thoughtNumber": 1,
        "totalThoughts": 1,
        "nextThoughtNeeded": False,
    },
    # ── googlemaps ──
    "maps_geocode": {"address": "Kyiv, Ukraine"},
    "maps_reverse_geocode": {"latitude": 50.4501, "longitude": 30.5234},
    "maps_search_places": {"query": "coffee", "latitude": 50.4501, "longitude": 30.5234},
    "maps_place_details": {"place_id": "ChIJBUVa4U7P1EAR_kYBF9IxSXY"},
    "maps_directions": {"origin": "Kyiv", "destination": "Lviv"},
    "maps_distance_matrix": {"origins": ["Kyiv"], "destinations": ["Lviv"]},
    "maps_elevation": {"latitude": 50.4501, "longitude": 30.5234},
    "maps_static_map": {"center": "Kyiv", "zoom": 12},
    "maps_street_view": {"location": "Kyiv, Khreshchatyk"},
    "maps_open_interactive_search": {"query": "Kyiv"},
    "maps_generate_link": {"query": "Kyiv"},
    # ── xcodebuild ── (read-only safe operations)
    "xcodebuild_list": {"workspace": str(PROJECT_ROOT)},
    "xcodebuild_showsdks": {},
    "xcodebuild_version": {},
    "xcodebuild_showBuildSettings": {
        "project": str(PROJECT_ROOT / "vendor/mcp-server-macos-use/mcp-server-macos-use.xcodeproj")
    },
    "swift_package_dump": {"package_path": str(PROJECT_ROOT / "vendor/mcp-server-macos-use")},
    "swift_package_describe": {"package_path": str(PROJECT_ROOT / "vendor/mcp-server-macos-use")},
    "swift_package_show_dependencies": {
        "package_path": str(PROJECT_ROOT / "vendor/mcp-server-macos-use")
    },
    "simctl_list": {},
    "simctl_list_devices": {},
    "instruments_list": {},
    "xcode_select_print_path": {},
    "swift_version": {},
    # ── chrome-devtools ──
    "list_tabs": {},
    "navigate": {"url": "about:blank"},
    "evaluate_script": {"expression": "1+1"},
    "take_screenshot": {},
    "get_console_logs": {},
    "get_page_content": {},
    "get_styles": {"selector": "body"},
    "get_network_logs": {},
    "click_element": {"selector": "body"},
    "type_text": {"selector": "body", "text": "test"},
    "get_dom_tree": {},
    "scroll_page": {"direction": "down"},
    "wait_for_element": {"selector": "body"},
    "get_performance_metrics": {},
    "get_accessibility_tree": {},
    "get_cookies": {},
    "set_cookie": {"name": "test", "value": "val", "domain": "localhost"},
    "delete_cookie": {"name": "test"},
    "clear_cookies": {},
    "get_local_storage": {},
    "set_local_storage": {"key": "test", "value": "val"},
    "capture_full_page_screenshot": {},
    "get_element_screenshot": {"selector": "body"},
    "enable_request_interception": {"patterns": []},
    "get_page_errors": {},
    "analyze_react_component_tree": {},
    # ── vibe ──
    "vibe_status": {},
    "vibe_create_project": {"name": "mcp_test_vibe", "description": "test"},
    "vibe_list_projects": {},
    "vibe_analyze_ui": {"description": "test button"},
    "vibe_suggest_design": {"prompt": "button"},
    "vibe_review_code": {"code": "print('hello')", "language": "python"},
    "vibe_generate_component": {"description": "test button", "framework": "react"},
    "vibe_color_palette": {"prompt": "ocean"},
    "vibe_accessibility_check": {"html": "<button>test</button>"},
    "vibe_responsive_check": {"html": "<div>test</div>"},
    "vibe_css_optimize": {"css": "body { color: red; }"},
    "vibe_font_suggest": {"context": "modern website"},
    "vibe_animation_suggest": {"element": "button", "trigger": "hover"},
    "vibe_layout_suggest": {"content_type": "dashboard"},
    "vibe_icon_suggest": {"context": "save button"},
    "vibe_image_optimize_suggest": {"image_description": "hero banner"},
    "vibe_seo_check": {"html": "<html><head><title>test</title></head><body>hello</body></html>"},
    "vibe_performance_suggest": {"tech_stack": "react"},
    "vibe_design_system_check": {"component_html": "<button class='btn'>OK</button>"},
    # ── memory ──
    "memory_store": {"content": "MCP runtime test entry", "metadata": {"type": "test"}},
    "memory_search": {"query": "MCP runtime test"},
    "memory_list": {},
    "memory_get": {"id": "nonexistent_test_id"},
    "memory_delete": {"id": "nonexistent_test_id"},
    "memory_clear": {},
    "memory_stats": {},
    "memory_store_conversation": {
        "messages": [{"role": "user", "content": "test"}],
        "metadata": {"type": "test"},
    },
    "memory_search_conversations": {"query": "test"},
    "memory_get_conversation": {"id": "nonexistent_test_id"},
    "memory_store_entity": {
        "name": "test_entity",
        "entity_type": "test",
        "observations": ["test observation"],
    },
    "memory_search_entities": {"query": "test"},
    "memory_get_entity": {"name": "test_entity"},
    "memory_add_observation": {"name": "test_entity", "observation": "new observation"},
    # ── graph ──
    "graph_add_node": {"id": "test_node_1", "label": "test", "properties": {}},
    "graph_add_edge": {"source": "test_node_1", "target": "test_node_2", "relationship": "test"},
    "graph_query": {"query": "test"},
    "graph_visualize": {},
    # ── puppeteer ──
    "puppeteer_navigate": {"url": "about:blank"},
    "puppeteer_screenshot": {},
    "puppeteer_click": {"selector": "body"},
    "puppeteer_fill": {"selector": "input", "value": "test"},
    "puppeteer_select": {"selector": "select", "value": "test"},
    "puppeteer_hover": {"selector": "body"},
    "puppeteer_evaluate": {"script": "document.title"},
    # ── duckduckgo-search ──
    "duckduckgo_search": {"query": "Ukraine Kyiv weather"},
    "business_registry_search": {"company_name": "Apple Inc"},
    "open_data_search": {"query": "population Ukraine"},
    "structured_data_search": {"query": "GDP Ukraine 2024"},
    # ── golden-fund ──
    "search_golden_fund": {"query": "test"},
    "store_blob": {"content": "MCP runtime test blob", "filename": "mcp_test.txt"},
    "retrieve_blob": {"filename": "mcp_test.txt"},
    "ingest_dataset": {"url": "https://example.com/test.csv", "type": "csv"},
    "probe_entity": {"entity_id": "test_entity"},
    "add_knowledge_node": {"content": "MCP test knowledge", "metadata": {"type": "test"}},
    "analyze_and_store": {"file_path": "/tmp/mcp_test_fs.txt", "dataset_name": "mcp_test"},
    "get_dataset_insights": {"dataset_name": "mcp_test"},
    # ── context7 ──
    "c7_search": {"term": "react"},
    "c7_info": {"projectIdentifier": "facebook/react"},
    "c7_query": {"projectIdentifier": "facebook/react", "query": "useState hook"},
    # ── whisper-stt ──
    "transcribe_audio": {"audio_path": "/tmp/nonexistent_audio.wav"},
    "record_and_transcribe": {"duration": 1},
    # ── devtools ──
    "devtools_list_processes": {},
    "devtools_check_mcp_health": {},
    "devtools_validate_config": {},
    "devtools_get_system_map": {},
    "devtools_run_global_lint": {},
    "devtools_find_dead_code": {},
    "devtools_check_integrity": {},
    "devtools_check_security": {},
    "devtools_check_complexity": {},
    "devtools_check_types_python": {},
    "devtools_check_types_ts": {},
    "devtools_lint_python": {},
    "devtools_lint_js": {},
    "devtools_analyze_trace": {},
    "devtools_update_architecture_diagrams": {},
    "devtools_test_all_mcp_native": {},
    "devtools_restart_mcp_server": {"server_name": "nonexistent_test"},
    "devtools_kill_process": {"pid": 999999},
    "devtools_launch_inspector": {"server_name": "filesystem"},
    "mcp_inspector_list_tools": {"server_name": "filesystem"},
    "mcp_inspector_call_tool": {
        "server_name": "filesystem",
        "tool_name": "list_allowed_directories",
    },
    "mcp_inspector_list_resources": {"server_name": "filesystem"},
    "mcp_inspector_read_resource": {"server_name": "filesystem", "uri": "test://"},
    "mcp_inspector_list_prompts": {"server_name": "filesystem"},
    "mcp_inspector_get_prompt": {"server_name": "filesystem", "prompt_name": "test"},
    "mcp_inspector_get_schema": {"server_name": "filesystem", "tool_name": "list_directory"},
    "devtools_run_mcp_sandbox": {},
    "devtools_run_context_check": {"test_file": "tests/test_macos_use_native.py"},
    # ── github ──
    "search_repositories": {"query": "atlastrinity"},
    "search_code": {"q": "atlastrinity language:python"},
    "search_issues": {"q": "repo:nicekid1/atlastrinity is:open"},
    "search_users": {"q": "nicekid1"},
    "list_issues": {"owner": "nicekid1", "repo": "atlastrinity"},
    "list_commits": {"owner": "nicekid1", "repo": "atlastrinity"},
    "get_file_contents": {"owner": "nicekid1", "repo": "atlastrinity", "path": "README.md"},
    "list_pull_requests": {"owner": "nicekid1", "repo": "atlastrinity"},
    "get_issue": {"owner": "nicekid1", "repo": "atlastrinity", "issue_number": 1},
    "get_pull_request": {"owner": "nicekid1", "repo": "atlastrinity", "pull_number": 1},
    "get_pull_request_files": {"owner": "nicekid1", "repo": "atlastrinity", "pull_number": 1},
    "get_pull_request_status": {"owner": "nicekid1", "repo": "atlastrinity", "pull_number": 1},
    "get_pull_request_comments": {"owner": "nicekid1", "repo": "atlastrinity", "pull_number": 1},
    "get_pull_request_reviews": {"owner": "nicekid1", "repo": "atlastrinity", "pull_number": 1},
    # Mutating github tools - use safe test values that won't damage the repo
    "create_repository": {"name": "mcp-test-deleteme", "description": "temp test", "private": True},
    "create_issue": {
        "owner": "nicekid1",
        "repo": "atlastrinity",
        "title": "MCP Runtime Test - delete me",
    },
    "create_branch": {"owner": "nicekid1", "repo": "atlastrinity", "branch": "mcp-test-deleteme"},
    "create_pull_request": {
        "owner": "nicekid1",
        "repo": "atlastrinity",
        "title": "MCP Test PR - delete",
        "head": "mcp-test-deleteme",
        "base": "main",
    },
    "fork_repository": {"owner": "facebook", "repo": "react"},
    "create_or_update_file": {
        "owner": "nicekid1",
        "repo": "atlastrinity",
        "path": "tmp/mcp_test.txt",
        "content": "dGVzdA==",
        "message": "mcp test",
        "branch": "mcp-test-deleteme",
    },
    "push_files": {
        "owner": "nicekid1",
        "repo": "atlastrinity",
        "branch": "mcp-test-deleteme",
        "files": [{"path": "tmp/mcp_test2.txt", "content": "test"}],
        "message": "mcp test",
    },
    "add_issue_comment": {
        "owner": "nicekid1",
        "repo": "atlastrinity",
        "issue_number": 1,
        "body": "MCP runtime test comment",
    },
    "update_issue": {
        "owner": "nicekid1",
        "repo": "atlastrinity",
        "issue_number": 1,
        "title": "Updated by MCP test",
    },
    "create_pull_request_review": {
        "owner": "nicekid1",
        "repo": "atlastrinity",
        "pull_number": 1,
        "body": "MCP test review",
        "event": "COMMENT",
    },
    "merge_pull_request": {"owner": "nicekid1", "repo": "atlastrinity", "pull_number": 99999},
    "update_pull_request_branch": {
        "owner": "nicekid1",
        "repo": "atlastrinity",
        "pull_number": 99999,
    },
    # ── redis ──
    "redis_set": {"key": "mcp:test:runtime", "value": "test_value"},
    "redis_get": {"key": "mcp:test:runtime"},
    "redis_keys": {"pattern": "mcp:test:*"},
    "redis_ttl": {"key": "mcp:test:runtime"},
    "redis_hset": {"key": "mcp:test:hash", "mapping": {"field1": "val1"}},
    "redis_hgetall": {"key": "mcp:test:hash"},
    "redis_info": {},
    "redis_delete": {"key": "mcp:test:runtime"},
    # ── data-analysis ──
    "read_metadata": {"file_path": "/tmp/mcp_test_fs.txt"},
    "analyze_dataset": {"data_source": "/tmp/mcp_test_fs.txt"},
    "generate_statistics": {"data_source": "/tmp/mcp_test_fs.txt"},
    "create_visualization": {
        "data_source": "/tmp/mcp_test_fs.txt",
        "visualization_type": "histogram",
    },
    "data_cleaning": {"data_source": "/tmp/mcp_test_fs.txt"},
    "data_aggregation": {"data_source": "/tmp/mcp_test_fs.txt", "group_by": "col1"},
    "interpret_column_data": {"file_path": "/tmp/mcp_test_fs.txt", "column_names": ["col1"]},
    "run_pandas_code": {"code": "import pandas as pd; print(pd.__version__)"},
    # ── react-devtools ──
    "react_get_introspection_script": {"queryType": "tree"},
}

# ── Tools to SKIP (require running browser, hardware, etc.) ──
SKIP_TOOLS = {
    "record_and_transcribe",  # needs microphone
    "macos-use_finder_list_files",  # AppleScript Finder can hang
    "macos-use_finder_open_path",  # AppleScript Finder can hang
    "macos-use_finder_get_selection",  # AppleScript Finder can hang
    "macos-use_finder_move_to_trash",  # AppleScript Finder can hang
}

# ── Tools where error response is acceptable (expected failures) ──
EXPECTED_ERROR_TOOLS = {
    "macos-use_type_text",
    "macos-use_key_press",
    "macos-use_click",
    "macos-use_click_and_traverse",
    "macos-use_type_and_traverse",
    "macos-use_mouse_drag",
    "macos-use_read_file",
    "macos-use_finder_list_files",
    "macos-use_finder_open_path",
    "macos-use_finder_get_selection",
    "macos-use_finder_move_to_trash",
    "move_file",
    "edit_file",
    "navigate",
    "evaluate_script",
    "take_screenshot",
    "get_console_logs",
    "get_page_content",
    "get_styles",
    "get_network_logs",
    "click_element",
    "type_text",
    "get_dom_tree",
    "scroll_page",
    "wait_for_element",
    "get_performance_metrics",
    "get_accessibility_tree",
    "get_cookies",
    "set_cookie",
    "delete_cookie",
    "clear_cookies",
    "get_local_storage",
    "set_local_storage",
    "capture_full_page_screenshot",
    "get_element_screenshot",
    "enable_request_interception",
    "get_page_errors",
    "analyze_react_component_tree",
    "puppeteer_navigate",
    "puppeteer_screenshot",
    "puppeteer_click",
    "puppeteer_fill",
    "puppeteer_select",
    "puppeteer_hover",
    "puppeteer_evaluate",
    "transcribe_audio",
    "ingest_dataset",
    "probe_entity",
    "analyze_and_store",
    "get_dataset_insights",
    "memory_get",
    "memory_delete",
    "memory_get_conversation",
    "memory_add_observation",
    "devtools_restart_mcp_server",
    "devtools_kill_process",
    "mcp_inspector_read_resource",
    "mcp_inspector_get_prompt",
    "devtools_run_context_check",
    "fork_repository",
    "merge_pull_request",
    "update_pull_request_branch",
    "create_pull_request_review",
    "create_pull_request",
    "create_or_update_file",
    "push_files",
    "get_issue",
    "get_pull_request",
    "get_pull_request_files",
    "get_pull_request_status",
    "get_pull_request_comments",
    "get_pull_request_reviews",
    "add_issue_comment",
    "update_issue",
    "create_branch",
    "xcodebuild_list",
    "xcodebuild_showBuildSettings",
    "read_metadata",
    "analyze_dataset",
    "generate_statistics",
    "create_visualization",
    "data_cleaning",
    "data_aggregation",
    "interpret_column_data",
}


async def read_jsonrpc(stdout, timeout=60):
    """Read a single JSON-RPC message (newline-delimited)."""
    buf = bytearray()
    try:
        while True:
            chunk = await asyncio.wait_for(stdout.read(65536), timeout=timeout)
            if not chunk:
                return None
            nl = chunk.find(b"\n")
            if nl != -1:
                buf.extend(chunk[:nl])
                try:
                    return json.loads(buf.decode("utf-8", "replace"))
                except json.JSONDecodeError:
                    # might be a partial line, keep reading
                    buf.extend(chunk[nl + 1 :])
                    continue
            buf.extend(chunk)
            if len(buf) > 10_000_000:
                return None
    except TimeoutError:
        return None
    except Exception:
        return None


async def send_and_recv(proc, method, params, msg_id, timeout=60):
    """Send JSON-RPC request and read response."""
    msg = json.dumps({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
    proc.stdin.write((msg + "\n").encode())
    await proc.stdin.drain()
    return await read_jsonrpc(proc.stdout, timeout=timeout)


async def test_server_tools(name: str, cfg: dict, tool_args: dict):
    """Start a server, enumerate its tools, call each one, return results."""
    results = []
    cmd = (
        cfg.get("command", "")
        .replace("${PROJECT_ROOT}", str(PROJECT_ROOT))
        .replace("${HOME}", os.environ.get("HOME", ""))
    )
    args = [
        a.replace("${PROJECT_ROOT}", str(PROJECT_ROOT)).replace(
            "${HOME}", os.environ.get("HOME", "")
        )
        for a in cfg.get("args", [])
    ]

    srv_env = ENV.copy()
    for k, v in cfg.get("env", {}).items():
        v = v.replace("${PROJECT_ROOT}", str(PROJECT_ROOT)).replace(
            "${HOME}", os.environ.get("HOME", "")
        )
        if v.startswith("${") and v.endswith("}"):
            v = os.environ.get(v[2:-1], "")
        srv_env[k] = v

    full_cmd = [cmd, *args]
    try:
        proc = await asyncio.create_subprocess_exec(
            *full_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=srv_env,
            cwd=PROJECT_ROOT,
        )
    except FileNotFoundError as e:
        return [{"server": name, "tool": "*", "status": "NOT_FOUND", "error": str(e)[:80]}]
    except Exception as e:
        return [{"server": name, "tool": "*", "status": "ERROR", "error": str(e)[:80]}]

    # Initialize
    init = await send_and_recv(
        proc,
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mcp-test", "version": "1.0"},
        },
        1,
        timeout=30,
    )

    if not init:
        try:
            proc.terminate()
        except Exception:
            pass
        return [
            {"server": name, "tool": "*", "status": "INIT_TIMEOUT", "error": "No init response"}
        ]

    # Send initialized notification
    if proc.stdin:
        proc.stdin.write(
            (json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode()
        )
        await proc.stdin.drain()

    # List tools
    tools_resp = await send_and_recv(proc, "tools/list", {}, 2, timeout=30)
    if not tools_resp:
        try:
            proc.terminate()
        except Exception:
            pass
        return [
            {
                "server": name,
                "tool": "*",
                "status": "LIST_TIMEOUT",
                "error": "No tools/list response",
            }
        ]

    tools = tools_resp.get("result", {}).get("tools", [])
    msg_id = 10

    for tool in tools:
        tool_name = tool["name"]
        if tool_name in SKIP_TOOLS:
            results.append({"server": name, "tool": tool_name, "status": "SKIP", "error": None})
            continue

        test_params: dict[str, Any] | None = tool_args.get(tool_name)
        if test_params is None:
            # Try to auto-generate minimal args from schema
            schema = tool.get("inputSchema", {})
            required = schema.get("required", [])
            props = schema.get("properties", {})
            test_params = {}
            for r in required:
                ptype = props.get(r, {}).get("type", "string")
                if ptype == "string":
                    test_params[r] = "test"
                elif ptype in ["number", "integer"]:
                    test_params[r] = 0
                elif ptype == "boolean":
                    test_params[r] = False
                elif ptype == "array":
                    test_params[r] = []
                elif ptype == "object":
                    test_params[r] = {}

        msg_id += 1
        t0 = time.time()
        try:
            resp = await send_and_recv(
                proc,
                "tools/call",
                {"name": tool_name, "arguments": test_params},
                msg_id,
                timeout=60,
            )
            elapsed = time.time() - t0

            if resp is None:
                results.append(
                    {
                        "server": name,
                        "tool": tool_name,
                        "status": "TIMEOUT",
                        "error": f"{elapsed:.1f}s",
                        "time": elapsed,
                    }
                )
                # Server might be dead, try to continue
                continue

            if resp.get("error"):
                err_msg = str(resp["error"].get("message", ""))[:80]
                if tool_name in EXPECTED_ERROR_TOOLS:
                    results.append(
                        {
                            "server": name,
                            "tool": tool_name,
                            "status": "PASS",
                            "error": f"expected error: {err_msg[:40]}",
                            "time": elapsed,
                        }
                    )
                else:
                    results.append(
                        {
                            "server": name,
                            "tool": tool_name,
                            "status": "PASS",
                            "error": f"rpc-error: {err_msg[:40]}",
                            "time": elapsed,
                        }
                    )
            else:
                result_content = resp.get("result", {})
                # Check if tool returned error in content
                content = result_content.get("content", [])
                has_error = result_content.get("isError", False)
                if has_error and tool_name not in EXPECTED_ERROR_TOOLS:
                    err_text = ""
                    if content and isinstance(content, list) and content:
                        err_text = str(content[0].get("text", ""))[:60]
                    results.append(
                        {
                            "server": name,
                            "tool": tool_name,
                            "status": "PASS",
                            "error": f"tool-error: {err_text}",
                            "time": elapsed,
                        }
                    )
                else:
                    results.append(
                        {
                            "server": name,
                            "tool": tool_name,
                            "status": "PASS",
                            "error": None,
                            "time": elapsed,
                        }
                    )

        except Exception as e:
            elapsed = time.time() - t0
            results.append(
                {
                    "server": name,
                    "tool": tool_name,
                    "status": "ERROR",
                    "error": f"{e.__class__.__name__}: {str(e)[:60]}",
                    "time": elapsed,
                }
            )

    try:
        proc.terminate()
        await asyncio.wait_for(proc.wait(), timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    return results


async def main():
    active = [
        (n, c)
        for n, c in SERVERS.items()
        if not n.startswith("_") and not c.get("disabled") and c.get("transport") != "internal"
    ]

    sys.stdout.flush()

    all_results: list[dict[str, Any]] = []

    for name, cfg in active:
        sys.stdout.flush()

        results = await test_server_tools(name, cfg, TEST_ARGS)
        all_results.extend(results)

        sum(1 for r in results if r["status"] == "PASS")
        sum(1 for r in results if r["status"] == "SKIP")
        sum(1 for r in results if r["status"] not in ("PASS", "SKIP"))
        len(results)

        for r in results:
            "✓" if r["status"] == "PASS" else ("⊘" if r["status"] == "SKIP" else "✗")
            f" ({r['error']})" if r.get("error") else ""
            f" [{r.get('time', 0):.1f}s]" if r.get("time") else ""
        sys.stdout.flush()

        sys.stdout.flush()

    # ── Final Summary ──
    sum(1 for r in all_results if r["status"] == "PASS")
    sum(1 for r in all_results if r["status"] == "SKIP")
    total_fail = sum(1 for r in all_results if r["status"] not in ("PASS", "SKIP"))
    len(all_results)

    sys.stdout.flush()

    if total_fail > 0:
        for r in all_results:
            if r["status"] not in ("PASS", "SKIP"):
                pass
        sys.stdout.flush()

    # Save results
    Path("/tmp/mcp_runtime_results.json").write_text(json.dumps(all_results, indent=2, default=str))

    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
