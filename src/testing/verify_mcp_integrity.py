"""MCP Catalog & Schema Integrity Verifier
Compares mcp_catalog.json and tool_schemas.json with live server data.
"""

import asyncio
import json
import os
import sys

# Add src to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from src.brain.mcp.mcp_registry import mcp_registry  # pyre-ignore
from src.brain.mcp.mcp_manager import mcp_manager  # pyre-ignore
from src.brain.logger import logger  # pyre-ignore


class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    ENDC = "\033[0m"


async def verify_integrity():

    # 1. Load static files
    catalog_path = os.path.join(PROJECT_ROOT, "src", "brain", "data", "mcp_catalog.json")
    schemas_path = os.path.join(PROJECT_ROOT, "src", "brain", "data", "tool_schemas.json")

    with open(catalog_path, encoding="utf-8") as f:
        catalog_data = json.load(f)
    with open(schemas_path, encoding="utf-8") as f:
        schemas_data = json.load(f)

    mcp_config = mcp_manager.config.get("mcpServers", {})

    report = []

    for server_name, server_cfg in mcp_config.items():
        if server_name.startswith("_") or server_cfg.get("disabled"):
            continue

        try:
            # Fetch live tools
            live_tools = await asyncio.wait_for(mcp_manager.list_tools(server_name), timeout=30.0)
            live_tool_names = {t.name for t in live_tools}

            # Verify Catalog
            catalog_info = catalog_data.get(server_name, {})
            key_tools = catalog_info.get("key_tools", [])
            missing_key_tools = [kt for kt in key_tools if kt not in live_tool_names]

            # Deep Schema Verification
            schema_issues = []
            for tool in live_tools:
                tool_name = tool.name
                static_schema = schemas_data.get(tool_name)

                if not static_schema:
                    # Report missing schema for explicitly listed key tools
                    if tool_name in key_tools:
                        schema_issues.append(
                            f"Tool {tool_name} is a KEY tool but has NO schema in tool_schemas.json"
                        )
                    continue

                # Check server ownership or alias
                if static_schema.get("server") != server_name and "alias_for" not in static_schema:
                    schema_issues.append(
                        f"Tool {tool_name} assigned to server {static_schema.get('server')} but found in {server_name}"
                    )

                # Skip deep comparison if it's an alias
                if "alias_for" in static_schema:
                    continue

                # Deep Comparison of Args
                live_schema = getattr(tool, "inputSchema", {})
                live_properties = live_schema.get("properties", {})
                live_required = set(live_schema.get("required", []))

                static_required = set(static_schema.get("required", []))
                static_optional = set(static_schema.get("optional", []))
                static_all_args = static_required.union(static_optional)

                # Check for missing required arguments in static schema
                missing_required = live_required - static_required
                if missing_required:
                    schema_issues.append(
                        f"Tool {tool_name}: Missing REQUIRED args in static config: {missing_required}"
                    )

                # Check for extra arguments in static schema (typos or outdated)
                live_all_args = set(live_properties.keys())
                extra_static_args = static_all_args - live_all_args
                if extra_static_args:
                    schema_issues.append(
                        f"Tool {tool_name}: Static config contains EXTRA/INVALID args: {extra_static_args}"
                    )

            # Also check for tools in catalog that don't exist live
            # (already covered by missing_key_tools, but let's be thorough)

            status = "OK"
            if missing_key_tools or schema_issues:
                status = "ISSUES FOUND"

            report.append(
                {
                    "server": server_name,
                    "status": status,
                    "missing_key_tools": missing_key_tools,
                    "schema_issues": schema_issues,
                    "total_live_tools": len(live_tool_names),
                }
            )

            if status == "OK":
                pass
            else:
                if missing_key_tools:
                    pass
                if schema_issues:
                    for _ in schema_issues:
                        pass

        except Exception as e:
            report.append({"server": server_name, "status": "CONNECTION FAILED", "error": str(e)})

    # Summary
    for item in report:
        (
            Colors.GREEN
            if item["status"] == "OK"
            else (Colors.RED if item["status"] == "CONNECTION FAILED" else Colors.YELLOW)
        )


if __name__ == "__main__":
    asyncio.run(verify_integrity())
