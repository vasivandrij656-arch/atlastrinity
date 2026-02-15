"""
Git Repository Manager with GitHub Integration.

Handles git initialization, GitHub token setup, and remote configuration.
"""

import os
import subprocess
from pathlib import Path
from typing import Any

import requests


def ensure_git_repository(project_path: Path) -> dict[str, Any]:
    """Ensure project has git initialized.

    Args:
        project_path: Path to project

    Returns:
        Status dict with success/error
    """
    git_dir = project_path / ".git"

    if git_dir.exists():
        return {"initialized": True, "message": "Git repository already exists"}

    try:
        # Initialize git
        result = subprocess.run(
            ["git", "init"], cwd=project_path, capture_output=True, text=True, check=False
        )

        if result.returncode != 0:
            return {"initialized": False, "error": f"Git init failed: {result.stderr}"}

        # Create initial .gitignore if not exists
        gitignore_path = project_path / ".gitignore"
        if not gitignore_path.exists():
            gitignore_path.write_text(
                """# Common ignores
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.venv/
node_modules/
.DS_Store
.env
.idea/
.vscode/
*.log
"""
            )

        # Create initial commit
        subprocess.run(["git", "add", ".gitignore"], cwd=project_path, check=False)
        subprocess.run(
            ["git", "commit", "-m", "chore: initial commit with .gitignore"],
            cwd=project_path,
            capture_output=True,
            check=False,
        )

        return {
            "initialized": True,
            "message": "Git repository initialized successfully",
            "created_gitignore": True,
        }

    except Exception as e:
        return {"initialized": False, "error": str(e)}


def setup_github_remote(
    project_path: Path, repo_name: str | None = None, github_token: str | None = None
) -> dict[str, Any]:
    """Setup GitHub remote with authentication.

    Args:
        project_path: Path to project
        repo_name: GitHub repo name (e.g., 'user/repo')
        github_token: GitHub personal access token

    Returns:
        Status dict with remote URL
    """
    # Try to get token from .env if not provided
    if github_token is None:
        github_token = _get_github_token_from_env(project_path)

    if not github_token:
        return {
            "configured": False,
            "error": "GitHub token not found. Set GITHUB_TOKEN in .env or pass as parameter",
        }

    # If repo_name not provided, try to infer from existing remote
    if repo_name is None:
        existing_remote = _get_existing_remote(project_path)
        if existing_remote:
            repo_name = _extract_repo_name(existing_remote)

    if not repo_name:
        return {
            "configured": False,
            "error": "Repo name required. Format: 'username/repository'",
        }

    try:
        # Configure remote URL with token
        remote_url = f"https://{github_token}@github.com/{repo_name}.git"

        # Check if origin exists
        check_result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=False,
        )

        if check_result.returncode == 0:
            # Update existing remote
            subprocess.run(
                ["git", "remote", "set-url", "origin", remote_url],
                cwd=project_path,
                check=True,
                capture_output=True,
            )
            action = "updated"
        else:
            # Add new remote
            subprocess.run(
                ["git", "remote", "add", "origin", remote_url],
                cwd=project_path,
                check=True,
                capture_output=True,
            )
            action = "added"

        # Configure git user if not set
        _configure_git_user(project_path)

        return {
            "configured": True,
            "action": action,
            "remote_url": f"https://github.com/{repo_name}.git",  # Don't expose token
            "repo_name": repo_name,
        }

    except Exception as e:
        return {"configured": False, "error": str(e)}


def _get_github_token_from_env(project_path: Path) -> str | None:
    """Read GITHUB_TOKEN from global .env (~/.config/atlastrinity/.env).

    Priority:
    1. Global config .env (~/.config/atlastrinity/.env) - PRIMARY SOURCE
    2. System environment variable (GITHUB_TOKEN)
    3. External project .env (project_path/.env) - for external projects only

    Note: AtlasTrinity uses ONLY global config, external projects can have their own.
    """
    from pathlib import Path as PathlibPath

    # 1. Check if this is AtlasTrinity internal (has src/brain/)
    is_internal = (project_path / "src" / "brain").exists()

    if is_internal:
        # Internal AtlasTrinity - use ONLY global .env
        global_env = PathlibPath.home() / ".config" / "atlastrinity" / ".env"
        if global_env.exists():
            try:
                content = global_env.read_text()
                for line in content.split("\n"):
                    if line.startswith("GITHUB_TOKEN="):
                        token = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if token:
                            return token
            except Exception:
                pass
    else:
        # External project - check project .env first, then global
        project_env = project_path / ".env"
        if project_env.exists():
            try:
                content = project_env.read_text()
                for line in content.split("\n"):
                    if line.startswith("GITHUB_TOKEN="):
                        token = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if token:
                            return token
            except Exception:
                pass

    # Fallback to environment variable
    return os.environ.get("GITHUB_TOKEN")


def _get_existing_remote(project_path: Path) -> str | None:
    """Get existing origin remote URL."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _extract_repo_name(remote_url: str) -> str | None:
    """Extract 'user/repo' from git remote URL."""
    # Handle HTTPS URLs
    if "github.com/" in remote_url:
        parts = remote_url.rsplit("github.com/", maxsplit=1)[-1]
        parts = parts.replace(".git", "").strip("/")
        return parts if "/" in parts else None

    # Handle SSH URLs
    if "git@github.com:" in remote_url:
        parts = remote_url.rsplit("git@github.com:", maxsplit=1)[-1]
        parts = parts.replace(".git", "").strip("/")
        return parts if "/" in parts else None

    return None


def _configure_git_user(project_path: Path) -> None:
    """Configure git user.name and user.email if not set."""
    try:
        # Check if user.name is set
        result = subprocess.run(
            ["git", "config", "user.name"],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0 or not result.stdout.strip():
            # Set default user
            subprocess.run(
                ["git", "config", "user.name", "AtlasTrinity Bot"],
                cwd=project_path,
                check=False,
            )
            subprocess.run(
                ["git", "config", "user.email", "bot@atlastrinity.local"],
                cwd=project_path,
                check=False,
            )
    except Exception:
        pass


def get_git_changes(project_path: Path, commits_back: int = 1) -> dict[str, Any]:
    """Get git log and diff for analysis.

    Args:
        project_path: Path to project
        commits_back: Number of commits to analyze

    Returns:
        Dict with log, diff, and modified files
    """
    try:
        # Get log
        log_result = subprocess.run(
            ["git", "log", f"-{commits_back}", "--stat", "--pretty=format:%H|%an|%ad|%s"],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=False,
        )

        if log_result.returncode != 0:
            return {"error": f"Git log failed: {log_result.stderr}"}

        # Get diff of ALL files (not just src/brain/)
        diff_result = subprocess.run(
            ["git", "diff", f"HEAD~{commits_back}", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=False,
        )

        git_diff = diff_result.stdout.strip()

        # Parse modified files from diff
        modified_files = []
        for line in git_diff.split("\n"):
            if line.startswith("diff --git"):
                file_path = line.split()[-1].replace("b/", "")
                modified_files.append(file_path)

        return {
            "log": log_result.stdout.strip(),
            "diff": git_diff,
            "modified_files": modified_files,
            "success": True,
        }

    except Exception as e:
        return {"error": str(e), "success": False}


def fetch_github_workflow_runs(project_path: Path, limit: int = 5) -> dict[str, Any]:
    """Fetch recent GitHub Action workflow runs.

    Args:
        project_path: Path to project to find repo/token
        limit: Number of runs to return

    Returns:
        Dict with runs list or error
    """
    token = _get_github_token_from_env(project_path)
    if not token:
        return {"error": "GITHUB_TOKEN not found"}

    remote = _get_existing_remote(project_path) or ""
    repo = _extract_repo_name(remote)
    if not repo:
        return {"error": "Could not determine repository name from git remote"}

    url = f"https://api.github.com/repos/{repo}/actions/runs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    params = {"per_page": limit}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            return {"error": f"GitHub API error {resp.status_code}: {resp.text}"}

        data = resp.json()
        return {"success": True, "runs": data.get("workflow_runs", []), "repo": repo}
    except Exception as e:
        return {"error": str(e)}


def fetch_github_workflow_jobs(project_path: Path, run_id: str) -> dict[str, Any]:
    """Fetch jobs for a specific workflow run.

    Args:
        project_path: Path to project
        run_id: Workflow run ID

    Returns:
        Dict with jobs list
    """
    token = _get_github_token_from_env(project_path)
    if not token:
        return {"error": "GITHUB_TOKEN not found"}

    remote = _get_existing_remote(project_path) or ""
    repo = _extract_repo_name(remote)
    if not repo:
        return {"error": "Could not determine repository name"}

    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return {"error": f"GitHub API error {resp.status_code}: {resp.text}"}

        data = resp.json()
        return {"success": True, "jobs": data.get("jobs", []), "repo": repo}
    except Exception as e:
        return {"error": str(e)}


def download_github_job_logs(project_path: Path, job_id: str) -> dict[str, Any]:
    """Download raw logs for a specific job.

    Args:
        project_path: Path to project
        job_id: Job ID

    Returns:
        Dict with log content
    """
    token = _get_github_token_from_env(project_path)
    if not token:
        return {"error": "GITHUB_TOKEN not found"}

    remote = _get_existing_remote(project_path) or ""
    repo = _extract_repo_name(remote)
    if not repo:
        return {"error": "Could not determine repository name"}

    url = f"https://api.github.com/repos/{repo}/actions/jobs/{job_id}/logs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        # Follow redirects automatically (requests does this by default)
        resp = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        if resp.status_code != 200:
            return {"error": f"GitHub API error {resp.status_code}: {resp.text}"}

        # The content IS the log
        return {"success": True, "logs": resp.text, "repo": repo, "job_id": job_id}
    except Exception as e:
        return {"error": str(e)}
