import logging
import sqlite3
from pathlib import Path
from typing import Any, Literal, cast

import pandas as pd

from .types import StorageResult

logger = logging.getLogger("golden_fund.storage.sql")


class SQLStorage:
    def __init__(self, db_path: Path | None = None):
        if db_path is None:
            # Default location: global config directory
            config_root = Path.home() / ".config" / "atlastrinity"
            self.db_dir = config_root / "data" / "golden_fund"
            self.db_path = self.db_dir / "golden.db"
        else:
            self.db_path = db_path
            self.db_dir = db_path.parent

        self.db_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize the database connection and ensure basic structure."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Enable WAL mode for better concurrency
                conn.execute("PRAGMA journal_mode=WAL;")
                # Create a metadata table to track datasets
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS datasets_metadata (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        dataset_name TEXT UNIQUE,
                        table_name TEXT,
                        source_url TEXT,
                        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        row_count INTEGER
                    )
                    """
                )
            logger.info(f"Initialized SQL storage at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")

    def store_dataset(
        self,
        df: pd.DataFrame,
        dataset_name: str,
        source_url: str = "",
        if_exists: Literal["fail", "replace", "append"] = "append",
    ) -> StorageResult:
        """
        Store a DataFrame as a table in SQLite with intelligent schema handling.
        """
        table_name = self._sanitize_table_name(dataset_name)
        # Add traceability metadata
        df["_gf_ingestion_id"] = dataset_name

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
                )
                existing_schema = cursor.fetchone()

                if existing_schema and if_exists == "append":
                    self._handle_append(df, table_name, existing_schema[0], conn)
                elif not existing_schema or if_exists == "replace":
                    self._handle_create_or_replace(df, table_name, dataset_name, if_exists, conn)

                self._update_metadata(conn, dataset_name, table_name, source_url, len(df))

            return StorageResult(
                success=True,
                target=table_name,
                data={"table_name": table_name, "rows": len(df), "db_path": str(self.db_path)},
            )
        except Exception as e:
            logger.error(f"Failed to store dataset {dataset_name}: {e}")
            return StorageResult(success=False, target=table_name, error=str(e))

    def _handle_append(
        self, df: pd.DataFrame, table_name: str, schema_sql: str, conn: sqlite3.Connection
    ):
        """Handle appending data with optional schema evolution."""
        schema_intel = self._get_schema_intelligence()
        if schema_intel:
            alter_stmts = schema_intel.evolve_schema(df, table_name, schema_sql)
            if alter_stmts:
                logger.info(f"Evolving schema for {table_name}: {alter_stmts}")
                for stmt in alter_stmts.split(";"):
                    if stmt.strip():
                        conn.execute(stmt)
                self._persist_schema_to_file(table_name, conn)

        df.to_sql(table_name, conn, if_exists="append", index=False)

    def _handle_create_or_replace(
        self,
        df: pd.DataFrame,
        table_name: str,
        dataset_name: str,
        if_exists: Literal["fail", "replace", "append"],
        conn: sqlite3.Connection,
    ):
        """Handle creating a new table or replacing an existing one."""
        schema_intel = self._get_schema_intelligence()
        created_smart = False

        if schema_intel:
            create_stmt = schema_intel.generate_schema(
                df, table_name, context=f"Dataset: {dataset_name}"
            )
            if create_stmt:
                logger.info(f"Creating smart schema for {table_name}")
                if if_exists == "replace":
                    conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                conn.execute(create_stmt)
                df.to_sql(table_name, conn, if_exists="append", index=False)
                self._persist_schema_to_file(table_name, conn)
                created_smart = True

        if not created_smart:
            df.to_sql(table_name, conn, if_exists=if_exists, index=False)

    def _get_schema_intelligence(self):
        """Lazy load SchemaIntelligence."""
        try:
            from ..schema_intelligence import SchemaIntelligence

            return SchemaIntelligence()
        except ImportError:
            logger.warning("SchemaIntelligence not available")
            return None

    def _update_metadata(
        self,
        conn: sqlite3.Connection,
        dataset_name: str,
        table_name: str,
        source_url: str,
        rows: int,
    ):
        """Update dataset metadata in sqlite."""
        conn.execute(
            """
            INSERT INTO datasets_metadata (dataset_name, table_name, source_url, row_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(dataset_name) DO UPDATE SET
                row_count = row_count + ?,
                ingested_at = CURRENT_TIMESTAMP
            """,
            (dataset_name, table_name, source_url, rows, rows),
        )

    def _persist_schema_to_file(self, table_name: str, conn: sqlite3.Connection):
        """Save the CREATE TABLE statement to a shared SQL file for reproducibility."""
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
            )
            res = cursor.fetchone()
            if res and res[0]:
                schema_sql = res[0] + ";\n"

                # Save to schema file in the same directory as the DB
                schema_file = self.db_dir / "golden_fund_schemas.sql"

                # Read existing to avoid dupes? Or just append?
                # For simplicity, appending. A smart system might parse/dedupe.
                with open(schema_file, "a", encoding="utf-8") as f:
                    f.write(f"\n-- Schema for {table_name} (Updated: {pd.Timestamp.now()})\n")
                    f.write(schema_sql)

                logger.info(f"Persisted schema for {table_name} to {schema_file}")
        except Exception as e:
            logger.warning(f"Failed to persist schema to file: {e}")

    def query(self, query: str, params: tuple = ()) -> StorageResult:
        """Execute a raw SQL query."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql_query(query, cast("Any", conn), params=list(params))
                return StorageResult(
                    success=True, target="query", data=df.to_dict(orient="records")
                )
        except Exception as e:
            return StorageResult(success=False, target="query", error=str(e))

    def _sanitize_table_name(self, name: str) -> str:
        """Sanitize string to be a valid SQL table name."""
        return "".join(c if c.isalnum() else "_" for c in name).lower()
