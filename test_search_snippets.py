import os
import sys

# Add root to path
sys.path.insert(0, os.path.abspath("."))

import json

from src.mcp_server.duckduckgo_search_server import duckduckgo_search


def test_search():
    print("Testing DuckDuckGo search with snippets...")
    result = duckduckgo_search("погода в Києві")

    if "results" in result:
        for i, res in enumerate(result["results"]):
            print(f"\nResult {i + 1}:")
            print(f"Title: {res.get('title')}")
            print(f"URL: {res.get('url')}")
            print(f"Snippet: {res.get('snippet', 'N/A')}")
    else:
        print(f"Error: {result}")


if __name__ == "__main__":
    test_search()
