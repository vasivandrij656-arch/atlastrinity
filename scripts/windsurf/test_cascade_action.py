#!/usr/bin/env python3
"""
Test Windsurf Cascade Action Phase
==================================

Invokes the standard _call_cascade method (with new flags) to test if it triggers
Action Phase logic (e.g. file creation).
"""

import os
import sys
import time
from pathlib import Path

# Add project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.messages import HumanMessage
from src.providers.windsurf import WindsurfLLM

def main():
    print("🌊 Testing Cascade Action Phase Flags...")
    
    # Initialize LLM
    try:
        llm = WindsurfLLM(model_name="swe-1.5")
        print(f"✅ LLM Initialized (Mode: {llm._mode})")
        
        if not llm.ls_port:
            print("❌ LS not detected.")
            sys.exit(1)
            
        # Specific prompt to trigger file creation
        # "Create a file named 'simulated_action.txt' with content 'Hello World'"
        prompt = "Create a file named 'simulated_action.txt' with content 'Hello Action Phase'"
        messages = [HumanMessage(content=prompt)]
        
        print(f"\n📝 Sending prompt: '{prompt}'")
        print("⏳ Waiting for Cascade response (may take 20s+)...")
        
        start_t = time.time()
        response = llm._call_cascade(messages)
        elapsed = time.time() - start_t
        
        print(f"\n📥 Response ({elapsed:.1f}s):")
        print("-" * 60)
        print(response)
        print("-" * 60)
        
        # Check if file was created? 
        # Note: The *server* executes the action. 
        # Use existing 'simulated_action.txt' check if possible, or just check response text.
        
        if "wrote" in response.lower() or "created" in response.lower():
            print("\n✅ Success! Response indicates action execution.")
        else:
            print("\n⚠️ Response does not clearly indicate action execution.")
            
    except Exception as e:
        print(f"\n❌ Test Failed: {e}")

if __name__ == "__main__":
    main()
