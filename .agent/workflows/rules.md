---
description: System rules, authorized models, and operational guidelines for Atlas Trinity
---

# Atlas Trinity System Rules

You must strictly adhere to the following operational rules and architectural constraints.

## Core Operational Rules

- **Context7 Automation**: ALWAYS use `context7` when you need code generation, setup or configuration steps, or library/API documentation. Automatically use the Context7 MCP tools to resolve library IDs and get library docs without being explicitly asked.
- **Workflow-Driven Generation**: Ensure that any generation pays attention to the workflow in the correct form, so that any generation has a clear direction.
- **Git Protocol**: After successfully completing a work phase or fixing a bug, always propose a git commit with a clear and descriptive message summarizing the changes.
- **Templates First**: Apply configuration changes ONLY to templates in the `Configuration Templates` directory. Verify that they are synchronized to the corresponding files in the `Active Configurations` folder.
- **Python Version**: ALWAYS use **Python 3.12**. This version is mandatory for all core logic, scripts, and environment configurations. Ensure all dependency management and runtime checks adhere to this version.

## Model Suite (Copilot Provider Only)

We use a single custom provider: **Copilot**. We only use the following 5 native models:

1. **`gpt-4o`** (Універсальна)
2. **`oswe-vscode-secondary`** (Нативний ID для Raptor Mini / Speed)
3. **`gpt-5-mini`** (Ефективність / Routing)
4. **`grok-code-fast-1`** (Швидке кодування від xAI)
5. **`gpt-4.1`** (Глибокі міркування / Reasoning)

## System Paths

- **Logs & Error Reports**: `/Users/dev/.config/atlastrinity/logs/`
- **Session Memory**: `/Users/dev/.config/atlastrinity/memory/`
- **Screenshots & Verification**: `/Users/dev/.config/atlastrinity/screenshots/`
- **Vibe Workspace**: `/Users/dev/.config/atlastrinity/vibe_workspace/`
- **Active Configurations**: `/Users/dev/.config/atlastrinity/`
- **Configuration Templates**: `/Users/dev/Documents/GitHub/atlastrinity/config/`
