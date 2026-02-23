"""
KyivChronicle: The Absolute Single Source of Truth for Time in NeuralCore.
Ensures ATLAS operates exclusively on Europe/Kyiv time with external synchronization.
"""

import logging
from datetime import UTC, datetime
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
        Uses multiple APIs with fallback for resilience.
        """
        apis = [
            (
                "https://timeapi.io/api/time/current/zone?timeZone=Europe/Kyiv",
                self._parse_timeapi_response,
            ),
            (
                "https://worldtimeapi.org/api/timezone/Europe/Kyiv",
                self._parse_worldtimeapi_response,
            ),
        ]

        for url, parser in apis:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(url)
                    if response.status_code == 200:
                        external_now = parser(response.json())
                        if external_now:
                            local_now = datetime.now(UTC)
                            drift = (external_now.astimezone(UTC) - local_now).total_seconds()
                            self._last_sync_drift = drift
                            logger.info(
                                f"[CHRONICLE] Time sync successful via {url.split('/')[2]}. "
                                f"Detected drift: {drift:.3f}s"
                            )
                            return True
            except Exception as e:
                logger.debug(
                    f"[CHRONICLE] Time sync failed for {url.split('/')[2]}: {type(e).__name__}: {e}"
                )

        logger.debug("[CHRONICLE] All time sync APIs unavailable. Using system clock.")
        return False

    @staticmethod
    def _parse_timeapi_response(data: dict) -> datetime | None:
        """Parse response from timeapi.io."""
        dt_str = data.get("dateTime")
        if dt_str:
            return datetime.fromisoformat(dt_str)
        return None

    @staticmethod
    def _parse_worldtimeapi_response(data: dict) -> datetime | None:
        """Parse response from worldtimeapi.org."""
        dt_str = data.get("datetime")
        if dt_str:
            return datetime.fromisoformat(dt_str)
        return None


# Global instance for pervasive access
kyiv_chronicle = KyivChronicle()
