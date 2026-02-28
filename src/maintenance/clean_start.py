import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Signatures of processes to kill
# We match against the full command line
TARGET_SIGNATURES = [
    "brain.server",
    "src/maintenance/watch_config.py",
    "src.mcp_server.vibe_server",  # Vibe Python Server
    "copilot_vibe_proxy.py",  # Copilot Proxy
    "vibe_windsurf_proxy.py",  # Windsurf Proxy
    ".local/bin/vibe",  # Vibe CLI Binary
    "vibe_cli",  # Vibe CLI Process Identity
    "electron .",  # Main Electron App
    "vite",  # Vite Renderer Dev Server
    "server-filesystem",  # @modelcontextprotocol/server-filesystem
    "server-sequential-thinking",  # @modelcontextprotocol/server-sequential-thinking
    "vendor/XcodeBuildMCP",  # Unified XcodeBuild Hub (Node)
    "chrome-devtools-mcp",  # Chrome DevTools Protocol MCP
    "server-puppeteer",  # @modelcontextprotocol/server-puppeteer
    "c7-mcp-server",  # Context7 Documentation Server
    "server-github",  # @modelcontextprotocol/server-github
    "mcp-server-macos-use",  # Native macOS-use Binary
    "mcp-server-googlemaps",  # Native Google Maps Binary
    "memory_server",  # Memory Graph Server (Python)
    "graph_server",  # Graph Visualization Server (Python)
    "whisper_server",  # Voice transcription Server (Python)
    "devtools_server",  # System Self-Analysis Server (Python)
    "duckduckgo_search_server",  # DDG Search Server (Python)
    "golden_fund/server",  # Golden Fund Server (Python)
    "redis_server",  # Redis State Server (Python)
    "data_analysis_server",  # Pandas Analysis Server (Python)
    "postgres_server",  # Postgres DB Server (Python)
    "react_devtools_mcp.js",  # React DevTools MCP (Node)
    "uvicorn",  # FastAPI/Uvicorn hosts
]

# Ports to check and free
TARGET_PORTS = [
    8000,  # Brain API
    3000,
    3001,  # UI / Vite
    8080,
    8085,
    8086,
    8088,
    8090,  # Vibe, Proxies, Internal
    9222,  # Chrome Debugging
]


def get_process_list() -> list[tuple[int, str]]:
    """Get list of running processes with PIDs and command lines."""
    try:
        # ps -eo pid,command
        result = subprocess.run(
            ["ps", "-eo", "pid,command"], capture_output=True, text=True, check=True
        )
        stdout: str = result.stdout
        lines: list[str] = stdout.strip().split("\n")
        processes: list[tuple[int, str]] = []
        for i in range(1, len(lines)):  # Skip header
            line: str = lines[i]
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                processes.append((int(parts[0]), parts[1]))
        return processes
    except Exception:
        return []


def kill_process(pid, name):
    """Try to kill a process gracefully, then forcefully."""
    try:
        # Skip self
        if pid == os.getpid():
            return

        os.kill(pid, signal.SIGTERM)

    except ProcessLookupError:
        pass
    except PermissionError:
        pass
    except Exception:
        pass


def get_ancestor_pids() -> set[int]:
    """Get the set of all ancestor process IDs."""
    ancestors = set()
    try:
        current_pid = os.getppid()  # Start with parent
        while current_pid > 0:
            ancestors.add(current_pid)
            # Find grandparent of current_pid
            result = subprocess.run(
                ["ps", "-o", "ppid=", "-p", str(current_pid)],
                capture_output=True,
                text=True,
                check=True,
            )
            ppid_str = result.stdout.strip()
            if not ppid_str:
                break
            current_pid = int(ppid_str)
            if current_pid in ancestors or current_pid == 0:
                break
    except Exception:
        pass
    return ancestors


def stop_brew_services():
    """Stop brew-managed services before killing processes to prevent auto-restart."""
    brew_services = []  # Redis should remain running for development
    for service in brew_services:
        try:
            result = subprocess.run(
                ["brew", "services", "list"],
                capture_output=True,
                text=True,
                check=False,
            )
            if (
                service in result.stdout
                and "started" in result.stdout.split(service)[1].split("\n")[0]
            ):
                print(f"  • {Colors.CYAN}Stopping brew service:{Colors.ENDC} {service}")
                subprocess.run(
                    ["brew", "services", "stop", service], capture_output=True, check=False
                )
                time.sleep(0.5)
        except Exception:
            pass


def main():

    # Stop brew-managed services first to prevent auto-restart after kill
    stop_brew_services()

    processes: list[tuple[int, str]] = get_process_list()
    terminated_pids: list[int] = []
    ancestors = get_ancestor_pids()
    my_pid = os.getpid()

    # Process cleanup
    for item in processes:
        pid: int = item[0]
        cmd: str = item[1]

        # Never kill self or any parents/ancestors
        if pid == my_pid or pid in ancestors:
            continue

        # Check against signatures
        if any(sig in cmd for sig in TARGET_SIGNATURES):
            # Double check it's not us
            if "clean_start.py" in cmd:
                continue

            print(f"  • {Colors.YELLOW}Terminating process:{Colors.ENDC} {pid} ({cmd[:60]}...)")
            kill_process(pid, cmd)
            terminated_pids.append(pid)

    # Port cleanup (lsof)
    for port in TARGET_PORTS:
        try:
            # lsof -t -i:PORT
            res = subprocess.run(["lsof", "-t", f"-i:{port}"], capture_output=True, text=True)
            pids = res.stdout.strip().split()
            for p in pids:
                if p:
                    pid = int(p)
                    if pid != my_pid and pid not in ancestors:
                        try:
                            print(f"  • {Colors.RED}Freeing port {port}:{Colors.ENDC} PID {pid}")
                            os.kill(pid, signal.SIGKILL)
                            terminated_pids.append(pid)
                        except ProcessLookupError:
                            pass
                        except Exception:
                            pass
        except Exception:
            pass

    killed_count: int = len(terminated_pids)
    if killed_count > 0:
        print(f"✅ {Colors.GREEN}Cleaned up {killed_count} lingering processes.{Colors.ENDC}")
        # Brief pause to let OS reclaim resources
        time.sleep(1)
    else:
        pass


class Colors:
    """ANSI color codes for terminal output."""

    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    ENDC = "\033[0m"


if __name__ == "__main__":
    main()
