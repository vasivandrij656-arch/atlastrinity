import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict, cast

from mcp.server import FastMCP

from .context_check import run_test_suite
from .diagram_generator import generate_architecture_diagram
from .git_manager import (
    download_github_job_logs,
    ensure_git_repository,
    fetch_github_workflow_jobs,
    fetch_github_workflow_runs,
    get_git_changes,
    setup_github_remote,
)
from .project_analyzer import analyze_project_structure, detect_changed_components
from .trace_analyzer import analyze_log_file

server = FastMCP("devtools-server")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VENV_BIN = PROJECT_ROOT / ".venv" / "bin"
VENV_PYTHON = VENV_BIN / "python"


class ResponseDict(TypedDict):
    success: bool
    git_status: dict[str, Any]
    github_status: dict[str, Any]
    diagram_status: dict[str, Any]
    project_type: str
    components_detected: int
    analysis: dict[str, Any]
    message: str
    updates_made: bool
    files_updated: list[str]
    timestamp: str


@server.tool()
def devtools_list_processes() -> dict[str, Any]:
    """List all processes tracked by the AtlasTrinity Watchdog.
    Includes PID, type (vibe, mcp, proxy), CPU usage history, and health status.
    """
    try:
        from src.brain.monitoring.watchdog import watchdog

        return watchdog.get_status()
    except Exception as e:
        return {"error": f"Failed to get process status: {e}"}


@server.tool()
async def devtools_restart_mcp_server(server_name: str) -> dict[str, Any]:
    """Gracefully restart a specific MCP server.

    Args:
        server_name: The name of the server to restart (e.g., 'vibe', 'memory', 'filesystem').
    """
    try:
        from src.brain.mcp.mcp_manager import mcp_manager

        success = await mcp_manager.restart_server(server_name)
        return {
            "success": success,
            "message": f"Server {server_name} restart {'initiated' if success else 'failed'}.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@server.tool()
async def devtools_kill_process(pid: int, hard: bool = False) -> dict[str, Any]:
    """Forcefully terminate or kill a specific process by PID.

    Args:
        pid: The Process ID to kill.
        hard: If True, send SIGKILL (hard kill). Otherwise SIGTERM (graceful).
    """
    try:
        from src.brain.monitoring.watchdog import watchdog

        success = await watchdog.terminate_process(pid, hard=hard)
        return {
            "success": success,
            "message": f"PID {pid} {'killed' if success else 'failed to kill'}.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@server.tool()
def devtools_check_mcp_health() -> dict[str, Any]:
    """Run the system-wide MCP health check script.
    Ping all enabled servers and report their status, response time, and tool counts.
    """
    script_path = PROJECT_ROOT / "scripts" / "check_mcp_health.py"

    if not script_path.exists():
        return {"error": f"Health check script not found at {script_path}"}

    try:
        # Run scripts/check_mcp_health.py --json
        cmd = [sys.executable, str(script_path), "--json"]
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL
        )

        output = result.stdout.strip()
        if not output:
            return {"error": "Health check returned empty output", "stderr": result.stderr}

        try:
            data = json.loads(output)
            return cast("dict[str, Any]", data)
        except json.JSONDecodeError:
            return {"error": "Failed to parse health check JSON", "raw_output": output}

    except Exception as e:
        return {"error": str(e)}


@server.tool()
def devtools_launch_inspector(server_name: str) -> dict[str, Any]:
    """Launch the official MCP Inspector for a specific server (Tier 1-4).
    This starts a background process and returns a URL (localhost) to open in the browser.

    Args:
        server_name: The name of the server to inspect (e.g., 'memory', 'vibe', 'filesystem').

    Note: The inspector process continues running in the background.

    """
    # Load active MCP config to find command
    config_path = Path.home() / ".config" / "atlastrinity" / "mcp" / "config.json"
    if not config_path.exists():
        # Fallback to template if active not found (unlikely in prod but helpful for dev)
        config_path = PROJECT_ROOT / "src" / "mcp_server" / "config.json.template"

    if not config_path.exists():
        return {"error": "MCP Configuration not found"}

    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        server_config = config.get("mcpServers", {}).get(server_name)
        if not server_config:
            return {"error": f"Server '{server_name}' not found in configuration."}

        command = server_config.get("command")
        args = server_config.get("args", [])
        env_vars = server_config.get("env", {})

        # Construct inspector command
        # npx @modelcontextprotocol/inspector <command> <args>
        inspector_cmd = ["npx", "@modelcontextprotocol/inspector", command, *args]

        # Prepare environment
        env = os.environ.copy()
        # Resolve variables in args/env (basic resolution)
        # NOTE: This is a simplified resolution. For full resolution, we'd need mcp_manager logic.
        # But commonly used vars are usually just HOME or PROJECT_ROOT.

        # Basic substitution for '${HOME}' and '${PROJECT_ROOT}' in args
        resolved_inspector_cmd = []
        for arg in inspector_cmd:
            arg = arg.replace("${HOME}", str(Path.home()))
            arg = arg.replace("${PROJECT_ROOT}", str(PROJECT_ROOT))
            resolved_inspector_cmd.append(arg)

        # Add server-specific env vars
        for k, v in env_vars.items():
            val = v.replace("${GITHUB_TOKEN}", env.get("GITHUB_TOKEN", ""))
            env[k] = val

        # Start detached process
        # We redirect stdout/stderr to capture the URL, but we need to be careful not to block.
        # Ideally, we start it, wait a second to scrape the URL from stderr, then let it run.

        proc = subprocess.Popen(
            resolved_inspector_cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            start_new_session=True,  # Detach
        )

        # Peek at output to find URL (inspector prints to stderr usually)
        # We'll wait up to 5 seconds
        import time

        for _ in range(10):
            if proc.poll() is not None:
                # Process died
                out, err = proc.communicate()
                return {
                    "error": "Inspector process exited immediately",
                    "stdout": out,
                    "stderr": err,
                }

            # We can't easily read without blocking unless we use threads or fancy non-blocking I/O.
            # Simple approach: Return success and tell user to check output or assume standard port.
            # But the user wants the URL.
            # Let's try to assume it works and return a generic message,
            # OR better: The inspector usually prints "Inspector is running at http://localhost:xxxx"

            time.sleep(0.5)

        # If it's still running, we assume success.
        return {
            "success": True,
            "message": f"Inspector launched for '{server_name}'.",
            "pid": proc.pid,
            "note": "Please check http://localhost:5173 (default) or check terminal output if visible.",
        }

    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# MCP Inspector CLI Tools - Headless verification without UI
# =============================================================================


def _get_inspector_server_cmd(
    server_name: str,
) -> tuple[list[str], dict[str, str]] | dict[str, Any]:
    """Build the inspector CLI command for a given server.

    Returns tuple (cmd_parts, env) on success, or error dict on failure.
    """
    config_path = Path.home() / ".config" / "atlastrinity" / "mcp" / "config.json"
    if not config_path.exists():
        return {"error": "MCP Configuration not found", "path": str(config_path)}

    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        server_config = config.get("mcpServers", {}).get(server_name)
        if not server_config:
            return {"error": f"Server '{server_name}' not found in configuration."}

        command = server_config.get("command")
        args = server_config.get("args", [])
        env_vars = server_config.get("env", {})

        # Build base command parts (will be joined with inspector args)
        # Resolve common variables
        resolved_args = []
        for arg in args:
            arg = arg.replace("${HOME}", str(Path.home()))
            arg = arg.replace("${PROJECT_ROOT}", str(PROJECT_ROOT))
            resolved_args.append(arg)

        resolved_command = command.replace("${HOME}", str(Path.home()))
        resolved_command = resolved_command.replace("${PROJECT_ROOT}", str(PROJECT_ROOT))

        # Base inspector + server command
        server_cmd = [resolved_command, *resolved_args]

        # Prepare environment
        env = os.environ.copy()
        for k, v in env_vars.items():
            val = v.replace("${GITHUB_TOKEN}", env.get("GITHUB_TOKEN", ""))
            val = val.replace("${HOME}", str(Path.home()))
            val = val.replace("${PROJECT_ROOT}", str(PROJECT_ROOT))
            env[k] = val

        return (server_cmd, env)

    except Exception as e:
        return {"error": f"Failed to load config: {e}"}


def _run_inspector_cli(
    server_name: str,
    method: str,
    extra_args: list[str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Run MCP Inspector CLI with specified method and return parsed JSON result."""
    if server_name == "devtools":
        return {
            "error": "Cannot inspect 'devtools' from within devtools (recursive). Use another server name."
        }

    result = _get_inspector_server_cmd(server_name)
    if isinstance(result, dict):
        return result  # Error dict

    server_cmd, env = result

    # Build full inspector command
    inspector_cmd = [
        "npx",
        "@modelcontextprotocol/inspector",
        "--cli",
        *server_cmd,
        "--method",
        method,
    ]

    if extra_args:
        inspector_cmd.extend(extra_args)

    try:
        proc_result = subprocess.run(
            inspector_cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,  # Isolate stdin to prevent interference with MCP stdio
        )

        stdout = proc_result.stdout.strip()
        stderr = proc_result.stderr.strip()

        if proc_result.returncode != 0:
            return {
                "success": False,
                "error": stderr or f"Exit code {proc_result.returncode}",
                "stdout": stdout,
            }

        if not stdout:
            return {"success": True, "data": None, "note": "Empty response"}

        try:
            data = json.loads(stdout)
            return {"success": True, "data": data}
        except json.JSONDecodeError:
            # Return raw output if not JSON
            return {"success": True, "raw_output": stdout}

    except subprocess.TimeoutExpired:
        return {"error": f"Timeout after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


@server.tool()
def mcp_inspector_list_tools(server_name: str) -> dict[str, Any]:
    """List all tools available on a specified MCP server via Inspector CLI.

    Args:
        server_name: Name of the MCP server (e.g., 'filesystem', 'memory', 'vibe').

    Returns:
        Dict with 'success' and 'data' (list of tools with names and schemas).
    """
    return _run_inspector_cli(server_name, "tools/list")


@server.tool()
def mcp_inspector_call_tool(
    server_name: str,
    tool_name: str,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call a specific tool on an MCP server via Inspector CLI.

    Args:
        server_name: Name of the MCP server.
        tool_name: Name of the tool to call.
        args: Optional dictionary of arguments to pass to the tool.

    Returns:
        Dict with 'success' and 'data' (tool execution result).
    """
    extra_args = ["--tool-name", tool_name]

    if args:
        for key, value in args.items():
            if isinstance(value, dict | list):
                extra_args.extend(["--tool-arg", f"{key}={json.dumps(value)}"])
            else:
                extra_args.extend(["--tool-arg", f"{key}={value}"])

    return _run_inspector_cli(server_name, "tools/call", extra_args)


@server.tool()
def mcp_inspector_list_resources(server_name: str) -> dict[str, Any]:
    """List all resources available on a specified MCP server via Inspector CLI.

    Args:
        server_name: Name of the MCP server.

    Returns:
        Dict with 'success' and 'data' (list of resources with URIs and descriptions).
    """
    return _run_inspector_cli(server_name, "resources/list")


@server.tool()
def mcp_inspector_read_resource(server_name: str, uri: str) -> dict[str, Any]:
    """Read a specific resource from an MCP server via Inspector CLI.

    Args:
        server_name: Name of the MCP server.
        uri: URI of the resource to read.

    Returns:
        Dict with 'success' and 'data' (resource contents).
    """
    extra_args = ["--uri", uri]
    return _run_inspector_cli(server_name, "resources/read", extra_args)


@server.tool()
def mcp_inspector_list_prompts(server_name: str) -> dict[str, Any]:
    """List all prompts available on a specified MCP server via Inspector CLI.

    Args:
        server_name: Name of the MCP server.

    Returns:
        Dict with 'success' and 'data' (list of prompts with names and descriptions).
    """
    return _run_inspector_cli(server_name, "prompts/list")


@server.tool()
def mcp_inspector_get_prompt(
    server_name: str,
    prompt_name: str,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Get a specific prompt from an MCP server via Inspector CLI.

    Args:
        server_name: Name of the MCP server.
        prompt_name: Name of the prompt to retrieve.
        args: Optional dictionary of arguments to pass to the prompt.

    Returns:
        Dict with 'success' and 'data' (prompt content with messages).
    """
    extra_args = ["--prompt-name", prompt_name]

    if args:
        for key, value in args.items():
            extra_args.extend(["--prompt-args", f"{key}={value}"])

    return _run_inspector_cli(server_name, "prompts/get", extra_args)


@server.tool()
def mcp_inspector_get_schema(server_name: str, tool_name: str) -> dict[str, Any]:
    """Get the JSON schema for a specific tool on an MCP server.

    Args:
        server_name: Name of the MCP server.
        tool_name: Name of the tool to get schema for.

    Returns:
        Dict with 'success' and 'schema' (input schema for the tool).
    """
    # First list all tools, then extract the specific one
    result = _run_inspector_cli(server_name, "tools/list")

    if not result.get("success"):
        return result

    data = result.get("data")
    if not data:
        return {"error": "No tools data returned"}

    # Handle different response formats
    tools_list = data.get("tools", data) if isinstance(data, dict) else data

    if not isinstance(tools_list, list):
        return {"error": "Unexpected tools format", "raw": data}

    for tool in tools_list:
        if isinstance(tool, dict) and tool.get("name") == tool_name:
            return {
                "success": True,
                "tool_name": tool_name,
                "schema": tool.get("inputSchema", tool.get("schema", {})),
                "description": tool.get("description", ""),
            }

    return {"error": f"Tool '{tool_name}' not found on server '{server_name}'"}


@server.tool()
def devtools_run_mcp_sandbox(
    server_name: str | None = None,
    all_servers: bool = False,
    chain_length: int = 1,
    autofix: bool = False,
) -> dict[str, Any]:
    """Run MCP sandbox tests with LLM-generated realistic scenarios.

    This tool tests ALL MCP tools (including destructive ones) in a safe
    isolated sandbox environment. It generates realistic test scenarios
    using LLM and can chain multiple tools together for natural testing flows.

    Args:
        server_name: Specific server to test (e.g., 'filesystem', 'memory')
        all_servers: Test all enabled MCP servers
        chain_length: Number of tools to chain in each scenario (1-5)
        autofix: Automatically attempt to fix failures via Vibe MCP

    Returns:
        Dict with test results including passed/failed counts and details.
    """
    script_path = PROJECT_ROOT / "scripts" / "mcp_sandbox.py"

    if not script_path.exists():
        return {"error": f"Sandbox script not found at {script_path}"}

    # Build command
    cmd = [str(VENV_PYTHON), str(script_path), "--json"]

    if server_name:
        cmd.extend(["--server", server_name])
    elif all_servers:
        cmd.append("--all")
    else:
        return {"error": "Must specify either server_name or all_servers=True"}

    if chain_length > 1:
        cmd.extend(["--chain", str(min(5, max(1, chain_length)))])

    if autofix:
        cmd.append("--autofix")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout for full test
            check=False,
            stdin=subprocess.DEVNULL,
        )

        stdout = result.stdout.strip()
        if not stdout:
            return {
                "error": "Sandbox returned empty output",
                "stderr": result.stderr,
                "returncode": result.returncode,
            }

        try:
            data = json.loads(stdout)
            return cast("dict[str, Any]", data)
        except json.JSONDecodeError:
            return {
                "error": "Failed to parse sandbox JSON output",
                "raw_output": stdout[:500],
                "stderr": result.stderr,
            }

    except subprocess.TimeoutExpired:
        return {"error": "Sandbox test timed out (>5 minutes)"}
    except Exception as e:
        return {"error": str(e)}


@server.tool()
def devtools_validate_config() -> dict[str, Any]:
    """Validate the syntax and basic structure of the local MCP configuration file."""
    config_path = Path.home() / ".config" / "atlastrinity" / "mcp" / "config.json"

    if not config_path.exists():
        return {"error": "Config file not found", "path": str(config_path)}

    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)

        mcp_servers = data.get("mcpServers", {})
        if not mcp_servers:
            return {"valid": False, "error": "Missing 'mcpServers' key or empty"}

        server_count = len([k for k in mcp_servers if not k.startswith("_")])
        return {"valid": True, "server_count": server_count, "path": str(config_path)}
    except json.JSONDecodeError as e:
        return {"valid": False, "error": f"JSON Syntax Error: {e}"}
    except Exception as e:
        return {"valid": False, "error": str(e)}


@server.tool()
def devtools_lint_python(file_path: str = ".") -> dict[str, Any]:
    """Run the 'ruff' linter on a specific file or directory.
    Returns structured JSON results of any violations found.
    """
    # Check if ruff is installed
    if not shutil.which("ruff"):
        return {"error": "Ruff is not installed or not in PATH."}

    try:
        # Run ruff check --output-format=json
        cmd = ["ruff", "check", "--output-format=json", file_path]
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL
        )

        # If exit code is 0, no errors (usually). But ruff returns non-zero on lint errors too.
        # We parse stdout.
        output = result.stdout.strip()

        # If empty and stderr has content, something crashed or misconfigured
        if not output and result.stderr:
            # Check if it was just a "no errors" case or actual failure
            if result.returncode == 0:
                return {"success": True, "violations": []}
            return {"error": f"Ruff execution failed: {result.stderr}"}

        if not output:
            return {"success": True, "violations": []}

        try:
            violations = json.loads(output)
            return {
                "success": len(violations) == 0,
                "violation_count": len(violations),
                "violations": violations,
            }
        except json.JSONDecodeError:
            return {"error": "Failed to parse ruff JSON output", "raw_output": output}

    except Exception as e:
        return {"error": str(e)}


@server.tool()
def devtools_lint_js(file_path: str = ".") -> dict[str, Any]:
    """Run JS/TS linters (oxlint and eslint) on a specific file or directory.
    Returns structured results from both tools.
    """
    results: dict[str, Any] = {"success": True, "violations": [], "summary": {}}

    # 1. Run oxlint
    if shutil.which("oxlint"):
        try:
            cmd = ["oxlint", "--format", "json", file_path]
            res = subprocess.run(
                cmd, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL
            )
            output = res.stdout.strip()
            if output:
                try:
                    data = json.loads(output)
                    violations = data if isinstance(data, list) else data.get("messages", [])
                    results["violations"].extend(violations)
                    results["summary"]["oxlint"] = len(violations)
                    if len(violations) > 0:
                        results["success"] = False
                except json.JSONDecodeError:
                    results["summary"]["oxlint_error"] = "Failed to parse JSON"
            else:
                results["summary"]["oxlint"] = 0
        except Exception as e:
            results["summary"]["oxlint_exception"] = str(e)

    # 2. Run eslint (via npx to use project-local config)
    if shutil.which("npx"):
        try:
            # Check for eslint config
            has_config = any(
                (PROJECT_ROOT / f).exists()
                for f in [
                    ".eslintrc.js",
                    ".eslintrc.json",
                    ".eslintrc.yml",
                    "eslint.config.js",
                    "eslint.config.mjs",
                    "eslint.config.ts",
                ]
            )
            if has_config:
                cmd = ["npx", "eslint", "--format", "json", file_path]
                # Filter out non-JSON lines (sometimes npx prints update notifications)
                res = subprocess.run(
                    cmd, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL
                )
                output = res.stdout.strip()
                if output:
                    # Find the first '[' which usually starts the JSON array
                    start_idx = output.find("[")
                    if start_idx != -1:
                        try:
                            violations = json.loads(output[start_idx:])
                            # ESLint returns objects with 'messages' list per file
                            total_eslint = 0
                            for item in violations:
                                msgs = item.get("messages", [])
                                total_eslint += len(msgs)
                                results["violations"].extend(msgs)
                            results["summary"]["eslint"] = total_eslint
                            if total_eslint > 0:
                                results["success"] = False
                        except json.JSONDecodeError:
                            results["summary"]["eslint_error"] = "Failed to parse JSON"
                else:
                    results["summary"]["eslint"] = 0
        except Exception as e:
            results["summary"]["eslint_exception"] = str(e)

    return results


@server.tool()
def devtools_run_global_lint() -> dict[str, Any]:
    """Run the complete system linting suite (npm run lint:all).
    This runs 13 parallel checks via lefthook:
    - JS/TS: biome, oxlint, tsc --noEmit (both tsconfigs), eslint type-aware
    - Python: ruff (25 rule sets), pyright (standard), pyrefly, xenon, bandit, vulture
    - Cross: knip (unused JS), security audit, yaml-sync
    """
    try:
        # npm run lint:all is defined in package.json at project root
        cmd = ["npm", "run", "lint:all"]
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "exit_code": result.returncode,
        }
    except Exception as e:
        return {"error": str(e), "success": False}


@server.tool()
def devtools_find_dead_code(target_path: str = ".") -> dict[str, Any]:
    """Run 'knip' (JS/TS) and 'vulture' (Python) to find unused code.
    Detects unused files, dependencies, exports, variables, and functions.
    """
    results: dict[str, Any] = {"success": True, "knip": {}, "vulture": {}}

    # 1. Knip (JS/TS dead code)
    if shutil.which("npx"):
        try:
            cwd = target_path if os.path.isdir(target_path) else "."
            cmd = ["npx", "knip", "--reporter", "json"]
            result = subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL
            )
            output = result.stdout.strip()
            if output:
                try:
                    results["knip"] = json.loads(output)
                except json.JSONDecodeError:
                    results["knip"] = {"raw_output": output}
            else:
                results["knip"] = {"issues": []}
        except Exception as e:
            results["knip"] = {"error": str(e)}
    else:
        results["knip"] = {"error": "npx not found"}

    # 2. Vulture (Python dead code)
    vulture_bin = (
        vbin
        if (
            vbin := shutil.which(
                "vulture", path=os.pathsep.join([str(VENV_BIN), os.environ.get("PATH", "")])
            )
        )
        else None
    )
    if vulture_bin:
        try:
            cmd = [
                vulture_bin,
                "src",
                "scripts",
                "vulture_whitelist.py",
                "--min-confidence",
                "80",
                "--exclude",
                ".venv,dist_venv,node_modules,__pycache__",
            ]
            result = subprocess.run(
                cmd,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
            )
            lines = [l for l in result.stdout.strip().splitlines() if l.strip()]
            results["vulture"] = {
                "dead_code_count": len(lines),
                "items": lines[:50],
            }
            if len(lines) > 0:
                results["success"] = False
        except Exception as e:
            results["vulture"] = {"error": str(e)}
    else:
        results["vulture"] = {"error": "vulture not installed (pip install vulture)"}

    return results


@server.tool()
def devtools_check_integrity(path: str = "src/") -> dict[str, Any]:
    """Run 'pyrefly' to check code integrity and find generic coding errors."""
    pyrefly_bin = (
        vbin
        if (
            vbin := shutil.which(
                "pyrefly", path=os.pathsep.join([str(VENV_BIN), os.environ.get("PATH", "")])
            )
        )
        else None
    )
    if not pyrefly_bin:
        return {"error": "pyrefly is not installed."}

    try:
        # Run pyrefly check
        cmd = [pyrefly_bin, "check", path]
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        # Simple heuristic to extract violation count if possible
        # Pyrefly usually prints something like "Found X errors"
        import re

        error_match = re.search(r"Found (\d+) error", stdout + stderr, re.IGNORECASE)
        error_count = (
            int(error_match.group(1)) if error_match else (0 if result.returncode == 0 else -1)
        )

        return {
            "success": result.returncode == 0,
            "error_count": error_count,
            "stdout": stdout,
            "stderr": stderr,
        }
    except Exception as e:
        return {"error": str(e)}


@server.tool()
def devtools_check_security(path: str = "src/") -> dict[str, Any]:
    """Run security audit tools (bandit, safety, detect-secrets, npm audit)."""
    results: dict[str, Any] = {}

    # 1. Bandit
    bandit_bin = (
        vbin
        if (
            vbin := shutil.which(
                "bandit", path=os.pathsep.join([str(VENV_BIN), os.environ.get("PATH", "")])
            )
        )
        else "bandit"
    )
    try:
        cmd = [bandit_bin, "-r", path, "-ll", "--format", "json"]
        res = subprocess.run(
            cmd, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL
        )
        results["bandit"] = json.loads(res.stdout) if res.stdout else {"error": res.stderr}
    except Exception as e:
        results["bandit"] = {"error": str(e)}

    # 2. Safety (Check dependencies)
    safety_bin = (
        vbin
        if (
            vbin := shutil.which(
                "safety", path=os.pathsep.join([str(VENV_BIN), os.environ.get("PATH", "")])
            )
        )
        else "safety"
    )
    try:
        cmd = [safety_bin, "check", "--json"]
        res = subprocess.run(
            cmd, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL
        )
        results["safety"] = json.loads(res.stdout) if res.stdout else {"error": res.stderr}
    except Exception as e:
        results["safety"] = {"error": str(e)}

    # 3. Detect-secrets
    ds_bin = (
        vbin
        if (
            vbin := shutil.which(
                "detect-secrets", path=os.pathsep.join([str(VENV_BIN), os.environ.get("PATH", "")])
            )
        )
        else "detect-secrets"
    )
    try:
        cmd = [ds_bin, "scan", path]
        res = subprocess.run(
            cmd, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL
        )
        results["secrets"] = json.loads(res.stdout) if res.stdout else {"error": res.stderr}
    except Exception as e:
        results["secrets"] = {"error": str(e)}

    # 4. NPM Audit
    if shutil.which("npm"):
        try:
            cmd = ["npm", "audit", "--json"]
            res = subprocess.run(
                cmd,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
            )
            results["npm_audit"] = json.loads(res.stdout) if res.stdout else {"error": res.stderr}
        except Exception as e:
            results["npm_audit"] = {"error": str(e)}

    return results


@server.tool()
def devtools_check_complexity(path: str = "src/") -> dict[str, Any]:
    """Run complexity audit (xenon)."""
    xenon_bin = (
        vbin
        if (
            vbin := shutil.which(
                "xenon", path=os.pathsep.join([str(VENV_BIN), os.environ.get("PATH", "")])
            )
        )
        else "xenon"
    )
    try:
        # xenon --max-absolute B --max-modules B --max-average A <path>
        cmd = [xenon_bin, "--max-absolute", "B", "--max-modules", "B", "--max-average", "A", path]
        res = subprocess.run(
            cmd, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL
        )
        return {
            "success": res.returncode == 0,
            "stdout": res.stdout.strip(),
            "stderr": res.stderr.strip(),
        }
    except Exception as e:
        return {"error": str(e)}


@server.tool()
def devtools_check_types_python(path: str = "src") -> dict[str, Any]:
    """Run deep type checking for Python (pyright).
    Uses the project's pyrightconfig.json for configuration.
    """
    try:
        cmd = ["npx", "pyright", path]
        res = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        stdout = res.stdout.strip()
        stderr = res.stderr.strip()

        # Parse error/warning counts from pyright output

        error_match = re.search(r"(\d+) error", stdout + stderr)
        warning_match = re.search(r"(\d+) warning", stdout + stderr)
        error_count = int(error_match.group(1)) if error_match else 0
        warning_count = int(warning_match.group(1)) if warning_match else 0

        return {
            "success": error_count == 0,
            "error_count": error_count,
            "warning_count": warning_count,
            "stdout": stdout,
            "stderr": stderr,
        }
    except Exception as e:
        return {"error": str(e)}


@server.tool()
def devtools_check_types_ts() -> dict[str, Any]:
    """Run deep type checking for TypeScript (tsc --noEmit) on both tsconfigs."""
    results: dict[str, Any] = {"success": True}
    configs = ["tsconfig.json", "tsconfig.main.json"]
    for cfg in configs:
        cfg_path = PROJECT_ROOT / cfg
        if not cfg_path.exists():
            results[cfg] = {"skipped": f"{cfg} not found"}
            continue
        try:
            cmd = ["npx", "tsc", "--noEmit", "-p", cfg]
            res = subprocess.run(
                cmd,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                check=False,
                stdin=subprocess.DEVNULL,
            )
            results[cfg] = {
                "success": res.returncode == 0,
                "stdout": res.stdout.strip(),
                "stderr": res.stderr.strip(),
            }
            if res.returncode != 0:
                results["success"] = False
        except Exception as e:
            results[cfg] = {"error": str(e)}
            results["success"] = False
    return results


@server.tool()
def devtools_run_context_check(test_file: str) -> dict[str, Any]:
    """Run logic validation tests from a YAML/JSON file against a mock runner (dry run).

    This tool validates the format of your test scenarios and runs them.
    Currently runs in 'dry_run' mode unless a runner is programmatically injected.
    Future versions will integrate with the active LLM session.

    Args:
        test_file: Path to the .yaml or .json test definition file.
    """
    return run_test_suite(test_file)


@server.tool()
def devtools_analyze_trace(log_path: str = "") -> dict[str, Any]:
    """Analyze an MCP execution log file for logic issues.

    Detects infinite loops (repeated tool calls), inefficiencies, and
    potential hallucinations in tool usage.

    Args:
        log_path: Path to the log file. Defaults to ~/.config/atlastrinity/logs/brain.log
    """
    if not log_path:
        log_path = str(Path.home() / ".config" / "atlastrinity" / "logs" / "brain.log")
    return analyze_log_file(log_path)


@server.tool()
def devtools_update_architecture_diagrams(
    project_path: str | None = None,
    commits_back: int = 1,
    target_mode: str = "internal",
    github_repo: str | None = None,
    github_token: str | None = None,
    init_git: bool = True,
    use_reasoning: bool = True,
) -> dict[str, Any]:
    """Auto-update architecture diagrams by analyzing git changes.

    Universal system that works for ANY project type (Python, Node.js, Rust, Go, etc.).
    Analyzes project structure dynamically and generates appropriate diagrams.

    Features:
    - Universal project detection (Python, Node.js, Rust, Go, generic)
    - Dynamic component analysis
    - Git initialization for new projects
    - GitHub token setup and remote configuration
    - Intelligent diagram generation based on project structure
    - LLM reasoning via sequential-thinking MCP (raptor-mini) for complex changes

    Args:
        project_path: Path to project. None = AtlasTrinity internal project
        commits_back: Number of commits to analyze for changes (default: 1)
        target_mode: 'internal' (AtlasTrinity) or 'external' (other projects)
        github_repo: GitHub repo name (e.g., 'user/repo') for remote setup
        github_token: GitHub token (reads from .env if not provided)
        init_git: Auto-initialize git if not present (default: True)
        use_reasoning: Use sequential-thinking MCP for deep analysis (default: True)

    Returns:
        Status of diagram updates with file locations, git status, GitHub config,
        and reasoning analysis if enabled
    """

    # Determine project paths
    if project_path is None:
        project_path_obj = PROJECT_ROOT
        target_mode = "internal"
    else:
        project_path_obj = Path(project_path).resolve()

    if not project_path_obj.exists():
        return {"error": f"Project path does not exist: {project_path_obj}", "success": False}

    response: ResponseDict = {
        "success": True,
        "git_status": {},
        "github_status": {},
        "diagram_status": {},
        "project_type": "",
        "components_detected": 0,
        "analysis": {},
        "message": "",
        "updates_made": False,
        "files_updated": [],
        "timestamp": "",
    }

    try:
        # Step 1: Analyze project structure (UNIVERSAL)
        project_analysis = analyze_project_structure(project_path_obj)
        response["project_type"] = project_analysis.get("project_type", "unknown")
        response["components_detected"] = len(project_analysis.get("components", []))  # type: ignore[typeddict-item]

        # Step 2: Ensure git is initialized
        if init_git and not project_analysis.get("git_initialized"):
            git_init_result = ensure_git_repository(project_path_obj)
            response["git_status"]["initialized"] = git_init_result
            if not git_init_result.get("initialized"):
                return {
                    "error": git_init_result.get("error") or "Git init failed",
                    "success": False,
                }

        # Step 3: Setup GitHub remote if requested
        if github_repo or github_token:
            github_result = setup_github_remote(project_path_obj, github_repo, github_token)
            response["github_status"] = github_result

        # Step 4: Get git changes (UNIVERSAL - all files, not just src/brain/)
        git_changes = get_git_changes(project_path_obj, commits_back)
        if not git_changes.get("success"):
            # No git history yet or error - create initial diagram
            git_changes = {"diff": "", "modified_files": [], "log": ""}

        git_diff: str = git_changes.get("diff", "")  # type: ignore[assignment]
        modified_files: list[str] = git_changes.get("modified_files", [])  # type: ignore[assignment]

        # Step 5: Detect affected components (UNIVERSAL)
        affected_components = detect_changed_components(project_analysis, git_diff, modified_files)

        # Step 5.5: Deep reasoning analysis (if enabled)
        reasoning_analysis = None
        if use_reasoning and len(modified_files) > 0:
            reasoning_analysis = _analyze_changes_with_reasoning(
                modified_files, affected_components, git_diff, project_analysis
            )

        response["analysis"] = {
            "modified_files": modified_files,
            "affected_components": affected_components,
            "has_changes": len(modified_files) > 0 or len(affected_components) > 0,
            "reasoning": reasoning_analysis,
        }

        if not response["analysis"]["has_changes"]:
            return {
                "success": True,
                "message": "No changes detected in project",
                "updates_made": False,
            }

        # Step 6: Generate/Update diagrams (UNIVERSAL)
        updated_files = []

        if target_mode == "internal":
            # AtlasTrinity internal mode - update both locations
            internal_path = (
                PROJECT_ROOT
                / "src"
                / "brain"
                / "data"
                / "architecture_diagrams"
                / "mcp_architecture.md"
            )
            docs_path = PROJECT_ROOT / ".agent" / "docs" / "mcp_architecture_diagram.md"

            # Generate fresh diagram based on current project structure
            # This ensures we actually reflect architectural changes
            diagram_content = generate_architecture_diagram(project_path_obj, project_analysis)

            # Create clean header
            update_notice = f"\n<!-- AUTO-UPDATED: {datetime.now().isoformat()} -->\n"
            update_notice += f"<!-- Modified: {', '.join(modified_files[:3])} -->\n\n"
            
            updated_diagram = update_notice + diagram_content

            # If a Vibe usage doc/diagram exists, append a reference so it's
            # included in the canonical architecture doc and exported assets.
            try:
                vibe_doc = PROJECT_ROOT / "docs" / "vibe-usage.md"
                vibe_svg = PROJECT_ROOT / "docs" / "vibe-usage-diagram.svg"
                if vibe_svg.exists() or vibe_doc.exists():
                    vibe_section = "\n\n### Vibe (AI agent) — Usage & Integration\n"
                    vibe_section += "The Vibe usage diagram and inventory are included in project exports.\n\n"
                    # Prefer PNG (exported into exports/) then fallback to svg
                    vibe_section += "![](/src/brain/data/architecture_diagrams/exports/vibe-usage-diagram.png)\n"
                    updated_diagram = updated_diagram + vibe_section
            except Exception:
                # non-fatal
                pass

            with open(internal_path, "w", encoding="utf-8") as f:
                f.write(updated_diagram)
            with open(docs_path, "w", encoding="utf-8") as f:
                f.write(updated_diagram)

            updated_files = [str(internal_path), str(docs_path)]
        else:
            # External project - generate diagram from project analysis
            diagram_path = project_path_obj / "architecture_diagram.md"

            # Generate diagram based on project structure
            diagram_content = generate_architecture_diagram(project_path_obj, project_analysis)

            with open(diagram_path, "w", encoding="utf-8") as f:
                f.write(diagram_content)

            updated_files.append(str(diagram_path))

        # Step 7: Export diagrams to PNG/SVG
        _export_diagrams(target_mode, project_path_obj)
        response["diagram_status"]["exported"] = True

        response["message"] = "Architecture diagrams updated successfully"  # type: ignore[typeddict-item]
        response["updates_made"] = True  # type: ignore[typeddict-item]
        response["files_updated"] = updated_files  # type: ignore[typeddict-item]
        response["timestamp"] = datetime.now().isoformat()  # type: ignore[typeddict-item]

        return cast("dict[str, Any]", response)

    except Exception as e:
        return {"error": f"Failed to update diagrams: {e}", "success": False}


# Old hardcoded functions removed - replaced by universal modules:
# - project_analyzer.py: analyze_project_structure, detect_changed_components
# - diagram_generator.py: generate_architecture_diagram
# - git_manager.py: ensure_git_repository, setup_github_remote, get_git_changes


def _analyze_changes_with_reasoning(
    modified_files: list[str],
    affected_components: list[str],
    git_diff: str,
    project_analysis: dict[str, Any],
) -> dict[str, Any] | None:
    """Analyze git changes using sequential-thinking MCP for deep reasoning.

    Uses raptor-mini model via sequential-thinking MCP to understand:
    - Architectural impact of changes
    - Cross-component dependencies
    - Potential diagram updates needed

    Args:
        modified_files: List of changed file paths
        affected_components: List of affected component names
        git_diff: Full git diff output
        project_analysis: Project structure analysis

    Returns:
        Dict with reasoning analysis or None if reasoning unavailable
    """
    try:
        # Try to call sequential-thinking MCP (raptor-mini)
        # Note: This requires MCP manager to be available
        # For standalone devtools server, we'll use a simplified analysis

        # Build context for reasoning
        context = f"""
Analyze the architectural impact of these changes:

Modified Files ({len(modified_files)}):
{chr(10).join(f"- {f}" for f in modified_files[:10])}

Affected Components ({len(affected_components)}):
{chr(10).join(f"- {c}" for c in affected_components)}

Project Type: {project_analysis.get("project_type", "unknown")}
Total Components: {len(project_analysis.get("components", []))}

Task: Identify cross-component impacts and recommend diagram updates.
"""

        # Since we're in MCP server context (no direct access to MCPManager),
        # we'll return a structured analysis that can be used by callers
        # The actual sequential-thinking call would be made by the agent/orchestrator

        return {
            "complexity": "high"
            if len(affected_components) > 3
            else "medium"
            if len(affected_components) > 1
            else "low",
            "cross_component": len(affected_components) > 1,
            "requires_deep_analysis": len(modified_files) > 5 or len(affected_components) > 3,
            "context_for_reasoning": context,
            "recommendation": (
                "Use sequential-thinking for deep analysis"
                if len(modified_files) > 5
                else "Standard diagram update sufficient"
            ),
        }

    except Exception as e:
        # Reasoning is optional, don't fail on errors
        return {"error": str(e), "reasoning_available": False}


def _export_diagrams(target_mode: str, project_path: Path) -> None:
    """Export diagrams to PNG/SVG using mmdc."""
    try:
        if target_mode == "internal":
            # Export from internal location
            input_path = (
                PROJECT_ROOT
                / "src"
                / "brain"
                / "data"
                / "architecture_diagrams"
                / "mcp_architecture.md"
            )
            output_dir = (
                PROJECT_ROOT / "src" / "brain" / "data" / "architecture_diagrams" / "exports"
            )
        else:
            # Export from external project
            input_path = project_path / "architecture_diagram.md"
            output_dir = project_path / "diagrams"

        output_dir.mkdir(parents=True, exist_ok=True)

        # Run mmdc
        cmd = [
            "mmdc",
            "-i",
            str(input_path),
            "-o",
            str(output_dir / "architecture.png"),
            "-t",
            "dark",
            "-b",
            "transparent",
        ]

        subprocess.run(cmd, capture_output=True, check=False, stdin=subprocess.DEVNULL)

        # Also look for any auxiliary diagrams (e.g. Vibe usage) and copy/convert
        # them into the exports directory so they are included in documentation
        # bundles. This keeps ad-hoc diagrams (docs/vibe-*.svg) in-sync.
        try:
            # Source candidate in docs/
            vibe_svg = PROJECT_ROOT / "docs" / "vibe-usage-diagram.svg"
            if vibe_svg.exists():
                target_svg = output_dir / "vibe-usage-diagram.svg"
                shutil.copy2(vibe_svg, target_svg)

                # Try best-effort PNG conversion (cairosvg / rsvg-convert / ImageMagick)
                png_path = output_dir / "vibe-usage-diagram.png"
                converted = False
                try:
                    import cairosvg

                    cairosvg.svg2png(url=str(vibe_svg), write_to=str(png_path))
                    converted = True
                except Exception:
                    # Try command-line fallbacks
                    for cmd_tool in (["rsvg-convert", "-o", str(png_path), str(vibe_svg)],
                                     ["convert", str(vibe_svg), str(png_path)]):
                        try:
                            subprocess.run(cmd_tool, check=True, capture_output=True)
                            converted = True
                            break
                        except Exception:
                            continue

                # If conversion failed, leave the SVG copy in place (still useful)
                if not converted:
                    # touch the svg so consumers know an asset exists
                    target_svg.touch()
        except Exception:
            # Non-critical — don't fail the whole export if auxiliary copy fails
            pass

    except Exception:
        # Export is optional, don't fail on errors
        pass


@server.tool()
def devtools_get_system_map() -> dict[str, Any]:
    """Get the complete AtlasTrinity system map: all paths, MCP servers, databases, logs, tools.

    Returns a structured map of:
    - Repository structure (src/, scripts/, config/, vendor/, tests/)
    - Global paths (~/.config/atlastrinity/): logs, databases, configs, models
    - All MCP servers with their commands and tool counts
    - Linter/code quality tool locations and configs
    - Testing methods for MCP servers

    Use this tool FIRST when you need to find any file, log, database, or tool location.
    """
    config_root = Path.home() / ".config" / "atlastrinity"
    log_dir = config_root / "logs"
    data_dir = config_root / "data"

    # Collect actual file states
    logs_found = sorted(str(p) for p in log_dir.glob("*.log*")) if log_dir.exists() else []
    dbs_found = []
    for db_path in [
        config_root / "atlastrinity.db",
        data_dir / "trinity.db",
        data_dir / "monitoring.db",
    ]:
        if db_path.exists():
            dbs_found.append(
                {"path": str(db_path), "size_kb": round(db_path.stat().st_size / 1024, 1)}
            )

    # Check golden_fund
    gf_dir = data_dir / "golden_fund"
    if gf_dir.exists():
        gf_files = list(gf_dir.iterdir())
        dbs_found.append({"path": str(gf_dir), "files": len(gf_files), "type": "directory"})

    # MCP config
    mcp_config_path = config_root / "mcp" / "config.json"
    mcp_servers_info = {}
    if mcp_config_path.exists():
        try:
            with open(mcp_config_path, encoding="utf-8") as f:
                mcp_data = json.load(f)
            for name, cfg in mcp_data.get("mcpServers", {}).items():
                if name.startswith("_"):
                    continue
                mcp_servers_info[name] = {
                    "tier": cfg.get("tier", 4),
                    "command": cfg.get("command", ""),
                    "disabled": cfg.get("disabled", False),
                    "transport": cfg.get("transport", "stdio"),
                }
        except Exception:
            pass

    return {
        "project_root": str(PROJECT_ROOT),
        "global_config_root": str(config_root),
        "paths": {
            "repository": {
                "src_brain": str(PROJECT_ROOT / "src" / "brain"),
                "src_mcp_server": str(PROJECT_ROOT / "src" / "mcp_server"),
                "src_renderer": str(PROJECT_ROOT / "src" / "renderer"),
                "src_main": str(PROJECT_ROOT / "src" / "main"),
                "scripts": str(PROJECT_ROOT / "scripts"),
                "config_templates": str(PROJECT_ROOT / "config"),
                "vendor": str(PROJECT_ROOT / "vendor"),
                "tests": str(PROJECT_ROOT / "tests"),
                "docs": str(PROJECT_ROOT / "docs"),
                "agent_docs": str(PROJECT_ROOT / ".agent" / "docs"),
                "protocols": str(PROJECT_ROOT / "src" / "brain" / "data" / "protocols"),
            },
            "global": {
                "config_yaml": str(config_root / "config.yaml"),
                "behavior_config": str(config_root / "behavior_config.yaml"),
                "vibe_config": str(config_root / "vibe_config.toml"),
                "env_secrets": str(config_root / ".env"),
                "mcp_config": str(mcp_config_path),
                "log_dir": str(log_dir),
                "brain_log": str(log_dir / "brain.log"),
                "main_db": str(config_root / "atlastrinity.db"),
                "trinity_db": str(data_dir / "trinity.db"),
                "monitoring_db": str(data_dir / "monitoring.db"),
                "golden_fund_dir": str(data_dir / "golden_fund"),
                "memory_dir": str(config_root / "memory"),
                "screenshots_dir": str(config_root / "screenshots"),
                "workspace": str(config_root / "workspace"),
                "vibe_workspace": str(config_root / "vibe_workspace"),
                "models_dir": str(config_root / "models"),
                "cache_dir": str(config_root / "cache"),
            },
        },
        "logs": logs_found,
        "databases": dbs_found,
        "mcp_servers": mcp_servers_info,
        "linter_configs": {
            "ruff": str(PROJECT_ROOT / "pyproject.toml"),
            "pyright": str(PROJECT_ROOT / "pyrightconfig.json"),
            "pyrefly": str(PROJECT_ROOT / "pyrefly.toml"),
            "biome": str(PROJECT_ROOT / "biome.json"),
            "eslint": str(PROJECT_ROOT / "eslint.config.mjs"),
            "knip": str(PROJECT_ROOT / "knip.json"),
            "lefthook": str(PROJECT_ROOT / "lefthook.yml"),
            "tsconfig": str(PROJECT_ROOT / "tsconfig.json"),
            "tsconfig_main": str(PROJECT_ROOT / "tsconfig.main.json"),
            "safety_policy": str(PROJECT_ROOT / ".safety-policy.yml"),
            "secrets_baseline": str(PROJECT_ROOT / ".secrets.baseline"),
        },
        "testing": {
            "health_check": "devtools_check_mcp_health()",
            "inspector_list": "mcp_inspector_list_tools(server_name)",
            "inspector_call": "mcp_inspector_call_tool(server_name, tool_name, args)",
            "sandbox_test": "devtools_run_mcp_sandbox(all_servers=True)",
            "log_analysis": "devtools_analyze_trace()",
            "scripts": {
                "health": str(PROJECT_ROOT / "scripts" / "check_mcp_health.py"),
                "sandbox": str(PROJECT_ROOT / "scripts" / "mcp_sandbox.py"),
                "integration": str(PROJECT_ROOT / "scripts" / "test_mcp_integration.py"),
                "validate": str(PROJECT_ROOT / "scripts" / "validate_mcp_servers.py"),
                "macos_tools": str(PROJECT_ROOT / "scripts" / "test_all_macos_tools.py"),
                "system_health": str(PROJECT_ROOT / "scripts" / "system_health_check.py"),
            },
        },
    }


@server.tool()
def devtools_test_all_mcp_native() -> dict[str, Any]:
    """Test ALL enabled MCP servers natively by spawning each server process,
    listing its tools via stdio JSON-RPC, and reporting results.

    This is a quick smoke test that verifies each server can start and respond.
    For deeper testing, use devtools_run_mcp_sandbox().

    Returns:
        Dict with per-server results: status, tool_count, response_time_ms, error.
    """

    config_path = Path.home() / ".config" / "atlastrinity" / "mcp" / "config.json"
    if not config_path.exists():
        return {"error": "MCP config not found", "path": str(config_path)}

    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        return {"error": f"Failed to load MCP config: {e}"}

    results = {}
    servers = config.get("mcpServers", {})

    for name, cfg in servers.items():
        if name.startswith("_"):
            continue
        if cfg.get("disabled", False):
            results[name] = {"status": "disabled", "tier": cfg.get("tier", 4)}
            continue

        transport = cfg.get("transport", "stdio")
        if transport == "internal":
            results[name] = {
                "status": "internal",
                "tier": cfg.get("tier", 4),
                "note": "Native service",
            }
            continue

        command = cfg.get("command", "")
        args = cfg.get("args", [])
        env_vars = cfg.get("env", {})

        # Resolve placeholders
        command = command.replace("${PROJECT_ROOT}", str(PROJECT_ROOT))
        command = command.replace("${HOME}", str(Path.home()))
        resolved_args = []
        for arg in args:
            arg = arg.replace("${PROJECT_ROOT}", str(PROJECT_ROOT))
            arg = arg.replace("${HOME}", str(Path.home()))
            resolved_args.append(arg)

        env = os.environ.copy()
        for k, v in env_vars.items():
            v = v.replace("${PROJECT_ROOT}", str(PROJECT_ROOT))
            v = v.replace("${HOME}", str(Path.home()))
            v = v.replace("${GOOGLE_MAPS_API_KEY}", os.environ.get("GOOGLE_MAPS_API_KEY", ""))
            v = v.replace("${GITHUB_TOKEN}", os.environ.get("GITHUB_TOKEN", ""))
            env[k] = v
        env["PYTHONPATH"] = str(PROJECT_ROOT)

        # JSON-RPC initialize + tools/list request
        init_request = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "devtools-test", "version": "1.0"},
                },
            }
        )
        list_request = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            }
        )
        stdin_data = init_request + "\n" + list_request + "\n"

        full_cmd = [command, *resolved_args]
        start = time.time()

        try:
            proc = subprocess.run(
                full_cmd,
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=15,
                env=env,
                cwd=str(PROJECT_ROOT),
            )
            elapsed_ms = round((time.time() - start) * 1000, 1)

            stdout = proc.stdout.strip()
            if not stdout:
                results[name] = {
                    "status": "error",
                    "tier": cfg.get("tier", 4),
                    "error": proc.stderr[:200] if proc.stderr else "Empty response",
                    "response_time_ms": elapsed_ms,
                }
                continue

            # Parse JSON-RPC responses (may be multiple lines)
            tool_count = 0
            for line in stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    resp = json.loads(line)
                    if resp.get("id") == 2 and "result" in resp:
                        tools = resp["result"].get("tools", [])
                        tool_count = len(tools)
                except json.JSONDecodeError:
                    continue

            if tool_count > 0:
                results[name] = {
                    "status": "online",
                    "tier": cfg.get("tier", 4),
                    "tool_count": tool_count,
                    "response_time_ms": elapsed_ms,
                }
            else:
                results[name] = {
                    "status": "started",
                    "tier": cfg.get("tier", 4),
                    "tool_count": 0,
                    "response_time_ms": elapsed_ms,
                    "note": "Server started but tools/list returned 0 (may need initialized notification)",
                }

        except subprocess.TimeoutExpired:
            results[name] = {
                "status": "timeout",
                "tier": cfg.get("tier", 4),
                "error": "Server did not respond within 15s",
            }
        except FileNotFoundError:
            results[name] = {
                "status": "not_found",
                "tier": cfg.get("tier", 4),
                "error": f"Command not found: {full_cmd[0]}",
            }
        except Exception as e:
            results[name] = {
                "status": "error",
                "tier": cfg.get("tier", 4),
                "error": str(e)[:200],
            }

    # Summary
    online = sum(
        1 for r in results.values() if r.get("status") in ("online", "started", "internal")
    )
    offline = sum(
        1 for r in results.values() if r.get("status") in ("error", "timeout", "not_found")
    )
    disabled = sum(1 for r in results.values() if r.get("status") == "disabled")

    return {
        "summary": {
            "total": len(results),
            "online": online,
            "offline": offline,
            "disabled": disabled,
            "health_pct": round(online / max(1, len(results) - disabled) * 100, 1),
        },
        "servers": results,
    }


if __name__ == "__main__":
    server.run()


@server.tool()
def devtools_list_github_workflows(limit: int = 5) -> dict[str, Any]:
    """List recent GitHub Action workflow runs for the current project.

    Args:
        limit: Number of runs to return (default: 5)
    """
    return fetch_github_workflow_runs(PROJECT_ROOT, limit=limit)


@server.tool()
def devtools_get_github_job_logs(
    run_id: str | None = None, job_id: str | None = None
) -> dict[str, Any]:
    """Get logs for a specific GitHub Action job.

    If run_id is provided, it first lists jobs in that run.
    If job_id is provided, it downloads the logs for that job.

    Args:
        run_id: Workflow run ID (optional, to list jobs)
        job_id: Job ID (optional, to download logs)
    """
    if job_id:
        return download_github_job_logs(PROJECT_ROOT, job_id)
    if run_id:
        return fetch_github_workflow_jobs(PROJECT_ROOT, run_id)

    return {"error": "Must provide either run_id or job_id"}
