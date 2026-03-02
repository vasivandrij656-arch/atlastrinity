"""
CognitiveGraph: The Relational and Causal Memory of NeuralCore.
Implements a graph-like structure on top of SQLite to track causality and experience.
"""

import json
import logging
from pathlib import Path
from typing import Any

import aiosqlite

from src.brain.neural_core.chronicle import kyiv_chronicle

logger = logging.getLogger("brain.neural_core.graph")


class CognitiveGraph:
    def __init__(self, db_path: str | None = None):
        if db_path is None:
            from src.brain.config import CONFIG_ROOT

            db_path = str(CONFIG_ROOT / "memory" / "cognitive_graph.db")

        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self):
        """Initializes the SQLite schema for the cognitive graph."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    label TEXT,
                    properties TEXT, -- JSON
                    kyiv_timestamp TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    weight REAL DEFAULT 1.0,
                    resonance REAL DEFAULT 0.0, -- Short-term activation
                    properties TEXT, -- JSON
                    kyiv_timestamp TEXT NOT NULL,
                    FOREIGN KEY(source_id) REFERENCES nodes(id),
                    FOREIGN KEY(target_id) REFERENCES nodes(id)
                );

                CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
                CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);
            """)
            await db.commit()
            logger.info(f"[COGNITIVE GRAPH] Initialized at {self.db_path}")

    async def add_node(self, node_id: str, node_type: str, label: str, properties: dict[str, Any]):
        """Adds a node to the cognitive graph."""
        timestamp = kyiv_chronicle.get_iso_now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO nodes (id, type, label, properties, kyiv_timestamp) VALUES (?, ?, ?, ?, ?)",
                (node_id, node_type, label, json.dumps(properties), timestamp),
            )
            await db.commit()

    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Retrieves a node by its ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
            row = await cursor.fetchone()
            if row:
                node = dict(row)
                node["properties"] = json.loads(node["properties"])
                return node
        return None

    async def search_nodes(
        self, node_type: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Searches for nodes by type, ordered by most recent."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if node_type:
                cursor = await db.execute(
                    "SELECT * FROM nodes WHERE type = ? ORDER BY kyiv_timestamp DESC LIMIT ?",
                    (node_type, limit),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM nodes ORDER BY kyiv_timestamp DESC LIMIT ?", (limit,)
                )
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                node = dict(row)
                node["properties"] = json.loads(node["properties"])
                results.append(node)
            return results

    async def get_recent_lessons(self, limit: int = 5) -> list[dict[str, Any]]:
        """Fast retrieval of recent neural lessons for agent context."""
        return await self.search_nodes(node_type="lesson", limit=limit)

    async def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        properties: dict[str, Any] | None = None,
    ):
        """Adds a directed edge between two nodes."""
        timestamp = kyiv_chronicle.get_iso_now()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO edges (source_id, target_id, relation, properties, kyiv_timestamp) VALUES (?, ?, ?, ?, ?)",
                (source_id, target_id, relation, json.dumps(properties or {}), timestamp),
            )
            await db.commit()

    async def get_causality_chain(self, node_id: str, depth: int = 3) -> list[dict[str, Any]]:
        """
        Naive implementation of causality retrieval (tracing edges).
        Useful for the ReflexPipe to understand 'Why did I do this?'.
        """
        # Complex recursive CTE or simple iterative approach
        # For now, let's just fetch direct neighbors
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM edges WHERE source_id = ? OR target_id = ?", (node_id, node_id)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def strengthen_synapse(
        self, source_id: str, target_id: str, amount: float = 0.1, multiplier: float = 1.0
    ):
        """
        Hebbian Learning: Strengthens the weight of an edge between two nodes.
        If the edge doesn't exist, it creates a new weak one.
        The strengthening is scaled by an external multiplier (e.g., from NeuroModulator).
        """
        effective_amount = amount * multiplier
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id, weight FROM edges WHERE source_id = ? AND target_id = ?",
                (source_id, target_id),
            )
            row = await cursor.fetchone()
            if row:
                edge_id, current_weight = row
                new_weight = min(2.0, current_weight + effective_amount)
                await db.execute(
                    "UPDATE edges SET weight = ?, resonance = resonance + ? WHERE id = ?",
                    (new_weight, effective_amount * 2, edge_id),
                )
            else:
                # Create a new potential synapse
                await self.add_edge(
                    source_id, target_id, "hebbian_link", {"weight": 0.1 * multiplier}
                )
            await db.commit()
            logger.debug(
                f"[COGNITIVE GRAPH] Synapse strengthened: {source_id} -> {target_id} (Amount: {effective_amount:.3f})"
            )

    async def decay_synapses(self, decay_factor: float = 0.05):
        """
        Synaptic Pruning: Gradually reduces weight and resonance of all edges.
        Edges with weight < 0.1 are eventually pruned.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE edges SET weight = weight * (1.0 - ?), resonance = resonance * 0.5",
                (decay_factor,),
            )
            # Prune weak links
            await db.execute("DELETE FROM edges WHERE weight < 0.1 AND relation = 'hebbian_link'")
            await db.commit()


# Global instance
cognitive_graph = CognitiveGraph()
