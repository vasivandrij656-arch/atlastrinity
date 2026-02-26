"""
Quick test for Windsurf provider.
Run: python scripts/test_windsurf_provider.py

Tests all three modes:
1. Local LS (auto-detected from running Windsurf IDE)
2. Direct cloud API
3. Proxy mode (requires windsurf_proxy.py running)
"""

import os
import sys

# Add project root to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# from dotenv import load_dotenv

# load_dotenv()

from langchain_core.messages import HumanMessage, SystemMessage

from src.providers.windsurf import WindsurfLLM, _detect_language_server, _ls_heartbeat


def test_auto_detection():
    """Test LS auto-detection."""
    port, csrf = _detect_language_server()
    if port and csrf:
        _ls_heartbeat(port, csrf)
    else:
        pass
    return port, csrf


def test_mode(mode: str):
    """Test a specific mode."""
    os.environ["WINDSURF_MODE"] = mode
    try:
        llm = WindsurfLLM()
        result = llm.invoke(
            [
                SystemMessage(content="You are helpful. Be brief."),
                HumanMessage(content="What is 2+2? Answer only the number."),
            ]
        )
        content = result.content
        return "[WINDSURF ERROR]" not in content
    except Exception:
        return False
    finally:
        os.environ.pop("WINDSURF_MODE", None)


def main():

    # Check env
    api_key = os.environ.get("WINDSURF_API_KEY", "")
    if not api_key:
        sys.exit(1)

    # Test auto-detection
    port, csrf = test_auto_detection()

    # Test modes
    results = {}
    if port and csrf:
        results["local"] = test_mode("local")
    results["direct"] = test_mode("direct")

    # Summary
    for _ in results.items():
        pass

    if not any(results.values()):
        pass


if __name__ == "__main__":
    main()
