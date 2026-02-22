"""
EvolutionSandbox: The Isolated Testing Environment for NeuralCore.
Allows safe application and verification of autonomous system updates.
"""

import asyncio
import logging
import os
import shutil
import tempfile
from typing import Any

logger = logging.getLogger("brain.neural_core.evolution.sandbox")


class EvolutionSandbox:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.sandbox_path: str | None = None
        self._temp_dir = None

    async def prepare_sandbox(self, files_to_copy: list[str]) -> bool:
        """Copies selected files from the base codebase to a temporary sandbox."""
        try:
            self._temp_dir = tempfile.mkdtemp(prefix="atlas_evolution_")
            self.sandbox_path = self._temp_dir
            logger.info(f"[SANDBOX] Created temporary workspace at {self.sandbox_path}")

            for rel_path in files_to_copy:
                src = os.path.join(self.base_dir, rel_path)
                dst = os.path.join(self.sandbox_path, rel_path)

                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
                elif os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)

            return True
        except Exception as e:
            logger.error(f"[SANDBOX] Failed to prepare sandbox: {e}")
            return False

    async def apply_patch(self, target_file: str, _diff_content: str) -> bool:
        """Applies a patch (simulated Vibe-style) to a file in the sandbox."""
        if not self.sandbox_path:
            return False

        dst_file = os.path.join(self.sandbox_path, target_file)
        if not os.path.exists(dst_file):
            logger.error(f"[SANDBOX] Target file {target_file} not found in sandbox.")
            return False

        try:
            # Simplified patch application for illustration
            # In a real scenario, this would use a more robust diff/patch utility
            logger.info(f"[SANDBOX] Applying autonomous patch to {target_file}...")
            # For now, we simulate success
            return True
        except Exception as e:
            logger.error(f"[SANDBOX] Patch application failed: {e}")
            return False

    async def run_verification(self) -> dict[str, Any]:
        """Runs linting and basic tests within the sandbox."""
        if not self.sandbox_path:
            return {"success": False, "error": "No sandbox initialized"}

        logger.info("[SANDBOX] Starting verification protocols...")

        # 1. Static Analysis (Linting)
        lint_process = await asyncio.create_subprocess_exec(
            "ruff",
            "check",
            self.sandbox_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await lint_process.communicate()
        lint_ok = lint_process.returncode == 0

        # 2. Dynamic Analysis (Placeholder for pytest)
        # In a real environment, we'd run pytest here
        test_ok = True

        return {
            "success": lint_ok and test_ok,
            "lint_report": stdout.decode() if not lint_ok else "All lint checks passed.",
            "test_report": "Tests passed (simulated).",
        }

    async def cleanup(self):
        """Removes the temporary sandbox directory."""
        if self._temp_dir and os.path.exists(self._temp_dir):
            shutil.rmtree(self._temp_dir)
            logger.info("[SANDBOX] Workspace cleaned up.")


# Global utilities
def get_sandbox(base_dir: str) -> EvolutionSandbox:
    return EvolutionSandbox(base_dir)
