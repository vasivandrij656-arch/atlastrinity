from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from watchdog.events import FileSystemEventHandler as _BaseHandler  # pyre-ignore
    from watchdog.observers import Observer  # pyre-ignore
else:
    try:
        from watchdog.events import FileSystemEventHandler as _BaseHandler
        from watchdog.observers import Observer
    except ImportError:
        print("Warning: 'watchdog' module not found. Auto-sync will not work in watch mode.")

        class _BaseHandler:
            """Fallback for missing watchdog"""

        class Observer:
            """Fallback for missing watchdog"""

            def schedule(self, *args: Any, **kwargs: Any) -> None:
                pass

            def start(self) -> None:
                pass

            def stop(self) -> None:
                pass

            def join(self) -> None:
                pass


# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_SRC = PROJECT_ROOT / "config"
CONFIG_DST_ROOT = Path.home() / ".config" / "atlastrinity"

# Mappings (Template Filename -> Destination Relative Path)
MAPPINGS: dict[str, str] = {
    "config.yaml.template": "config.yaml",
    "behavior_config.yaml.template": "behavior_config.yaml",
    "vibe_config.toml.template": "vibe_config.toml",
    "vibe/agents/accept-edits.toml.template": "vibe/agents/accept-edits.toml",
    "vibe/agents/auto-approve.toml.template": "vibe/agents/auto-approve.toml",
    "vibe/agents/plan.toml.template": "vibe/agents/plan.toml",
    "mcp_servers.json.template": "mcp/config.json",
    "prometheus.yml.template": "prometheus.yml",
}


# Load .env if it exists
def load_env():
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()


load_env()


def process_template(src_path: Path, dst_path: Path):
    """Copies template to destination with variable substitution."""
    try:
        if not src_path.exists():
            return

        with open(src_path, encoding="utf-8") as f:
            content = f.read()

        # Core replacements
        replacements = {
            "${PROJECT_ROOT}": str(PROJECT_ROOT),
            "${HOME}": str(Path.home()),
            "${CONFIG_ROOT}": str(CONFIG_DST_ROOT),
            "${PYTHONPATH}": str(PROJECT_ROOT),
        }

        for key, value in replacements.items():
            content = content.replace(key, value)

        # Dynamic replacements for any ${VARIABLE} from .env / environment
        matches = re.findall(r"\${([A-Z0-9_]+)}", content)
        for var_name in set(matches):
            env_val = os.getenv(var_name)
            if env_val is not None:
                content = content.replace(f"${{{var_name}}}", env_val)

        # Ensure dir exists
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        # Smart write: only overwrite if content is actually different
        if dst_path.exists():
            try:
                with open(dst_path, encoding="utf-8") as f:
                    if f.read() == content:
                        print(f"Skipping {src_path.name} (identical)")
                        return  # Content is identical, skip write
            except Exception:
                pass  # If can't read, proceed to write

        print(f"Syncing {src_path.name} -> {dst_path}")
        with open(dst_path, "w", encoding="utf-8") as f:
            f.write(content)

    except Exception as e:
        print(f"Error processing template {src_path}: {e}")


# pyre-ignore[invalid-inheritance]
class ConfigHandler(_BaseHandler):
    def on_modified(self, event):
        if event.is_directory:
            return

        # Get relative path from config source
        try:
            rel_path = Path(str(event.src_path)).relative_to(CONFIG_SRC)
            filename = str(rel_path)
        except ValueError:
            return

        if filename in MAPPINGS:
            dst_rel = MAPPINGS[filename]
            dst_path = CONFIG_DST_ROOT / dst_rel
            # Add a small delay to ensure write verify
            time.sleep(0.1)
            process_template(Path(str(event.src_path)), dst_path)
        elif "vibe/agents/" in filename and filename.endswith(".template"):
            # Dynamic agent sync
            dst_name = Path(filename).stem
            dst_path = CONFIG_DST_ROOT / "vibe" / "agents" / dst_name
            time.sleep(0.1)
            process_template(Path(str(event.src_path)), dst_path)


def ensure_github_remote_setup():
    """Ensures git remote 'origin' is configured with GITHUB_TOKEN for passwordless operations."""
    try:
        import subprocess

        # 1. Get token from env
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            return

        # 2. Check current remote
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                check=True,
            )
            current_url = result.stdout.strip()
        except subprocess.CalledProcessError:
            return

        # 3. Check if token is already in URL
        # Format: https://TOKEN@github.com/solagurma/atlastrinity.git
        if token in current_url:
            return

        # 4. Update remote URL
        new_url = f"https://{token}@github.com/solagurma/atlastrinity.git"
        subprocess.run(
            ["git", "remote", "set-url", "origin", new_url], cwd=str(PROJECT_ROOT), check=True
        )

    except Exception:
        pass


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Watch or sync configs")
    parser.add_argument("--sync-only", action="store_true", help="Sync once and exit")
    args = parser.parse_args()

    # Initial sync
    # Standard mappings
    for tpl, dst in MAPPINGS.items():
        src = CONFIG_SRC / tpl
        if src.exists():
            process_template(src, CONFIG_DST_ROOT / dst)

    # Dynamic Agent templates
    agent_tpl_dir = CONFIG_SRC / "vibe" / "agents"
    if agent_tpl_dir.exists():
        for tpl in agent_tpl_dir.glob("*.template"):
            dst_name = tpl.stem
            process_template(tpl, CONFIG_DST_ROOT / "vibe" / "agents" / dst_name)

    # Ensure GitHub remote is set up (Use token from .env)
    ensure_github_remote_setup()

    if args.sync_only:
        return

    if Observer is None:
        print("Watchdog not installed, exiting watch mode.")
        return

    event_handler = ConfigHandler()
    observer = Observer()

    # Watch config directory
    observer.schedule(event_handler, str(CONFIG_SRC), recursive=True)

    # Also watch .env file if it exists
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        # pyre-ignore[invalid-inheritance]
        class EnvHandler(_BaseHandler):
            def on_modified(self, event):
                if event.src_path == str(env_file):
                    load_env()
                    for tpl, dst in MAPPINGS.items():
                        process_template(CONFIG_SRC / tpl, CONFIG_DST_ROOT / dst)

        observer.schedule(EnvHandler(), str(PROJECT_ROOT), recursive=False)

    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()


if __name__ == "__main__":
    main()
