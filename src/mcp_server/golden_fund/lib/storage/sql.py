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

        try:
            from ..schema_intelligence import SchemaIntelligence

            schema_intel = SchemaIntelligence()
        except ImportError:
            schema_intel = None
            logger.warning("SchemaIntelligence not available")

        try:
            with sqlite3.connect(self.db_path) as conn:
                # Check if table exists
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
                )
                existing_schema = cursor.fetchone()

                if existing_schema and if_exists == "append":
                    # Smart Evolution
                    if schema_intel:
                        alter_stmts = schema_intel.evolve_schema(df, table_name, existing_schema[0])
                        if alter_stmts:
                            logger.info(f"Evolving schema for {table_name}: {alter_stmts}")
                            # Execute ALTER statements (splitting by ; if multiple)
                            for stmt in alter_stmts.split(";"):
                                if stmt.strip():
                                    conn.execute(stmt)
                            # Save updated schema (persistence to file)
                            self._persist_schema_to_file(table_name, conn)

                    # Append
                    df.to_sql(table_name, conn, if_exists="append", index=False)

                elif not existing_schema or if_exists == "replace":
                    # Smart Creation
                    created_smart = False
                    if schema_intel:
                        create_stmt = schema_intel.generate_schema(
                            df, table_name, context=f"Dataset: {dataset_name}"
                        )
                        if create_stmt:
                            logger.info(f"Creating smart schema for {table_name}: {create_stmt}")
                            if if_exists == "replace":
                                conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                            conn.execute(create_stmt)
                            created_smart = True

                            # Append data to the smart table
                            df.to_sql(table_name, conn, if_exists="append", index=False)

                            # Save schema to file
                            self._persist_schema_to_file(table_name, conn)

                    if not created_smart:
                        # Fallback to pandas default
                        df.to_sql(table_name, conn, if_exists=if_exists, index=False)

                # Update metadata
                conn.execute(
                    """
                    INSERT INTO datasets_metadata (dataset_name, table_name, source_url, row_count)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(dataset_name) DO UPDATE SET
                        row_count = row_count + ?,
                        ingested_at = CURRENT_TIMESTAMP
                    """,
                    (dataset_name, table_name, source_url, len(df), len(df)),
                )

            return StorageResult(
                success=True,
                target=table_name,
                data={"table_name": table_name, "rows": len(df), "db_path": str(self.db_path)},
            )
        except Exception as e:
            logger.error(f"Failed to store dataset {dataset_name}: {e}")
            return StorageResult(success=False, target=table_name, error=str(e))

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
