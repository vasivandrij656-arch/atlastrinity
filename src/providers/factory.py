"""
LLM Provider Factory
====================

Creates the appropriate LLM provider (CopilotLLM or WindsurfLLM) based on
the `models.provider` setting in config.yaml.

Usage:
    from src.providers.factory import create_llm

    llm = create_llm(model_name="gpt-4o")
    llm = create_llm(model_name="swe-1.5", provider="windsurf")
"""

from __future__ import annotations

import os
from typing import Any
from src.brain.config.config_loader import config


def get_provider_name() -> str:
    """Get the configured provider name from config or environment."""
    # 1. Environment variable override
    env_provider = os.getenv("LLM_PROVIDER", "").lower()
    if env_provider in ("copilot", "windsurf"):
        return env_provider

    # 2. Config.yaml
    try:
        from src.brain.config.config_loader import config

        provider = config.get("models.provider", "copilot")
        if provider and isinstance(provider, str):
            return provider.lower()
    except Exception:
        pass

    return "copilot"


def create_llm(
    model_name: str | None = None,
    vision_model_name: str | None = None,
    api_key: str | None = None,
    max_tokens: int | None = None,
    provider: str | None = None,
    **kwargs: Any,
) -> Any:
    """Create an LLM instance based on the configured provider.

    Args:
        model_name: Model name (provider-specific)
        vision_model_name: Vision model name (CopilotLLM only)
        api_key: API key override
        max_tokens: Max tokens for generation
        provider: Force a specific provider ("copilot" or "windsurf")
        **kwargs: Additional arguments passed to the LLM constructor

    Returns:
        CopilotLLM or WindsurfLLM instance
    """
    # Support "provider:model" syntax (e.g., "copilot:gpt-4o" or "windsurf:deepseek-v3")
    if model_name and ":" in model_name:
        parts = model_name.split(":", 1)
        if parts[0].lower() in ("copilot", "windsurf"):
            provider = parts[0]
            model_name = parts[1]

    # Model Alias Mapping (System-driven)
    model_name = config.resolve_model_alias(model_name)

    chosen_provider = (provider or get_provider_name()).lower()

    if chosen_provider == "windsurf":
        from .windsurf import WindsurfLLM

        kwargs.pop("vision_model_name", None)

        return WindsurfLLM(
            model_name=model_name,
            vision_model_name=vision_model_name,
            api_key=api_key,
            max_tokens=max_tokens,
            **kwargs,
        )
    from .copilot import CopilotLLM

    return CopilotLLM(
        model_name=model_name,
        vision_model_name=vision_model_name,
        api_key=api_key,
        max_tokens=max_tokens,
        **kwargs,
    )
