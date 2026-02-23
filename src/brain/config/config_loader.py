import os
import shutil
from pathlib import Path
from typing import IO, Any, cast

import yaml

try:
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover

    def dotenv_values(
        dotenv_path: str | os.PathLike | None = None,
        stream: IO[str] | None = None,
        verbose: bool = False,
        interpolate: bool = True,
        encoding: str | None = "utf-8",
    ) -> dict[str, str | None]:
        return {}

    # type: ignore[reportAssignmentType]

import re

from src.brain.config import CONFIG_ROOT, MCP_DIR, PROJECT_ROOT, deep_merge


class SystemConfig:
    """Singleton for system configuration with synchronization logic."""

    _instance = None
    _config: dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sync_configs()
            cls._instance._load_config()
        return cls._instance

    def _sync_configs(self):
        """Ensure global configuration directories exist.
        Config is read ONLY from global location (~/.config/atlastrinity/).
        User config values have PRIORITY over built-in defaults.
        Templates are synced to global location on first run only.
        """
        CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
        MCP_DIR.mkdir(parents=True, exist_ok=True)

        # Configuration files to sync from templates
        configs_to_sync = [
            {
                "global": CONFIG_ROOT / "config.yaml",
                "template": PROJECT_ROOT / "config" / "config.yaml.template",
                "use_defaults": True,  # Generate from _get_defaults() if template missing
            },
            {
                "global": CONFIG_ROOT / "behavior_config.yaml",
                "template": PROJECT_ROOT / "config" / "behavior_config.yaml.template",
                "use_defaults": False,
            },
            {
                "global": CONFIG_ROOT / "vibe_config.toml",
                "template": PROJECT_ROOT / "config" / "vibe_config.toml.template",
                "use_defaults": False,
            },
            {
                "global": MCP_DIR / "config.json",
                "template": PROJECT_ROOT / "config" / "mcp_servers.json.template",
                "use_defaults": False,
            },
        ]

        # Sync each config file (first run only)
        for config_spec in configs_to_sync:
            global_path: Path = cast(Path, config_spec["global"])
            template_path: Path = cast(Path, config_spec["template"])

            if not global_path.exists():
                if config_spec["use_defaults"]:
                    # Generate from defaults (for config.yaml)
                    with open(global_path, "w", encoding="utf-8") as f:
                        yaml.dump(
                            self._get_defaults(),
                            f,
                            default_flow_style=False,
                            allow_unicode=True,
                        )
                elif template_path.exists():
                    # Copy from template
                    shutil.copy2(str(template_path), str(global_path))

        # Load .env secrets into process environment (do NOT rewrite config files)
        env_path = CONFIG_ROOT / ".env"
        if env_path.exists():
            env_vars = dotenv_values(env_path)
            for key, value in (env_vars or {}).items():
                if value is None:
                    continue
                if os.environ.get(key) != value:
                    os.environ[key] = value

    def _load_config(self):
        """Loads configuration exclusively from the global system folder."""
        config_path = CONFIG_ROOT / "config.yaml"
        if not config_path.exists():
            self._config = self._get_defaults()
            return
        try:
            with open(config_path, encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                self._config = deep_merge(self._get_defaults(), loaded)
        except Exception:
            self._config = self._get_defaults()

    def _get_defaults(self) -> dict[str, Any]:
        """Default configuration with fallback to environment variables."""
        base_defaults = {
            "agents": {
                "atlas": {
                    "model": "",  # Must be set in config.yaml
                    "deep_model": "",  # Deep chat model for philosophical conversations
                    "temperature": 0.7,
                    "max_tokens": 2000,
                    "max_tokens_deep": 12000,  # Deep persona/philosophical mode (increased)
                },
                "tetyana": {
                    "model": "",  # Execution (Main)
                    "reasoning_model": "",  # Tool Selection (Reasoning)
                    "reflexion_model": "",  # Self-Correction
                    "temperature": 0.5,
                    "max_tokens": 2000,
                },
                "grisha": {
                    "vision_model": "",
                    "strategy_model": "",
                    "temperature": 0.3,
                    "max_tokens": 1500,
                },
            },
            "orchestrator": {
                "max_recursion_depth": 5,
                "task_timeout": 300,
                # Who should announce and lead recovery when a step fails: 'atlas' or 'grisha'
                "recovery_voice_agent": "grisha",
                # If true, call Grisha to validate failed steps even when requires_verification is not set
                "validate_failed_steps_with_grisha": True,
                "subtask_timeout": 120,
            },
            "mcp": {
                "terminal": {"enabled": True},
                "filesystem": {"enabled": True},
                "macos_use": {"enabled": True},
                "sequential_thinking": {
                    "enabled": True,
                    "model": "",  # Must be set in config.yaml
                },
                "vibe": {"enabled": True, "workspace": str(CONFIG_ROOT / "vibe_workspace")},
            },
            "security": {
                "dangerous_commands": ["rm -r", "mkfs"],
                "require_confirmation": True,
            },
            "voice": {
                "tts": {
                    "engine": os.getenv("TTS_ENGINE", "ukrainian-tts"),
                    "device": "mps",
                },
                "stt": {
                    "model": os.getenv("STT_MODEL", "large-v3"),
                    "language": "uk",
                },
            },
            "system": {
                "workspace_path": "${CONFIG_ROOT}/workspace",
                "repository_path": str(
                    PROJECT_ROOT,
                ),  # Path to Trinity source code for self-healing
            },
            "database": {
                # Default to local SQLite (async via aiosqlite). Use DATABASE_URL env var to override.
                "url": os.getenv(
                    "DATABASE_URL",
                    f"sqlite+aiosqlite:///{CONFIG_ROOT}/atlastrinity.db",
                ),
            },
            "models": {
                "aliases": {
                    "atlas-deep": "gpt-4.1",
                },
                "copilot_fallback": "gpt-4o",
            },
            "state": {"redis_url": os.getenv("REDIS_URL", "redis://localhost:6379/0")},
            "logging": {"level": "INFO", "max_log_size": 10485760, "backup_count": 5},
        }

        template_yaml = PROJECT_ROOT / "config" / "config.yaml.template"
        if template_yaml.exists():
            try:
                with open(template_yaml, encoding="utf-8") as f:
                    template = yaml.safe_load(f) or {}
                return deep_merge(base_defaults, template)
            except Exception:
                return base_defaults

        return base_defaults

    def _substitute_placeholders(self, value: Any) -> Any:
        """Substitute ${VAR} placeholders recursively in strings, lists, or dicts."""
        if isinstance(value, str):

            def replace_match(match):
                var_name = match.group(1)
                if var_name == "PROJECT_ROOT":
                    return str(PROJECT_ROOT)
                if var_name == "CONFIG_ROOT":
                    return str(CONFIG_ROOT)
                if var_name == "HOME":
                    return str(Path.home())
                # Fallback to environment variables
                return os.getenv(var_name, match.group(0))

            return re.sub(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}", replace_match, value)

        if isinstance(value, list):
            return [self._substitute_placeholders(item) for item in value]

        if isinstance(value, dict):
            return {k: self._substitute_placeholders(v) for k, v in value.items()}

        return value

    def get(self, key_path: str, default: Any = None) -> Any:
        keys = key_path.split(".")
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        # Custom logic for sequential thinking model inheritance
        if key_path == "mcp.sequential_thinking.model" and not value:
            return self.get("models.reasoning") or self.get("models.default")

        return self._substitute_placeholders(value)

    def get_api_key(self, key_name: str) -> str:
        env_map = {
            "copilot_api_key": "COPILOT_API_KEY",
            "github_token": "GITHUB_TOKEN",
            "openai_api_key": "OPENAI_API_KEY",
        }

        env_var = env_map.get(key_name)
        if env_var:
            val = os.getenv(env_var)
            if val:
                return val

        return cast("str", self.get(f"api.{key_name}", ""))

    def get_agent_config(self, agent_name: str) -> dict[str, Any]:
        """Returns specific agent configuration with global model inheritance."""
        agent_config = self.get(f"agents.{agent_name}", {}).copy()

        # 1. Main model inheritance
        if not agent_config.get("model"):
            agent_config["model"] = self.get("models.default")

        # 2. Tetyana specialized models
        if agent_name == "tetyana":
            if not agent_config.get("reasoning_model"):
                agent_config["reasoning_model"] = self.get("models.reasoning")
            if not agent_config.get("vision_model"):
                agent_config["vision_model"] = self.get("models.vision")
            if not agent_config.get("reflexion_model"):
                agent_config["reflexion_model"] = self.get("models.default")

        # 3. Grisha specialized models
        elif agent_name == "grisha":
            if not agent_config.get("vision_model"):
                agent_config["vision_model"] = self.get("models.vision")
            if not agent_config.get("strategy_model"):
                agent_config["strategy_model"] = self.get("models.reasoning") or self.get(
                    "models.default",
                )

        return cast("dict[str, Any]", agent_config)

    def get_security_config(self) -> dict[str, Any]:
        """Returns security configuration."""
        return cast("dict[str, Any]", self.get("security", {}))

    def resolve_model_alias(self, model_name: str | None) -> str | None:
        """Resolves a virtual model ID to a real provider model ID via config aliases."""
        if not model_name:
            return model_name

        aliases = self.get("models.aliases", {})
        if not isinstance(aliases, dict):
            return model_name

        return aliases.get(model_name, model_name)

    @property
    def all(self) -> dict[str, Any]:
        return self._config


config = SystemConfig()


def get_config_value(section: str, key: str, default: Any = None) -> Any:
    """Legacy compatibility function for fetching config values."""
    path = f"{section}.{key}" if section else key
    return config.get(path, default)
