import logging
import os
import sys
import time
from pathlib import Path

logger = logging.getLogger(Path(__file__).stem)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)

from langchain_core.messages import HumanMessage, SystemMessage

from providers.windsurf import WindsurfLLM


def run_test():
    logger.info(f"Using Python {sys.version}")

    # Configuration
    MODEL_NAME = "deepseek-v3"
    API_KEY = os.getenv("WINDSURF_API_KEY")

    if not API_KEY:
        logger.info("ERROR: WINDSURF_API_KEY environment variable not set")
        logger.info("Get your API key from the Windsurf dashboard and run:")
        logger.info("export WINDSURF_API_KEY='your_api_key_here'")
        # For CI/Discovery, we shouldn't exit with 1 if just imported.
        # But if run as script, exit.
        return False

    logger.info(f"Testing Windsurf Cascade flow with model: {MODEL_NAME}")
    logger.info("=" * 60)

    # Create LLM instance with cascade mode
    llm = WindsurfLLM(model_name=MODEL_NAME, api_key=API_KEY, direct_mode=False)

    # Prepare messages
    messages = [
        SystemMessage(content="Ти корисний асистент. Відповідай українською."),
        HumanMessage(content="Опиши, як працює Cascade pipeline у Windsurf провайдері?"),
    ]

    # Run test
    logger.info("Sending request through Cascade pipeline...")
    start_time = time.time()

    try:
        response = llm.invoke(messages)
        elapsed = time.time() - start_time

        logger.info(f"\nResponse received in {elapsed:.2f} seconds")
        logger.info("-" * 60)
        logger.info(response.content)
        logger.info("-" * 60)
        logger.info("✅ Test successful! Cascade pipeline is working with free model.")
        return True

    except Exception as e:
        logger.info(f"\n❌ Test failed: {e!s}")
        logger.info("Possible solutions:")
        logger.info("1. Ensure language_server_macos_arm is running")
        logger.info("2. Verify your API key has sufficient quota")
        logger.info("3. Check network/firewall settings")
        return False


if __name__ == "__main__":
    if not run_test():
        sys.exit(1)
