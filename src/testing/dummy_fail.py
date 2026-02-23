"""Dummy failing script for testing Sandbox Looper."""

import time

def buggy_function():
    print("Running buggy_function...")
    time.sleep(1)
    
    # This will cause a ZeroDivisionError
    result = 10 / 0
    print(f"Result is {result}")

if __name__ == "__main__":
    print("Starting dummy script...")
    buggy_function()
    print("Finished successfully!")
