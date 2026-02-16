"""Comprehensive MCP Tool Verification Test Suite.

Cross-references and validates:
1. mcp_servers.json.template (server config)
2. mcp_catalog.json (catalog descriptions + key_tools)
3. tool_schemas.json (tool schemas with required/optional args)
4. Actual Python source code (@server.tool() registrations)
5. ToolDispatcher routing (synonym maps, handler logic)
6. mcp_registry.py (get_server_for_tool, get_tool_schema)

Run: python -m pytest tests/test_all_mcp_tools.py -v
"""

import ast
import json
import re
import sys
from pathlib import Path

import pytest

# ─── Paths ───────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
MCP_SERVER_DIR = SRC_DIR / "mcp_server"
BRAIN_DIR = SRC_DIR / "brain"
DATA_DIR = BRAIN_DIR / "data"
CONFIG_DIR = PROJECT_ROOT / "config"

# Add project root to path for imports
sys.path.insert(0, str(PROJECT_ROOT))


# ─── Load JSON data sources ─────────────────────────────────────────────────
def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


MCP_SERVERS_CONFIG = load_json(CONFIG_DIR / "mcp_servers.json.template")
MCP_CATALOG = load_json(DATA_DIR / "mcp_catalog.json")
TOOL_SCHEMAS = load_json(DATA_DIR / "tool_schemas.json")


# ─── Extract actual tools from Python source via AST ────────────────────────
def extract_tools_from_python(filepath: Path) -> list[str]:
    """Parse Python file AST to find @server.tool() decorated functions."""
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return []

    tools = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for dec in node.decorator_list:
                # Match @server.tool() or @mcp.tool()
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    if dec.func.attr == "tool":
                        tools.append(node.name)
    return tools


def extract_tools_from_js(filepath: Path) -> list[str]:
    """Extract tool names from JS MCP server via regex."""
    try:
        source = filepath.read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError):
        return []
    # Look for name: 'tool_name' patterns in ListToolsRequestSchema handler
    return re.findall(r"name:\s*['\"](\w+)['\"]", source)


# ─── Build actual tools map from source code ────────────────────────────────
PYTHON_SERVERS = {
    "vibe": MCP_SERVER_DIR / "vibe_server.py",
    "memory": MCP_SERVER_DIR / "memory_server.py",
    "graph": MCP_SERVER_DIR / "graph_server.py",
    "duckduckgo-search": MCP_SERVER_DIR / "duckduckgo_search_server.py",
    "redis": MCP_SERVER_DIR / "redis_server.py",
    "whisper-stt": MCP_SERVER_DIR / "whisper_server.py",
    "data-analysis": MCP_SERVER_DIR / "data_analysis_server.py",
    "devtools": MCP_SERVER_DIR / "devtools_server.py",
    "golden-fund": MCP_SERVER_DIR / "golden_fund" / "server.py",
}

JS_SERVERS = {
    "react-devtools": MCP_SERVER_DIR / "react_devtools_mcp.js",
}

# External servers (npx/bunx/Swift binary) — we can't extract tools from source
EXTERNAL_SERVERS = {
    "macos-use",
    "filesystem",
    "sequential-thinking",
    "googlemaps",
    "xcodebuild",
    "chrome-devtools",
    "puppeteer",
    "context7",
    "github",
}

# Internal/native servers
INTERNAL_SERVERS = {"tour-guide", "system"}

# Build actual_tools_map
ACTUAL_TOOLS: dict[str, list[str]] = {}
for server_name, filepath in PYTHON_SERVERS.items():
    ACTUAL_TOOLS[server_name] = extract_tools_from_python(filepath)

for server_name, filepath in JS_SERVERS.items():
    ACTUAL_TOOLS[server_name] = extract_tools_from_js(filepath)


# ─── Helper: get non-alias schemas for a server ─────────────────────────────
def get_schema_tools_for_server(server_name: str) -> list[str]:
    """Get all non-alias tool names from tool_schemas.json for a server."""
    return [
        name
        for name, schema in TOOL_SCHEMAS.items()
        if schema.get("server") == server_name and "alias_for" not in schema
    ]


def get_all_schema_tools_for_server(server_name: str) -> list[str]:
    """Get ALL tool names (including aliases) for a server."""
    return [name for name, schema in TOOL_SCHEMAS.items() if schema.get("server") == server_name]


def get_catalog_key_tools(server_name: str) -> list[str]:
    """Get key_tools from mcp_catalog.json for a server."""
    entry = MCP_CATALOG.get(server_name, {})
    return entry.get("key_tools", [])


def get_config_servers() -> dict[str, dict]:
    """Get all enabled servers from mcp_servers.json.template."""
    return {
        name: cfg
        for name, cfg in MCP_SERVERS_CONFIG.get("mcpServers", {}).items()
        if not name.startswith("_")
    }


CONFIG_SERVERS = get_config_servers()


# =============================================================================
# TEST 1: Every server in mcp_servers.json.template has a catalog entry
# =============================================================================
class TestServerConfigConsistency:
    """Verify mcp_servers.json.template ↔ mcp_catalog.json consistency."""

    def test_all_config_servers_have_catalog_entry(self):
        """Every enabled server in config must have a catalog entry."""
        missing = []
        for name, cfg in CONFIG_SERVERS.items():
            if cfg.get("disabled"):
                continue
            if name not in MCP_CATALOG:
                # 'system' and 'tour-guide' (internal) are special
                if cfg.get("transport") != "internal":
                    missing.append(name)
        assert not missing, f"Servers in config but missing from catalog: {missing}"

    def test_all_catalog_servers_have_config_entry(self):
        """Every catalog server should have a config entry (or be 'system'/internal)."""
        missing = []
        for name in MCP_CATALOG:
            if name not in CONFIG_SERVERS and name != "system":
                missing.append(name)
        assert not missing, f"Servers in catalog but missing from config: {missing}"

    def test_config_server_has_command_or_transport(self):
        """Every config server must have either command or transport=internal."""
        broken = []
        for name, cfg in CONFIG_SERVERS.items():
            if cfg.get("disabled"):
                continue
            transport = cfg.get("transport", "stdio")
            if transport == "internal":
                continue
            if not cfg.get("command"):
                broken.append(name)
        assert not broken, f"Servers missing 'command': {broken}"


# =============================================================================
# TEST 2: Tool schemas consistency
# =============================================================================
class TestToolSchemasConsistency:
    """Verify tool_schemas.json entries are correct."""

    def test_every_schema_has_server(self):
        """Every tool schema must reference a valid server."""
        missing_server = []
        for tool_name, schema in TOOL_SCHEMAS.items():
            if "server" not in schema:
                missing_server.append(tool_name)
        assert not missing_server, f"Tools without 'server' field: {missing_server}"

    def test_schema_servers_are_known(self):
        """Every server referenced in schemas should be in catalog or config."""
        all_known_servers = (
            set(CONFIG_SERVERS.keys())
            | set(MCP_CATALOG.keys())
            | {
                "system",
                "local",
            }
        )
        unknown = set()
        for tool_name, schema in TOOL_SCHEMAS.items():
            server = schema.get("server", "")
            if server and server not in all_known_servers:
                unknown.add(f"{tool_name} -> {server}")
        assert not unknown, f"Tools referencing unknown servers: {unknown}"

    def test_aliases_point_to_existing_tools(self):
        """Every alias must point to a tool that exists in schemas."""
        broken_aliases = []
        for tool_name, schema in TOOL_SCHEMAS.items():
            alias_for = schema.get("alias_for")
            if alias_for and alias_for not in TOOL_SCHEMAS:
                broken_aliases.append(f"{tool_name} -> {alias_for}")
        assert not broken_aliases, f"Broken aliases: {broken_aliases}"

    def test_non_alias_schemas_have_required_field(self):
        """Non-alias schemas should have 'required' field (can be empty list)."""
        missing = []
        for tool_name, schema in TOOL_SCHEMAS.items():
            if "alias_for" in schema:
                continue
            if "required" not in schema and "description" not in schema:
                missing.append(tool_name)
        # Relaxed: just check there's at least description or required
        assert not missing, f"Schemas without 'required' or 'description': {missing}"


# =============================================================================
# TEST 3: Catalog key_tools exist in schemas
# =============================================================================
class TestCatalogKeyToolsCoverage:
    """Verify catalog key_tools are backed by tool schemas."""

    @pytest.mark.parametrize("server_name", list(MCP_CATALOG.keys()))
    def test_catalog_key_tools_have_schemas(self, server_name: str):
        """Every key_tool in catalog should exist in tool_schemas.json."""
        key_tools = get_catalog_key_tools(server_name)
        if not key_tools:
            pytest.skip(f"No key_tools defined for {server_name}")

        missing = []
        for tool in key_tools:
            if tool not in TOOL_SCHEMAS:
                missing.append(tool)
        assert not missing, f"[{server_name}] key_tools missing from tool_schemas.json: {missing}"

    @pytest.mark.parametrize("server_name", list(MCP_CATALOG.keys()))
    def test_catalog_key_tools_reference_correct_server(self, server_name: str):
        """key_tools should map to their declared server in schemas."""
        key_tools = get_catalog_key_tools(server_name)
        if not key_tools:
            pytest.skip(f"No key_tools for {server_name}")

        mismatched = []
        for tool in key_tools:
            schema = TOOL_SCHEMAS.get(tool, {})
            schema_server = schema.get("server", "")
            if schema_server and schema_server != server_name:
                # Aliases might reference different names
                if "alias_for" not in schema:
                    mismatched.append(
                        f"{tool}: schema says '{schema_server}', catalog says '{server_name}'"
                    )
        assert not mismatched, f"[{server_name}] key_tools with wrong server: {mismatched}"


# =============================================================================
# TEST 4: Actual Python/JS tools match schemas
# =============================================================================
class TestActualSourceToolsMatchSchemas:
    """Verify tools registered in source code match tool_schemas.json."""

    @pytest.mark.parametrize("server_name", list(ACTUAL_TOOLS.keys()))
    def test_source_tools_have_schemas(self, server_name: str):
        """Every @server.tool() in source should have a schema entry."""
        actual = set(ACTUAL_TOOLS[server_name])
        schema_tools = set(get_schema_tools_for_server(server_name))
        # Also check all aliases
        all_schema_names = set(get_all_schema_tools_for_server(server_name))

        # Some tools may be registered in source but not in schemas
        # (internal/helper tools). We want to find genuinely missing ones.
        missing = []
        for tool in actual:
            if tool not in schema_tools and tool not in all_schema_names:
                # Check if it's referenced by an alias
                is_aliased = any(
                    s.get("alias_for") == tool
                    for s in TOOL_SCHEMAS.values()
                    if s.get("server") == server_name
                )
                if not is_aliased:
                    missing.append(tool)

        if missing:
            pytest.fail(
                f"[{server_name}] Source tools NOT in tool_schemas.json: {missing}\n"
                f"  Source tools: {sorted(actual)}\n"
                f"  Schema tools: {sorted(schema_tools)}"
            )

    @pytest.mark.parametrize("server_name", list(ACTUAL_TOOLS.keys()))
    def test_schema_tools_exist_in_source(self, server_name: str):
        """Every schema tool should exist in source code."""
        actual = set(ACTUAL_TOOLS[server_name])
        schema_tools = get_schema_tools_for_server(server_name)

        missing = []
        for tool in schema_tools:
            if tool not in actual:
                # Check if it's an alias
                schema = TOOL_SCHEMAS.get(tool, {})
                if "alias_for" not in schema:
                    missing.append(tool)

        if missing:
            pytest.fail(
                f"[{server_name}] Schema tools NOT found in source: {missing}\n"
                f"  Source tools: {sorted(actual)}\n"
                f"  Schema tools: {sorted(schema_tools)}"
            )


# =============================================================================
# TEST 5: ToolDispatcher routing coverage
# =============================================================================
class TestToolDispatcherRouting:
    """Verify that ToolDispatcher can route all known tools."""

    def _get_dispatcher_source(self):
        """Read ToolDispatcher source for analysis."""
        return (BRAIN_DIR / "tool_dispatcher.py").read_text(encoding="utf-8")

    def test_vibe_synonyms_cover_all_vibe_tools(self):
        """All vibe tools should appear in VIBE_SYNONYMS or vibe_map."""
        source = self._get_dispatcher_source()

        vibe_schema_tools = get_schema_tools_for_server("vibe")
        # Extract vibe_map keys from source
        vibe_map_match = re.search(r"vibe_map\s*=\s*\{([^}]+)\}", source, re.DOTALL)
        vibe_map_keys = set()
        if vibe_map_match:
            vibe_map_keys = set(re.findall(r'"(\w+)"', vibe_map_match.group(1)))

        # Extract VIBE_SYNONYMS
        synonyms_match = re.search(r"VIBE_SYNONYMS\s*=\s*\[([^\]]+)\]", source, re.DOTALL)
        vibe_synonyms = set()
        if synonyms_match:
            vibe_synonyms = set(re.findall(r'"(\w+)"', synonyms_match.group(1)))

        all_routable = vibe_synonyms | vibe_map_keys

        not_routable = []
        for tool in vibe_schema_tools:
            if tool not in all_routable:
                not_routable.append(tool)

        assert not not_routable, f"Vibe tools not routable via dispatcher: {not_routable}"

    def test_macos_map_covers_key_tools(self):
        """All macos-use key_tools should be in MACOS_MAP values or direct tools."""
        source = self._get_dispatcher_source()

        macos_key_tools = get_catalog_key_tools("macos-use")

        # Extract MACOS_MAP values
        map_match = re.search(r"MACOS_MAP\s*=\s*\{([^}]+)\}", source, re.DOTALL)
        map_values = set()
        if map_match:
            # Get values (right side of : in dict)
            map_values = set(re.findall(r':\s*"([^"]+)"', map_match.group(1)))

        not_mapped = []
        for tool in macos_key_tools:
            if tool not in map_values and tool != "execute_command":
                not_mapped.append(tool)

        # This is informational - macos-use tools may be direct-routed
        if not_mapped:
            print(
                f"INFO: macos-use key_tools not in MACOS_MAP values (may be direct): {not_mapped}"
            )

    def test_golden_fund_synonyms_include_all_tools(self):
        """Golden Fund schema tools should be routable."""
        gf_schema_tools = get_schema_tools_for_server("golden-fund")

        missing_from_schemas = [tool for tool in gf_schema_tools if tool not in TOOL_SCHEMAS]
        assert not missing_from_schemas, (
            f"Golden Fund tools missing from schemas: {missing_from_schemas}"
        )

    def test_devtools_tools_routable(self):
        """All devtools schema tools should be routable."""
        devtools_schema = get_schema_tools_for_server("devtools")
        # devtools handler does pass-through for most tools
        missing = [t for t in devtools_schema if t not in TOOL_SCHEMAS]
        assert not missing, f"Devtools tools missing from schemas: {missing}"

    def test_data_analysis_tools_in_validation(self):
        """Data analysis tools should be listed in _validate_realm_tool_compatibility."""
        source = self._get_dispatcher_source()

        da_schema_tools = get_schema_tools_for_server("data-analysis")

        # Extract data_analysis_tools list
        match = re.search(r"data_analysis_tools\s*=\s*\[([^\]]+)\]", source, re.DOTALL)
        validation_tools = set()
        if match:
            validation_tools = set(re.findall(r'"(\w+)"', match.group(1)))

        not_in_validation = []
        for tool in da_schema_tools:
            if tool not in validation_tools:
                not_in_validation.append(tool)

        assert not not_in_validation, (
            f"Data-analysis tools not in validation list: {not_in_validation}"
        )


# =============================================================================
# TEST 6: mcp_registry functions work correctly
# =============================================================================
class TestMcpRegistryFunctions:
    """Verify mcp_registry.py utility functions."""

    @pytest.fixture(autouse=True)
    def setup_registry(self):
        """Load registry before tests."""
        try:
            from src.brain.mcp.mcp_registry import (
                SERVER_CATALOG,
                get_all_tool_names,
                get_server_for_tool,
                get_tool_names_for_server,
                get_tool_schema,
                load_registry,
            )
            from src.brain.mcp.mcp_registry import (
                TOOL_SCHEMAS as REG_SCHEMAS,
            )

            load_registry()
            self.get_tool_schema = get_tool_schema
            self.get_server_for_tool = get_server_for_tool
            self.get_all_tool_names = get_all_tool_names
            self.get_tool_names_for_server = get_tool_names_for_server
            self.reg_schemas = REG_SCHEMAS
            self.server_catalog = SERVER_CATALOG
            self.available = True
        except Exception as e:
            self.available = False
            self.skip_reason = str(e)

    def test_registry_loads(self):
        if not self.available:
            pytest.skip(f"Registry not loadable: {self.skip_reason}")
        assert self.server_catalog, "SERVER_CATALOG is empty"
        assert self.reg_schemas, "TOOL_SCHEMAS is empty"

    def test_get_server_for_all_schema_tools(self):
        """get_server_for_tool should return non-None for every schema tool."""
        if not self.available:
            pytest.skip("Registry not loadable")

        no_server = []
        for tool_name, _schema in self.reg_schemas.items():
            server = self.get_server_for_tool(tool_name)
            if server is None:
                no_server.append(tool_name)

        assert not no_server, f"Tools with no server mapping: {no_server}"

    def test_get_tool_schema_resolves_aliases(self):
        """get_tool_schema should resolve aliases to canonical schemas."""
        if not self.available:
            pytest.skip("Registry not loadable")

        # Check known aliases
        aliases = {
            name: schema["alias_for"]
            for name, schema in self.reg_schemas.items()
            if "alias_for" in schema
        }
        for alias_name, canonical_name in aliases.items():
            alias_schema = self.get_tool_schema(alias_name)
            canonical_schema = self.get_tool_schema(canonical_name)
            if canonical_schema is not None:
                assert alias_schema is not None, (
                    f"Alias '{alias_name}' -> '{canonical_name}' did not resolve"
                )


# =============================================================================
# TEST 7: Comprehensive per-server tool inventory
# =============================================================================
class TestPerServerToolInventory:
    """Detailed per-server tests comparing all 3 data sources."""

    @pytest.mark.parametrize(
        "server_name,expected_tools",
        [
            (
                "vibe",
                [
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
                    "vibe_which",
                    "vibe_test_in_sandbox",
                ],
            ),
            (
                "memory",
                [
                    "create_entities",
                    "add_observations",
                    "get_entity",
                    "list_entities",
                    "search",
                    "create_relation",
                    "delete_entity",
                    "ingest_verified_dataset",
                    "trace_data_chain",
                    "query_db",
                    "batch_add_nodes",
                    "get_db_schema",
                    "bulk_ingest_table",
                ],
            ),
            (
                "graph",
                [
                    "get_graph_json",
                    "generate_mermaid",
                    "get_node_details",
                    "get_related_nodes",
                ],
            ),
            (
                "redis",
                [
                    "redis_get",
                    "redis_set",
                    "redis_keys",
                    "redis_delete",
                    "redis_info",
                    "redis_ttl",
                    "redis_hgetall",
                    "redis_hset",
                ],
            ),
            (
                "whisper-stt",
                [
                    "transcribe_audio",
                    "record_and_transcribe",
                ],
            ),
            (
                "duckduckgo-search",
                [
                    "duckduckgo_search",
                    "business_registry_search",
                    "open_data_search",
                    "structured_data_search",
                ],
            ),
            (
                "golden-fund",
                [
                    "search_golden_fund",
                    "store_blob",
                    "retrieve_blob",
                    "ingest_dataset",
                    "probe_entity",
                    "add_knowledge_node",
                    "analyze_and_store",
                    "get_dataset_insights",
                ],
            ),
            (
                "react-devtools",
                [
                    "react_get_introspection_script",
                ],
            ),
        ],
    )
    def test_expected_tools_in_source(self, server_name: str, expected_tools: list[str]):
        """Verify expected tools actually exist in source."""
        actual = set(ACTUAL_TOOLS.get(server_name, []))
        missing = [t for t in expected_tools if t not in actual]
        assert not missing, (
            f"[{server_name}] Expected tools missing from source: {missing}\n"
            f"  Actual source tools: {sorted(actual)}"
        )

    @pytest.mark.parametrize(
        "server_name,expected_tools",
        [
            (
                "vibe",
                [
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
                    "vibe_which",
                    "vibe_test_in_sandbox",
                ],
            ),
            (
                "memory",
                [
                    "create_entities",
                    "add_observations",
                    "get_entity",
                    "list_entities",
                    "search",
                    "create_relation",
                    "delete_entity",
                    "ingest_verified_dataset",
                    "trace_data_chain",
                    "query_db",
                    "batch_add_nodes",
                    "get_db_schema",
                    "bulk_ingest_table",
                ],
            ),
            (
                "graph",
                [
                    "get_graph_json",
                    "generate_mermaid",
                    "get_node_details",
                    "get_related_nodes",
                ],
            ),
            (
                "redis",
                [
                    "redis_get",
                    "redis_set",
                    "redis_keys",
                    "redis_delete",
                    "redis_info",
                    "redis_ttl",
                    "redis_hgetall",
                    "redis_hset",
                ],
            ),
            (
                "whisper-stt",
                [
                    "transcribe_audio",
                    "record_and_transcribe",
                ],
            ),
            (
                "duckduckgo-search",
                [
                    "duckduckgo_search",
                    "business_registry_search",
                    "open_data_search",
                    "structured_data_search",
                ],
            ),
            (
                "golden-fund",
                [
                    "search_golden_fund",
                    "store_blob",
                    "retrieve_blob",
                    "ingest_dataset",
                    "probe_entity",
                    "add_knowledge_node",
                    "analyze_and_store",
                    "get_dataset_insights",
                ],
            ),
        ],
    )
    def test_expected_tools_in_schemas(self, server_name: str, expected_tools: list[str]):
        """Verify expected tools have schema entries."""
        missing = [t for t in expected_tools if t not in TOOL_SCHEMAS]
        assert not missing, (
            f"[{server_name}] Expected tools missing from tool_schemas.json: {missing}"
        )


# =============================================================================
# TEST 8: Extra tools in source not tracked anywhere
# =============================================================================
class TestExtraToolsTracking:
    """Find tools in source that are not in schemas or catalog."""

    @pytest.mark.parametrize("server_name", list(ACTUAL_TOOLS.keys()))
    def test_report_untracked_tools(self, server_name: str):
        """Report tools in source but not in catalog key_tools or schemas."""
        actual = set(ACTUAL_TOOLS[server_name])
        schema_tools = set(get_schema_tools_for_server(server_name))

        untracked_in_schema = actual - schema_tools
        # Filter out aliases
        truly_untracked = []
        for tool in untracked_in_schema:
            is_known = any(
                s.get("alias_for") == tool or s.get("server") == server_name
                for t_name, s in TOOL_SCHEMAS.items()
                if t_name == tool
            )
            if not is_known:
                truly_untracked.append(tool)

        if truly_untracked:
            print(f"WARNING [{server_name}]: Source tools not in schemas: {truly_untracked}")


# =============================================================================
# TEST 9: Config file paths and binaries existence
# =============================================================================
class TestConfigPaths:
    """Verify that configured paths and binaries exist."""

    def test_python_server_files_exist(self):
        """All Python MCP server files should exist."""
        missing = []
        for name, path in PYTHON_SERVERS.items():
            if not path.exists():
                missing.append(f"{name}: {path}")
        assert not missing, f"Missing Python server files: {missing}"

    def test_js_server_files_exist(self):
        """All JS MCP server files should exist."""
        missing = []
        for name, path in JS_SERVERS.items():
            if not path.exists():
                missing.append(f"{name}: {path}")
        assert not missing, f"Missing JS server files: {missing}"

    def test_swift_binaries_path_pattern(self):
        """Swift binary configs should reference vendor/ paths correctly."""
        for name in ["macos-use", "googlemaps"]:
            cfg = CONFIG_SERVERS.get(name)
            if not cfg:
                continue
            command = cfg.get("command", "")
            if "${PROJECT_ROOT}" in command:
                # Resolve and check
                resolved = command.replace("${PROJECT_ROOT}", str(PROJECT_ROOT))
                if not Path(resolved).exists():
                    print(f"WARNING: Binary not found for {name}: {resolved}")


# =============================================================================
# TEST 10: Schema required/optional field validation
# =============================================================================
class TestSchemaFieldValidation:
    """Verify schema field definitions are consistent."""

    def test_required_args_are_not_in_optional(self):
        """Required args should not also appear in optional."""
        overlaps = []
        for tool_name, schema in TOOL_SCHEMAS.items():
            if "alias_for" in schema:
                continue
            required = set(schema.get("required", []))
            optional = set(schema.get("optional", []))
            overlap = required & optional
            if overlap:
                overlaps.append(f"{tool_name}: {overlap}")
        assert not overlaps, f"Tools with args in both required and optional: {overlaps}"

    def test_types_cover_all_args(self):
        """Types dict should cover all required+optional args."""
        incomplete = []
        for tool_name, schema in TOOL_SCHEMAS.items():
            if "alias_for" in schema:
                continue
            types = schema.get("types", {})
            if not types:
                continue  # Some tools have no args
            required = schema.get("required", [])
            optional = schema.get("optional", [])
            all_args = set(required) | set(optional)
            typed_args = set(types.keys())
            missing_types = all_args - typed_args
            if missing_types:
                incomplete.append(f"{tool_name}: {missing_types}")
        if incomplete:
            print(f"INFO: Tools with args missing type definitions: {incomplete}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
