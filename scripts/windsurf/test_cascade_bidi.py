#!/usr/bin/env python3
"""
Test Windsurf Cascade Bidirectional Streaming
=============================================

Invokes the experimental _call_cascade_bidi method to test StartChatClientRequestStream.
"""

import os
import sys
from pathlib import Path

# Add project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.messages import HumanMessage
from src.providers.windsurf import WindsurfLLM

def main():
    print("🌊 Testing Cascade Bidi Stream...")
    
    # Initialize LLM (auto-detects LS)
    try:
        llm = WindsurfLLM(model_name="windsurf-fast") # Model doesn't matter much for initial connection
        print(f"✅ LLM Initialized (Mode: {llm._mode})")
        
        if not llm.ls_port or not llm.ls_csrf:
            print("❌ LS not detected. Is Windsurf running?")
            sys.exit(1)
            
        print(f"   LS Port: {llm.ls_port}")
        print(f"   CSRF: {llm.ls_csrf[:10]}...")
        
        # Call Bidi Stream
        messages = [HumanMessage(content="Hello, are you there?")]
        print("\n📡 Sending request via StartChatClientRequestStream...")
        
        try:
            response = llm._call_cascade_bidi(messages)
            print("\n📥 Response:")
            print(response)
        except Exception as e:
            print(f"\n❌ Bidi Call Failed: {e}")
            
    except Exception as e:
        print(f"❌ Setup Failed: {e}")

if __name__ == "__main__":
    main()
