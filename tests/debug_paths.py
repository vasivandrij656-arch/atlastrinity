from pathlib import Path
import sys
import os

print(f"__file__: {__file__}")
PROJECT_ROOT = Path(__file__).parent.parent
print(f"PROJECT_ROOT: {PROJECT_ROOT}")
CONFIG_DIR = PROJECT_ROOT / "config"
print(f"CONFIG_DIR: {CONFIG_DIR}")
MCP_SERVERS = CONFIG_DIR / "mcp_servers.json.template"
print(f"MCP_SERVERS: {MCP_SERVERS}")
print(f"Exists: {MCP_SERVERS.exists()}")
