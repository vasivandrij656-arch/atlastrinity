import json
import logging
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .types import StorageResult

logger = logging.getLogger("golden_fund.storage.search")


class SearchStorage:
    """
    Search engine storage adapter (SQLite with FTS5).
    Provides full-text search capabilities without external dependencies.
    """

    def __init__(
        self,
        enabled: bool = True,
        index_name: str = "golden_fund_index",
        # Kept for compatibility but unused in SQLite mode
        hosts: list[str] | None = None,
    ):
        self.enabled = enabled
        self.index_name = index_name

        # SQLite DB path (per index)
        # Using ~/.config/atlastrinity/data/search/
        self.db_path = (
            Path.home() / ".config" / "atlastrinity" / "data" / "search" / f"{index_name}.db"
        )

        if enabled:
            try:
                self._init_db()
                logger.info(f"SearchStorage (SQLite/FTS5) initialized: {self.db_path}")
            except Exception as e:
                logger.error(f"Failed to init SQLite FTS5: {e}")
                self.enabled = False
        else:
            logger.info("SearchStorage disabled")

    def _init_db(self):
        """Initialize SQLite database with FTS5 table."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            # Enable FTS5 extension if it's not builtin (usually it is in Python 3.12+)
            # Create FTS5 virtual table
            # We store the raw JSON source in a separate column or in the FTS table (if needed for result)
            # Here we follow a simple schema: id, title, content, description, source_json

            conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {self.index_name} USING fts5(
                    id, 
                    title, 
                    content, 
                    description, 
                    source_json UNINDEXED
                )
            """)
            conn.commit()

    def index_documents(self, data: dict[str, Any] | list[dict[str, Any]]) -> StorageResult:
        if not self.enabled:
            return StorageResult(False, "search", error="SearchStorage is disabled")

        try:
            if not data:
                return StorageResult(False, "search", error="No data provided")

            if isinstance(data, dict):
                data = [data]

            doc_count = 0
            with sqlite3.connect(self.db_path) as conn:
                for item in data:
                    doc_id = item.get("id", str(uuid.uuid4()))
                    title = item.get("title", "")
                    content = item.get("content", "")
                    description = item.get("description", "")
                    source_json = json.dumps(item, ensure_ascii=False)

                    conn.execute(
                        f"INSERT OR REPLACE INTO {self.index_name} (id, title, content, description, source_json) VALUES (?, ?, ?, ?, ?)",
                        (doc_id, title, content, description, source_json),
                    )
                    doc_count += 1
                conn.commit()

            logger.info(f"Indexed {doc_count} docs into '{self.index_name}' (SQLite)")

            return StorageResult(
                True, "search", data={"index": self.index_name, "indexed_count": doc_count}
            )
        except Exception as e:
            msg = f"Indexing failed: {e}"
            logger.error(msg)
            return StorageResult(False, "search", error=msg)

    def search(self, query: str, limit: int = 10) -> StorageResult:
        if not self.enabled:
            return StorageResult(False, "search", error="SearchStorage is disabled")

        try:
            logger.info(f"Searching '{self.index_name}' for: {query}")

            results = []
            total = 0

            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row

                # Basic FTS5 sanitization: remove or escape special chars
                # For simplicity, we'll strip most punct that FTS5 interprets specially
                sanitized_query = re.sub(r"[^a-zA-Z0-9\sа-яА-ЯіІєЄїЇґҐ]", " ", query)
                sanitized_query = " ".join(sanitized_query.split())  # normalize spaces

                if not sanitized_query:
                    return StorageResult(True, "search", data={"results": [], "total": 0})

                # Strategy 1: Direct match
                cursor = conn.execute(
                    f"SELECT id, source_json, rank FROM {self.index_name} WHERE {self.index_name} MATCH ? ORDER BY rank LIMIT ?",
                    (sanitized_query, limit),
                )
                rows = cursor.fetchall()

                # Strategy 2: Wildcard match if no rows found
                if not rows and len(sanitized_query) > 2:
                    wildcard_query = " ".join([f"{term}*" for term in sanitized_query.split()])
                    logger.info(f"No direct matches, trying wildcard: {wildcard_query}")
                    cursor = conn.execute(
                        f"SELECT id, source_json, rank FROM {self.index_name} WHERE {self.index_name} MATCH ? ORDER BY rank LIMIT ?",
                        (wildcard_query, limit),
                    )
                    rows = cursor.fetchall()

                for row in rows:
                    results.append(
                        {
                            "id": row["id"],
                            "score": row["rank"],
                            "source": json.loads(row["source_json"]),
                        }
                    )

                total = len(results)

            return StorageResult(True, "search", data={"results": results, "total": total})

        except Exception as e:
            return StorageResult(False, "search", error=f"Search failed: {e}")
