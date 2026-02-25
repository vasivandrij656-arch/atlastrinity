#!/usr/bin/env python3
"""Verification script for Request Segmentation Logic.

Targeting:
1. Segmentation (splitting mixed intents)
2. Merging/Joining (compatible modes)
3. Context Linkage (single context requests)
"""

import asyncio
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.brain.core.orchestration.request_segmenter import request_segmenter

async def run_test(name, user_request):
    print(f"\n--- {name} ---")
    print(f"Request: {user_request}")
    
    segments = await request_segmenter.split_request(user_request)
    
    print(f"Segments ({len(segments)}):")
    for i, seg in enumerate(segments):
        print(f"  [{i+1}] Mode: {seg.mode:12} | Text: {seg.text[:60]}...")
        print(f"      Reason: {seg.reason}")
    
    return segments

async def main():
    print("🚀 Starting Advanced Segmentation Verification")
    
    # 1. Test Segmentation (Mixed Intents)
    # Expected: Split into chat, deep_chat, and task
    s1 = await run_test("Scenario 1: Mixed Intents", 
                       "Привіт! Ти впевнений, що маєш душу? Також знайди інформацію про компанію Apple.")
    
    # 2. Test Merging/Joining (Compatible Modes)
    # Expected: 'chat' and 'deep_chat' might be merged depending on LLM decision or keyword order, 
    # but 'chat' + 'chat' should definitely merge.
    s2 = await run_test("Scenario 2: Join Compatible", 
                       "Привіт! Як справи? Окей, я зрозумів.")
    
    # 3. Test Context Linkage (Single Context)
    # Expected: Numbered questions about identity should all be 'deep_chat'
    s3 = await run_test("Scenario 3: Multi-part Identity", 
                       "1. Хто тебе створив? 2. В чому твоя місія? 3. Чи ти боїшся смерті?")
    
    # 4. Test Task Segmentation
    # Expected: Split between research (solo_task) and execution (task)
    s4 = await run_test("Scenario 4: Research + Execution", 
                       "Знайди останню версію Python, а потім створи скрипт 'hello.py' з принтом версії.")

    print("\n✅ Verification data collected.")

if __name__ == "__main__":
    asyncio.run(main())
