import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from src.mcp_server.golden_fund.lib.storage.search import SearchStorage
from src.mcp_server.golden_fund.lib.storage.sql import SQLStorage
from src.mcp_server.golden_fund.lib.storage.vector import VectorStorage


async def run_diagnostic():
    print("--- Searching SQLite SQL Fallback ---")
    sql = SQLStorage()
    # Try a broad query that should match something if data exists
    # Based on previous results, we have court_cases
    query = "court"
    res = sql.query("SELECT * FROM datasets_metadata WHERE dataset_name LIKE ?", (f"%{query}%",))
    print(
        f"SQL Metadata Match for '{query}': {res.success}, Count: {len(res.data) if res.data else 0}"
    )

    print("\n--- Searching Keyword Index (FTS5) ---")
    search = SearchStorage()
    search_res = search.search(query)
    print(
        f"Keyword Search Match for '{query}': {search_res.success}, Results: {len(search_res.data.get('results', [])) if search_res.data else 0}"
    )

    print("\n--- Searching Vector Index (Chroma) ---")
    vector = VectorStorage()
    if vector.enabled:
        vec_res = vector.search(query)
        print(
            f"Vector Search Match for '{query}': {vec_res.success}, Results: {len(vec_res.data.get('results', [])) if vec_res.data else 0}"
        )
    else:
        print("Vector Storage is DISABLED")


if __name__ == "__main__":
    asyncio.run(run_diagnostic())
