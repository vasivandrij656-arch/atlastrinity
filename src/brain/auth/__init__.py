"""AtlasTrinity Universal Authentication & Auto-Registration System

Hyper-universal authentication system that allows Atlas
to automatically register and obtain access to any service.

Modules:
    access_policy     - Atlas access policy to key stores (FULL/RESTRICTED/NONE)
    ci_compat         - CI/CD environment detection and graceful degradation
    credential_vault  - Encrypted storage for tokens and credentials
    keychain_bridge   - Integration with macOS Keychain, Google Keychain, etc.
    identity_provider - Universal identity verification providers (Diia, BankID, NFC)
    oauth_engine      - Universal OAuth2/OIDC engine
    registration_engine - Automatic registration on arbitrary platforms
    auth_manager      - Central authentication coordinator
    system_access     - Privileged operations using system credentials

Access Policy:
    Set ATLAS_KEYCHAIN_ACCESS=full in .env to grant Atlas full keychain access.

CI/CD:
    Auto-detects CI environments (GitHub Actions, GitLab CI, etc.)
    and gracefully degrades — no keychain, no browser stores, no sudo.
    Vault and env/dotenv sources remain fully functional.
"""

from src.brain.auth.access_policy import AccessLevel, AccessPolicy, load_access_policy
from src.brain.auth.auth_manager import AuthManager
from src.brain.auth.ci_compat import CIEnvironment, CIProvider, detect_ci_environment, is_ci

__all__ = [
    "AccessLevel",
    "AccessPolicy",
    "AuthManager",
    "CIEnvironment",
    "CIProvider",
    "detect_ci_environment",
    "is_ci",
    "load_access_policy",
]
