import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.brain.monitoring import watchdog


async def test():
    await watchdog.reconcile_processes()
    watchdog.get_status()


if __name__ == "__main__":
    asyncio.run(test())
