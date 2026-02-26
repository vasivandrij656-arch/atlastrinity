"""
System Health Check Script for AtlasTrinity
Checks all critical components and reports issues
"""

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Set CONFIG_ROOT
os.environ["CONFIG_ROOT"] = os.path.expanduser("~/.config/atlastrinity")

# Import yaml at module level
try:
    import yaml
except ImportError:
    yaml = None


def check_yaml_syntax():
    """Check YAML syntax in behavior config"""

    if yaml is None:
        return {"status": "error", "message": "yaml module not available"}

    config_path = os.path.expanduser("~/.config/atlastrinity/behavior_config.yaml")
    if not os.path.exists(config_path):
        return {"status": "error", "message": "behavior_config.yaml not found"}

    try:
        with open(config_path) as f:
            yaml.safe_load(f)
        return {"status": "ok", "message": "YAML syntax is valid"}
    except yaml.YAMLError as e:
        return {"status": "error", "message": f"YAML syntax error: {e}"}
    except Exception as e:
        return {"status": "error", "message": f"Error reading YAML: {e}"}


def check_mcp_servers():
    """Check MCP server configuration"""

    config_path = os.path.expanduser("~/.config/atlastrinity/mcp/config.json")
    if not os.path.exists(config_path):
        return {"status": "error", "message": "MCP config.json not found"}

    try:
        with open(config_path) as f:
            content = f.read()
            # Remove comments that start with "_comment"
            content = re.sub(r'"_comment[^"]*":\s*"[^"]*",?\s*', "", content)
            config = json.loads(content)

        servers = config.get("mcpServers", {})
        disabled_count = sum(
            1 for s in servers.values() if isinstance(s, dict) and s.get("disabled", False)
        )
        enabled_count = len([s for s in servers.values() if isinstance(s, dict)]) - disabled_count

        return {
            "status": "ok",
            "message": f"Found {len(servers)} servers ({enabled_count} enabled, {disabled_count} disabled)",
        }
    except Exception as e:
        return {"status": "error", "message": f"Error reading MCP config: {e}"}


def check_database():
    """Check database connectivity"""

    try:
        from src.brain.memory.db.manager import db_manager

        async def test_db():
            try:
                await db_manager.initialize()
                if not db_manager.available:
                    return {"status": "error", "message": "Database not available"}

                session = await db_manager.get_session()
                await session.close()
                return {"status": "ok", "message": "Database connection successful"}
            except Exception as e:
                return {"status": "error", "message": f"Database error: {e}"}

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(test_db())
        finally:
            loop.close()
    except Exception as e:
        return {"status": "error", "message": f"Database import error: {e}"}


def check_python_deps():
    """Check Python dependencies"""

    critical_deps = ["sqlalchemy", "yaml", "asyncio", "pathlib"]
    missing_deps = []

    for dep in critical_deps:
        try:
            if dep == "yaml":
                pass
            else:
                __import__(dep)
        except ImportError:
            missing_deps.append(dep)

    if missing_deps:
        return {"status": "error", "message": f"Missing dependencies: {missing_deps}"}
    return {"status": "ok", "message": "All critical dependencies available"}


def check_vibe_server():
    """Check Vibe server status"""

    vibe_binary = os.path.expanduser("~/.local/bin/vibe")
    if not os.path.exists(vibe_binary):
        return {"status": "warning", "message": "Vibe binary not found at ~/.local/bin/vibe"}

    try:
        result = subprocess.run(
            [vibe_binary, "--version"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return {"status": "ok", "message": f"Vibe server available: {result.stdout.strip()}"}
        return {"status": "error", "message": f"Vibe server error: {result.stderr}"}
    except Exception as e:
        return {"status": "error", "message": f"Vibe server check failed: {e}"}


def check_memory_usage():
    """Check system memory usage"""

    try:
        import psutil

        memory = psutil.virtual_memory()
        if memory.percent > 90:
            return {"status": "warning", "message": f"High memory usage: {memory.percent}%"}
        return {"status": "ok", "message": f"Memory usage: {memory.percent}%"}
    except ImportError:
        return {"status": "warning", "message": "psutil not available - cannot check memory"}
    except Exception as e:
        return {"status": "error", "message": f"Memory check failed: {e}"}


def check_recent_errors():
    """Check for recent errors in logs"""

    log_dir = os.path.expanduser("~/.config/atlastrinity/logs")
    if not os.path.exists(log_dir):
        return {"status": "warning", "message": "Log directory not found"}

    brain_log = os.path.join(log_dir, "brain.log")
    if not os.path.exists(brain_log):
        return {"status": "warning", "message": "Brain log not found"}

    try:
        # Read last 50 lines of brain log
        with open(brain_log) as f:
            lines = f.readlines()[-50:]

        error_count = sum(1 for line in lines if "ERROR" in line.upper())
        if error_count > 5:
            return {"status": "warning", "message": f"Found {error_count} errors in recent logs"}
        return {"status": "ok", "message": f"Found {error_count} errors in recent logs"}
    except Exception as e:
        return {"status": "error", "message": f"Log check failed: {e}"}


def main():
    """Run all health checks"""

    checks = [
        ("YAML Configuration", check_yaml_syntax),
        ("MCP Servers", check_mcp_servers),
        ("Database", check_database),
        ("Python Dependencies", check_python_deps),
        ("Vibe Server", check_vibe_server),
        ("System Resources", check_memory_usage),
        ("Recent Errors", check_recent_errors),
    ]

    results = {}
    issues_found = 0

    for name, check_func in checks:
        try:
            result = check_func()
            results[name] = result

            ("✅" if result["status"] == "ok" else "⚠️" if result["status"] == "warning" else "❌")

            if result["status"] in ["error", "warning"]:
                issues_found += 1

        except Exception as e:
            results[name] = {"status": "error", "message": f"Check failed: {e}"}
            issues_found += 1

    if issues_found > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
