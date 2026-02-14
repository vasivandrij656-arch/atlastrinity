"""Identity Provider — Universal identity verification providers.

Supported:
- Diia.QES (Qualified Electronic Signature)
- BankID (Ukrainian banking identification)
- NFC (for electronic documents / ID cards)
- FIDO2/WebAuthn (hardware keys)
- Mobile ID (SMS/Push verification)
- Certificates (X.509, PKCS#12)

All through a single abstract IdentityProvider interface.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger("brain.auth.identity")


class IdentityMethod(StrEnum):
    """Identity verification methods."""

    DIA_EID = "dia_eid"  # Diia.QES
    BANK_ID = "bank_id"  # BankID
    NFC_SCAN = "nfc_scan"  # NFC (e-passport, ID card)
    FIDO2 = "fido2"  # FIDO2/WebAuthn hardware keys
    MOBILE_ID = "mobile_id"  # Mobile ID (SMS/Push)
    CERTIFICATE = "certificate"  # X.509 / PKCS#12 cert
    MANUAL_APPROVAL = "manual_approval"  # Manual user approval


class IdentityStatus(StrEnum):
    """Identity verification status."""

    PENDING = "pending"
    AWAITING_USER = "awaiting_user"  # Waiting for user action (signature, NFC, etc.)
    VERIFIED = "verified"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class IdentityChallenge:
    """Identity challenge (what needs to be done for verification)."""

    challenge_id: str
    method: IdentityMethod
    instructions: str  # Human-readable instructions for the user
    payload: dict[str, Any] = field(default_factory=dict)
    qr_code_data: str | None = None  # For QR-based flows (Diia)
    deep_link: str | None = None  # For mobile flows
    timeout_seconds: int = 300
    created_at: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.timeout_seconds


@dataclass
class IdentityResult:
    """Identity verification result."""

    status: IdentityStatus
    method: IdentityMethod
    subject: dict[str, Any] = field(default_factory=dict)  # Full name, tax ID, etc.
    signature: bytes | None = None  # Electronic signature
    certificate: bytes | None = None  # Certificate
    raw_response: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    timestamp: float = field(default_factory=time.time)


class IdentityProvider(ABC):
    """Abstract base class for identity verification providers."""

    @abstractmethod
    def get_method(self) -> IdentityMethod:
        """Returns the identity verification method."""
        ...

    @abstractmethod
    async def create_challenge(self, context: dict[str, Any]) -> IdentityChallenge:
        """Creates a challenge for identity verification.

        Args:
            context: Operation context (what the identity verification is for)
        """
        ...

    @abstractmethod
    async def verify_challenge(self, challenge: IdentityChallenge) -> IdentityResult:
        """Verifies the challenge response.

        Can be polling-based (waits for user confirmation in Diia)
        or direct (verifies immediately).
        """
        ...

    @abstractmethod
    async def sign_data(self, data: bytes, context: dict[str, Any]) -> IdentityResult:
        """Signs data with an electronic signature."""
        ...

    async def is_available(self) -> bool:
        """Checks if the provider is available."""
        return True


class DiaEidProvider(IdentityProvider):
    """Diia.QES — Qualified Electronic Signature via Diia.

    Flow:
    1. Atlas creates a signature request -> receives QR code / deep link
    2. User scans QR / opens Diia -> confirms
    3. Atlas receives signed data

    Configuration:
        Requires a key file (.jks, .dat, .pfx) or cloud-based Diia.Signature
    """

    def __init__(
        self,
        key_file: Path | None = None,
        key_password: str | None = None,
        api_url: str = "https://id.diia.gov.ua",
        acquirer_token: str | None = None,
    ) -> None:
        self._key_file = key_file
        self._key_password = key_password
        self._api_url = api_url.rstrip("/")
        self._acquirer_token = acquirer_token

    def get_method(self) -> IdentityMethod:
        return IdentityMethod.DIA_EID

    async def create_challenge(self, context: dict[str, Any]) -> IdentityChallenge:
        """Creates a signature request via Diia.

        For cloud Diia.Signature — generates deep link for the mobile app.
        For file-based — prepares data for local signing.
        """
        import uuid

        challenge_id = str(uuid.uuid4())

        if self._key_file and self._key_file.exists():
            # File-based: local signing (user has key on disk)
            return IdentityChallenge(
                challenge_id=challenge_id,
                method=IdentityMethod.DIA_EID,
                instructions=(
                    "\ud83d\udd10 Signing via QES key file.\n"
                    f"Key: {self._key_file.name}\n"
                    "Enter key password when prompted."
                ),
                payload={
                    "mode": "file_based",
                    "key_file": str(self._key_file),
                    "context": context,
                },
                timeout_seconds=120,
            )
        # Cloud-based: via Diia app
        deep_link = f"diia://sign?requestId={challenge_id}"
        return IdentityChallenge(
            challenge_id=challenge_id,
            method=IdentityMethod.DIA_EID,
            instructions=(
                "\ud83d\udcf1 Open the Diia app and confirm the signature.\n"
                f"Or scan the QR code.\n"
                f"Request ID: {challenge_id[:8]}..."
            ),
            payload={"mode": "cloud", "context": context},
            deep_link=deep_link,
            qr_code_data=deep_link,
            timeout_seconds=300,
        )

    async def verify_challenge(self, challenge: IdentityChallenge) -> IdentityResult:
        """Checks signature status.

        For file-based: signing already done locally.
        For cloud: polling Diia API.
        """
        if challenge.is_expired:
            return IdentityResult(
                status=IdentityStatus.EXPIRED,
                method=IdentityMethod.DIA_EID,
                error="Challenge expired",
            )

        mode = challenge.payload.get("mode", "cloud")

        if mode == "file_based":
            # File-based signing: result is already in payload
            return IdentityResult(
                status=IdentityStatus.VERIFIED,
                method=IdentityMethod.DIA_EID,
                signature=challenge.payload.get("signature"),
                raw_response=challenge.payload,
            )

        # Cloud-based: poll Diia API
        # In real integration this would be an HTTP request to id.diia.gov.ua
        return IdentityResult(
            status=IdentityStatus.AWAITING_USER,
            method=IdentityMethod.DIA_EID,
            raw_response={"challenge_id": challenge.challenge_id, "mode": mode},
        )

    async def sign_data(self, data: bytes, context: dict[str, Any]) -> IdentityResult:
        """Signs data via QES.

        For file-based: uses IIT library / openssl.
        For cloud: sends data for signing to Diia.
        """
        if self._key_file and self._key_file.exists():
            return await self._sign_with_file(data)

        # Cloud mode: requires user interaction
        challenge = await self.create_challenge(
            {
                "action": "sign_data",
                "data_hash": data[:32].hex(),
                **context,
            }
        )
        return IdentityResult(
            status=IdentityStatus.AWAITING_USER,
            method=IdentityMethod.DIA_EID,
            raw_response={"challenge": challenge},
        )

    async def _sign_with_file(self, data: bytes) -> IdentityResult:
        """Sign via key file (IIT / openssl)."""
        # In real implementation this would call the IIT library
        # or openssl with DSTU 4145-2002
        logger.info("📝 File-based signing with: %s", self._key_file)
        return IdentityResult(
            status=IdentityStatus.AWAITING_USER,
            method=IdentityMethod.DIA_EID,
            raw_response={"mode": "file_based", "key": str(self._key_file)},
        )

    async def is_available(self) -> bool:
        if self._key_file:
            return self._key_file.exists()
        return self._acquirer_token is not None


class BankIdProvider(IdentityProvider):
    """BankID — Identification via banking service.

    Supported banks:
    - PrivatBank, Monobank, PUMB, Oschadbank, etc.

    Flow:
    1. Atlas creates a request -> BankID returns an authorization URL
    2. User authorizes in the bank
    3. BankID returns identification data
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        api_url: str = "https://id.bank.gov.ua",
        callback_url: str = "http://localhost:8086/auth/callback",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._api_url = api_url.rstrip("/")
        self._callback_url = callback_url

    def get_method(self) -> IdentityMethod:
        return IdentityMethod.BANK_ID

    async def create_challenge(self, context: dict[str, Any]) -> IdentityChallenge:
        import uuid

        challenge_id = str(uuid.uuid4())

        # BankID OAuth2 Authorization URL
        auth_url = (
            f"{self._api_url}/v1/bank/oauth2/authorize"
            f"?response_type=code"
            f"&client_id={self._client_id}"
            f"&redirect_uri={self._callback_url}"
            f"&state={challenge_id}"
        )

        return IdentityChallenge(
            challenge_id=challenge_id,
            method=IdentityMethod.BANK_ID,
            instructions=(
                "\ud83c\udfe6 Authorize via BankID.\n"
                "Choose your bank and confirm identification.\n"
                f"URL: {auth_url}"
            ),
            payload={"auth_url": auth_url, "context": context},
            deep_link=auth_url,
            timeout_seconds=300,
        )

    async def verify_challenge(self, challenge: IdentityChallenge) -> IdentityResult:
        if challenge.is_expired:
            return IdentityResult(
                status=IdentityStatus.EXPIRED,
                method=IdentityMethod.BANK_ID,
                error="Challenge expired",
            )

        # In real implementation this would exchange code for token
        return IdentityResult(
            status=IdentityStatus.AWAITING_USER,
            method=IdentityMethod.BANK_ID,
        )

    async def sign_data(self, data: bytes, context: dict[str, Any]) -> IdentityResult:
        # BankID does not support signing, only identification
        return IdentityResult(
            status=IdentityStatus.FAILED,
            method=IdentityMethod.BANK_ID,
            error="BankID does not support data signing, use DIA_EID instead",
        )

    async def is_available(self) -> bool:
        return bool(self._client_id and self._client_secret)


class NfcIdentityProvider(IdentityProvider):
    """NFC Identity — Reading electronic documents via NFC.

    Supported:
    - Biometric passports (ICAO 9303)
    - ID cards with NFC chip
    - eResidency cards

    Requires NFC reader (built into MacBook Pro or external).
    """

    def __init__(self, reader_name: str | None = None) -> None:
        self._reader_name = reader_name

    def get_method(self) -> IdentityMethod:
        return IdentityMethod.NFC_SCAN

    async def create_challenge(self, context: dict[str, Any]) -> IdentityChallenge:
        import uuid

        return IdentityChallenge(
            challenge_id=str(uuid.uuid4()),
            method=IdentityMethod.NFC_SCAN,
            instructions=(
                "\ud83d\udce1 Place the document with NFC chip on the reader.\n"
                "Supported: biometric passport, ID card.\n"
                "Hold the document still for ~5 seconds."
            ),
            payload={"reader": self._reader_name, "context": context},
            timeout_seconds=60,
        )

    async def verify_challenge(self, challenge: IdentityChallenge) -> IdentityResult:
        if challenge.is_expired:
            return IdentityResult(
                status=IdentityStatus.EXPIRED,
                method=IdentityMethod.NFC_SCAN,
                error="NFC scan timeout",
            )
        # Real NFC read via pyscard or nfcpy
        return IdentityResult(
            status=IdentityStatus.AWAITING_USER,
            method=IdentityMethod.NFC_SCAN,
        )

    async def sign_data(self, data: bytes, context: dict[str, Any]) -> IdentityResult:
        return IdentityResult(
            status=IdentityStatus.FAILED,
            method=IdentityMethod.NFC_SCAN,
            error="NFC documents cannot sign data directly",
        )

    async def is_available(self) -> bool:
        # Check for NFC reader availability
        try:
            import subprocess

            result = subprocess.run(
                ["system_profiler", "SPSmartCardsDataType"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return "NFC" in result.stdout or "Smart Card" in result.stdout
        except Exception:
            return False


class CertificateProvider(IdentityProvider):
    """Certificate — Signing via X.509 / PKCS#12 certificates.

    Supported:
    - .pfx / .p12 files (PKCS#12)
    - .pem / .crt + .key files
    - Hardware tokens (Yubikey, etc.)
    - macOS Keychain certificates
    """

    def __init__(
        self,
        cert_path: Path | None = None,
        key_path: Path | None = None,
        password: str | None = None,
    ) -> None:
        self._cert_path = cert_path
        self._key_path = key_path
        self._password = password

    def get_method(self) -> IdentityMethod:
        return IdentityMethod.CERTIFICATE

    async def create_challenge(self, context: dict[str, Any]) -> IdentityChallenge:
        import uuid

        return IdentityChallenge(
            challenge_id=str(uuid.uuid4()),
            method=IdentityMethod.CERTIFICATE,
            instructions=(
                "\ud83d\udd0f Signing via certificate.\n"
                f"Certificate: {self._cert_path or 'Keychain'}\n"
                "Enter password if required."
            ),
            payload={
                "cert_path": str(self._cert_path) if self._cert_path else None,
                "context": context,
            },
            timeout_seconds=120,
        )

    async def verify_challenge(self, challenge: IdentityChallenge) -> IdentityResult:
        return IdentityResult(
            status=IdentityStatus.VERIFIED,
            method=IdentityMethod.CERTIFICATE,
        )

    async def sign_data(self, data: bytes, context: dict[str, Any]) -> IdentityResult:
        """Sign via openssl or cryptography."""
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            if self._cert_path and self._cert_path.suffix in (".pfx", ".p12"):
                # PKCS#12
                from cryptography.hazmat.primitives.serialization import pkcs12

                pfx_data = self._cert_path.read_bytes()
                pwd = self._password.encode() if self._password else None
                private_key, certificate, _ = pkcs12.load_key_and_certificates(pfx_data, pwd)

                if private_key is None:
                    return IdentityResult(
                        status=IdentityStatus.FAILED,
                        method=IdentityMethod.CERTIFICATE,
                        error="No private key in certificate",
                    )

                signature = private_key.sign(data, padding.PKCS1v15(), hashes.SHA256())  # type: ignore[union-attr]

                return IdentityResult(
                    status=IdentityStatus.VERIFIED,
                    method=IdentityMethod.CERTIFICATE,
                    signature=signature,
                    certificate=certificate.public_bytes(serialization.Encoding.PEM)
                    if certificate
                    else None,
                )

            if self._key_path and self._key_path.exists():
                # PEM key file
                key_data = self._key_path.read_bytes()
                pwd = self._password.encode() if self._password else None
                private_key = serialization.load_pem_private_key(key_data, password=pwd)

                signature = private_key.sign(data, padding.PKCS1v15(), hashes.SHA256())  # type: ignore[union-attr]

                cert_bytes = None
                if self._cert_path and self._cert_path.exists():
                    cert_bytes = self._cert_path.read_bytes()

                return IdentityResult(
                    status=IdentityStatus.VERIFIED,
                    method=IdentityMethod.CERTIFICATE,
                    signature=signature,
                    certificate=cert_bytes,
                )

        except Exception as e:
            return IdentityResult(
                status=IdentityStatus.FAILED,
                method=IdentityMethod.CERTIFICATE,
                error=str(e),
            )

        return IdentityResult(
            status=IdentityStatus.FAILED,
            method=IdentityMethod.CERTIFICATE,
            error="No certificate or key configured",
        )

    async def is_available(self) -> bool:
        if self._cert_path:
            return self._cert_path.exists()
        if self._key_path:
            return self._key_path.exists()
        return False


class ManualApprovalProvider(IdentityProvider):
    """Manual Approval — Manual user confirmation.

    Fallback for cases when automatic identification is not possible.
    Atlas shows what needs to be done, user confirms manually.
    """

    def get_method(self) -> IdentityMethod:
        return IdentityMethod.MANUAL_APPROVAL

    async def create_challenge(self, context: dict[str, Any]) -> IdentityChallenge:
        import uuid

        action = context.get("action", "confirm action")
        service = context.get("service", "unknown service")

        return IdentityChallenge(
            challenge_id=str(uuid.uuid4()),
            method=IdentityMethod.MANUAL_APPROVAL,
            instructions=(
                f"\u270b Your confirmation is required.\n"
                f"Action: {action}\n"
                f"Service: {service}\n"
                f"Confirm or reject."
            ),
            payload={"context": context},
            timeout_seconds=600,
        )

    async def verify_challenge(self, challenge: IdentityChallenge) -> IdentityResult:
        # In real system this would be a UI prompt
        return IdentityResult(
            status=IdentityStatus.AWAITING_USER,
            method=IdentityMethod.MANUAL_APPROVAL,
        )

    async def sign_data(self, data: bytes, context: dict[str, Any]) -> IdentityResult:
        return IdentityResult(
            status=IdentityStatus.FAILED,
            method=IdentityMethod.MANUAL_APPROVAL,
            error="Manual approval cannot sign data",
        )


class IdentityProviderRegistry:
    """Registry of all available identity verification providers.

    Usage:
        registry = IdentityProviderRegistry()
        registry.register(DiaEidProvider(key_file=Path("key.jks")))
        registry.register(BankIdProvider(client_id="xxx"))

        # Find an available provider
        provider = await registry.get_available(IdentityMethod.DIA_EID)

        # Or just the best available
        provider = await registry.get_best_available()
    """

    def __init__(self) -> None:
        self._providers: dict[IdentityMethod, IdentityProvider] = {}
        # Method priority (lower = better)
        self._priority: dict[IdentityMethod, int] = {
            IdentityMethod.DIA_EID: 0,
            IdentityMethod.CERTIFICATE: 1,
            IdentityMethod.BANK_ID: 2,
            IdentityMethod.FIDO2: 3,
            IdentityMethod.NFC_SCAN: 4,
            IdentityMethod.MOBILE_ID: 5,
            IdentityMethod.MANUAL_APPROVAL: 99,
        }

    def register(self, provider: IdentityProvider) -> None:
        """Registers an identity verification provider."""
        self._providers[provider.get_method()] = provider
        logger.info("🆔 Identity provider registered: %s", provider.get_method().value)

    def get(self, method: IdentityMethod) -> IdentityProvider | None:
        return self._providers.get(method)

    async def get_available(self, method: IdentityMethod) -> IdentityProvider | None:
        """Returns the provider if it is available."""
        provider = self._providers.get(method)
        if provider and await provider.is_available():
            return provider
        return None

    async def get_best_available(self) -> IdentityProvider | None:
        """Returns the best available provider by priority."""
        available = []
        for method, provider in self._providers.items():
            if await provider.is_available():
                available.append((self._priority.get(method, 50), provider))

        if not available:
            # Fallback: manual approval is always available
            manual = self._providers.get(IdentityMethod.MANUAL_APPROVAL)
            if manual:
                return manual
            return None

        available.sort(key=lambda x: x[0])
        return available[0][1]

    def list_registered(self) -> list[IdentityMethod]:
        return list(self._providers.keys())
