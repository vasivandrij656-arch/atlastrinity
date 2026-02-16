import asyncio
import json
import os
import re
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.brain.agents.grisha import Grisha
from src.brain.agents.tetyana import Tetyana
from src.brain.mcp_manager import mcp_manager


async def run():
    tet = Tetyana(model_name="grok-code-fast-1")
    step = {
        "id": 424,
        "action": "Launch a browser and navigate to https://accounts.google.com/signup.",
        "tool": "browser",
        "args": {"action": "navigate", "url": "https://accounts.google.com/signup"},
    }

    await tet.execute_step(step, attempt=1)

    # Find the latest note for step_424
    notes_search = await mcp_manager.call_tool(
        "notes",
        "search_notes",
        {"tags": ["step_424"], "limit": 5},
    )
    _ = getattr(notes_search, "structuredContent", None) or getattr(
        notes_search,
        "content",
        None,
    )

    # Read note content if available and extract file path (first file path)
    note_id = None
    if isinstance(notes_search, dict):
        notes = notes_search.get("notes", [])
        if notes:
            note_id = notes[0]["id"]
    elif hasattr(notes_search, "structuredContent"):
        sc = notes_search.structuredContent.get("result", {})
        notes = sc.get("notes", [])
        if notes:
            note_id = notes[0]["id"]

    screenshot_path = None
    if note_id:
        note = await mcp_manager.call_tool("notes", "read_note", {"note_id": note_id})
        if isinstance(note, dict) and note.get("success"):
            content = note.get("content", "")
        else:
            note_content_list = getattr(note, "content", [])
            if (
                isinstance(note_content_list, list)
                and len(note_content_list) > 0
                and hasattr(note_content_list[0], "text")
            ):
                text_content = getattr(note_content_list[0], "text", "")
                try:
                    content = json.loads(text_content).get("content", "")
                except Exception:
                    content = text_content
            else:
                content = ""
        m = re.search(r"(/[^\s]+\.png)", content)
        if m:
            screenshot_path = m.group(1)

    # Ask Grisha to verify using the saved screenshot if found
    gr = Grisha()
    result = {"success": True, "output": "Navigated to accounts.google.com/signup"}
    await gr.verify_step(step, result, screenshot_path=screenshot_path)

    await mcp_manager.cleanup()


if __name__ == "__main__":
    asyncio.run(run())
