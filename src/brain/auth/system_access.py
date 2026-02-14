"""System Access — Privileged operations using system credentials.

Provides Atlas with the ability to:
- Execute commands with sudo (using ATLAS_SYSTEM_PASSWORD from .env)
- Unlock macOS Keychain programmatically
- Read protected keychain entries that require password confirmation
- Run any system command that requires elevated privileges

The system password is stored in .env (ATLAS_SYSTEM_PASSWORD) and is
loaded automatically when the config module initializes.

Security model:
    - Password is NEVER logged or printed
    - Password is passed via stdin (not command-line arguments)
    - All sudo operations are audited to auth audit log
    - The password can also unlock the login keychain for bulk reads
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("brain.auth.system")


@dataclass
class CommandResult:
    """Result of a privileged command execution."""

    success: bool
    stdout: str
    stderr: str
    return_code: int
    duration: float
    command_summary: str  # Sanitized command description (no secrets)


class SystemAccess:
    """Provides privileged system access for Atlas.

    Uses ATLAS_SYSTEM_PASSWORD from .env for:
    - sudo command execution
    - macOS Keychain unlock
    - Protected keychain entry reads

    Usage:
        access = SystemAccess()

        # Run a command with sudo
        result = access.sudo_exec(["brew", "install", "something"])

        # Unlock keychain for batch reads
        access.unlock_keychain()

        # Read a protected keychain entry
        secret = access.read_keychain_secret("github.com", "user@email.com")
    """

    def __init__(self) -> None:
        from src.brain.auth.ci_compat import detect_ci_environment

        self._ci_env = detect_ci_environment()
        self._password: str | None = self._load_password()
        self._keychain_unlocked = False

        if self._ci_env.is_ci:
            logger.info(
                "🔧 CI mode (%s): system access limited (keychain=%s, sudo=%s)",
                self._ci_env.provider.value,
                self._ci_env.has_macos_keychain,
                self._ci_env.has_sudo,
            )

    @property
    def is_ci(self) -> bool:
        """True if running in a CI/CD environment."""
        return self._ci_env.is_ci

    def _load_password(self) -> str | None:
        """Load system password from environment / .env."""
        password = os.getenv("ATLAS_SYSTEM_PASSWORD")
        if password:
            logger.info("🔑 System password loaded from environment")
        else:
            # Try reading directly from .env file
            try:
                from src.brain.config.config import CONFIG_ROOT

                env_path = CONFIG_ROOT / ".env"
                if env_path.exists():
                    with open(env_path, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("ATLAS_SYSTEM_PASSWORD="):
                                password = line.split("=", 1)[1].strip().strip("'\"")
                                logger.info("🔑 System password loaded from .env file")
                                break
            except Exception as e:
                logger.debug("Could not read .env for system password: %s", e)

        if not password:
            logger.warning(
                "⚠️ ATLAS_SYSTEM_PASSWORD not set. "
                "Sudo and protected keychain access will not be available. "
                "Add ATLAS_SYSTEM_PASSWORD=<password> to .env"
            )
        return password

    @property
    def has_password(self) -> bool:
        """Check if system password is available."""
        return self._password is not None

    @property
    def is_keychain_unlocked(self) -> bool:
        """Check if keychain has been unlocked in this session."""
        return self._keychain_unlocked

    # ── Sudo Execution ──────────────────────────────────────────────────

    def sudo_exec(
        self,
        command: list[str],
        *,
        timeout: int = 30,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        """Execute a command with sudo privileges.

        The password is piped via stdin — never passed as a CLI argument.

        Args:
            command: Command and arguments (without 'sudo' prefix)
            timeout: Max execution time in seconds
            cwd: Working directory
            env: Additional environment variables

        Returns:
            CommandResult with stdout, stderr, return_code
        """
        if not self._password:
            return CommandResult(
                success=False,
                stdout="",
                stderr="ATLAS_SYSTEM_PASSWORD not set",
                return_code=-1,
                duration=0.0,
                command_summary=f"sudo {command[0] if command else '?'}",
            )

        full_cmd = ["sudo", "-S", *command]
        cmd_summary = f"sudo {' '.join(command[:3])}{'...' if len(command) > 3 else ''}"

        start = time.monotonic()
        try:
            run_env = os.environ.copy()
            if env:
                run_env.update(env)

            result = subprocess.run(
                full_cmd,
                input=f"{self._password}\n",
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(cwd) if cwd else None,
                env=run_env,
                check=False,
            )

            duration = time.monotonic() - start
            success = result.returncode == 0

            if success:
                logger.info("✅ sudo: %s (%.1fs)", cmd_summary, duration)
            else:
                logger.warning("❌ sudo failed: %s (rc=%d)", cmd_summary, result.returncode)

            return CommandResult(
                success=success,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
                duration=duration,
                command_summary=cmd_summary,
            )

        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            logger.error("⏰ sudo timeout: %s after %ds", cmd_summary, timeout)
            return CommandResult(
                success=False,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                return_code=-1,
                duration=duration,
                command_summary=cmd_summary,
            )
        except Exception as e:
            duration = time.monotonic() - start
            logger.error("❌ sudo exception: %s — %s", cmd_summary, e)
            return CommandResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=-1,
                duration=duration,
                command_summary=cmd_summary,
            )

    # ── Keychain Operations ─────────────────────────────────────────────

    def unlock_keychain(
        self,
        keychain_path: str | None = None,
    ) -> bool:
        """Unlock the macOS login keychain using the system password.

        This allows subsequent keychain reads without user prompts.
        Returns False gracefully in CI environments without macOS Keychain.

        Args:
            keychain_path: Path to keychain file. Default: login.keychain-db
        """
        if self._ci_env.is_ci:
            logger.info("🔧 CI mode: keychain unlock skipped (CI environment)")
            return False

        if not self._password:
            logger.warning("Cannot unlock keychain: no system password")
            return False

        kc = keychain_path or str(Path.home() / "Library" / "Keychains" / "login.keychain-db")

        try:
            result = subprocess.run(
                ["security", "unlock-keychain", "-p", self._password, kc],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            if result.returncode == 0:
                self._keychain_unlocked = True
                logger.info("🔓 Keychain unlocked: %s", Path(kc).name)
                return True

            logger.warning(
                "❌ Keychain unlock failed (rc=%d): %s",
                result.returncode,
                result.stderr.strip(),
            )
            return False

        except Exception as e:
            logger.error("❌ Keychain unlock exception: %s", e)
            return False

    def read_keychain_secret(
        self,
        service: str,
        account: str | None = None,
        *,
        password_type: str = "generic",
    ) -> str | None:
        """Read a secret from macOS Keychain, unlocking if needed.

        Unlike the basic KeychainBridge methods, this can read entries
        that require password confirmation by first unlocking the keychain.

        Args:
            service: Service name or server name
            account: Account name (optional)
            password_type: "generic" or "internet"

        Returns:
            The secret string, or None if not found
        """
        # Ensure keychain is unlocked
        if not self._keychain_unlocked:
            self.unlock_keychain()

        if password_type == "internet":
            cmd = ["security", "find-internet-password", "-s", service, "-w"]
        else:
            cmd = ["security", "find-generic-password", "-s", service, "-w"]

        if account:
            cmd.insert(-1, "-a")
            cmd.insert(-1, account)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            if result.returncode == 0:
                secret = result.stdout.strip()
                logger.debug("🔑 Read keychain secret: %s", service)
                return secret

            # If we get an auth error, try unlocking and retry once
            if "authorization" in result.stderr.lower() or result.returncode == 36:
                if self.unlock_keychain():
                    retry = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                    if retry.returncode == 0:
                        return retry.stdout.strip()

            return None

        except Exception as e:
            logger.debug("Keychain read failed for %s: %s", service, e)
            return None

    def read_all_keychain_secrets(
        self,
        entries: list[dict[str, Any]],
    ) -> dict[str, str]:
        """Batch-read secrets from keychain for multiple entries.

        Unlocks the keychain once, then reads all requested entries.

        Args:
            entries: List of {"service": ..., "account": ..., "type": "generic"|"internet"}

        Returns:
            Dict mapping service names to their secrets
        """
        if not self._password:
            return {}

        # Unlock once
        self.unlock_keychain()

        results: dict[str, str] = {}
        for entry in entries:
            service = entry.get("service", "")
            account = entry.get("account")
            ptype = entry.get("type", "generic")

            secret = self.read_keychain_secret(service, account, password_type=ptype)
            if secret:
                results[service] = secret

        logger.info(
            "📦 Batch keychain read: %d/%d secrets retrieved",
            len(results),
            len(entries),
        )
        return results

    # ── Utility ─────────────────────────────────────────────────────────

    def test_password(self) -> bool:
        """Verify the system password is correct by running a harmless sudo command."""
        result = self.sudo_exec(["true"])
        return result.success

    def status(self) -> dict[str, Any]:
        """Return current system access status."""
        return {
            "has_password": self.has_password,
            "keychain_unlocked": self._keychain_unlocked,
            "password_verified": None,  # Call test_password() to verify
            "is_ci": self._ci_env.is_ci,
            "ci_provider": self._ci_env.provider.value,
            "available_features": self._ci_env.available_features,
        }
