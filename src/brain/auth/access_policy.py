"""Access Policy — Defines Atlas access level to system key stores.

Access levels:
- FULL:       Atlas has full access to any credentials in Keychain,
              .env, browser storage, etc. Can automatically select and
              use any secrets for any actions.
- RESTRICTED: Atlas can only use allowed credentials
              (via whitelist/blacklist).
- NONE:       Atlas has no access to system key stores.

Policy is set via:
1. Env var: ATLAS_KEYCHAIN_ACCESS=full|restricted|none
2. config.yaml -> auth.access_policy.level
3. Programmatically via set_policy()
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger("brain.auth.policy")


class AccessLevel(StrEnum):
    """Atlas access level to key stores."""

    FULL = "full"
    RESTRICTED = "restricted"
    NONE = "none"


class CredentialCategory(StrEnum):
    """Credential category by purpose."""

    API_KEY = "api_key"
    OAUTH_TOKEN = "oauth_token"
    PASSWORD = "password"
    SSH_KEY = "ssh_key"
    GPG_KEY = "gpg_key"
    CERTIFICATE = "certificate"
    COOKIE = "cookie"
    BROWSER_STORAGE = "browser_storage"
    WIFI_PASSWORD = "wifi_password"
    CLOUD_ACCOUNT = "cloud_account"
    IDE_TOKEN = "ide_token"
    AI_TOKEN = "ai_token"
    CUSTOM = "custom"


@dataclass
class DiscoveredCredential:
    """Credential found during auto-discovery."""

    service: str
    account: str | None
    category: CredentialCategory
    source: str  # keychain, env, dotenv, etc.
    has_secret: bool  # True if secret is accessible (not just metadata)
    metadata: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0  # 0.0–1.0, how confident in the category


# ── Well-known service patterns for categorization ──────────────────────

_CATEGORY_PATTERNS: dict[CredentialCategory, list[str]] = {
    CredentialCategory.API_KEY: [
        "api_key", "apikey", "api-key", "_key",
        "google_maps", "openrouter", "mistral",
        "sendgrid", "stripe", "twilio", "aws_",
    ],
    CredentialCategory.OAUTH_TOKEN: [
        "oauth", "access_token", "refresh_token",
        "bearer", "jwt",
    ],
    CredentialCategory.IDE_TOKEN: [
        "copilot", "windsurf", "cursor", "code safe storage",
        "fleet", "intellij", "vscode", "goose",
    ],
    CredentialCategory.AI_TOKEN: [
        "openai", "chatgpt", "claude", "anthropic",
        "gemini", "mistral", "openrouter", "perplexity",
        "grok", "deepseek", "together", "replicate",
    ],
    CredentialCategory.CLOUD_ACCOUNT: [
        "google", "icloud", "apple", "microsoft",
        "azure", "aws", "gcp", "firebase", "supabase",
    ],
    CredentialCategory.PASSWORD: [
        "password", "passwd", "login",
    ],
    CredentialCategory.SSH_KEY: [
        "ssh", "id_rsa", "id_ed25519",
    ],
    CredentialCategory.GPG_KEY: [
        "gpg", "pgp",
    ],
    CredentialCategory.CERTIFICATE: [
        "cert", "certificate", "x509", "pkcs",
        "ssl", "tls",
    ],
    CredentialCategory.WIFI_PASSWORD: [
        "airport", "wifi", "wpa", "ssid",
    ],
    CredentialCategory.BROWSER_STORAGE: [
        "chrome safe storage", "firefox", "safari",
        "brave", "edge", "opera",
    ],
    CredentialCategory.COOKIE: [
        "cookie", "session", "csrf",
    ],
}


def categorize_credential(
    service: str,
    account: str | None = None,
) -> tuple[CredentialCategory, float]:
    """Determines credential category by service name and account.

    Returns:
        (category, confidence) — category and confidence level 0.0–1.0
    """
    combined = f"{service} {account or ''}".lower()

    best_category = CredentialCategory.CUSTOM
    best_score = 0.0

    for category, patterns in _CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if pattern in combined:
                # Longer pattern match = higher confidence
                score = len(pattern) / max(len(combined), 1)
                # Boost for exact service match
                if pattern in service.lower():
                    score = min(score + 0.3, 1.0)
                if score > best_score:
                    best_score = score
                    best_category = category

    # Default confidence if nothing matched
    if best_score == 0.0:
        best_score = 0.1

    return best_category, min(best_score, 1.0)


@dataclass
class AccessPolicy:
    """Atlas access policy to key stores.

    Defines what Atlas can do with credentials:
    - Which categories are allowed
    - Which specific services are in whitelist / blacklist
    - Whether auto-import, auto-discover, auto-use are permitted
    """

    level: AccessLevel = AccessLevel.NONE

    # FULL mode: Atlas can use EVERYTHING
    # RESTRICTED mode: only allowed categories / services
    allowed_categories: set[CredentialCategory] = field(default_factory=set)
    blocked_categories: set[CredentialCategory] = field(default_factory=set)

    # Whitelist/blacklist of specific services
    allowed_services: set[str] = field(default_factory=set)  # if not empty, only these
    blocked_services: set[str] = field(default_factory=set)  # always block these

    # Operations
    can_auto_discover: bool = False   # Automatic scanning of all stores
    can_auto_import: bool = False     # Automatic import into vault
    can_auto_use: bool = False        # Automatic use without prompting
    can_store: bool = False           # Can store new credentials
    can_delete: bool = False          # Can delete credentials
    can_export: bool = False          # Can export credentials

    def is_credential_allowed(
        self,
        service: str,
        category: CredentialCategory | None = None,
    ) -> bool:
        """Checks if access to a specific credential is allowed."""
        if self.level == AccessLevel.NONE:
            return False

        if self.level == AccessLevel.FULL:
            # FULL: everything allowed, except blocked
            if service.lower() in {s.lower() for s in self.blocked_services}:
                return False
            return not (category and category in self.blocked_categories)

        # RESTRICTED
        if service.lower() in {s.lower() for s in self.blocked_services}:
            return False

        if self.allowed_services:
            if service.lower() not in {s.lower() for s in self.allowed_services}:
                return False

        if category:
            if self.blocked_categories and category in self.blocked_categories:
                return False
            if self.allowed_categories and category not in self.allowed_categories:
                return False

        return True

    @property
    def is_full_access(self) -> bool:
        return self.level == AccessLevel.FULL

    @property
    def is_restricted(self) -> bool:
        return self.level == AccessLevel.RESTRICTED

    @property
    def is_disabled(self) -> bool:
        return self.level == AccessLevel.NONE


def load_access_policy(config: dict[str, Any] | None = None) -> AccessPolicy:
    """Loads Access Policy from env var + config.

    Priority:
    1. ATLAS_KEYCHAIN_ACCESS env var (highest)
    2. config.yaml -> auth.access_policy
    3. Default = NONE (safe by default)
    """
    # 1. Env var — highest priority
    env_level = os.getenv("ATLAS_KEYCHAIN_ACCESS", "").strip().lower()

    # 2. Config fallback
    cfg = (config or {}).get("auth", {}).get("access_policy", {})
    config_level = cfg.get("level", "").strip().lower()

    # Determine level
    level_str = env_level or config_level or "none"
    try:
        level = AccessLevel(level_str)
    except ValueError:
        logger.warning("⚠️ Unknown access level '%s', falling back to NONE", level_str)
        level = AccessLevel.NONE

    # Build policy
    policy = AccessPolicy(level=level)

    if level == AccessLevel.FULL:
        # FULL ACCESS — everything allowed
        policy.can_auto_discover = True
        policy.can_auto_import = True
        policy.can_auto_use = True
        policy.can_store = True
        policy.can_delete = True
        policy.can_export = True
        logger.info(
            "\ud83d\udd13 Access Policy: FULL — Atlas has full access to all credentials"
        )
    elif level == AccessLevel.RESTRICTED:
        # Restricted — read whitelist/blacklist from config
        policy.allowed_categories = {
            CredentialCategory(c)
            for c in cfg.get("allowed_categories", [])
            if c in CredentialCategory.__members__.values()
        }
        policy.blocked_categories = {
            CredentialCategory(c)
            for c in cfg.get("blocked_categories", [])
            if c in CredentialCategory.__members__.values()
        }
        policy.allowed_services = set(cfg.get("allowed_services", []))
        policy.blocked_services = set(cfg.get("blocked_services", []))
        policy.can_auto_discover = cfg.get("can_auto_discover", True)
        policy.can_auto_import = cfg.get("can_auto_import", False)
        policy.can_auto_use = cfg.get("can_auto_use", False)
        policy.can_store = cfg.get("can_store", True)
        policy.can_delete = cfg.get("can_delete", False)
        policy.can_export = cfg.get("can_export", False)
        logger.info(
            "🔒 Access Policy: RESTRICTED — limited access (categories=%s, services=%s)",
            [c.value for c in policy.allowed_categories],
            list(policy.allowed_services),
        )
    else:
        logger.info("🚫 Access Policy: NONE — access to key stores disabled")

    # Blocked services (applied at ALL levels)
    extra_blocked = set(cfg.get("blocked_services", []))
    if extra_blocked:
        policy.blocked_services.update(extra_blocked)

    return policy
