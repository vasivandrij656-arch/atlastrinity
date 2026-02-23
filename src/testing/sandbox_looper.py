"""Sandbox Looper — Continuous Test and Heal Module

This script runs a target application continuously in a subprocess.
If the application crashes, it captures the error and passes it to the
SelfHealingHypermodule to automatically patch the code via Vibe.
Once the fix is purportedly applied, it restarts the application again.
"""

import asyncio
import logging
import subprocess
import sys
import time
from pathlib import Path

from src.brain.healing.hypermodule import HealingMode, healing_hypermodule
from src.brain.monitoring.logger import logger

logger = logging.getLogger("brain.healing.sandbox_looper")


class SandboxLooper:
    def __init__(self, target_script: str, max_retries: int = 5):
        self.target_script = target_script
        self.max_retries = max_retries
        self.current_retry = 0
        self.running = False

    async def start(self):
        """Start the continuous loop."""
        self.running = True
        logger.info(f"[SandboxLooper] Starting continuous test loop for: {self.target_script}")

        # Ensure Hypermodule is ready
        await healing_hypermodule.initialize()

        while self.running and self.current_retry < self.max_retries:
            logger.info(f"\n[SandboxLooper] --- Starting Process (Attempt {self.current_retry + 1}/{self.max_retries}) ---")
            
            try:
                # Run the target script and capture output
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    self.target_script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout_data, stderr_data = await process.communicate()
                return_code = process.returncode

                stdout_str = stdout_data.decode("utf-8")
                stderr_str = stderr_data.decode("utf-8")

                if return_code == 0:
                    logger.info("[SandboxLooper] Process completed successfully without errors!")
                    self.current_retry = 0  # Reset on success
                    break  # Could also loop forever if it's a daemon
                else:
                    logger.error(f"[SandboxLooper] Process crashed with code {return_code}")
                    logger.error(f"[SandboxLooper] STDERR: {stderr_str}")

                    # Attempt to heal
                    logger.info("[SandboxLooper] Triggering Self-Healing, waiting up to 60s for fix to apply...")
                    await self._heal_error(stderr_str, stdout_str)
                    
                    self.current_retry += 1
                    logger.info("[SandboxLooper] Waiting 30 seconds before restarting to ensure code is written...")
                    await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"[SandboxLooper] Error running process: {e}")
                self.current_retry += 1
                await asyncio.sleep(5)

        if self.current_retry >= self.max_retries:
            logger.critical("[SandboxLooper] Max retries reached. Application is hopelessly broken or the loop failed to heal it.")

        await healing_hypermodule.shutdown()
        logger.info("[SandboxLooper] Exited.")

    async def _heal_error(self, error_str: str, stdout_str: str):
        """Pass error to Hypermodule for automated healing."""
        logger.info("[SandboxLooper] 🦅 Triggering Self-Healing Hypermodule...")
        
        # We wrap the error properly to give maximum context
        context = {
            "error": error_str,
            "step_id": "sandbox_looper_execution",
            "step_context": {
                "target_script": self.target_script,
                "stdout": stdout_str[-2000:],  # Last 2000 chars
            },
            "depth": 0
        }

        # Use HEAL mode, which will eventually leverage Vibe/Copilot to patch the file
        result = await healing_hypermodule.run(HealingMode.HEAL, context=context)

        if result.success:
            logger.info(f"[SandboxLooper] ✅ Fix applied successfully (Duration: {result.duration_seconds:.1f}s)")
            logger.info(f"[SandboxLooper] Details: {result.message}")
        else:
            logger.error(f"[SandboxLooper] ❌ Healing failed: {result.message}")


async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m src.testing.sandbox_looper <path_to_script>")
        sys.exit(1)

    target = sys.argv[1]
    if not Path(target).exists():
        print(f"Error: Target script {target} does not exist.")
        sys.exit(1)

    # Configure root logger to output to console for the sandbox
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    looper = SandboxLooper(target_script=target, max_retries=10)
    
    try:
        await looper.start()
    except KeyboardInterrupt:
        logger.info("\n[SandboxLooper] Interrupted by user. Shutting down...")


if __name__ == "__main__":
    asyncio.run(main())
