"""OAuth Engine — Universal OAuth2/OIDC engine.

Supports ANY OAuth2 service without hardcoding:
- Authorization Code Flow
- Client Credentials Flow
- Device Code Flow
- PKCE Extension
- Token Refresh
- OpenID Connect Discovery

Configuration via OAuthServiceConfig — describe any service.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
import urllib.parse
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx

logger = logging.getLogger("brain.auth.oauth")


class OAuthFlowType(StrEnum):
    """Supported OAuth2 flows."""

    AUTHORIZATION_CODE = "authorization_code"
    CLIENT_CREDENTIALS = "client_credentials"
    DEVICE_CODE = "device_code"
    PKCE = "pkce"  # Authorization Code + PKCE
    IMPLICIT = "implicit"  # Legacy, not recommended
    REFRESH_TOKEN = "refresh_token"


@dataclass
class OAuthServiceConfig:
    """OAuth2 configuration for an arbitrary service.

    Describe any OAuth2 service — Atlas will be able to work with it.

    Example:
        config = OAuthServiceConfig(
            service_id="my_gov_portal",
            display_name="Government Portal",
            authorize_url="https://portal.gov.ua/oauth/authorize",
            token_url="https://portal.gov.ua/oauth/token",
            client_id="atlas_app_123",
            scopes=["read", "write"],
        )
    """

    service_id: str  # Unique ID (for vault storage)
    display_name: str  # Human-readable name

    # OAuth2 Endpoints (can be set manually or via discovery)
    authorize_url: str | None = None
    token_url: str | None = None
    revoke_url: str | None = None
    userinfo_url: str | None = None
    device_code_url: str | None = None
    discovery_url: str | None = None  # OIDC Discovery URL (.well-known/openid-configuration)

    # Client credentials
    client_id: str | None = None
    client_secret: str | None = None

    # Flow configuration
    flow: OAuthFlowType = OAuthFlowType.AUTHORIZATION_CODE
    scopes: list[str] = field(default_factory=list)
    redirect_uri: str = "http://localhost:8086/auth/callback"

    # Token settings
    token_type: str = "Bearer"
    supports_refresh: bool = True

    # Extra params for authorize/token requests
    extra_authorize_params: dict[str, str] = field(default_factory=dict)
    extra_token_params: dict[str, str] = field(default_factory=dict)

    # Custom headers
    custom_headers: dict[str, str] = field(default_factory=dict)

    # Auto-registration (if service supports programmatic registration)
    registration_url: str | None = None
    registration_payload: dict[str, Any] | None = None


@dataclass
class OAuthTokenSet:
    """OAuth2 token set."""

    access_token: str
    token_type: str = "Bearer"
    refresh_token: str | None = None
    expires_in: int | None = None
    scope: str | None = None
    id_token: str | None = None
    obtained_at: float = field(default_factory=time.time)
    raw_response: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.expires_in is None:
            return False
        return time.time() > self.obtained_at + self.expires_in

    @property
    def ttl_seconds(self) -> float | None:
        if self.expires_in is None:
            return None
        return max(0.0, self.obtained_at + self.expires_in - time.time())

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "refresh_token": self.refresh_token,
            "expires_in": self.expires_in,
            "scope": self.scope,
            "id_token": self.id_token,
            "obtained_at": self.obtained_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OAuthTokenSet:
        return cls(
            access_token=d["access_token"],
            token_type=d.get("token_type", "Bearer"),
            refresh_token=d.get("refresh_token"),
            expires_in=d.get("expires_in"),
            scope=d.get("scope"),
            id_token=d.get("id_token"),
            obtained_at=d.get("obtained_at", time.time()),
            raw_response=d,
        )


class OAuthEngine:
    """Universal OAuth2 engine.

    Works with any OAuth2 service via OAuthServiceConfig.

    Usage:
        engine = OAuthEngine()

        # 1. Configure a service
        config = OAuthServiceConfig(
            service_id="gov_portal",
            display_name="Gov Portal",
            authorize_url="https://...",
            token_url="https://...",
            client_id="xxx",
        )
        engine.register_service(config)

        # 2. Get Authorization URL
        url, state = await engine.get_authorize_url("gov_portal")

        # 3. Exchange code for tokens
        tokens = await engine.exchange_code("gov_portal", code, state)

        # 4. Refresh token
        tokens = await engine.refresh_token("gov_portal")
    """

    def __init__(self) -> None:
        self._services: dict[str, OAuthServiceConfig] = {}
        self._states: dict[str, dict[str, str]] = {}  # state → {service_id, code_verifier, ...}
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
            )
        return self._http_client

    async def close(self) -> None:
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    # ── Service Management ──────────────────────────────────────────────

    def register_service(self, config: OAuthServiceConfig) -> None:
        """Registers an OAuth2 service."""
        self._services[config.service_id] = config
        logger.info("📋 OAuth service registered: %s (%s)", config.service_id, config.display_name)

    def get_service(self, service_id: str) -> OAuthServiceConfig | None:
        return self._services.get(service_id)

    def list_services(self) -> list[str]:
        return list(self._services.keys())

    async def discover_endpoints(self, service_id: str) -> bool:
        """Automatically discovers endpoints via OIDC Discovery."""
        config = self._services.get(service_id)
        if not config or not config.discovery_url:
            return False

        try:
            client = await self._get_client()
            resp = await client.get(config.discovery_url)
            resp.raise_for_status()
            data = resp.json()

            config.authorize_url = data.get("authorization_endpoint", config.authorize_url)
            config.token_url = data.get("token_endpoint", config.token_url)
            config.revoke_url = data.get("revocation_endpoint", config.revoke_url)
            config.userinfo_url = data.get("userinfo_endpoint", config.userinfo_url)
            config.device_code_url = data.get(
                "device_authorization_endpoint", config.device_code_url
            )

            logger.info("🔍 OIDC Discovery successful for: %s", service_id)
            return True
        except Exception as e:
            logger.error("❌ OIDC Discovery failed for %s: %s", service_id, e)
            return False

    # ── Authorization Code Flow ─────────────────────────────────────────

    def get_authorize_url(self, service_id: str) -> tuple[str, str]:
        """Generates Authorization URL for user redirect.

        Returns:
            (authorize_url, state) — URL for redirect + state for verification
        """
        config = self._services[service_id]
        if not config.authorize_url:
            raise ValueError(f"No authorize_url configured for {service_id}")

        state = secrets.token_urlsafe(32)

        params: dict[str, str] = {
            "response_type": "code",
            "client_id": config.client_id or "",
            "redirect_uri": config.redirect_uri,
            "state": state,
        }

        if config.scopes:
            params["scope"] = " ".join(config.scopes)

        state_data: dict[str, str] = {"service_id": service_id}

        # PKCE extension
        if config.flow == OAuthFlowType.PKCE:
            code_verifier = secrets.token_urlsafe(64)
            code_challenge = hashlib.sha256(code_verifier.encode()).digest()
            import base64

            code_challenge_b64 = base64.urlsafe_b64encode(code_challenge).rstrip(b"=").decode()
            params["code_challenge"] = code_challenge_b64
            params["code_challenge_method"] = "S256"
            state_data["code_verifier"] = code_verifier

        # Extra params
        params.update(config.extra_authorize_params)

        self._states[state] = state_data

        url = f"{config.authorize_url}?{urllib.parse.urlencode(params)}"
        return url, state

    async def exchange_code(
        self,
        service_id: str,
        code: str,
        state: str,
    ) -> OAuthTokenSet:
        """Exchanges authorization code for tokens."""
        config = self._services[service_id]
        if not config.token_url:
            raise ValueError(f"No token_url configured for {service_id}")

        # Verify state
        state_data = self._states.pop(state, None)
        if state_data is None or state_data.get("service_id") != service_id:
            raise ValueError("Invalid or expired state parameter")

        data: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.redirect_uri,
            "client_id": config.client_id or "",
        }

        if config.client_secret:
            data["client_secret"] = config.client_secret

        # PKCE verifier
        if "code_verifier" in state_data:
            data["code_verifier"] = state_data["code_verifier"]

        data.update(config.extra_token_params)

        client = await self._get_client()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        headers.update(config.custom_headers)

        resp = await client.post(config.token_url, data=data, headers=headers)
        resp.raise_for_status()
        token_data = resp.json()

        tokens = OAuthTokenSet.from_dict(token_data)
        logger.info("✅ Token obtained for: %s", service_id)
        return tokens

    # ── Client Credentials Flow ─────────────────────────────────────────

    async def client_credentials(self, service_id: str) -> OAuthTokenSet:
        """Obtains token via Client Credentials flow (machine-to-machine)."""
        config = self._services[service_id]
        if not config.token_url:
            raise ValueError(f"No token_url configured for {service_id}")

        data: dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": config.client_id or "",
            "client_secret": config.client_secret or "",
        }

        if config.scopes:
            data["scope"] = " ".join(config.scopes)

        data.update(config.extra_token_params)

        client = await self._get_client()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        headers.update(config.custom_headers)

        resp = await client.post(config.token_url, data=data, headers=headers)
        resp.raise_for_status()
        token_data = resp.json()

        return OAuthTokenSet.from_dict(token_data)

    # ── Device Code Flow ────────────────────────────────────────────────

    async def start_device_flow(self, service_id: str) -> dict[str, Any]:
        """Starts Device Code flow (for CLI / headless).

        Returns:
            {"device_code": "xxx", "user_code": "ABCD-EFGH",
             "verification_uri": "https://...", "interval": 5}
        """
        config = self._services[service_id]
        url = config.device_code_url or (
            config.token_url.replace("/token", "/device/code") if config.token_url else None
        )
        if not url:
            raise ValueError(f"No device_code_url for {service_id}")

        data: dict[str, str] = {"client_id": config.client_id or ""}
        if config.scopes:
            data["scope"] = " ".join(config.scopes)

        client = await self._get_client()
        resp = await client.post(url, data=data)
        resp.raise_for_status()
        return resp.json()

    async def poll_device_token(
        self,
        service_id: str,
        device_code: str,
        interval: int = 5,
        max_attempts: int = 60,
    ) -> OAuthTokenSet | None:
        """Polling for Device Code flow."""
        import asyncio

        config = self._services[service_id]
        if not config.token_url:
            raise ValueError(f"No token_url for {service_id}")

        for _ in range(max_attempts):
            data = {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": config.client_id or "",
            }

            client = await self._get_client()
            resp = await client.post(config.token_url, data=data)

            if resp.status_code == 200:
                return OAuthTokenSet.from_dict(resp.json())

            body = resp.json()
            error = body.get("error", "")

            if error == "authorization_pending":
                await asyncio.sleep(interval)
                continue
            if error == "slow_down":
                interval += 5
                await asyncio.sleep(interval)
                continue
            if error in ("expired_token", "access_denied"):
                logger.warning("Device flow failed: %s", error)
                return None
            logger.error("Unexpected device flow error: %s", body)
            return None

        return None

    # ── Token Refresh ───────────────────────────────────────────────────

    async def refresh_token(
        self,
        service_id: str,
        refresh_token: str,
    ) -> OAuthTokenSet:
        """Refreshes token via refresh_token."""
        config = self._services[service_id]
        if not config.token_url:
            raise ValueError(f"No token_url for {service_id}")

        data: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": config.client_id or "",
        }

        if config.client_secret:
            data["client_secret"] = config.client_secret

        client = await self._get_client()
        resp = await client.post(config.token_url, data=data)
        resp.raise_for_status()
        token_data = resp.json()

        tokens = OAuthTokenSet.from_dict(token_data)
        logger.info("🔄 Token refreshed for: %s", service_id)
        return tokens

    # ── Token Revocation ────────────────────────────────────────────────

    async def revoke_token(
        self,
        service_id: str,
        token: str,
        token_type_hint: str = "access_token",
    ) -> bool:
        """Revokes a token."""
        config = self._services[service_id]
        if not config.revoke_url:
            logger.warning("No revoke_url for %s", service_id)
            return False

        data = {
            "token": token,
            "token_type_hint": token_type_hint,
            "client_id": config.client_id or "",
        }
        if config.client_secret:
            data["client_secret"] = config.client_secret

        client = await self._get_client()
        resp = await client.post(config.revoke_url, data=data)
        return resp.status_code in (200, 204)

    # ── UserInfo ────────────────────────────────────────────────────────

    async def get_userinfo(
        self,
        service_id: str,
        access_token: str,
    ) -> dict[str, Any]:
        """Gets user information (OIDC userinfo)."""
        config = self._services[service_id]
        if not config.userinfo_url:
            raise ValueError(f"No userinfo_url for {service_id}")

        client = await self._get_client()
        resp = await client.get(
            config.userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()

    # ── Dynamic Client Registration ─────────────────────────────────────

    async def register_client(
        self,
        service_id: str,
        app_name: str = "AtlasTrinity",
        app_uri: str | None = None,
        redirect_uris: list[str] | None = None,
    ) -> dict[str, Any]:
        """Dynamic OAuth2 client registration (RFC 7591).

        For services that support Dynamic Client Registration.
        """
        config = self._services[service_id]
        if not config.registration_url:
            raise ValueError(f"No registration_url for {service_id}")

        payload = config.registration_payload or {}
        payload.update(
            {
                "client_name": app_name,
                "redirect_uris": redirect_uris or [config.redirect_uri],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "client_secret_basic",
            }
        )
        if app_uri:
            payload["client_uri"] = app_uri

        client = await self._get_client()
        resp = await client.post(
            config.registration_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        result = resp.json()

        # Update config with received credentials
        if "client_id" in result:
            config.client_id = result["client_id"]
        if "client_secret" in result:
            config.client_secret = result["client_secret"]

        logger.info(
            "✅ Client registered for %s: client_id=%s", service_id, result.get("client_id")
        )
        return result
