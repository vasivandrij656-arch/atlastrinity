"""
GitHub Copilot Token Retriever
==============================

Отримує ghu_ токен для GitHub Copilot API через OAuth Device Flow.
Працює з двома IDE:
  1. VS Code  — через GitHub Copilot App (client_id: Iv1.b507a08c87ecfe98)
  2. Windsurf — витягує токен з локальної БД Windsurf (state.vscdb)

Використання:
  python -m providers.get_copilot_token                        # Інтерактивний режим
  python -m providers.get_copilot_token --method vscode        # OAuth device flow
  python -m providers.get_copilot_token --method windsurf      # Витягнути з Windsurf DB
  python -m providers.get_copilot_token --update-env           # Оновити .env файли автоматично
  python -m providers.get_copilot_token --test                 # Тільки перевірити поточний токен

Автор: AtlasTrinity Team
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import requests

# ─── Constants ───────────────────────────────────────────────────────────────

# GitHub Copilot VS Code App OAuth client ID (public, not a secret)
COPILOT_CLIENT_ID = "Iv1.b507a08c87ecfe98"

GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"
COPILOT_TOKEN_URL_V1 = "https://api.github.com/copilot_internal/v1/token"

# Editor headers that Copilot API expects
COPILOT_HEADERS = {
    "Editor-Version": "vscode/1.85.0",
    "Editor-Plugin-Version": "copilot/1.144.0",
    "User-Agent": "GithubCopilot/1.144.0",
}

# Paths — providers/utils/ is inside project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
GLOBAL_ENV = Path.home() / ".config" / "atlastrinity" / ".env"
PROJECT_ENV = PROJECT_ROOT / ".env"

# IDE database paths (macOS)
VSCODE_STATE_DB = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Code"
    / "User"
    / "globalStorage"
    / "state.vscdb"
)
WINDSURF_STATE_DB = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Windsurf"
    / "User"
    / "globalStorage"
    / "state.vscdb"
)

# ─── Colors ──────────────────────────────────────────────────────────────────


class C:
    """ANSI color codes for terminal output."""

    BOLD = "\033[1m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def info(msg: str) -> None:
    print(f"{C.CYAN}INFO{C.RESET}  {msg}")


def warn(msg: str) -> None:
    print(f"{C.YELLOW}WARN{C.RESET}  {msg}")


def error(msg: str) -> None:
    print(f"{C.RED}ERROR{C.RESET} {msg}")


def step(msg: str) -> None:
    print(f"\n{C.BOLD}{C.GREEN}==>{C.RESET} {C.BOLD}{msg}{C.RESET}")


# ─── HTTP Helpers ────────────────────────────────────────────────────────────


def _post_json(url: str, data: dict) -> dict:
    """POST form-encoded data, return JSON response."""
    resp = requests.post(url, data=data, headers={"Accept": "application/json"}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _get_json(url: str, headers: dict) -> dict:
    """GET with headers, return JSON response."""
    resp = requests.get(url, headers={**headers, "Accept": "application/json"}, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ─── Token Verification ─────────────────────────────────────────────────────


def verify_token(token: str) -> dict | None:
    """Verify a ghu_ token against Copilot API. Returns session data or None."""
    headers = {
        "Authorization": f"token {token}",
        **COPILOT_HEADERS,
    }
    try:
        data = _get_json(COPILOT_TOKEN_URL, headers)
        return data
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else None

        # Fallback to v1 if v2 is not found or fails with certain errors
        if status_code in (404, 403):
            try:
                info("Trying fallback to Copilot Token V1 API...")
                data = _get_json(COPILOT_TOKEN_URL_V1, headers)
                return data
            except Exception:
                pass  # Fall through to original error handling

        if status_code == 403:
            try:
                body = e.response.json() if e.response else {}
                error_msg = body.get("error_details", {}).get("message", body.get("message", ""))
                error(f"403 Forbidden: {error_msg}")
            except Exception:
                error("403 Forbidden: Token rejected by Copilot API")
        elif status_code == 401:
            error("401 Unauthorized: Token is invalid or expired")
        else:
            error(f"HTTP {status_code}: {e}")
        return None
    except Exception as e:
        error(f"Connection error: {e}")
        return None


def print_token_info(data: dict) -> None:
    """Pretty-print Copilot session token info."""
    data.get("sku", "unknown")
    data.get("chat_enabled", False)
    data.get("agent_mode_auto_approval", False)
    data.get("individual", False)
    data.get("endpoints", {}).get("api", "unknown")
    expires = data.get("expires_at", 0)

    (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expires)) if expires else "unknown")


# ─── Method 1: OAuth Device Flow (VS Code scheme) ───────────────────────────


def get_token_oauth_device_flow() -> str | None:
    """
    Get ghu_ token via GitHub Copilot App OAuth Device Flow.

    This is the same flow VS Code uses internally:
    1. Request device code from GitHub
    2. User authorizes in browser
    3. Poll for access token

    Returns ghu_ token or None on failure.
    """
    step("Starting GitHub Copilot OAuth Device Flow")

    # Step 1: Request device code
    try:
        device_data = _post_json(
            GITHUB_DEVICE_CODE_URL,
            {
                "client_id": COPILOT_CLIENT_ID,
                "scope": "copilot",
            },
        )
    except Exception as e:
        error(f"Failed to request device code: {e}")
        return None

    device_code = device_data["device_code"]
    user_code = device_data["user_code"]
    verification_uri = device_data["verification_uri"]
    expires_in = device_data["expires_in"]
    interval = device_data.get("interval", 5)

    # Step 2: Show user code and open browser
    print(f"\n{C.BOLD}ПЕРЕЙДІТЬ ЗА ПОСИЛАННЯМ:{C.RESET} {C.CYAN}{verification_uri}{C.RESET}")
    print(f"{C.BOLD}ВВЕДІТЬ КОД:{C.RESET} {C.YELLOW}{C.BOLD}{user_code}{C.RESET}")
    print(f"{C.DIM}(Код діє {expires_in // 60} хв.){C.RESET}\n")

    # Try to open browser automatically
    try:
        if platform.system() == "Darwin":
            subprocess.run(["open", verification_uri], check=False, capture_output=True)
            info("Браузер відкрито автоматично")
        elif platform.system() == "Linux":
            subprocess.run(["xdg-open", verification_uri], check=False, capture_output=True)
    except Exception:
        pass

    # Step 3: Poll for token

    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)

        try:
            token_data = _post_json(
                GITHUB_ACCESS_TOKEN_URL,
                {
                    "client_id": COPILOT_CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
        except Exception as e:
            error(f"\nPoll error: {e}")
            continue

        if "access_token" in token_data:
            token = token_data["access_token"]
            info(f"Токен отримано: {token[:10]}...{token[-4:]}")
            return token

        err = token_data.get("error", "")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval = token_data.get("interval", interval + 5)
            continue
        if err == "expired_token":
            error("Код авторизації протермінувався. Спробуйте ще раз.")
            return None
        if err == "access_denied":
            error("Авторизацію відхилено користувачем.")
            return None
        error(f"Невідома помилка: {err} - {token_data.get('error_description', '')}")
        return None

    error("Таймаут очікування авторизації.")
    return None


# ─── Method 2: Extract from IDE DB ──────────────────────────────────────────


def _search_db_for_ghu_token(db_path: Path, ide_name: str) -> str | None:
    """
    Search an IDE's state.vscdb for ghu_ tokens.

    Searches in:
    1. All plaintext values (including terminal history)
    2. GitHub auth secret keys (reports if encrypted)

    Returns the most recent valid ghu_ token found, or None.
    """
    if not db_path.exists():
        error(f"{ide_name} DB not found: {db_path}")
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Show GitHub/Copilot related keys for diagnostics
        cursor.execute(
            "SELECT key FROM ItemTable WHERE key LIKE '%github%' OR key LIKE '%copilot%'"
        )
        keys = [row[0] for row in cursor.fetchall()]
        if keys:
            for _ in keys:
                pass

        # Search ALL values for ghu_ tokens (including terminal history, settings, etc.)
        found_tokens: list[str] = []
        cursor.execute("SELECT key, value FROM ItemTable")
        rows = cursor.fetchall()
        info(f"Знайдено {len(rows)} рядків у DB. Шукаю токени...")
        for _, value in rows:
            if isinstance(value, str) and "ghu_" in value:
                for match in re.finditer(r"ghu_[A-Za-z0-9]{36}", value):
                    token = match.group(0)
                    if token not in found_tokens:
                        found_tokens.append(token)

        info(f"Знайдено {len(found_tokens)} потенційних токенів.")

        # Check for encrypted GitHub auth secrets
        cursor.execute("""SELECT key FROM ItemTable WHERE key LIKE '%secret%github%auth%'""")
        secret_rows = cursor.fetchall()
        if secret_rows and not found_tokens:
            warn(f"{ide_name}: GitHub токен зашифрований через Electron safeStorage.")

        # Show logged-in account if available
        cursor.execute("SELECT value FROM ItemTable WHERE key LIKE '%copilot-github%'")
        account_row = cursor.fetchone()
        if account_row:
            info(f"{ide_name} GitHub акаунт: {C.BOLD}{account_row[0]}{C.RESET}")

        conn.close()

        if not found_tokens:
            return None

        # Verify tokens (newest first — last in list is likely most recent)
        for token in reversed(found_tokens):
            data = verify_token(token)
            if data:
                info(f"Валідний токен: {token[:10]}...{token[-4:]}")
                return token
            warn(f"Токен {token[:10]}... невалідний, пробую наступний...")

        return None

    except Exception as e:
        error(f"Помилка читання {ide_name} DB: {e}")
        return None


def get_token_from_windsurf() -> str | None:
    """Try to extract GitHub ghu_ token from Windsurf's state database."""
    step("Searching for GitHub token in Windsurf")
    return _search_db_for_ghu_token(WINDSURF_STATE_DB, "Windsurf")


def get_token_from_vscode() -> str | None:
    """Try to extract GitHub ghu_ token from VS Code's state database."""
    step("Searching for GitHub token in VS Code")
    return _search_db_for_ghu_token(VSCODE_STATE_DB, "VS Code")


# ─── .env Update ─────────────────────────────────────────────────────────────


def _set_env_var(env_path: Path, key: str, value: str) -> bool:
    """Set or replace a single key=value in an .env file. Returns True if changed."""
    if not env_path.exists():
        return False

    content = env_path.read_text()
    pattern = rf"^{re.escape(key)}=.*$"

    if re.search(pattern, content, re.MULTILINE):
        new_content = re.sub(pattern, f"{key}={value}", content, flags=re.MULTILINE)
    else:
        # Key doesn't exist — append it
        if not content.endswith("\n"):
            content += "\n"
        new_content = content + f"{key}={value}\n"

    if new_content == content:
        return False

    env_path.write_text(new_content)
    return True


def update_env_file(env_path: Path, token: str) -> bool:
    """Update COPILOT_API_KEY and VISION_API_KEY in an .env file."""
    if not env_path.exists():
        warn(f"Файл не знайдено: {env_path}")
        return False

    changed = False
    changed |= _set_env_var(env_path, "COPILOT_API_KEY", token)
    changed |= _set_env_var(env_path, "VISION_API_KEY", token)

    if changed:
        info(f"Оновлено: {env_path}")
    else:
        warn(f"Нічого не змінено в {env_path}")
    return changed


def update_all_env(token: str) -> None:
    """Update token in PROJECT .env.

    The .env file in project root is the source of truth for all environment variables.
    System reads from this file and syncs to global location.
    """
    step("Оновлення .env файлу проекту")

    if update_env_file(PROJECT_ENV, token):
        info(f"Оновлено: {PROJECT_ENV}")
        # Sync to global location using existing setup script
        try:
            import subprocess
            import sys

            result = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "scripts" / "setup_dev.py")],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
            )

            if result.returncode == 0:
                pass
            else:
                pass
        except Exception:
            pass
    else:
        warn(f"Нічого не змінено в {PROJECT_ENV}")


# ─── Test Current Token ─────────────────────────────────────────────────────


def test_current_token() -> bool:
    """Test the currently configured COPILOT_API_KEY."""
    step("Перевірка поточного COPILOT_API_KEY")

    # Load from project .env first, then global
    token: str | None = None
    for env_path in [PROJECT_ENV, GLOBAL_ENV]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("COPILOT_API_KEY="):
                    token = line.split("=", 1)[1].strip()
                    break
        if token:
            break

    if not token:
        token = os.getenv("COPILOT_API_KEY")

    if not token:
        error("COPILOT_API_KEY не знайдено ні в .env, ні в environment")
        return False

    data = verify_token(token)
    if data:
        info("Токен працює!")
        print_token_info(data)
        return True
    error("Токен НЕ працює")
    return False


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    """Main entry point for Copilot token retrieval."""
    parser = argparse.ArgumentParser(
        description="GitHub Copilot Token Retriever",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Приклади:
  %(prog)s                        # Інтерактивний режим
  %(prog)s --method vscode        # OAuth device flow
  %(prog)s --method windsurf      # Витягнути з Windsurf
  %(prog)s --test                 # Перевірити поточний токен
    %(prog)s --method vscode  # Отримати + (за замовчуванням) оновити .env
        """,
    )
    parser.add_argument(
        "--method",
        choices=["vscode", "windsurf", "auto"],
        default=None,
        help="Метод отримання токена (default: інтерактивний вибір)",
    )
    parser.add_argument(
        "--update-env",
        action="store_true",
        help="Автоматично оновити .env файли після отримання токена",
    )
    parser.add_argument(
        "--no-update-env",
        action="store_true",
        help="Не оновлювати .env файли автоматично (перевизує --update-env)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Тільки перевірити поточний COPILOT_API_KEY",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Тихий режим — вивести тільки токен",
    )

    args = parser.parse_args()

    if not args.quiet:
        print(f"{C.BOLD}--- Copilot Token Retriever Started ---{C.RESET}")

    # Test mode
    if args.test:
        success = test_current_token()
        sys.exit(0 if success else 1)

    # Determine method
    method = args.method

    if method is None:
        # Interactive mode

        try:
            choice = input("  Вибір [1-4]: ").strip()
        except (KeyboardInterrupt, EOFError):
            sys.exit(0)

        method_map = {"1": "vscode", "2": "windsurf", "3": "vscode_db", "4": "test"}
        method = method_map.get(choice, "vscode")

        if method == "test":
            test_current_token()
            sys.exit(0)

    # Execute method
    token = None

    if method == "auto":
        token = get_token_from_windsurf()
        if not token:
            token = get_token_from_vscode()
        if not token:
            token = get_token_oauth_device_flow()

    elif method == "vscode":
        token = get_token_oauth_device_flow()

    elif method == "vscode_db":
        token = get_token_from_vscode()
        if not token:
            warn("Не вдалося витягнути з DB. Переключаюсь на OAuth Device Flow...")
            token = get_token_oauth_device_flow()

    elif method == "windsurf":
        token = get_token_from_windsurf()
        if not token:
            warn("Не вдалося витягнути з Windsurf. Переключаюсь на OAuth Device Flow...")
            token = get_token_oauth_device_flow()

    if not token:
        error("Не вдалося отримати токен")
        sys.exit(1)

    # Verify token
    step("Верифікація токена")
    data = verify_token(token)
    if data:
        info("Токен валідний!")
        if not args.quiet:
            print_token_info(data)
    else:
        error("Токен отримано, але він не працює з Copilot API")
        error("Переконайтесь що акаунт має активну Copilot підписку")
        sys.exit(1)

    # Output token
    if args.quiet:
        pass
    else:
        pass

    # Auto-update .env by default (this updates both COPILOT_API_KEY and
    # VISION_API_KEY). Use --no-update-env to opt out.
    if not getattr(args, "no_update_env", False):
        try:
            update_all_env(token)
        except Exception:
            warn("Не вдалося оновити .env автоматично")


# Export main function for module imports
__all__ = ["main"]

if __name__ == "__main__":
    main()
