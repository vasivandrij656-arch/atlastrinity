"""Credential Vault — Encrypted storage for tokens and credentials.

Stores all secrets in encrypted form (Fernet/AES-256).
Supports TTL, auto-refresh, versioning, and access audit.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger("brain.auth.vault")


@dataclass
class Credential:
    """Universal structure for storing credentials."""

    service: str  # Service identifier (arbitrary)
    credential_type: str  # oauth2, api_key, bearer, basic, cookie, certificate, custom
    data: dict[str, Any]  # Payload (client_id, secret, tokens, etc.)
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None  # Unix timestamp, None = never expires
    auto_refresh: bool = False
    refresh_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    version: int = 1

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    @property
    def ttl_seconds(self) -> float | None:
        if self.expires_at is None:
            return None
        remaining = self.expires_at - time.time()
        return max(0.0, remaining)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Credential:
        return cls(**d)


class CredentialVault:
    """Encrypted storage for all Atlas credentials.

    Uses Fernet (AES-128-CBC with HMAC) for encryption.
    Stored at ~/.config/atlastrinity/auth/vault.enc

    Usage:
        vault = CredentialVault()
        vault.store("github", "oauth2", {"access_token": "xxx", "refresh_token": "yyy"})
        cred = vault.get("github")
        vault.delete("github")
    """

    def __init__(self, vault_dir: Path | None = None) -> None:
        from src.brain.config.config import CONFIG_ROOT

        self._vault_dir = vault_dir or CONFIG_ROOT / "auth"
        self._vault_dir.mkdir(parents=True, exist_ok=True)
        self._vault_file = self._vault_dir / "vault.enc"
        self._key_file = self._vault_dir / ".vault_key"
        self._audit_file = self._vault_dir / "audit.log"

        # Restrict permissions (owner-only)
        try:
            os.chmod(self._vault_dir, 0o700)
        except OSError:
            pass

        self._fernet = self._init_encryption()
        self._credentials: dict[str, Credential] = {}
        self._load()

    # ── Encryption ──────────────────────────────────────────────────────

    def _init_encryption(self) -> Fernet:
        """Initialize or load the encryption key."""
        # 1. Try from env
        env_key = os.getenv("ATLAS_VAULT_KEY")
        if env_key:
            return Fernet(env_key.encode())

        # 2. Load from file
        if self._key_file.exists():
            key = self._key_file.read_bytes().strip()
            return Fernet(key)

        # 3. Generate new key
        key = Fernet.generate_key()
        self._key_file.write_bytes(key)
        try:
            os.chmod(self._key_file, 0o600)
        except OSError:
            pass
        logger.info("🔐 Vault key generated: %s", self._key_file)
        return Fernet(key)

    def _encrypt(self, data: str) -> bytes:
        return self._fernet.encrypt(data.encode("utf-8"))

    def _decrypt(self, data: bytes) -> str:
        return self._fernet.decrypt(data).decode("utf-8")

    # ── Storage ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load vault from disk."""
        if not self._vault_file.exists():
            self._credentials = {}
            return

        try:
            encrypted = self._vault_file.read_bytes()
            decrypted = self._decrypt(encrypted)
            raw = json.loads(decrypted)
            self._credentials = {k: Credential.from_dict(v) for k, v in raw.items()}
            logger.info("🔓 Vault loaded: %d credentials", len(self._credentials))
        except (InvalidToken, json.JSONDecodeError, KeyError) as e:
            logger.error("❌ Vault corrupted or wrong key: %s", e)
            self._credentials = {}

    def _save(self) -> None:
        """Save vault to disk."""
        raw = {k: v.to_dict() for k, v in self._credentials.items()}
        data = json.dumps(raw, ensure_ascii=False, indent=None)
        encrypted = self._encrypt(data)
        self._vault_file.write_bytes(encrypted)
        try:
            os.chmod(self._vault_file, 0o600)
        except OSError:
            pass

    def _audit(self, action: str, service: str, details: str = "") -> None:
        """Write access audit log entry."""
        entry = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {action} | {service} | {details}\n"
        with open(self._audit_file, "a", encoding="utf-8") as f:
            f.write(entry)

    # ── CRUD ────────────────────────────────────────────────────────────

    def store(
        self,
        service: str,
        credential_type: str,
        data: dict[str, Any],
        *,
        expires_in: float | None = None,
        auto_refresh: bool = False,
        refresh_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Credential:
        """Store a credential for a service.

        Args:
            service: Unique identifier (e.g. "data.gov.ua", "github", "custom_api")
            credential_type: Type (oauth2, api_key, bearer, basic, cookie, certificate, custom)
            data: Credential payload
            expires_in: TTL in seconds (None = never expires)
            auto_refresh: Whether auto-refresh is needed
            refresh_url: URL for token refresh
            metadata: Additional information
        """
        expires_at = (time.time() + expires_in) if expires_in else None

        # Version bump if updating
        version = 1
        if service in self._credentials:
            version = self._credentials[service].version + 1

        cred = Credential(
            service=service,
            credential_type=credential_type,
            data=data,
            expires_at=expires_at,
            auto_refresh=auto_refresh,
            refresh_url=refresh_url,
            metadata=metadata or {},
            version=version,
        )

        self._credentials[service] = cred
        self._save()
        self._audit("STORE", service, f"type={credential_type} v{version}")
        logger.info("✅ Credential stored: %s (type=%s, v%d)", service, credential_type, version)
        return cred

    def get(self, service: str, *, allow_expired: bool = False) -> Credential | None:
        """Get credential for a service."""
        cred = self._credentials.get(service)
        if cred is None:
            return None

        if cred.is_expired and not allow_expired:
            self._audit("ACCESS_EXPIRED", service)
            logger.warning("⏰ Credential expired: %s", service)
            return None

        self._audit("ACCESS", service)
        return cred

    def get_data(self, service: str, key: str | None = None) -> Any:
        """Shortcut: get data from a credential.

        vault.get_data("github", "access_token") → "ghp_xxx"
        vault.get_data("github") → {"access_token": "ghp_xxx", ...}
        """
        cred = self.get(service)
        if cred is None:
            return None
        if key is None:
            return cred.data
        return cred.data.get(key)

    def delete(self, service: str) -> bool:
        """Delete a credential."""
        if service in self._credentials:
            del self._credentials[service]
            self._save()
            self._audit("DELETE", service)
            logger.info("🗑️ Credential deleted: %s", service)
            return True
        return False

    def list_services(self) -> list[dict[str, Any]]:
        """Return list of all services (without secret data)."""
        result = []
        for name, cred in self._credentials.items():
            result.append({
                "service": name,
                "type": cred.credential_type,
                "expired": cred.is_expired,
                "ttl": cred.ttl_seconds,
                "auto_refresh": cred.auto_refresh,
                "version": cred.version,
                "created_at": cred.created_at,
            })
        return result

    def get_expiring_soon(self, threshold_seconds: float = 3600) -> list[str]:
        """Return services with tokens expiring soon."""
        expiring = []
        for name, cred in self._credentials.items():
            if cred.ttl_seconds is not None and cred.ttl_seconds < threshold_seconds:
                expiring.append(name)
        return expiring

    def rotate_encryption_key(self, new_key: bytes | None = None) -> None:
        """Rotate the vault encryption key."""
        new_key = new_key or Fernet.generate_key()
        self._fernet = Fernet(new_key)
        self._key_file.write_bytes(new_key)
        self._save()
        self._audit("KEY_ROTATION", "*", "Encryption key rotated")
        logger.info("🔄 Vault encryption key rotated")

    def export_backup(self, path: Path) -> None:
        """Export an encrypted vault backup."""
        if self._vault_file.exists():
            import shutil

            shutil.copy2(self._vault_file, path)
            self._audit("EXPORT", "*", f"Backup to {path}")

    def wipe(self) -> None:
        """Complete vault destruction (DANGEROUS!)."""
        self._credentials = {}
        if self._vault_file.exists():
            self._vault_file.unlink()
        self._audit("WIPE", "*", "Vault wiped")
        logger.warning("💀 Vault wiped completely")
