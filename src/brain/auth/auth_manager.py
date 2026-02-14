"""Auth Manager — Central authentication coordinator for Atlas.

Single entry point for all authentication operations:
- Get credentials for a service (from vault, keychain, or via registration)
- Register on a new service
- Sign data with electronic signature
- Manage tokens (refresh, revoke)
- Search stored credentials

Access Policy (ATLAS_KEYCHAIN_ACCESS env var):
- full:       Atlas has FULL access to all credentials and can
              autonomously select the right ones for any action
- restricted: only allowed categories / services
- none:       access disabled (default)

Usage:
    from src.brain.auth import AuthManager

    auth = AuthManager()

    # Get access token for a service
    token = await auth.get_access_token("data_gov_ua")

    # Register on a new service
    result = await auth.register("new_service", flow=my_flow)

    # Get credential from any source
    cred = auth.find_credential("github.com")

    # Sign a document
    signed = await auth.sign_document(data, method="dia_eid")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("brain.auth.manager")


class AuthManager:
    """Central authentication coordinator for AtlasTrinity.

    Combines all subsystems:
    - CredentialVault (encrypted storage)
    - KeychainBridge (macOS Keychain, Chrome, SSH, GPG, .env)
    - IdentityProviderRegistry (Dia, BankID, NFC, FIDO2, Certificates)
    - OAuthEngine (any OAuth2 service)
    - RegistrationEngine (automatic registration)
    - TokenRefresher (background token refresh)
    - SystemAccess (sudo, keychain unlock via ATLAS_SYSTEM_PASSWORD)

    Credential lookup order:
    1. Vault (encrypted local storage)
    2. macOS Keychain
    3. Environment variables / .env
    4. Chrome / Firefox saved passwords
    5. SSH / GPG keys

    If credential not found:
    -> Propose registration via RegistrationEngine
    -> Or request from user manually
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        from src.brain.auth.access_policy import AccessPolicy, load_access_policy
        from src.brain.auth.ci_compat import detect_ci_environment
        from src.brain.auth.credential_vault import CredentialVault
        from src.brain.auth.identity_provider import (
            IdentityProviderRegistry,
        )
        from src.brain.auth.keychain_bridge import KeychainBridge
        from src.brain.auth.oauth_engine import OAuthEngine
        from src.brain.auth.registration_engine import RegistrationEngine
        from src.brain.auth.token_refresher import TokenRefresher

        self._config = config or {}
        self._ci_env = detect_ci_environment()

        # Access Policy — determines Atlas's access level
        self.policy: AccessPolicy = load_access_policy(self._config)

        # Core components
        self.vault = CredentialVault()
        self.keychain = KeychainBridge()
        self.identity = IdentityProviderRegistry()
        self.oauth = OAuthEngine()
        self.registration = RegistrationEngine(
            vault=self.vault,
            identity_registry=self.identity,
        )
        self.refresher = TokenRefresher(
            vault=self.vault,
            oauth_engine=self.oauth,
        )

        # Register default identity providers
        self._setup_default_providers()

        # Auto-discovery: if FULL ACCESS — scan everything immediately
        # In CI, skip auto-discovery to avoid keychain/system access
        self._discovery_done = False
        if self.policy.is_full_access and self.policy.can_auto_discover:
            if self._ci_env.is_ci:
                logger.info(
                    "🔧 CI mode: skipping initial discovery (provider=%s)",
                    self._ci_env.provider.value,
                )
                self._discovery_done = True  # Mark as done (nothing to discover)
            else:
                self._run_initial_discovery()

        logger.info(
            "🔐 AuthManager initialized (access_policy=%s, ci=%s)",
            self.policy.level.value,
            self._ci_env.is_ci,
        )

    def _setup_default_providers(self) -> None:
        """Set up default identity providers."""
        from src.brain.auth.identity_provider import (
            BankIdProvider,
            CertificateProvider,
            DiaEidProvider,
            ManualApprovalProvider,
            NfcIdentityProvider,
        )

        # Dia.EID — check for key availability
        dia_key = self._config.get("dia_key_file")
        dia_password = self._config.get("dia_key_password")
        dia_token = self._config.get("dia_acquirer_token")
        if dia_key or dia_token:
            self.identity.register(
                DiaEidProvider(
                    key_file=Path(dia_key) if dia_key else None,
                    key_password=dia_password,
                    acquirer_token=dia_token,
                )
            )

        # BankID
        bank_id = self._config.get("bank_id_client_id")
        bank_secret = self._config.get("bank_id_client_secret")
        if bank_id:
            self.identity.register(
                BankIdProvider(client_id=bank_id, client_secret=bank_secret)
            )

        # NFC (always available as an option)
        self.identity.register(NfcIdentityProvider())

        # Certificate provider
        cert_path = self._config.get("cert_path")
        key_path = self._config.get("key_path")
        cert_password = self._config.get("cert_password")
        if cert_path or key_path:
            self.identity.register(
                CertificateProvider(
                    cert_path=Path(cert_path) if cert_path else None,
                    key_path=Path(key_path) if key_path else None,
                    password=cert_password,
                )
            )

        # Manual Approval — always as a fallback
        self.identity.register(ManualApprovalProvider())

    # ── Credential Lookup (Multi-source) ────────────────────────────────

    def _run_initial_discovery(self) -> None:
        """Initial scan of all available credentials.

        Called automatically with FULL ACCESS.
        Finds all credentials across all sources and optionally
        imports into vault for fast access.
        """
        try:
            all_entries = self.keychain.discover_all(force_refresh=True)
            self._discovery_done = True

            if self.policy.can_auto_import:
                imported = self._auto_import_discovered(all_entries)
                if imported:
                    logger.info(
                        "📥 Auto-imported %d credentials to vault", imported
                    )

            logger.info(
                "🔓 Initial discovery complete: %d credentials found across all sources",
                len(all_entries),
            )
        except Exception as e:
            logger.warning("⚠️ Initial discovery failed: %s", e)

    def _auto_import_discovered(
        self,
        entries: list[Any] | None = None,
    ) -> int:
        """Automatically import discovered credentials into vault.

        Imports only those that have a secret and are not yet in vault.
        """
        from src.brain.auth.access_policy import categorize_credential

        if entries is None:
            entries = self.keychain.discover_all()

        imported = 0
        for entry in entries:
            # Skip entries without secret
            if not entry.secret:
                continue

            # Skip if already in vault
            if self.vault.get(entry.service):
                continue

            # Check policy
            category, confidence = categorize_credential(
                entry.service, entry.account
            )
            if not self.policy.is_credential_allowed(entry.service, category):
                continue

            # Import
            self.vault.store(
                service=entry.service,
                credential_type=f"auto_import_{entry.source.value}",
                data={
                    "secret": entry.secret,
                    "account": entry.account,
                    "original_source": entry.source.value,
                    "category": category.value,
                    "confidence": confidence,
                },
            )
            imported += 1

        return imported

    def find_credential(self, service: str) -> dict[str, Any] | None:
        """Search for a credential for a service across all sources.

        Search order:
        1. Vault
        2. macOS Keychain
        3. Environment / .env
        4. Browser keychains

        Returns:
            {"source": "vault|keychain|env|...", "data": {...}} or None
        """
        # 1. Vault
        cred = self.vault.get(service)
        if cred:
            return {"source": "vault", "data": cred.data, "credential": cred}

        # 2. Keychain — search by service name
        keychain_entry = self.keychain.get_credential_for_domain(service)
        if keychain_entry and keychain_entry.secret:
            return {
                "source": keychain_entry.source.value,
                "data": {
                    "secret": keychain_entry.secret,
                    "account": keychain_entry.account,
                    "service": keychain_entry.service,
                },
                "entry": keychain_entry,
            }

        # 3. Search all keychain sources
        entries = self.keychain.search(service)
        if entries:
            best = entries[0]
            return {
                "source": best.source.value,
                "data": {
                    "secret": best.secret,
                    "account": best.account,
                    "service": best.service,
                },
                "entry": best,
            }

        return None

    async def get_access_token(self, service: str) -> str | None:
        """Get access token for a service.

        Automatically refreshes if expired.
        """
        cred = self.vault.get(service)
        if cred and not cred.is_expired:
            return cred.data.get("access_token")

        # Try to refresh
        if cred and cred.auto_refresh and cred.data.get("refresh_token"):
            success = await self.refresher.force_refresh(service)
            if success:
                updated = self.vault.get(service)
                if updated:
                    return updated.data.get("access_token")

        # Nothing found
        return None

    async def get_api_key(self, service: str) -> str | None:
        """Get API key for a service."""
        result = self.find_credential(service)
        if result:
            data = result["data"]
            return data.get("api_key") or data.get("secret") or data.get("access_token")
        return None

    # ── OAuth2 Operations ───────────────────────────────────────────────

    def configure_oauth_service(self, config: dict[str, Any]) -> None:
        """Configure an OAuth2 service.

        Args:
            config: {
                "service_id": "my_service",
                "display_name": "My Service",
                "authorize_url": "https://...",
                "token_url": "https://...",
                "client_id": "xxx",
                "client_secret": "yyy",  # optional
                "scopes": ["read", "write"],
                "flow": "authorization_code",  # or "pkce", "client_credentials", "device_code"
            }
        """
        from src.brain.auth.oauth_engine import OAuthFlowType, OAuthServiceConfig

        flow_map = {
            "authorization_code": OAuthFlowType.AUTHORIZATION_CODE,
            "pkce": OAuthFlowType.PKCE,
            "client_credentials": OAuthFlowType.CLIENT_CREDENTIALS,
            "device_code": OAuthFlowType.DEVICE_CODE,
        }

        svc = OAuthServiceConfig(
            service_id=config["service_id"],
            display_name=str(config.get("display_name", config["service_id"])),
            authorize_url=config.get("authorize_url"),
            token_url=config.get("token_url"),
            revoke_url=config.get("revoke_url"),
            userinfo_url=config.get("userinfo_url"),
            device_code_url=config.get("device_code_url"),
            discovery_url=config.get("discovery_url"),
            client_id=config.get("client_id"),
            client_secret=config.get("client_secret"),
            flow=flow_map.get(config.get("flow", "authorization_code"), OAuthFlowType.AUTHORIZATION_CODE),
            scopes=config.get("scopes", []),
            redirect_uri=config.get("redirect_uri", "http://localhost:8086/auth/callback"),
            registration_url=config.get("registration_url"),
            extra_authorize_params=config.get("extra_authorize_params", {}),
            extra_token_params=config.get("extra_token_params", {}),
            custom_headers=config.get("custom_headers", {}),
        )
        self.oauth.register_service(svc)

    async def oauth_authorize(self, service_id: str) -> dict[str, str]:
        """Start OAuth2 authorization.

        Returns:
            {"authorize_url": "https://...", "state": "xxx"}
        """
        url, state = self.oauth.get_authorize_url(service_id)
        return {"authorize_url": url, "state": state}

    async def oauth_callback(
        self,
        service_id: str,
        code: str,
        state: str,
    ) -> dict[str, Any]:
        """Handle OAuth2 callback.

        Stores tokens in vault.
        """
        tokens = await self.oauth.exchange_code(service_id, code, state)

        # Store in vault
        self.vault.store(
            service=service_id,
            credential_type="oauth2",
            data=tokens.to_dict(),
            expires_in=tokens.expires_in,
            auto_refresh=True,
        )

        return tokens.to_dict()

    async def oauth_client_credentials(self, service_id: str) -> dict[str, Any]:
        """Get token via Client Credentials flow."""
        tokens = await self.oauth.client_credentials(service_id)

        self.vault.store(
            service=service_id,
            credential_type="oauth2",
            data=tokens.to_dict(),
            expires_in=tokens.expires_in,
            auto_refresh=False,  # Client Credentials has no refresh
        )

        return tokens.to_dict()

    async def oauth_device_flow(self, service_id: str) -> dict[str, Any]:
        """Start Device Code flow.

        Returns:
            {"user_code": "ABCD-EFGH", "verification_uri": "https://..."}
        """
        return await self.oauth.start_device_flow(service_id)

    # ── Registration ────────────────────────────────────────────────────

    async def register(
        self,
        service_name: str,
        flow: Any | None = None,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register on a service.

        Args:
            service_name: Service name
            flow: RegistrationFlow or None (for auto-detect)
            variables: Initial variables (email, name, etc.)
        """

        if flow:
            self.registration.register_flow(flow)
            result = await self.registration.execute(flow, variables)
        else:
            # Check if there is a registered flow
            existing_flow = self.registration.get_flow(service_name)
            if existing_flow:
                result = await self.registration.execute(existing_flow, variables)
            else:
                return {
                    "success": False,
                    "error": f"No registration flow for '{service_name}'. Define a RegistrationFlow first.",
                }

        return {
            "success": result.success,
            "steps_completed": result.steps_completed,
            "steps_total": result.steps_total,
            "credentials_stored": result.credentials_stored,
            "errors": result.errors,
            "duration": result.duration_seconds,
        }

    # ── Identity / Signing ──────────────────────────────────────────────

    async def sign_document(
        self,
        data: bytes,
        method: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Sign data with an electronic signature.

        Args:
            data: Data to sign
            method: Method ("dia_eid", "certificate", etc.), None = auto
            context: Additional context
        """
        from src.brain.auth.identity_provider import IdentityMethod, IdentityStatus

        if method:
            provider = await self.identity.get_available(IdentityMethod(method))
        else:
            provider = await self.identity.get_best_available()

        if not provider:
            return {"success": False, "error": "No signing provider available"}

        result = await provider.sign_data(data, context or {})

        return {
            "success": result.status == IdentityStatus.VERIFIED,
            "status": result.status.value,
            "method": result.method.value,
            "signature": result.signature.hex() if result.signature else None,
            "awaiting_user": result.status == IdentityStatus.AWAITING_USER,
            "error": result.error,
        }

    async def verify_identity(
        self,
        method: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Verify user identity.

        Returns:
            {"challenge": {...}, "instructions": "...", "status": "..."}
        """
        from src.brain.auth.identity_provider import IdentityMethod

        if method:
            provider = await self.identity.get_available(IdentityMethod(method))
        else:
            provider = await self.identity.get_best_available()

        if not provider:
            return {"success": False, "error": "No identity provider available"}

        challenge = await provider.create_challenge(context or {})

        return {
            "challenge_id": challenge.challenge_id,
            "method": challenge.method.value,
            "instructions": challenge.instructions,
            "deep_link": challenge.deep_link,
            "qr_code_data": challenge.qr_code_data,
            "timeout": challenge.timeout_seconds,
        }

    # ── Token Management ────────────────────────────────────────────────

    async def start_auto_refresh(self) -> None:
        """Start background token refresh."""
        await self.refresher.start()

    async def stop_auto_refresh(self) -> None:
        """Stop background token refresh."""
        await self.refresher.stop()

    # ── Vault Operations ────────────────────────────────────────────────

    def store_credential(
        self,
        service: str,
        credential_type: str,
        data: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """Store credential in vault."""
        self.vault.store(service, credential_type, data, **kwargs)

    def delete_credential(self, service: str) -> bool:
        """Delete a credential."""
        return self.vault.delete(service)

    def list_credentials(self) -> list[dict[str, Any]]:
        """List all stored credentials (without secrets)."""
        return self.vault.list_services()

    def import_from_keychain(self, service: str) -> bool:
        """Import credential from macOS Keychain to vault."""
        entry = self.keychain.get_credential_for_domain(service)
        if entry and entry.secret:
            self.vault.store(
                service=service,
                credential_type="keychain_import",
                data={
                    "secret": entry.secret,
                    "account": entry.account,
                    "original_source": entry.source.value,
                },
            )
            logger.info("📥 Imported from keychain: %s", service)
            return True
        return False

    def import_from_env(self, env_key: str, service: str | None = None) -> bool:
        """Import credential from environment variable to vault."""
        entry = self.keychain.get_from_env(env_key)
        if entry and entry.secret:
            self.vault.store(
                service=service or env_key.lower(),
                credential_type="env_import",
                data={"secret": entry.secret, "env_key": env_key},
            )
            logger.info("📥 Imported from env: %s", env_key)
            return True
        return False

    # ── Status & Diagnostics ────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        """Full authentication system status."""
        return {
            "access_policy": {
                "level": self.policy.level.value,
                "can_auto_discover": self.policy.can_auto_discover,
                "can_auto_import": self.policy.can_auto_import,
                "can_auto_use": self.policy.can_auto_use,
                "can_store": self.policy.can_store,
                "discovery_done": self._discovery_done,
            },
            "environment": {
                "is_ci": self._ci_env.is_ci,
                "ci_provider": self._ci_env.provider.value,
                "runner_os": self._ci_env.runner_os,
                "available_features": self._ci_env.available_features,
            },
            "vault": {
                "total_credentials": len(self.vault.list_services()),
                "expiring_soon": self.vault.get_expiring_soon(3600),
                "services": [s["service"] for s in self.vault.list_services()],
            },
            "keychain": {
                "available_sources": [s.value for s in self.keychain.available_sources],
                "cached_entries": (
                    len(self.keychain._discovery_cache)
                    if self.keychain._discovery_cache is not None
                    else 0
                ),
            },
            "identity": {
                "registered_providers": [
                    m.value for m in self.identity.list_registered()
                ],
            },
            "oauth": {
                "configured_services": self.oauth.list_services(),
            },
            "registration": {
                "registered_flows": self.registration.list_flows(),
            },
            "refresher": {
                "running": self.refresher.is_running,
                "stats": self.refresher.stats,
            },
        }

    # ── Autonomous Credential Resolution (FULL ACCESS) ──────────────────

    def get_best_credential_for(
        self,
        purpose: str,
        *,
        prefer_category: str | None = None,
    ) -> dict[str, Any] | None:
        """Autonomously finds the best credential for a given purpose.

        Atlas determines which credential fits best on its own.
        Works only with FULL or RESTRICTED access.

        Args:
            purpose: What the credential is needed for (e.g. "github api",
                     "google maps", "ai chat", "ssh deploy")
            prefer_category: Preferred category (api_key, oauth_token, etc.)

        Returns:
            {"service": ..., "secret": ..., "source": ..., "category": ...}
            or None
        """
        if self.policy.is_disabled:
            logger.warning("🚫 get_best_credential_for: access policy is NONE")
            return None

        if not self.policy.can_auto_use:
            logger.warning(
                "🔒 get_best_credential_for: auto_use is disabled"
            )
            return None

        from src.brain.auth.access_policy import categorize_credential

        # 1. Search in vault
        vault_cred = self.vault.get(purpose)
        if vault_cred and not vault_cred.is_expired:
            return {
                "service": vault_cred.service,
                "secret": vault_cred.data.get("secret")
                or vault_cred.data.get("access_token")
                or vault_cred.data.get("api_key"),
                "source": "vault",
                "category": vault_cred.credential_type,
                "data": vault_cred.data,
            }

        # 2. Smart search across all sources
        results = self.keychain.smart_search(purpose, category=prefer_category)
        for entry in results:
            if not entry.secret:
                continue

            cat, conf = categorize_credential(entry.service, entry.account)
            if not self.policy.is_credential_allowed(entry.service, cat):
                continue

            return {
                "service": entry.service,
                "secret": entry.secret,
                "source": entry.source.value,
                "category": cat.value,
                "account": entry.account,
                "confidence": conf,
            }

        # 3. find_credential as fallback
        found = self.find_credential(purpose)
        if found:
            return found

        logger.debug("🔍 No credential found for purpose: %s", purpose)
        return None

    def discover_all_credentials(
        self,
        *,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Full scan and categorization of ALL available credentials.

        Returns a list with metadata (no secrets in plain text).
        Requires can_auto_discover policy.
        """
        if not self.policy.can_auto_discover:
            logger.warning("🔒 discover_all_credentials: auto_discover is disabled")
            return []

        from src.brain.auth.access_policy import categorize_credential

        entries = self.keychain.discover_all(force_refresh=force_refresh)
        result: list[dict[str, Any]] = []

        for entry in entries:
            category, confidence = categorize_credential(
                entry.service, entry.account
            )
            result.append({
                "service": entry.service,
                "account": entry.account,
                "source": entry.source.value,
                "category": category.value,
                "confidence": confidence,
                "has_secret": bool(entry.secret),
                "allowed": self.policy.is_credential_allowed(
                    entry.service, category
                ),
            })

        return result

    def auto_import_all(self) -> dict[str, Any]:
        """Imports ALL available credentials into vault.

        Requires can_auto_import policy.

        Returns:
            {"imported": int, "skipped": int, "errors": int}
        """
        if not self.policy.can_auto_import:
            return {"imported": 0, "skipped": 0, "errors": 0,
                    "error": "auto_import is disabled by policy"}

        entries = self.keychain.discover_all(force_refresh=True)
        imported = self._auto_import_discovered(entries)

        return {
            "imported": imported,
            "total_scanned": len(entries),
            "vault_total": len(self.vault.list_services()),
        }

    def get_credential_inventory(self) -> dict[str, Any]:
        """Full credential inventory by categories.

        Convenient overview: how many credentials of each category found,
        from which sources, what is in vault and what is not.
        """
        if not self.policy.can_auto_discover:
            return {"error": "auto_discover is disabled by policy"}

        from src.brain.auth.access_policy import categorize_credential

        entries = self.keychain.discover_all()
        vault_services = {s["service"] for s in self.vault.list_services()}

        inventory: dict[str, list[dict[str, Any]]] = {}
        for entry in entries:
            cat, _conf = categorize_credential(entry.service, entry.account)
            cat_name = cat.value

            if cat_name not in inventory:
                inventory[cat_name] = []

            inventory[cat_name].append({
                "service": entry.service,
                "account": entry.account,
                "source": entry.source.value,
                "in_vault": entry.service in vault_services,
                "has_secret": bool(entry.secret),
            })

        summary = {
            "total": len(entries),
            "in_vault": len(vault_services),
            "categories": {
                cat: len(items) for cat, items in inventory.items()
            },
            "details": inventory,
        }
        return summary

    def ensure_full_access(self) -> bool:
        """Checks and confirms that Atlas has FULL ACCESS.

        If ATLAS_KEYCHAIN_ACCESS is not set — returns False
        and prints instructions.
        """
        if self.policy.is_full_access:
            if not self._discovery_done:
                self._run_initial_discovery()
            return True

        logger.warning(
            "⚠️ Atlas does NOT have full keychain access.\n"
            "To grant full access, add to ~/.config/atlastrinity/.env:\n"
            "  ATLAS_KEYCHAIN_ACCESS=full\n"
            "Or set environment variable: export ATLAS_KEYCHAIN_ACCESS=full"
        )
        return False

    async def cleanup(self) -> None:
        """Cleanup resources."""
        await self.refresher.stop()
        await self.oauth.close()
        await self.registration.close()
        logger.info("🧹 AuthManager cleaned up")
