import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from src.brain.config import CONFIG_ROOT, PROJECT_ROOT
from src.brain.config.config_loader import config
from src.brain.core.services.state_manager import state_manager
from src.brain.mcp.mcp_registry import (
    SERVER_CATALOG,
    TOOL_SCHEMAS,
    get_server_for_tool,
    get_tool_schema,
)
from src.brain.monitoring.logger import logger


class ToolDispatcher:
    """Centralized dispatcher for MCP tools.
    Unifies tool name resolution, synonym mapping, and argument normalization.
    """

    # --- SYNONYMS & INTENT MAPPINGS ---
    TERMINAL_SYNONYMS = [
        "terminal",
        "bash",
        "zsh",
        "sh",
        "python",
        "python3",
        "pip",
        "pip3",
        "cmd",
        "run",
        "execute",
        "execute_command",
        "terminal_execute",
        "execute_terminal",
        "terminal.execute",
        "osascript",
        "applescript",
        "curl",
        "wget",
        "jq",
        "grep",
        "git",
        "npm",
        "npx",
        "brew",
        "mkdir",
        "ls",
        "cat",
        "rm",
        "mv",
        "cp",
        "touch",
        "sudo",
    ]

    FILESYSTEM_SYNONYMS = [
        "filesystem",
        "fs",
        "file",
        "files",
        "editor",
        "directory_tree",
        "list_directory",
        "read_file",
        "write_file",
        "tree",
    ]

    SERACH_SYNONYMS: list[str] = []  # Deprecated

    VIBE_SYNONYMS = [
        "vibe",
        "vibe_prompt",
        "vibe_ask",
        "vibe_analyze_error",
        "vibe_smart_plan",
        "vibe_code_review",
        "vibe_implement_feature",
        "vibe_execute_subcommand",
        "vibe_list_sessions",
        "vibe_session_details",
        "vibe_which",
        "vibe_get_config",
        "vibe_configure_model",
        "vibe_set_mode",
        "vibe_configure_provider",
        "vibe_session_resume",
        "vibe_reload_config",
        "vibe_check_db",
        "vibe_get_system_context",
        "vibe_test_in_sandbox",
        "debug",
        "fix",
        "implement",
        "feature",
        "review",
        "plan",
        "ask",
        "question",
        "config",
        "model",
        "provider",
        "resume",
        "reload",
        "mode",
    ]

    BROWSER_SYNONYMS = [
        "browser",
        "puppeteer",
        "navigate",
        "google",
        "bing",
        "web",
        "web_search",
        "internet_search",
        "online_search",
    ]

    DUCKDUCKGO_SYNONYMS = [
        "duckduckgo",
        "ddg",
        "duckduckgo-search",
        "duckduckgo_search",
        "search_web",
        "web_search",
    ]

    KNOWLEDGE_SYNONYMS = [
        "memory",
        "knowledge",
        "entity",
        "entities",
        "observation",
        "observations",
        "fact",
        "recall",
        "remember",
        "store_fact",
        "add_memory",
        "relationship",
        "relation",
    ]

    GRAPH_SYNONYMS = [
        "graph",
        "visualization",
        "diagram",
        "mermaid",
        "flowchart",
        "nodes",
        "edges",
        "node_details",
        "related_nodes",
        "traverse",
    ]

    REDIS_SYNONYMS = [
        "redis",
        "cache",
        "state_inspection",
        "session_storage",
        "flags",
        "retry_pending",
        "restart_pending",
    ]

    DEVTOOLS_SYNONYMS = [
        "devtools",
        "lint",
        "linter",
        "check",
        "inspect",
        "inspector",
        "validate",
        "health",
        "ruff",
        "oxlint",
        "knip",
        "pyrefly",
        "pyrefly",
        "devtools_run_global_lint",
        "ci",
        "cicd",
        "github_actions",
        "workflow",
        "job",
        "logs",
    ]

    WINDSURF_SYNONYMS = [
        "windsurf",
        "winserf",
        "cascade",
        "action_phase",
        "chat",
        "windsurf_chat",
        "windsurf_cascade",
        "windsurf_status",
    ]

    CONTEXT7_SYNONYMS = [
        "context7",
        "c7",
        "docs",
        "documentation",
        "library",
        "library_search",
        "api_docs",
        "lookup",
        "c7_search",
        "c7_query",
        "c7_info",
        "c7_list_libraries",
        "c7_get_context",
    ]

    GOLDEN_FUND_SYNONYMS = [
        "golden_fund",
        "goldenfund",
        "gold_fund",
        "goldfund",
        "gf",
        "ingest",
        "ingestion",
        "probe",
        "probe_entity",
        "vector_search",
        "semantic_search",
        "knowledge_base",
        "kb",
        "analyze_and_store",
        "get_dataset_insights",
        "dataset_insights",
        "store_analysis",
        "persist_analysis",
    ]

    GITHUB_SYNONYMS = [
        "github",
        "repo",
        "repository",
        "pull_request",
        "pr",
        "issue",
        "issues",
        "gh",
        "git_hub",
    ]

    DATA_ANALYSIS_SYNONYMS = [
        "data_analysis",
        "data-analysis",
        "analyze_data",
        "analyze-data",
        "data_analyze",
        "data-analyze",
        "statistics",
        "statistical_analysis",
        "data_processing",
        "data-processing",
        "data_visualization",
        "data-visualization",
        "data_cleaning",
        "data-cleaning",
        "data_transformation",
        "data-transformation",
        "machine_learning",
        "machine-learning",
        "predictive_modeling",
        "predictive-modeling",
        "data_aggregation",
        "data-aggregation",
        "data_reporting",
        "data-reporting",
        "analyze_dataset",
        "analyze-dataset",
        "generate_statistics",
        "generate-statistics",
        "create_visualization",
        "create-visualization",
        "read_metadata",
        "interpret_column_data",
        "run_pandas_code",
        "pandas",
        "csv_analysis",
        "excel_analysis",
    ]

    XCODEBUILD_SYNONYMS = [
        "xcodebuild",
        "xcode",
        "ios_development",
        "ios-development",
        "macos_development",
        "macos-development",
        "build_project",
        "build-project",
        "run_tests",
        "simulator",
        "simulators",
        "simctl",
        "xcodeproj",
        "xcworkspace",
        "testflight",
        "app_store",
        "build_project",
        "run_tests",
        "list_simulators",
        "boot_simulator",
        "install_app",
        "launch_app",
        "analyze_logs",
        "get_coverage",
        "archive_project",
        "clean_build",
    ]

    MAPS_SYNONYMS = [
        "maps",
        "location",
        "directions",
        "route",
        "traffic",
        "streetview",
        "street_view",
        "static_map",
        "geocode",
        "elevation",
        "place",
        "places",
        "atlas_maps",
        "cyberpunk_maps",
    ]

    MACOS_MAP = {
        "click": "macos-use_click_and_traverse",
        "type": "macos-use_type_and_traverse",
        "write": "macos-use_type_and_traverse",
        "press": "macos-use_press_key_and_traverse",
        "hotkey": "macos-use_press_key_and_traverse",
        "refresh": "macos-use_refresh_traversal",
        "screenshot": "macos-use_take_screenshot",
        "vision": "macos-use_analyze_screen",
        "ocr": "macos-use_analyze_screen",
        "open": "macos-use_open_app",
        "launch": "macos-use_open_app",
        "scroll": "macos-use_scroll_and_traverse",
        "fetch": "macos-use_fetch_url",
        "fetch_url": "macos-use_fetch_url",
        "time": "macos-use_get_time",
        "get_time": "macos-use_get_time",
        "notification": "macos-use_send_notification",
        "run_applescript": "macos-use_run_applescript",
        "applescript": "macos-use_run_applescript",
        "spotlight": "macos-use_spotlight_search",
        "spotlight_search": "macos-use_spotlight_search",
        "clipboard_set": "macos-use_set_clipboard",
        "set_clipboard": "macos-use_set_clipboard",
        "clipboard_get": "macos-use_get_clipboard",
        "get_clipboard": "macos-use_get_clipboard",
        # Direct mappings for behavior engine
        "macos-use_get_clipboard": "macos-use_get_clipboard",
        "macos-use_set_clipboard": "macos-use_set_clipboard",
        "macos-use_analyze_screen": "macos-use_analyze_screen",
        # Screenshot tools
        "take_screenshot": "macos-use_take_screenshot",
        # Browser automation
        "launch_browser": "puppeteer_navigate",
        "open_browser": "puppeteer_navigate",
        "browser_navigate": "puppeteer_navigate",
        "navigate": "puppeteer_navigate",
        # Vision/OCR tools
        "analyze_screen": "macos-use_analyze_screen",
        # System monitoring tools
        "list_running_apps": "macos-use_list_running_apps",
        "running_apps": "macos-use_list_running_apps",
        "list_apps": "macos-use_list_running_apps",
        "list_browser_tabs": "macos-use_list_browser_tabs",
        "browser_tabs": "macos-use_list_browser_tabs",
        "tabs": "macos-use_list_browser_tabs",
        "list_windows": "macos-use_list_all_windows",
        "all_windows": "macos-use_list_all_windows",
        "windows": "macos-use_list_all_windows",
        # Notes tools
        "create_note": "macos-use_notes_create_note",
        "notes_create": "macos-use_notes_create_note",
        "list_notes": "macos-use_notes_list_folders",
        "notes_list": "macos-use_notes_list_folders",
        "get_note": "macos-use_notes_get_content",
        "read_note": "macos-use_notes_get_content",
        "search_notes": "macos-use_notes_get_content",
        "notes_get": "macos-use_notes_get_content",
        # Finder tools
        "finder_open": "macos-use_finder_open_path",
        "open_path": "macos-use_finder_open_path",
        "list_files": "macos-use_finder_list_files",
        "finder_list": "macos-use_finder_list_files",
        "finder_selection": "macos-use_finder_get_selection",
        "get_selection": "macos-use_finder_get_selection",
        "trash": "macos-use_finder_move_to_trash",
        "move_to_trash": "macos-use_finder_move_to_trash",
        # Calendar/Reminders
        "calendar_events": "macos-use_calendar_events",
        "create_event": "macos-use_create_event",
        "reminders": "macos-use_reminders",
        "create_reminder": "macos-use_create_reminder",
        # Mail
        "send_mail": "macos-use_mail_send",
        "mail_send": "macos-use_mail_send",
        "read_inbox": "macos-use_mail_read_inbox",
        "mail_read": "macos-use_mail_read_inbox",
        # Media/System
        "system_control": "macos-use_system_control",
        "media": "macos-use_system_control",
        # Explicit Terminal support within macos-use routing
        "terminal": "execute_command",
        "execute_command": "execute_command",
        "shell": "execute_command",
        "bash": "execute_command",
        "zsh": "execute_command",
        "sh": "execute_command",
        "ls": "macos-use_finder_list_files",
        "cd": "execute_command",
        "pwd": "execute_command",
        "echo": "execute_command",
        "cat": "execute_command",
        "grep": "execute_command",
        "curl": "macos-use_fetch_url",
        "wget": "macos-use_fetch_url",
        "date": "macos-use_get_time",
        "notify": "macos-use_send_notification",
        "alert": "macos-use_send_notification",
        "find": "macos-use_spotlight_search",
        "mdfind": "macos-use_spotlight_search",
        "right_click": "macos-use_right_click_and_traverse",
        "double_click": "macos-use_double_click_and_traverse",
        "drag": "macos-use_drag_and_drop_and_traverse",
        "drop": "macos-use_drag_and_drop_and_traverse",
        "drag_and_drop": "macos-use_drag_and_drop_and_traverse",
        # Windsurf
        "windsurf": "windsurf_cascade",
        "winserf": "windsurf_cascade",
        "cascade": "windsurf_cascade",
        "action_phase": "windsurf_cascade",
        # Discovery
        "list_tools": "macos-use_list_tools_dynamic",
        "discovery": "macos-use_list_tools_dynamic",
        # Generic FS mapping for macos-use
        "list_directory": "macos-use_finder_list_files",
        # New Tools (Expansion to 60+)
        "frontmost_app": "macos-use_get_frontmost_app",
        "active_app": "macos-use_get_frontmost_app",
        "battery": "macos-use_get_battery_info",
        "power": "macos-use_get_battery_info",
        "wifi": "macos-use_get_wifi_details",
        "set_volume": "macos-use_set_system_volume",
        "volume": "macos-use_set_system_volume",
        "set_brightness": "macos-use_set_screen_brightness",
        "brightness": "macos-use_set_screen_brightness",
        "empty_trash": "macos-use_empty_trash",
        "window_info": "macos-use_get_active_window_info",
        "active_window": "macos-use_get_active_window_info",
        "close_window": "macos-use_close_window",
        "move_window": "macos-use_move_window",
        "resize_window": "macos-use_resize_window",
        "network_interfaces": "macos-use_list_network_interfaces",
        "interfaces": "macos-use_list_network_interfaces",
        "ip_address": "macos-use_get_ip_address",
        "my_ip": "macos-use_get_ip_address",
        "permissions": "macos-use_request_permissions",
        "setup_permissions": "macos-use_request_permissions",
        "fix_permissions": "macos-use_request_permissions",
        # Google Maps (Bridged)
        "geocode": "maps_geocode",
        "reverse_geocode": "maps_reverse_geocode",
        "search_places": "maps_search_places",
        "place_details": "maps_place_details",
        "directions": "maps_directions",
        "distance_matrix": "maps_distance_matrix",
        "street_view": "maps_street_view",
        "static_map": "maps_static_map",
        "elevation": "maps_elevation",
        "open_interactive_search": "maps_open_interactive_search",
        "generate_link": "maps_generate_link",
        "start_tour": "maps_start_tour",
        "tour_control": "maps_tour_control",
    }

    MACOS_USE_PRIORITY = {
        "bash",
        "zsh",
        "sh",
        "execute",
        "run",
        "cmd",
        "command",
        "git",
        "npm",
        "npx",
        "pip",
        "brew",
        "curl",
        "wget",
        "time",
        "clock",
        "date",
        "fetch",
        "url",
        "scrape",
        "volume",
        "brightness",
        "mute",
        "play",
        "pause",
        "calendar",
        "event",
        "reminder",
        "note",
        "mail",
        "email",
        "finder",
        "trash",
        "spotlight",
        "applescript",
        "osascript",
    }

    def __init__(self, mcp_manager) -> None:
        self.mcp_manager = mcp_manager
        self._tasks: set[asyncio.Task] = set()  # To prevent GC of long-running tasks
        self._current_pid: int | None = None
        self._total_calls = 0
        self._macos_use_calls = 0

    def set_pid(self, pid: int | None):
        """Update the currently tracked PID for macOS automation."""
        self._current_pid = pid

    # Common hallucinated tool names that LLMs generate but don't exist
    HALLUCINATED_TOOLS = {
        "create_spreadsheet": "No 'create_spreadsheet' tool exists. Use data-analysis server tools like run_pandas_code to generate CSV/Excel files, or use filesystem.write_file to write CSV content directly.",
        "spreadsheet": "No 'spreadsheet' server exists. Use data-analysis server for data processing or filesystem for writing CSV files.",
        "spreadsheet.create_spreadsheet": "No 'spreadsheet' server exists. Use data-analysis server tools like run_pandas_code to generate CSV/Excel files, or use filesystem.write_file.",
        "evaluate": "No 'evaluate' tool exists. Use vibe_code_review for code evaluation or execute_command for running tests.",
        "assess": "No 'assess' tool exists. Use vibe_code_review for assessment.",
        "verify": "No 'verify' tool exists. Use execute_command to run verification commands.",
        "validate": "No 'validate' tool exists. Use execute_command to run validation scripts.",
        "check": "No 'check' tool exists. Use execute_command for running check commands.",
        "test": "No 'test' tool exists. Use execute_command('npm test') or similar.",
        "compile": "No 'compile' tool exists. Use execute_command with appropriate build command.",
        "build": "No 'build' tool exists. Use execute_command('npm run build') or similar.",
        "deploy": "No 'deploy' tool exists. Use execute_command with deployment scripts.",
        "run": "Use execute_command for running arbitrary commands.",
    }

    async def resolve_and_dispatch(
        self,
        tool_name: str | None,
        args: dict[str, Any],
        explicit_server: str | None = None,
    ) -> dict[str, Any]:
        """The main entry point for dispatching a tool call.
        Resolves the tool name, normalizes arguments, and executes the call via MCPManager.
        """
        try:
            # 1. Basic cleaning and normalization
            tool_name = (tool_name or "").strip().lower()
            if not tool_name or tool_name == "none":
                logger.error(f"[DISPATCHER] Empty or 'none' tool call detected. Args: {args}")
                return {
                    "success": False,
                    "error": "Empty tool name or 'none' provided in tool call. Please specify a valid tool from the catalog.",
                    "invalid_tool": True,
                }
            if not isinstance(args, dict):
                args = {}

            # 2. Check for known hallucinated tools
            if tool_name in self.HALLUCINATED_TOOLS:
                suggestion = self.HALLUCINATED_TOOLS[tool_name]
                logger.warning(
                    f"[DISPATCHER] Hallucinated tool detected: '{tool_name}'. {suggestion}"
                )
                return {
                    "success": False,
                    "error": f"Tool '{tool_name}' does not exist. {suggestion}",
                    "hallucinated": True,
                }

            # 3. Resolve tool name and server
            server, resolved_tool, normalized_args = self._resolve_routing(
                tool_name, args, explicit_server
            )

            # 4. Handle internal system tools
            if server in {"_trinity_native", "system"}:
                return await self._handle_system(resolved_tool, normalized_args)

            # Handle Tour Guide tools (internal execution)
            if server == "tour-guide":
                return await self._execute_tour(resolved_tool, normalized_args)

            if not server:
                return self._handle_resolution_failure(tool_name)

            # 4b. Post-routing hallucination check (catches dot-notation like "spreadsheet.tool")
            if server in self.HALLUCINATED_TOOLS:
                suggestion = self.HALLUCINATED_TOOLS[server]
                logger.warning(
                    f"[DISPATCHER] Hallucinated server detected: '{server}'. {suggestion}"
                )
                return {
                    "success": False,
                    "error": f"Server '{server}' does not exist. {suggestion}",
                    "hallucinated": True,
                }

            # 5. Validate compatibility and arguments
            validation_result = self._pre_dispatch_validation(
                server, resolved_tool, normalized_args
            )
            if validation_result:
                return validation_result

            # 6. Apply command wrapping (CWD handling)
            self._wrap_commands(server, resolved_tool, normalized_args)

            # 7. Final validation and dispatch
            validated_args = self._validate_args(resolved_tool, normalized_args)
            if validated_args.get("__validation_error__"):
                return self._handle_validation_error(
                    server, resolved_tool, normalized_args, validated_args
                )

            return await self._dispatch_to_mcp(server, resolved_tool, validated_args)

        except Exception as e:
            logger.error(f"[DISPATCHER] Dispatch failed for tool '{tool_name}': {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "exception_type": type(e).__name__,
                "tool_name": tool_name,
                "args_keys": list(args.keys()) if isinstance(args, dict) else [],
            }

    def _resolve_routing(
        self, tool_name: str, args: dict[str, Any], explicit_server: str | None
    ) -> tuple[str | None, str, dict[str, Any]]:
        """Resolve the server and canonical tool name."""
        if not tool_name:
            tool_name = self._infer_tool_from_args(args)

        # Handle Dot Notation
        if "." in tool_name:
            parts = tool_name.split(".", 1)
            explicit_server = parts[0]
            tool_name = parts[1]
        else:
            explicit_server = self._normalize_server_prefix(tool_name, explicit_server)
            if explicit_server:
                for p in [f"{explicit_server}_", f"{explicit_server.replace('-', '_')}_"]:
                    if tool_name.startswith(p):
                        tool_name = tool_name[len(p) :]
                        break

        if explicit_server:
            return self._resolve_tool_and_args(tool_name, args, explicit_server)

        return self._intelligent_routing(tool_name, args)

    def _normalize_server_prefix(self, tool_name: str, explicit_server: str | None) -> str | None:
        """Heuristically normalize server prefix in tool name."""
        from src.brain.mcp.mcp_registry import SERVER_CATALOG, TOOL_SCHEMAS

        if explicit_server or tool_name in TOOL_SCHEMAS:
            return explicit_server

        sorted_servers = sorted(SERVER_CATALOG.keys(), key=len, reverse=True)
        for s_name in sorted_servers:
            prefixes = [f"{s_name}_", f"{s_name.replace('-', '_')}_"]
            if any(tool_name.startswith(p) for p in prefixes):
                return s_name
        return None

    def _handle_resolution_failure(self, tool_name: str) -> dict[str, Any]:
        """Provide suggestions for unknown tools."""
        from src.brain.mcp.mcp_registry import get_all_tool_names

        all_tools = get_all_tool_names()
        similar = [t for t in all_tools if tool_name in t.lower() or t.lower() in tool_name][:5]
        suggestion = f" Did you mean: {', '.join(similar)}" if similar else ""
        logger.warning(f"[DISPATCHER] Unknown tool: '{tool_name}'.{suggestion}")
        return {
            "success": False,
            "error": f"Could not resolve server for tool: '{tool_name}'.{suggestion}",
            "unknown_tool": True,
        }

    def _pre_dispatch_validation(
        self, server: str, tool: str, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Validate realm-tool compatibility."""
        is_comp, err = self._validate_realm_tool_compatibility(server, tool, args)
        if not is_comp:
            # Downgrade to debug: tools execute regardless, WARNING floods logs
            logger.debug(f"[DISPATCHER] Compatibility note: {server}.{tool} - {err}")
            # Don't block execution — just log for diagnostics
        return None

    def _wrap_commands(self, server: str, tool: str, args: dict[str, Any]) -> None:
        """Central command wrapping for terminal tools."""
        if server == "xcodebuild" and tool == "execute_command":
            cmd = args.get("command") or args.get("cmd")
            cwd = args.get("cwd") or args.get("path")
            if cwd and cmd and str(cmd).strip() and not str(cmd).startswith("cd "):
                args["command"] = f"cd {cwd} && {cmd}"

    def _handle_validation_error(
        self, server: str, tool: str, args: dict[str, Any], validated: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle argument validation failures."""
        error_msg = validated.pop("__validation_error__")
        logger.error(f"[DISPATCHER] Validation failed for {server}.{tool}: {error_msg}")
        return {
            "success": False,
            "error": f"Invalid arguments for '{tool}': {error_msg}",
            "validation_error": True,
            "server": server,
            "tool": tool,
            "provided_args": list(args.keys()),
        }

    async def _dispatch_to_mcp(
        self, server: str, tool: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        """Final metrics tracking and MCP call."""
        self._total_calls += 1
        if server == "xcodebuild":
            self._macos_use_calls += 1

        logger.info(f"[DISPATCHER] Calling {server}.{tool}")
        try:
            result = await self.mcp_manager.call_tool(server, tool, args)
            return self._process_mcp_result(server, tool, args, result)
        except Exception as e:
            logger.error(f"[DISPATCHER] MCP call failed: {e}")
            return {
                "success": False,
                "error": f"MCP call failed: {e!s}",
                "server": server,
                "tool": tool,
            }

    def _process_mcp_result(
        self, server: str, tool: str, args: dict[str, Any], result: Any
    ) -> dict[str, Any]:
        """Analyze result from MCP and add metadata if needed.
        STABILIZATION: Converts SDK objects to dicts to prevent 'not subscriptable' errors.
        """
        # Visual Hook: Update map state if result contains location data
        self._post_process_map_data(tool, result)

        # Convert CallToolResult (SDK object) to dict if it's not already
        if not isinstance(result, dict):
            # Attempt to convert SDK object to a dictionary
            # Typical SDK result has 'content', 'isError', 'meta'
            processed = {
                "success": not getattr(result, "is_error", getattr(result, "isError", False)),
                "result": getattr(result, "content", str(result)),
                "error": getattr(result, "error", None),
                "server": server,
                "tool": tool,
            }
            # Many agents expect 'content' explicitly (like Tetyana)
            if hasattr(result, "content"):
                processed["content"] = result.content

            result = processed

        error_msg = str(result.get("error") or "")
        if "not found" in error_msg.lower() or "-32602" in error_msg:
            result["tool_not_found"] = True
            result["suggestion"] = f"Tool '{tool}' may not exist on server '{server}'."
        elif "bad request" in error_msg.lower() or "400" in error_msg:
            result["bad_request"] = True

        result["server"] = server
        result["tool"] = tool
        return result

    def _post_process_map_data(self, tool_name: str, result: Any) -> None:
        """Post-process tool result for visual display."""
        try:
            from src.brain.navigation.map_state import map_state_manager

            # Check if result contains location data
            if tool_name.startswith("maps_") and isinstance(result, dict):
                # Distance Matrix results
                if tool_name == "maps_distance_matrix" and "rows" in result:
                    for row in result.get("rows", []):
                        for element in row.get("elements", []):
                            distance = element.get("distance", {}).get("text")
                            duration = element.get("duration", {}).get("text")
                            if distance or duration:
                                # Notify frontend to show distance overlay
                                map_state_manager.set_distance_info(
                                    distance=distance, duration=duration
                                )

                # Directions results
                elif tool_name == "maps_directions" and "routes" in result:
                    routes = result.get("routes", [])
                    if routes:
                        leg = routes[0].get("legs", [{}])[0]
                        map_state_manager.add_route(
                            origin=leg.get("start_location"),
                            destination=leg.get("end_location"),
                            polyline=routes[0].get("overview_polyline", {}).get("points"),
                            distance=leg.get("distance", {}).get("text"),
                            duration=leg.get("duration", {}).get("text"),
                            steps=leg.get("steps", []),
                        )
                        # Ensure map is visible
                        map_state_manager.trigger_map_display()
        except ImportError:
            pass  # map_state might not be available in all contexts
        except Exception as e:
            logger.warning(f"[DISPATCHER] Map visualization hook failed: {e}")

    def _validate_realm_tool_compatibility(
        self, server: str, tool_name: str, args: dict[str, Any]
    ) -> tuple[bool, str]:
        """Validate that a tool is compatible with its assigned realm/server.

        Returns:
            (is_valid: bool, error_message: str)
        """

        # Get server capabilities and key tools
        server_info = SERVER_CATALOG.get(server)
        if not server_info:
            return False, f"Unknown server/realm: {server}"

        # Check if tool is in the server's key tools
        key_tools = server_info.get("key_tools", [])
        if tool_name in key_tools:
            return True, ""

        # Check if tool exists in the tool schemas for this server
        # Tool names in schemas are typically in the format "server_tool_name"
        expected_tool_patterns = [
            f"{server}_{tool_name}",
            f"{server.replace('-', '_')}_{tool_name}",
            tool_name,  # Some tools might be listed without server prefix
        ]

        # Check if any of the patterns exist in tool schemas
        tool_found = False
        for pattern in expected_tool_patterns:
            if pattern in TOOL_SCHEMAS:
                tool_found = True
                break

        if tool_found:
            return True, ""

        # Check if tool name starts with normalized server prefix (standard naming convention)
        # e.g., "duckduckgo_search" starts with "duckduckgo-search" → "duckduckgo_search_"
        server_prefix = server.replace("-", "_") + "_"
        if tool_name.startswith(server_prefix) or tool_name.startswith(server + "_"):
            return True, ""

        # Special case: data-analysis realm validation
        if server == "data-analysis":
            data_analysis_tools = [
                "analyze_dataset",
                "generate_statistics",
                "create_visualization",
                "data_cleaning",
                "data_aggregation",
                "read_metadata",
                "interpret_column_data",
                "run_pandas_code",
            ]
            if tool_name in data_analysis_tools:
                return True, ""
            return (
                False,
                f"Tool '{tool_name}' is not compatible with data-analysis realm. Available tools: {', '.join(data_analysis_tools)}",
            )

        # Special case: golden-fund realm validation
        if server == "golden-fund":
            golden_fund_tools = [
                "search_golden_fund",
                "ingest_dataset",
                "probe_entity",
                "add_knowledge_node",
                "store_blob",
                "retrieve_blob",
                "analyze_and_store",
                "get_dataset_insights",
            ]
            if tool_name in golden_fund_tools:
                return True, ""
            return (
                False,
                f"Tool '{tool_name}' is not compatible with golden-fund realm. Available tools: {', '.join(golden_fund_tools)}",
            )

        # For other realms, provide a generic compatibility check
        capabilities = server_info.get("capabilities", [])
        tool_lower = tool_name.lower()

        # Check if tool name contains keywords from server capabilities
        capability_match = any(
            cap_keyword in tool_lower
            for capability in capabilities
            for cap_keyword in capability.lower().split()
        )

        if capability_match:
            return True, ""

        return (
            False,
            f"Tool '{tool_name}' may not be compatible with {server} realm. Server capabilities: {', '.join(capabilities)}",
        )

    # Universal argument synonym map: schema_name -> [known LLM aliases]
    _ARG_SYNONYMS: dict[str, list[str]] = {
        "term": ["query", "search", "keyword", "libraryName"],
        "command": ["cmd", "action", "script", "code"],
        "goal": [
            "feature_description",
            "features",
            "objective",
            "prompt",
            "errors",
            "artifacts_to_fix",
        ],
        "data_source": ["source", "file", "path", "dataset"],
        "log_path": ["logs", "path", "file"],
        "prompt": ["query", "question", "objective", "action"],
        "company_name": ["query", "name", "company"],
        "query": ["question", "search", "term", "action", "path"],
        "file_path": ["review_scope", "path", "file", "source_file"],
        "libraryName": ["query", "term", "search"],
    }

    def _autofill_missing_args(
        self, tool_name: str, validated: dict[str, Any], missing: list[str]
    ) -> list[str]:
        """Try to auto-fill common missing arguments with sensible defaults.

        Uses a universal synonym table to map LLM-generated argument names
        to the canonical names expected by tool schemas.
        """
        for req in list(missing):
            if req in validated and validated[req] is not None:
                continue

            # 1. Try universal synonym lookup
            synonyms = self._ARG_SYNONYMS.get(req, [])
            for syn in synonyms:
                if syn in validated and validated[syn] is not None:
                    validated[req] = validated[syn]
                    logger.info(f"[DISPATCHER] Auto-filled '{req}' from '{syn}' for {tool_name}")
                    break

        # Re-check after auto-fill
        return [r for r in missing if r not in validated or validated[r] is None]

    def _convert_arg_types(
        self, tool_name: str, validated: dict[str, Any], types_map: dict[str, str]
    ) -> None:
        """Perform type conversion with improved error handling."""
        for key, expected_type in types_map.items():
            if key in validated and validated[key] is not None:
                value = validated[key]
                try:
                    validated[key] = self._convert_single_arg_value(
                        tool_name, key, value, expected_type
                    )
                except (ValueError, TypeError) as e:
                    logger.error(
                        f"[DISPATCHER] Type conversion failed for '{key}' in tool '{tool_name}': {e}. Expected: {expected_type}, Got: {type(value).__name__}.",
                    )

    def _convert_single_arg_value(
        self, tool_name: str, key: str, value: Any, expected_type: str
    ) -> Any:
        """Helper to convert a single argument value to the expected type."""
        if expected_type == "str" and not isinstance(value, str):
            return str(value)
        if expected_type == "int" and not isinstance(value, int):
            if isinstance(value, float):
                return int(value)
            return int(float(value))
        if expected_type == "float" and not isinstance(value, int | float):
            return float(value)
        if expected_type == "bool" and not isinstance(value, bool):
            return str(value).lower() in ("true", "1", "yes", "on")
        if expected_type == "list" and not isinstance(value, list):
            return self._convert_to_list(value)
        if expected_type == "dict" and not isinstance(value, dict):
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    logger.warning(f"[DISPATCHER] Could not parse dict from string for '{key}'")
        return value

    def _convert_to_list(self, value: Any) -> list[Any]:
        """Helper to convert a value to a list."""
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else [value]
            except json.JSONDecodeError:
                if "," in value:
                    return [v.strip() for v in value.split(",")]
                return [value]
        return [value]

    def _validate_args(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize arguments according to tool schema.
        Returns args with __validation_error__ key if validation failed.
        """
        from src.brain.mcp.mcp_registry import get_tool_schema

        schema = get_tool_schema(tool_name)
        if not schema:
            # No schema found - pass through without validation
            logger.debug(
                f"[DISPATCHER] No schema found for tool '{tool_name}', skipping validation"
            )
            return args if isinstance(args, dict) else {}

        validated = dict(args) if isinstance(args, dict) else {}

        # Check required arguments
        required = schema.get("required", [])
        missing = [r for r in required if r not in validated or validated[r] is None]

        if missing:
            # Try to auto-fill common missing arguments with sensible defaults FIRST
            missing = self._autofill_missing_args(tool_name, validated, missing)

            # ONLY log and fail if there are genuinely missing args after autofill
            if missing:
                error_msg = f"Missing required arguments: {', '.join(missing)}. Schema requires: {required}. Provided: {list(validated.keys())}"
                logger.error(f"[DISPATCHER] Validation failed for '{tool_name}': {error_msg}")
                validated["__validation_error__"] = error_msg
                return validated

        # Type conversion with improved error handling
        self._convert_arg_types(tool_name, validated, schema.get("types", {}))

        return validated

    def _infer_tool_from_args(self, args: dict[str, Any]) -> str:
        """Infers tool name from common argument patterns when missing."""
        action = str(args.get("action", "")).lower()
        command = str(args.get("command", args.get("cmd", ""))).lower()
        path = str(args.get("path", "")).lower()

        if "vibe" in action or "vibe" in command:
            return "vibe"
        if any(kw in action for kw in ["click", "type", "press", "screenshot", "scroll"]):
            return "xcodebuild"
        if any(kw in action for kw in ["read", "write", "list", "save", "delete"]) or path:
            return "filesystem"
        if any(kw in action for kw in ["browser", "puppeteer", "navigate", "google", "search"]):
            return "puppeteer"
        if command:
            return "terminal"

        return action or "terminal"

    def _can_macos_use_handle(self, tool_name: str) -> bool:
        """Check if macOS-use can handle this tool based on priority set."""
        tool_lower = tool_name.lower()

        # Direct check in priority set
        if any(priority in tool_lower for priority in self.MACOS_USE_PRIORITY):
            return True

        # Check if it's already a macos-use tool
        if tool_lower.startswith("xcodebuild") or tool_lower.startswith("macos_use_"):
            return True

        # Check MACOS_MAP
        return tool_lower in self.MACOS_MAP

    def _intelligent_routing(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> tuple[str | None, str, dict[str, Any]]:
        """Intelligent tier-based routing with macOS-use priority.
        Now delegates to BehaviorEngine for config-driven routing.
        """
        from src.brain.behavior.behavior_engine import behavior_engine

        # Fix for generic 'memory' tool call (LLM hallucination)
        if tool_name.lower() == "memory" and "query" in args:
            return "memory", "search", args

        # Delegate to behavior engine for routing (replaces 150+ lines of hardcoded logic)
        try:
            server, resolved_tool, normalized_args = behavior_engine.route_tool(
                tool_name,
                args,
            )

            if server:
                # Still pass through server-specific handlers if they exist for normalized handling
                handlers = {
                    "xcodebuild": self._handle_xcodebuild_unified,
                    "filesystem": self._handle_filesystem,
                    "terminal": self._handle_terminal,
                    "vibe": self._handle_vibe,
                    "puppeteer": self._handle_browser,
                    "browser": self._handle_browser,
                    "devtools": self._handle_devtools,
                    "context7": self._handle_context7,
                    "golden-fund": self._handle_golden_fund,
                    "data-analysis": self._handle_data_analysis,
                    "tour-guide": self._handle_tour,
                }
                if server in handlers:
                    logger.debug(
                        f"[DISPATCHER] Delegating {server}.{resolved_tool} to specialized handler"
                    )
                    return handlers[server](resolved_tool, normalized_args)

                logger.debug(
                    f"[DISPATCHER] BehaviorEngine routing: {tool_name} -> {server}.{resolved_tool}",
                )
                return server, resolved_tool, normalized_args
        except Exception as e:
            logger.warning(
                f"[DISPATCHER] BehaviorEngine routing failed: {e}, falling back to registry",
            )

        # Fallback: Use registry-based resolution
        return self._resolve_tool_and_args(tool_name, args)

    def get_coverage_stats(self) -> dict[str, Any]:
        """Get macOS-use coverage statistics."""
        coverage_pct = (
            (self._macos_use_calls / self._total_calls * 100) if self._total_calls > 0 else 0
        )
        return {
            "total_calls": self._total_calls,
            "macos_use_calls": self._macos_use_calls,
            "coverage_percentage": round(coverage_pct, 2),
            "target": 90.0,
        }

    def _resolve_tool_and_args(
        self,
        tool_name: str,
        args: dict[str, Any],
        explicit_server: str | None = None,
    ) -> tuple[str | None, str, dict[str, Any]]:
        """Resolves tool name to canonical form and normalizes arguments."""
        # 1. Strict Server Priority
        res_explicit = self._handle_explicit_server(tool_name, args, explicit_server)
        if res_explicit:
            return res_explicit

        # 2. Namespace/Synonym Routing
        res_synonym = self._route_by_synonyms(tool_name, args, explicit_server)
        if res_synonym:
            return res_synonym

        # 3. Fallback: Registry
        return self._resolve_from_registry(tool_name, args, explicit_server)

    def _handle_explicit_server(
        self, tool_name: str, args: dict[str, Any], explicit_server: str | None
    ) -> tuple[str, str, dict[str, Any]] | None:
        """Handle strict server priority routing."""
        handlers = {
            "xcodebuild": self._handle_xcodebuild_unified,
            "macos-use": self._handle_macos_use,
            "filesystem": self._handle_filesystem,
            "terminal": self._handle_terminal,
            "vibe": self._handle_vibe,
            "puppeteer": self._handle_browser,
            "browser": self._handle_browser,
            "devtools": self._handle_devtools,
            "context7": self._handle_context7,
            "golden-fund": self._handle_golden_fund,
            "golden_fund": self._handle_golden_fund,
            "tour-guide": self._handle_tour,
            "googlemaps": self._handle_xcodebuild_unified,
            "google-maps": self._handle_xcodebuild_unified,
            "report-generator": self._handle_report_generator,
        }
        if explicit_server and explicit_server in handlers:
            return handlers[explicit_server](tool_name, args)
        return None

    def _route_by_synonyms(
        self, tool_name: str, args: dict[str, Any], explicit_server: str | None
    ) -> tuple[str | None, str, dict[str, Any]] | None:
        """Route tool by name synonyms or namespaces."""
        # macOS-use & Notes
        if (
            tool_name.startswith(("xcodebuild", "macos_use_", "notes_", "note_"))
            or tool_name in self.MACOS_MAP
            or explicit_server in ("notes", "macos-use")
        ):
            return self._handle_macos_use(tool_name, args)

        # Google Maps & Navigation
        if tool_name.startswith("maps_") or explicit_server in ("googlemaps", "google-maps"):
            return "xcodebuild", tool_name, args

        # Basic Synonyms
        if tool_name in self.TERMINAL_SYNONYMS:
            return self._handle_terminal(tool_name, args)
        if tool_name in self.FILESYSTEM_SYNONYMS:
            return self._handle_filesystem(tool_name, args)
        if (tool_name in self.BROWSER_SYNONYMS and tool_name != "search") or tool_name.startswith(
            ("puppeteer_", "browser_")
        ):
            return self._handle_browser(tool_name, args)
        if tool_name in self.VIBE_SYNONYMS:
            return self._handle_vibe(tool_name, args)
        if tool_name in self.DUCKDUCKGO_SYNONYMS:
            return "duckduckgo-search", "duckduckgo_search", args

        # Specialized Tools
        if tool_name in ["sequential-thinking", "sequentialthinking", "think"]:
            return "sequential-thinking", "sequentialthinking", args
        if tool_name in self.DEVTOOLS_SYNONYMS:
            return self._handle_devtools(tool_name, args)
        if tool_name in self.CONTEXT7_SYNONYMS:
            return self._handle_context7(tool_name, args)
        if tool_name in self.GOLDEN_FUND_SYNONYMS:
            return self._handle_golden_fund(tool_name, args)
        if tool_name in self.DATA_ANALYSIS_SYNONYMS or explicit_server == "data-analysis":
            return self._handle_data_analysis(tool_name, args)
        if tool_name in self.XCODEBUILD_SYNONYMS or explicit_server == "xcodebuild":
            return self._handle_xcodebuild(tool_name, args)
        if tool_name.startswith("git_") or explicit_server == "git":
            return self._handle_legacy_git(tool_name, args)

        # Hallucination Fallbacks
        if tool_name == "prerequisite_gap_analyzer":
            args["objective"] = "Analyze prerequisites and gaps for this feature"
            return "vibe", "vibe_smart_plan", args

        return None

    def _resolve_from_registry(
        self, tool_name: str, args: dict[str, Any], explicit_server: str | None
    ) -> tuple[str | None, str, dict[str, Any]]:
        """Final fallback to MCP registry lookup."""
        # Normalize hyphenated tool names to underscores for Python-based servers
        if tool_name == "duckduckgo-search":
            tool_name = "duckduckgo_search"
        elif tool_name == "whisper-stt":
            tool_name = "transcribe_audio"

        server = explicit_server or get_server_for_tool(tool_name)
        if not server:
            # Try registry-based name mapping
            schema = get_tool_schema(tool_name)
            if schema:
                server = schema.get("server")

        return server, tool_name, args

    def _handle_legacy_git(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        """Maps legacy git_server tools to macos-use execute_command."""
        subcommand = tool_name.replace("git_", "").replace("_", "-")  # git_status -> status

        # Base command
        cmd_parts = ["git", subcommand]

        # Heuristic argument mapping
        if "path" in args:  # implicit cwd usually, but for git command usually we run IN that dir
            # We rely on mcp_manager to handle 'cwd' via chaining or just assume '.' is target
            pass

        # Simple flags mapping
        if args.get("porcelain"):
            cmd_parts.append("--porcelain")
        if args.get("staged"):
            cmd_parts.append("--staged")
        if args.get("message"):
            cmd_parts.extend(["-m", f'"{args["message"]}"'])
        if args.get("branch"):
            cmd_parts.append(args["branch"])
        if args.get("target"):
            cmd_parts.append(args["target"])

        # Construct command
        full_command = " ".join(cmd_parts)

        new_args = {"command": full_command}
        if "path" in args:
            # git_server used 'path' as cwd.
            # execute_command doesn't natively support cwd param in mcp-server-macos-use (it runs in user home usually)
            # So we chain it: cd path && git ...
            path = args["path"]
            new_args["command"] = f"cd {path} && {full_command}"

        return "xcodebuild", "execute_command", new_args

    def _handle_report_generator(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        """Fallback to handle hallucinated report-generator server requests"""
        logger.info(
            f"[DISPATCHER] Handled hallucinated report-generator ({tool_name}), redirecting to data-analysis"
        )
        # Ensure we have some sort of command for it
        if "action" not in args:
            args["action"] = tool_name
        return "data-analysis", "analyze_dataset", args

    def _handle_data_analysis(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        """Maps data analysis synonyms to canonical data-analysis tools."""
        action = args.get("action") or tool_name

        # Action mappings
        mapping = {
            "analyze_data": "analyze_dataset",
            "analyze-dataset": "analyze_dataset",
            "statistics": "generate_statistics",
            "generate-statistics": "generate_statistics",
            "visualization": "create_visualization",
            "create-visualization": "create_visualization",
            "cleaning": "data_cleaning",
            "data-cleaning": "data_cleaning",
            "modeling": "predictive_modeling",
            "predictive-modeling": "predictive_modeling",
            "aggregation": "data_aggregation",
            "data-aggregation": "data_aggregation",
        }
        resolved_tool = mapping.get(action, action)

        # If the tool name itself was the action
        if resolved_tool == "data-analysis":
            resolved_tool = "analyze_dataset"  # Default

        return "data-analysis", resolved_tool, args

    def _handle_xcodebuild_unified(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        """Unified handler for xcodebuild server (native Xcode + macOS bridge + Maps bridge).

        Routes to the appropriate sub-handler based on tool name prefix:
        - macos-use_* / execute_command / MACOS_MAP -> _handle_macos_use
        - maps_* -> direct passthrough to xcodebuild
        - everything else -> _handle_xcodebuild (native Xcode tools)
        """
        if (
            tool_name.startswith("macos-use_")
            or tool_name in self.MACOS_MAP
            or tool_name in ("execute_command", "terminal")
        ):
            return self._handle_macos_use(tool_name, args)
        if tool_name.startswith("maps_"):
            return "xcodebuild", tool_name, args
        return self._handle_xcodebuild(tool_name, args)

    def _handle_xcodebuild(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        """Maps XcodeBuildMCP synonyms to canonical xcodebuild tools."""
        action = args.get("action") or tool_name

        # Action mappings for common synonyms
        mapping = {
            # NOTE: xcodebuildmcp uses tool names like build_sim/list_sims/boot_sim/etc.
            # Keep this mapping aligned with live tools/list.
            "build_project": "discover_projs",
            "build-project": "discover_projs",
            "xcode": "discover_projs",
            "run_tests": "test_sim",
            "run-tests": "test_sim",
            "simulator": "list_sims",
            "ios_simulator": "list_sims",
            "ios-simulator": "list_sims",
            "list_simulators": "list_sims",
            "boot_simulator": "boot_sim",
            "install_app": "install_app_sim",
            "launch_app": "launch_app_sim",
            "analyze_logs": "doctor",
            "xcode_logs": "doctor",
            "xcode-logs": "doctor",
            "coverage": "doctor",
            "code_coverage": "doctor",
            "code-coverage": "doctor",
            "archive": "doctor",
            "archive_project": "doctor",
            "archive-project": "doctor",
            "clean": "clean",
            "clean_build": "clean",
        }
        resolved_tool = mapping.get(action, action)

        # Default action for generic xcodebuild call
        if resolved_tool in ["xcodebuild", "xcode", "ios_development", "macos_development"]:
            resolved_tool = "discover_projs"

        return "xcodebuild", resolved_tool, args

    def _handle_terminal(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        """Standardizes terminal command execution via macos-use.

        Handles LLM-generated argument variations:
        - command/cmd/code/script/args/action -> command
        - path -> cwd (for cd chaining)
        - Cleans up extraneous args (step_id, action, etc.)
        """
        # Extract command from various possible argument names
        cmd = (
            args.get("command")
            or args.get("cmd")
            or args.get("code")
            or args.get("script")
            or args.get("args")
            or args.get("action")
        )

        # Extract working directory from 'path' or 'cwd'
        cwd = args.get("cwd") or args.get("path")

        # Handle cases where tool_name IS the command (mkdir, ls, etc)
        if tool_name in [
            "mkdir",
            "ls",
            "cat",
            "rm",
            "mv",
            "cp",
            "touch",
            "sudo",
            "git",
            "npm",
            "npx",
            "brew",
        ]:
            if isinstance(cmd, str):
                cmd = f"{tool_name} {cmd}".strip()
            else:
                cmd = tool_name

        # Build clean args dict with only what execute_command expects
        clean_args: dict[str, Any] = {}
        clean_args["command"] = str(cmd) if cmd else ""

        # Chain cwd if provided (cd path && command)
        if cwd and clean_args["command"] and not clean_args["command"].startswith("cd "):
            clean_args["command"] = f"cd {cwd} && {clean_args['command']}"

        return "xcodebuild", "execute_command", clean_args

    def _handle_filesystem(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        """Maps filesystem synonyms to canonical tools."""
        action = args.get("action") or tool_name

        # Action mappings
        mapping = {
            "list_dir": "list_directory",
            "ls": "list_directory",
            "mkdir": "create_directory",
            "write": "write_file",
            "save": "write_file",
            "read": "read_file",
            "cat": "read_file",
            "exists": "get_file_info",
            "directory_tree": "list_directory",
            "tree": "list_directory",
        }
        resolved_tool = mapping.get(action, action)

        # If the tool name itself was the action
        if resolved_tool == "filesystem":
            resolved_tool = "read_file"  # Default

        return "filesystem", resolved_tool, args

    def _handle_browser(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        """Maps browser synonyms to Puppeteer tools.

        IMPORTANT: 'search' must NEVER be routed through this method.
        Search functionality is handled exclusively by the memory server.
        This ensures search results are properly stored and accessible for knowledge graph operations.
        """
        action = args.get("action") or tool_name

        # Critical safeguard: prevent 'search' from being routed to puppeteer directly
        # Instead of crashing, we route to duckduckgo for actual web search
        if tool_name == "search" or action == "search":
            logger.info("[DISPATCHER] Redirecting browser search to duckduckgo-search")
            return "duckduckgo-search", "duckduckgo_search", args

        mapping = {
            "google": "puppeteer_navigate",
            "bing": "puppeteer_navigate",
            "navigate": "puppeteer_navigate",
            "browse": "puppeteer_navigate",
            "web_search": "puppeteer_navigate",
            "internet_search": "puppeteer_navigate",
            "online_search": "puppeteer_navigate",
            "screenshot": "puppeteer_screenshot",
            "click": "puppeteer_click",
            "type": "puppeteer_fill",
            "fill": "puppeteer_fill",
        }

        resolved_tool = mapping.get(action, action)

        # Ensure 'puppeteer_' prefix if not already present
        if not resolved_tool.startswith("puppeteer_") and resolved_tool != "puppeteer":
            resolved_tool = f"puppeteer_{resolved_tool}"

        # If it was just 'browser' or 'puppeteer'
        if resolved_tool in ["browser", "puppeteer", "puppeteer_browser", "puppeteer_puppeteer"]:
            resolved_tool = "puppeteer_navigate"

        return "puppeteer", resolved_tool, args

    def _handle_vibe(self, tool_name: str, args: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
        """Normalizes Vibe AI tool calls and arguments."""
        # Tool name normalization
        vibe_map = {
            "vibe": "vibe_prompt",
            "prompt": "vibe_prompt",
            "vibe_prompt": "vibe_prompt",
            "ask": "vibe_ask",
            "vibe_ask": "vibe_ask",
            "question": "vibe_ask",
            "plan": "vibe_smart_plan",
            "smart_plan": "vibe_smart_plan",
            "vibe_smart_plan": "vibe_smart_plan",
            "debug": "vibe_analyze_error",
            "fix": "vibe_analyze_error",
            "vibe_analyze_error": "vibe_analyze_error",
            "analyze_error": "vibe_analyze_error",
            "review": "vibe_code_review",
            "vibe_code_review": "vibe_code_review",
            "code_review": "vibe_code_review",
            "implement": "vibe_implement_feature",
            "feature": "vibe_implement_feature",
            "vibe_implement_feature": "vibe_implement_feature",
            "implement_feature": "vibe_implement_feature",
            "subcommand": "vibe_execute_subcommand",
            "vibe_execute_subcommand": "vibe_execute_subcommand",
            "sessions": "vibe_list_sessions",
            "vibe_list_sessions": "vibe_list_sessions",
            "session_details": "vibe_session_details",
            "vibe_session_details": "vibe_session_details",
            "which": "vibe_which",
            "vibe_which": "vibe_which",
            "config": "vibe_get_config",
            "get_config": "vibe_get_config",
            "vibe_get_config": "vibe_get_config",
            "model": "vibe_configure_model",
            "configure_model": "vibe_configure_model",
            "switch_model": "vibe_configure_model",
            "vibe_configure_model": "vibe_configure_model",
            "mode": "vibe_set_mode",
            "set_mode": "vibe_set_mode",
            "vibe_set_mode": "vibe_set_mode",
            "provider": "vibe_configure_provider",
            "configure_provider": "vibe_configure_provider",
            "vibe_configure_provider": "vibe_configure_provider",
            "resume": "vibe_session_resume",
            "continue": "vibe_session_resume",
            "vibe_session_resume": "vibe_session_resume",
            "reload": "vibe_reload_config",
            "reload_config": "vibe_reload_config",
            "vibe_reload_config": "vibe_reload_config",
            "check_db": "vibe_check_db",
            "vibe_check_db": "vibe_check_db",
            "system_context": "vibe_get_system_context",
            "get_system_context": "vibe_get_system_context",
            "vibe_get_system_context": "vibe_get_system_context",
            "test_in_sandbox": "vibe_test_in_sandbox",
            "sandbox": "vibe_test_in_sandbox",
            "vibe_test_in_sandbox": "vibe_test_in_sandbox",
        }
        resolved_tool = vibe_map.get(tool_name, tool_name)
        if not resolved_tool.startswith("vibe_"):
            resolved_tool = f"vibe_{resolved_tool}"

        # Argument normalization
        if "prompt" not in args:
            if "objective" in args:
                args["prompt"] = args["objective"]
            elif "question" in args:
                args["prompt"] = args["question"]
            elif "error_message" in args:
                args["prompt"] = args["error_message"]
            elif "action" in args:
                args["prompt"] = args["action"]

        # Normalize 'goal' for vibe_implement_feature
        if resolved_tool == "vibe_implement_feature" and "goal" not in args:
            if "feature_description" in args:
                args["goal"] = args["feature_description"]
            elif "features" in args:
                args["goal"] = args["features"]
            elif "errors" in args:
                args["goal"] = args["errors"]
            elif "artifacts_to_fix" in args:
                args["goal"] = args["artifacts_to_fix"]
            elif "previous_verification_results" in args:
                args["goal"] = args["previous_verification_results"]
            elif "prompt" in args:
                args["goal"] = args["prompt"]

        # Normalize 'file_path' for vibe_code_review
        if resolved_tool == "vibe_code_review" and "file_path" not in args:
            if "review_scope" in args:
                args["file_path"] = args["review_scope"]
            elif "path" in args:
                args["file_path"] = args["path"]

        # Enforce defaults/timeouts - Vibe tasks can be long-running
        if "timeout_s" not in args:
            # Try mcp.vibe config first, then default to 1 hour (3600s)
            vibe_cfg = config.get("mcp", {}).get("vibe", {})
            args["timeout_s"] = float(vibe_cfg.get("timeout_s", 3600))

        # Enforce absolute CWD or workspace from config
        if not args.get("cwd"):
            system_config = config.get("system", {})
            # Recommended default is CONFIG_ROOT / "workspace" if not in config
            workspace_str = system_config.get("workspace_path", str(CONFIG_ROOT / "workspace"))
            workspace = Path(workspace_str).expanduser().absolute()
            args["cwd"] = str(workspace)
            workspace.mkdir(parents=True, exist_ok=True)

        # Verify repository path for self-healing
        system_config = config.get("system", {})
        repo_path = Path(system_config.get("repository_path", PROJECT_ROOT)).expanduser().absolute()
        if (repo_path / ".git").exists():
            logger.info(f"[DISPATCHER] Repository root verified for self-healing: {repo_path}")
        else:
            logger.warning(
                f"[DISPATCHER] Repository root at {repo_path} is NOT a git repo. Self-healing might be limited.",
            )

        return "vibe", resolved_tool, args

    async def _handle_system(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Handles internal Trinity system tools."""
        if tool_name == "restart_mcp_server":
            server_to_restart = args.get("server_name")
            if not server_to_restart:
                return {"success": False, "error": "Missing 'server_name' argument."}

            logger.info(f"[SYSTEM] Restarting MCP server: {server_to_restart}")
            success = await self.mcp_manager.restart_server(server_to_restart)
            return {
                "success": success,
                "result": f"Server '{server_to_restart}' restart {'successful' if success else 'failed'}.",
            }

        if tool_name == "query_db":
            # For now, we don't expose raw SQL to agents for safety, but we could implement specific queries
            return {
                "success": False,
                "error": "Direct DB queries via LLM are currently restricted for safety.",
            }

        if tool_name == "restart_application":
            reason = args.get("reason", "Manual restart triggered")
            logger.warning(f"[SYSTEM] Application restart triggered: {reason}")

            # trigger async restart to allow this request to complete
            import os
            import sys

            async def delayed_restart():
                # Set restart_pending flag in Redis for resumption logic
                if state_manager and state_manager.available:
                    restart_metadata = {
                        "reason": reason,
                        "timestamp": datetime.now().isoformat(),
                        "session_id": "current",  # Or a specific active session ID if known
                    }
                    cast("Any", state_manager).redis.set(
                        cast("Any", state_manager)._key("restart_pending"),
                        json.dumps(restart_metadata),
                    )
                    logger.info("[SYSTEM] restart_pending flag set in Redis.")

                await asyncio.sleep(2.0)
                logger.info("[SYSTEM] Executing os.execv restart now...")
                os.execv(sys.executable, [sys.executable, *sys.argv])  # nosec B606

            task = asyncio.create_task(delayed_restart())
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

            return {
                "success": True,
                "result": "Initiating graceful restart sequence. I will be back in a moment.",
            }

        if tool_name in {"system", "status"}:
            # Generic status/meta tool for informational steps
            return {
                "success": True,
                "result": args.get("message") or args.get("action") or "Operation noted by system.",
            }

        return {"success": False, "error": f"Unknown system tool: {tool_name}"}

    async def _execute_tour(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Executes Tour Driver commands locally."""
        from src.brain.navigation.tour_driver import tour_driver

        try:
            if tool_name == "tour_start":
                polyline = args.get("polyline")
                if not polyline:
                    return {"success": False, "error": "Missing 'polyline' argument"}
                await tour_driver.start_tour(polyline)
                return {"success": True, "result": "Tour started successfully"}

            if tool_name == "tour_stop":
                await tour_driver.stop_tour()
                return {"success": True, "result": "Tour stopped"}

            if tool_name == "tour_pause":
                tour_driver.pause_tour()
                return {"success": True, "result": "Tour paused"}

            if tool_name == "tour_resume":
                tour_driver.resume_tour()
                return {"success": True, "result": "Tour resumed"}

            if tool_name == "tour_look":
                angle = args.get("angle", 0)
                tour_driver.look_around(int(angle))
                return {"success": True, "result": f"Looked {angle} degrees"}

            if tool_name == "tour_set_speed":
                speed = args.get("speed", 1.0)
                tour_driver.set_speed(float(speed))
                return {"success": True, "result": f"Speed set to {speed}"}

            return {"success": False, "error": f"Unknown tour tool: {tool_name}"}
        except Exception as e:
            logger.exception(f"[DISPATCHER] Tour execution failed: {e}")
            return {"success": False, "error": str(e)}

    def _handle_tour(self, tool_name: str, args: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
        """Resolution handler for tour guide tools."""
        # Simple pass-through as tools are 1:1 mapped
        return "tour-guide", tool_name, args

    def _handle_devtools(
        self, tool_name: str, args: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any]]:
        """Maps DevTools synonyms to canonical tools."""
        if tool_name in ["lint", "linter", "ruff"]:
            return "devtools", "devtools_lint_python", args
        if tool_name in ["oxlint", "js_lint"]:
            return "devtools", "devtools_lint_js", args
        if tool_name in ["inspect", "inspector"]:
            return "devtools", "devtools_launch_inspector", args
        if tool_name in ["health", "check"]:
            if "mcp" in str(args):
                return "devtools", "devtools_check_mcp_health", args
            return "devtools", "devtools_check_mcp_health", args
        return "devtools", tool_name, args

    def _handle_context7(
        self, tool_name: str, args: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any]]:
        """Maps Context7 synonyms and legacy tools to working canonical tools."""
        # 1. Map synonyms and legacy tools to live Context7 tool names
        if tool_name in [
            "docs",
            "documentation",
            "lookup",
            "library",
            "c7_search",
            "c7_list_libraries",
            "resolve-library-id",
            "resolve_library_id",
        ]:
            resolved_tool = "c7_search"
        elif tool_name in [
            "c7_query",
            "c7_info",
            "get_context",
            "c7_get_context",
            "get-library-docs",
            "get_library_docs",
        ]:
            resolved_tool = "c7_query"
        else:
            resolved_tool = tool_name

        # 2. Argument normalization/mapping
        if resolved_tool == "c7_search":
            # Live schema expects: term
            if "libraryName" in args and "term" not in args:
                args["term"] = args.pop("libraryName")
            if "query" in args and "term" not in args:
                args["term"] = args.pop("query")
        elif resolved_tool == "c7_query":
            # Live schema expects: projectIdentifier + query
            if "context7CompatibleLibraryID" in args and "projectIdentifier" not in args:
                args["projectIdentifier"] = args.pop("context7CompatibleLibraryID")
            if "topic" in args and "query" not in args:
                args["query"] = args.pop("topic")

        return "context7", resolved_tool, args

    def _handle_golden_fund(
        self, tool_name: str, args: dict[str, Any]
    ) -> tuple[str, str, dict[str, Any]]:
        """Maps Golden Fund synonyms to canonical tools."""
        if tool_name in ["ingest", "ingestion", "etl"]:
            return "golden-fund", "ingest_dataset", args
        if tool_name in ["probe", "deep_search", "explore"]:
            return "golden-fund", "probe_entity", args
        if tool_name in ["vector_search", "semantic_search", "kb_search", "search_kb"]:
            args["mode"] = args.get("mode", "semantic")
            return "golden-fund", "search_golden_fund", args
        return "golden-fund", tool_name, args

    def _handle_macos_use(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        """Standardizes macos-use GUI and productivity tool calls."""
        if tool_name.startswith("git_"):
            return self._handle_legacy_git(tool_name, args)

        clean_name = self._get_clean_macos_tool_name(tool_name, args)
        resolved_tool = self.MACOS_MAP.get(clean_name, tool_name)

        # FINAL SAFETY: If we still have 'xcodebuild' as a method name, it's definitely an error.
        if resolved_tool == "xcodebuild":
            resolved_tool = self._last_resort_macos_mapping(args)

        if resolved_tool == "macos-use_fetch_url":
            self._patch_fetch_args(args)

        # Inject PID if missing
        if self._current_pid and "pid" not in args:
            args["pid"] = self._current_pid

        # Standardize 'identifier' for app opening
        if resolved_tool == "macos-use_open_application_and_traverse":
            self._standardize_app_identifier(args)

        return "xcodebuild", resolved_tool, args

    def _get_clean_macos_tool_name(self, tool_name: str, args: dict[str, Any]) -> str:
        """Extract clean tool name from macos-use prefix or generic call."""
        if tool_name.startswith(("macos-use_", "macos_use_")):
            return tool_name[10:]
        if tool_name == "xcodebuild":
            return self._infer_macos_tool_from_args(args)
        return tool_name

    def _infer_macos_tool_from_args(self, args: dict[str, Any]) -> str:
        """Heuristically infer the tool based on arguments."""
        if "identifier" in args:
            return "open"
        if "x" in args:
            return "click"
        if "text" in args:
            return "type"
        if "path" in args:
            return "finder_list"
        if "url" in args:
            return "fetch"
        if "command" in args:
            return "terminal"
        return "screenshot"

    def _last_resort_macos_mapping(self, args: dict[str, Any]) -> str:
        """Handle cases where tool name remains generic 'xcodebuild'."""
        if "command" in args or "cmd" in args:
            resolved = "execute_command"
        elif "path" in args:
            resolved = "macos-use_finder_open_path"
        else:
            resolved = "macos-use_take_screenshot"
        logger.info(f"[DISPATCHER] Last-resort mapping macos-use -> {resolved}")
        return resolved

    def _patch_fetch_args(self, args: dict[str, Any]) -> None:
        """Patch 'urls[0]' to 'url' for fetch_url if needed."""
        if "urls" in args and "url" not in args:
            urls = args.get("urls")
            if isinstance(urls, list) and len(urls) > 0:
                args["url"] = urls[0]
                logger.info(f"[DISPATCHER] Patched fetch: urls[0] -> url ({args['url']})")

    def _standardize_app_identifier(self, args: dict[str, Any]) -> None:
        """Ensure 'identifier' is present for application opening."""
        if "identifier" not in args:
            args["identifier"] = args.get("app_name") or args.get("name") or args.get("app") or ""
