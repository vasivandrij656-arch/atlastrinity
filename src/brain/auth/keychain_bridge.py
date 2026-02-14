"""Keychain Bridge — Integration with system credential stores.

Supports:
- macOS Keychain (via Security framework / `security` CLI)
- Google Chrome Keychain (cookie extraction for authenticated sessions)
- Browser profiles (Firefox, Safari, Chrome — cookies & saved passwords)
- System Credential Manager (Windows Credential Manager / Linux Secret Service)
- SSH Agent (ssh keys)
- GPG Agent (GPG keys)

All through the unified KeychainBridge interface.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger("brain.auth.keychain")


class KeychainSource(StrEnum):
    """Supported credential sources."""

    MACOS_KEYCHAIN = "macos_keychain"
    CHROME_PASSWORDS = "chrome_passwords"
    CHROME_COOKIES = "chrome_cookies"
    FIREFOX_PASSWORDS = "firefox_passwords"
    SAFARI_PASSWORDS = "safari_passwords"
    SSH_AGENT = "ssh_agent"
    GPG_AGENT = "gpg_agent"
    ENVIRONMENT = "environment"
    DOTENV_FILE = "dotenv_file"
    SYSTEM_CREDENTIAL_STORE = "system_credential_store"


@dataclass
class KeychainEntry:
    """Entry from a credential store."""

    source: KeychainSource
    service: str
    account: str | None = None
    secret: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class KeychainBridge:
    """Universal bridge to system key stores.

    Allows Atlas to retrieve credentials from:
    - macOS Keychain
    - Browser profiles (Chrome, Firefox, Safari)
    - SSH/GPG agents
    - Environment variables
    - .env files

    With FULL ACCESS — Atlas has unrestricted access to ALL credentials
    and can automatically select the right ones for any action.

    Usage:
        bridge = KeychainBridge()
        # Get password from macOS Keychain
        entry = bridge.get_from_macos_keychain("github.com", "user@example.com")

        # Find all credentials for a domain
        entries = bridge.search("github.com")

        # Store a new credential in macOS Keychain
        bridge.store_to_macos_keychain("my-api", "atlas", "secret123")

        # Full scan — find ALL available credentials
        discovered = bridge.discover_all()

        # Fuzzy search
        results = bridge.smart_search("github")
    """

    def __init__(self) -> None:
        from src.brain.auth.ci_compat import detect_ci_environment

        self._is_macos = platform.system() == "Darwin"
        self._is_linux = platform.system() == "Linux"
        self._ci_env = detect_ci_environment()
        self._available_sources = self._detect_available_sources()
        self._discovery_cache: list[KeychainEntry] | None = None

    @property
    def is_ci(self) -> bool:
        """True if running in a CI/CD environment."""
        return self._ci_env.is_ci

    def _detect_available_sources(self) -> set[KeychainSource]:
        """Detect which credential sources are available on this system.

        In CI environments, only env vars and dotenv are reliably available.
        macOS Keychain and browser stores are skipped automatically.
        """
        sources: set[KeychainSource] = {
            KeychainSource.ENVIRONMENT,
            KeychainSource.DOTENV_FILE,
        }

        # In CI, skip interactive/OS-specific credential stores
        if self._ci_env.is_ci:
            logger.info(
                "🔧 CI mode (%s): limiting to env + dotenv sources",
                self._ci_env.provider.value,
            )
            return sources

        if self._is_macos:
            sources.add(KeychainSource.MACOS_KEYCHAIN)
            # Chrome on macOS
            chrome_dir = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
            if chrome_dir.exists():
                sources.add(KeychainSource.CHROME_PASSWORDS)
                sources.add(KeychainSource.CHROME_COOKIES)
            # Safari
            safari_dir = Path.home() / "Library" / "Safari"
            if safari_dir.exists():
                sources.add(KeychainSource.SAFARI_PASSWORDS)
            # Firefox
            firefox_dir = Path.home() / "Library" / "Application Support" / "Firefox" / "Profiles"
            if firefox_dir.exists():
                sources.add(KeychainSource.FIREFOX_PASSWORDS)

        elif self._is_linux:
            sources.add(KeychainSource.SYSTEM_CREDENTIAL_STORE)
            chrome_dir = Path.home() / ".config" / "google-chrome"
            if chrome_dir.exists():
                sources.add(KeychainSource.CHROME_PASSWORDS)
            firefox_dir = Path.home() / ".mozilla" / "firefox"
            if firefox_dir.exists():
                sources.add(KeychainSource.FIREFOX_PASSWORDS)

        # SSH Agent
        if os.getenv("SSH_AUTH_SOCK"):
            sources.add(KeychainSource.SSH_AGENT)

        # GPG Agent
        try:
            result = subprocess.run(
                ["gpg", "--version"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                sources.add(KeychainSource.GPG_AGENT)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        logger.info("🔑 Available keychain sources: %s", [s.value for s in sources])
        return sources

    @property
    def available_sources(self) -> set[KeychainSource]:
        return self._available_sources.copy()

    # ── macOS Keychain ──────────────────────────────────────────────────

    def get_from_macos_keychain(
        self,
        service: str,
        account: str | None = None,
    ) -> KeychainEntry | None:
        """Get credential from macOS Keychain via `security` CLI."""
        if KeychainSource.MACOS_KEYCHAIN not in self._available_sources:
            return None

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
                return KeychainEntry(
                    source=KeychainSource.MACOS_KEYCHAIN,
                    service=service,
                    account=account,
                    secret=secret,
                )
        except subprocess.TimeoutExpired:
            logger.warning("⏰ Keychain access timeout for: %s", service)
        except Exception as e:
            logger.debug("Keychain access failed for %s: %s", service, e)

        return None

    def get_internet_password(
        self,
        server: str,
        account: str | None = None,
        protocol: str | None = None,
    ) -> KeychainEntry | None:
        """Get internet password from macOS Keychain (for websites)."""
        if KeychainSource.MACOS_KEYCHAIN not in self._available_sources:
            return None

        cmd = ["security", "find-internet-password", "-s", server, "-w"]
        if account:
            cmd.insert(-1, "-a")
            cmd.insert(-1, account)
        if protocol:
            cmd.insert(-1, "-r")
            cmd.insert(-1, protocol)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                return KeychainEntry(
                    source=KeychainSource.MACOS_KEYCHAIN,
                    service=server,
                    account=account,
                    secret=result.stdout.strip(),
                    metadata={"password_type": "internet", "protocol": protocol},
                )
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.debug("Internet password access failed for %s: %s", server, e)

        return None

    def store_to_macos_keychain(
        self,
        service: str,
        account: str,
        secret: str,
        *,
        label: str | None = None,
        update_existing: bool = True,
    ) -> bool:
        """Store credential in macOS Keychain."""
        if KeychainSource.MACOS_KEYCHAIN not in self._available_sources:
            return False

        # Delete existing if updating
        if update_existing:
            subprocess.run(
                ["security", "delete-generic-password", "-s", service, "-a", account],
                capture_output=True,
                timeout=10,
                check=False,
            )

        cmd = [
            "security",
            "add-generic-password",
            "-s",
            service,
            "-a",
            account,
            "-w",
            secret,
        ]
        if label:
            cmd.extend(["-l", label])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
            if result.returncode == 0:
                logger.info("✅ Stored to macOS Keychain: %s / %s", service, account)
                return True
            logger.error("❌ Keychain store failed: %s", result.stderr.strip())
        except Exception as e:
            logger.error("❌ Keychain store exception: %s", e)

        return False

    def list_macos_keychain(self, service_filter: str | None = None) -> list[KeychainEntry]:
        """List all macOS Keychain entries (no passwords, metadata only).

        Uses the full-scan parser for correct attribute parsing.
        """
        if KeychainSource.MACOS_KEYCHAIN not in self._available_sources:
            return []

        entries = self._scan_full_keychain()
        if service_filter:
            entries = [
                e for e in entries
                if service_filter.lower() in (e.service or "").lower()
            ]
        return entries

    # ── Environment & Dotenv ────────────────────────────────────────────

    def get_from_env(self, key: str) -> KeychainEntry | None:
        """Get value from an environment variable."""
        value = os.getenv(key)
        if value:
            return KeychainEntry(
                source=KeychainSource.ENVIRONMENT,
                service=key,
                secret=value,
            )
        return None

    def get_from_dotenv(
        self,
        key: str,
        dotenv_path: Path | None = None,
    ) -> KeychainEntry | None:
        """Get value from a .env file."""
        from src.brain.config.config import CONFIG_ROOT

        path = dotenv_path or CONFIG_ROOT / ".env"
        if not path.exists():
            return None

        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    if k.strip() == key:
                        v = v.strip().strip("'\"")
                        return KeychainEntry(
                            source=KeychainSource.DOTENV_FILE,
                            service=key,
                            secret=v,
                            metadata={"file": str(path)},
                        )
        except Exception as e:
            logger.error("Failed to read .env: %s", e)

        return None

    # ── SSH Agent ───────────────────────────────────────────────────────

    def list_ssh_keys(self) -> list[KeychainEntry]:
        """List SSH keys from ssh-agent."""
        if KeychainSource.SSH_AGENT not in self._available_sources:
            return []

        try:
            result = subprocess.run(
                ["ssh-add", "-l"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                return []

            entries = []
            for line in result.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    entries.append(
                        KeychainEntry(
                            source=KeychainSource.SSH_AGENT,
                            service="ssh",
                            account=parts[2] if len(parts) > 2 else None,
                            metadata={
                                "bits": parts[0],
                                "fingerprint": parts[1],
                                "type": parts[-1].strip("()") if parts else None,
                            },
                        )
                    )
            return entries
        except Exception as e:
            logger.error("Failed to list SSH keys: %s", e)
            return []

    # ── GPG Agent ───────────────────────────────────────────────────────

    def list_gpg_keys(self) -> list[KeychainEntry]:
        """List GPG keys."""
        if KeychainSource.GPG_AGENT not in self._available_sources:
            return []

        try:
            result = subprocess.run(
                ["gpg", "--list-keys", "--with-colons"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                return []

            entries = []
            for line in result.stdout.splitlines():
                if line.startswith("uid:"):
                    fields = line.split(":")
                    uid = fields[9] if len(fields) > 9 else ""
                    entries.append(
                        KeychainEntry(
                            source=KeychainSource.GPG_AGENT,
                            service="gpg",
                            account=uid,
                            metadata={"trust": fields[1] if len(fields) > 1 else ""},
                        )
                    )
            return entries
        except Exception as e:
            logger.error("Failed to list GPG keys: %s", e)
            return []

    # ── Universal Search ────────────────────────────────────────────────

    def search(
        self,
        query: str,
        sources: set[KeychainSource] | None = None,
    ) -> list[KeychainEntry]:
        """Universal credential search across all available sources.

        Args:
            query: Search query (domain, service, name)
            sources: Limit search to specific sources (None = all)
        """
        target_sources = sources or self._available_sources
        results: list[KeychainEntry] = []

        if KeychainSource.MACOS_KEYCHAIN in target_sources:
            # Keychain: search by service
            entry = self.get_from_macos_keychain(query)
            if entry:
                results.append(entry)
            # Internet password
            entry = self.get_internet_password(query)
            if entry:
                results.append(entry)

        if KeychainSource.ENVIRONMENT in target_sources:
            # Env: search by direct key name or common patterns
            patterns = [
                query.upper().replace(".", "_").replace("-", "_"),
                f"{query.upper().replace('.', '_')}_API_KEY",
                f"{query.upper().replace('.', '_')}_TOKEN",
            ]
            for pattern in patterns:
                entry = self.get_from_env(pattern)
                if entry:
                    results.append(entry)

        if KeychainSource.DOTENV_FILE in target_sources:
            # Dotenv: search by key patterns
            patterns = [
                query.upper().replace(".", "_").replace("-", "_"),
                f"{query.upper().replace('.', '_')}_API_KEY",
                f"{query.upper().replace('.', '_')}_TOKEN",
            ]
            for pattern in patterns:
                entry = self.get_from_dotenv(pattern)
                if entry:
                    results.append(entry)

        return results

    def get_credential_for_domain(self, domain: str) -> KeychainEntry | None:
        """Find the best credential for a given domain.

        Priority:
        1. macOS Keychain internet password
        2. macOS Keychain generic password
        3. Environment variable
        4. .env file
        """
        results = self.search(domain)
        if results:
            # Priority: macOS Keychain > Env > Dotenv
            priority = {
                KeychainSource.MACOS_KEYCHAIN: 0,
                KeychainSource.CHROME_PASSWORDS: 1,
                KeychainSource.SAFARI_PASSWORDS: 2,
                KeychainSource.ENVIRONMENT: 3,
                KeychainSource.DOTENV_FILE: 4,
            }
            results.sort(key=lambda e: priority.get(e.source, 99))
            return results[0]
        return None

    # ── Full Discovery (FULL ACCESS mode) ───────────────────────────────

    def discover_all(self, *, force_refresh: bool = False) -> list[KeychainEntry]:
        """Full scan of ALL available credential stores.

        Collects ALL entries from macOS Keychain, .env, SSH, GPG.
        Uses cache for fast repeated access.

        Args:
            force_refresh: Force re-scan (ignore cache)

        Returns:
            Complete list of all found credentials (no passwords for keychain,
            with passwords for .env)
        """
        if self._discovery_cache is not None and not force_refresh:
            return self._discovery_cache.copy()

        all_entries: list[KeychainEntry] = []

        # 1. macOS Keychain — all entries
        if KeychainSource.MACOS_KEYCHAIN in self._available_sources:
            keychain_entries = self._scan_full_keychain()
            all_entries.extend(keychain_entries)
            logger.info("🔑 Keychain: found %d entries", len(keychain_entries))

        # 2. Environment variables — all that look like secrets
        env_entries = self._scan_environment()
        all_entries.extend(env_entries)
        logger.info("🔑 Environment: found %d entries", len(env_entries))

        # 3. .env file — all entries
        dotenv_entries = self._scan_dotenv()
        all_entries.extend(dotenv_entries)
        logger.info("🔑 .env file: found %d entries", len(dotenv_entries))

        # 4. SSH keys
        ssh_entries = self.list_ssh_keys()
        all_entries.extend(ssh_entries)

        # 5. GPG keys
        gpg_entries = self.list_gpg_keys()
        all_entries.extend(gpg_entries)

        self._discovery_cache = all_entries
        logger.info(
            "🔓 Full Discovery: found %d credentials across all sources",
            len(all_entries),
        )
        return all_entries.copy()

    def invalidate_cache(self) -> None:
        """Clear the discovery cache."""
        self._discovery_cache = None

    def _scan_full_keychain(self) -> list[KeychainEntry]:
        """Scan macOS Keychain and collect ALL entries with metadata.

        Parses `security dump-keychain` output to extract:
        - Service name (svce / srvr)
        - Account (acct)
        - Type (class: genp/inet)
        - Label (0x00000007 / labl)
        - Creation date (cdat)
        """
        if not self._is_macos:
            return []

        try:
            result = subprocess.run(
                ["security", "dump-keychain"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                return []

            entries: list[KeychainEntry] = []
            current: dict[str, str] = {}
            current_class: str = ""

            for line in result.stdout.splitlines():
                stripped = line.strip()

                # New entry starts with "class:"
                if stripped.startswith("class:"):
                    # Save previous entry
                    if current.get("svce") or current.get("srvr"):
                        service = current.get("svce") or current.get("srvr", "")
                        service = self._clean_keychain_value(service)
                        account = self._clean_keychain_value(
                            current.get("acct", "")
                        )

                        if service:  # Skip entries with empty service
                            entries.append(
                                KeychainEntry(
                                    source=KeychainSource.MACOS_KEYCHAIN,
                                    service=service,
                                    account=account or None,
                                    metadata={
                                        "class": current_class,
                                        "label": self._clean_keychain_value(
                                            current.get("labl", current.get("0x00000007", ""))
                                        ),
                                        "created": current.get("cdat", ""),
                                        "modified": current.get("mdat", ""),
                                    },
                                )
                            )
                    current = {}
                    # Parse class name: 'class: "genp"' or 'class: 0x00000010'
                    class_part = stripped.split(":", 1)[1].strip().strip('"')
                    current_class = class_part

                # Parse keychain attributes in format:
                #   "key"<type>="value"   (e.g. "svce"<blob>="Chrome Safe Storage")
                #   "key"<type>=<NULL>
                #   0x00000007 <blob>="Label Value"
                elif '"' in stripped and "=" in stripped:
                    # Format: "svce"<blob>="Chrome Safe Storage"
                    # Match: "key"<type>=value
                    m = re.match(r'"(\w+)"<[^>]+>=(.+)', stripped)
                    if m:
                        key = m.group(1)
                        raw_value = m.group(2).strip()
                        if raw_value == "<NULL>":
                            value = ""
                        elif raw_value.startswith('"') and raw_value.endswith('"'):
                            value = raw_value.strip('"')
                        elif raw_value.startswith("0x"):
                            # Hex-encoded: extract the readable part after the hex
                            readable_match = re.search(r'"([^"]*)"', stripped)
                            if readable_match:
                                value = readable_match.group(1)
                            else:
                                value = raw_value
                        else:
                            value = raw_value
                        current[key] = value
                    else:
                        # Format: 0x00000007 <blob>="Label Value"
                        m2 = re.match(r'(0x[0-9a-fA-F]+)\s+<[^>]+>=(.+)', stripped)
                        if m2:
                            key = m2.group(1)
                            raw_value = m2.group(2).strip()
                            if raw_value.startswith('"') and raw_value.endswith('"'):
                                current[key] = raw_value.strip('"')
                            elif raw_value != "<NULL>":
                                current[key] = raw_value

            # Don't forget last entry
            if current.get("svce") or current.get("srvr"):
                service = current.get("svce") or current.get("srvr", "")
                service = self._clean_keychain_value(service)
                account = self._clean_keychain_value(current.get("acct", ""))
                if service:
                    entries.append(
                        KeychainEntry(
                            source=KeychainSource.MACOS_KEYCHAIN,
                            service=service,
                            account=account or None,
                            metadata={
                                "class": current_class,
                                "label": self._clean_keychain_value(
                                    current.get("labl", current.get("0x00000007", ""))
                                ),
                                "created": current.get("cdat", ""),
                            },
                        )
                    )

            return entries

        except Exception as e:
            logger.error("❌ Full keychain scan failed: %s", e)
            return []

    def _scan_environment(self) -> list[KeychainEntry]:
        """Scan environment variables looking for secrets.

        Searches for variables with keywords:
        KEY, TOKEN, SECRET, PASSWORD, API, AUTH, CREDENTIAL
        """
        secret_patterns = {
            "KEY", "TOKEN", "SECRET", "PASSWORD", "API",
            "AUTH", "CREDENTIAL", "PASS", "PWD",
        }

        entries: list[KeychainEntry] = []
        for key, value in os.environ.items():
            key_upper = key.upper()
            if any(p in key_upper for p in secret_patterns):
                # Skip obviously non-secret system vars
                if key_upper in {
                    "SSH_AUTH_SOCK", "GPG_AGENT_INFO",
                    "TERM", "PATH", "HOME", "USER", "SHELL",
                    "LANG", "LC_ALL", "DISPLAY",
                    "XDG_CACHE_HOME", "XDG_CONFIG_HOME",
                    "CONFIG_ROOT", "ANONYMIZED_TELEMETRY",
                    "CHROMA_TELEMETRY_ENABLED",
                    "LANGCHAIN_TRACING_V2",
                }:
                    continue

                entries.append(
                    KeychainEntry(
                        source=KeychainSource.ENVIRONMENT,
                        service=key,
                        secret=value,
                        metadata={"env_key": key},
                    )
                )

        return entries

    def _scan_dotenv(self) -> list[KeychainEntry]:
        """Scan ALL entries from .env file."""
        from src.brain.config.config import CONFIG_ROOT

        path = CONFIG_ROOT / ".env"
        if not path.exists():
            return []

        entries: list[KeychainEntry] = []
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line or not line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    if key and value:
                        entries.append(
                            KeychainEntry(
                                source=KeychainSource.DOTENV_FILE,
                                service=key,
                                secret=value,
                                metadata={"file": str(path), "env_key": key},
                            )
                        )
        except Exception as e:
            logger.error("Failed to scan .env: %s", e)

        return entries

    @staticmethod
    def _clean_keychain_value(value: str) -> str:
        """Clean a value from keychain dump.

        Handles hex-encoded strings like 0x12AB... and removes extra quotes.
        """
        if not value:
            return ""
        value = value.strip().strip('"')
        # Handle hex-encoded values like 0x12AB...
        if value.startswith("0x") and all(
            c in "0123456789abcdefABCDEF" for c in value[2:]
        ):
            try:
                return bytes.fromhex(value[2:]).decode("utf-8", errors="replace")
            except (ValueError, UnicodeDecodeError):
                pass
        # Handle <NULL> placeholders
        if value == "<NULL>":
            return ""
        return value

    # ── Smart Search (fuzzy + category-aware) ───────────────────────────

    def smart_search(
        self,
        query: str,
        *,
        category: str | None = None,
    ) -> list[KeychainEntry]:
        """Smart search across all credentials with fuzzy matching.

        Unlike search(), searches all sources simultaneously,
        including the full keychain dump, and supports partial matches.

        Args:
            query: Search query (partial name, domain, account)
            category: Filter by category (api_key, ide_token, etc.)
        """
        query_lower = query.lower()
        all_entries = self.discover_all()

        results: list[KeychainEntry] = []
        for entry in all_entries:
            # Match against service, account, label
            searchable = " ".join(
                filter(None, [
                    entry.service,
                    entry.account,
                    entry.metadata.get("label", ""),
                    entry.metadata.get("env_key", ""),
                ])
            ).lower()

            if query_lower in searchable:
                # Category filter
                if category:
                    from src.brain.auth.access_policy import (
                        CredentialCategory,
                        categorize_credential,
                    )
                    cat, _ = categorize_credential(entry.service, entry.account)
                    try:
                        target_cat = CredentialCategory(category)
                        if cat != target_cat:
                            continue
                    except ValueError:
                        pass

                results.append(entry)

        return results

    def get_all_api_keys(self) -> list[KeychainEntry]:
        """Return all found API keys from .env and environment."""
        from src.brain.auth.access_policy import CredentialCategory, categorize_credential

        all_entries = self.discover_all()
        return [
            e for e in all_entries
            if categorize_credential(e.service, e.account)[0]
            in {CredentialCategory.API_KEY, CredentialCategory.AI_TOKEN}
        ]

    def get_all_ide_tokens(self) -> list[KeychainEntry]:
        """Return all IDE tokens (Copilot, Windsurf, Cursor, etc.)."""
        from src.brain.auth.access_policy import CredentialCategory, categorize_credential

        all_entries = self.discover_all()
        return [
            e for e in all_entries
            if categorize_credential(e.service, e.account)[0]
            == CredentialCategory.IDE_TOKEN
        ]

    def get_all_ai_tokens(self) -> list[KeychainEntry]:
        """Return all AI-related tokens (ChatGPT, Claude, etc.)."""
        from src.brain.auth.access_policy import CredentialCategory, categorize_credential

        all_entries = self.discover_all()
        return [
            e for e in all_entries
            if categorize_credential(e.service, e.account)[0]
            == CredentialCategory.AI_TOKEN
        ]

    def get_google_credentials(self) -> list[KeychainEntry]:
        """Return all Google-related credentials (accounts, API keys, etc.)."""
        return self.smart_search("google")

    def get_credential_with_secret(
        self,
        service: str,
        account: str | None = None,
    ) -> KeychainEntry | None:
        """Get credential WITH the actual secret (password/token).

        Tries macOS Keychain (generic + internet password),
        then .env, then environment.
        """
        # 1. macOS Keychain — generic password
        entry = self.get_from_macos_keychain(service, account)
        if entry and entry.secret:
            return entry

        # 2. macOS Keychain — internet password
        entry = self.get_internet_password(service, account)
        if entry and entry.secret:
            return entry

        # 3. .env file
        entry = self.get_from_dotenv(service)
        if entry and entry.secret:
            return entry

        # 4. Environment
        entry = self.get_from_env(service)
        if entry and entry.secret:
            return entry

        # 5. Fuzzy search across discovery cache
        results = self.smart_search(service)
        for r in results:
            if r.secret:
                return r

        return None

    def bulk_export(self) -> dict[str, list[dict[str, Any]]]:
        """Export metadata of all credentials grouped by source.

        Does NOT include secrets — only service, account, metadata.
        For audit and review purposes.
        """
        all_entries = self.discover_all()
        grouped: dict[str, list[dict[str, Any]]] = {}

        for entry in all_entries:
            source = entry.source.value
            if source not in grouped:
                grouped[source] = []
            grouped[source].append({
                "service": entry.service,
                "account": entry.account,
                "has_secret": bool(entry.secret),
                "metadata": {
                    k: v for k, v in entry.metadata.items()
                    if k != "raw"  # Exclude raw dump data
                },
            })

        return grouped
