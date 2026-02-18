# VIBE INSTRUCTIONS

============================================================
ATLASTRINITY SELF-HEALING DIAGNOSTIC REPORT
=
ROLE: Senior Architect & Self-Healing Engineer.
MISSION: Diagnose with ARCHITECTURAL AWARENESS, fix, and verify.

CONTEXT NOTE: Architecture diagrams have been refreshed and are available
in `src/brain/data/architecture_diagrams/mcp_architecture.md`.
Please use them to understand component interactions.

=
1. WHAT HAPPENED (Problem Description)
========================================
ERROR MESSAGE:
Process 58503 (Python) is stuck (0% CPU for extended period).

========================================
2. CONTEXT (Environment & History)
========================================
System Root: /Users/dev/Documents/GitHub/atlastrinity/src
Project Directory: /Users/dev/.config/atlastrinity/workspace

DATABASE SCHEMA (for reference):
- sessions: id, started_at, ended_at
- tasks: id, session_id, goal, status, created_at
- task_steps: id, task_id, sequence_number, action, tool, status, error_message
- tool_executions: id, step_id, server_name, tool_name, arguments, result

RECENT LOGS:

            CRITICAL SYSTEM ERROR ANALYSIS REQUIRED.
            
            ERROR:
            Process 58503 (Python) is stuck (0% CPU for extended period).
            
            CONTEXT:
            Step ID: watchdog_kill_58503
            Action: unknown
            
            LOGS (Last 20 lines):
            Process Info: {'pid': 58503, 'name': 'Python', 'cmdline': '/opt/homebrew/Cellar/python@3.12/3.12.12/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python /Users/dev/.local/bin/vibe -p Read and execute the instructions from file: /Users/dev/.config/atlastrinity/workspace/.vibe/instructions/vibe_instructions_1771391737_9175f1.md --output streaming --agent auto-approve --max-turns 45', 'started': '2026-02-18T07:15:38.445779', 'type': 'vibe_cli', 'last_seen': 1771392034.678831, 'stuck_count': 12, 'cpu_history': [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 'status': 'running', 'memory_mb': 88.59375}  # pyre-ignore
            
            TASK:
            1. Identify the ROOT CAUSE only.
            2. Determine SEVERITY:
               - MINOR: logic error, handled by code change.
               - SERVICE_CRITICAL: Specific tool/service is dead/stuck.
               - SYSTEM_CRITICAL: Memory leak, deadlock, corrupted state.
            3. Recommend STRATEGY: HOT_PATCH, SERVICE_RESTART, or PHOENIX_RESTART.
            
            Output JSON only:
            {
                "root_cause": "...",
                "severity": "...",
                "strategy": "...",
                "fix_plan": "...",
                "confidence": 0.0 to 1.0
            }
            

2.1 RECENT LOGS (Pointer-based Context)
========================================
Full log file: /Users/dev/.config/atlastrinity/logs/vibe_server.log
ACTION: Use your 'read_file' or 'filesystem_read' tool to inspect this file if needed.

BRIEF LOG SNIPPET (last 30 lines for quick orientation):

            CRITICAL SYSTEM ERROR ANALYSIS REQUIRED.
            
            ERROR:
            Process 58503 (Python) is stuck (0% CPU for extended period).
            
            CONTEXT:
            Step ID: watchdog_kill_58503
            Action: unknown
            
            LOGS (Last 20 lines):
            Process Info: {'pid': 58503, 'name': 'Python', 'cmdline': '/opt/homebrew/Cellar/python@3.12/3.12.12/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python /Users/dev/.local/bin/vibe -p Read and execute the instructions from file: /Users/dev/.config/atlastrinity/workspace/.vibe/instructions/vibe_instructions_1771391737_9175f1.md --output streaming --agent auto-approve --max-turns 45', 'started': '2026-02-18T07:15:38.445779', 'type': 'vibe_cli', 'last_seen': 1771392034.678831, 'stuck_count': 12, 'cpu_history': [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 'status': 'running', 'memory_mb': 88.59375}  # pyre-ignore
            
            TASK:
            1. Identify the ROOT CAUSE only.
            2. Determine SEVERITY:
               - MINOR: logic error, handled by code change.
               - SERVICE_CRITICAL: Specific tool/service is dead/stuck.
               - SYSTEM_CRITICAL: Memory leak, deadlock, corrupted state.
            3. Recommend STRATEGY: HOT_PATCH, SERVICE_RESTART, or PHOENIX_RESTART.
            
            Output JSON only:
            {
                "root_cause": "...",
                "severity": "...",
                "strategy": "...",
                "fix_plan": "...",
                "confidence": 0.0 to 1.0
            }
            

========================================
4. YOUR INSTRUCTIONS
========================================

ANALYSIS MODE (no changes):
1. Perform deep root cause analysis
2. Explain WHY this error occurred
3. Suggest specific fixes with rationale
4. Estimate complexity and risk of each fix

Do NOT apply any changes - analysis only.