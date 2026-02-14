"""Vibe MCP Server - Hyper-Refactored Implementation

This server wraps the Mistral Vibe CLI in MCP-compliant programmatic mode.
Fully aligned with official Mistral Vibe documentation and configuration.

Key Features:
- Full configuration support (providers, models, agents, tool permissions)
- 17 MCP tools covering all Vibe capabilities
- Streaming output with real-time notifications
- Proper error handling and resource cleanup
- Session persistence and resumption
- Dynamic model/provider switching

Based on official Mistral Vibe documentation:
https://docs.mistral.ai/vibe/configuration/

Author: AtlasTrinity Team
Date: 2026-01-20
Version: 3.0 (Hyper-Refactored)
"""

from __future__ import annotations

import asyncio
import atexit
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from re import Pattern
from typing import Any, Literal, cast
from unittest.mock import MagicMock

from dotenv import load_dotenv
from mcp.server import FastMCP
from mcp.server.fastmcp import Context
from sqlalchemy import text

from src.brain.memory.db.manager import db_manager
from src.brain.monitoring.utils.security import mask_sensitive_data

from .vibe_config import (
    AgentMode,
    ProviderConfig,
    VibeConfig,
)

# Import CopilotLLM for token exchange (from project root)
sys.path.append(str(Path(__file__).parent.parent.parent))  # Add project root to path
try:
    from src.providers.copilot import CopilotLLM
except ImportError:
    CopilotLLM = None  # Graceful fallback if import fails

# =============================================================================
# SETUP: Logging, Configuration, Constants
# =============================================================================

# ANSI escape code pattern for stripping colors
ANSI_ESCAPE: Pattern = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

# Default config root (fallback if config_loader fails)
DEFAULT_CONFIG_ROOT = Path.home() / ".config" / "atlastrinity"

# TUI artifacts to filter out from logs
SPAM_TRIGGERS = [
    "Welcome to",
    "│",
    "╭",
    "╮",
    "╰",
    "─",
    "──",
    "[2K",
    "[1A",
    "Press Enter",
    "↵",
    "ListToolsRequest",
    "Processing request of type",
    "Secure MCP Filesystem Server",
    "Client does not support MCP Roots",
    "Resolving dependencies",
    "Resolved, downloaded and extracted",
    "Saved lockfile",
    "Sequential Thinking MCP Server",
    "Starting Context7 MCP Server",
    "Context7 MCP Server connected via stdio",
    "Redis connected via URL",
    "Lessons:",
    "Strategies:",
    "Discoveries:",
    "brain - INFO - [MEMORY]",
    "brain - INFO - [STATE]",
]

logger = logging.getLogger("vibe_mcp")
logger.setLevel(logging.DEBUG)

# Setup file and stream handlers
try:
    log_dir = DEFAULT_CONFIG_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # File handler
    fh = logging.FileHandler(log_dir / "vibe_server.log", mode="a", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ),
    )
    logger.addHandler(fh)
except Exception as e:
    print(f"[VIBE] Warning: Could not setup file logging: {e}")

sh = logging.StreamHandler(sys.stderr)
sh.setLevel(logging.INFO)
sh.setFormatter(logging.Formatter("[VIBE_MCP] %(levelname)s: %(message)s"))
logger.addHandler(sh)

# Load configuration
try:
    from src.brain.config.config_loader import CONFIG_ROOT, PROJECT_ROOT, get_config_value

    VIBE_BINARY: str = get_config_value("mcp.vibe", "binary", "vibe")
    # Timeout is now controlled by vibe_config.toml (eff_timeout logic)
    DEFAULT_TIMEOUT_S: float = 600.0
    MAX_OUTPUT_CHARS: int = int(get_config_value("mcp.vibe", "max_output_chars", 500000))
    VIBE_WORKSPACE = get_config_value("mcp.vibe", "workspace", str(CONFIG_ROOT / "vibe_workspace"))
    VIBE_CONFIG_FILE = get_config_value("mcp.vibe", "config_file", None)
    AGENT_MODEL_OVERRIDE = get_config_value("agents.tetyana", "model", None)

    if not AGENT_MODEL_OVERRIDE:
        logger.warning(
            "[VIBE] AGENT_MODEL_OVERRIDE not set in config, strict configuration enforced",
        )

except Exception:

    def get_config_value(section: str, key: str, default: Any = None) -> Any:  # vulture: ignore
        return default

    VIBE_BINARY = "vibe"
    DEFAULT_TIMEOUT_S = 600.0
    MAX_OUTPUT_CHARS = 500000
    CONFIG_ROOT = Path.home() / ".config" / "atlastrinity"
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    VIBE_WORKSPACE = str(CONFIG_ROOT / "vibe_workspace")
    VIBE_CONFIG_FILE = None

# Derived paths
SYSTEM_ROOT = str(PROJECT_ROOT)
LOG_DIR = str(CONFIG_ROOT / "logs")
INSTRUCTIONS_DIR = str(Path(VIBE_WORKSPACE) / "instructions")
VIBE_SESSION_DIR = Path.home() / ".vibe" / "logs" / "session"
DATABASE_URL = get_config_value(
    "database",
    "url",
    f"sqlite+aiosqlite:///{CONFIG_ROOT}/atlastrinity.db",
)

# Allowed subcommands (CLI-only, no TUI)
ALLOWED_SUBCOMMANDS = {
    "list-editors",
    "list-modules",
    "run",
    "enable",
    "disable",
    "install",
    "smart-plan",
    "ask",
    "agent-reset",
    "agent-on",
    "agent-off",
    "vibe-status",
    "vibe-continue",
    "vibe-cancel",
    "vibe-help",
    "eternal-engine",
    "screenshots",
}

# Blocked subcommands (interactive TUI)
BLOCKED_SUBCOMMANDS = {"tui", "agent-chat", "self-healing-status", "self-healing-scan"}

# =============================================================================
# PLATFORM & DEVELOPMENT GUIDELINES
# =============================================================================

MACOS_DEVELOPMENT_GUIDELINES = """
MACOS DEVELOPMENT DOCTRINE:
- TARGET: macOS 13.0+ (Ventura).
- FRAMEWORK: SwiftUI (macOS specialized).
- UI MODIFIERS: Avoid iOS-specific modifiers like .navigationBarItems or .navigationBarTitle. Use .toolbar, .navigationTitle, and .navigationSubtitle.
- COLORS: Use platform-agnostic Color.secondary, Color.primary, or NSColor-linked colors. Avoid Color(.systemBackground) (iOS).
- CONCURRENCY: Strictly use @MainActor for SwiftUI Views and ViewModels.
- NETWORKING: Use Foundation URLSession or low-level Network.framework for macOS.
"""

DYNAMIC_VERIFICATION_PROTOCOL = """
DYNAMIC VERIFICATION PROTOCOL:
1. IDENTIFY Project Type:
   - .swift / Package.swift -> Swift Project
   - .py / requirements.txt -> Python Project
   - .js, .ts / package.json -> Node.js Project
2. EXECUTE Build/Check:
   - Swift: Run 'swift build' in the project root.
   - Python: Run 'python -m py_compile <file>' and 'ruff check <file>'.
   - Node.js: Run 'npm run build' or 'tsc --noEmit'.
3. MANDATORY GLOBAL LINT (13 parallel checks):
   - Run 'devtools.devtools_run_global_lint' AFTER any code modification.
   - JS/TS: biome, oxlint, tsc --noEmit (both tsconfigs), eslint type-aware (floating promises, unsafe types)
   - Python: ruff (25 rule sets incl. PERF/FURB/TRY/RET), pyright (standard), pyrefly, xenon, bandit, vulture (dead code)
   - Cross: knip (unused JS/TS), security audit, yaml-sync
4. ANALYZE Output:
   - If ANY linting errors or build failures (exit code != 0) are found, READ the error log, ANALYZE the message, and FIX it in the next iteration.
   - Continue until the report shows 0 errors.
"""

# =============================================================================
# GLOBAL STATE
# =============================================================================

# Vibe configuration (loaded at startup)
_vibe_config: VibeConfig | None = None
_current_mode: AgentMode = AgentMode.AUTO_APPROVE
_current_model: str | None = None
_proxy_process: subprocess.Popen | None = None

# Concurrency Control (Queueing)
# Vibe is heavy on tokens and resources. We serialize calls to avoid Rate Limit collisions.
VIBE_LOCK = asyncio.Lock()
VIBE_QUEUE_SIZE = 0


async def _emergency_cleanup() -> None:
    """Forcefully terminate lingering vibe and proxy processes to unblock the queue."""
    logger.warning("[VIBE] Emergency cleanup triggered. Terminating lingering processes...")
    try:
        # 1. Kill any active proxy
        _cleanup_provider_proxy()

        # 2. Kill any actual 'vibe' CLI processes that might be hanging
        # We use pgrep/pkill for platform-agnostic (ish) cleanup on Unix

        # Use -f to match the command line (more robust than exact name)
        subprocess.run(["pkill", "-9", "-f", "vibe"], capture_output=True, check=False)

    except Exception as e:
        logger.error(f"[VIBE] Emergency cleanup failed: {e}")


def get_vibe_config() -> VibeConfig:
    """Get or load the Vibe configuration."""
    global _vibe_config, _current_mode
    if _vibe_config is None:
        config_path = Path(VIBE_CONFIG_FILE) if VIBE_CONFIG_FILE else None
        _vibe_config = VibeConfig.load(config_path=config_path)
        logger.info(f"[VIBE] Loaded configuration: active_model={_vibe_config.active_model}")

        # Initialize _current_mode from config
        _current_mode = _vibe_config.default_mode

    return _vibe_config


def sync_vibe_configuration() -> None:
    """Sync active vibe_config.toml and support files to VIBE_HOME."""
    try:
        # Load config to resolve paths
        config = get_vibe_config()

        # Determine VIBE_HOME from config or env
        vibe_home = (
            Path(config.vibe_home)
            if config.vibe_home
            else Path(os.getenv("VIBE_HOME", str(Path.home() / ".vibe")))
        )
        vibe_home_config = vibe_home / "config.toml"

        # Determine Source Config Root (where templates are synced)
        source_root = DEFAULT_CONFIG_ROOT
        source_config_path = (
            Path(VIBE_CONFIG_FILE) if VIBE_CONFIG_FILE else source_root / "vibe_config.toml"
        )

        if not source_config_path.exists():
            logger.warning(f"Source config not found at {source_config_path}, skipping sync")
            return

        # Ensure VIBE_HOME structure exists
        vibe_home.mkdir(parents=True, exist_ok=True)
        (vibe_home / "prompts").mkdir(exist_ok=True)
        (vibe_home / "agents").mkdir(exist_ok=True)

        # 1. Sync main config.toml
        # Always sync if source is newer or target missing
        should_sync_main = not vibe_home_config.exists()
        if not should_sync_main:
            try:
                if source_config_path.stat().st_mtime > vibe_home_config.stat().st_mtime:
                    should_sync_main = True
            except OSError:
                should_sync_main = True

        if should_sync_main:
            shutil.copy2(source_config_path, vibe_home_config)
            logger.info(f"Synced Vibe config to: {vibe_home_config}")

        # 2. Sync agents and prompts folders from source_root/vibe/
        # These are usually populated by sync_config_templates.js
        for folder_name in ["agents", "prompts"]:
            src_folder = source_root / "vibe" / folder_name
            dst_folder = vibe_home / folder_name

            if src_folder.exists() and src_folder.is_dir():
                for src_file in src_folder.glob("*.toml"):
                    dst_file = dst_folder / src_file.name

                    # If it's a symlink in VIBE_HOME, we might want to respect it,
                    # but usually we want actual files for Vibe's portability
                    if not dst_file.exists() or src_file.stat().st_mtime > dst_file.stat().st_mtime:
                        if dst_file.is_symlink():
                            dst_file.unlink()
                        shutil.copy2(src_file, dst_file)
                        logger.debug(f"Synced Vibe {folder_name}: {src_file.name}")

    except Exception as e:
        logger.error(f"Failed to sync Vibe configuration: {e}")


def reload_vibe_config() -> VibeConfig:
    """Force reload the Vibe configuration."""
    global _vibe_config
    _vibe_config = None
    return get_vibe_config()


# =============================================================================
# INITIALIZATION
# =============================================================================

server = FastMCP("vibe")

logger.info(
    f"[VIBE] Server initialized | "
    f"Binary: {VIBE_BINARY} | "
    f"Workspace: {VIBE_WORKSPACE} | "
    f"Timeout: {DEFAULT_TIMEOUT_S}s",
)

# Perform startup sync
sync_vibe_configuration()


def _ensure_provider_proxy(p_conf: ProviderConfig) -> None:
    """Start the provider's local proxy if configured and needed."""
    global _proxy_process
    if not p_conf.requires_proxy or not p_conf.proxy_command:
        return

    try:
        # Check if port is already in use (heuristic based on api_base)
        port = 8085
        if "localhost:" in p_conf.api_base or "127.0.0.1:" in p_conf.api_base:
            try:
                # Extract port from URL like http://localhost:8085
                match = re.search(r":(\d+)", p_conf.api_base)
                if match:
                    port = int(match.group(1))
            except Exception:
                pass

        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            is_used = s.connect_ex(("127.0.0.1", port)) == 0

        if is_used:
            logger.info(
                f"[VIBE] Proxy port {port} for {p_conf.name} already in use, assuming active."
            )
            return

        # Expand variables in command (PROJECT_ROOT, etc.)
        cmd_str = VibeConfig.expand_vars(p_conf.proxy_command)
        import shlex

        try:
            cmd = shlex.split(cmd_str)
        except ValueError:
            # Fallback if shlex fails
            cmd = cmd_str.split()

        logger.info(mask_sensitive_data(f"[VIBE] Starting proxy for {p_conf.name}: {cmd_str}"))
        # Start as a daemon subprocess, redirecting output to log file
        proxy_log = log_dir / f"{p_conf.name}_proxy.log"
        _proxy_process = subprocess.Popen(
            cmd,
            stdout=open(proxy_log, "a", encoding="utf-8"),  # noqa: SIM115
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        logger.info(
            f"[VIBE] Proxy for {p_conf.name} started (PID: {_proxy_process.pid}, Log: {proxy_log})"
        )
    except Exception as e:
        logger.error(f"[VIBE] Failed to start proxy for {p_conf.name}: {e}")


def _cleanup_provider_proxy() -> None:
    """Terminate the active provider proxy subprocess."""
    if _proxy_process:
        logger.info(f"[VIBE] Terminating active proxy (PID: {_proxy_process.pid})...")
        try:
            _proxy_process.terminate()
            _proxy_process.wait(timeout=2)
        except Exception as e:
            logger.warning(f"[VIBE] Error stopping proxy: {e}")
            if _proxy_process:
                _proxy_process.kill()


# Register cleanup
atexit.register(_cleanup_provider_proxy)
# Deferred startup: _start_copilot_proxy is called inside vibe_prompt when needed

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    if not isinstance(text, str):
        return str(text)
    return ANSI_ESCAPE.sub("", text)


async def is_network_available(
    host: str = "api.mistral.ai",
    port: int = 443,
    timeout: float = 3.0,
) -> bool:
    """Check if the network and specific host are reachable."""
    try:
        await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        return True
    except (TimeoutError, OSError) as e:
        logger.warning(f"[VIBE] Network check failed for {host}:{port}: {e}")
        return False


def truncate_output(text: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """Truncate text with indicator if exceeded."""
    if not isinstance(text, str):
        text = str(text)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...[TRUNCATED: Output exceeded {max_chars} chars]..."


def resolve_vibe_binary() -> str | None:
    """Resolve the path to the Vibe CLI binary."""
    # Try ~/.local/bin first (common location)
    local_bin = os.path.expanduser("~/.local/bin/vibe")
    if os.path.exists(local_bin):
        return local_bin

    # Try absolute path from config
    if os.path.isabs(VIBE_BINARY) and os.path.exists(VIBE_BINARY):
        return VIBE_BINARY

    # Search PATH
    found = shutil.which(VIBE_BINARY)
    if found:
        return found

    logger.warning(f"Vibe binary '{VIBE_BINARY}' not found")
    return None


def _prepare_temp_vibe_home(model_alias: str) -> str:
    """Prepare a temporary VIBE_HOME with a custom config.toml for model switching."""
    temp_dir = tempfile.mkdtemp(prefix="vibe_home_")
    temp_path = Path(temp_dir)

    try:
        config = get_vibe_config()
        # Find real VIBE_HOME
        vibe_home = Path(config.vibe_home or os.getenv("VIBE_HOME", str(Path.home() / ".vibe")))

        # 1. Link support folders (prompts, logs, and agents are essential)
        # We use a helper for recursive symlinking to ensure subfolders like 'session' work
        def link_recursive(src_dir: Path, dst_dir: Path):
            dst_dir.mkdir(parents=True, exist_ok=True)
            for item in src_dir.glob("*"):
                dst_item = dst_dir / item.name
                if item.is_dir():
                    link_recursive(item, dst_item)
                else:
                    try:
                        if dst_item.exists() or dst_item.is_symlink():
                            dst_item.unlink()
                        os.symlink(item, dst_item)
                    except (OSError, FileExistsError):
                        try:
                            shutil.copy2(item, dst_item)
                        except OSError:
                            pass

        for folder in ["prompts", "logs", "agents"]:
            src = vibe_home / folder
            if src.exists():
                link_recursive(src, temp_path / folder)
            else:
                (temp_path / folder).mkdir(parents=True, exist_ok=True)

        # 2. Link essential files if they exist
        for filename in ["instructions.md", "trusted_folders.toml", "vibe.log", "vibehistory"]:
            src = vibe_home / filename
            dst = temp_path / filename
            if src.exists():
                try:
                    os.symlink(src, dst)
                except (OSError, FileExistsError):
                    try:
                        shutil.copy2(src, dst)
                    except OSError:
                        pass

        # 3. Generate custom config.toml
        # We generate a fresh TOML matching the VibeConfig object
        # This ensures all provider overrides and MCP servers are propagated
        def get_val(obj, key, default):
            """Safely get value from object, handling MagicMocks."""
            val = getattr(obj, key, default)
            # If it's a MagicMock, it won't be in the expected type
            from unittest.mock import MagicMock

            if isinstance(val, MagicMock):
                return default
            return val

        toml_lines = [
            "# Generated Vibe Configuration for Temp Session",
            f'active_model = "{model_alias}"',
            f"fallback_chain = {json.dumps(get_val(config, 'fallback_chain', []))}",
            f'system_prompt_id = "{get_val(config, "system_prompt_id", "cli")!s}"',
            f'default_mode = "{get_val(config, "default_mode", "auto-approve")!s}"',
            "enable_auto_update = false",
            f"max_turns = {int(get_val(config, 'max_turns', 100))}",
            f"disable_welcome_banner_animation = {str(get_val(config, 'disable_welcome_banner_animation', True)).lower()}",
            f"vim_keybindings = {str(get_val(config, 'vim_keybindings', False)).lower()}",
            f"timeout_s = {float(get_val(config, 'timeout_s', 600.0))}",
            "",
        ]

        # Add providers
        for provider in config.providers:
            # Skip if it's the default placeholder or redundant
            if not provider.name or not provider.api_base:
                continue

            # Standardize localhost to 127.0.0.1 to avoid DNS/Hang issues
            api_base = str(provider.api_base)
            if "localhost" in api_base:
                api_base = api_base.replace("localhost", "127.0.0.1")

            toml_lines.extend(
                [
                    "[[providers]]",
                    f'name = "{provider.name}"',
                    f'api_base = "{api_base}"',
                    f'api_key_env_var = "{provider.api_key_env_var}"',
                    f'api_style = "{provider.api_style}"',
                    f'backend = "{provider.backend}"',
                    "",
                ]
            )

        # Add models
        for model in config.models:
            # Handle potential mocks or non-string types safely
            m_name = str(model.name)
            m_provider = str(model.provider)
            m_alias = str(model.alias)
            m_temp = float(model.temperature)
            m_in_p = float(model.input_price)
            m_out_p = float(model.output_price)

            toml_lines.extend(
                [
                    "[[models]]",
                    f'name = "{m_name}"',
                    f'provider = "{m_provider}"',
                    f'alias = "{m_alias}"',
                    f"temperature = {m_temp}",
                    f"input_price = {m_in_p}",
                    f"output_price = {m_out_p}",
                    "",
                ]
            )

        # Add MCP servers (Documentation: supported transports and fields)
        for mcp in config.mcp_servers:
            toml_lines.extend(
                [
                    "[[mcp_servers]]",
                    f'name = "{mcp.name}"',
                    f'transport = "{mcp.transport}"',
                ]
            )
            if mcp.url:
                toml_lines.append(f'url = "{mcp.url}"')
            if mcp.command:
                toml_lines.append(f'command = "{mcp.command}"')
            if mcp.args:
                toml_lines.append(f"args = {json.dumps(list(mcp.args))}")
            if mcp.env:
                env_dict = {k: str(v) for k, v in dict(mcp.env).items()}
                env_parts = [f"{k} = {json.dumps(v)}" for k, v in env_dict.items()]
                toml_lines.append(f"env = {{ {', '.join(env_parts)} }}")
            if mcp.startup_timeout_sec:
                toml_lines.append(f"startup_timeout_sec = {mcp.startup_timeout_sec}")
            if mcp.tool_timeout_sec:
                toml_lines.append(f"tool_timeout_sec = {mcp.tool_timeout_sec}")
            toml_lines.append("")

        # Add tool patterns and permissions
        if config.enabled_tools:
            toml_lines.append(f"enabled_tools = {list(config.enabled_tools)}")
        if config.disabled_tools:
            toml_lines.append(f"disabled_tools = {list(config.disabled_tools)}")

        for tool_name, tool_conf in config.tools.items():
            toml_lines.extend([f"[tools.{tool_name}]", f'permission = "{tool_conf.permission}"'])

        config_text = "\n".join(toml_lines)
        (temp_path / "config.toml").write_text(config_text, encoding="utf-8")
        logger.debug(f"[VIBE] Prepared temp VIBE_HOME at {temp_dir} with model={model_alias}")
        logger.debug(f"[VIBE] Generated TOML:\n{config_text}")
        return temp_dir

    except Exception as e:
        logger.error(f"[VIBE] Failed to prepare temp VIBE_HOME: {e}")
        # Clean up on failure
        shutil.rmtree(temp_dir, ignore_errors=True)
        return ""


def prepare_workspace_and_instructions() -> None:
    """Ensure necessary directories exist."""
    try:
        Path(VIBE_WORKSPACE).mkdir(parents=True, exist_ok=True)
        Path(INSTRUCTIONS_DIR).mkdir(parents=True, exist_ok=True)
        logger.debug(f"Workspace ready: {VIBE_WORKSPACE}")
    except Exception as e:
        logger.error(f"Failed to create workspace: {e}")


def cleanup_old_instructions(max_age_hours: int = 24) -> int:
    """Remove instruction files older than max_age_hours."""
    instructions_path = Path(INSTRUCTIONS_DIR)
    if not instructions_path.exists():
        return 0

    now = datetime.now()
    cleaned = 0
    try:
        for f in instructions_path.glob("vibe_instructions_*.md"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if (now - mtime).total_seconds() > max_age_hours * 3600:
                    f.unlink()
                    cleaned += 1
            except Exception as e:
                logger.debug(f"Failed to cleanup {f.name}: {e}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

    if cleaned > 0:
        logger.info(f"Cleaned {cleaned} old instruction files")
    return cleaned


def handle_long_prompt(prompt: str, cwd: str | None = None) -> tuple[str, str | None]:
    """Handle long prompts by offloading to a file.
    Returns (final_prompt_arg, file_path_to_cleanup)
    """
    if len(prompt) <= 2000:
        return prompt, None

    try:
        os.makedirs(INSTRUCTIONS_DIR, exist_ok=True)

        timestamp = int(datetime.now().timestamp())
        unique_id = uuid.uuid4().hex[:6]
        filename = f"vibe_instructions_{timestamp}_{unique_id}.md"
        filepath = os.path.join(INSTRUCTIONS_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# VIBE INSTRUCTIONS\n\n")
            f.write(prompt)

        logger.debug(f"Large prompt ({len(prompt)} chars) stored at {filepath}")

        # Return a reference to the file
        return f"Read and execute the instructions from file: {filepath}", filepath

    except Exception as e:
        logger.warning(f"Failed to offload prompt: {e}")
        # Fallback: truncate if necessary
        if len(prompt) > 10000:
            return prompt[:10000] + "\n[TRUNCATED]", None
        return prompt, None


def _generate_task_session_id(prompt: str) -> str:
    """Generate a stable session ID in Vibe's native timestamp format.
    Native format: session_YYYYMMDD_HHMMSS_random
    """
    now = datetime.now()
    # We use a task-specific hash as the "random" part to maintain stability for the same prompt
    import hashlib

    h = hashlib.sha256(prompt.strip()[:500].encode()).hexdigest()[:8]
    return f"session_{now.strftime('%Y%m%d_%H%M%S')}_{h}"


async def run_vibe_subprocess(
    argv: list[str],
    cwd: str | None,
    timeout_s: float,
    env: dict[str, str] | None = None,
    ctx: Context | None = None,
    prompt_preview: str | None = None,
    vibe_home_override: str | None = None,
) -> dict[str, Any]:
    """Execute Vibe CLI subprocess with streaming output and global queueing."""
    global VIBE_QUEUE_SIZE
    process_env = _prepare_vibe_env(env)

    # Apply VIBE_HOME override if provided
    if vibe_home_override:
        process_env["VIBE_HOME"] = vibe_home_override
        logger.debug(f"[VIBE] Using VIBE_HOME override: {vibe_home_override}")
    else:
        logger.debug(f"[VIBE] Using default VIBE_HOME: {process_env.get('VIBE_HOME', 'Not Set')}")

    # Queue Management
    VIBE_QUEUE_SIZE += 1
    if VIBE_LOCK.locked():
        msg = f"⏳ [VIBE-QUEUE] Task queued (Position: {VIBE_QUEUE_SIZE - 1}). Waiting for active task to complete..."
        logger.info(msg)
        await _emit_vibe_log(ctx, "info", msg)

    # Use a timeout for lock acquisition to avoid indefinite queue hangs
    # We wait up to timeout*2 to allow for one full task completion + some buffer
    lock_timeout = (timeout_s or DEFAULT_TIMEOUT_S) * 2
    try:
        await asyncio.wait_for(VIBE_LOCK.acquire(), timeout=lock_timeout)
    except TimeoutError:
        VIBE_QUEUE_SIZE -= 1
        error_msg = f"Queue timeout: Lock held for over {lock_timeout}s. Forcing emergency reset."
        logger.error(f"[VIBE] {error_msg}")
        await _emit_vibe_log(ctx, "error", f"🚨 [VIBE-QUEUE] {error_msg}")
        await _emergency_cleanup()
        return {"success": False, "error": error_msg, "command": argv}

    try:
        VIBE_QUEUE_SIZE -= 1
        logger.debug(mask_sensitive_data(f"[VIBE] Executing: {' '.join(argv)}"))
        logger.debug(mask_sensitive_data(f"[VIBE] Full argv: {argv}"))

        if prompt_preview:
            await _emit_vibe_log(
                ctx, "info", f"🚀 [VIBE-LIVE] Запуск Vibe: {prompt_preview[:80]}..."
            )

        result = await _execute_vibe_with_retries(argv, cwd, timeout_s, process_env, ctx)
        return result

    except Exception as outer_e:
        error_msg = f"Outer subprocess error: {outer_e}"
        logger.error(f"[VIBE] {error_msg}")
        return {"success": False, "error": error_msg, "command": argv}
    finally:
        # 1. Release Lock correctly
        if VIBE_LOCK.locked():
            try:
                VIBE_LOCK.release()
            except RuntimeError:
                # Already released or not held by this task
                pass

        # 2. Clean up temp VIBE_HOME if it was an override
        if vibe_home_override and "vibe_home_" in vibe_home_override:
            try:
                # We give a small delay to ensure file handles are closed
                await asyncio.sleep(0.5)
                shutil.rmtree(vibe_home_override, ignore_errors=True)
                logger.debug(f"[VIBE] Cleaned up temp VIBE_HOME: {vibe_home_override}")
            except Exception as e:
                logger.warning(
                    mask_sensitive_data(
                        f"[VIBE] Failed to cleanup temp home {vibe_home_override}: {e}"
                    )
                )


def _prepare_vibe_env(env: dict[str, str] | None) -> dict[str, str]:
    """Prepare environment variables for Vibe subprocess."""
    config = get_vibe_config()
    # Load environment variables from .env
    load_dotenv()

    process_env = os.environ.copy()

    # Ensure MISTRAL_API_KEY and COPILOT_API_KEY are explicitly propagated
    for key in ["MISTRAL_API_KEY", "COPILOT_API_KEY", "OPENROUTER_API_KEY"]:
        if key in os.environ:
            process_env[key] = os.environ[key]

    # Force non-interactive/programmatic mode for Vibe (Textual-based)
    process_env["TERM"] = "dumb"
    process_env["PAGER"] = "cat"
    process_env["NO_COLOR"] = "1"
    process_env["PYTHONUNBUFFERED"] = "1"
    process_env["TEXTUAL_ALLOW_NON_INTERACTIVE"] = "1"
    process_env["VIBE_DEBUG_RAW"] = "false"
    process_env.update(config.get_environment())
    if env:
        process_env.update({k: str(v) for k, v in env.items()})

    # Ensure PYTHONPATH includes src and project root for module resolution
    existing_pp = process_env.get("PYTHONPATH", "")
    # Add src and project root if not already present
    paths_to_add = [str(PROJECT_ROOT), str(PROJECT_ROOT / "src")]
    # Note: Vibe might be running in a different CWD, so absolute paths are safer
    for p in paths_to_add:
        if p not in existing_pp:
            existing_pp = f"{p}:{existing_pp}" if existing_pp else p
    process_env["PYTHONPATH"] = existing_pp

    # Auto-inject Session Tokens for providers that require exchange (e.g., Copilot)
    for p_conf in config.providers:
        if p_conf.requires_token_exchange and CopilotLLM:
            # We look for the raw API key in env
            # For Copilot, it's typically COPILOT_API_KEY
            raw_key_var = (
                "COPILOT_API_KEY" if p_conf.name == "copilot" else f"{p_conf.name.upper()}_API_KEY"
            )
            api_key = process_env.get(raw_key_var) or os.getenv(raw_key_var)

            if api_key:
                try:
                    # Current implementation uses CopilotLLM for exchange
                    # In the future, this can be dispatched by provider type
                    # Use configured default model for token exchange
                    exchange_model = config.models[0].name if config.models else "gpt-4o"
                    llm = CopilotLLM(api_key=api_key, model_name=exchange_model)
                    token, _ = llm._get_session_token()
                    process_env[p_conf.api_key_env_var] = token
                    logger.debug(
                        f"[VIBE] Successfully injected token for provider: {p_conf.name}, token: ***"
                    )
                except Exception as e:
                    logger.warning(
                        f"[VIBE] Failed to inject token for {p_conf.name}: {e}. Token was sanitized."
                    )

    return process_env


async def _emit_vibe_log(ctx: Context | None, level: str, message: str) -> None:
    """Emit log message to the client context."""
    if not ctx:
        return
    try:
        # Cast level string to Literal expected by ctx.log
        log_level = cast("Literal['debug', 'info', 'warning', 'error']", level)
        # Robustness: ensure we don't await a MagicMock or failing call
        if hasattr(ctx, "log"):
            if isinstance(ctx.log, MagicMock):
                logger.debug(f"[VIBE-MOCK-LOG] {level}: {message}")
                return
            await ctx.log(log_level, message, logger_name="vibe_mcp")
    except Exception as e:
        logger.debug(f"[VIBE] Failed to send log to client: {e}")


async def _handle_vibe_line(line: str, stream_name: str, ctx: Context | None) -> None:
    """Process and log a single line of output from Vibe."""
    line = mask_sensitive_data(_clean_vibe_line(line))
    if not line:
        return

    # Try structured logging first
    if await _try_parse_structured_vibe_log(line, ctx):
        return

    # Fallback to standard streaming log
    await _format_and_emit_vibe_log(line, stream_name, ctx)


def _clean_vibe_line(line: str) -> str:
    """Filter out terminal control characters and TUI artifacts."""
    if not line:
        return ""
    if any(c < "\x20" for c in line if c not in "\t\n\r"):
        line = "".join(c for c in line if c >= "\x20" or c in "\t\n\r")
    return line.strip()


async def _try_parse_structured_vibe_log(line: str, ctx: Context | None) -> bool:
    """Try to parse as JSON for structured logging."""
    try:
        obj = json.loads(line)
        if not isinstance(obj, dict) or not obj.get("role") or not obj.get("content"):
            return False

        role_map = {
            "assistant": "🧠 [VIBE-THOUGHT]",
            "tool": "🔧 [VIBE-ACTION]",
        }
        prefix = role_map.get(obj["role"], "💬 [VIBE-GEN]")
        message = f"{prefix} {str(obj['content'])[:200]}"

        logger.info(message)
        await _emit_vibe_log(ctx, "info", message)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


async def _format_and_emit_vibe_log(line: str, stream_name: str, ctx: Context | None) -> None:
    """Format and emit a standard log line."""
    if any(t in line for t in SPAM_TRIGGERS):
        return

    if len(line) >= 1000:
        return

    if "Thinking" in line or "Planning" in line:
        formatted = f"🧠 [VIBE-THOUGHT] {line}"
    elif "Running" in line or "Executing" in line:
        formatted = f"🔧 [VIBE-ACTION] {line}"
    else:
        formatted = f"⚡ [VIBE-LIVE] {line}"

    logger.debug(mask_sensitive_data(f"[VIBE_{stream_name}] {line}"))
    level = "warning" if stream_name == "ERR" else "info"
    await _emit_vibe_log(ctx, level, formatted)


async def _read_vibe_stream(
    stream: asyncio.StreamReader,
    chunks: list[bytes],
    stream_name: str,
    timeout_s: float,
    ctx: Context | None,
) -> None:
    """Read stream in chunks to handle TUI artifacts and provide real-time logging."""
    try:
        while True:
            # Use read() instead of readline() to handle status lines without newlines
            # Apply a timeout to avoid hangs if the process stops writing but won't exit
            data = await asyncio.wait_for(stream.read(1024), timeout=timeout_s)
            if not data:
                break

            chunks.append(data)

            # For logging, we still try to process lines if they exist in the chunk
            text = data.decode(errors="replace")
            for line in text.split("\n"):
                if line.strip():
                    await _handle_vibe_line(line, stream_name, ctx)
    except TimeoutError:
        logger.warning(f"[VIBE] Read timeout on {stream_name} after {timeout_s}s")
    except Exception as e:
        logger.debug(f"[VIBE] Error reading {stream_name} stream: {e}")


async def _execute_vibe_with_retries(
    argv: list[str],
    cwd: str | None,
    timeout_s: float,
    process_env: dict[str, str],
    ctx: Context | None,
) -> dict[str, Any]:
    """Execute loop with retries for Vibe subprocess."""
    MAX_RETRIES = 3
    # Optimized backoff delays for faster fallback
    BACKOFF_DELAYS = [60, 180, 300]

    for attempt in range(MAX_RETRIES):
        logger.info(f"[VIBE] Starting attempt {attempt + 1}/{MAX_RETRIES}...")
        try:
            # Execute subprocess with DEVNULL for stdin to avoid TUI hangs
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=cwd or VIBE_WORKSPACE,
                env=process_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
            )

            stdout_chunks: list[bytes] = []
            stderr_chunks: list[bytes] = []

            try:
                streams_to_read = []
                if process.stdout:
                    streams_to_read.append(
                        _read_vibe_stream(process.stdout, stdout_chunks, "OUT", timeout_s, ctx)
                    )
                if process.stderr:
                    streams_to_read.append(
                        _read_vibe_stream(process.stderr, stderr_chunks, "ERR", timeout_s, ctx)
                    )

                if streams_to_read:
                    # Apply an outer timeout to the gather as well
                    # Wrap in ensure_future to satisfy type checker
                    gather_task = asyncio.ensure_future(asyncio.gather(*streams_to_read))
                    await asyncio.wait_for(gather_task, timeout=timeout_s + 10)
            finally:
                pass

            try:
                # Wait for the process to finish, with a timeout
                await asyncio.wait_for(process.wait(), timeout=5)

                await _emit_vibe_log(ctx, "info", "✅ [VIBE-LIVE] Vibe завершив роботу успішно")
            except TimeoutError:
                return await _handle_vibe_timeout(
                    process, argv, timeout_s, stdout_chunks, stderr_chunks, ctx
                )

            stdout = strip_ansi(b"".join(stdout_chunks).decode(errors="replace"))
            stderr = strip_ansi(b"".join(stderr_chunks).decode(errors="replace"))

            if process.returncode != 0:
                # Check for API rate limits and other fallback triggers
                rate_limit_patterns = [
                    r"Rate limit[s]? exceeded",
                    r"Upgrade to Pro",
                    r"429 Too Many Requests",
                    r"Insufficient quota",
                    r"RateLimitError",
                ]
                is_rate_limit = any(
                    re.search(p, stderr, re.IGNORECASE) or re.search(p, stdout, re.IGNORECASE)
                    for p in rate_limit_patterns
                )

                if is_rate_limit:
                    res = await _handle_vibe_rate_limit(
                        attempt, MAX_RETRIES, BACKOFF_DELAYS, stdout, stderr, argv, ctx
                    )
                    if isinstance(res, tuple) and res[0] is True:
                        # Model switched, update VIBE_HOME for next attempt
                        new_home = res[1]
                        if new_home:
                            process_env["VIBE_HOME"] = new_home
                        continue
                    if isinstance(res, bool) and res is True:
                        continue
                    return cast("dict[str, Any]", res)

                # Check for Session not found (failed resume)

            # Use regex for more robust detection of Vibe session errors (Iteration 3)
            session_patterns = [
                r"session '.*' not found",
                r"not found in .*logs/session",
                r"failed to resume session",
            ]

            session_error = any(
                re.search(p, stderr, re.IGNORECASE | re.DOTALL)
                or re.search(p, stdout, re.IGNORECASE | re.DOTALL)
                for p in session_patterns
            )

            if session_error and "--resume" in argv:
                logger.warning(
                    f"[VIBE-RETRY-DIAG] Session error detected. Retrying without --resume. ID: {uuid.uuid4().hex[:8]}"
                )
                try:
                    idx = argv.index("--resume")
                    argv.pop(idx)  # remove --resume
                    if idx < len(argv):
                        argv.pop(idx)  # remove session_id
                    # Continue loop to retry immediately with updated argv
                    continue
                except (ValueError, IndexError):
                    pass

            if process.returncode != 0:
                logger.debug(
                    f"[VIBE-FAIL-DIAG] Code {process.returncode}. Out length: {len(stdout)}. Err length: {len(stderr)}"
                )
                logger.debug(f"[VIBE-FAIL-SNIPPET] Stderr snippet: {stderr[-500:]}")

            return {
                "success": process.returncode == 0,
                "returncode": process.returncode,
                "stdout": truncate_output(stdout),
                "stderr": truncate_output(stderr),
                "command": argv,
            }
        except FileNotFoundError:
            return {"success": False, "error": f"Vibe binary not found: {argv[0]}", "command": argv}
        except Exception as e:
            logger.error(
                mask_sensitive_data(f"[VIBE] Subprocess error during attempt {attempt + 1}: {e}")
            )
            if attempt == MAX_RETRIES - 1:
                return {"success": False, "error": str(e), "command": argv}

    return {"success": False, "error": "Retries exhausted", "command": argv}


async def _handle_vibe_timeout(
    process: asyncio.subprocess.Process,
    argv: list[str],
    timeout_s: float,
    stdout_chunks: list[bytes],
    stderr_chunks: list[bytes],
    ctx: Context | None,
) -> dict[str, Any]:
    """Handle process timeout by terminating/killing and returning partial output."""
    logger.warning(f"[VIBE] Process timeout ({timeout_s}s), terminating")
    await _emit_vibe_log(ctx, "warning", f"⏱️ [VIBE-LIVE] Перевищено timeout ({timeout_s}s)")

    try:
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=5)
    except TimeoutError:
        process.kill()
        await process.wait()

    stdout_str = strip_ansi(b"".join(stdout_chunks).decode(errors="replace"))
    stderr_str = strip_ansi(b"".join(stderr_chunks).decode(errors="replace"))

    return {
        "success": False,
        "error": f"Vibe execution timed out after {timeout_s}s",
        "returncode": -1,
        "stdout": truncate_output(stdout_str),
        "stderr": truncate_output(stderr_str),
        "command": argv,
    }


async def _handle_vibe_rate_limit(
    attempt: int,
    max_retries: int,
    backoff_delays: list[int],
    stdout: str,
    stderr: str,
    argv: list[str],
    ctx: Context | None,
) -> bool | tuple[bool, str | None] | dict[str, Any]:
    """Handle rate limit errors with multi-tier backoff or report failure."""
    global _current_model

    config = get_vibe_config()

    # Use configurable fallback chain from VibeConfig
    chain = config.fallback_chain
    if not chain:
        # Emergency default if config is empty
        chain = ["gpt-4o", "gpt-4.1", "deepseek-v3", "windsurf-fast"]

    try:
        current_idx = (
            chain.index(_current_model) if _current_model and _current_model in chain else -1
        )

        # Iterate through the chain starting from the next model
        for next_idx in range(current_idx + 1, len(chain)):
            next_model_alias = chain[next_idx]
            m_conf = config.get_model_by_alias(next_model_alias)
            p_conf = config.get_provider(m_conf.provider) if m_conf else None

            if m_conf and p_conf and p_conf.is_available():
                logger.info(
                    f"[VIBE] Rate limit for {_current_model}. Switching to {next_model_alias} (Tier {next_idx + 1})..."
                )
                await _emit_vibe_log(
                    ctx,
                    "info",
                    f"🔄 [VIBE-FALLBACK] Ліміт для {_current_model}. Переключаюсь на {next_model_alias}...",
                )

                # Start proxy if configured for this provider
                if p_conf.requires_proxy:
                    _ensure_provider_proxy(p_conf)

                _current_model = next_model_alias
                new_home = _prepare_temp_vibe_home(next_model_alias)
                return True, new_home
            logger.debug(f"[VIBE] Skipping {next_model_alias}: provider not available.")
    except ValueError:
        # In case current_model is not in chain
        pass

    error_msg = (
        f"API rate limit exceeded after {max_retries} attempts and all fallbacks. "
        f"Current model: {_current_model}"
    )
    logger.error(f"[VIBE] {error_msg}")
    await _emit_vibe_log(ctx, "error", f"❌ [VIBE-RATE-LIMIT] {error_msg}")
    return {
        "success": False,
        "error": error_msg,
        "error_type": "RATE_LIMIT",
    }


@server.tool()
async def vibe_test_in_sandbox(
    ctx: Context,
    test_script: str,
    target_files: dict[str, str],
    command: str,
    dependencies: list[str] | None = None,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """Execute a test script in an isolated temporary sandbox.

    Args:
        test_script: Content of the test script (e.g., Python unit test)
        target_files: Dictionary of {filename: content} to mock/create in sandbox
        command: Command to run (e.g., "python test_script.py")
        dependencies: (Optional) Mock dependencies or instructions
        timeout_s: Execution timeout (default: 30s)

    Returns:
        Execution results (stdout, stderr, returncode)
    """
    logger.info(f"[VIBE] Sandbox execution requested: {command}")

    # Create temp directory
    try:
        with tempfile.TemporaryDirectory(prefix="vibe_sandbox_") as sandbox_dir:
            # 1. Write target files
            for fname, content in target_files.items():
                fpath = os.path.join(sandbox_dir, fname)
                os.makedirs(os.path.dirname(fpath), exist_ok=True)
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(content)

            # 2. Write test script to checking file
            # If command references a specific file, stick to it, otherwise default
            runner_main = "vibe_test_runner.py"
            runner_path = os.path.join(sandbox_dir, runner_main)
            with open(runner_path, "w", encoding="utf-8") as f:
                f.write(test_script)

            # 3. Execute
            logger.debug(f"Running sandbox command in {sandbox_dir}")

            # Prepare env
            env = os.environ.copy()
            env["PYTHONPATH"] = sandbox_dir  # Add sandbox to path
            # Execute subprocess with DEVNULL for stdin to avoid TUI hangs
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=sandbox_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
                env=env,
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_s)

            return {
                "success": process.returncode == 0,
                "returncode": process.returncode,
                "stdout": stdout.decode(errors="replace"),
                "stderr": stderr.decode(errors="replace"),
                "sandbox_dir_was": sandbox_dir,
            }

    except TimeoutError:
        return {
            "success": False,
            "error": f"Sandbox execution timed out after {timeout_s}s",
            "returncode": -1,
        }
    except Exception as e:
        return {"success": False, "error": f"Sandbox internal error: {e}", "returncode": -1}


# =============================================================================
# MCP TOOLS - CORE (6 tools)
# =============================================================================


@server.tool()
async def vibe_which(ctx: Context) -> dict[str, Any]:
    """Locate the Vibe CLI binary and report its version and configuration.

    Returns:
        Dict with 'binary' path, 'version', current 'model', and 'mode'

    """
    vibe_path = resolve_vibe_binary()
    if not vibe_path:
        logger.warning("[VIBE] Binary not found on PATH")
        return {
            "success": False,
            "error": f"Vibe CLI not found (binary='{VIBE_BINARY}')",
        }

    logger.debug(f"[VIBE] Found binary at: {vibe_path}")

    try:
        process = await asyncio.create_subprocess_exec(
            vibe_path,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        version = stdout.decode().strip() if process.returncode == 0 else "unknown"
    except Exception as e:
        logger.warning(f"Failed to get Vibe version: {e}")
        version = "unknown"

    config = get_vibe_config()

    return {
        "success": True,
        "binary": vibe_path,
        "version": version,
        "active_model": _current_model or config.active_model,
        "mode": _current_mode.value,
        "available_models": [m.alias for m in config.get_available_models()],
    }


@server.tool()
async def vibe_prompt(
    ctx: Context,
    prompt: str,
    cwd: str | None = None,
    timeout_s: float | None = None,
    # Enhanced options
    model: str | None = None,
    agent: str | None = None,
    mode: str | None = None,
    session_id: str | None = None,
    enabled_tools: list[str] | None = None,
    disabled_tools: list[str] | None = None,
    max_turns: int | None = None,
    max_price: float | None = None,
    output_format: str = "streaming",
) -> dict[str, Any]:
    """Send a prompt to Vibe AI agent in programmatic mode.

    The PRIMARY tool for interacting with Vibe. Executes in CLI mode with
    structured output. All execution is logged and visible.

    Args:
        prompt: The message/query for Vibe AI (Mistral-powered)
        cwd: Working directory for execution (default: vibe_workspace)
        timeout_s: Timeout in seconds (default from config)
        model: Model alias to use (overrides active_model)
        agent: Agent profile name (loads from agents directory)
        mode: Operational mode (plan/auto-approve/accept-edits)
        session_id: Session ID to resume
        enabled_tools: Additional tools to enable (glob/regex patterns)
        disabled_tools: Additional tools to disable (glob/regex patterns)
        max_turns: Maximum conversation turns
        max_price: Maximum cost limit in dollars
        output_format: Output format (streaming/json/text)

    Returns:
        Dict with 'success', 'stdout', 'stderr', 'returncode', 'parsed_response'

    """
    prepare_workspace_and_instructions()

    vibe_path = resolve_vibe_binary()
    if not vibe_path:
        return {
            "success": False,
            "error": "Vibe CLI not found on PATH",
        }

    config = get_vibe_config()
    eff_timeout = timeout_s if timeout_s is not None else config.timeout_s
    # Default to PROJECT_ROOT for project operations, fall back to workspace
    eff_cwd = cwd or str(PROJECT_ROOT)
    if not os.path.exists(eff_cwd):
        eff_cwd = VIBE_WORKSPACE

    # Ensure workspace exists (for instructions/logs)
    os.makedirs(VIBE_WORKSPACE, exist_ok=True)
    if eff_cwd != VIBE_WORKSPACE:
        os.makedirs(eff_cwd, exist_ok=True)

    # Check network before proceeding if it's an AI prompt
    if not await is_network_available():
        return {
            "success": False,
            "error": "Mistral API is unreachable. Please check your internet connection.",
            "returncode": -2,
        }

    # Validate output_format to avoid CLI errors (only text, json, streaming supported)
    valid_formats = {"text", "json", "streaming"}
    if output_format not in valid_formats:
        logger.warning(
            f"[VIBE] Invalid output_format '{output_format}' requested. "
            f"Falling back to 'streaming'. valid_formats={valid_formats}"
        )
        output_format = "streaming"

    final_prompt, prompt_file_to_clean = handle_long_prompt(prompt, eff_cwd)

    # Automatic Session Persistence (if not provided)
    eff_session_id = session_id or _generate_task_session_id(prompt)

    try:
        # Determine effective mode
        effective_mode = AgentMode(mode) if mode else _current_mode

        # Prepare temp VIBE_HOME with robust model selection
        # Priority: 1. explicit arg, 2. current session fallback, 3. global override, 4. config default
        target_model = model or _current_model or AGENT_MODEL_OVERRIDE or config.active_model

        vibe_home_override = None
        if target_model:
            # Ensure proxy is running if the target model uses copilot
            m_conf = config.get_model_by_alias(target_model)
            if m_conf and m_conf.provider:
                p_conf = config.get_provider(m_conf.provider)
                if p_conf and p_conf.requires_proxy:
                    _ensure_provider_proxy(p_conf)

            vibe_home_override = _prepare_temp_vibe_home(target_model)

        # Build command using config (Model switching is handled via VIBE_HOME override)
        argv = [
            vibe_path,
            *config.to_cli_args(
                prompt=final_prompt,
                cwd=eff_cwd,
                mode=effective_mode,
                model="default",  # We handle model override via VIBE_HOME
                agent=agent,
                session_id=eff_session_id,
                max_turns=max_turns,
                max_price=max_price,
                output_format=output_format,
            ),
        ]

        logger.info(f"[VIBE] Executing prompt: {prompt[:50]}... (timeout={eff_timeout}s)")

        result = await run_vibe_subprocess(
            argv=argv,
            cwd=eff_cwd,
            timeout_s=eff_timeout,
            ctx=ctx,
            prompt_preview=prompt,
            vibe_home_override=vibe_home_override,
        )

        # Try to parse JSON response
        if result.get("success") and result.get("stdout"):
            try:
                result["parsed_response"] = json.loads(result["stdout"])
            except json.JSONDecodeError:
                # Try to extract JSON from streaming format
                lines = result["stdout"].split("\n")
                json_lines = [line for line in lines if line.strip().startswith("{")]
                if json_lines:
                    try:
                        result["parsed_response"] = json.loads(json_lines[-1])
                    except json.JSONDecodeError:
                        result["parsed_response"] = None

        return result

    finally:
        # Cleanup temporary file
        if prompt_file_to_clean and os.path.exists(prompt_file_to_clean):
            try:
                os.remove(prompt_file_to_clean)
                logger.debug(f"Cleaned up prompt file: {prompt_file_to_clean}")
            except Exception as e:
                logger.warning(f"Failed to cleanup prompt file: {e}")


@server.tool()
async def vibe_analyze_error(
    ctx: Context,
    error_message: str,
    file_path: str | None = None,
    log_context: str | None = None,
    recovery_history: list[dict[str, Any]] | str | None = None,
    cwd: str | None = None,
    timeout_s: float | None = None,
    auto_fix: bool = True,
    session_id: str | None = None,
    # Enhanced context for better self-healing
    step_action: str | None = None,
    expected_result: str | None = None,
    actual_result: str | None = None,
    full_plan_context: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Deep error analysis and optional auto-fix using Vibe AI.

    Designed for self-healing scenarios when the system encounters errors
    it cannot resolve. Vibe acts as a Senior Engineer.

    Args:
        error_message: The error message or stack trace
        file_path: Path to the file with the error (if known)
        log_context: Recent log entries for context
        recovery_history: List of past recovery attempts or a summary string
        cwd: Working directory
        timeout_s: Timeout in seconds (default: 600)
        auto_fix: Automatically apply fixes (default: True)
        step_action: The action that was being performed when the error occurred
        expected_result: What was expected to happen
        actual_result: What actually happened
        full_plan_context: The full execution plan for context

    Returns:
        Analysis with root cause, suggested or applied fixes, and verification

    """
    prepare_workspace_and_instructions()

    # Build structured problem report
    prompt_parts = [
        "=" * 60,
        "ATLASTRINITY SELF-HEALING DIAGNOSTIC REPORT",
        "=",
        "ROLE: Senior Architect & Self-Healing Engineer.",
        "MISSION: Diagnose with ARCHITECTURAL AWARENESS, fix, and verify.",
        "",
        "CONTEXT NOTE: Architecture diagrams have been refreshed and are available",
        "in `src/brain/data/architecture_diagrams/mcp_architecture.md`.",
        "Please use them to understand component interactions.",
        "",
        "=",
        "1. WHAT HAPPENED (Problem Description)",
        "=" * 40,
        f"ERROR MESSAGE:\n{error_message}",
    ]

    # Add step context if available
    if step_action:
        prompt_parts.extend(
            [
                "",
                f"STEP ACTION: {step_action}",
            ],
        )

    if expected_result:
        prompt_parts.append(f"EXPECTED RESULT: {expected_result}")

    if actual_result:
        prompt_parts.append(f"ACTUAL RESULT: {actual_result}")

    prompt_parts.extend(
        [
            "",
            "=" * 40,
            "2. CONTEXT (Environment & History)",
            "=" * 40,
            f"System Root: {SYSTEM_ROOT}",
            f"Project Directory: {cwd or VIBE_WORKSPACE}",
            "",
            "DATABASE SCHEMA (for reference):",
            "- sessions: id, started_at, ended_at",
            "- tasks: id, session_id, goal, status, created_at",
            "- task_steps: id, task_id, sequence_number, action, tool, status, error_message",
            "- tool_executions: id, step_id, server_name, tool_name, arguments, result",
        ],
    )

    if log_context:
        prompt_parts.extend(
            [
                "",
                "RECENT LOGS:",
                log_context,
            ],
        )

    if recovery_history:
        prompt_parts.extend(
            [
                "",
                "=" * 40,
                "3. PAST ATTEMPTS (What Was Already Tried)",
                "=" * 40,
            ],
        )
        if isinstance(recovery_history, list):
            for i, attempt in enumerate(recovery_history):
                status = "✅ SUCCESS" if attempt.get("status") == "success" else "❌ FAILED"
                prompt_parts.append(
                    f"Attempt {i + 1}: {attempt.get('action', 'Unknown')} | {status}",
                )
                if attempt.get("error"):
                    prompt_parts.append(f"  └─ Error: {attempt.get('error')}")
            prompt_parts.append("")
            prompt_parts.append("⚠️ CRITICAL: Do NOT repeat strategies that have already failed!")
        else:
            prompt_parts.append(recovery_history)
            prompt_parts.append("⚠️ CRITICAL: Do NOT repeat strategies that have already failed!")

    if full_plan_context:
        prompt_parts.extend(
            [
                "",
                "FULL PLAN CONTEXT:",
                str(full_plan_context)[:1000],  # More aggressive limit
            ],
        )

    if log_context:
        # Instead of embedding logs, we tell Vibe where to find them and give a tiny snippet
        prompt_parts.extend(
            [
                "",
                "2.1 RECENT LOGS (Pointer-based Context)",
                "=" * 40,
                f"Full log file: {DEFAULT_CONFIG_ROOT}/logs/vibe_server.log",
                "ACTION: Use your 'read_file' or 'filesystem_read' tool to inspect this file if needed.",
                "",
                "BRIEF LOG SNIPPET (last 30 lines for quick orientation):",
                "\n".join(str(log_context).splitlines()[-30:]),  # Only last 30 lines
            ],
        )

    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
                # If file is huge, take just the relevant part if we can guess line number
                # For now, just take a smaller chunk to be safe
                prompt_parts.extend(
                    [
                        "",
                        f"RELEVANT FILE: {file_path}",
                        "```",
                        content[:3000],
                        "```",
                    ],
                )
        except Exception as e:
            logger.warning(f"Could not read file {file_path}: {e}")

    prompt_parts.extend(
        [
            "",
            "=" * 40,
            "4. YOUR INSTRUCTIONS",
            "=" * 40,
        ],
    )

    if auto_fix:
        prompt_parts.extend(
            [
                "",
                "PHASE 1 - DIAGNOSE:",
                "  1.1. Perform Root Cause Analysis (RCA) - identify the EXACT cause",
                "  1.2. Explain WHY this error occurred (not just what happened)",
                "  1.3. Check if this is related to configuration, codebase, or environment limits (macOS vs iOS)",
                f"  1.4. Apply guidelines from: {MACOS_DEVELOPMENT_GUIDELINES}",
                "",
                "PHASE 2 - FIX:",
                "  2.1. Create a fix strategy with clear rationale",
                "  2.2. Execute the fix (edit code, run commands as needed)",
                "  2.3. Ensure the fix addresses the ROOT CAUSE, not symptoms",
                f"  2.4. Follow DYNAMIC VERIFICATION: {DYNAMIC_VERIFICATION_PROTOCOL}",
                "",
                "PHASE 2.5 - SANDBOX VERIFICATION (CRITICAL):",
                "  2.5.1. Before applying any fix to the main codebase, TRY to reproduce the fix in a sandbox.",
                "  2.5.2. Use the 'vibe_test_in_sandbox' tool if available.",
                "  2.5.3. Create a minimal reproduction script and verify your fix actually works.",
                "  2.5.4. If sandbox test passes, ONLY THEN apply the fix to the main codebase.",
                "",
                "PHASE 3 - VERIFY:",
                "  3.1. Verify the fix works by running appropriate functional checks",
                "  3.2. MANDATORY: Run 'devtools.devtools_run_global_lint' to ensure no code quality regression",
                "  3.3. Confirm no new issues were introduced and all violations are fixed",
                "  3.4. Report results with evidence of success (0 linting errors)",
                "",
                "PHASE 4 - PREVENTION:",
                "  4.1. Identify if this issue was caused by a systemic weakness (invalid path logic, missing config, unstable utility).",
                "  4.2. PROPOSE and (if safe) APPLY a preventative measure: update configuration templates, improve utility functions, or add more robust error handling in the culprit module.",
                "  4.3. Ensure that 'fixing for yourself' means the system is now more resilient to this specific class of errors.",
                "",
                "OUTPUT FORMAT:",
                "Provide a structured response with:",
                "- ROOT_CAUSE: [description]",
                "- FIX_APPLIED: [what was changed now]",
                "- PREVENTION_MEASURE: [what was changed to prevent recurrence]",
                "- VERIFICATION: [evidence of success]",
                "- voice_message: [Direct speech to the user in Ukrainian, explaining what you did]",
                "- STATUS: SUCCESS | PARTIAL | FAILED",
            ],
        )
    else:
        prompt_parts.extend(
            [
                "",
                "ANALYSIS MODE (no changes):",
                "1. Perform deep root cause analysis",
                "2. Explain WHY this error occurred",
                "3. Suggest specific fixes with rationale",
                "4. Estimate complexity and risk of each fix",
                "",
                "Do NOT apply any changes - analysis only.",
            ],
        )

    prompt = "\n".join(prompt_parts)

    logger.info(f"[VIBE] Analyzing error (auto_fix={auto_fix}, step={step_action})")

    return cast(
        "dict[str, Any]",
        await vibe_prompt(
            ctx=ctx,
            prompt=prompt,
            cwd=cwd,
            timeout_s=timeout_s or DEFAULT_TIMEOUT_S,
            model=model or _current_model or AGENT_MODEL_OVERRIDE,
            mode="auto-approve" if auto_fix else "plan",
            session_id=session_id,
            max_turns=config.max_turns,
        ),
    )


@server.tool()
async def vibe_implement_feature(
    ctx: Context,
    goal: str,
    context_files: list[str] | None = None,
    constraints: str | None = None,
    cwd: str | None = None,
    timeout_s: float | None = 1200,
    session_id: str | None = None,
    # Enhanced options for software development
    quality_checks: bool = True,
    iterative_review: bool = True,
    max_iterations: int = 3,
    run_linting: bool = True,
    code_style: str = "ruff",
    model: str | None = None,
) -> dict[str, Any]:
    """Deep coding mode: Implements a complex feature or refactoring.

    Vibe acts as a Senior Architect to plan, implement, verify, and iteratively
    improve the code until quality standards are met.

    Args:
        goal: High-level objective (e.g., "Add user profile page with API and DB")
        context_files: List of relevant file paths
        constraints: Technical constraints or guidelines
        cwd: Working directory
        timeout_s: Timeout (default: 1200s for deep work)
        quality_checks: Run lint/syntax checks after implementation (default: True)
        iterative_review: Self-review and fix issues until clean (default: True)
        max_iterations: Maximum review/fix iterations (default: 3)
        run_linting: Run linter on modified files (default: True)
        code_style: Linter to use - "ruff" or "pylint" (default: "ruff")

    Returns:
        Implementation report with changed files, verification results, and quality metrics

    """
    prepare_workspace_and_instructions()

    # Gather file contents
    file_contents = []
    if context_files:
        for fpath in context_files:
            if os.path.exists(fpath):
                try:
                    with open(fpath, encoding="utf-8") as f:
                        content = f.read()[:3000]  # Reduced limit for token efficiency
                        file_contents.append(f"FILE: {fpath}\n```\n{content}\n```")
                except Exception as e:
                    file_contents.append(f"FILE: {fpath} (Error: {e})")
            else:
                file_contents.append(f"FILE: {fpath} (Not found, will create)")

    context_str = "\n\n".join(file_contents) if file_contents else "(No files provided)"

    # Build enhanced prompt with iterative workflow
    quality_section = ""
    if quality_checks:
        quality_section = f"""
QUALITY REQUIREMENTS:
- All code must pass {code_style} linting
- Type hints required for function parameters and returns
- Docstrings required for public functions
- Error handling for external operations
- No hardcoded secrets or credentials
"""

    iterative_section = ""
    if iterative_review:
        iterative_section = f"""
ITERATIVE IMPROVEMENT PROTOCOL:
After initial implementation, follow this loop (max {max_iterations} iterations):

1. RUN DYNAMIC VERIFICATION:
   - {DYNAMIC_VERIFICATION_PROTOCOL}
   - IF APPLICABLE: Use 'vibe_test_in_sandbox' to verify isolated logic before integration.
   
2. SELF-REVIEW:
   - Verify compliance with: {MACOS_DEVELOPMENT_GUIDELINES}
   - Check for edge cases not handled
   - Verify error messages are helpful
   - Ensure code is readable and maintainable
   
3. IF ISSUES FOUND:
   - Fix the issues
   - Return to step 1
   
4. IF CLEAN:
   - Report success with summary

Track your iterations and report final status.
"""

    prompt = f"""
============================================================
ATLASTRINITY SOFTWARE DEVELOPMENT TASK
============================================================

ROLE: You are the Senior Software Architect and Lead Developer for AtlasTrinity.
MISSION: Implement a feature that will work reliably in production.

GOAL:
{goal}

============================================================
CONTEXT FILES
============================================================
{context_str}

============================================================
CONSTRAINTS & GUIDELINES
============================================================
{constraints or "Standard project guidelines apply."}
{quality_section}

============================================================
ENVIRONMENT
============================================================
System Root: {SYSTEM_ROOT}
Project Directory: {cwd or VIBE_WORKSPACE}

============================================================
IMPLEMENTATION WORKFLOW
============================================================

PHASE 1 - ANALYZE & PLAN:
  1.1. Understand the goal completely
  1.2. Review existing code structure
  1.3. Identify files to create/modify
  1.4. Plan the implementation approach

PHASE 2 - IMPLEMENT:
  2.1. Create/edit necessary files
  2.2. Handle imports and dependencies
  2.3. Add proper error handling
  2.4. Include type hints and docstrings

PHASE 3 - VERIFY:
  3.1. Check syntax is valid
  3.2. MANDATORY: Run 'devtools.devtools_run_global_lint' and fix any violations
  3.3. Verify imports resolve correctly
{iterative_section}

PHASE 4 - REPORT:
  Provide a structured summary:
  - FILES_MODIFIED: [list of files]
  - FILES_CREATED: [list of files]
  - CHANGES_SUMMARY: [brief description]
  - VERIFICATION_STATUS: PASSED | FAILED
  - ISSUES_REMAINING: [any known issues]
  - NEXT_STEPS: [recommendations if any]

============================================================
EXECUTE NOW
============================================================
"""

    logger.info(f"[VIBE] Implementing feature: {goal[:50]}... (iterative={iterative_review})")

    return cast(
        "dict[str, Any]",
        await vibe_prompt(
            ctx=ctx,
            prompt=prompt,
            cwd=cwd,
            timeout_s=timeout_s or 1200,
            model=model or _current_model or AGENT_MODEL_OVERRIDE,
            mode="auto-approve",
            session_id=session_id,
            max_turns=30 + (max_iterations * 5 if iterative_review else 0),
        ),
    )


@server.tool()
async def vibe_code_review(
    ctx: Context,
    file_path: str,
    focus_areas: str | None = None,
    cwd: str | None = None,
    timeout_s: float | None = None,
    session_id: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Request a code review from Vibe AI for a specific file.

    Args:
        file_path: Path to the file to review
        focus_areas: Specific areas to focus on (e.g., "security", "performance")
        cwd: Working directory
        timeout_s: Timeout in seconds (default: 300)

    Returns:
        Code review analysis with suggestions

    """
    if not os.path.exists(file_path):
        return {
            "success": False,
            "error": f"File not found: {file_path}",
        }

    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()[:10000]  # Limit
    except Exception as e:
        return {
            "success": False,
            "error": f"Could not read file: {e}",
        }

    prompt_parts = [
        f"CODE REVIEW REQUEST: {file_path}",
        "",
        f"FILE CONTENT:\n```\n{content}\n```",
        "",
        "Please review this code and provide:",
        "1. Overall code quality assessment",
        "2. Potential bugs or issues",
        "3. Security concerns (if any)",
        "4. Performance improvements",
        "5. Code style and best practices",
    ]

    if focus_areas:
        prompt_parts.append(f"\nFOCUS AREAS: {focus_areas}")

    return cast(
        "dict[str, Any]",
        await vibe_prompt(
            ctx=ctx,
            prompt="\n".join(prompt_parts),
            cwd=cwd,
            timeout_s=timeout_s or 300,
            model=model or _current_model or AGENT_MODEL_OVERRIDE,
            mode="plan",  # Read-only mode
            session_id=session_id,
            max_turns=5,
        ),
    )


@server.tool()
async def vibe_smart_plan(
    ctx: Context,
    objective: str,
    context: str | None = None,
    cwd: str | None = None,
    timeout_s: float | None = None,
    session_id: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Generate a smart execution plan for a complex objective.

    Args:
        objective: The goal or task to plan for
        context: Additional context (existing code, constraints, etc.)
        cwd: Working directory
        timeout_s: Timeout in seconds (default: 300)

    Returns:
        Structured plan with steps, actions, tools, and verification criteria

    """
    prompt_parts = [
        "CREATE A DETAILED EXECUTION PLAN",
        "",
        f"OBJECTIVE: {objective}",
    ]

    if context:
        prompt_parts.append(f"\nCONTEXT:\n{context}")

    prompt_parts.extend(
        [
            "",
            "For each step, specify:",
            "- Action to perform",
            "- Required tools/commands",
            "- Expected outcome",
            "- Verification criteria",
        ],
    )

    return cast(
        "dict[str, Any]",
        await vibe_prompt(
            ctx=ctx,
            prompt="\n".join(prompt_parts),
            cwd=cwd,
            timeout_s=timeout_s or 300,
            mode="plan",
            session_id=session_id,
            max_turns=5,
            model=model,
        ),
    )


# =============================================================================
# MCP TOOLS - CONFIGURATION (5 new tools)
# =============================================================================


@server.tool()
async def vibe_get_config(ctx: Context) -> dict[str, Any]:
    """Get the current Vibe configuration state.

    Returns:
        Current configuration including active model, mode, providers, and models

    """
    config = get_vibe_config()

    return {
        "success": True,
        "active_model": _current_model or config.active_model,
        "mode": _current_mode.value,
        "default_mode": config.default_mode.value,
        "max_turns": config.max_turns,
        "max_price": config.max_price,
        "timeout_s": config.timeout_s,
        "providers": [
            {
                "name": p.name,
                "api_base": p.api_base,
                "available": p.is_available(),
            }
            for p in config.providers
        ],
        "models": [
            {
                "alias": m.alias,
                "name": m.name,
                "provider": m.provider,
                "temperature": m.temperature,
            }
            for m in config.models
        ],
        "available_models": [m.alias for m in config.get_available_models()],
        "enabled_tools": config.enabled_tools,
        "disabled_tools": config.disabled_tools,
    }


@server.tool()
async def vibe_configure_model(
    ctx: Context,
    model_alias: str,
    persist: bool = False,
) -> dict[str, Any]:
    """Switch the active model for Vibe operations.

    Args:
        model_alias: Alias of the model to use (from models list)
        persist: If True, update the config file (not yet implemented)

    Returns:
        Confirmation with the new active model

    """
    global _current_model

    config = get_vibe_config()
    model = config.get_model_by_alias(model_alias)

    if not model:
        available = [m.alias for m in config.models]
        return {
            "success": False,
            "error": f"Model '{model_alias}' not found",
            "available_models": available,
        }

    # Check if provider is available
    provider = config.get_provider(model.provider)
    if not provider or not provider.is_available():
        return {
            "success": False,
            "error": f"Provider '{model.provider}' is not available (missing API key)",
            "hint": f"Set {provider.api_key_env_var if provider else 'API_KEY'} environment variable",
        }

    _current_model = model_alias
    logger.info(f"[VIBE] Switched active model to: {model_alias}")

    return {
        "success": True,
        "active_model": model_alias,
        "model_name": model.name,
        "provider": model.provider,
        "temperature": model.temperature,
    }


@server.tool()
async def vibe_set_mode(
    ctx: Context,
    mode: str,
) -> dict[str, Any]:
    """Change the operational mode for Vibe.

    Args:
        mode: Operational mode - "default", "plan", "accept-edits", or "auto-approve"
            - default: Requires confirmation for tool executions
            - plan: Read-only mode for exploration
            - accept-edits: Auto-approves file edit tools only
            - auto-approve: Auto-approves all tool executions

    Returns:
        Confirmation with the new mode

    """
    global _current_mode

    try:
        new_mode = AgentMode(mode)
    except ValueError:
        return {
            "success": False,
            "error": f"Invalid mode: '{mode}'",
            "valid_modes": [m.value for m in AgentMode],
        }

    _current_mode = new_mode
    logger.info(f"[VIBE] Changed operational mode to: {mode}")

    return {
        "success": True,
        "mode": mode,
        "description": {
            "default": "Requires confirmation for tool executions",
            "plan": "Read-only mode for exploration",
            "accept-edits": "Auto-approves file edit tools only",
            "auto-approve": "Auto-approves all tool executions",
        }.get(mode, "Unknown"),
    }


@server.tool()
async def vibe_configure_provider(
    ctx: Context,
    name: str,
    api_base: str,
    api_key_env_var: str,
    api_style: str = "openai",
    backend: str = "generic",
) -> dict[str, Any]:
    """Add or update a provider configuration (runtime only).

    Args:
        name: Provider identifier
        api_base: Base URL for API calls
        api_key_env_var: Environment variable for API key
        api_style: API style - "mistral", "openai", or "anthropic"
        backend: Backend implementation - "mistral", "generic", or "anthropic"

    Returns:
        Confirmation with provider details

    """
    config = get_vibe_config()

    try:
        new_provider = ProviderConfig(
            name=name,
            api_base=api_base,
            api_key_env_var=api_key_env_var,
            api_style=api_style,  # type: ignore
            backend=backend,  # type: ignore
        )
    except Exception as e:
        return {
            "success": False,
            "error": f"Invalid provider configuration: {e}",
        }

    # Check if provider already exists
    existing = config.get_provider(name)
    if existing:
        # Update existing (remove and re-add)
        config.providers = [p for p in config.providers if p.name != name]

    config.providers.append(new_provider)
    logger.info(f"[VIBE] Added/updated provider: {name}")

    return {
        "success": True,
        "provider": name,
        "api_base": api_base,
        "available": new_provider.is_available(),
        "note": "This change is runtime-only. Add to vibe_config.toml for persistence.",
    }


@server.tool()
async def vibe_session_resume(
    ctx: Context,
    session_id: str,
    prompt: str | None = None,
    cwd: str | None = None,
    timeout_s: float | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Resume a previous Vibe session.

    Args:
        session_id: Session ID to resume (partial match supported)
        prompt: Optional new prompt to continue with
        cwd: Working directory
        timeout_s: Timeout in seconds

    Returns:
        Result of the resumed session

    """
    # Verify session exists
    target_path = None

    # Search in session directory
    if VIBE_SESSION_DIR.exists():
        files = list(VIBE_SESSION_DIR.glob(f"*{session_id}*.json"))
        if files:
            target_path = files[0]

    if not target_path:
        return {
            "success": False,
            "error": f"Session '{session_id}' not found",
            "hint": "Use vibe_list_sessions to see available sessions",
        }

    # Extract full session ID from filename
    full_session_id = target_path.stem.replace("session_", "")

    # Use vibe_prompt with session continuation
    return cast(
        "dict[str, Any]",
        await vibe_prompt(
            ctx=ctx,
            prompt=prompt or "Continue from where we left off.",
            cwd=cwd,
            timeout_s=timeout_s,
            session_id=full_session_id,
            model=model,
        ),
    )


# =============================================================================
# MCP TOOLS - UTILITY (5 tools)
# =============================================================================


@server.tool()
async def vibe_ask(
    ctx: Context,
    question: str,
    cwd: str | None = None,
    timeout_s: float | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Ask Vibe AI a quick question (read-only, no tool execution).

    Args:
        question: The question to ask
        cwd: Working directory
        timeout_s: Timeout in seconds (default: 300)

    Returns:
        AI response without file modifications

    """
    return cast(
        "dict[str, Any]",
        await vibe_prompt(
            ctx=ctx,
            prompt=question,
            cwd=cwd,
            timeout_s=timeout_s or 300,
            mode="plan",
            max_turns=3,
            output_format="json",
            model=model,
        ),
    )


@server.tool()
async def vibe_execute_subcommand(
    ctx: Context,
    subcommand: str,
    args: list[str] | None = None,
    cwd: str | None = None,
    timeout_s: float | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute a specific Vibe CLI subcommand (utility operations).

    For AI interactions, use vibe_prompt() instead.

    Allowed subcommands:
        list-editors, list-modules, run, enable, disable, install,
        agent-reset, agent-on, agent-off, vibe-status, vibe-continue,
        vibe-cancel, vibe-help, eternal-engine, screenshots

    Args:
        subcommand: The Vibe subcommand
        args: Optional arguments
        cwd: Working directory
        timeout_s: Timeout in seconds
        env: Additional environment variables

    Returns:
        Command output and exit code

    """
    vibe_path = resolve_vibe_binary()
    if not vibe_path:
        return {"success": False, "error": "Vibe CLI not found"}

    sub = (subcommand or "").strip()
    if not sub:
        return {"success": False, "error": "Missing subcommand"}

    if sub in BLOCKED_SUBCOMMANDS:
        return {
            "success": False,
            "error": f"Subcommand '{sub}' is interactive and blocked",
            "suggestion": "Use vibe_prompt() for AI interactions",
        }

    if sub not in ALLOWED_SUBCOMMANDS:
        return {
            "success": False,
            "error": f"Unknown subcommand: '{sub}'",
            "allowed": sorted(ALLOWED_SUBCOMMANDS),
        }

    argv = [vibe_path, sub]
    if args:
        # Filter out interactive arguments
        clean_args = [str(a) for a in args if a != "--no-tui"]
        argv.extend(clean_args)

    # Create preview from subcommand and args
    preview = f"{sub} {' '.join(str(a) for a in (args or []))[:50]}"

    return await run_vibe_subprocess(
        argv=argv,
        cwd=cwd,
        timeout_s=timeout_s or DEFAULT_TIMEOUT_S,
        env=env,
        ctx=ctx,
        prompt_preview=preview,
    )


@server.tool()
async def vibe_list_sessions(ctx: Context, limit: int = 10) -> dict[str, Any]:
    """List recent Vibe session logs with metrics.

    Useful for tracking costs, context size, and session IDs for resuming.

    Args:
        limit: Number of sessions to return (default: 10)

    Returns:
        List of recent sessions with metadata

    """
    if not VIBE_SESSION_DIR.exists():
        return {
            "success": False,
            "error": f"Session directory not found at {VIBE_SESSION_DIR}",
        }

    try:
        files = sorted(
            VIBE_SESSION_DIR.glob("session_*.json"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )[:limit]

        sessions = []
        for f in files:
            try:
                with open(f, encoding="utf-8") as jf:
                    data = json.load(jf)
                    meta = data.get("metadata", {})
                    stats = meta.get("stats", {})

                    sessions.append(
                        {
                            "session_id": meta.get("session_id"),
                            "timestamp": meta.get("start_time"),
                            "steps": stats.get("steps", 0),
                            "prompt_tokens": stats.get("session_prompt_tokens", 0),
                            "completion_tokens": stats.get("session_completion_tokens", 0),
                            "file": f.name,
                        },
                    )
            except Exception as e:
                logger.debug(f"Failed to parse session {f.name}: {e}")

        return {
            "success": True,
            "sessions": sessions,
            "count": len(sessions),
        }

    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        return {
            "success": False,
            "error": f"Failed to list sessions: {e}",
        }


@server.tool()
async def vibe_session_details(ctx: Context, session_id_or_file: str) -> dict[str, Any]:
    """Get full details of a specific Vibe session.

    Args:
        session_id_or_file: Session ID or filename

    Returns:
        Full session details including history and token counts

    """
    target_path = None

    # Check absolute path
    if os.path.isabs(session_id_or_file) and os.path.exists(session_id_or_file):
        target_path = Path(session_id_or_file)

    # Check in session directory
    elif (VIBE_SESSION_DIR / session_id_or_file).exists():
        target_path = VIBE_SESSION_DIR / session_id_or_file

    # Search by pattern
    else:
        files = list(VIBE_SESSION_DIR.glob(f"*{session_id_or_file}*.json"))
        if files:
            target_path = files[0]

    if not target_path:
        return {
            "success": False,
            "error": f"Session '{session_id_or_file}' not found",
        }

    try:
        with open(target_path, encoding="utf-8") as f:
            data = json.load(f)
            return {
                "success": True,
                "data": data,
            }
    except Exception as e:
        logger.error(f"Failed to read session: {e}")
        return {
            "success": False,
            "error": f"Failed to read session: {e}",
        }


@server.tool()
async def vibe_reload_config(ctx: Context) -> dict[str, Any]:
    """Reload the Vibe configuration from disk.

    Returns:
        New configuration summary

    """
    global _current_mode, _current_model

    try:
        config = reload_vibe_config()

        # Reset runtime overrides
        _current_mode = config.default_mode
        _current_model = None

        return {
            "success": True,
            "active_model": config.active_model,
            "mode": config.default_mode.value,
            "providers_count": len(config.providers),
            "models_count": len(config.models),
        }
    except Exception as e:
        logger.error(f"Failed to reload config: {e}")
        return {
            "success": False,
            "error": f"Failed to reload config: {e}",
        }


# =============================================================================
# MCP TOOLS - DATABASE (2 tools)
# =============================================================================


@server.tool()
async def vibe_check_db(
    ctx: Context,
    query: str | None = None,
    action: str | None = None,
    expected_files: list[str] | None = None,
    verify_integrity: bool = False,
    log_output: bool = False,
    timeout_s: float | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Execute a read-only SQL SELECT query against the AtlasTrinity database OR verify files.

    CRITICAL: This tool ONLY accepts valid SQL SELECT statements OR a list of expected files.

    MODES:
    1. RAW SQL: Provide `query` (e.g., "SELECT * FROM sessions").
    2. FILE CHECK: Provide `expected_files` (e.g., ["task.md", "src/main.py"]).
       - This works by querying the 'files' table.

    SCHEMA:
    - sessions: id, started_at, ended_at
    - tasks: id, session_id, goal, status, created_at
    - task_steps: id, task_id, sequence_number, action, tool, status, error_message
    - tool_executions: id, step_id, server_name, tool_name, arguments, result
    - logs: timestamp, level, source, message
    - files: id, path, name, size, mtime, is_dir, last_scanned

    Args:
        query: A valid SQL SELECT statement (optional if expected_files is provided).
        action: (Optional) Description of the action (used for logging/logic).
        expected_files: (Optional) List of filenames or paths to verify existence of.
        verify_integrity: (Optional) Unused flag, kept for compatibility.
        log_output: (Optional) Unused flag, kept for compatibility.
        timeout_s: (Optional) Unused flag, kept for compatibility.
        cwd: (Optional) Unused flag, kept for compatibility.

    Returns:
        Query results as list of dictionaries OR file verification results.

    """
    from sqlalchemy import text

    from src.brain.memory.db.manager import db_manager

    # SMART LOGIC: Construct query from expected_files if query is missing
    if not query and expected_files:
        if not isinstance(expected_files, list):
            return {
                "success": False,
                "error": "Argument 'expected_files' must be a list of strings.",
            }

        # Build a safe query using OR conditions for the 'files' table
        # We search by 'path' ending with the filename or containing it
        conditions = []
        for f in expected_files:
            # Simple sanitization: remove single quotes
            safe_f = f.replace("'", "")
            conditions.append(f"path LIKE '%{safe_f}'")
            conditions.append(f"name = '{safe_f}'")  # Also check exact name match

        if conditions:
            where_clause = " OR ".join(conditions)
            query = f"SELECT path, name, size, mtime FROM files WHERE {where_clause}"
        else:
            return {
                "success": False,
                "error": "List of 'expected_files' was provided but empty.",
            }

    if not query:
        return {
            "success": False,
            "error": "Either 'query' OR 'expected_files' must be provided.",
            "usage": "vibe_check_db(query='SELECT * ...') OR vibe_check_db(expected_files=['file1.py'])",
        }

    # Basic SQL validation
    clean_query = query.strip().upper()

    # 1. Reject natural language (heuristic: many words, no SQL-specific structure)
    words = query.split()
    if len(words) > 5 and not any(k in clean_query for k in ["SELECT", "FROM", "WHERE", "JOIN"]):
        return {
            "success": False,
            "error": "This tool requires a SQL query, not natural language. For tasks or questions, use 'vibe_prompt' or 'vibe_ask'.",
            "hint": f"Your input looked like a goal: '{query[:50]}...'",
        }

    # 2. Enforce SELECT only
    if not clean_query.startswith("SELECT"):
        return {
            "success": False,
            "error": "Only SELECT queries are allowed for safety and read-only access.",
        }

    # 3. Prevent destructive operations
    forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "TRUNCATE", "ALTER", "CREATE"]
    if any(re.search(rf"\b{f}\b", clean_query) for f in forbidden):
        return {
            "success": False,
            "error": "Forbidden keyword detected in query. Only read-only SELECT is allowed.",
        }

    # Use central DB manager when available
    try:
        await db_manager.initialize()
        if not db_manager.available:
            return {"success": False, "error": "Database not initialized"}

        session = await db_manager.get_session()
        try:
            res = await session.execute(text(query))
            rows = [dict(r) for r in res.mappings().all()]
            return {"success": True, "count": len(rows), "data": rows}
        finally:
            await session.close()

    except Exception as e:
        logger.error(f"Database query error: {e}")
        return {"success": False, "error": str(e)}


@server.tool()
async def vibe_get_system_context(ctx: Context) -> dict[str, Any]:
    """Retrieve current operational context from the database.

    Helps Vibe focus on the current state before performing deep analysis.

    Returns:
        Current session, recent tasks, and errors

    """

    try:
        await db_manager.initialize()
        if not db_manager.available:
            return {"success": False, "error": "Database not initialized"}

        db_session = await db_manager.get_session()
        try:
            # Latest session
            res = await db_session.execute(
                text("SELECT id, started_at FROM sessions ORDER BY started_at DESC LIMIT 1"),
            )
            session_row = res.mappings().first()
            session_id = str(session_row["id"]) if session_row else None

            # Latest tasks
            tasks = []
            if session_id:
                tasks_res = await db_session.execute(
                    text(
                        "SELECT id, goal, status, created_at FROM tasks WHERE session_id = :sid ORDER BY created_at DESC LIMIT 5",
                    ),
                    {"sid": session_id},
                )
                tasks = [dict(r) for r in tasks_res.mappings().all()]

            # Recent errors
            errors_res = await db_session.execute(
                text(
                    "SELECT timestamp, source, message FROM logs WHERE level IN ('ERROR', 'WARNING') ORDER BY timestamp DESC LIMIT 5",
                ),
            )
            errors = [dict(r) for r in errors_res.mappings().all()]

            return {
                "success": True,
                "current_session_id": session_id,
                "recent_tasks": tasks,
                "recent_errors": errors,
                "system_root": SYSTEM_ROOT,
                "project_root": VIBE_WORKSPACE,
            }
        finally:
            await db_session.close()
    except Exception as e:
        logger.error(f"Database query error in vibe_get_system_context: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    logger.info("[VIBE] MCP Server starting (v3.0 Hyper-Refactored)...")
    prepare_workspace_and_instructions()
    cleanup_old_instructions()

    # Pre-load configuration
    try:
        config = get_vibe_config()
        logger.info(
            f"[VIBE] Configuration loaded: {len(config.models)} models, {len(config.providers)} providers",
        )
    except Exception as e:
        logger.warning(f"[VIBE] Could not load configuration: {e}")

    try:
        # Check for uvloop
        try:
            import uvloop

            with asyncio.Runner(loop_factory=uvloop.new_event_loop) as runner:
                runner.run(server.run_stdio_async())
        except ImportError:
            server.run(transport="stdio")

    except (BrokenPipeError, KeyboardInterrupt, asyncio.CancelledError):
        logger.info("[VIBE] Server shutdown requested")
        sys.exit(0)
    except ExceptionGroup as eg:
        if any(isinstance(e, BrokenPipeError) or "Broken pipe" in str(e) for e in eg.exceptions):
            sys.exit(0)
        logger.error(f"[VIBE] Unexpected error group: {eg}")
        sys.exit(1)
    except BaseException as e:
        if isinstance(e, BrokenPipeError) or "Broken pipe" in str(e):
            sys.exit(0)
        logger.error(f"[VIBE] Unexpected error: {e}")
        sys.exit(1)
