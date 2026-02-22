"""
EnvironmentObserver: The Universal Awareness Module of NeuralCore.
Monitors filesystem, keychain, and system services to feed local context into the CognitiveGraph.
"""

import asyncio
import logging
import os
from pathlib import Path

from src.brain.config import CONFIG_ROOT, PROJECT_ROOT
from src.brain.neural_core.memory.graph import cognitive_graph

logger = logging.getLogger("brain.neural_core.observer")


class EnvironmentObserver:
    def __init__(self):
        self._running = False

    async def observe_system(self):
        """Perform a holistic scan of the ATLAS environment."""
        logger.info("[OBSERVER] Scanning system environment...")

        # 1. Spatial Awareness (Filesystem)
        try:
            config_files = list(Path(CONFIG_ROOT).glob("**/*.yaml"))
            logger.info(
                f"[OBSERVER] Detected {len(config_files)} configuration files in CONFIG_ROOT."
            )

            # Record knowledge of home in graph
            await cognitive_graph.add_node(
                "spatial_atlas_home",
                "environment",
                "ATLAS Configuration Home",
                {"path": str(CONFIG_ROOT), "discovery_type": "filesystem_scan"},
            )
        except Exception as e:
            logger.error(f"[OBSERVER] Filesystem scan failed: {e}")

        # 2. Security Awareness (Stub for Keychain integration)
        # Note: In a real implementation with keychain access, this would safely
        # verify the presence of critical tokens without reading secrets.
        await cognitive_graph.add_node(
            "security_perimeter",
            "environment",
            "Security Infrastructure",
            {"status": "monitored", "components": ["Keychain", "EnvVars"]},
        )

        logger.info("[OBSERVER] System observation cycle complete.")

    def start_background_scanning(self, interval_hours: int = 12):
        """Starts the background observation loop."""
        if self._running:
            return

        self._running = True

        async def loop():
            while self._running:
                await self.observe_system()
                await asyncio.sleep(interval_hours * 3600)

        asyncio.create_task(loop())
        logger.info(f"[OBSERVER] Background scanning started (interval: {interval_hours}h).")


# Global instance
environment_observer = EnvironmentObserver()
