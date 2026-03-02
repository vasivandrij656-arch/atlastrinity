# System Map Protocol

**Version:** 1.0.0
**Date:** 2026-02-06
**Owner:** All Agents (Atlas, Tetyana, Grisha)
**Purpose:** Single source of truth for ALL system paths, tools, databases, logs, and testing methods.

> **CRITICAL**: This document is the complete system map. When you need to find a file, log, database, tool, or script — refer here first.

---

## 1. REPOSITORY STRUCTURE (`${PROJECT_ROOT}`)

```
atlastrinity/
├── src/                          # Source code
│   ├── brain/                    # Core Brain logic (Python)
│   │   ├── agents/               # Agent implementations
│   │   ├── data/                 # Data files for brain
│   │   │   ├── mcp_catalog.json       # MCP server catalog (descriptions, key_tools)
│   │   │   ├── tool_schemas.json      # All tool schemas (input params, required fields)
│   │   │   ├── user_constraints.txt   # User constraints
│   │   │   ├── protocols/             # Agent operational protocols (THIS directory)
│   │   │   └── architecture_diagrams/ # Auto-generated diagrams
│   │   ├── db/                   # Database models
│   │   ├── prompts/              # LLM prompt templates
│   │   ├── scripts/              # Brain-internal scripts
│   │   ├── tools/                # Internal tool definitions
│   │   ├── utils/                # Utility modules (security, etc.)
│   │   ├── voice/                # TTS/STT integration
│   │   ├── navigation/           # Navigation logic
│   │   ├── services/             # Service layer
│   │   ├── config.py             # PATH CONSTANTS (LOG_DIR, MEMORY_DIR, CONFIG_ROOT, etc.)
│   │   ├── config_loader.py      # SystemConfig singleton (loads config.yaml)
│   │   ├── config_validator.py   # Config validation
│   │   ├── orchestrator.py       # Main task orchestrator (Atlas→Tetyana→Grisha)
│   │   ├── tool_dispatcher.py    # Tool routing & execution
│   │   ├── mcp_manager.py        # MCP server lifecycle management
│   │   ├── mcp_registry.py       # Tool schemas & server catalog loader
│   │   ├── mcp_health_dashboard.py # Health check dashboard
│   │   ├── mcp_preflight.py      # Preflight checks before MCP calls
│   │   ├── behavior_engine.py    # Config-driven behavior (replaces hardcoded rules)
│   │   ├── server.py             # FastAPI Brain server
│   │   ├── state_manager.py      # Redis state management
│   │   ├── memory.py             # Long-term memory (SQLite + ChromaDB)
│   │   ├── knowledge_graph.py    # Knowledge graph operations
│   │   ├── logger.py             # Logging setup (writes to LOG_DIR)
│   │   ├── watchdog.py           # Process watchdog
│   │   ├── monitoring.py         # System monitoring
│   │   ├── system_healing.py     # Self-healing logic
│   │   ├── parallel_healing.py   # Parallel healing orchestration
│   │   └── error_router.py       # Error classification & routing
│   │
│   ├── mcp_server/               # MCP Server implementations (Python)
│   │   ├── vibe_server.py             # Vibe CLI (18 tools) - Mistral AI coding assistant
│   │   ├── memory_server.py           # Memory/Knowledge Graph (9 tools)
│   │   ├── graph_server.py            # Graph visualization (4 tools)
│   │   ├── devtools_server.py         # DevTools: linters, inspector, sandbox (25+ tools)
│   │   ├── duckduckgo_search_server.py # Web search (DuckDuckGo)
│   │   ├── data_analysis_server.py    # Pandas data analysis (10 tools)
│   │   ├── whisper_server.py          # Speech-to-Text (Whisper)
│   │   ├── redis_server.py            # Redis observability (5 tools)
│   │   ├── golden_fund/               # Golden Fund knowledge base
│   │   │   └── server.py              # Golden Fund server (8 tools)
│   │   ├── vibe_config.py             # Vibe configuration management
│   │   ├── config_loader.py           # MCP-specific config loader
│   │   ├── context_check.py           # Logic test runner
│   │   ├── diagram_generator.py       # Architecture diagram generator
│   │   ├── git_manager.py             # Git operations helper
│   │   ├── project_analyzer.py        # Universal project analyzer
│   │   ├── trace_analyzer.py          # Log trace analyzer
│   │   ├── react_devtools_mcp.js      # React DevTools (Node.js)
│   │   └── tool_result_interface.py   # Tool result interface
│   │
│   ├── renderer/                 # Electron Frontend (React/TypeScript)
│   │   ├── components/           # React components
│   │   ├── styles/               # CSS styles
│   │   ├── App.tsx               # Main React app
│   │   ├── index.html            # HTML entry
│   │   └── main.tsx              # React entry point
│   │
│   └── main/                     # Electron Main Process (TypeScript)
│       ├── main.ts               # Electron main
│       └── permissions.ts        # macOS permissions
│
├── vendor/                       # Third-party MCP binaries
│   ├── mcp-server-macos-use/     # macOS Universal Commander (63 tools) [bridged via XcodeBuildMCP]
│   │   └── mcp-server-macos-use  # Swift binary (accessed through xcodebuild bridge)
│   ├── mcp-server-googlemaps/    # Google Maps MCP (11 tools) [bridged via XcodeBuildMCP]
│   │   └── .build/release/mcp-server-googlemaps  # Swift binary (accessed through xcodebuild bridge)
│   └── XcodeBuildMCP/            # Unified MCP Hub (144+ tools: 70 native + 63 macOS + 11 Maps)
│
├── scripts/                      # Utility Scripts (115+)
│   ├── check_mcp_health.py       # MCP health check (CLI: --json --tools --all)
│   ├── check_mcp_preflight.py    # MCP preflight validation
│   ├── mcp_sandbox.py            # MCP sandbox testing (--server X --all --chain N --autofix)
│   ├── mcp_self_analyze.py       # MCP self-analysis
│   ├── validate_mcp_servers.py   # MCP server validation after setup
│   ├── verify_mcp_integrity.py   # MCP integrity verification
│   ├── test_mcp_integration.py   # MCP integration tests (all servers)
│   ├── test_mcp_call_manual.py   # Manual MCP tool call tester
│   ├── test_mcp_connectivity.py  # MCP connectivity test
│   ├── test_vibe_mcp_tools.py    # Vibe MCP tool tests
│   ├── test_vibe_deep.py         # Deep Vibe tests
│   ├── test_vibe_full.py         # Full Vibe test suite
│   ├── test_all_macos_tools.py   # macOS-use tool tests
│   ├── test_native.py            # Native tool tests
│   ├── system_health_check.py    # Full system health check
│   ├── diagnose_system.py        # System diagnostics
│   ├── verify_environment.py     # Environment verification
│   ├── verify_vibe_tools.py      # Vibe tools verification
│   ├── verify_macos_use.py       # macOS-use verification
│   ├── setup_dev.py              # Development setup (full)
│   ├── fresh_install.sh          # Fresh installation script
│   ├── restart_brain.sh          # Brain restart
│   ├── clean-cache.sh            # Cache cleanup
│   ├── clean_full.sh             # Full cleanup
│   ├── db_report.py              # Database report
│   ├── debug_db.py               # Database debugging
│   ├── verify_db_tables.py       # Database table verification
│   ├── sync_and_validate_configs.py  # Config sync/validation
│   ├── sync_config_templates.js  # Template sync (Node.js)
│   └── ... (100+ more utility scripts)
│
├── config/                       # Configuration Templates
│   ├── config.yaml.template      # Main config template
│   ├── behavior_config.yaml.template  # Behavior rules template
│   ├── mcp_servers.json.template # MCP servers config template (MASTER)
│   ├── vibe_config.toml.template # Vibe config template
│   ├── prometheus.yml.template   # Prometheus metrics template
│   └── vibe/agents/              # Agent-specific vibe configs
│
├── tests/                        # Test Suite (pytest)
│   ├── conftest.py               # Pytest fixtures
│   ├── mock_config/              # Mock configurations
│   ├── logic_tests/              # Logic test scenarios (YAML)
│   └── test_*.py                 # 60+ test files
│
├── docs/                         # Documentation
│   ├── SYSTEM_OVERVIEW.md        # Technical architecture
│   ├── MCP_SERVERS.md            # MCP server docs
│   └── ... (30+ docs)
│
├── .agent/                       # Agent Documentation
│   ├── docs/                     # Architecture docs, diagrams
│   ├── plans/                    # Task plans
│   ├── skills/                   # Agent skills (MCP monitoring)
│   └── workflows/                # Agent workflows (git, diagrams, etc.)
│
├── .github/workflows/            # CI/CD (8 workflows)
├── build/                        # Build assets (icons)
├── providers/                    # Provider implementations
│   └── copilot.py                # Copilot proxy provider
│
├── pyproject.toml                # Python project config (ruff, pyright, etc.)
├── pyrightconfig.json            # Pyright type checking config
├── pyrefly.toml                  # Pyrefly config
├── biome.json                    # Biome (JS/TS) linter config
├── eslint.config.mjs             # ESLint config
├── knip.json                     # Knip (unused code) config
├── lefthook.yml                  # Git hooks (13 parallel lint checks)
├── package.json                  # Node.js deps + lint:all script
├── tsconfig.json                 # TypeScript config (renderer)
├── tsconfig.main.json            # TypeScript config (main process)
├── vite.config.ts                # Vite bundler config
├── setup.cfg                     # Python setup config
├── pytest.ini                    # Pytest config
├── requirements.txt              # Python dependencies
├── requirements-dev.txt          # Dev dependencies
├── docker-compose.yml            # Docker config
├── .env.example                  # Environment template
├── .cursorrules                  # Cursor IDE rules
├── start_brain.sh                # Brain startup script
├── README.md                     # Project README
└── ...
```

---

## 2. GLOBAL PATHS (`~/.config/atlastrinity/`)

All runtime data lives OUTSIDE the repository in `~/.config/atlastrinity/`:

| Path                                            | Description                                        | Type      |
| ----------------------------------------------- | -------------------------------------------------- | --------- |
| `~/.config/atlastrinity/.env`                   | API keys, tokens, secrets                          | Secrets   |
| `~/.config/atlastrinity/config.yaml`            | Main system config (agents, models, MCP)           | Config    |
| `~/.config/atlastrinity/behavior_config.yaml`   | Agent behavior rules (68KB)                        | Config    |
| `~/.config/atlastrinity/vibe_config.toml`       | Vibe provider & model config                       | Config    |
| `~/.config/atlastrinity/prometheus.yml`         | Prometheus metrics config                          | Config    |
| `~/.config/atlastrinity/atlastrinity.db`        | **Main SQLite database**                           | Database  |
| `~/.config/atlastrinity/data/trinity.db`        | Trinity data DB                                    | Database  |
| `~/.config/atlastrinity/data/monitoring.db`     | Monitoring metrics DB                              | Database  |
| `~/.config/atlastrinity/data/golden_fund/`      | Golden Fund knowledge data                         | Database  |
| `~/.config/atlastrinity/data/search/`           | Search index data                                  | Database  |
| `~/.config/atlastrinity/logs/brain.log`         | **Main Brain log** (rotated, 10MB max, 5 backups)  | Logs      |
| `~/.config/atlastrinity/mcp/config.json`        | **Active MCP server configuration** (runtime copy) | Config    |
| `~/.config/atlastrinity/memory/`                | Long-term memory storage (ChromaDB)                | Storage   |
| `~/.config/atlastrinity/screenshots/`           | Screenshots from Vision/OCR                        | Storage   |
| `~/.config/atlastrinity/workspace/`             | Agent workspace (777 permissions)                  | Workspace |
| `~/.config/atlastrinity/vibe_workspace/`        | Vibe coding workspace (777 permissions)            | Workspace |
| `~/.config/atlastrinity/vibe/`                  | Vibe session data                                  | Storage   |
| `~/.config/atlastrinity/cache/`                 | General cache (XDG_CACHE_HOME)                     | Cache     |
| `~/.config/atlastrinity/models/tts/`            | TTS voice models                                   | Models    |
| `~/.config/atlastrinity/models/faster-whisper/` | Whisper STT models                                 | Models    |
| `~/.config/atlastrinity/models/stanza/`         | NLP Stanza models                                  | Models    |
| `~/.config/atlastrinity/models/nltk/`           | NLTK data                                          | Models    |
| `~/.config/atlastrinity/models/huggingface/`    | HuggingFace models (HF_HOME)                       | Models    |

### Python Constants (from `src/brain/config.py`):

```python
CONFIG_ROOT  = Path.home() / ".config" / "atlastrinity"
LOG_DIR      = CONFIG_ROOT / "logs"
MEMORY_DIR   = CONFIG_ROOT / "memory"
SCREENSHOTS_DIR = CONFIG_ROOT / "screenshots"
MCP_DIR      = CONFIG_ROOT / "mcp"
WORKSPACE_DIR = CONFIG_ROOT / "workspace"
VIBE_WORKSPACE = CONFIG_ROOT / "vibe_workspace"
```

---

## 3. MCP SERVERS — COMPLETE REGISTRY

### Tier 1 — Core (Always loaded)

| Server                | Transport | Command                                                 | Source        | Tools                                               |
| --------------------- | --------- | ------------------------------------------------------- | ------------- | --------------------------------------------------- |
| `xcodebuild`          | stdio     | `node vendor/XcodeBuildMCP/dist/index.js mcp`           | Local Node.js | 144+ (70 native + 63 macOS bridge + 11 Maps bridge) |
| `filesystem`          | stdio     | `npx @modelcontextprotocol/server-filesystem`           | npm           | ~10                                                 |
| `sequential-thinking` | stdio     | `bunx @modelcontextprotocol/server-sequential-thinking` | npm           | 1                                                   |

### Tier 2 — High Priority (Loaded at startup)

| Server              | Transport | Command                                              | Source       | Tools |
| ------------------- | --------- | ---------------------------------------------------- | ------------ | ----- |
| `vibe`              | stdio     | `python3 -m src.mcp_server.vibe_server`              | Local Python | 18    |
| `memory`            | stdio     | `python3 -m src.mcp_server.memory_server`            | Local Python | 9     |
| `graph`             | stdio     | `python3 -m src.mcp_server.graph_server`             | Local Python | 4     |
| `devtools`          | stdio     | `python3 -m src.mcp_server.devtools_server`          | Local Python | 25+   |
| `duckduckgo-search` | stdio     | `python3 -m src.mcp_server.duckduckgo_search_server` | Local Python | ~5    |
| `golden-fund`       | stdio     | `python3 -m src.mcp_server.golden_fund.server`       | Local Python | 8     |
| `whisper-stt`       | stdio     | `python3 -m src.mcp_server.whisper_server`           | Local Python | ~3    |
| `github`            | stdio     | `npx @modelcontextprotocol/server-github`            | npm          | ~20   |
| `redis`             | stdio     | `python3 -m src.mcp_server.redis_server`             | Local Python | 5     |
| `data-analysis`     | stdio     | `python3 -m src.mcp_server.data_analysis_server`     | Local Python | 10    |
| `tour-guide`        | internal  | Native Python (ToolDispatcher)                       | Internal     | 6     |

---

## 4. LINTER & CODE QUALITY TOOLS

All available via `devtools` MCP server or `npm run lint:all`:

| Tool               | Language    | Config File                           | DevTools Function             |
| ------------------ | ----------- | ------------------------------------- | ----------------------------- |
| **Ruff**           | Python      | `pyproject.toml` (25 rule sets)       | `devtools_lint_python`        |
| **Pyright**        | Python      | `pyrightconfig.json`                  | `devtools_check_types_python` |
| **Pyrefly**        | Python      | `pyrefly.toml`                        | `devtools_check_integrity`    |
| **Bandit**         | Python      | `pyproject.toml`                      | `devtools_check_security`     |
| **Vulture**        | Python      | `vulture_whitelist.py`                | `devtools_find_dead_code`     |
| **Xenon**          | Python      | (inline args)                         | `devtools_check_complexity`   |
| **Biome**          | JS/TS       | `biome.json`                          | via `npm run lint:all`        |
| **OxLint**         | JS/TS       | (inline)                              | `devtools_lint_js`            |
| **ESLint**         | JS/TS       | `eslint.config.mjs`                   | `devtools_lint_js`            |
| **TypeScript**     | TS          | `tsconfig.json`, `tsconfig.main.json` | `devtools_check_types_ts`     |
| **Knip**           | JS/TS       | `knip.json`                           | `devtools_find_dead_code`     |
| **Safety**         | Python deps | `.safety-policy.yml`                  | `devtools_check_security`     |
| **detect-secrets** | All         | `.secrets.baseline`                   | `devtools_check_security`     |
| **npm audit**      | JS deps     | `package.json`                        | `devtools_check_security`     |
| **Lefthook**       | Git hooks   | `lefthook.yml`                        | Runs 13 checks in parallel    |

---

## 5. TESTING MCP SERVERS NATIVELY

### Method 1: Health Check (Quick — connection test)

```bash
# CLI
python scripts/check_mcp_health.py --json --tools

# Via devtools MCP tool
devtools_check_mcp_health()
```

### Method 2: MCP Inspector CLI (Deep — per-tool test)

```bash
# List tools
npx @modelcontextprotocol/inspector --cli <server_command> --method tools/list

# Call specific tool
npx @modelcontextprotocol/inspector --cli <server_command> --method tools/call --tool-name <name> --tool-arg key=value
```

### Method 3: Sandbox Testing (Full — with LLM scenarios)

```bash
# Test single server
python scripts/mcp_sandbox.py --server filesystem --full

# Test all servers
python scripts/mcp_sandbox.py --all --json

# With auto-fix
python scripts/mcp_sandbox.py --all --autofix
```

---

## 6. LOG ANALYSIS

### Log Locations:

- **Brain log**: `~/.config/atlastrinity/logs/brain.log` (main, rotated)
- **Turbo daemon**: `${PROJECT_ROOT}/.turbo/daemon/` (build logs)

### Log Analysis Tools:

- `devtools_analyze_trace(log_path)` — Detect loops, inefficiencies, hallucinations
- `scripts/db_report.py` — Database state report
- `scripts/debug_db.py` — Database debugging

---

## 7. DATABASE LOCATIONS

| Database      | Path                                        | Engine             | Purpose               |
| ------------- | ------------------------------------------- | ------------------ | --------------------- |
| Main DB       | `~/.config/atlastrinity/atlastrinity.db`    | SQLite (aiosqlite) | Core application data |
| Trinity DB    | `~/.config/atlastrinity/data/trinity.db`    | SQLite             | Trinity-specific data |
| Monitoring DB | `~/.config/atlastrinity/data/monitoring.db` | SQLite             | Metrics & monitoring  |
| Golden Fund   | `~/.config/atlastrinity/data/golden_fund/`  | SQLite + files     | Knowledge base        |
| Memory        | `~/.config/atlastrinity/memory/`            | ChromaDB           | Vector embeddings     |
| Redis         | `redis://localhost:6379/0`                  | Redis              | State management      |

---

## 8. QUICK REFERENCE — COMMON TASKS

| Task                   | How                                                               |
| ---------------------- | ----------------------------------------------------------------- |
| Check all MCP servers  | `devtools_check_mcp_health()`                                     |
| Test specific MCP tool | `mcp_inspector_call_tool(server, tool, args)`                     |
| Find brain logs        | `~/.config/atlastrinity/logs/brain.log`                           |
| Analyze log for issues | `devtools_analyze_trace("~/.config/atlastrinity/logs/brain.log")` |
| Run all linters        | `devtools_run_global_lint()`                                      |
| Lint Python file       | `devtools_lint_python("path/to/file.py")`                         |
| Lint JS/TS file        | `devtools_lint_js("path/to/file.ts")`                             |
| Check Python types     | `devtools_check_types_python("src/")`                             |
| Find dead code         | `devtools_find_dead_code()`                                       |
| Security audit         | `devtools_check_security()`                                       |
| Check DB state         | `vibe_check_db()` or `scripts/db_report.py`                       |
| Test all MCP tools     | `devtools_run_mcp_sandbox(all_servers=True)`                      |
| Get full system map    | `devtools_get_system_map()`                                       |
| Restart MCP server     | `devtools_restart_mcp_server(server_name)`                        |
| View running processes | `devtools_list_processes()`                                       |
| Validate MCP config    | `devtools_validate_config()`                                      |
