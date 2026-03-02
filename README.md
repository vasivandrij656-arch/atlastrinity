# AtlasTrinity 🔱

**Autonomous Recursive Agentic System for macOS**
_High-End AGI-lite Architecture (Thin Client, Fat Brain)_

[![CI Core Pipeline](https://github.com/olegkizima01/atlastrinity/workflows/CI%20Core%20Pipeline/badge.svg)](https://github.com/olegkizima01/atlastrinity/actions/workflows/ci-core.yml)
[![Trinity Agent Tests](https://github.com/olegkizima01/atlastrinity/workflows/Trinity%20Agent%20Tests/badge.svg)](https://github.com/olegkizima01/atlastrinity/actions/workflows/test-trinity.yml)

![AtlasTrinity UI](design-system/dizaine_electron.png)

### 💎 Strict Integrity

The entire cognitive stack (Brain + 18 MCP servers) has undergone deep hardening. Verified: **0 errors** in types, asynchronous calls, and structure via Pyrefly. All Redis interaction has been modernized to `redis.asyncio`.

---

## 🌟 About the Project

**AtlasTrinity** is an intelligent multi-agent ecosystem for macOS that allows autonomous execution of any tasks on the computer via voice or text. The system uses a triad of agents (**Atlas**, **Tetyana**, **Grisha**) for planning, execution, and verification of actions using the MCP (Model Context Protocol).

### What makes AtlasTrinity unique:

- 🧠 **Recursive Multi-Agent Intelligence** — three agents with different roles recursively solving tasks of any depth.
- 🔧 **173+ tools** via a single MCP hub (XcodeBuild + macOS-use + GoogleMaps + Windsurf).
- 🔄 **Self-Healing Engine** — automatic error correction via CI-Bridge and Hypermodule.
- 🗣️ **Voice Interface** — recognition (Whisper large-v3) and speech synthesis (Ukrainian voices).
- 🗺️ **Cyber-punk Maps** — interactive Google Maps with virtual tours and Street View.
- 💾 **Multi-level Memory** — SQLite + ChromaDB + Redis + Golden Fund with semantic search.
- 🔐 **Authentication** — OAuth2, Keychain, Credential Vault, Diia.EP, BankID.
- 🖥️ **Electron Desktop App** — Vite + React interface with a real-time agent dashboard.
- 📊 **Data Analysis** — Pandas-based data analysis (CSV, Excel, JSON, Parquet).
- 🔀 **Hybrid LLM Providers** — automatic switching between Copilot and Windsurf.

---

## 📋 System Requirements

| Component   | Minimum        | Recommended          |
| ----------- | -------------- | -------------------- |
| **macOS**   | 14.5+ (Sonoma) | 15.0+ (Sequoia)      |
| **Python**  | 3.10+          | 3.12.12              |
| **Node.js** | 18.x           | 22.x+                |
| **Swift**   | 5.9+           | 6.x                  |
| **Redis**   | 7.x            | latest               |
| **Bun**     | 1.x            | latest               |
| **Xcode**   | 16.x+          | latest               |
| **Disk**    | ~5 GB          | ~10 GB (with models) |

---

## 🚀 Quick Start

### 1. Cloning and Setup

```bash
# Clone the repository
git clone https://github.com/olegkizima01/atlastrinity.git
cd atlastrinity

# Full automatic deployment
npm run setup
# or
python3 scripts/setup_dev.py
```

### 2. What Setup Does:

- ✅ **Python venv**: Creates `.venv` with all dependencies from `requirements.txt`.
- ✅ **NPM Packages**: Installs 18+ MCP servers (Swift, Python, Node).
- ✅ **FORCED Native Build**: Recompiles Swift MCP servers (`macos-use`, `googlemaps`, `windsurf`) for guaranteed operation.
- ✅ **AI Models**: Downloads TTS (Ukrainian voice) and STT (Faster-Whisper large-v3) models (~3 GB).
- ✅ **Redis**: Installs via Homebrew and starts the service.
- ✅ **FORCED Config Sync**: Synchronizes configurations, forcing an overwrite of `~/.config/atlastrinity/` from current templates.
- ✅ **SQLite DB**: Initializes the database (`recovery_attempts` table, sessions, tasks).
- ✅ **Dev Tools**: Installs Ruff, Pyrefly, Oxlint, Knip, MCP Inspector.
- ✅ **Verification**: Checks Python version, existence of Swift, Bun, Redis, Vibe CLI.

### 3. API Key Configuration

```bash
# Edit ~/.config/atlastrinity/.env
nano ~/.config/atlastrinity/.env
```

```env
# === Copilot (Primary Provider) ===
COPILOT_API_KEY=ghu_your_token_here

# === Windsurf (Alternative Provider) ===
WINDSURF_API_KEY=sk-ws-your_token_here
WINDSURF_INSTALL_ID=your_install_id_here

# === GitHub (for GitHub MCP server) ===
GITHUB_TOKEN=ghp_your_token_here

# === Google Maps (for navigation and maps) ===
GOOGLE_MAPS_API_KEY=your_key_here
```

### 4. Launch

```bash
npm run dev
```

One command starts **5 parallel processes**:

| Process            | Description                 | URL                     |
| ------------------ | --------------------------- | ----------------------- |
| **Brain**          | Python FastAPI backend      | `http://127.0.0.1:8000` |
| **Renderer**       | Vite React frontend         | `http://localhost:3000` |
| **Electron**       | Desktop window              | —                       |
| **Copilot Proxy**  | LLM API gateway             | `:8086`                 |
| **Config Watcher** | Auto-config synchronization | —                       |

### 5. System Check

```bash
# MCP server status (90+ tools)
npm run mcp:status

# Environment verification
npm run verify

# Redis check
npm run redis:check

# Code integrity
npm run lint:all
```

### Fresh Install (from scratch)

For a complete clean install (removes caches and starts from zero):

```bash
npm run fresh-install
```

---

## 🤖 Cognitive Architecture (Trinity)

The system uses a **Multi-Agent Reasoning Loop**, where each agent has its specialization:

| Agent          | Role                               | Model (default)           | Voice   |
| -------------- | ---------------------------------- | ------------------------- | ------- |
| **Atlas** 🔱   | Strategist (Meta-Planner)          | gpt-4.1                   | Dmytro  |
| **Tetyana** ⚡ | Executor (Tools / CLI / GUI)       | gpt-4.1                   | Tetiana |
| **Grisha** 🛡️  | Critic (Vision / Security / Audit) | gpt-4.1 + gpt-4o (Vision) | Mykyta  |

### How the cycle works:

```
User Request
      │
      ▼
┌─ ATLAS (Strategist) ──────────────────────┐
│  • Request Analysis + ChromaDB lookup     │
│  • Meta-Planning (Sequential Thinking)    │
│  • Step-by-step plan creation             │
└──────────────┬────────────────────────────┘
               │
      ┌────────▼────────┐
      │  TETYANA (Exec)  │◄── Feedback from Grisha
      │  • Execution     │     (recommendations, reports)
      │    via MCP       │
      └────────┬────────┘
               │
      ┌────────▼────────┐
      │  GRISHA (Audit)  │
      │  • Vision analysis│     ✅ → Proceed
      │  • Security check │     ❌ → Recursive fix
      │  • Quality Score  │
      └─────────────────┘
```

- **Recursive Self-Correction**: If a step fails, Atlas creates a subtask executed by the same rules — recursion depth up to 5 levels.
- **Strategic Deviation**: Tetyana can suggest a more efficient path — Atlas evaluates and rebuilds the plan "on the fly".
- **Vision-Based Verification**: Grisha takes screenshots and analyzes them via GPT-4o Vision to confirm actual execution.

---

## 🔀 Hybrid LLM Providers

AtlasTrinity supports **two LLM providers** with automatic switching:

### GitHub Copilot (Primary)

| Model                    | Purpose                      |
| ------------------------ | ---------------------------- |
| `gpt-4.1`                | Primary model for all agents |
| `gpt-4o`                 | Vision / Multimodal tasks    |
| `gpt-5-mini`             | Fast tasks                   |
| `claude-haiku-4.5`       | Claude 4.5 (200K context)    |
| `gemini-flash-3-preview` | Gemini Flash 3 (1M context)  |
| `oswe-vscode-secondary`  | Deep problem analysis        |
| `o3-mini`                | Reasoning model              |

### Windsurf / Codeium (Alternative, FREE tier)

| Model           | Purpose                         |
| --------------- | ------------------------------- |
| `swe-1.5`       | Software engineering specialist |
| `deepseek-r1`   | Logical reasoning & CoT         |
| `kimi-k2.5`     | Fast context & coding           |
| `gpt-5.1-codex` | GPT-5.1 Codex                   |

```bash
# Provider switching
python -m providers switch windsurf

# Status check
python -m providers status

# Token retrieval
python -m providers token copilot --method vscode
python -m providers token windsurf
```

---

## 🛠 MCP Ecosystem (18 Active Servers, 200+ Tools)

MCP (Model Context Protocol) is the "nervous system" of AtlasTrinity. Servers are organized by tiers:

### Tier 1 — System Core

| Server                  | Tools    | Technology             | Description                                                               |
| ----------------------- | -------- | ---------------------- | ------------------------------------------------------------------------- |
| **xcodebuild**          | **173+** | Node.js + Swift Bridge | Unified hub: Xcode (94) + macOS-use (63) + GoogleMaps (11) + Windsurf (5) |
| **windsurf**            | 16       | Native Swift           | Windsurf AI with Cascade Action Phase                                     |
| **filesystem**          | 11       | Node.js                | File operations (read/write/search/move)                                  |
| **sequential-thinking** | 1        | Node.js (Bun)          | Dynamic step-by-step planning                                             |

### Tier 2 — High Priority

| Server                | Tools | Technology                 | Description                                                           |
| --------------------- | ----- | -------------------------- | --------------------------------------------------------------------- |
| **vibe**              | 18    | Python                     | AI Coding, Self-Healing, Code Review, Debugging                       |
| **memory**            | 9     | Python (SQLite + ChromaDB) | Knowledge Graph, persistent memory                                    |
| **golden-fund**       | 8     | Python                     | Golden Knowledge Fund: semantic search, entity probing, data analysis |
| **graph**             | 4     | Python                     | Knowledge Graph visualization (Mermaid, JSON)                         |
| **data-analysis**     | 10    | Python (Pandas)            | Data analysis: CSV, Excel, JSON, Parquet                              |
| **devtools**          | 7+    | Python                     | Linter wrapper (Ruff, Oxlint, Knip, Pyrefly), MCP Inspector, Sandbox  |
| **redis**             | 5     | Python                     | State inspection: get/set/keys/delete/info                            |
| **duckduckgo-search** | 3     | Python                     | Fast web search without API keys                                      |
| **whisper-stt**       | 2     | Python (Whisper)           | Speech-to-Text (Faster-Whisper large-v3)                              |
| **github**            | 20+   | Node.js                    | GitHub API: PRs, Issues, Search, File Operations                      |
| **tour-guide**        | 6     | Python (Internal)          | Virtual tours: start/stop/pause/resume/look/speed                     |

---

## 🖥️ Electron Desktop App

The interface is built with **Electron + Vite + React** (TypeScript):

| Component               | Purpose                                                     |
| ----------------------- | ----------------------------------------------------------- |
| **NeuralCore**          | Central panel with clockwork animation of agent states      |
| **ChatPanel**           | Textual dialogue with agents                                |
| **CommandLine**         | Direct command input for MCP servers                        |
| **MapView**             | Interactive Google Maps with cyber-punk style & Street View |
| **AgentStatus**         | Real-time status of each agent (Atlas, Tetyana, Grisha)     |
| **ExecutionLog**        | Live execution log of steps                                 |
| **SessionManager**      | Session and history management                              |
| **ClockworkBackground** | Animated clockwork mechanism behind agent layers            |

---

## 🎙️ Voice Interface (Voice)

| Function      | Technology              | Details                                                    |
| ------------- | ----------------------- | ---------------------------------------------------------- |
| **STT**       | Faster-Whisper large-v3 | Local model, Ukrainian/English                             |
| **TTS**       | Ukrainian-TTS           | Voices: Dmytro (Atlas), Tetiana (Tetyana), Mykyta (Grisha) |
| **Bilingual** | Auto-detect             | Automatic language detection                               |

---

## 🔄 Self-Healing & Monitoring

### Self-Healing Engine (`src/brain/healing/`)

| Module                 | Purpose                                           |
| ---------------------- | ------------------------------------------------- |
| **Hypermodule**        | Recursive analysis and error correction           |
| **CI Bridge**          | CI/CD integration for automatic fixes             |
| **Parallel Healing**   | Parallel correction of multiple issues            |
| **System Healing**     | Restoration of system state after failures        |
| **Server Manager**     | MCP server restart on connection loss             |
| **Improvement Engine** | Error pattern analysis and improvement generation |
| **Log Analyzer**       | Structured log analysis for diagnostics           |

### Monitoring (`src/brain/monitoring/`)

- **Watchdog**: System health monitoring with automatic alerts.
- **Metrics**: Prometheus-compatible metrics (port 8001).
- **Notifications**: System notifications for critical events.
- **OpenTelemetry**: Tracing for all MCP calls.

---

## 💾 Memory Hierarchy

| Level           | Technology              | Purpose                                                              |
| --------------- | ----------------------- | -------------------------------------------------------------------- |
| **Short-term**  | Redis + `SharedContext` | Current state: open files, CWD, active operations                    |
| **Structured**  | SQLite (aiosqlite)      | Session history, tasks, GraphChain, logs                             |
| **Semantic**    | ChromaDB (Vector Store) | "Experience" — abstract strategies and lessons for similarity search |
| **Golden Fund** | Dedicated MCP Server    | Verified knowledge with forced isolation and "Promotion" system      |

---

## 📊 Data Analysis Engine

Pandas-based server for data analysis (`data-analysis` MCP):

- **Formats**: CSV, Excel, JSON, Parquet.
- **Tools**: `read_metadata`, `analyze_dataset`, `generate_statistics`, `create_visualization`, `data_cleaning`, `data_aggregation`, `interpret_column_data`, `run_pandas_code`.

---

## 🗺️ Navigation and Virtual Tours

- **Google Maps Integration** (11 tools): geocoding, directions, traffic, places search, street view.
- **Tour Driver** (`src/brain/navigation/`): Autonomous virtual tours with real map movement.
- **Tour Guide** (Internal MCP): `tour_start`, `tour_stop`, `tour_pause`, `tour_resume`, `tour_look`, `tour_set_speed`.
- **MapView** UI: Cyber-punk styling with effects, POI markers, and Street View.

---

## 🔐 Authentication and Security

### Credential Management

- **Credential Vault** — encrypted local storage with auto-refresh support.
- **macOS Keychain** — system storage integration.
- **SSH/GPG Agent** — support for SSH and GPG keys.
- **Auto-Discovery** — automatic scanning of credential stores.

---

## ⚙️ Smart Configuration (Global First)

AtlasTrinity uses a **Global First** architecture for security and convenience:

| Path                             | Purpose                                               |
| -------------------------------- | ----------------------------------------------------- |
| `config/*.template`              | **Source of Truth** — configuration templates in repo |
| `~/.config/atlastrinity/`        | **Runtime** — active configurations (auto-sync)       |
| `~/.config/atlastrinity/.env`    | **Secrets** — API keys and tokens                     |
| `~/.config/atlastrinity/models/` | **AI Models** — local STT/TTS models                  |

---

## 📈 CI/CD Pipeline

### GitHub Actions Workflows

| Workflow                | Trigger  | Description                                                                |
| ----------------------- | -------- | -------------------------------------------------------------------------- |
| **CI Core Pipeline**    | Push, PR | Linting (Biome, Oxlint, TSC, ESLint, Ruff, Pyright, Pyrefly), tests, build |
| **Trinity Agent Tests** | Push, PR | Agent testing (Atlas, Tetyana, Grisha), MCP orchestration                  |

---

## 📦 Production Build

To create a ready-to-use macOS application (.app / .dmg):

```bash
# Full DMG build (arm64)
npm run build:mac
```

---

## 🗂️ Project Structure

```text
atlastrinity/
├── src/
│   ├── brain/                # 🧠 Python Core (FastAPI, Asyncio)
│   │   ├── agents/           #    Atlas, Tetyana, Grisha implementations
│   │   ├── core/             #    Orchestrator, SharedContext, StateManager
│   │   ├── healing/          #    Self-Healing engine
│   │   ├── memory/           #    ChromaDB, Golden Fund, Semantic Search
│   │   ├── mcp/              #    MCP Client, Tool Dispatcher, Routing
│   │   ├── voice/            #    STT (Whisper), TTS (Ukrainian-TTS)
│   │   └── server.py         #    Main API Gateway
│   ├── main/                 # ⚡ Electron Host Process (TypeScript)
│   ├── renderer/             # 🎨 Frontend UI (React + Vite + TypeScript)
│   ├── mcp_server/           # 🔧 Custom MCP Servers (Python)
│   └── ...
├── vendor/                   # 📦 External Swift MCP servers
├── config/                   # ⚙️ Configuration Templates
├── scripts/                  # 🛠 DevOps & Diagnostic Utilities
├── tests/                    # 🧪 Test Suite (50+ tests)
├── docs/                     # 📚 Documentation (40+ files)
└── .github/                  # 🔄 CI/CD Workflows + Dependabot
```

---

## 🧪 Useful Commands

```bash
# === Development ===
npm run dev                   # Start everything (Brain + UI + Electron + Proxy + Watcher)

# === MCP ===
npm run mcp:status            # Status of all servers
npm run test:sandbox          # Sandbox testing of MCP servers

# === Diagnostics ===
npm run verify                # Environment check
npm run redis:check           # Redis status

# === Maintenance ===
npm run clean:full            # Full memory cleanup
npm run config:sync           # Synchronize configs
```

---

## 📜 License

MIT

---

**AtlasTrinity** 🔱 _Recursive Intelligence for macOS_
