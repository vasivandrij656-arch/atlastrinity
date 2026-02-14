---
description: Formal Self-Healing Workflow with Sandbox Verification and State Preservation
---

# Self-Healing Phoenix Protocol

## Overview

The self-healing system is unified in **`src/brain/healing/hypermodule.py`** — the **SelfHealingHypermodule**. It consolidates all scattered healing/maintenance scripts into a single orchestrator with 4 modes.

## Unified Entry Point

```python
from src.brain.healing import healing_hypermodule, HealingMode

# Reactive healing (fix active error)
result = await healing_hypermodule.run(HealingMode.HEAL, context={
    "error": "...",
    "step_id": "step_1",
    "step_context": {...},
})

# System diagnostics
result = await healing_hypermodule.run(HealingMode.DIAGNOSE)

# Preventive maintenance
result = await healing_hypermodule.run(HealingMode.PREVENT)

# Proactive code improvements
result = await healing_hypermodule.run(HealingMode.IMPROVE)
```

## Modes

### 1. HEAL — Reactive Error Fixing

**When:** An active error occurs during task execution.
**Flow:**

1. Save task state snapshot
2. Try parallel healing (non-blocking via `ParallelHealingManager`)
3. Fallback to blocking heal (via `HealingOrchestrator`)
4. Restore state on completion

### 2. DIAGNOSE — System Health Check

**When:** On startup, on demand, or when suspected degradation.
**Flow:**

1. Run `SystemFixer.run_all()` — auto-fix known issues
2. Run `health_checks` — YAML, MCP, DB, Vibe, memory
3. Run `mcp_health` — MCP server connectivity
4. Check CI/CD workflow status via GitHub API
5. Report unified diagnostic with recommendations

### 3. PREVENT — Preventive Maintenance

**When:** Every 6 hours (cron) or on demand.
**Flow:**

1. Log rotation and cleanup
2. Config sync verification (templates → active)
3. CI/CD failure analysis → improvement notes
4. Memory/cache cleanup
5. Stale notes cleanup (>30 days)

### 4. IMPROVE — Proactive Code Improvement

**When:** Improvement notes have accumulated from log analysis.
**Flow:**

1. Read pending notes from `LogAnalyzer`
2. Group into `Hotspot` objects by file
3. Generate fix via Vibe for each hotspot
4. Verify with lint/tests
5. Auto-commit with `[Self-Healing:Improvement]` tag
6. Mark notes as addressed

## Background Services

- **LogAnalyzer** — daemon thread watching `~/.config/atlastrinity/logs/brain.log`
  - Extracts: error patterns, slow ops, repeated warnings, resource bottlenecks
  - Persists notes to `~/.config/atlastrinity/memory/improvement_notes.json`

- **ServerManager** — MCP server restart with state preservation
  - Snapshots task state before restart
  - Restores after reconnection for seamless resumption

- **CIBridge** — GitHub Actions integration
  - Queries workflow status via API
  - Triggers auto-fix workflows
  - Commits with `[Self-Healing]` tags

## CI/CD Integration

New workflow: `.github/workflows/self-healing.yml`

- Runs every 6 hours (PREVENT mode)
- Manual dispatch with mode selection (diagnose/prevent/improve)
- Auto-commits changes and uploads diagnostic reports

## Configuration

All settings in `behavior_config.yaml` under `self_healing.hypermodule:`.

## Core Files

| File                                      | Purpose                               |
| ----------------------------------------- | ------------------------------------- |
| `src/brain/healing/hypermodule.py`        | Main orchestrator (4 modes)           |
| `src/brain/healing/modes.py`              | Enums and dataclasses                 |
| `src/brain/healing/log_analyzer.py`       | Background log watcher                |
| `src/brain/healing/ci_bridge.py`          | CI/CD integration                     |
| `src/brain/healing/server_manager.py`     | Server lifecycle management           |
| `src/brain/healing/improvement_engine.py` | Proactive improvement engine          |
| `src/brain/healing/system_healing.py`     | Phoenix Protocol (legacy, still used) |
| `src/brain/healing/parallel_healing.py`   | Parallel healing (legacy, still used) |
