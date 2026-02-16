import asyncio
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.getcwd())

from langchain_core.messages import HumanMessage

from src.providers.windsurf import WindsurfLLM


async def verify_model(model_id: str):
    print(f"\n[TEST] Verifying model: {model_id}...")  # noqa: T201
    try:
        llm = WindsurfLLM(model_id=model_id, temperature=0.0)
        # Force proxy mode for stability in this environment
        llm._mode = "proxy"

        response = await llm.ainvoke([HumanMessage(content="Hello, respond with exactly 'OK'")])
        # AIMessage.content can be str or list of dicts/ContentBlock
        content = response.content
        if isinstance(content, list):
            # Extract text from content blocks if necessary
            result = "".join(
                [
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                ]
            )
        else:
            result = str(content)

        result = result.strip()

        if "OK" in result:
            print(f"✅ Model {model_id} is WORKING (Response: {result})")  # noqa: T201
            return True
        print(f"⚠️ Model {model_id} returned unexpected response: {result}")  # noqa: T201
        return False

    except Exception as e:
        print(f"❌ Model {model_id} FAILED: {e}")  # noqa: T201
        return False


async def main():
    # List of models from all_models.json
    models_to_test = [
        "deepseek-v3",
        "deepseek-r1",
        "swe-1.5",
        "kimi-k2.5",
        "grok-code-fast-1",
        "windsurf-fast",
    ]

    print("--- Windsurf Multi-Model Verification ---")  # noqa: T201

    # Ensure proxy is running (caller's responsibility, but we check env)
    if not os.environ.get("WINDSURF_PROXY_URL"):
        os.environ["WINDSURF_PROXY_URL"] = "http://localhost:8085/v1"
        print(f"Set WINDSURF_PROXY_URL to {os.environ['WINDSURF_PROXY_URL']}")  # noqa: T201

    results = {}
    for model in models_to_test:
        results[model] = await verify_model(model)

    print("\n--- Final Results ---")  # noqa: T201
    for model, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{model:20} : {status}")  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main())
