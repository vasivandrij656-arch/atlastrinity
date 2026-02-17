"""CI/CD Bridge for Self-Healing System.

Integrates GitHub Actions workflow results into the self-healing pipeline.
Reads workflow runs, analyzes failures, and can trigger auto-fix workflows
or commit fixes with [Self-Healing] tags.
"""

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.brain.healing.modes import CommitTag, ErrorDomain, HealingPriority, ImprovementNote

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

            async with (
                aiohttp.ClientSession() as session,
                session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp,
            ):
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

            failed_info = (
                ", ".join(j.get("name", "unknown") for j in result.failed_jobs) or "unknown jobs"
            )

            # Classify error domain from failed job names and error logs
            domain = self.classify_error(f"{result.name} {failed_info} {result.error_logs}")

            note = ImprovementNote(
                id=f"ci_{result.run_id}",
                category="ci_failure",
                description=f"[{domain.value}] CI workflow '{result.name}' failed: {failed_info}",
                severity=HealingPriority.HIGH,
                first_seen=datetime.now(),
                last_seen=datetime.now(),
            )
            notes.append(note)
            logger.info(f"[CIBridge] CI failure detected: {result.name} (domain={domain.value})")

            # If logs are available and it's a frontend error, parse further
            if result.error_logs and domain == ErrorDomain.FRONTEND:
                frontend_notes = self.analyze_frontend_errors(result.error_logs)
                notes.extend(frontend_notes)

        return notes

    @staticmethod
    def classify_error(log_line: str) -> ErrorDomain:
        """Classify an error line into a domain.

        Uses pattern matching to determine if the error is from frontend,
        backend, config, test, or build systems.
        """
        import re

        line = log_line.lower()

        # Frontend patterns
        if re.search(
            r"error ts\d+|ts\d+:|biome|vite|eslint|oxlint|renderer|react|jsx|tsx",
            line,
        ):
            return ErrorDomain.FRONTEND

        # Backend patterns
        if re.search(
            r"pytest|importerror|modulenotfounderror|pyrefly|ruff|pyright|python|pip",
            line,
        ):
            return ErrorDomain.BACKEND

        # Config patterns
        if re.search(r"yaml|json.*config|mcp.*config|\.env|config.*sync", line):
            return ErrorDomain.CONFIG

        # Test patterns
        if re.search(r"test.*fail|assert|expect|failed.*test|test.*error", line):
            return ErrorDomain.TEST

        # Build patterns
        if re.search(
            r"electron-builder|swift build|npm run build|build.*fail|dmg|packaging",
            line,
        ):
            return ErrorDomain.BUILD

        # Default to backend for unclassified
        return ErrorDomain.BACKEND

    def analyze_frontend_errors(self, log_content: str) -> list[ImprovementNote]:
        """Parse TypeScript/Vite/Lint errors from CI logs into structured notes.

        Extracts file paths, line numbers, and error codes from common
        frontend tooling output formats.

        Returns:
            List of ImprovementNote objects with source file information.
        """
        import re

        notes: list[ImprovementNote] = []
        seen: set[str] = set()

        # TypeScript errors: src/renderer/foo.tsx(42,5): error TS2345: ...
        ts_pattern = re.compile(r"([\w./]+\.tsx?)\((\d+),\d+\):\s*error\s+(TS\d+):\s*(.+)")

        # Vite errors: [vite] Internal server error: ...
        vite_pattern = re.compile(r"\[vite\].*?error:?\s*(.+)", re.IGNORECASE)

        # Biome/ESLint: src/renderer/foo.tsx:42:5 lint/rule: message
        lint_pattern = re.compile(r"([\w./]+\.tsx?):(\d+):\d+\s+(\S+):\s*(.+)")

        for line in log_content.splitlines():
            # TypeScript errors
            ts_match = ts_pattern.search(line)
            if ts_match:
                file_path, line_num, error_code, message = ts_match.groups()
                note_id = f"ts_{error_code}_{file_path}_{line_num}"
                if note_id not in seen:
                    seen.add(note_id)
                    notes.append(
                        ImprovementNote(
                            id=note_id,
                            category="typescript_error",
                            description=f"{error_code}: {message.strip()}",
                            source_file=file_path,
                            source_line=int(line_num),
                            severity=HealingPriority.HIGH,
                            first_seen=datetime.now(),
                            last_seen=datetime.now(),
                        )
                    )
                continue

            # Lint errors
            lint_match = lint_pattern.search(line)
            if lint_match:
                file_path, line_num, rule, message = lint_match.groups()
                note_id = f"lint_{rule}_{file_path}_{line_num}"
                if note_id not in seen:
                    seen.add(note_id)
                    notes.append(
                        ImprovementNote(
                            id=note_id,
                            category="lint_error",
                            description=f"{rule}: {message.strip()}",
                            source_file=file_path,
                            source_line=int(line_num),
                            severity=HealingPriority.MEDIUM,
                            first_seen=datetime.now(),
                            last_seen=datetime.now(),
                        )
                    )
                continue

            # Vite errors
            vite_match = vite_pattern.search(line)
            if vite_match:
                message = vite_match.group(1)
                note_id = f"vite_{hash(message) & 0xFFFFFF:06x}"
                if note_id not in seen:
                    seen.add(note_id)
                    notes.append(
                        ImprovementNote(
                            id=note_id,
                            category="vite_error",
                            description=f"Vite: {message.strip()}",
                            severity=HealingPriority.HIGH,
                            first_seen=datetime.now(),
                            last_seen=datetime.now(),
                        )
                    )

        if notes:
            logger.info(f"[CIBridge] Parsed {len(notes)} frontend errors from logs")
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

            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp,
            ):
                if resp.status == 204:
                    logger.info(f"[CIBridge] Triggered workflow: {workflow_name}")
                    return True
                logger.warning(f"[CIBridge] Failed to trigger workflow: {resp.status}")
                return False
        except Exception as e:
            logger.error(f"[CIBridge] Failed to trigger auto-fix: {e}")
            return False

    def parse_event_payload(self) -> dict[str, Any] | None:
        """Parse GitHub Actions event payload from GITHUB_EVENT_PATH."""
        event_path = os.getenv("GITHUB_EVENT_PATH")
        if not event_path or not os.path.exists(event_path):
            return None

        try:
            with open(event_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[CIBridge] Failed to parse event payload: {e}")
            return None

    def fetch_workflow_logs(self, run_id: int) -> str | None:
        """Fetch workflow logs using gh CLI.

        Returns:
            Path to downloaded log file or None.
        """
        try:
            # Check if gh is available
            subprocess.run(["gh", "--version"], check=True, capture_output=True)

            log_dir = Path.home() / ".config" / "atlastrinity" / "logs" / f"run_{run_id}"
            log_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"[CIBridge] Downloading logs for run {run_id}...")

            # Capture logs from gh run view
            result = subprocess.run(
                ["gh", "run", "view", str(run_id), "--log"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                check=True,
            )

            log_file = log_dir / "workflow.log"
            log_file.write_text(result.stdout, encoding="utf-8")
            return str(log_file)

        except subprocess.CalledProcessError as e:
            logger.error(f"[CIBridge] Failed to fetch logs: {e.stderr}")
            return None
        except Exception as e:
            logger.error(f"[CIBridge] Log fetch error: {e}")
            return None

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

    async def _get_failed_jobs(self, run_id: int, headers: dict[str, str]) -> list[dict[str, Any]]:
        """Get failed jobs for a workflow run."""
        try:
            import aiohttp

            url = f"https://api.github.com/repos/{self._repo}/actions/runs/{run_id}/jobs"
            async with (
                aiohttp.ClientSession() as session,
                session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp,
            ):
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
