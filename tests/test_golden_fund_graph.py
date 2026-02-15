import asyncio
import logging
import sys
from pathlib import Path

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

# Adjust logging
logging.basicConfig(level=logging.INFO)

from src.mcp_server.golden_fund.lib.storage.vector import VectorStorage
from src.mcp_server.golden_fund.tools.ingest import ingest_dataset


async def test_graph_extraction():
    print("--- Testing Graph Extraction ---")

    # 1. Ingest sample text with entities
    text = """
    The Atlas Trinity project, led by Oleg Mykolayovych, is a sophisticated AI system.
    It uses the Golden Fund for memory storage and Vibe for coding.
    The HQ is located in Kyiv.
    """

    # Simulate a web page content (we can just pass text directly if we modify ingest.py to accept raw text,
    # but ingest_dataset expects a URL.
    # We can use a data: url or just a dummy url and mock the scraper?
    # Or rely on ingest_dataset handling plain text if I pass it?
    # ingest_dataset takes URL. Scraper handles URL.
    # Let's mock the scraper or just use a dummy file.

    # Actually, simpler: Test EntityExtractor directly first.
    from src.mcp_server.golden_fund.lib.entity_extractor import EntityExtractor

    extractor = EntityExtractor()
    if not extractor.llm:
        print("Skipping test: CopilotLLM not available")
        return

    result = extractor.extract(text, source_url="test_script")
    print(f"Extraction Result: {result}")

    assert len(result.get("entities", [])) > 0, "No entities extracted"

    # Check for specific entities
    names = [e["name"] for e in result["entities"]]
    print(f"Entities found: {names}")
    assert "Atlas Trinity" in names or "Atlas Trinity project" in names
    assert "Oleg Mykolayovych" in names

    # 2. Test Integration with VectorStorage
    vector_storage = VectorStorage()
    if vector_storage.enabled:
        # Manually store to verify
        from src.mcp_server.golden_fund.tools.ingest import _perform_entity_storage

        msg = _perform_entity_storage(text, "test_url", "test_run", extractor, vector_storage)
        print(f"Storage Msg: {msg}")

        # Verify via search
        search_res = vector_storage.search("Oleg", where={"type": "entity"})
        print(f"Search Result: {search_res}")

        found = False
        if search_res.success and search_res.data:
            for item in search_res.data.get("results", []):
                if item["metadata"].get("type") == "entity":
                    found = True
                    break

        if found:
            print("✅ Entity stored and retrieved successfully from ChromaDB")
        else:
            print("❌ Entity not found in ChromaDB after storage")


if __name__ == "__main__":
    asyncio.run(test_graph_extraction())
