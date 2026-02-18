---
description: Handshake protocol between external agents and Atlas Trinity for robust development.
---

# Agent-Trinity Interaction Workflow

This document defines the protocol for AI agents (Windsurf, VS Code, Cursor) and human developers to interact with the Atlas Trinity self-healing and verification engine.

## The Interaction Loop

To ensure every code change is stable and integrated, follow this loop:

### 0. Synchronization (Mandatory)

BEFORE making any changes, synchronize your local environment with the latest remote state:
`git pull --rebase origin main`

### 1. Development Phase

As an agent, you make changes to the code or configurations.

> [!IMPORTANT]
> Always modify templates in `config/*.template` instead of the active files in `~/.config/atlastrinity/`.

### 2. Pre-flight Verification (The Handshake)

Before committing or pushing, run the **Agent Pre-flight**. This synchronizes configurations, runs delta-linting on changed files, and checks system integrity.

// turbo
**Command:** `python3 scripts/agent_preflight.py`
**With Auto-fix:** `python3 scripts/agent_preflight.py --autofix`
**MCP Tool:** `devtools_server.devtools_trigger_preflight(autofix=True)`

> [!TIP]
> Use the `--autofix` flag to automatically resolve linting errors, configuration mismatches, and system degradations detected during the check.

### 3. Review and Resolve

The pre-flight tool will output a structured report:

- **HEALTHY:** Proceed to commit.
- **DEGRADED:** Review the `Recommendations` section.
- **CRITICAL:** Use `devtools_apply_localized_fix` if available, or manually fix the reported issues.

### 4. Continuous Integration (CI)

Once pushed, the GitHub Actions pipeline (`ci-core.yml`) takes over.

- If it fails, the `auto-fix.yml` workflow will automatically trigger.
- The **Self-Healing Hypermodule** will analyze the logs, generate a fix, and create an `auto-fix` PR.
- You should then pull these fixes back into your local workspace.

## Key MCP Tools for Agents

| Tool                               | Purpose                                                |
| ---------------------------------- | ------------------------------------------------------ |
| `devtools_trigger_preflight`       | Runs synchronizers, linters, and diagnostics.          |
| `devtools_get_self_healing_status` | Lists pending log-analyzer notes and hotspots.         |
| `devtools_apply_localized_fix`     | Triggers a focused improvement cycle for a file.       |
| `devtools_restart_mcp_server`      | Restarts servers if diagnostics report they are stuck. |

## Troubleshooting

- If `agent_preflight.py` fails with an import error, ensure you are in the project root and the virtual environment is activated.
- If GITHUB_TOKEN is missing, CI/CD status checks will be skipped.
- **Identity Mandate**: All GitHub operations must use the `GITHUB_TOKEN @[.env]`. Access level and identity are derived from the current token.
