import os
import sys
from pathlib import Path

# Add project root and src to sys.path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))

try:
    from langchain_core.messages import HumanMessage

    from providers.windsurf import WindsurfLLM
except ImportError as e:
    print(f"Error importing: {e}")
    sys.exit(1)


def test_provider():
    print("🚀 Testing WindsurfLLM provider directly...")

    try:
        # Force local mode to test the same thing as the bridge
        os.environ["WINDSURF_MODE"] = "local"

        provider = WindsurfLLM(model_name="swe-1.5")
        print(f"Mode: {provider._mode}")
        print(f"LS Port: {provider.ls_port}")

        if not provider.ls_port:
            print("❌ LS not detected. Make sure Windsurf is running.")
            return

        messages = [HumanMessage(content="Hello, answer with 'OK'.")]
        response = provider.invoke(messages)
        print(f"✅ Response: {response.content}")

    except Exception as e:
        print(f"❌ Provider failed: {e}")


if __name__ == "__main__":
    test_provider()
