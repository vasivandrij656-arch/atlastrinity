import asyncio

from src.brain.core.orchestration.tool_dispatcher import ToolDispatcher


class MockMCPManager:
    async def call_tool(self, server, tool, args):
         return {"success": True, "result": "mocked", "content": [{"type": "text", "text": "mock"}]}

async def main():
    dispatcher = ToolDispatcher(MockMCPManager())
    
    print("=== ЕТАП 1: Нативні інструменти (Native Tools) ===")
    
    # Test Mapping
    native_tests = [
        ("ls", {"path": "/tmp"}),
        ("mkdir", {"command": "test"}),
        ("read", {"path": "test.txt", "action": "read"}),
        ("system", {"message": "ping"}),
        ("tour_start", {"polyline": "abc"}),
        ("restart_mcp_server", {"server_name": "filesystem"}),
    ]
    
    for tool_name, args in native_tests:
        print(f"\n--- Перевірка: {tool_name} ---")
        try:
            # Check routing mapping
            server, resolved_tool, new_args = dispatcher._resolve_routing(tool_name, dict(args), None)
            print(f"Мапінг: сервер '{server}', інструмент '{resolved_tool}' | Аргументи: {new_args}")
            
            # Check execution
            res = await dispatcher.resolve_and_dispatch(tool_name, dict(args))
            print(f"Виконання '{tool_name}': " + ("Успішно ✅" if res.get('success') else f"Помилка ❌ ({res.get('error', 'unknown')})"))
            if not res.get('success'):
                print(f"Деталі помилки: {res}")
        except Exception as e:
            print(f"Exception during routing/execution for {tool_name}: {e}")

    print("\n=== ЕТАП 2: Інші інструменти (Other Tools) ===")
    
    other_tests = [
        ("search_web", {"query": "python"}),
        ("docs", {"term": "requests"}),
        ("vibe_ask", {"question": "how to?"}),
        ("github", {"action": "status"}),
        ("analyze_data", {"action": "analyze_data"}),
    ]
    
    for tool_name, args in other_tests:
        print(f"\n--- Перевірка: {tool_name} ---")
        try:
            # Check routing mapping
            server, resolved_tool, new_args = dispatcher._resolve_routing(tool_name, dict(args), None)
            print(f"Мапінг: сервер '{server}', інструмент '{resolved_tool}'")
            
            # Since we mock MCPManager, it should 'succeed' by returning our mock except for validation logic
            res = await dispatcher.resolve_and_dispatch(tool_name, dict(args))
            print(f"Виконання '{tool_name}': " + ("Успішно ✅" if res.get('success') else f"Помилка ❌ ({res.get('error', 'Validation error')})"))
        except Exception as e:
            print(f"Exception during routing for {tool_name}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
