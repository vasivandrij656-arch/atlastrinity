import asyncio
import os
import sys

# Add root to path
sys.path.insert(0, os.path.abspath("."))

import logging

from src.brain.core.orchestration.orchestrator import Trinity
from src.brain.monitoring.logger import logger


async def test_run():
    logging.basicConfig(level=logging.INFO)
    print("Initializing Trinity...")
    trinity = Trinity()
    await trinity.initialize()

    print("Running weather request...")
    # Using a slightly different query to avoid any cached results/cooldowns
    result = await trinity.run("Яка зараз погода в Києві? Потрібна детальна відповідь.")

    print(f"Result: {result}")

    # Wait a bit for background tasks (like voice)
    await asyncio.sleep(10)


if __name__ == "__main__":
    # Capture stderr to a file
    with open("test_trinity_stderr.log", "w") as stderr_log:
        sys.stderr = stderr_log
        try:
            asyncio.run(test_run())
        finally:
            # sys.stderr restoration is usually not needed here as the process ends,
            # but it's good practice.
            sys.stderr = sys.__stderr__
