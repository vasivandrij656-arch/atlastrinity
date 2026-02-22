"""
NeuralCore: The Autonomous Cognitive Heart of ATLAS.
Unifies all cognitive sub-systems into a single sentient hub.
"""

import logging
from typing import Any, Optional

from src.brain.neural_core.chronicle import kyiv_chronicle
from src.brain.neural_core.evolution.engine import evolution_engine
from src.brain.neural_core.memory.graph import cognitive_graph
from src.brain.neural_core.reflection.pipeline import reflex_pipe

logger = logging.getLogger("brain.neural_core")


class NeuralCore:
    def __init__(self):
        self.chronicle = kyiv_chronicle
        self.graph = cognitive_graph
        self.reflex = reflex_pipe
        self.evolution = evolution_engine
        self._initialized = False

    async def initialize(self):
        """Initializes all cognitive sub-systems."""
        if self._initialized:
            return

        logger.info("[NEURAL CORE] Initializing the Living Brain...")

        # 1. Initialize Graph
        await self.graph.initialize()

        # 2. Initial Time Sync
        await self.chronicle.sync_time()

        # 3. Start Evolution Loop (6-hour cycle)
        self.evolution.start_background_loop(interval_hours=6)

        self._initialized = True
        logger.info("[NEURAL CORE] Awakening complete. Cognitive systems operational.")

    def get_time(self) -> str:
        """Absolute Europe/Kyiv time."""
        return self.chronicle.get_iso_now()


# Global instance
neural_core = NeuralCore()
