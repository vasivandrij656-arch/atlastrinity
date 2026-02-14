"""CI/CD Compatibility — Environment detection and graceful degradation.

Detects when running in CI/CD pipelines (GitHub Actions, GitLab CI, etc.)
and adjusts auth system behavior accordingly:

- No macOS Keychain access in CI (ubuntu runners)
- No system password / sudo in CI
- No browser credential stores
- Limited environment variables
- Self-healing: auto-detects environment and adjusts strategy

Environment detection checks:
    CI=true                    — Generic CI indicator
    GITHUB_ACTIONS=true        — GitHub Actions
    GITLAB_CI=true             — GitLab CI
    JENKINS_URL                — Jenkins
    CIRCLECI=true              — CircleCI
    TRAVIS=true                — Travis CI
    BUILDKITE=true             — Buildkite
    TF_BUILD=True              — Azure Pipelines
"""

from __future__ import annotations

import logging
import os
import platform
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger("brain.auth.ci")


class CIProvider(StrEnum):
    """Known CI/CD providers."""

    GITHUB_ACTIONS = "github_actions"
    GITLAB_CI = "gitlab_ci"
    JENKINS = "jenkins"
    CIRCLECI = "circleci"
    TRAVIS = "travis"
    BUILDKITE = "buildkite"
    AZURE_PIPELINES = "azure_pipelines"
    GENERIC_CI = "generic_ci"
    LOCAL = "local"  # Not in CI


@dataclass(frozen=True)
class CIEnvironment:
    """Describes the detected CI/CD environment."""

    is_ci: bool
    provider: CIProvider
    has_macos_keychain: bool
    has_system_password: bool
    has_browser_stores: bool
    has_sudo: bool
    runner_os: str

    @property
    def is_local(self) -> bool:
        return not self.is_ci

    @property
    def available_features(self) -> list[str]:
        """List of available auth features in this environment."""
        features = ["credential_vault", "env_vars", "dotenv"]
        if self.has_macos_keychain:
            features.append("macos_keychain")
        if self.has_system_password:
            features.append("system_access")
        if self.has_browser_stores:
            features.append("browser_passwords")
        if self.has_sudo:
            features.append("sudo")
        return features


def detect_ci_environment() -> CIEnvironment:
    """Detect CI/CD environment and available capabilities.

    Returns a CIEnvironment describing what's available.
    This is the primary self-healing entry point — the auth system
    uses this to automatically adjust its behavior.
    """
    is_ci = _is_ci()
    provider = _detect_provider()
    runner_os = platform.system()  # Darwin, Linux, Windows
    is_macos = runner_os == "Darwin"

    if is_ci:
        logger.info(
            "🔧 CI environment detected: provider=%s, os=%s",
            provider.value,
            runner_os,
        )
        env = CIEnvironment(
            is_ci=True,
            provider=provider,
            has_macos_keychain=is_macos and _has_security_cli(),
            has_system_password=bool(os.getenv("ATLAS_SYSTEM_PASSWORD")),
            has_browser_stores=False,  # Never in CI
            has_sudo=_has_sudo(),
            runner_os=runner_os,
        )
    else:
        env = CIEnvironment(
            is_ci=False,
            provider=CIProvider.LOCAL,
            has_macos_keychain=is_macos and _has_security_cli(),
            has_system_password=bool(os.getenv("ATLAS_SYSTEM_PASSWORD")),
            has_browser_stores=is_macos or runner_os == "Linux",
            has_sudo=_has_sudo(),
            runner_os=runner_os,
        )

    logger.info(
        "🔑 Auth capabilities: %s", ", ".join(env.available_features)
    )
    return env


def _is_ci() -> bool:
    """Check if we're running in any CI environment."""
    ci_indicators = [
        "CI",
        "GITHUB_ACTIONS",
        "GITLAB_CI",
        "JENKINS_URL",
        "CIRCLECI",
        "TRAVIS",
        "BUILDKITE",
        "TF_BUILD",
        "CODEBUILD_BUILD_ID",
        "BITBUCKET_PIPELINE",
    ]
    return any(os.getenv(var) for var in ci_indicators)


def _detect_provider() -> CIProvider:
    """Detect which CI provider we're running on."""
    if os.getenv("GITHUB_ACTIONS"):
        return CIProvider.GITHUB_ACTIONS
    if os.getenv("GITLAB_CI"):
        return CIProvider.GITLAB_CI
    if os.getenv("JENKINS_URL"):
        return CIProvider.JENKINS
    if os.getenv("CIRCLECI"):
        return CIProvider.CIRCLECI
    if os.getenv("TRAVIS"):
        return CIProvider.TRAVIS
    if os.getenv("BUILDKITE"):
        return CIProvider.BUILDKITE
    if os.getenv("TF_BUILD"):
        return CIProvider.AZURE_PIPELINES
    if os.getenv("CI"):
        return CIProvider.GENERIC_CI
    return CIProvider.LOCAL


def _has_security_cli() -> bool:
    """Check if macOS `security` CLI is available."""
    import subprocess

    try:
        result = subprocess.run(
            ["security", "help"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _has_sudo() -> bool:
    """Check if sudo is available (not that we have a password)."""
    import subprocess

    try:
        result = subprocess.run(
            ["sudo", "--version"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def is_ci() -> bool:
    """Quick check: are we in CI?"""
    return _is_ci()


def skip_in_ci(reason: str = "Not available in CI environment"):
    """Pytest marker to skip tests that require local machine features.

    Usage:
        @skip_in_ci("Requires macOS Keychain")
        def test_keychain_read(self):
            ...
    """
    import pytest

    return pytest.mark.skipif(
        _is_ci(),
        reason=reason,
    )


def require_macos_keychain():
    """Pytest marker to skip tests that require macOS Keychain."""
    import pytest

    return pytest.mark.skipif(
        not (platform.system() == "Darwin" and _has_security_cli()),
        reason="Requires macOS with Keychain access",
    )
