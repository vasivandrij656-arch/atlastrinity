import asyncio
import pandas as pd
from pathlib import Path
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from src.mcp_server.golden_fund.tools.ingest import ingest_dataset

async def test_chunked_ingestion():
    # 1. Create a sample CSV with 10 rows
    test_file = Path("/tmp/large_test_dataset.csv")
    df = pd.DataFrame({
        "id": range(10),
        "data": [f"Row {i}" for i in range(10)],
        "search_term": ["Наугольник" if i == 7 else "Empty" for i in range(10)]
    })
    df.to_csv(test_file, index=False)
    
    url = f"file://{test_file}"
    print(f"Test file created: {test_file}")
    
    # 2. Ingest first chunk (rows 0-5)
    print("\n--- Ingesting Chunk 1 (offset=0, limit=5) ---")
    res1 = await ingest_dataset(url, type="csv", offset=0, limit=5)
    print(f"Result 1:\n{res1}\n")
    
    if "[CONTINUATION REQUIRED]" in res1 and "offset=5" in res1:
        print("✅ SUCCESS: Chunk 1 triggered continuation protocol correctly.")
    else:
        print("❌ FAILURE: Chunk 1 did not trigger continuation correctly.")
        
    # 3. Ingest second chunk (rows 5-10)
    print("\n--- Ingesting Chunk 2 (offset=5, limit=5) ---")
    res2 = await ingest_dataset(url, type="csv", offset=5, limit=5)
    print(f"Result 2:\n{res2}\n")
    
    if "Processing chunk: records 5 to 10 of 10" in res2:
        print("✅ SUCCESS: Chunk 2 processed correctly.")
    else:
        print("❌ FAILURE: Chunk 2 range incorrect.")
        
    if "Stored in SQL" not in res2:
         print("✅ SUCCESS: SQL storage skipped for continuation chunk.")
    else:
         print("❌ FAILURE: SQL storage was NOT skipped for continuation chunk.")

    # Cleanup
    if test_file.exists():
        test_file.unlink()

if __name__ == "__main__":
    asyncio.run(test_chunked_ingestion())
