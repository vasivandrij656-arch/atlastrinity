#!/usr/bin/env python3
"""
Regenerate MCP Data Files (Catalog & Schemas)

1. Dumps live tools from all enabled MCP servers to /tmp/mcp_tools_live_full.json
2. Regenerates src/brain/data/mcp_catalog.json using descriptions from config
   and tool lists from live dump.
3. Runs schema_sync.py to regenerate src/brain/data/tool_schemas.json
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Valid environments for subprocesses
ENV = os.environ.copy()
ENV["PROJECT_ROOT"] = str(PROJECT_ROOT)
ENV["PYTHONPATH"] = str(PROJECT_ROOT)


async def read_jsonrpc(stdout, timeout=30):
    """Read a single JSON-RPC message (newline-delimited)."""
    try:
        if not stdout:
            return None
        # Read line by line
        line = await asyncio.wait_for(stdout.readline(), timeout=timeout)
        if not line:
            return None
        return json.loads(line.decode("utf-8").strip())
    except Exception:
        return None


async def send_and_recv(proc, method, params, msg_id, timeout=30):
    """Send JSON-RPC request and read response."""
    if not proc.stdin:
        return None
    msg = json.dumps({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
    proc.stdin.write((msg + "\n").encode())
    await proc.stdin.drain()
    
    # Read response (might get notifications first, loop until response with id)
    start_time = asyncio.get_event_loop().time()
    while True:
        if asyncio.get_event_loop().time() - start_time > timeout:
            return None
            
        resp = await read_jsonrpc(proc.stdout, timeout=timeout)
        if not resp:
            return None
        
        if resp.get("id") == msg_id:
            return resp
        # Ignore notifications or other messages


async def get_server_tools(name: str, cfg: dict) -> dict[str, Any] | None:
    """Launch server and get list of tools."""
    cmd = (
        cfg.get("command", "")
        .replace("${PROJECT_ROOT}", str(PROJECT_ROOT))
        .replace("${HOME}", os.environ.get("HOME", ""))
    )
    args = [
        a.replace("${PROJECT_ROOT}", str(PROJECT_ROOT)).replace(
            "${HOME}", os.environ.get("HOME", "")
        )
        for a in cfg.get("args", [])
    ]

    srv_env = ENV.copy()
    for k, v in cfg.get("env", {}).items():
        v = v.replace("${PROJECT_ROOT}", str(PROJECT_ROOT)).replace(
            "${HOME}", os.environ.get("HOME", "")
        )
        if v.startswith("${") and v.endswith("}"):
            v_name = v[2:-1]
            v = os.environ.get(v_name, "")
        srv_env[k] = v

    print(f"[{name}] Starting...", file=sys.stderr)
    
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=srv_env,
            cwd=PROJECT_ROOT,
        )

        # Initialize
        init = await send_and_recv(
            proc,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp-regenerate", "version": "1.0"},
            },
            1,
            timeout=10,
        )

        if not init:
            print(f"[{name}] Failed to initialize", file=sys.stderr)
            return None

        # Send initialized
        if proc.stdin:
            proc.stdin.write(
                (json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode()
            )
            await proc.stdin.drain()

        # List tools
        tools_resp = await send_and_recv(proc, "tools/list", {}, 2, timeout=15)
        
        # Clean shutdown
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=2)
        except Exception:
            try:
                proc.kill()
            except:
                pass

        if tools_resp and "result" in tools_resp:
            tools = tools_resp["result"].get("tools", [])
            print(f"[{name}] Found {len(tools)} tools", file=sys.stderr)
            return {"status": "ok", "tools": tools}
        
        return {"status": "error", "error": "No tools returned"}

    except Exception as e:
        print(f"[{name}] Error: {e}", file=sys.stderr)
        if proc:
            try:
                proc.kill()
            except:
                pass
        return {"status": "error", "error": str(e)}


async def main():
    # 1. Load Configuration
    config_path = PROJECT_ROOT / "config" / "mcp_servers.json.template"
    if not config_path.exists():
        print(f"Config not found at {config_path}")
        return 1
        
    config_data = json.loads(config_path.read_text())
    servers = config_data.get("mcpServers", {})
    
    # 2. Dump Live Tools
    live_data = {}
    
    tasks = []
    server_names = []
    
    for name, cfg in servers.items():
        if name.startswith("_") or cfg.get("disabled") or cfg.get("transport") == "internal":
            continue
            
        # Skip servers that might be problematic or heavy if not needed
        # but for regeneration we usually want everything possible.
        
        server_names.append(name)
        tasks.append(get_server_tools(name, cfg))
    
    print(f"Querying {len(tasks)} servers...", file=sys.stderr)
    results = await asyncio.gather(*tasks)
    
    for name, result in zip(server_names, results):
        if result:
            live_data[name] = result
            
    # Save live dump
    dump_path = Path("/tmp/mcp_tools_live_full.json")
    dump_path.write_text(json.dumps(live_data, indent=2))
    print(f"Live tools dumped to {dump_path}", file=sys.stderr)
    
    # 3. Regenerate Catalog
    catalog = {}
    
    for name, cfg in servers.items():
        # Include even disabled servers in catalog if they have descriptions
        if name.startswith("_"):
            continue
            
        info = {
            "description": cfg.get("description", ""),
            "tier": cfg.get("tier", 4),
            "agents": cfg.get("agents", []),
        }
        
        if "note" in cfg:
            info["priority_note"] = cfg["note"]
            
        # Add key_tools if available from live dump
        if name in live_data and live_data[name].get("status") == "ok":
            tools = live_data[name].get("tools", [])
            # Heuristic: Pick first 5 tools or specific interesting ones
            tool_names = [t["name"] for t in tools]
            # Simple heuristic: list up to 10 tools
            info["key_tools"] = tool_names[:10]
            info["tool_count"] = len(tool_names)
        else:
            # Fallback for offline/disabled servers - verify if we can extract from description
            # or just leave empty
            info["key_tools"] = []
            
        catalog[name] = info
        
    # Ensure data dir exists
    data_dir = PROJECT_ROOT / "src" / "brain" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    catalog_path = data_dir / "mcp_catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=2))
    print(f"Regenerated catalog at {catalog_path}", file=sys.stderr)
    
    # 4. Sync Schemas
    print("Running schema_sync.py...", file=sys.stderr)
    from src.maintenance import schema_sync
    try:
        schema_sync.main()
        print("Schema sync completed.", file=sys.stderr)
    except Exception as e:
        print(f"Schema sync failed: {e}", file=sys.stderr)
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
