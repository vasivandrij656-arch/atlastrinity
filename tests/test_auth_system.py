"""Tests for the Universal Authentication System."""

from __future__ import annotations

import os
import time
from unittest.mock import patch

import pytest

from src.brain.auth.ci_compat import is_ci
from src.brain.auth.credential_vault import Credential, CredentialVault
from src.brain.auth.identity_provider import (
    DiaEidProvider,
    IdentityMethod,
    IdentityProviderRegistry,
    ManualApprovalProvider,
)
from src.brain.auth.keychain_bridge import KeychainBridge, KeychainSource
from src.brain.auth.oauth_engine import (
    OAuthEngine,
    OAuthFlowType,
    OAuthServiceConfig,
    OAuthTokenSet,
)
from src.brain.auth.registration_engine import (
    RegistrationEngine,
    RegistrationFlow,
    RegistrationStep,
    StepType,
)

# CI detection — used to skip tests that require local machine features
_IN_CI = is_ci() or os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"


# ── Credential ──────────────────────────────────────────────────────────


class TestCredential:
    def test_not_expired_when_no_expiry(self):
        cred = Credential(service="test", credential_type="api_key", data={"key": "val"})
        assert not cred.is_expired
        assert cred.ttl_seconds is None

    def test_expired_when_past(self):
        cred = Credential(
            service="test",
            credential_type="api_key",
            data={},
            expires_at=time.time() - 100,
        )
        assert cred.is_expired
        assert cred.ttl_seconds == 0.0

    def test_not_expired_when_future(self):
        cred = Credential(
            service="test",
            credential_type="api_key",
            data={},
            expires_at=time.time() + 3600,
        )
        assert not cred.is_expired
        assert cred.ttl_seconds is not None
        assert cred.ttl_seconds > 3500

    def test_to_dict_and_from_dict(self):
        cred = Credential(
            service="github",
            credential_type="oauth2",
            data={"access_token": "ghp_xxx"},
            metadata={"note": "test"},
        )
        d = cred.to_dict()
        restored = Credential.from_dict(d)
        assert restored.service == "github"
        assert restored.data["access_token"] == "ghp_xxx"
        assert restored.metadata["note"] == "test"


# ── Credential Vault ────────────────────────────────────────────────────


class TestCredentialVault:
    def test_store_and_get(self, tmp_path):
        vault = CredentialVault(vault_dir=tmp_path / "vault")
        vault.store("github", "oauth2", {"token": "abc123"})

        cred = vault.get("github")
        assert cred is not None
        assert cred.data["token"] == "abc123"
        assert cred.credential_type == "oauth2"

    def test_get_nonexistent_returns_none(self, tmp_path):
        vault = CredentialVault(vault_dir=tmp_path / "vault")
        assert vault.get("nonexistent") is None

    def test_get_expired_returns_none(self, tmp_path):
        vault = CredentialVault(vault_dir=tmp_path / "vault")
        vault.store("temp", "api_key", {"key": "x"}, expires_in=0.01)
        time.sleep(0.05)
        assert vault.get("temp") is None
        assert vault.get("temp", allow_expired=True) is not None

    def test_get_data_shortcut(self, tmp_path):
        vault = CredentialVault(vault_dir=tmp_path / "vault")
        vault.store("svc", "api_key", {"api_key": "secret", "region": "us"})
        assert vault.get_data("svc", "api_key") == "secret"
        assert vault.get_data("svc")["region"] == "us"
        assert vault.get_data("nonexistent") is None

    def test_delete(self, tmp_path):
        vault = CredentialVault(vault_dir=tmp_path / "vault")
        vault.store("test", "api_key", {"key": "val"})
        assert vault.delete("test") is True
        assert vault.get("test") is None
        assert vault.delete("test") is False

    def test_list_services(self, tmp_path):
        vault = CredentialVault(vault_dir=tmp_path / "vault")
        vault.store("svc1", "oauth2", {"token": "a"})
        vault.store("svc2", "api_key", {"key": "b"})

        services = vault.list_services()
        names = [s["service"] for s in services]
        assert "svc1" in names
        assert "svc2" in names

    def test_version_bump_on_update(self, tmp_path):
        vault = CredentialVault(vault_dir=tmp_path / "vault")
        vault.store("svc", "api_key", {"key": "v1"})
        cred1 = vault.get("svc")
        assert cred1 is not None
        assert cred1.version == 1

        vault.store("svc", "api_key", {"key": "v2"})
        cred2 = vault.get("svc")
        assert cred2 is not None
        assert cred2.version == 2
        assert cred2.data["key"] == "v2"

    def test_persistence(self, tmp_path):
        vault_dir = tmp_path / "vault"
        vault1 = CredentialVault(vault_dir=vault_dir)
        vault1.store("persistent", "api_key", {"key": "saved"})

        # Create new vault instance (simulates restart)
        vault2 = CredentialVault(vault_dir=vault_dir)
        cred = vault2.get("persistent")
        assert cred is not None
        assert cred.data["key"] == "saved"

    def test_get_expiring_soon(self, tmp_path):
        vault = CredentialVault(vault_dir=tmp_path / "vault")
        vault.store("expiring", "oauth2", {"token": "x"}, expires_in=100)
        vault.store("not_expiring", "oauth2", {"token": "y"}, expires_in=99999)

        expiring = vault.get_expiring_soon(500)
        assert "expiring" in expiring
        assert "not_expiring" not in expiring

    def test_wipe(self, tmp_path):
        vault = CredentialVault(vault_dir=tmp_path / "vault")
        vault.store("s1", "api_key", {"k": "v"})
        vault.store("s2", "api_key", {"k": "v"})
        vault.wipe()
        assert vault.list_services() == []


# ── Keychain Bridge ─────────────────────────────────────────────────────


class TestKeychainBridge:
    def test_available_sources_includes_env(self):
        bridge = KeychainBridge()
        assert KeychainSource.ENVIRONMENT in bridge.available_sources
        assert KeychainSource.DOTENV_FILE in bridge.available_sources

    def test_get_from_env(self):
        bridge = KeychainBridge()
        import os

        os.environ["TEST_ATLAS_KEY_12345"] = "test_value"
        try:
            entry = bridge.get_from_env("TEST_ATLAS_KEY_12345")
            assert entry is not None
            assert entry.secret == "test_value"
            assert entry.source == KeychainSource.ENVIRONMENT
        finally:
            del os.environ["TEST_ATLAS_KEY_12345"]

    def test_get_from_env_missing(self):
        bridge = KeychainBridge()
        entry = bridge.get_from_env("NONEXISTENT_KEY_XYZ_12345")
        assert entry is None

    def test_get_from_dotenv(self, tmp_path):
        dotenv = tmp_path / ".env"
        dotenv.write_text('MY_KEY="my_value"\nOTHER=42\n')

        bridge = KeychainBridge()
        entry = bridge.get_from_dotenv("MY_KEY", dotenv)
        assert entry is not None
        assert entry.secret == "my_value"

    def test_search_env(self):
        bridge = KeychainBridge()
        import os

        os.environ["TESTSERVICE_API_KEY"] = "found_it"
        try:
            results = bridge.search(
                "testservice",
                sources={KeychainSource.ENVIRONMENT},
            )
            secrets = [e.secret for e in results if e.secret]
            assert "found_it" in secrets
        finally:
            del os.environ["TESTSERVICE_API_KEY"]


# ── Identity Provider ───────────────────────────────────────────────────


class TestIdentityProviderRegistry:
    @pytest.mark.asyncio
    async def test_register_and_get(self):
        registry = IdentityProviderRegistry()
        manual = ManualApprovalProvider()
        registry.register(manual)

        provider = registry.get(IdentityMethod.MANUAL_APPROVAL)
        assert provider is manual

    @pytest.mark.asyncio
    async def test_get_best_available_returns_manual_as_fallback(self):
        registry = IdentityProviderRegistry()
        manual = ManualApprovalProvider()
        registry.register(manual)

        best = await registry.get_best_available()
        assert best is manual

    @pytest.mark.asyncio
    async def test_manual_approval_creates_challenge(self):
        provider = ManualApprovalProvider()
        challenge = await provider.create_challenge({"action": "test", "service": "test_svc"})
        assert challenge.method == IdentityMethod.MANUAL_APPROVAL
        assert "confirmation" in challenge.instructions.lower()

    @pytest.mark.asyncio
    async def test_dia_eid_cloud_challenge(self):
        provider = DiaEidProvider()
        challenge = await provider.create_challenge({"action": "register"})
        assert challenge.method == IdentityMethod.DIA_EID
        assert challenge.deep_link is not None
        assert "diia://" in challenge.deep_link

    @pytest.mark.asyncio
    async def test_dia_eid_file_challenge(self, tmp_path):
        key_file = tmp_path / "test.jks"
        key_file.write_bytes(b"fake_key")

        provider = DiaEidProvider(key_file=key_file)
        challenge = await provider.create_challenge({"action": "sign"})
        assert challenge.payload["mode"] == "file_based"
        assert challenge.deep_link is None


# ── OAuth Engine ────────────────────────────────────────────────────────


class TestOAuthEngine:
    def test_register_and_list_services(self):
        engine = OAuthEngine()
        config = OAuthServiceConfig(
            service_id="test_svc",
            display_name="Test Service",
            authorize_url="https://example.com/auth",
            token_url="https://example.com/token",
            client_id="cid",
        )
        engine.register_service(config)
        assert "test_svc" in engine.list_services()
        assert engine.get_service("test_svc") is config

    def test_get_authorize_url(self):
        engine = OAuthEngine()
        config = OAuthServiceConfig(
            service_id="test",
            display_name="Test",
            authorize_url="https://example.com/auth",
            token_url="https://example.com/token",
            client_id="my_client",
            scopes=["read", "write"],
        )
        engine.register_service(config)

        url, state = engine.get_authorize_url("test")
        assert "example.com/auth" in url
        assert "client_id=my_client" in url
        assert "scope=read+write" in url
        assert len(state) > 10

    def test_get_authorize_url_pkce(self):
        engine = OAuthEngine()
        config = OAuthServiceConfig(
            service_id="pkce_test",
            display_name="PKCE Test",
            authorize_url="https://example.com/auth",
            token_url="https://example.com/token",
            client_id="client",
            flow=OAuthFlowType.PKCE,
        )
        engine.register_service(config)

        url, _state = engine.get_authorize_url("pkce_test")
        assert "code_challenge=" in url
        assert "code_challenge_method=S256" in url

    def test_token_set_expiry(self):
        tokens = OAuthTokenSet(
            access_token="abc",
            expires_in=3600,
            obtained_at=time.time(),
        )
        assert not tokens.is_expired
        assert tokens.ttl_seconds is not None and tokens.ttl_seconds > 3500

    def test_token_set_expired(self):
        tokens = OAuthTokenSet(
            access_token="abc",
            expires_in=1,
            obtained_at=time.time() - 100,
        )
        assert tokens.is_expired


# ── Registration Engine ─────────────────────────────────────────────────


class TestRegistrationEngine:
    def test_variable_resolution(self, tmp_path):
        vault = CredentialVault(vault_dir=tmp_path / "vault")
        engine = RegistrationEngine(vault=vault)

        result = engine._resolve_value(
            "Hello {{name}}, your key is {{key}}", {"name": "Atlas", "key": "abc"}
        )
        assert result == "Hello Atlas, your key is abc"

    def test_resolve_nested(self, tmp_path):
        vault = CredentialVault(vault_dir=tmp_path / "vault")
        engine = RegistrationEngine(vault=vault)

        result = engine._resolve_value(
            {"email": "{{email}}", "token": "{{token}}"},
            {"email": "a@b.com", "token": "xyz"},
        )
        assert result == {"email": "a@b.com", "token": "xyz"}

    def test_extract_by_path(self, tmp_path):
        vault = CredentialVault(vault_dir=tmp_path / "vault")
        engine = RegistrationEngine(vault=vault)

        data = {"data": {"api_key": "secret123", "nested": {"deep": "value"}}}
        assert engine._extract_by_path(data, "data.api_key") == "secret123"
        assert engine._extract_by_path(data, "data.nested.deep") == "value"
        assert engine._extract_by_path(data, "data.missing") is None

    @pytest.mark.asyncio
    async def test_execute_store_credential(self, tmp_path):
        vault = CredentialVault(vault_dir=tmp_path / "vault")
        engine = RegistrationEngine(vault=vault)

        flow = RegistrationFlow(
            flow_id="test_store",
            service_name="Test",
            steps=[
                RegistrationStep(
                    name="store",
                    step_type=StepType.STORE_CREDENTIAL,
                    credential_service="test_service",
                    credential_type="api_key",
                    credential_data_map={"api_key": "{{api_key}}"},
                ),
            ],
            variables={"api_key": "my_secret_key"},
        )

        result = await engine.execute(flow)
        assert result.success
        assert "test_service" in result.credentials_stored

        cred = vault.get("test_service")
        assert cred is not None
        assert cred.data["api_key"] == "my_secret_key"

    @pytest.mark.asyncio
    async def test_execute_extract_step(self, tmp_path):
        vault = CredentialVault(vault_dir=tmp_path / "vault")
        engine = RegistrationEngine(vault=vault)

        flow = RegistrationFlow(
            flow_id="test_extract",
            service_name="Test",
            steps=[
                RegistrationStep(
                    name="store",
                    step_type=StepType.STORE_CREDENTIAL,
                    credential_service="test_svc",
                    credential_type="api_key",
                    credential_data_map={"key": "{{value}}"},
                ),
            ],
            variables={"value": "extracted_value"},
        )

        result = await engine.execute(flow)
        assert result.success

    @pytest.mark.asyncio
    async def test_execute_wait_step(self, tmp_path):
        vault = CredentialVault(vault_dir=tmp_path / "vault")
        engine = RegistrationEngine(vault=vault)

        flow = RegistrationFlow(
            flow_id="test_wait",
            service_name="Test",
            steps=[
                RegistrationStep(
                    name="wait",
                    step_type=StepType.WAIT,
                    wait_seconds=0.1,
                ),
            ],
        )

        start = time.time()
        result = await engine.execute(flow)
        assert result.success
        assert time.time() - start >= 0.1


# ── Flow Templates ──────────────────────────────────────────────────────


class TestFlowTemplates:
    def test_create_api_key_flow(self):
        from src.brain.auth.flow_templates import create_api_key_registration

        flow = create_api_key_registration(
            service_id="test_api",
            service_name="Test API",
            register_url="https://example.com/register",
        )
        assert flow.flow_id == "register_test_api"
        assert len(flow.steps) >= 3
        step_types = [s.step_type for s in flow.steps]
        assert StepType.USER_INPUT in step_types
        assert StepType.HTTP_JSON in step_types
        assert StepType.STORE_CREDENTIAL in step_types

    def test_create_oauth2_flow(self):
        from src.brain.auth.flow_templates import create_oauth2_registration

        flow = create_oauth2_registration(
            service_id="test_oauth",
            service_name="Test OAuth",
            registration_url="https://example.com/register",
            authorize_url="https://example.com/auth",
            token_url="https://example.com/token",
            scopes=["read"],
        )
        assert flow.flow_id == "register_oauth_test_oauth"
        step_types = [s.step_type for s in flow.steps]
        assert StepType.OAUTH_REGISTER in step_types
        assert StepType.CALLBACK_LISTEN in step_types
        assert StepType.STORE_CREDENTIAL in step_types

    def test_create_government_portal_flow(self):
        from src.brain.auth.flow_templates import create_government_portal_registration

        flow = create_government_portal_registration(
            service_id="gov_test",
            service_name="Gov Test Portal",
            portal_url="https://portal.gov.test",
            identity_method="dia_eid",
        )
        assert flow.requires_identity
        step_types = [s.step_type for s in flow.steps]
        assert StepType.IDENTITY_VERIFY in step_types
        assert StepType.STORE_CREDENTIAL in step_types

    def test_create_web_form_flow(self):
        from src.brain.auth.flow_templates import create_web_form_registration

        flow = create_web_form_registration(
            service_id="web_test",
            service_name="Web Test",
            form_url="https://example.com/signup",
            fields={"email": "Email", "name": "Name"},
        )
        step_types = [s.step_type for s in flow.steps]
        assert StepType.HTTP_GET in step_types
        assert StepType.EXTRACT in step_types
        assert StepType.HTTP_POST in step_types


# ── Auth Manager Integration ────────────────────────────────────────────


class TestAuthManager:
    def test_initialization(self, tmp_path):
        with patch("src.brain.auth.credential_vault.CredentialVault") as MockVault:
            MockVault.return_value = CredentialVault(vault_dir=tmp_path / "vault")
            from src.brain.auth.auth_manager import AuthManager

            auth = AuthManager()
            assert auth.vault is not None
            assert auth.keychain is not None
            assert auth.identity is not None
            assert auth.oauth is not None

    def test_find_credential_from_vault(self, tmp_path):
        from src.brain.auth.auth_manager import AuthManager

        auth = AuthManager()
        auth.vault = CredentialVault(vault_dir=tmp_path / "vault")
        auth.vault.store("test_svc", "api_key", {"api_key": "secret"})

        result = auth.find_credential("test_svc")
        assert result is not None
        assert result["source"] == "vault"
        assert result["data"]["api_key"] == "secret"

    def test_find_credential_not_found(self, tmp_path):
        from src.brain.auth.auth_manager import AuthManager

        auth = AuthManager()
        auth.vault = CredentialVault(vault_dir=tmp_path / "vault")

        result = auth.find_credential("nonexistent")
        assert result is None

    def test_store_and_delete_credential(self, tmp_path):
        from src.brain.auth.auth_manager import AuthManager

        auth = AuthManager()
        auth.vault = CredentialVault(vault_dir=tmp_path / "vault")

        auth.store_credential("svc", "api_key", {"key": "val"})
        assert auth.find_credential("svc") is not None

        auth.delete_credential("svc")
        assert auth.find_credential("svc") is None

    def test_list_credentials(self, tmp_path):
        from src.brain.auth.auth_manager import AuthManager

        auth = AuthManager()
        auth.vault = CredentialVault(vault_dir=tmp_path / "vault")
        auth.store_credential("a", "api_key", {"k": "1"})
        auth.store_credential("b", "oauth2", {"t": "2"})

        listing = auth.list_credentials()
        names = [s["service"] for s in listing]
        assert "a" in names
        assert "b" in names

    def test_status(self, tmp_path):
        from src.brain.auth.auth_manager import AuthManager

        auth = AuthManager()
        auth.vault = CredentialVault(vault_dir=tmp_path / "vault")

        status = auth.status()
        assert "vault" in status
        assert "keychain" in status
        assert "identity" in status
        assert "oauth" in status
        assert "refresher" in status
        assert "access_policy" in status
        assert status["access_policy"]["level"] in {"full", "restricted", "none"}

    def test_configure_oauth_service(self, tmp_path):
        from src.brain.auth.auth_manager import AuthManager

        auth = AuthManager()
        auth.configure_oauth_service(
            {
                "service_id": "test_oauth",
                "display_name": "Test",
                "authorize_url": "https://example.com/auth",
                "token_url": "https://example.com/token",
                "client_id": "client123",
                "scopes": ["read"],
            }
        )
        assert "test_oauth" in auth.oauth.list_services()


# ── Access Policy ───────────────────────────────────────────────────────


class TestAccessPolicy:
    def test_load_full_from_env(self, monkeypatch):
        from src.brain.auth.access_policy import AccessLevel, load_access_policy

        monkeypatch.setenv("ATLAS_KEYCHAIN_ACCESS", "full")
        policy = load_access_policy()
        assert policy.level == AccessLevel.FULL
        assert policy.is_full_access
        assert policy.can_auto_discover
        assert policy.can_auto_import
        assert policy.can_auto_use
        assert policy.can_store
        assert policy.can_delete
        assert policy.can_export

    def test_load_none_by_default(self, monkeypatch):
        from src.brain.auth.access_policy import AccessLevel, load_access_policy

        monkeypatch.delenv("ATLAS_KEYCHAIN_ACCESS", raising=False)
        policy = load_access_policy()
        assert policy.level == AccessLevel.NONE
        assert policy.is_disabled
        assert not policy.can_auto_discover

    def test_load_restricted_from_config(self, monkeypatch):
        from src.brain.auth.access_policy import AccessLevel, load_access_policy

        monkeypatch.delenv("ATLAS_KEYCHAIN_ACCESS", raising=False)
        config = {
            "auth": {
                "access_policy": {
                    "level": "restricted",
                    "can_auto_discover": True,
                    "can_auto_use": False,
                }
            }
        }
        policy = load_access_policy(config)
        assert policy.level == AccessLevel.RESTRICTED
        assert policy.is_restricted
        assert policy.can_auto_discover
        assert not policy.can_auto_use

    def test_env_overrides_config(self, monkeypatch):
        from src.brain.auth.access_policy import AccessLevel, load_access_policy

        monkeypatch.setenv("ATLAS_KEYCHAIN_ACCESS", "full")
        config = {"auth": {"access_policy": {"level": "none"}}}
        policy = load_access_policy(config)
        assert policy.level == AccessLevel.FULL  # env wins

    def test_invalid_level_falls_back_to_none(self, monkeypatch):
        from src.brain.auth.access_policy import AccessLevel, load_access_policy

        monkeypatch.setenv("ATLAS_KEYCHAIN_ACCESS", "banana")
        policy = load_access_policy()
        assert policy.level == AccessLevel.NONE

    def test_is_credential_allowed_full(self):
        from src.brain.auth.access_policy import (
            AccessLevel,
            AccessPolicy,
            CredentialCategory,
        )

        policy = AccessPolicy(level=AccessLevel.FULL)
        assert policy.is_credential_allowed("github", CredentialCategory.API_KEY)
        assert policy.is_credential_allowed("anything")

    def test_is_credential_allowed_full_with_blocked(self):
        from src.brain.auth.access_policy import (
            AccessLevel,
            AccessPolicy,
        )

        policy = AccessPolicy(
            level=AccessLevel.FULL,
            blocked_services={"super_secret"},
        )
        assert policy.is_credential_allowed("github")
        assert not policy.is_credential_allowed("super_secret")

    def test_is_credential_allowed_none(self):
        from src.brain.auth.access_policy import AccessLevel, AccessPolicy

        policy = AccessPolicy(level=AccessLevel.NONE)
        assert not policy.is_credential_allowed("github")

    def test_is_credential_allowed_restricted(self):
        from src.brain.auth.access_policy import (
            AccessLevel,
            AccessPolicy,
            CredentialCategory,
        )

        policy = AccessPolicy(
            level=AccessLevel.RESTRICTED,
            allowed_categories={CredentialCategory.API_KEY},
        )
        assert policy.is_credential_allowed("github", CredentialCategory.API_KEY)
        assert not policy.is_credential_allowed("github", CredentialCategory.PASSWORD)


class TestCredentialCategorization:
    def test_categorize_api_key(self):
        from src.brain.auth.access_policy import CredentialCategory, categorize_credential

        cat, conf = categorize_credential("GOOGLE_MAPS_API_KEY")
        assert cat == CredentialCategory.API_KEY
        assert conf > 0.0

    def test_categorize_ide_token(self):
        from src.brain.auth.access_policy import CredentialCategory, categorize_credential

        cat, _conf = categorize_credential("Windsurf Safe Storage")
        assert cat == CredentialCategory.IDE_TOKEN

    def test_categorize_ai_token(self):
        from src.brain.auth.access_policy import CredentialCategory, categorize_credential

        cat, _conf = categorize_credential("OPENROUTER_API_KEY")
        # Could be API_KEY or AI_TOKEN depending on pattern matching
        assert cat in {CredentialCategory.API_KEY, CredentialCategory.AI_TOKEN}

    def test_categorize_wifi(self):
        from src.brain.auth.access_policy import CredentialCategory, categorize_credential

        cat, _conf = categorize_credential("AirPort")
        assert cat == CredentialCategory.WIFI_PASSWORD

    def test_categorize_ssh(self):
        from src.brain.auth.access_policy import CredentialCategory, categorize_credential

        cat, _ = categorize_credential("ssh", "id_ed25519")
        assert cat == CredentialCategory.SSH_KEY

    def test_categorize_unknown(self):
        from src.brain.auth.access_policy import CredentialCategory, categorize_credential

        cat, conf = categorize_credential("random_thing_xyz_123")
        assert cat == CredentialCategory.CUSTOM
        assert conf == 0.1  # low confidence default


class TestKeychainBridgeDiscovery:
    def test_discover_all_returns_list(self):
        bridge = KeychainBridge()
        results = bridge.discover_all()
        assert isinstance(results, list)
        # In CI, may find 0 entries (no keychain, minimal env)
        if not _IN_CI:
            assert len(results) > 0

    def test_discover_all_caching(self):
        bridge = KeychainBridge()
        results1 = bridge.discover_all()
        results2 = bridge.discover_all()
        assert len(results1) == len(results2)
        # Force refresh
        results3 = bridge.discover_all(force_refresh=True)
        assert isinstance(results3, list)

    def test_invalidate_cache(self):
        bridge = KeychainBridge()
        bridge.discover_all()
        assert bridge._discovery_cache is not None
        bridge.invalidate_cache()
        assert bridge._discovery_cache is None

    def test_smart_search(self):
        bridge = KeychainBridge()
        results = bridge.smart_search("copilot")
        assert isinstance(results, list)
        # In CI, COPILOT_API_KEY may not exist

    def test_bulk_export(self):
        bridge = KeychainBridge()
        export = bridge.bulk_export()
        assert isinstance(export, dict)
        # In CI, may have no sources with entries
        if not _IN_CI:
            assert len(export) > 0

    def test_get_all_api_keys(self):
        bridge = KeychainBridge()
        keys = bridge.get_all_api_keys()
        assert isinstance(keys, list)

    def test_scan_environment(self):
        bridge = KeychainBridge()
        entries = bridge._scan_environment()
        assert isinstance(entries, list)
        # Check that obvious non-secrets like PATH are excluded
        service_names = {e.service for e in entries}
        assert "PATH" not in service_names

    def test_clean_keychain_value(self):
        assert KeychainBridge._clean_keychain_value("") == ""
        assert KeychainBridge._clean_keychain_value("<NULL>") == ""
        assert KeychainBridge._clean_keychain_value('"hello"') == "hello"
        assert KeychainBridge._clean_keychain_value("plain") == "plain"


class TestAuthManagerWithPolicy:
    def test_full_access_init(self, tmp_path, monkeypatch):
        from src.brain.auth.auth_manager import AuthManager

        monkeypatch.setenv("ATLAS_KEYCHAIN_ACCESS", "full")
        auth = AuthManager()
        auth.vault = CredentialVault(vault_dir=tmp_path / "vault")
        assert auth.policy.is_full_access
        assert auth.policy.can_auto_use

    def test_none_access_init(self, tmp_path, monkeypatch):
        from src.brain.auth.auth_manager import AuthManager

        monkeypatch.setenv("ATLAS_KEYCHAIN_ACCESS", "none")
        auth = AuthManager()
        assert auth.policy.is_disabled

    def test_ensure_full_access(self, monkeypatch):
        from src.brain.auth.auth_manager import AuthManager

        monkeypatch.setenv("ATLAS_KEYCHAIN_ACCESS", "full")
        auth = AuthManager()
        assert auth.ensure_full_access()

    def test_ensure_full_access_fails_when_none(self, monkeypatch):
        from src.brain.auth.auth_manager import AuthManager

        monkeypatch.setenv("ATLAS_KEYCHAIN_ACCESS", "none")
        auth = AuthManager()
        assert not auth.ensure_full_access()

    def test_discover_all_credentials(self, tmp_path, monkeypatch):
        from src.brain.auth.auth_manager import AuthManager

        monkeypatch.setenv("ATLAS_KEYCHAIN_ACCESS", "full")
        auth = AuthManager()
        auth.vault = CredentialVault(vault_dir=tmp_path / "vault")

        discovered = auth.discover_all_credentials()
        assert isinstance(discovered, list)
        # Each entry should have required keys
        if discovered:
            entry = discovered[0]
            assert "service" in entry
            assert "source" in entry
            assert "category" in entry
            assert "has_secret" in entry
            assert "allowed" in entry

    def test_discover_blocked_when_no_policy(self, monkeypatch):
        from src.brain.auth.auth_manager import AuthManager

        monkeypatch.setenv("ATLAS_KEYCHAIN_ACCESS", "none")
        auth = AuthManager()
        discovered = auth.discover_all_credentials()
        assert discovered == []

    def test_get_best_credential_for(self, tmp_path, monkeypatch):
        from src.brain.auth.auth_manager import AuthManager

        monkeypatch.setenv("ATLAS_KEYCHAIN_ACCESS", "full")
        auth = AuthManager()
        auth.vault = CredentialVault(vault_dir=tmp_path / "vault")

        # Store something in vault
        auth.vault.store("test_service", "api_key", {"secret": "test123"})
        result = auth.get_best_credential_for("test_service")
        assert result is not None
        assert result["source"] == "vault"

    def test_get_best_credential_blocked_when_no_auto_use(self, monkeypatch):
        from src.brain.auth.auth_manager import AuthManager

        monkeypatch.setenv("ATLAS_KEYCHAIN_ACCESS", "none")
        auth = AuthManager()
        result = auth.get_best_credential_for("anything")
        assert result is None

    def test_get_credential_inventory(self, tmp_path, monkeypatch):
        from src.brain.auth.auth_manager import AuthManager

        monkeypatch.setenv("ATLAS_KEYCHAIN_ACCESS", "full")
        auth = AuthManager()
        auth.vault = CredentialVault(vault_dir=tmp_path / "vault")

        inventory = auth.get_credential_inventory()
        assert "total" in inventory
        assert "categories" in inventory
        assert "details" in inventory

    def test_auto_import_all(self, tmp_path, monkeypatch):
        from src.brain.auth.auth_manager import AuthManager

        monkeypatch.setenv("ATLAS_KEYCHAIN_ACCESS", "full")
        auth = AuthManager()
        auth.vault = CredentialVault(vault_dir=tmp_path / "vault")

        result = auth.auto_import_all()
        assert "imported" in result
        assert "total_scanned" in result
        assert "vault_total" in result

    def test_status_includes_policy(self, tmp_path, monkeypatch):
        from src.brain.auth.auth_manager import AuthManager

        monkeypatch.setenv("ATLAS_KEYCHAIN_ACCESS", "full")
        auth = AuthManager()
        auth.vault = CredentialVault(vault_dir=tmp_path / "vault")

        status = auth.status()
        assert "access_policy" in status
        assert status["access_policy"]["level"] == "full"
        assert status["access_policy"]["can_auto_discover"] is True
        assert status["access_policy"]["can_auto_use"] is True

    def test_status_includes_environment(self, tmp_path, monkeypatch):
        from src.brain.auth.auth_manager import AuthManager

        monkeypatch.setenv("ATLAS_KEYCHAIN_ACCESS", "full")
        auth = AuthManager()
        auth.vault = CredentialVault(vault_dir=tmp_path / "vault")

        status = auth.status()
        assert "environment" in status
        env_info = status["environment"]
        assert "is_ci" in env_info
        assert "ci_provider" in env_info
        assert "runner_os" in env_info
        assert "available_features" in env_info
        assert isinstance(env_info["available_features"], list)


class TestCICompatibility:
    """Tests that verify CI/CD graceful degradation."""

    def test_ci_detection_module_imports(self):
        from src.brain.auth.ci_compat import (
            CIEnvironment,
            CIProvider,
            detect_ci_environment,
            is_ci,
        )

        assert callable(detect_ci_environment)
        assert callable(is_ci)
        assert CIProvider.LOCAL.value == "local"
        assert CIProvider.GITHUB_ACTIONS.value == "github_actions"
        # CIEnvironment should be a dataclass
        env = detect_ci_environment()
        assert isinstance(env, CIEnvironment)

    def test_ci_env_has_expected_fields(self):
        from src.brain.auth.ci_compat import detect_ci_environment

        env = detect_ci_environment()
        assert isinstance(env.is_ci, bool)
        assert isinstance(env.has_macos_keychain, bool)
        assert isinstance(env.has_system_password, bool)
        assert isinstance(env.has_browser_stores, bool)
        assert isinstance(env.has_sudo, bool)
        assert isinstance(env.runner_os, str)
        assert isinstance(env.available_features, list)

    def test_ci_env_always_has_vault_and_env(self):
        from src.brain.auth.ci_compat import detect_ci_environment

        env = detect_ci_environment()
        features = env.available_features
        assert "credential_vault" in features
        assert "env_vars" in features
        assert "dotenv" in features

    def test_simulated_ci_keychain_bridge(self, monkeypatch):
        """Simulate CI environment and verify KeychainBridge degrades gracefully."""
        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("GITHUB_ACTIONS", "true")

        bridge = KeychainBridge()
        assert bridge.is_ci
        # Only env + dotenv should be available in CI
        assert KeychainSource.ENVIRONMENT in bridge.available_sources
        assert KeychainSource.DOTENV_FILE in bridge.available_sources
        assert KeychainSource.MACOS_KEYCHAIN not in bridge.available_sources
        assert KeychainSource.CHROME_PASSWORDS not in bridge.available_sources

    def test_simulated_ci_discover_all(self, monkeypatch):
        """discover_all should succeed in CI (even if 0 results)."""
        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("GITHUB_ACTIONS", "true")

        bridge = KeychainBridge()
        results = bridge.discover_all()
        assert isinstance(results, list)

    def test_simulated_ci_auth_manager_init(self, monkeypatch):
        """AuthManager should init without errors in CI."""
        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("ATLAS_KEYCHAIN_ACCESS", "full")

        from src.brain.auth.auth_manager import AuthManager

        auth = AuthManager()
        assert auth.policy.is_full_access
        # In CI, discovery should be marked done (skipped)
        assert auth._discovery_done is True

    def test_simulated_ci_auth_manager_none_access(self, monkeypatch):
        """AuthManager with none access works in CI."""
        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("ATLAS_KEYCHAIN_ACCESS", "none")

        from src.brain.auth.auth_manager import AuthManager

        auth = AuthManager()
        assert auth.policy.is_disabled
        assert auth.discover_all_credentials() == []

    def test_simulated_ci_system_access(self, monkeypatch):
        """SystemAccess should degrade gracefully in CI."""
        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("GITHUB_ACTIONS", "true")

        from src.brain.auth.system_access import SystemAccess

        access = SystemAccess()
        assert access.is_ci
        # Keychain unlock should return False gracefully
        assert access.unlock_keychain() is False
        status = access.status()
        assert status["is_ci"] is True
        assert status["ci_provider"] == "github_actions"
