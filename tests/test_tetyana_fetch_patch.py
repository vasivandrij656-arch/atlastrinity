import pytest

from src.brain.agents.tetyana import Tetyana


@pytest.mark.asyncio
async def test_fetch_urls_patch(monkeypatch):
    """Ensure that when 'urls' is provided and 'url' is missing, the first URL is taken."""
    tet = Tetyana(model_name="grok-code-fast-1")

    captured = {}

    async def fake_call(server_name, tool_name, arguments):
        captured["server"] = server_name
        captured["tool"] = tool_name
        captured["args"] = dict(arguments)  # copy to inspect
        return {"success": True, "output": "ok"}

    from src.brain.mcp_manager import mcp_manager

    monkeypatch.setattr(mcp_manager, "call_tool", fake_call)

    tool_call = {"name": "fetch", "args": {"urls": ["http://example.com"]}}
    result = await tet._execute_tool(tool_call)

    assert captured["args"].get("url") == "http://example.com"
    assert isinstance(result, dict)
    assert result.get("success") is True
