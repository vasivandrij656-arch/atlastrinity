import asyncio
import os
import sys
from pathlib import Path

# Add project root and src to path for imports
PROJECT_ROOT = Path("/Users/dev/Documents/GitHub/atlastrinity")
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SRC_ROOT))

# Force setup of env vars
os.environ["WINDSURF_API_KEY"] = (
    "sk-ws-01-3vQio5CLce8beK1OqKX1zvWmP-nTjOV3JpO3O5v3tI6Yy7SIRWJyanWHnCpjDnCKIOd1JVKFww8DKfmu5yRqVqGbazlrug"
)
os.environ["WINDSURF_MODE"] = (
    "cascade"  # Use cascade mode as it's most reliable/bypasses chat blocks
)

from langchain_core.messages import HumanMessage

from providers.windsurf import WindsurfLLM


async def test_model(model_id: str):
    print(f"\n[TESTING] Model: {model_id}")

    try:
        # Initialize LLM
        llm = WindsurfLLM(model_name=model_id)

        print(f"  > Mode: {llm._mode}")
        print("  > Protocol: Connect-RPC")
        print("  > Sending request...")

        # Simple prompt
        messages = [HumanMessage(content="Say 'OK' and nothing else.")]

        # Time the request
        import time

        start = time.time()

        # We use invoke for a direct synchronous-like test in async wrapper
        # Actually WindsurfLLM.invoke is synchronous in langchain context but we can wrap it
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: llm.invoke(messages))

        end = time.time()
        duration = end - start

        if isinstance(response.content, list):
            # Handle list response
            content_str = str(response.content).strip()
        else:
            # Handle string response
            content_str = str(response.content).strip()

        if content_str and all(
            err not in content_str
            for err in ["WINDSURF ERROR", "resource_exhausted", "internal error"]
        ):
            print(f"  [SUCCESS] Response: {content_str} ({duration:.2f}s)")
            return True, content_str
        print(f"  [FAILED] Empty response ({duration:.2f}s)")
        return False, "Empty"

    except Exception as e:
        print(f"  [ERROR] {e!s}")
        return False, str(e)


async def main():
    test_models = [
        "swe-1.5",
        "claude-4.6-opus",
        "gpt-5.2-codex",
        "deepseek-v3",
        "llama-3.1-405b",
        "sonnet-4.5",
    ]

    results = {}
    for m in test_models:
        success, info = await test_model(m)
        results[m] = "✅ Working" if success else f"❌ Failed ({info})"

    print("\n" + "=" * 60)
    print("WINDSURF MODEL DIAGNOSTIC REPORT")
    print("=" * 60)
    for m, res in results.items():
        print(f"{m:<20}: {res}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
