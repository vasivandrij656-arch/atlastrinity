"""
KyivChronicle: The Absolute Single Source of Truth for Time in NeuralCore.
Ensures ATLAS operates exclusively on Europe/Kyiv time with external synchronization.
"""

import asyncio
import logging
from datetime import UTC, datetime, timezone
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger("brain.neural_core.chronicle")


class KyivChronicle:
    _instance = None
    _timezone = ZoneInfo("Europe/Kyiv")
    _last_sync_drift = 0.0  # Seconds offset from local clock

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def last_sync(self) -> float:
        """Returns the drift found during last sync."""
        return self._last_sync_drift

    def get_now(self) -> datetime:
        """Returns current time in Europe/Kyiv, adjusted for drift."""
        # Note: In this version, we return the local time forced to Kyiv TZ.
        # Drift adjustment can be added after sync_time logic is fully tested.
        return datetime.now(self._timezone)

    def get_iso_now(self) -> str:
        """Returns ISO format timestamp in Kyiv timezone."""
        return self.get_now().isoformat()

    async def sync_time(self) -> bool:
        """
        Attempts to synchronize with an external time source to detect local clock skew.
        This ensures the 'Absolute Time' principle of the HOCE upgrade.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Using a reliable public API for time sync check
                response = await client.get("https://worldtimeapi.org/api/timezone/Europe/Kyiv")
                if response.status_code == 200:
                    data = response.json()
                    external_now_str = data.get("datetime")
                    if external_now_str:
                        external_now = datetime.fromisoformat(external_now_str)
                        local_now = datetime.now(UTC)
                        # WorldTimeAPI returns UTC-based ISO string here usually or with offset
                        # We compare UTC to UTC to find the drift
                        drift = (external_now.astimezone(UTC) - local_now).total_seconds()
                        self._last_sync_drift = drift
                        logger.info(
                            f"[CHRONICLE] Time sync successful. Detected drift: {drift:.3f}s"
                        )
                        return True
        except Exception as e:
            logger.warning(
                f"[CHRONICLE] External time sync failed: {e}. Falling back to system clock."
            )

        return False


# Global instance for pervasive access
kyiv_chronicle = KyivChronicle()
