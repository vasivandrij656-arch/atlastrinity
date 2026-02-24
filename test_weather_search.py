import logging

from src.mcp_server.duckduckgo_search_server import duckduckgo_search

logging.basicConfig(level=logging.INFO)

print("Testing DuckDuckGo search for weather in Kyiv...")
try:
    result = duckduckgo_search(query="погода в Києві зараз")
    print(f"Result: {result}")
except Exception as e:
    print(f"Error: {e}")
