"""Token Refresher — Background service for automatic token renewal.

Monitors the vault for expiring tokens and automatically
refreshes them via the corresponding OAuth2 flow.

Runs as an asyncio background task.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger("brain.auth.refresher")


class TokenRefresher:
    """Automatic OAuth2 token renewal.

    Usage:
        refresher = TokenRefresher(vault=vault, oauth_engine=engine)
        await refresher.start()  # Starts background task

        # Or one-time refresh
        await refresher.refresh_expiring(threshold=3600)
    """

    def __init__(
        self,
        vault: Any,
        oauth_engine: Any,
        check_interval: float = 300,  # Check every 5 minutes
        refresh_threshold: float = 600,  # Refresh if TTL < 10 minutes
    ) -> None:
        self._vault = vault
        self._oauth_engine = oauth_engine
        self._check_interval = check_interval
        self._refresh_threshold = refresh_threshold
        self._running = False
        self._task: asyncio.Task | None = None
        self._stats = {
            "refreshed": 0,
            "failed": 0,
            "last_check": 0.0,
        }

    async def start(self) -> None:
        """Starts the background refresh loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._refresh_loop())
        logger.info("🔄 Token refresher started (interval=%ds)", self._check_interval)

    async def stop(self) -> None:
        """Stops the refresh loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("⏹️ Token refresher stopped")

    async def _refresh_loop(self) -> None:
        """Main loop."""
        while self._running:
            try:
                await self.refresh_expiring(self._refresh_threshold)
                self._stats["last_check"] = time.time()
            except Exception as e:
                logger.error("❌ Refresh loop error: %s", e)

            await asyncio.sleep(self._check_interval)

    async def refresh_expiring(self, threshold: float | None = None) -> dict[str, bool]:
        """Refreshes all tokens that expire soon.

        Returns:
            {service_id: success} for each refreshed service
        """
        threshold = threshold or self._refresh_threshold
        expiring = self._vault.get_expiring_soon(threshold)
        results: dict[str, bool] = {}

        for service in expiring:
            cred = self._vault.get(service, allow_expired=True)
            if not cred:
                continue

            if not cred.auto_refresh:
                continue

            if cred.credential_type != "oauth2":
                continue

            refresh_token = cred.data.get("refresh_token")
            if not refresh_token:
                logger.warning("⚠️ No refresh_token for: %s", service)
                results[service] = False
                continue

            try:
                new_tokens = await self._oauth_engine.refresh_token(service, refresh_token)
                # Update vault
                self._vault.store(
                    service=service,
                    credential_type="oauth2",
                    data=new_tokens.to_dict(),
                    expires_in=new_tokens.expires_in,
                    auto_refresh=True,
                    refresh_url=cred.refresh_url,
                    metadata=cred.metadata,
                )
                results[service] = True
                self._stats["refreshed"] += 1
                logger.info("✅ Token refreshed: %s (TTL: %ss)", service, new_tokens.expires_in)
            except Exception as e:
                results[service] = False
                self._stats["failed"] += 1
                logger.error("❌ Refresh failed for %s: %s", service, e)

        return results

    async def force_refresh(self, service: str) -> bool:
        """Force refresh a specific token."""
        cred = self._vault.get(service, allow_expired=True)
        if not cred:
            return False

        refresh_token = cred.data.get("refresh_token")
        if not refresh_token:
            return False

        try:
            new_tokens = await self._oauth_engine.refresh_token(service, refresh_token)
            self._vault.store(
                service=service,
                credential_type="oauth2",
                data=new_tokens.to_dict(),
                expires_in=new_tokens.expires_in,
                auto_refresh=cred.auto_refresh,
                refresh_url=cred.refresh_url,
                metadata=cred.metadata,
            )
            return True
        except Exception as e:
            logger.error("Force refresh failed for %s: %s", service, e)
            return False

    @property
    def stats(self) -> dict[str, Any]:
        return self._stats.copy()

    @property
    def is_running(self) -> bool:
        return self._running
