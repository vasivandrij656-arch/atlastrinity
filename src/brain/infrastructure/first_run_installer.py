"""AtlasTrinity First Run Installer
Автоматичне налаштування на новому Mac при першому запуску .app

Features:
- Встановлення Homebrew (якщо немає)
- Встановлення Docker, Redis (SQLite використовується як локальна БД)
- Запуск сервісів
- Створення бази даних та таблиць
- Завантаження TTS/STT моделей
- Перевірка permissions (Accessibility, Screen Recording)

Використання:
- Викликається з Electron main process при першому запуску
- Надсилає progress callbacks для UI
"""

import asyncio
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from src.brain.monitoring.logger import logger  # pyre-ignore

# Import config paths
try:
    from src.brain.config import CONFIG_ROOT, MODELS_DIR, WHISPER_DIR  # pyre-ignore
except ImportError:
    # Fallback for direct execution
    CONFIG_ROOT = Path.home() / ".config" / "atlastrinity"
    MODELS_DIR = CONFIG_ROOT / "models" / "tts"
    WHISPER_DIR = CONFIG_ROOT / "models" / "faster-whisper"
    MCP_DIR = CONFIG_ROOT / "mcp"
    WORKSPACE_DIR = CONFIG_ROOT / "workspace"
    VIBE_WORKSPACE = CONFIG_ROOT / "vibe_workspace"


class SetupStep(Enum):
    CHECK_SYSTEM = "check_system"
    CHECK_PERMISSIONS = "check_permissions"
    INSTALL_HOMEBREW = "install_homebrew"
    INSTALL_REDIS = "install_redis"
    INSTALL_POSTGRES = "install_postgres"
    START_SERVICES = "start_services"
    CREATE_DATABASE = "create_database"
    INSTALL_MACOS_USE = "install_macos_use"
    DOWNLOAD_TTS = "download_tts"
    DOWNLOAD_STT = "download_stt"
    BUILD_MACOS_USE = "build_macos_use"
    INSTALL_VIBE = "install_vibe"
    SETUP_COMPLETE = "setup_complete"


@dataclass
class SetupProgress:
    step: SetupStep
    progress: float  # 0.0 - 1.0
    message: str
    success: bool = True
    error: str | None = None


# Progress callback type
ProgressCallback = Callable[[SetupProgress], None]


def _run_command(cmd: list, timeout: int = 300, capture: bool = True) -> tuple[int, str, str]:
    """Execute command and return (returncode, stdout, stderr)"""
    try:
        result = subprocess.run(
            cmd, check=False, capture_output=capture, text=True, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def _run_command_async(cmd: str, timeout: int = 600) -> tuple[int, str, str]:
    """Execute shell command with pipe handling"""
    try:
        result = subprocess.run(
            cmd,
            check=False,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,  # nosec B602
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)


class FirstRunInstaller:
    """Orchestrates first-run setup on a new Mac"""

    def __init__(self, progress_callback: ProgressCallback | None = None):
        self.callback = progress_callback or self._default_callback
        self.errors: list[str] = []

    def _default_callback(self, progress: SetupProgress):
        """Default console output"""
        icon = "✓" if progress.success else "✗"
        print(
            f"[{icon}] {progress.step.value}: {progress.message} ({progress.progress * 100:.0f}%)",
            file=sys.stderr,
        )
        if progress.error:
            print(f"    Error: {progress.error}", file=sys.stderr)

    def _report(
        self,
        step: SetupStep,
        progress: float,
        message: str,
        success: bool = True,
        error: str | None = None,
    ):
        """Report progress to callback"""
        self.callback(
            SetupProgress(
                step=step,
                progress=progress,
                message=message,
                success=success,
                error=error,
            ),
        )
        if not success and error:
            self.errors.append(f"{step.value}: {error}")

    # ============ SYSTEM CHECKS ============

    def check_system(self) -> bool:
        """Check macOS version and architecture"""
        self._report(SetupStep.CHECK_SYSTEM, 0.0, "Перевірка системи...")

        import platform

        # Check macOS
        if platform.system() != "Darwin":
            self._report(
                SetupStep.CHECK_SYSTEM,
                1.0,
                "Помилка: AtlasTrinity підтримує тільки macOS",
                success=False,
                error="Not macOS",
            )
            return False

        # Check ARM64
        arch = platform.machine()
        if arch != "arm64":
            self._report(
                SetupStep.CHECK_SYSTEM,
                1.0,
                f"Помилка: Потрібен Apple Silicon (знайдено: {arch})",
                success=False,
                error=f"Architecture: {arch}",
            )
            return False

        # Check macOS version
        mac_ver = platform.mac_ver()[0]
        self._report(SetupStep.CHECK_SYSTEM, 1.0, f"macOS {mac_ver} (ARM64) ✓")
        return True

    def check_permissions(self) -> dict[str, bool | str]:
        """Check Accessibility, Screen Recording, Camera, and Microphone permissions."""
        self._report(
            SetupStep.CHECK_PERMISSIONS,
            0.0,
            "Перевірка дозволів macOS (надайте їх у вікнах, що з'являться)...",
        )

        permissions: dict[str, bool | str] = {
            "accessibility": False,
            "screen_recording": False,
            "camera": False,
            "microphone": False,
        }

        # 1. Check and Request Accessibility
        try:
            from ApplicationServices import (
                AXIsProcessTrustedWithOptions,  # type: ignore
                kAXTrustedCheckOptionPrompt,  # type: ignore
            )

            options = {kAXTrustedCheckOptionPrompt: True}
            permissions["accessibility"] = bool(AXIsProcessTrustedWithOptions(options))
        except ImportError:
            # Fallback: try AppleScript test (doesn't prompt elegantly)
            code, _out, _ = _run_command(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to return name of first process',
                ],
            )
            permissions["accessibility"] = code == 0

        # 2. Check and Request Screen Recording
        try:
            import Quartz  # type: ignore

            if hasattr(Quartz, "CGPreflightScreenCaptureAccess"):
                permissions["screen_recording"] = bool(
                    Quartz.CGPreflightScreenCaptureAccess()  # type: ignore
                )
                if not permissions["screen_recording"] and hasattr(
                    Quartz, "CGRequestScreenCaptureAccess"
                ):
                    Quartz.CGRequestScreenCaptureAccess()  # type: ignore
                    permissions["screen_recording"] = "requested"
        except ImportError:
            # Fallback: Check Screen Recording (try to take a screenshot)
            try:
                import tempfile

                test_path = Path(tempfile.gettempdir()) / "atlastrinity_perm_test.png"
                code, _, _ = _run_command(["screencapture", "-x", str(test_path)], timeout=5)
                if test_path.exists():
                    test_path.unlink()
                    permissions["screen_recording"] = True
            except Exception:
                pass

        # 3. Check and Request Camera & Microphone
        try:
            from AVFoundation import AVCaptureDevice  # type: ignore

            # Camera ("vide")
            video_auth_status = AVCaptureDevice.authorizationStatusForMediaType_("vide")
            if video_auth_status == 0:  # AVAuthorizationStatusNotDetermined
                AVCaptureDevice.requestAccessForMediaType_completionHandler_("vide", None)
                permissions["camera"] = "requested"
            else:
                permissions["camera"] = video_auth_status == 3  # AVAuthorizationStatusAuthorized

            # Microphone ("soun")
            audio_auth_status = AVCaptureDevice.authorizationStatusForMediaType_("soun")
            if audio_auth_status == 0:
                AVCaptureDevice.requestAccessForMediaType_completionHandler_("soun", None)
                permissions["microphone"] = "requested"
            else:
                permissions["microphone"] = audio_auth_status == 3
        except ImportError:
            pass

        # Interpret "requested" as False for the immediate status check (since they are pending)
        status_acc = (
            "✓"
            if permissions["accessibility"] is True
            else "⏳"
            if permissions["accessibility"] == "requested"
            else "✗"
        )
        status_screen = (
            "✓"
            if permissions["screen_recording"] is True
            else "⏳"
            if permissions["screen_recording"] == "requested"
            else "✗"
        )
        status_cam = (
            "✓"
            if permissions["camera"] is True
            else "⏳"
            if permissions["camera"] == "requested"
            else "✗"
        )
        status_mic = (
            "✓"
            if permissions["microphone"] is True
            else "⏳"
            if permissions["microphone"] == "requested"
            else "✗"
        )

        self._report(
            SetupStep.CHECK_PERMISSIONS,
            1.0,
            f"Access: {status_acc}, Screen: {status_screen}, Camera: {status_cam}, Mic: {status_mic}",
        )

        missing_perms = [k for k, v in permissions.items() if v is not True]

        if missing_perms:
            print("\n" + "!" * 50, file=sys.stderr)
            print("⚠️  УВАГА: ПОТРІБНІ ДОДАТКОВІ ДОЗВОЛИ", file=sys.stderr)
            print("   Перевірте системні вікна запиту дозволів та погодьте їх.", file=sys.stderr)
            print(
                "   Або надайте їх вручну в System Settings > Privacy & Security.", file=sys.stderr
            )

            if permissions["accessibility"] is not True:
                print("   > Accessibility (Universal Access)", file=sys.stderr)
                _run_command(
                    [
                        "open",
                        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
                    ]
                )

            if permissions["screen_recording"] is not True:
                print("   > Screen Recording", file=sys.stderr)
                # Opens screen recording directly on newer macOS
                _run_command(
                    [
                        "open",
                        "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
                    ]
                )

            print("   > Full Disk Access (Рекомендовано)", file=sys.stderr)
            _run_command(
                ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"]
            )

            print("!" * 50 + "\n", file=sys.stderr)

        return permissions

    # ============ HOMEBREW ============

    def check_homebrew(self) -> bool:
        """Check if Homebrew is installed"""
        return shutil.which("brew") is not None

    def install_homebrew(self) -> bool:
        """Install Homebrew (requires user interaction for sudo)"""
        self._report(SetupStep.INSTALL_HOMEBREW, 0.0, "Перевірка Homebrew...")

        if self.check_homebrew():
            self._report(SetupStep.INSTALL_HOMEBREW, 1.0, "Homebrew вже встановлено ✓")
            return True

        self._report(
            SetupStep.INSTALL_HOMEBREW,
            0.2,
            "Встановлення Homebrew (може потребувати пароль)...",
        )

        # Homebrew install script
        install_cmd = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'

        try:
            # This requires user interaction in Terminal
            # In production, we might need to spawn a Terminal window
            process = subprocess.Popen(
                install_cmd,
                shell=True,  # nosec B602
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            # Stream output
            if process.stdout:
                for line in iter(process.stdout.readline, ""):  # pyre-ignore
                    if line:
                        print(f"[Homebrew] {line.strip()}", file=sys.stderr)

            process.wait()

            if process.returncode == 0:
                # Add to PATH for Apple Silicon
                brew_path = "/opt/homebrew/bin"
                if brew_path not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = f"{brew_path}:{os.environ.get('PATH', '')}"

                self._report(SetupStep.INSTALL_HOMEBREW, 1.0, "Homebrew встановлено ✓")
                return True
            self._report(
                SetupStep.INSTALL_HOMEBREW,
                1.0,
                "Помилка встановлення Homebrew",
                success=False,
                error=f"Exit code: {process.returncode}",
            )
            return False

        except Exception as e:
            self._report(
                SetupStep.INSTALL_HOMEBREW,
                1.0,
                "Помилка встановлення Homebrew",
                success=False,
                error=str(e),
            )
            return False

    # ============ SERVICES ============

    def _install_brew_package(
        self,
        step: SetupStep,
        formula: str,
        cask: bool = False,
        check_cmd: str | None = None,
    ) -> bool:
        """Generic brew install helper"""
        self._report(step, 0.0, f"Перевірка {formula}...")

        # Check if already installed
        if check_cmd and shutil.which(check_cmd):
            self._report(step, 1.0, f"{formula} вже встановлено ✓")
            return True

        # For casks, check via brew list
        if cask:
            code, _, _ = _run_command(["brew", "list", "--cask", formula])
            if code == 0:
                self._report(step, 1.0, f"{formula} вже встановлено ✓")
                return True

        self._report(step, 0.3, f"Встановлення {formula}...")

        cmd = ["brew", "install"]
        if cask:
            cmd.append("--cask")
        cmd.append(formula)

        code, _stdout, stderr = _run_command(cmd, timeout=600)

        if code == 0:
            self._report(step, 1.0, f"{formula} встановлено ✓")
            return True
        self._report(
            step,
            1.0,
            f"Помилка встановлення {formula}",
            success=False,
            error=stderr[:200],  # pyre-ignore
        )
        return False

    def install_redis(self) -> bool:
        """Install Redis"""
        return self._install_brew_package(SetupStep.INSTALL_REDIS, "redis", check_cmd="redis-cli")

    def install_vibe(self) -> bool:
        """Install Mistral Vibe CLI"""
        self._report(SetupStep.INSTALL_VIBE, 0.0, "Перевірка Vibe CLI...")

        if shutil.which("vibe"):
            self._report(SetupStep.INSTALL_VIBE, 1.0, "Vibe CLI вже встановлено ✓")
            return True

        self._report(SetupStep.INSTALL_VIBE, 0.3, "Встановлення Vibe CLI...")

        # Install via official script (https://help.mistral.ai/en/articles/496007-get-started-with-mistral-vibe)
        cmd = "curl -LsSf https://mistral.ai/vibe/install.sh | bash"
        code, _stdout, stderr = _run_command_async(cmd, timeout=300)

        if code == 0:
            self._report(SetupStep.INSTALL_VIBE, 1.0, "Vibe CLI успішно встановлено ✓")
            return True
        self._report(
            SetupStep.INSTALL_VIBE,
            1.0,
            "Помилка встановлення Vibe CLI",
            success=False,
            error=stderr[:100],  # pyre-ignore
        )
        return False

    def install_postgres(self) -> bool:
        """Install PostgreSQL (skipped if using SQLite backend)"""
        from src.brain.config.config_loader import config as sys_config  # pyre-ignore

        db_url = sys_config.get(
            "database.url",
            f"sqlite+aiosqlite:///{CONFIG_ROOT}/atlastrinity.db",
        )
        if db_url.startswith("sqlite"):
            self._report(
                SetupStep.INSTALL_POSTGRES,
                1.0,
                "SQLite is configured as the DB backend; skipping PostgreSQL installation.",
            )
            return True

        return self._install_brew_package(
            SetupStep.INSTALL_POSTGRES,
            "postgresql@17",
            check_cmd="psql",
        )

    def start_services(self) -> bool:
        """Start Redis and PostgreSQL services"""
        from src.brain.config.config_loader import config as sys_config  # pyre-ignore

        self._report(SetupStep.START_SERVICES, 0.0, "Запуск сервісів...")

        # Only include PostgreSQL service if backend requires it

        db_url = sys_config.get(
            "database.url",
            f"sqlite+aiosqlite:///{CONFIG_ROOT}/atlastrinity.db",
        )

        services = ["redis"]
        if not db_url.startswith("sqlite"):
            services.append("postgresql@17")
        all_ok = True

        for i, service in enumerate(services):
            progress = (i + 1) / len(services)

            # Check if already running
            code, out, _ = _run_command(["brew", "services", "info", service, "--json"])
            if '"running":true' in out.replace(" ", "") or '"running": true' in out:
                self._report(SetupStep.START_SERVICES, progress, f"{service} вже запущено")
                continue

            # Start service
            code, _, stderr = _run_command(["brew", "services", "start", service])
            if code != 0:
                self._report(
                    SetupStep.START_SERVICES,
                    progress,
                    f"Помилка запуску {service}",
                    success=False,
                    error=stderr[:100],  # pyre-ignore
                )
                all_ok = False
            else:
                self._report(SetupStep.START_SERVICES, progress, f"{service} запущено")

        # Check Docker
        if shutil.which("docker"):
            code, _, _ = _run_command(["docker", "info"], timeout=10)
            if code != 0:
                self._report(
                    SetupStep.START_SERVICES,
                    1.0,
                    "Docker Desktop не запущено. Запустіть його вручну.",
                    success=False,
                )
                # Not critical - user can start it later

        return all_ok

    # ============ DATABASE ============

    async def _ensure_postgres_role(self, username: str = "dev") -> bool:
        """Ensure the specified role exists in Postgres."""
        try:
            _rc, out, _ = _run_command(
                ["psql", "-tAc", f"SELECT 1 FROM pg_roles WHERE rolname='{username}';"],
            )
            if "1" not in out:
                self._report(SetupStep.CREATE_DATABASE, 0.1, f"Створення ролі '{username}'...")
                code, _, stderr = _run_command(["createuser", "-s", username])
                if code != 0:
                    logger.warning(f"Failed to create user {username}: {stderr}")
                    return False
                return True
            return True
        except Exception:
            return False

    async def create_database(self) -> bool:
        """Create structured database and tables (supports SQLite or PostgreSQL)"""
        from src.brain.config.config_loader import config as sys_config  # pyre-ignore

        self._report(SetupStep.CREATE_DATABASE, 0.0, "Створення бази даних...")

        # Use config.get

        db_url = sys_config.get(
            "database.url",
            f"sqlite+aiosqlite:///{CONFIG_ROOT}/atlastrinity.db",
        )

        if db_url.startswith("sqlite"):
            # For SQLite, ensure file/directory exists and return
            try:
                CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
                db_file = CONFIG_ROOT / "atlastrinity.db"
                if not db_file.exists():
                    db_file.touch()
                self._report(SetupStep.CREATE_DATABASE, 1.0, "SQLite database ensured.")
                return True
            except Exception as e:
                self._report(
                    SetupStep.CREATE_DATABASE,
                    1.0,
                    "Failed to ensure SQLite DB",
                    success=False,
                    error=str(e),
                )
                return False

        db_name = "atlastrinity_db"
        username = os.environ.get("USER", "dev")

        # Wait for PostgreSQL to be ready
        for _attempt in range(10):
            code, _, _ = _run_command(["pg_isready"], timeout=5)
            if code == 0:
                break
            await asyncio.sleep(1)
        else:
            self._report(
                SetupStep.CREATE_DATABASE,
                1.0,
                "PostgreSQL не відповідає",
                success=False,
                error="pg_isready failed",
            )
            return False

        self._report(SetupStep.CREATE_DATABASE, 0.3, "PostgreSQL готовий...")

        # Check if database exists
        code, out, _ = _run_command(
            [
                "psql",
                "-U",
                username,
                "-d",
                "postgres",
                "-t",
                "-c",
                f"SELECT 1 FROM pg_database WHERE datname='{db_name}';",
            ],
        )

        if "1" not in out:
            # Create database
            self._report(SetupStep.CREATE_DATABASE, 0.5, f"Створення бази {db_name}...")
            code, _, stderr = _run_command(["createdb", "-U", username, db_name])
            if code != 0:
                self._report(
                    SetupStep.CREATE_DATABASE,
                    1.0,
                    "Помилка створення бази",
                    success=False,
                    error=stderr[:100],
                )
                return False

        self._report(SetupStep.CREATE_DATABASE, 0.7, "Ініціалізація таблиць...")

        # Initialize SQLAlchemy tables
        try:
            from src.brain.memory.db.manager import db_manager  # pyre-ignore

            await db_manager.initialize()
            self._report(SetupStep.CREATE_DATABASE, 1.0, "База даних готова ✓")
            return True
        except Exception as e:
            self._report(
                SetupStep.CREATE_DATABASE,
                1.0,
                "Помилка ініціалізації таблиць",
                success=False,
                error=str(e)[:100],  # pyre-ignore
            )
            return False

    # ============ NATIVE BINARIES ============

    def build_macos_use(self) -> bool:
        """Build macOS native helpers (placeholder)."""
        self._report(
            SetupStep.BUILD_MACOS_USE,
            0.0,
            "Building macOS native helpers (placeholder)...",
        )
        # TODO: implement build steps for macos-use native helper binary
        self._report(SetupStep.BUILD_MACOS_USE, 1.0, "macos-use build skipped (placeholder).")
        return True

    def download_tts_models(self) -> bool:
        """Download Ukrainian TTS models (silently)"""
        self._report(
            SetupStep.DOWNLOAD_TTS,
            0.2,
            "Завантаження ukrainian-tts (може тривати довго)...",
        )

        try:
            # Trigger download by importing TTS
            MODELS_DIR.mkdir(parents=True, exist_ok=True)

            from ukrainian_tts.tts import TTS  # pyre-ignore

            TTS(cache_folder=str(MODELS_DIR), device="cpu")

            self._report(SetupStep.DOWNLOAD_TTS, 1.0, "TTS моделі готові ✓")
            return True
        except Exception as e:
            self._report(
                SetupStep.DOWNLOAD_TTS,
                1.0,
                "Помилка завантаження TTS",
                success=False,
                error=str(e)[:100],  # pyre-ignore
            )
            return False

    def download_stt_models(self) -> bool:
        """Download Faster-Whisper STT models"""
        self._report(SetupStep.DOWNLOAD_STT, 0.0, "Завантаження STT моделей...")

        # Check if models exist
        if WHISPER_DIR.exists() and any(WHISPER_DIR.iterdir()):
            self._report(SetupStep.DOWNLOAD_STT, 1.0, "STT моделі вже завантажені ✓")
            return True

        self._report(SetupStep.DOWNLOAD_STT, 0.2, "Завантаження Faster-Whisper large-v3...")

        try:
            WHISPER_DIR.mkdir(parents=True, exist_ok=True)

            from faster_whisper import WhisperModel  # pyre-ignore

            WhisperModel(
                "large-v3",
                device="cpu",
                compute_type="int8",
                download_root=str(WHISPER_DIR),
            )

            self._report(SetupStep.DOWNLOAD_STT, 1.0, "STT моделі готові ✓")
            return True
        except Exception as e:
            self._report(
                SetupStep.DOWNLOAD_STT,
                1.0,
                "Помилка завантаження STT",
                success=False,
                error=str(e)[:100],  # pyre-ignore
            )
            return False

    # ============ MAIN ORCHESTRATOR ============

    async def run_full_setup(self) -> bool:
        """Run complete first-run setup.
        Returns True if all critical steps succeeded.
        """
        from src.brain.config.config_loader import config as sys_config  # noqa: F841 # pyre-ignore

        print("\n" + "=" * 60, file=sys.stderr)
        print("🔱 AtlasTrinity First Run Setup", file=sys.stderr)
        print("=" * 60 + "\n", file=sys.stderr)

        # 1. System check (critical)
        if not self.check_system():
            return False

        # 2. Permissions check (informational)
        permissions = self.check_permissions()
        missing_perms = [k for k, v in permissions.items() if v is not True]
        if missing_perms:
            print("\n⚠️  Відкрийте System Settings > Privacy & Security", file=sys.stderr)
            print("   та надайте всі необхідні дозволи для AtlasTrinity.", file=sys.stderr)
            print(
                f"   Відсутні або очікують дозволу: {', '.join(missing_perms)}\n", file=sys.stderr
            )

        # 3. Homebrew (critical)
        if not self.install_homebrew():
            return False

        # 4. Install services (important but can continue)
        self.install_redis()
        self.install_vibe()
        # self.install_postgres() # Перейшли на SQLite, установка PostgreSQL більше не є обов'язковою

        # 5. Start services
        self.start_services()

        # 6. Database (important)
        await self.create_database()

        # 7. Native Binaries (macos-use)
        self.build_macos_use()

        # 8. Models (can be downloaded later)
        self.download_tts_models()
        self.download_stt_models()

        # 9. Project Workspace
        try:
            project_ws = (
                Path(sys_config.get("system.workspace_path", str(CONFIG_ROOT / "workspace")))
                .expanduser()
                .absolute()
            )
            project_ws.mkdir(parents=True, exist_ok=True)
            self._report(SetupStep.SETUP_COMPLETE, 0.9, f"Робоча папка {project_ws.name} готова ✓")
        except Exception:
            pass

        # Mark setup as complete
        setup_marker = CONFIG_ROOT / "setup_complete"
        setup_marker.parent.mkdir(parents=True, exist_ok=True)
        setup_marker.write_text(
            f"Completed at: {__import__('datetime').datetime.now().isoformat()}",  # pyre-ignore
        )

        self._report(SetupStep.SETUP_COMPLETE, 1.0, "Налаштування завершено!")

        print("\n" + "=" * 60, file=sys.stderr)
        if self.errors:
            print(f"⚠️  Завершено з {len(self.errors)} помилками:", file=sys.stderr)
            for err in self.errors:
                print(f"   - {err}", file=sys.stderr)
        else:
            print("✅ Всі налаштування успішно виконані!", file=sys.stderr)
        print("=" * 60 + "\n", file=sys.stderr)

        return len(self.errors) == 0

    def is_setup_complete(self) -> bool:
        """Check if first-run setup was already completed"""
        return (CONFIG_ROOT / "setup_complete").exists()


# ============ CLI ENTRY POINT ============


async def main():
    """CLI entry point for testing"""
    installer = FirstRunInstaller()

    if installer.is_setup_complete():
        print("✓ Setup already complete. Use --force to re-run.", file=sys.stderr)
        if "--force" not in sys.argv:
            return

    success = await installer.run_full_setup()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
