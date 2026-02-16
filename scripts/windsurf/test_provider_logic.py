import sys
import os
import asyncio
from langchain_core.messages import HumanMessage

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.providers.windsurf import WindsurfLLM

async def main():
    print("Testing WindsurfLLM (Python Provider)...")
    
    # Force use of local LS
    os.environ["WINDSURF_MODE"] = "local"
    # Ensure LS credentials from .env are used
    
    llm = WindsurfLLM(model_name="swe-1.5")
    
    messages = [HumanMessage(content="Hello!")]
    
    try:
        print("Sending request...")
        response = await llm.ainvoke(messages)
        print("Response received:")
        print(response.content)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
