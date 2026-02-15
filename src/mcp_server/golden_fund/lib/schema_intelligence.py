"""
Schema Intelligence Module for Golden Fund
Uses LLM to generate and evolve SQL schemas intelligently.
"""

import logging
import sys
from pathlib import Path
from typing import cast

import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage

# Ensure project root is in path to import providers
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

try:
    from src.providers.copilot import CopilotLLM
except ImportError:
    # Fallback/Mock for environments where src.providers is not available
    CopilotLLM = None

logger = logging.getLogger("golden_fund.schema_intelligence")


class SchemaIntelligence:
    def __init__(self):
        self.llm = None
        if CopilotLLM:
            try:
                self.llm = CopilotLLM()
                logger.info("SchemaIntelligence initialized with CopilotLLM")
            except Exception as e:
                logger.warning(f"Failed to initialize CopilotLLM: {e}")
        else:
            logger.warning("CopilotLLM not available. Schema Intelligence will be disabled.")

    def generate_schema(self, df: pd.DataFrame, table_name: str, context: str = "") -> str | None:
        """
        Generate a CREATE TABLE statement for the given DataFrame.
        """
        if not self.llm:
            return None

        try:
            # Prepare sample data
            sample = df.head(5).to_string(index=False)
            dtypes = df.dtypes.to_string()

            prompt = (
                f"Generate a robust SQLite CREATE TABLE statement for table '{table_name}'.\n"
                f"Context: {context}\n\n"
                f"Data Types:\n{dtypes}\n\n"
                f"Sample Data:\n{sample}\n\n"
                "Requirements:\n"
                "1. Use appropriate SQLite data types (TEXT, INTEGER, REAL, BLOB).\n"
                "2. Add PRIMARY KEY if an 'id' column exists, otherwise suggest one.\n"
                "3. Add meaningful column constraints (NOT NULL) where appropriate based on sample.\n"
                "4. Return ONLY the SQL statement, no markdown formatting or explanations."
            )

            response = self.llm.invoke(
                [
                    SystemMessage(content="You are an expert SQL Database Administrator."),
                    HumanMessage(content=prompt),
                ]
            )

            sql = cast("str", response.content).strip()
            # Cleanup markdown code blocks if present
            sql = sql.removeprefix("```sql")
            sql = sql.removeprefix("```")
            sql = sql.removesuffix("```")

            return sql.strip()

        except Exception as e:
            logger.error(f"Failed to generate schema: {e}")
            return None

    def evolve_schema(self, df: pd.DataFrame, table_name: str, current_schema: str) -> str | None:
        """
        Generate ALTER TABLE statements to evolve the schema for new data.
        """
        if not self.llm:
            return None

        try:
            # Check for new columns
            # This logic could be done purely in python, but LLM can help with typing
            # For now, let's use python to find diff, LLM to generate SQL

            # Simple python check for missing columns
            # But the requirement is "intelligent append".
            # Let's ask LLM to compare sample data with current schema string.

            sample = df.head(5).to_string(index=False)

            prompt = (
                f"I need to insert this data into existing table '{table_name}'.\n"
                f"Current Schema:\n{current_schema}\n\n"
                f"New Data Sample:\n{sample}\n\n"
                "Determine if the schema needs evolution (e.g. new columns).\n"
                "If strictly compatible, return 'COMPATIBLE'.\n"
                "If new columns are needed, return the SQLite ALTER TABLE statements (one per line).\n"
                "Return ONLY the SQL or 'COMPATIBLE'."
            )

            response = self.llm.invoke(
                [
                    SystemMessage(content="You are an expert SQL Database Administrator."),
                    HumanMessage(content=prompt),
                ]
            )

            result = cast("str", response.content).strip()
            if "COMPATIBLE" in result.upper():
                return None

            # Cleanup
            cleaned = result.replace("```sql", "").replace("```", "").strip()
            return cleaned

        except Exception as e:
            logger.error(f"Failed to evolve schema: {e}")
            return None
