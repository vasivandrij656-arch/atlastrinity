"""
Model Registry
==============

Single source of truth for loading model definitions from config/all_models.json.
All providers and proxies should use this module instead of hardcoding model lists.

Usage:
    from providers.utils.model_registry import get_copilot_models, get_windsurf_models
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# ─── Windsurf Internal UID Map ────────────────────────────────────────────────
# Display name → Windsurf/Codeium internal proto model UID
# This is the ONLY place where Windsurf internal UIDs should be defined.
WINDSURF_UID_MAP: dict[str, str] = {
    # Cascade Models
    "swe-1.5": "MODEL_SWE_1_5",
    "swe-1": "MODEL_SWE_1",
    "swe-1-mini": "MODEL_SWE_1_MINI",
    "swe-grep": "MODEL_SWE_GREP",
    "windsurf-fast": "MODEL_CHAT_11121",
    # Windsurf Premier 🚀
    "llama-3.1-405b": "MODEL_LLAMA_3_1_405B",
    "llama-3.1-70b": "MODEL_LLAMA_3_1_70B",
    # Next-Gen Premium (Changelog)
    "claude-4.6-opus": "MODEL_CLAUDE_4_6_OPUS",
    "claude-4.6-opus-fast": "MODEL_CLAUDE_4_6_OPUS_FAST",
    "gpt-5.2-codex": "MODEL_GPT_5_2_CODEX",
    "gpt-5.3-codex-spark": "MODEL_GPT_5_3_CODEX_SPARK",
    "gemini-3-pro": "MODEL_GEMINI_3_PRO",
    "gemini-3-flash": "MODEL_GEMINI_3_FLASH",
    "sonnet-4.5": "MODEL_SONNET_4_5",
    "gpt-5.1-codex": "MODEL_GPT_5_1_CODEX",
    "gpt-5.1-codex-mini": "MODEL_GPT_5_1_CODEX_MINI",
    # Legacy/Standard Premium
    "gpt-4o": "MODEL_GPT_4_O",
    "claude-3.5-sonnet": "MODEL_CLAUDE_3_5_SONNET",
    "deepseek-v3": "MODEL_DEEPSEEK_V3",
    "deepseek-r1": "MODEL_DEEPSEEK_R1",
    "grok-code-fast-1": "MODEL_GROK_CODE_FAST_1",
    "kimi-k2.5": "kimi-k2-5",
}

# ─── Config Path Resolution ──────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_ALL_MODELS_PATH = _PROJECT_ROOT / "config" / "all_models.json"


def _find_all_models_path() -> Path:
    """Resolve the path to all_models.json."""
    # 1. Relative to project root
    if _ALL_MODELS_PATH.exists():
        return _ALL_MODELS_PATH
    # 2. Environment variable override
    env_path = os.getenv("ALL_MODELS_JSON")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    # 3. Fallback — return default even if missing (will raise on load)
    return _ALL_MODELS_PATH


# ─── Loaders ─────────────────────────────────────────────────────────────────


def load_all_models() -> list[dict[str, Any]]:
    """Load all model definitions from config/all_models.json.

    Returns:
        List of model dicts (each with 'id', 'vendor', 'capabilities', etc.)
    """
    path = _find_all_models_path()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("data", [])


def get_copilot_models() -> dict[str, str]:
    """Get Copilot model display names as {id: id}.

    Filters all_models.json entries where vendor == 'Copilot'.
    """
    models = load_all_models()
    return {m["id"]: m["id"] for m in models if m.get("vendor") == "Copilot"}


def get_windsurf_models() -> dict[str, str]:
    """Get Windsurf model display names mapped to internal UIDs.

    Filters all_models.json entries where vendor == 'Windsurf',
    then maps each to its Windsurf internal proto UID via WINDSURF_UID_MAP.

    Models not found in WINDSURF_UID_MAP use their display name as fallback.
    """
    models = load_all_models()
    result: dict[str, str] = {}
    for m in models:
        if m.get("vendor") == "Windsurf":
            model_id: str = m["id"]
            uid = WINDSURF_UID_MAP.get(model_id, model_id)
            if uid is not None:
                result[model_id] = uid
    return result


def get_model_tier(model_id: str, vendor: str | None = None) -> str:
    """Get the tier (free, value, premium) for a given model ID and optional vendor.

    Defaults to 'free' if model not found or tier not specified.
    """
    try:
        models = load_all_models()
        for m in models:
            if m.get("id") == model_id:
                if vendor and m.get("vendor") != vendor:
                    continue
                return m.get("tier", "free")
    except Exception:
        pass
    return "free"
