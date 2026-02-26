"""
Test Windsurf provider with free models.

This script tests the Windsurf provider with all available free models.
It will try each model and report the results.

Usage:
    python scripts/test_windsurf_free_models.py

Environment variables:
    WINDSURF_API_KEY: Your Windsurf API key (required)
    WINDSURF_MODE: Set to 'local', 'direct', or 'proxy' (default: auto-detect)
"""

import os
import sys
import time

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from langchain_core.messages import HumanMessage, SystemMessage

from src.providers.windsurf import WindsurfLLM, _detect_language_server, _ls_heartbeat

# Free models to test
FREE_MODELS = [
    "deepseek-v3",
    "deepseek-r1",
    "swe-1",
    "grok-code-fast-1",
    "kimi-k2.5",
]

# Test prompt
TEST_PROMPT = """
Please provide a brief response to the following question:
What is the capital of France? Also, what is 5+7?

Your response should be in this exact format:
Capital: [capital]
Sum: [sum]
"""


def test_model(model_name: str, mode: str | None = None) -> tuple[bool, str]:
    """Test a single model with the given mode."""

    start_time = time.time()

    try:
        # Set mode if specified
        if mode:
            os.environ["WINDSURF_MODE"] = mode

        # Initialize the model
        llm = WindsurfLLM(model_name=model_name)

        # Make the API call
        response = llm.invoke(
            [
                SystemMessage(content="You are a helpful assistant. Be concise and accurate."),
                HumanMessage(content=TEST_PROMPT),
            ]
        )

        # Process the response
        # Ensure content is a string before calling strip()
        content = (
            str(response.content).strip() if hasattr(response, "content") else str(response).strip()
        )
        elapsed = time.time() - start_time

        # Simple validation of response format
        if "Capital:" in content and "Sum:" in content:
            return True, content
        return False, content

    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = f"Error after {elapsed:.2f}s: {e!s}"
        return False, error_msg

    finally:
        # Clean up environment variable
        os.environ.pop("WINDSURF_MODE", None)


def main():

    # Check API key
    api_key = os.environ.get("WINDSURF_API_KEY")
    if not api_key:
        sys.exit(1)

    # Get mode from env or auto-detect
    mode = os.environ.get("WINDSURF_MODE")
    if not mode:
        # Try to auto-detect LS
        port, csrf = _detect_language_server()
        if port and csrf and _ls_heartbeat(port, csrf):
            mode = "local"
        else:
            mode = "direct"  # Fall back to direct mode

    # Test each model
    results = {}
    for model in FREE_MODELS:
        success, response = test_model(model, mode)
        results[model] = {
            "success": success,
            "response": response,
        }

    # Print summary

    sum(1 for r in results.values() if r["success"])

    for model, result in results.items():
        "✅" if result["success"] else "❌"
        if not result["success"]:
            pass


if __name__ == "__main__":
    main()
