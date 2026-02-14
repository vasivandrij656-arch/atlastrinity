"""CI/CD Bridge for Self-Healing System.

Integrates GitHub Actions workflow results into the self-healing pipeline.
Reads workflow runs, analyzes failures, and can trigger auto-fix workflows
or commit fixes with [Self-Healing] tags.
"""

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.brain.healing.modes import CommitTag, HealingPriority, ImprovementNote

logger = logging.getLogger("brain.healing.ci_bridge")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


@dataclass
class WorkflowResult:
    """Result of a GitHub Actions workflow run."""

    name: str
    status: str  # "success", "failure", "cancelled"
    conclusion: str | None = None
    run_id: int = 0
    url: str = ""
    started_at: str = ""
    failed_jobs: list[dict[str, Any]] = field(default_factory=list)
    error_logs: str = ""


class CIBridge:
    """Bridges CI/CD workflow results into the self-healing system.

    Features:
    - Query GitHub Actions API for recent workflow runs
    - Analyze CI failures and create improvement notes
    - Trigger auto-fix workflows
    - Commit and push with [Self-Healing] tags
    """

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or PROJECT_ROOT
        self._github_token = os.getenv("GITHUB_TOKEN")
        self._repo = "solagurma/atlastrinity"

    async def check_workflow_status(self) -> list[WorkflowResult]:
        """Query GitHub Actions API for recent workflow runs.

        Returns most recent run per workflow.
        """
        results: list[WorkflowResult] = []

        if not self._github_token:
            logger.warning("[CIBridge] No GITHUB_TOKEN set, cannot check workflow status")
            return results

        try:
            import aiohttp

            headers = {
                "Authorization": f"token {self._github_token}",
                "Accept": "application/vnd.github.v3+json",
            }
            url = f"https://api.github.com/repos/{self._repo}/actions/runs?per_page=20"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        logger.warning(f"[CIBridge] GitHub API returned {resp.status}")
                        return results
                    data = await resp.json()

            # Group by workflow name, keep latest
            latest_by_name: dict[str, dict] = {}
            for run in data.get("workflow_runs", []):
                name = run.get("name", "unknown")
                if name not in latest_by_name:
                    latest_by_name[name] = run

            for name, run in latest_by_name.items():
                result = WorkflowResult(
                    name=name,
                    status=run.get("status", "unknown"),
                    conclusion=run.get("conclusion"),
                    run_id=run.get("id", 0),
                    url=run.get("html_url", ""),
                    started_at=run.get("run_started_at", ""),
                )
                if result.conclusion == "failure":
                    result.failed_jobs = await self._get_failed_jobs(result.run_id, headers)

                results.append(result)

        except ImportError:
            logger.warning("[CIBridge] aiohttp not available, using git CLI fallback")
            results = self._check_local_ci()
        except Exception as e:
            logger.error(f"[CIBridge] Failed to check workflow status: {e}")

        return results

    async def analyze_failures(self, results: list[WorkflowResult]) -> list[ImprovementNote]:
        """Analyze CI failures and create improvement notes.

        Returns:
            List of ImprovementNote objects for failed workflows.
        """
        notes: list[ImprovementNote] = []

        for result in results:
            if result.conclusion != "failure":
                continue

            failed_info = ", ".join(
                j.get("name", "unknown") for j in result.failed_jobs
            ) or "unknown jobs"

            note = ImprovementNote(
                id=f"ci_{result.run_id}",
                category="ci_failure",
                description=f"CI workflow '{result.name}' failed: {failed_info}",
                severity=HealingPriority.HIGH,
                first_seen=datetime.now(),
                last_seen=datetime.now(),
            )
            notes.append(note)
            logger.info(f"[CIBridge] CI failure detected: {result.name}")

        return notes

    async def trigger_auto_fix(self, workflow_name: str = "auto-fix.yml") -> bool:
        """Trigger auto-fix workflow via GitHub API.

        Returns:
            True if the workflow was triggered successfully.
        """
        if not self._github_token:
            logger.warning("[CIBridge] No GITHUB_TOKEN, cannot trigger workflow")
            return False

        try:
            import aiohttp

            headers = {
                "Authorization": f"token {self._github_token}",
                "Accept": "application/vnd.github.v3+json",
            }
            url = f"https://api.github.com/repos/{self._repo}/actions/workflows/{workflow_name}/dispatches"
            payload = {"ref": "main"}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 204:
                        logger.info(f"[CIBridge] Triggered workflow: {workflow_name}")
                        return True
                    else:
                        logger.warning(f"[CIBridge] Failed to trigger workflow: {resp.status}")
                        return False
        except Exception as e:
            logger.error(f"[CIBridge] Failed to trigger auto-fix: {e}")
            return False

    def commit_and_push(
        self,
        message: str,
        files: list[str] | None = None,
        tag: CommitTag = CommitTag.SELF_HEALING,
    ) -> str | None:
        """Git commit with [Self-Healing] tag and push.

        Args:
            message: Commit message (tag is prepended automatically).
            files: Specific files to commit (None = stage all changes).
            tag: CommitTag to prepend.

        Returns:
            Commit hash if successful, None otherwise.
        """
        try:
            cwd = str(self.project_root)

            # Stage files
            if files:
                for f in files:
                    subprocess.run(["git", "add", f], cwd=cwd, check=True, capture_output=True)
            else:
                subprocess.run(["git", "add", "-A"], cwd=cwd, check=True, capture_output=True)

            # Check if there are changes to commit
            status = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=cwd,
                capture_output=True,
            )
            if status.returncode == 0:
                logger.info("[CIBridge] No changes to commit")
                return None

            # Commit
            full_message = f"{tag.value} {message}"
            subprocess.run(
                ["git", "commit", "-m", full_message],
                cwd=cwd,
                check=True,
                capture_output=True,
            )

            # Get commit hash
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
            )
            commit_hash = result.stdout.strip()

            # Push
            push_result = subprocess.run(
                ["git", "push"],
                cwd=cwd,
                capture_output=True,
                text=True,
            )
            if push_result.returncode != 0:
                logger.warning(f"[CIBridge] Push failed: {push_result.stderr}")
            else:
                logger.info(f"[CIBridge] Committed and pushed: {commit_hash[:8]} — {full_message}")

            return commit_hash

        except subprocess.CalledProcessError as e:
            logger.error(f"[CIBridge] Git operation failed: {e}")
            return None
        except Exception as e:
            logger.error(f"[CIBridge] Commit failed: {e}")
            return None

    # --- Private methods ---

    async def _get_failed_jobs(
        self, run_id: int, headers: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Get failed jobs for a workflow run."""
        try:
            import aiohttp

            url = f"https://api.github.com/repos/{self._repo}/actions/runs/{run_id}/jobs"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()

            return [
                {"name": job["name"], "conclusion": job.get("conclusion")}
                for job in data.get("jobs", [])
                if job.get("conclusion") == "failure"
            ]
        except Exception:
            return []

    def _check_local_ci(self) -> list[WorkflowResult]:
        """Fallback: check local CI logs when no API access."""
        results: list[WorkflowResult] = []
        ci_log = Path.home() / ".config" / "atlastrinity" / "logs" / "ci_pipeline.log"

        if ci_log.exists():
            try:
                content = ci_log.read_text(encoding="utf-8")
                if "FAILED" in content or "ERROR" in content:
                    results.append(
                        WorkflowResult(
                            name="Local CI",
                            status="completed",
                            conclusion="failure",
                            error_logs=content[-500:],
                        )
                    )
            except Exception:
                pass

        return results


# Singleton
ci_bridge = CIBridge()
