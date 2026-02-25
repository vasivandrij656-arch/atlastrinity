import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from src.mcp_server.golden_fund.lib.connectors.opendatabot_connector import OpendatabotConnector
from src.mcp_server.golden_fund.tools.ingest import ingest_dataset


async def test_high_impact_ingestion():
    print("--- Opendatabot High-Impact Simulation Test ---")
    connector = OpendatabotConnector()  # Will use simulation mode if no key

    query = "забудовник"
    companies = connector.search_company(query)
    print(f"Discovered {len(companies)} companies in simulation.")

    # Ingest the first company as a high-impact 'structured' sample
    # We pass the dict directly to a mock-like ingest if we had an 'ingest_dict' tool,
    # but for now we'll simulate by saving to a temp file and ingesting that.

    import json
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as tf:
        json.dump(companies, tf, ensure_ascii=False, indent=2)
        temp_path = tf.name

    print(f"Created temporary simulation file: {temp_path}")

    try:
        # Ingest the simulation file
        result = await ingest_dataset(url=f"file://{temp_path}", type="json")
        print(f"Ingestion Result: {result}")
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


if __name__ == "__main__":
    asyncio.run(test_high_impact_ingestion())
