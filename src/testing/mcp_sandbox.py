"""AtlasTrinity MCP Testing Sandbox

Isolated testing environment for ALL MCP servers and tools with:
- Safe sandbox directory for destructive operations
- LLM-generated realistic test scenarios
- Multi-tool chaining for natural testing flows
- Auto-fix integration via Vibe MCP

Usage:
    python scripts/mcp_sandbox.py --server filesystem --full
    python scripts/mcp_sandbox.py --server memory --chain 3
    python scripts/mcp_sandbox.py --all --autofix
    python scripts/mcp_sandbox.py --all --full --json
"""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast

# Add project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.brain.config.config_loader import config  # noqa: E402
from src.providers.factory import create_llm  # noqa: E402


class SimpleWindsurfLLM:
    def __init__(self, api_key=None, model="deepseek-v3"):
        # Priority: WINDSURF_API_KEY -> COPILOT_API_KEY -> None
        self.api_key = api_key or os.getenv("WINDSURF_API_KEY") or os.getenv("COPILOT_API_KEY")
        self.model = model
        self.api_base = "https://server.self-serve.windsurf.com"

        # If using Copilot key, switch to Copilot endpoint
        if os.getenv("COPILOT_API_KEY") and not os.getenv("WINDSURF_API_KEY"):
            self.api_base = "https://api.githubcopilot.com"
            self.model = "gpt-4o"

    async def ainvoke(self, prompt: str) -> Any:
        import httpx

        if not self.api_key:
            raise ValueError("No API key found (WINDSURF_API_KEY or COPILOT_API_KEY)")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Use appropriate endpoint based on API key
        if "windsurf" in self.api_base.lower():
            url = f"{self.api_base}/v1/chat/completions"
        else:
            url = f"{self.api_base}/chat/completions"

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "response_format": {"type": "json_object"} if "JSON" in prompt else None,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            # Mock object to match LangChain interface slightly
            class MockResponse:
                def __init__(self, content):
                    self.content = content

                def __str__(self):
                    return self.content

            r = MockResponse(content)
            return r


# Sandbox configuration
SANDBOX_ROOT = Path("/tmp/atlas_sandbox")
SANDBOX_HOME = SANDBOX_ROOT / "home"
SANDBOX_FS = SANDBOX_ROOT / "fs"


class Colors:
    """ANSI color codes for terminal output."""

    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ENDC = "\033[0m"


def setup_sandbox() -> Path:
    """Create isolated sandbox environment."""
    # Clean up any previous sandbox
    if SANDBOX_ROOT.exists():
        shutil.rmtree(SANDBOX_ROOT)

    # Create sandbox directories
    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    SANDBOX_HOME.mkdir(parents=True, exist_ok=True)
    SANDBOX_FS.mkdir(parents=True, exist_ok=True)

    # Create some test files for read operations
    test_file = SANDBOX_HOME / "test_file.txt"
    test_file.write_text("This is a sandbox test file.\nLine 2.\nLine 3.\n")

    test_dir = SANDBOX_HOME / "test_dir"
    test_dir.mkdir(exist_ok=True)
    (test_dir / "nested_file.txt").write_text("Nested content")

    return SANDBOX_ROOT


def cleanup_sandbox():
    """Remove sandbox after testing."""
    if SANDBOX_ROOT.exists():
        shutil.rmtree(SANDBOX_ROOT)


def sandbox_path(original_path: str) -> str:
    """Convert original path to sandbox path for safety."""
    path = Path(original_path).expanduser()

    # Map home directory to sandbox home
    home = Path.home()
    if str(path).startswith(str(home)):
        relative = path.relative_to(home)
        return str(SANDBOX_HOME / relative)

    # Map everything else to sandbox fs
    if path.is_absolute():
        return str(SANDBOX_FS / str(path).lstrip("/"))

    return str(SANDBOX_FS / original_path)


def load_mcp_config() -> dict:
    """Load MCP configuration."""
    config_path = Path.home() / ".config" / "atlastrinity" / "mcp" / "config.json"
    if not config_path.exists():
        return {}
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def run_inspector_cmd(
    server_name: str,
    method: str,
    extra_args: list[str] | None = None,
    timeout: float = 30.0,
) -> dict:
    """Run MCP Inspector CLI command and return parsed result."""
    config = load_mcp_config()
    server_config = config.get("mcpServers", {}).get(server_name)

    if not server_config:
        return {"error": f"Server '{server_name}' not found in configuration"}

    command = server_config.get("command", "")
    args = server_config.get("args", [])
    env_vars = server_config.get("env", {})

    # Resolve variables
    resolved_args = []
    for arg in args:
        arg = arg.replace("${HOME}", str(Path.home()))
        arg = arg.replace("${PROJECT_ROOT}", str(PROJECT_ROOT))
        resolved_args.append(arg)

    resolved_command = command.replace("${HOME}", str(Path.home()))
    resolved_command = resolved_command.replace("${PROJECT_ROOT}", str(PROJECT_ROOT))

    # Build inspector command
    inspector_cmd = [
        "npx",
        "@modelcontextprotocol/inspector",
        "--cli",
        resolved_command,
        *resolved_args,
        "--method",
        method,
    ]

    if extra_args:
        inspector_cmd.extend(extra_args)

    # Prepare environment with virtual environment support
    env = os.environ.copy()

    # Ensure we use the same Python environment as the main program
    venv_python = str(PROJECT_ROOT / ".venv" / "bin" / "python")
    if Path(venv_python).exists():
        # Update PATH to include venv bin directory
        venv_bin = str(PROJECT_ROOT / ".venv" / "bin")
        env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"
        env["VIRTUAL_ENV"] = str(PROJECT_ROOT / ".venv")
        # print(f"{Colors.CYAN}🔧 Using virtual environment: {PROJECT_ROOT / '.venv'}{Colors.ENDC}")

    for k, v in env_vars.items():
        val = v.replace("${GITHUB_TOKEN}", env.get("GITHUB_TOKEN", ""))
        val = v.replace("${HOME}", str(Path.home()))
        val = v.replace("${PROJECT_ROOT}", str(PROJECT_ROOT))
        env[k] = val

    try:
        result = subprocess.run(
            inspector_cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
            check=False,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr.strip() or f"Exit code {result.returncode}",
            }

        stdout = result.stdout.strip()
        if not stdout:
            return {"success": True, "data": None}

        try:
            return {"success": True, "data": json.loads(stdout)}
        except json.JSONDecodeError:
            return {"success": True, "raw_output": stdout}

    except subprocess.TimeoutExpired:
        return {"error": f"Timeout after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


async def generate_test_scenario(
    server_name: str,
    tools: list[dict],
    chain_length: int = 1,
    use_sandbox: bool = True,
) -> dict:
    """Use LLM to generate a realistic test scenario.

    Args:
        server_name: Name of the MCP server
        tools: List of available tools with schemas
        chain_length: Number of tools to chain in the scenario
        use_sandbox: Whether to use sandbox paths

    Returns:
        Dict with task description, steps, and expected outcome
    """

    # Select tools for the chain
    selected_tools = tools[:chain_length] if len(tools) >= chain_length else tools

    tools_desc = "\n".join(
        [f"- {t.get('name')}: {t.get('description', '')[:100]}" for t in selected_tools]
    )

    sandbox_note = (
        f"""
IMPORTANT: Use sandbox paths for ALL file operations:
- Instead of /Users/{{USER}}/... use {SANDBOX_HOME}/...
- Instead of /tmp/... use {SANDBOX_FS}/tmp/...
- Create test files in {SANDBOX_HOME}/
"""
        if use_sandbox
        else ""
    )

    prompt = f"""You are a QA engineer testing MCP server '{server_name}'.

Available tools to test:
{tools_desc}

{sandbox_note}

Create a realistic test scenario that uses {"these tools in sequence" if chain_length > 1 else "this tool"}.
The scenario should be practical and verifiable.

Return ONLY a JSON object with this structure:
{{
    "task": "Brief description of what we're testing",
    "steps": [
        {{"tool": "tool_name", "args": {{"arg1": "value1"}}, "expected": "what should happen"}}
    ],
    "final_check": "How to verify the entire scenario succeeded"
}}

Generate the test scenario:"""

    response_text = ""
    try:
        # Ensure system config is loaded (this loads .env from global config correctly)
        from src.brain.config.config_loader import config
        # Force load if not already done (singleton handles it, but good to be sure)

        try:
            # Get model from config, fallback to gpt-4o if not set
            llm = create_llm(model_name=config.get("models.sandbox"))
            response = await llm.ainvoke(prompt)
        except Exception:
            # Fallback to Windsurf
            llm = SimpleWindsurfLLM()
            response = await llm.ainvoke(prompt)

        response_text = response.content if hasattr(response, "content") else str(response)

        # Handle list response
        if isinstance(response_text, list):
            response_text = response_text[0] if response_text else ""
        response_text = str(response_text).strip()

        # Extract JSON from response
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            response_text = response_text.removeprefix("json")

        scenario = json.loads(response_text.strip())
        return {"success": True, "scenario": scenario}

    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse scenario JSON: {e}", "raw": response_text[:200]}
    except Exception as e:
        return {"error": f"Provider error: {e}"}


async def execute_test_step(
    server_name: str,
    step: dict,
    use_sandbox: bool = True,
) -> dict:
    """Execute a single test step and return result."""
    tool_name = step.get("tool")
    args = step.get("args", {})
    expected = step.get("expected", "")

    # Apply sandbox path transformation for file-related args
    if use_sandbox:
        sandboxed_args = {}
        for key, value in args.items():
            if (
                isinstance(value, str)
                and ("path" in key.lower() or "file" in key.lower() or "dir" in key.lower())
            ) or (isinstance(value, str) and value.startswith("/")):
                sandboxed_args[key] = sandbox_path(value)
            else:
                sandboxed_args[key] = value
        args = sandboxed_args

    # Build tool call args
    extra_args = ["--tool-name", tool_name]
    for key, value in args.items():
        if isinstance(value, dict | list):
            extra_args.extend(["--tool-arg", f"{key}={json.dumps(value)}"])
        elif value is not None:
            extra_args.extend(["--tool-arg", f"{key}={value}"])

    # Execute
    result = run_inspector_cmd(server_name, "tools/call", cast("list[str]", extra_args))

    return {
        "tool": tool_name,
        "args": args,
        "expected": expected,
        "result": result,
        "success": result.get("success", False) and not result.get("error"),
    }


async def analyze_test_result(
    step_result: dict,
    scenario_context: str,
) -> dict:
    """Use LLM to determine if test step passed."""

    # Ensure config loaded

    result_str = json.dumps(step_result.get("result", {}), indent=2, ensure_ascii=False)[:800]

    # ... prompt definition omitted for brevity ...
    prompt = f"""Analyze this MCP tool test result.

Context: {scenario_context}
Tool: {step_result.get("tool")}
Args: {json.dumps(step_result.get("args", {}))}
Expected: {step_result.get("expected", "N/A")}

Actual Result:
{result_str}

Did this test PASS or FAIL? Consider:
1. Did the tool execute without errors?
2. Does the output match the expected behavior?
3. Any warnings or unexpected behavior?

Respond with: PASS or FAIL followed by a brief explanation (max 30 words)."""

    try:
        try:
            # Get model from config, fallback to gpt-4o if not set
            llm = create_llm(model_name=config.get("models.sandbox"))
            response = await llm.ainvoke(prompt)
        except Exception:
            # Fallback to Windsurf
            llm = SimpleWindsurfLLM()
            response = await llm.ainvoke(prompt)

        verdict = response.content if hasattr(response, "content") else str(response)

        if isinstance(verdict, list):
            verdict = verdict[0] if verdict else ""
        verdict = str(verdict).strip()

        passed = verdict.upper().startswith("PASS")
        return {
            "passed": passed,
            "verdict": verdict,
        }
    except Exception as e:
        return {
            "passed": step_result.get("success", False),
            "verdict": f"LLM analysis failed: {e}",
        }


async def run_scenario(
    server_name: str,
    scenario: dict,
    use_sandbox: bool = True,
    verbose: bool = False,
) -> dict:
    """Execute a complete test scenario."""
    task = scenario.get("task", "Unknown task")
    steps = scenario.get("steps", [])

    results = {
        "task": task,
        "steps_total": len(steps),
        "steps_passed": 0,
        "steps_failed": 0,
        "step_results": [],
        "final_verdict": "unknown",
    }

    for _, step in enumerate(steps):
        if verbose:
            pass

        # Execute step
        step_result = await execute_test_step(server_name, step, use_sandbox)

        # Analyze result
        analysis = await analyze_test_result(step_result, task)
        step_result["analysis"] = analysis

        results["step_results"].append(step_result)

        if analysis.get("passed"):
            results["steps_passed"] += 1
            if verbose:
                pass
        else:
            results["steps_failed"] += 1
            if verbose:
                pass

    # Final verdict
    if results["steps_failed"] == 0:
        results["final_verdict"] = "PASS"
    elif results["steps_passed"] > results["steps_failed"]:
        results["final_verdict"] = "PARTIAL"
    else:
        results["final_verdict"] = "FAIL"

    return results


async def auto_fix_failure(
    server_name: str,
    step_result: dict,
) -> dict:
    """Attempt to fix a failed test step via Vibe MCP."""
    from src.brain.mcp.mcp_manager import mcp_manager

    error_context = json.dumps(
        {
            "server": server_name,
            "tool": step_result.get("tool"),
            "args": step_result.get("args"),
            "error": step_result.get("result", {}).get("error"),
            "output": str(step_result.get("result", {}))[:500],
        },
        indent=2,
    )

    try:
        result = await mcp_manager.call_tool(
            "vibe",
            "vibe_analyze_error",
            {
                "error_message": f"MCP tool test failed: {step_result.get('tool')}",
                "auto_fix": True,
                "log_context": error_context,
            },
        )
        return {
            "attempted": True,
            "result": str(result)[:300],
        }
    except Exception as e:
        return {
            "attempted": True,
            "error": str(e),
        }


async def test_server_full(
    server_name: str,
    chain_length: int = 1,
    use_sandbox: bool = True,
    autofix: bool = False,
    verbose: bool = False,
) -> dict:
    """Test ALL tools on a server with LLM-generated scenarios."""
    report = {
        "server": server_name,
        "mode": "full_sandbox_test",
        "chain_length": chain_length,
        "tools_tested": 0,
        "scenarios_passed": 0,
        "scenarios_failed": 0,
        "scenario_results": [],
        "timestamp": datetime.now().isoformat(),
    }

    # Get tools list
    tools_result = run_inspector_cmd(server_name, "tools/list")
    if tools_result.get("error"):
        report["error"] = tools_result["error"]
        return report

    tools_data = tools_result.get("data", {})
    tools_list = tools_data.get("tools", tools_data) if isinstance(tools_data, dict) else tools_data

    if not isinstance(tools_list, list):
        report["error"] = "Could not parse tools list"
        return report

    report["total_tools"] = len(tools_list)

    # Group tools for chained scenarios
    if chain_length > 1:
        # Create chains of tools
        tool_groups = []
        for i in range(0, len(tools_list), chain_length):
            group = tools_list[i : i + chain_length]
            if group:
                tool_groups.append(group)
    else:
        # Each tool individually
        tool_groups = [[t] for t in tools_list]

    for group in tool_groups:
        group_names = [t.get("name") for t in group]
        if verbose:
            pass

        # Generate scenario
        scenario_result = await generate_test_scenario(
            server_name, group, chain_length=len(group), use_sandbox=use_sandbox
        )

        if scenario_result.get("error"):
            report["scenario_results"].append(
                {
                    "tools": group_names,
                    "error": scenario_result["error"],
                    "verdict": "SKIP",
                }
            )
            continue

        scenario = scenario_result.get("scenario", {})

        # Execute scenario
        run_result = await run_scenario(server_name, scenario, use_sandbox, verbose)
        run_result["tools"] = group_names

        report["scenario_results"].append(run_result)
        report["tools_tested"] += len(group)

        if run_result["final_verdict"] == "PASS":
            report["scenarios_passed"] += 1
        else:
            report["scenarios_failed"] += 1

            # Auto-fix if requested
            if autofix and run_result.get("step_results"):
                for step_result in run_result["step_results"]:
                    if not step_result.get("analysis", {}).get("passed"):
                        fix_result = await auto_fix_failure(server_name, step_result)
                        step_result["autofix"] = fix_result

    return report


def print_sandbox_report(reports: list[dict], total_time: float):
    """Print human-readable sandbox test report."""

    sum(r.get("scenarios_passed", 0) for r in reports)
    sum(r.get("scenarios_failed", 0) for r in reports)
    sum(r.get("tools_tested", 0) for r in reports)

    for report in reports:
        report["server"]
        passed = report.get("scenarios_passed", 0)
        failed = report.get("scenarios_failed", 0)
        report.get("tools_tested", 0)
        report.get("total_tools", 0)

        if report.get("error"):
            continue

        if (failed == 0 and passed > 0) or passed > failed:
            pass
        else:
            pass


async def main_async(args):
    """Async main entry point."""
    import time

    start_time = time.time()

    # Helper to only print in non-JSON mode
    def log(msg: str):
        if not args.json:
            pass

    # Setup sandbox
    if not args.no_sandbox:
        log(f"{Colors.CYAN}🔧 Setting up sandbox at {SANDBOX_ROOT}...{Colors.ENDC}")
        setup_sandbox()

    # Load configuration
    config = load_mcp_config()
    if not config:
        if args.json:
            pass
        else:
            pass
        return 1

    # Get servers to test
    servers = config.get("mcpServers", {})
    if args.server:
        if args.server not in servers:
            if args.json:
                pass
            else:
                pass
            return 1
        servers = {args.server: servers[args.server]}

    # Filter out disabled and internal servers
    active_servers = [
        name
        for name, cfg in servers.items()
        if not name.startswith("_") and not cfg.get("disabled", False)
    ]

    if args.all:
        # Test all servers
        pass
    elif not args.server:
        if args.json:
            pass
        else:
            pass
        return 1

    log(f"{Colors.BOLD}{Colors.CYAN}🧪 Starting MCP Sandbox Tests...{Colors.ENDC}\n")

    reports = []
    for server_name in active_servers:
        log(f"{Colors.BOLD}▶ {server_name}{Colors.ENDC}")
        report = await test_server_full(
            server_name,
            chain_length=args.chain,
            use_sandbox=not args.no_sandbox,
            autofix=args.autofix,
            verbose=not args.json,
        )
        reports.append(report)

    total_time = time.time() - start_time

    # Cleanup sandbox
    if not args.no_sandbox and not args.keep_sandbox:
        cleanup_sandbox()

    # Output
    if args.json:
        _ = {
            "mode": "sandbox_full_test",
            "timestamp": datetime.now().isoformat(),
            "test_time_seconds": round(total_time, 2),
            "sandbox_path": str(SANDBOX_ROOT),
            "total_servers": len(reports),
            "total_passed": sum(r.get("scenarios_passed", 0) for r in reports),
            "total_failed": sum(r.get("scenarios_failed", 0) for r in reports),
            "reports": reports,
        }
    else:
        print_sandbox_report(reports, total_time)

    return 0


def main():
    parser = argparse.ArgumentParser(description="MCP Testing Sandbox - Full Coverage")
    parser.add_argument("--server", type=str, help="Test specific server")
    parser.add_argument("--all", action="store_true", help="Test all enabled servers")
    parser.add_argument(
        "--full", action="store_true", help="Test ALL tools (alias for default behavior)"
    )
    parser.add_argument(
        "--chain", type=int, default=1, help="Chain length for multi-tool scenarios (1-5)"
    )
    parser.add_argument("--autofix", action="store_true", help="Auto-fix failures via Vibe")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--no-sandbox", action="store_true", help="Don't use sandbox (DANGEROUS)")
    parser.add_argument(
        "--keep-sandbox", action="store_true", help="Don't cleanup sandbox after test"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # Validate chain length
    args.chain = max(1, min(5, args.chain))

    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
