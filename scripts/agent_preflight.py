#!/usr/bin/env python3
"""Agent Pre-flight Verification Tool.

Designed for agents (VS Code, Windsurf) to run before committing changes.
Performs: delta-linting, template synchronization, MCP integrity check, 
and system diagnostics via the Self-Healing Hypermodule.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

# Add project root and src to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.brain.healing.hypermodule import healing_hypermodule, HealingMode

class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    CYAN = "\033[96m"
    ENDC = "\033[0m"

async def run_preflight():
    print(f"{Colors.BOLD}{Colors.CYAN}--- Atlas Trinity Agent Pre-flight ---{Colors.ENDC}\n")

    # 1. Delta-Sync Config Templates
    print(f"{Colors.BOLD}[1/4] Synchronizing configuration templates...{Colors.ENDC}")
    try:
        from src.maintenance.config_sync import main as sync_configs
        sync_configs()
        print(f"{Colors.GREEN}✓ Setup synchronized from templates.{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.RED}✗ Config sync failed: {e}{Colors.ENDC}")

    # 2. Verify Changed Files (Lefthook)
    print(f"\n{Colors.BOLD}[2/4] Running delta-linting on changed files...{Colors.ENDC}")
    try:
        # Check for changed files using git
        diff_proc = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True,
            text=True,
            check=True
        )
        changed_files = diff_proc.stdout.splitlines()
        
        if not changed_files:
            print(f"{Colors.YELLOW}! No staged changes found. Use 'git add' to include files for verification.{Colors.ENDC}")
        else:
            print(f"Analyzing {len(changed_files)} staged files...")
            # We run the full pipeline for now, but we could optimize to specific commands
            # if we integrate more deeply with lefthook filters.
            lint_proc = subprocess.run(
                ["npx", "lefthook", "run", "lint:all"],
                cwd=str(PROJECT_ROOT),
                capture_output=False # Show output to user
            )
            if lint_proc.returncode == 0:
                print(f"{Colors.GREEN}✓ All checks passed.{Colors.ENDC}")
            else:
                print(f"{Colors.RED}✗ Linting/Checks failed.{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.RED}✗ Git/Lefthook error: {e}{Colors.ENDC}")

    # 3. MCP Integrity Check
    print(f"\n{Colors.BOLD}[3/4] Verifying MCP Server Integrity...{Colors.ENDC}")
    try:
        from src.testing.verify_mcp_integrity import verify_integrity
        await verify_integrity()
        print(f"{Colors.GREEN}✓ MCP Catalog and schemas are consistent.{Colors.ENDC}")
    except Exception as e:
        # verify_integrity prints its own report
        print(f"{Colors.YELLOW}! MCP Integrity check encountered issues.{Colors.ENDC}")

    # 4. System Diagnostics (Hypermodule)
    print(f"\n{Colors.BOLD}[4/4] Running System Diagnostics...{Colors.ENDC}")
    try:
        result = await healing_hypermodule.run(HealingMode.DIAGNOSE)
        if result.success:
            status = result.details.get("overall_status", "unknown")
            issues = result.details.get("issues_found", 0)
            
            if status == "healthy":
                print(f"{Colors.GREEN}✓ System Status: HEALTHY{Colors.ENDC}")
            else:
                print(f"{Colors.YELLOW}! System Status: {status.upper()} ({issues} issues found){Colors.ENDC}")
                
            recs = result.details.get("recommendations", [])
            if recs:
                print(f"\n{Colors.BOLD}Recommendations:{Colors.ENDC}")
                for rec in recs:
                    print(f"  - {rec}")
        else:
            print(f"{Colors.RED}✗ Diagnostics failed: {result.message}{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.RED}✗ Hypermodule error: {e}{Colors.ENDC}")

    print(f"\n{Colors.BOLD}{Colors.CYAN}--- Pre-flight Completed ---{Colors.ENDC}")

if __name__ == "__main__":
    try:
        asyncio.run(run_preflight())
    except KeyboardInterrupt:
        print("\nPre-flight cancelled by user.")
        sys.exit(1)
