"""Test script for the enhanced learning and adaptation systems"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, UTC

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.brain.neural_core.core import neural_core
from src.brain.behavior.behavior_engine import behavior_engine
from src.brain.behavior.consolidation import consolidation_module

async def test_neuro_modulator_tool_stress():
    print("\n[TEST] 1. Testing NeuroModulator Tool-Specific Stress...")
    
    # Reset state
    neural_core.chemistry._chemistry.cortisol = 0.1
    initial_cortisol = neural_core.chemistry._chemistry.cortisol
    
    # Normal stress
    print("Sending normal stress...")
    neural_core.chemistry.stress(intensity=0.1)
    stress_1 = neural_core.chemistry._chemistry.cortisol
    print(f"Cortisol after normal stress: {stress_1:.2f}")
    
    # Tool-specific stress (delete_file has +0.4 sensitivity)
    print("Sending tool-specific stress for 'delete_file'...")
    neural_core.chemistry.stress(intensity=0.1, tool_name="filesystem.delete_file")
    stress_2 = neural_core.chemistry._chemistry.cortisol
    increased_stress = stress_2 - stress_1
    print(f"Cortisol after delete_file stress: {stress_2:.2f} (Increase: {increased_stress:.2f})")
    
    if increased_stress > 0.45: # 0.1 base + 0.4 sensitivity
        print("✅ Tool-specific stress PASSED!")
    else:
        print("❌ Tool-specific stress FAILED!")
        return False
        
    return True

async def test_neuro_modulator_accelerated_recovery():
    print("\n[TEST] 2. Testing NeuroModulator Accelerated Recovery...")
    
    neural_core.chemistry._chemistry.cortisol = 0.8
    print(f"Initial high cortisol: {neural_core.chemistry._chemistry.cortisol:.2f}")
    
    neural_core.chemistry.accelerate_recovery(multiplier=2.0)
    recovered_cortisol = neural_core.chemistry._chemistry.cortisol
    print(f"Cortisol after accelerated recovery: {recovered_cortisol:.2f}")
    
    if recovered_cortisol < 0.8:
        print("✅ Accelerated recovery PASSED!")
    else:
        print("❌ Accelerated recovery FAILED!")
        return False
        
    return True

async def test_behavior_engine_dynamic_alpha():
    print("\n[TEST] 3. Testing BehaviorEngine Dynamic Alpha...")
    
    pattern_type = "test_type"
    pattern_name = "test_pattern"
    
    # Initialize pattern metadata in config
    if "patterns" not in behavior_engine.config:
        behavior_engine.config["patterns"] = {}
    if pattern_type not in behavior_engine.config["patterns"]:
        behavior_engine.config["patterns"][pattern_type] = {}
    behavior_engine.config["patterns"][pattern_type][pattern_name] = {
        "metadata": {"usage_count": 0, "success_rate": 0.5, "volatility": 0.5, "last_result": True}
    }
    
    # 1. Flip result to increase volatility
    print("Flipping results to increase volatility...")
    behavior_engine.update_pattern_metrics(pattern_type, pattern_name, success=False)
    vol_1 = behavior_engine.config["patterns"][pattern_type][pattern_name]["metadata"]["volatility"]
    print(f"Volatility after flip: {vol_1}")
    
    # 2. Keep result same to decrease volatility
    print("Keeping results same to decrease volatility...")
    behavior_engine.update_pattern_metrics(pattern_type, pattern_name, success=False)
    vol_2 = behavior_engine.config["patterns"][pattern_type][pattern_name]["metadata"]["volatility"]
    print(f"Volatility after same result: {vol_2}")
    
    if vol_2 < vol_1:
        print("✅ Dynamic volatility adjustment PASSED!")
    else:
        print("❌ Dynamic volatility adjustment FAILED!")
        return False
        
    return True

async def test_immediate_consolidation():
    print("\n[TEST] 4. Testing Immediate Consolidation Trigger...")
    
    # Mock task state
    mock_state = {
        "_theme": "Test Failure Task",
        "step_results": [
            {"action": "test_tool", "status": "FAILED", "error": "Simulated critical error"}
        ]
    }
    
    print("Triggering immediate consolidation...")
    # This calls LLM, so we'll just check if it runs without crashing and logs correctly
    # In a real environment, we'd mock the LLM
    try:
        lesson = await consolidation_module.consolidate_immediate(mock_state)
        print(f"Consolidation result: {lesson}")
        print("✅ Immediate consolidation PASSED (execution check)!")
    except Exception as e:
        print(f"❌ Immediate consolidation FAILED: {e}")
        return False
        
    return True

async def main():
    print("=== STARTING LEARNING SYSTEMS VERIFICATION ===")
    
    success = True
    success &= await test_neuro_modulator_tool_stress()
    success &= await test_neuro_modulator_accelerated_recovery()
    success &= await test_behavior_engine_dynamic_alpha()
    # success &= await test_immediate_consolidation() # Skip LLM call in automated test if possible, or expect potential fail if no API key
    
    if success:
        print("\n✨ ALL COMPONENT TESTS PASSED! ✨")
    else:
        print("\n💥 SOME TESTS FAILED! 💥")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
