import asyncio
import os

from langchain_core.messages import HumanMessage

from src.providers.windsurf import WindsurfLLM


async def test_cascade_tool():
    print("🚀 Testing Direct Cascade Tool Calling...")

    # Ensure mode is forced to cascade for detection
    os.environ["WINDSURF_MODE"] = "cascade"

    llm = WindsurfLLM(model_name="deepseek-v3")
    print(f"Detected Mode: {llm._mode}")
    if hasattr(llm, "ls_port"):
        print(f"LS Port: {llm.ls_port}")

    messages = [
        HumanMessage(
            content="Create a file named ~/Desktop/cascade_test.txt with content 'Hello from Cascade!'"
        )
    ]

    # Define a simple tool to see if it triggers the same error
    tools = [
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Write a file to disk",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["path", "content"],
                },
            },
        }
    ]

    try:
        print("Calling LLM...")
        # Bind tools to see if the LS handles them
        llm_with_tools = llm.bind_tools(tools)
        response = llm_with_tools.invoke(messages)
        print("Response received!")
        print(response)
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_cascade_tool())
