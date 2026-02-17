import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))


async def simulate_tier3_fallback():
    print("🚀 Starting Live Tier 3 Fallback Simulation")

    # We sabotages the environment by removing keys or setting them to invalid values
    # BUT we want to keep the Copilot key if it exists, or at least let it try the proxy.

    # In Vibe MCP, we use the library vibe_server directly to invoke the tool logic
    from src.mcp_server import vibe_server

    # We will call vibe_implement_feature
    # It will use devstral-2 (Tier 1) by default

    test_prompt = "Create a simple hello world in python"

    # Sabotage providers: We mock get_provider to return unavailable for mistral and openrouter
    from src.mcp_server.vibe_config import ApiStyle, Backend, ProviderConfig

    def mock_get_provider(name):
        if name in ("mistral", "openrouter"):
            p = ProviderConfig(
                name=name,
                api_base="http://fail",
                api_key_env_var=f"FAIL_{name}",
                api_style=ApiStyle.OPENAI,
                backend=Backend.GENERIC,
            )
            return p
        # For copilot, we return a working one (or at least valid config)
        if name == "copilot":
            return ProviderConfig(
                name="copilot",
                api_base="http://localhost:8086",
                api_key_env_var="COPILOT_SESSION_TOKEN",
                api_style=ApiStyle.OPENAI,
                backend=Backend.GENERIC,
            )
        return None

    print("⚠️  Sabotaging Tier 1 (Mistral) and Tier 2 (OpenRouter)...")

    with patch("src.mcp_server.vibe_server.get_vibe_config") as mock_conf_getter:
        # Use explicit config instead of calling the mocked function
        mock_config = MagicMock()
        mock_config.get_provider = MagicMock(side_effect=mock_get_provider)

        # Explicitly set path properties
        test_workspace = os.path.join(tempfile.gettempdir(), "vibe_test_workspace")
        os.makedirs(test_workspace, exist_ok=True)
        mock_config.workspace = test_workspace

        # Mock model lookup (required for vibe_server internal checks)
        def mock_get_model(alias):
            m = MagicMock()
            m.name = alias
            m.alias = alias
            return m

        mock_config.get_model_by_alias = MagicMock(side_effect=mock_get_model)

        # Verify gpt-4o is there
        copilot_model = mock_config.get_model_by_alias("gpt-4o")
        if copilot_model:
            print(
                f"📡 Copilot Model from config: {copilot_model.name} (Alias: {copilot_model.alias})"
            )
        else:
            print("📡 Copilot Model gpt-4o not found in config")

        mock_conf_getter.return_value = mock_config

        # Now we invoke the tool. We expect it to:
        # 1. Try Mistral -> Fail (due to invalid setup/mock)
        # 2. Check OpenRouter -> See it's unavailable (via mock_get_provider)
        # 3. Fallback to Copilot -> Trigger gpt-4o alias -> Which points to raptor-mini

        # Mock Context
        mock_ctx = MagicMock()
        mock_ctx.log = AsyncMock()

        print("🛠️  Invoking vibe_implement_feature...")
        try:
            result = await vibe_server.vibe_implement_feature(
                ctx=mock_ctx, goal=test_prompt, cwd=str(PROJECT_ROOT)
            )
            print("\n✅ Simulation Call Finished.")
            print(f"Result success: {result.get('success')}")
        except Exception as e:
            print(f"❌ Simulation Call Failed: {e}")


if __name__ == "__main__":
    asyncio.run(simulate_tier3_fallback())
