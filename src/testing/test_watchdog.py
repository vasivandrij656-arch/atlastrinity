import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from unittest.mock import MagicMock


async def test():
    # 1. Ensure we have the real watchdog behavior
    from src.brain.monitoring.watchdog import ProcessWatchdog

    test_watchdog = ProcessWatchdog()

    # 2. Mock monitoring system localized to this test call
    test_watchdog.mon = MagicMock()
    test_watchdog.mon.log_for_grafana = MagicMock()  # It's not async

    # 3. Reconcile (this calls psutil)
    await test_watchdog.reconcile_processes()
    status = test_watchdog.get_status()
    assert "process_count" in status


if __name__ == "__main__":
    asyncio.run(test())
