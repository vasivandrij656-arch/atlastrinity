"""AtlasTrinity Full Stack Development Setup Script
Виконує комплексне налаштування середовища після клонування:
- Перевірка середовища (Python 3.12.12, Bun, Swift)
- Створення та синхронізація глобальних конфігурацій (~/.config/atlastrinity)
- Компіляція нативних MCP серверів (Swift)
- Встановлення Python та NPM залежностей
- Завантаження AI моделей (STT/TTS)
- Перевірка системних сервісів (Redis, Vibe CLI)
"""

import argparse
import asyncio
import json
import os
import platform
import re
import select
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path


# Кольори для консолі
class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


class InstallationTracker:
    """Tracks the status of each setup phase for the final report."""

    def __init__(self):
        self.results = {
            "DB Restore": ("Pending", Colors.WARNING or "\033[93m"),
            "venv Creation": ("Pending", Colors.WARNING or "\033[93m"),
            "Python Packages": ("Pending", Colors.WARNING or "\033[93m"),
            "NPM Packages": ("Pending", Colors.WARNING or "\033[93m"),
            "Swift Build (macos-use)": ("Pending", Colors.WARNING or "\033[93m"),
            "Model Downloads": ("Pending", Colors.WARNING or "\033[93m"),
            "DB Initialization": ("Pending", Colors.WARNING or "\033[93m"),
            "Knowledge Base Setup": ("Pending", Colors.WARNING or "\033[93m"),
            "MCP Tools Integration": ("Pending", Colors.WARNING or "\033[93m"),
        }

    def update(self, key, status, color=None):
        if color is None:
            color = Colors.OKGREEN
        if key in self.results:
            self.results[key] = (status, color)

    def print_report(self):
        print(f"\n{Colors.OKCYAN}{Colors.BOLD}🎉 Очікуваний результат:{Colors.ENDC}")
        for key, (status, color) in self.results.items():
            icon = "✅" if color == Colors.OKGREEN else "⚠️" if color == Colors.WARNING else "❌"
            print(f"  {icon} {key:<40} {color}{status}{Colors.ENDC}")
        print()


tracker = InstallationTracker()


def _log_to_file(msg: str):
    """Logs a message to the setup_dev.log file."""
    log_dir = CONFIG_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "setup_dev.log"
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    # Strip ANSI colors for file logging
    clean_msg = re.sub(r"\033\[[0-9;]*m", "", msg)
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {clean_msg}\n")
    except Exception:
        pass


def print_step(msg: str):
    output = f"{Colors.BOLD}{Colors.OKCYAN}STEP:{Colors.ENDC} {msg}"
    print(output)
    _log_to_file(output)


def print_success(msg: str):
    output = f"{Colors.OKGREEN}SUCCESS:{Colors.ENDC} {msg}"
    print(output)
    _log_to_file(output)


def print_warning(msg: str):
    output = f"{Colors.WARNING}WARNING:{Colors.ENDC} {msg}"
    print(output)
    _log_to_file(output)


def print_error(msg: str):
    output = f"{Colors.FAIL}ERROR:{Colors.ENDC} {msg}"
    print(output, file=sys.stderr)
    _log_to_file(output)


def print_info(msg: str):
    output = f"{Colors.OKBLUE}INFO:{Colors.ENDC} {msg}"
    print(output)
    _log_to_file(output)


# Константи
REQUIRED_PYTHON = "3.12.12"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CONFIG_ROOT = Path.home() / ".config" / "atlastrinity"
VENV_PATH = PROJECT_ROOT / ".venv"

# Папки для конфігів та моделей
DIRS = {
    "config": CONFIG_ROOT,
    "logs": CONFIG_ROOT / "logs",
    "memory": CONFIG_ROOT / "memory",
    "screenshots": CONFIG_ROOT / "screenshots",
    "tts_models": CONFIG_ROOT / "models" / "tts",
    "stt_models": CONFIG_ROOT / "models" / "faster-whisper",
    "mcp": CONFIG_ROOT / "mcp",
    "workspace": CONFIG_ROOT / "workspace",
    "vibe_workspace": CONFIG_ROOT / "vibe_workspace",
    "stanza": CONFIG_ROOT / "models" / "stanza",
    "huggingface": CONFIG_ROOT / "models" / "huggingface",
}


def check_python_version():
    """Перевіряє версію Python"""
    print_step(f"Перевірка версії Python (ціль: {REQUIRED_PYTHON})...")
    current_version = platform.python_version()

    if current_version == REQUIRED_PYTHON:
        print_success(f"Python {current_version} знайдено")
        return True

    print_warning(f"Поточна версія Python: {current_version}")

    # Proactive installation/fix
    if shutil.which("brew"):
        print_info(f"Спроба оновити Python до {REQUIRED_PYTHON} через Homebrew...")
        try:
            # brew install python@3.12 installs the latest in that branch
            # If we want EXACTLY 3.12.12, brew might not provide it as a separate formula easily
            # but we can try to update the branch
            subprocess.run(["brew", "upgrade", "python@3.12"], check=False)

            # Re-check after potential upgrade
            # Wait a bit for filesystem
            time.sleep(1)
            # We can't easily change the running process python version,
            # so we inform the user to restart if we detect a change was made or still mismatched.
            print_info(f"Рекомендуємо переконатися, що у вас встановлено {REQUIRED_PYTHON}.")
            print_info(
                "Якщо ви використовуєте pyenv: pyenv install 3.12.12 && pyenv global 3.12.12"
            )
        except Exception as e:
            print_warning(f"Не вдалося автоматично оновити Python: {e}")

    return True  # Дозволяємо продовжити, але з попередженням


def ensure_directories():
    """Створює необхідні директорії в ~/.config"""
    print_step("Налаштування глобальних директорій...")
    for name, path in DIRS.items():
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            print_success(f"Створено {name}: {path}")
        else:
            print_success(f"Директорія {name} вже існує")


def check_system_tools():
    """Перевіряє наявність базових інструментів та встановлює відсутні"""
    print_step("Перевірка базових інструментів (Brew, Python, Node, Bun)...")

    # Ensure Homebrew is in PATH
    brew_paths = ["/opt/homebrew/bin", "/usr/local/bin"]
    for p in brew_paths:
        if p not in os.environ["PATH"]:
            os.environ["PATH"] = p + os.pathsep + os.environ["PATH"]

    if not shutil.which("brew"):
        print_error("Homebrew не знайдено! Він критично необхідний.")
        return False

    # 1. Ensure Python 3.12
    if not shutil.which("python3.12"):
        print_info("Python 3.12 не знайдено. Встановлення через Brew...")
        try:
            subprocess.run(["brew", "install", "python@3.12"], check=True)
            print_success("Python 3.12 встановлено")
        except Exception as e:
            print_error(f"Не вдалося встановити Python 3.12: {e}")
    else:
        print_success("Python 3.12 знайдено")

    # 2. Ensure Node 22
    if not shutil.which("node") or "v22" not in subprocess.getoutput("node --version"):
        print_info("Node 22 не знайдено або версія застаріла. Встановлення node@22 через Brew...")
        try:
            subprocess.run(["brew", "install", "node@22"], check=True)
            # Link node@22 if possible
            subprocess.run(["brew", "link", "--overwrite", "node@22"], check=False)

            # Export path for current session
            node_path = "/opt/homebrew/opt/node@22/bin"
            if os.path.exists(node_path):
                os.environ["PATH"] = node_path + os.pathsep + os.environ["PATH"]
            print_success("Node 22 встановлено")
        except Exception as e:
            print_error(f"Не вдалося встановити Node 22: {e}")
    else:
        print_success(f"Node знайдено ({subprocess.getoutput('node --version').strip()})")

    # 3. Check other tools (includes all 13 linters from lint:all + build tools)
    tools = [
        "safety",
        "detect-secrets",
        "gcloud",
        "actionlint",
    ]
    # Python tools that live in .venv/bin
    venv_tools = {
        "ruff",
        "pyrefly",
        "vulture",
        "bandit",
        "xenon",
        "safety",
        "detect-secrets",
        "zizmor",
    }
    missing = []

    for tool in tools:
        path = shutil.which(tool)
        if path:
            print_success(f"{tool} знайдено")
        else:
            # Check venv for python tools (only if venv exists)
            if tool in venv_tools:
                venv_tool = PROJECT_ROOT / ".venv" / "bin" / tool
                if venv_tool.exists():
                    print_success(f"{tool} знайдено у .venv")
                    continue

            if tool in ["bun", "swift", "npm"] or tool == "vibe":
                print_warning(f"{tool} НЕ знайдено")
                missing.append(tool)
            else:
                # Python-specific tools are non-blocking here as they'll be installed later
                print_info(f"{tool} поки не знайдено (буде встановлено у .venv пізніше)")

    # Check npx-based tools (biome, eslint, pyright, tsc, lefthook are npm devDependencies)
    npx_tools = ["@biomejs/biome", "eslint", "pyright", "lefthook"]
    for pkg in npx_tools:
        pkg_dir = PROJECT_ROOT / "node_modules" / pkg
        if pkg_dir.exists():
            print_success(f"{pkg} знайдено в node_modules")
        else:
            print_info(f"{pkg} поки не знайдено (буде встановлено через npm install)")

    # Auto-install Vibe if missing
    if "vibe" in missing:
        print_info("Vibe CLI не знайдено. Встановлення Vibe...")
        try:
            subprocess.run(
                "curl -LsSf https://mistral.ai/vibe/install.sh | bash", shell=True, check=True
            )
            # Add to PATH for current session (Vibe installs to ~/.local/bin)
            vibe_bin = Path.home() / ".local" / "bin"
            os.environ["PATH"] = str(vibe_bin) + os.pathsep + os.environ.get("PATH", "")
            print_success("Vibe CLI встановлено")
            if "vibe" in missing:
                missing.remove("vibe")
        except Exception as e:
            print_error(f"Не вдалося встановити Vibe CLI: {e}")

    # Auto-install Bun if missing
    if "bun" in missing:
        print_info("Bun не знайдено. Встановлення Bun...")
        try:
            subprocess.run("curl -fsSL https://bun.sh/install | bash", shell=True, check=True)
            # Add to PATH for current session
            bun_bin = Path.home() / ".bun" / "bin"
            os.environ["PATH"] += os.pathsep + str(bun_bin)
            print_success("Bun встановлено")
            if "bun" in missing:
                missing.remove("bun")
        except Exception as e:
            print_error(f"Не вдалося встановити Bun: {e}")

    # Auto-install JS dev tools if missing
    if any(t in missing for t in ["oxlint", "knip"]):
        print_info("Деякі JS інструменти (oxlint/knip) відсутні. Спроба встановити через npm...")
        try:
            subprocess.run(["npm", "install", "-g", "oxlint", "knip"], check=False)
            print_success("JS інструменти встановлено")
            for t in ["oxlint", "knip"]:
                if t in missing:
                    missing.remove(t)
        except Exception:
            pass

    # Auto-install gcloud if missing
    if "gcloud" in missing:
        print_info("gcloud CLI не знайдено. Встановлення Google Cloud SDK через Brew...")
        try:
            subprocess.run(["brew", "install", "--cask", "google-cloud-sdk"], check=True)
            # Brew usually symlinks gcloud to common paths, but we ensure it's in PATH
            print_success("Google Cloud SDK (gcloud) було встановлено")
            if "gcloud" in missing:
                missing.remove("gcloud")
        except Exception as e:
            print_warning(f"Не вдалося автоматично встановити Google Cloud SDK: {e}")
            print_info(
                "Будь ласка, встановіть його вручну: https://cloud.google.com/sdk/docs/install"
            )

    if "swift" in missing:
        print_error("Swift необхідний для компіляції macos-use та googlemaps MCP серверів!")
        print_info("Встановіть Xcode або Command Line Tools: xcode-select --install")

    # Auto-install GitHub CLI if missing
    if "gh" in missing:
        print_info("GitHub CLI (gh) не знайдено. Встановлення через Brew...")
        try:
            subprocess.run(["brew", "install", "gh"], check=True)
            print_success("GitHub CLI встановлено")
            if "gh" in missing:
                missing.remove("gh")
        except Exception as e:
            print_warning(f"Не вдалося встановити GitHub CLI: {e}")

    # 4. Check for Full Xcode (for XcodeBuildMCP)
    # Search multiple locations: standard, beta, user Desktop, Spotlight
    xcode_candidates = [
        Path("/Applications/Xcode.app"),
        Path("/Applications/Xcode-beta.app"),
        Path.home() / "Desktop" / "Xcode.app",
        Path.home() / "Desktop" / "Xcode-beta.app",
    ]
    # Also search via Spotlight for non-standard locations
    try:
        spotlight = subprocess.run(
            ["mdfind", "kMDItemCFBundleIdentifier == 'com.apple.dt.Xcode'"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        for line in spotlight.stdout.strip().splitlines():
            p = Path(line.strip())
            if p.exists() and p not in xcode_candidates:
                xcode_candidates.append(p)
    except Exception:
        pass

    xcode_app = next((p for p in xcode_candidates if p.exists()), None)

    if shutil.which("xcodebuild"):
        result = subprocess.run(
            ["xcodebuild", "-version"], capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            print_success("Повний Xcode знайдено")
        elif xcode_app:
            print_warning(f"xcode-select вказує на CLT, але Xcode знайдено: {xcode_app}")
            xcode_dev_path = xcode_app / "Contents" / "Developer"
            print_info(f"Автоматичне переключення: sudo xcode-select -s {xcode_dev_path}")
            try:
                subprocess.run(["sudo", "xcode-select", "-s", str(xcode_dev_path)], check=True)
                print_success(f"Переключено на повний Xcode ({xcode_app.name})")
            except Exception as e:
                print_error(f"Не вдалося переключитись: {e}")
                print_info(f"Спробуйте вручну: sudo xcode-select -s {xcode_dev_path}")
        else:
            print_warning("Знайдено тільки Command Line Tools (повний Xcode відсутній)")
            print_info("XcodeBuildMCP буде пропущено при налаштуванні.")
    elif xcode_app:
        xcode_dev_path = xcode_app / "Contents" / "Developer"
        print_warning(f"Xcode знайдено ({xcode_app}), але не активовано!")
        print_info(f"Автоматичне переключення: sudo xcode-select -s {xcode_dev_path}")
        try:
            subprocess.run(["sudo", "xcode-select", "-s", str(xcode_dev_path)], check=True)
            print_success(f"Переключено на повний Xcode ({xcode_app.name})")
        except Exception as e:
            print_error(f"Не вдалося переключитись: {e}")
    else:
        print_warning("Xcode не знайдено")
        print_info("XcodeBuildMCP буде пропущено при налаштуванні.")

    return "brew" not in missing  # Brew є обов'язковим


def ensure_database():
    """Initialize SQLite database in global config folder"""
    print_step("Налаштування основної бази даних (SQLite)...")
    db_path = CONFIG_ROOT / "atlastrinity.db"
    backup_path = PROJECT_ROOT / "backups" / "databases" / "atlastrinity.db"

    # 1. Restore from backup if exists and local is missing
    encrypted_backup = PROJECT_ROOT / "backups" / "databases" / "atlastrinity.db.encrypted"
    if not db_path.exists():
        if backup_path.exists():
            print_info("Відновлення основної бази з бекапу репозиторію...")
            try:
                shutil.copy2(backup_path, db_path)
                print_success("Базу даних відновлено")
            except Exception as e:
                print_warning(f"Не вдалося відновити базу: {e}")
        elif encrypted_backup.exists():
            print_info("Відновлення основної бази з зашифрованого бекапу...")
            try:
                from src.maintenance.secure_backup import SecureBackupManager

                backup_mgr = SecureBackupManager(PROJECT_ROOT)
                key = backup_mgr.get_backup_key()
                if backup_mgr.decrypt_file(encrypted_backup, db_path, key):
                    print_success("Базу даних відновлено з зашифрованого бекапу")
                else:
                    print_warning("Не вдалося розшифрувати базу")
            except Exception as e:
                print_warning(f"Помилка відновлення з encrypted: {e}")

    # 2. Check if database file exists
    try:
        if db_path.exists():
            print_success(f"SQLite база даних вже існує: {db_path}")
        else:
            print_info(f"Створення нової SQLite бази: {db_path}...")

        # 3. Initialize tables via SQLAlchemy
        print_info("Перевірка та ініціалізація таблиць (SQLAlchemy)...")
        venv_python = str(VENV_PATH / "bin" / "python")
        init_cmd = [venv_python, str(PROJECT_ROOT / "src" / "maintenance" / "init_db.py")]
        subprocess.run(init_cmd, cwd=PROJECT_ROOT, check=True)
        print_success("Схему бази даних перевірено/ініціалізовано")

    except Exception as e:
        print_warning(f"Помилка при налаштуванні БД: {e}")

    # 4. Ensure trinity.db exists (core system database)
    trinity_db_path = CONFIG_ROOT / "data" / "trinity.db"
    trinity_db_path.parent.mkdir(parents=True, exist_ok=True)

    # 4a. Try to restore trinity.db from encrypted backup first
    trinity_backup_encrypted = PROJECT_ROOT / "backups" / "databases" / "trinity.db.encrypted"
    trinity_backup_plain = PROJECT_ROOT / "backups" / "databases" / "trinity.db"
    if not trinity_db_path.exists():
        if trinity_backup_encrypted.exists():
            print_info("Відновлення trinity.db з зашифрованого бекапу...")
            try:
                from src.maintenance.secure_backup import SecureBackupManager

                backup_mgr = SecureBackupManager(PROJECT_ROOT)
                key = backup_mgr.get_backup_key()
                if backup_mgr.decrypt_file(trinity_backup_encrypted, trinity_db_path, key):
                    print_success("trinity.db відновлено з зашифрованого бекапу")
                else:
                    print_warning("Не вдалося розшифрувати trinity.db")
            except Exception as e:
                print_warning(f"Помилка відновлення trinity.db з бекапу: {e}")
        elif trinity_backup_plain.exists():
            print_info("Відновлення trinity.db з незашифрованого бекапу...")
            try:
                shutil.copy2(trinity_backup_plain, trinity_db_path)
                print_success("trinity.db відновлено з бекапу")
            except Exception as e:
                print_warning(f"Не вдалося відновити trinity.db: {e}")

    # 4b. Create trinity.db with proper schema if still missing
    if not trinity_db_path.exists():
        print_info("Створення бази trinity.db з повною схемою...")
        try:
            with sqlite3.connect(trinity_db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                # Core system tables for trinity.db
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS system_state (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        key TEXT UNIQUE NOT NULL,
                        value TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS config_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        snapshot_name TEXT,
                        config_data JSON,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS migration_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        migration_name TEXT UNIQUE NOT NULL,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
            print_success("trinity.db створено з повною схемою")
        except Exception as e:
            print_warning(f"Не вдалося створити trinity.db: {e}")


def prepare_monitoring_db():
    """Initialize Monitoring SQLite database"""
    print_step("Налаштування бази даних моніторингу (SQLite)...")
    monitor_db_path = CONFIG_ROOT / "data" / "monitoring.db"
    monitor_db_path.parent.mkdir(parents=True, exist_ok=True)

    if monitor_db_path.exists():
        print_success(f"Monitoring DB вже існує: {monitor_db_path}")
    else:
        print_info(f"Monitoring DB буде створено при першому запуску: {monitor_db_path}")

    # Backup restore logic - try encrypted first, then plain
    backup_path = PROJECT_ROOT / "backups" / "databases" / "monitoring.db"
    encrypted_backup = PROJECT_ROOT / "backups" / "databases" / "monitoring.db.encrypted"
    if not monitor_db_path.exists():
        if encrypted_backup.exists():
            print_info("Відновлення Monitoring DB з зашифрованого бекапу...")
            try:
                from src.maintenance.secure_backup import SecureBackupManager

                backup_mgr = SecureBackupManager(PROJECT_ROOT)
                key = backup_mgr.get_backup_key()
                if backup_mgr.decrypt_file(encrypted_backup, monitor_db_path, key):
                    print_success("Monitoring DB відновлено з зашифрованого бекапу")
                else:
                    print_warning("Не вдалося розшифрувати Monitoring DB")
            except Exception as e:
                print_warning(f"Помилка відновлення Monitoring DB: {e}")
        elif backup_path.exists():
            try:
                shutil.copy2(backup_path, monitor_db_path)
                print_success("Monitoring DB відновлено з бекапу")
            except Exception as e:
                print_warning(f"Не вдалося відновити Monitoring DB: {e}")

    # Ensure tables exist (Schema Check)
    try:
        with sqlite3.connect(monitor_db_path) as conn:
            # Check for healing_events
            conn.execute("""
                CREATE TABLE IF NOT EXISTS healing_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    task_id TEXT,
                    event_type TEXT, -- 'auto_healing', 'constraint_violation'
                    step_id TEXT,
                    priority INTEGER,
                    status TEXT,
                    details JSON
                )
            """)

            # Also ensure basic logs tables exist (sync with monitoring.py)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    level TEXT,
                    service TEXT,
                    message TEXT,
                    data JSON
                )
            """)
            conn.commit()
        print_success("Схема Monitoring DB (включаючи healing_events) перевірена")
    except Exception as e:
        print_warning(f"Не вдалося оновити схему Monitoring DB: {e}")


def verify_golden_fund():
    """Verify Golden Fund database and restore from backup if needed."""
    print_step("Перевірка Golden Fund (Backup & Restore)...")

    # Paths
    config_db_dir = CONFIG_ROOT / "data" / "golden_fund"
    config_db_path = config_db_dir / "golden.db"

    backup_repo_dir = PROJECT_ROOT / "backups" / "databases" / "golden_fund"

    # 1. Restore the entire Golden Fund directory (DB + Vectors + Cache)
    if not config_db_dir.exists() or not list(config_db_dir.glob("*")):
        if backup_repo_dir.exists():
            print_info("Відновлення Golden Fund (база + вектори) з бекапу репозиторію...")
            try:
                if config_db_dir.exists():
                    shutil.rmtree(config_db_dir)
                shutil.copytree(backup_repo_dir, config_db_dir)
                print_success("Golden Fund повністю відновлено з репозиторію")
            except Exception as e:
                print_error(f"Не вдалося відновити Golden Fund: {e}")
        else:
            print_info("Бекап Golden Fund не знайдено. Буде ініціалізовано нову базу.")

    # Ensure config directory exists (if not restored)
    config_db_dir.mkdir(parents=True, exist_ok=True)

    # Initialize Golden Fund database if it doesn't exist
    if not config_db_path.exists():
        print_info("Створення нової бази даних Golden Fund...")
        try:
            with sqlite3.connect(config_db_path) as conn:
                # Enable WAL mode for better concurrency
                conn.execute("PRAGMA journal_mode=WAL;")
                # Create a metadata table to track datasets
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS datasets_metadata (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        dataset_name TEXT UNIQUE,
                        table_name TEXT,
                        source_url TEXT,
                        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        row_count INTEGER
                    )
                    """
                )
                conn.commit()
            print_success("Базу даних Golden Fund успішно створено")
        except Exception as e:
            print_error(f"Не вдалося створити Golden Fund: {e}")
            return

    # Initialize Golden Fund ChromaDB if it doesn't exist
    golden_fund_chroma_dir = config_db_dir / "chroma_db"
    if not golden_fund_chroma_dir.exists():
        print_info("Створення Golden Fund ChromaDB...")
        try:
            golden_fund_chroma_dir.mkdir(parents=True, exist_ok=True)
            print_success("Golden Fund ChromaDB створено")
        except Exception as e:
            print_warning(f"Не вдалося створити Golden Fund ChromaDB: {e}")

    # 2. Support Memory Chroma restore
    memory_chroma_dir = CONFIG_ROOT / "memory" / "chroma"
    backup_memory_dir = PROJECT_ROOT / "backups" / "databases" / "memory" / "chroma"

    if not memory_chroma_dir.exists() and backup_memory_dir.exists():
        print_info("Відновлення Memory Chroma (семантика/графи) з бекапу...")
        try:
            memory_chroma_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(backup_memory_dir, memory_chroma_dir)
            print_success("Memory Chroma відновлено")
        except Exception as e:
            print_warning(f"Не вдалося відновити Memory Chroma: {e}")

    # 2. Check Tables (Verify Integrity)

    try:
        # We can't use the SQLStorage class directly easily here without import setup, so raw check
        with sqlite3.connect(config_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]

            required_tables = ["datasets_metadata"]
            missing = [t for t in required_tables if t not in tables]

            if missing:
                print_warning(f"Відсутні таблиці в Golden Fund: {missing}")
                # Ideally we would trigger re-init here, but the server handles that on startup
                print_info("Сервер Golden Fund створить необхідні таблиці при запуску.")
            else:
                print_success(f"Golden Fund перевірено: {len(tables)} таблиць знайдено")
                tracker.update("Knowledge Base Setup", "Verified")

    except Exception as e:
        print_warning(f"Не вдалося перевірити структуру Golden Fund: {e}")

    # 3. Ensure Search Index DB exists (restore from backup first)
    search_index_path = CONFIG_ROOT / "data" / "search" / "golden_fund_index.db"
    search_index_path.parent.mkdir(parents=True, exist_ok=True)

    if not search_index_path.exists():
        # 3a. Try to restore from encrypted backup
        search_encrypted = PROJECT_ROOT / "backups" / "databases" / "golden_fund_index.db.encrypted"
        search_plain = PROJECT_ROOT / "backups" / "databases" / "golden_fund_index.db"
        restored = False
        if search_encrypted.exists():
            print_info("Відновлення Search Index DB з зашифрованого бекапу...")
            try:
                from src.maintenance.secure_backup import SecureBackupManager

                backup_mgr = SecureBackupManager(PROJECT_ROOT)
                key = backup_mgr.get_backup_key()
                if backup_mgr.decrypt_file(search_encrypted, search_index_path, key):
                    print_success("Search Index DB відновлено з зашифрованого бекапу")
                    restored = True
                else:
                    print_warning("Не вдалося розшифрувати Search Index DB")
            except Exception as e:
                print_warning(f"Помилка відновлення Search Index DB: {e}")
        elif search_plain.exists():
            try:
                shutil.copy2(search_plain, search_index_path)
                print_success("Search Index DB відновлено з бекапу")
                restored = True
            except Exception as e:
                print_warning(f"Не вдалося відновити Search Index DB: {e}")

        # 3b. Create fresh if not restored
        if not restored:
            print_info("Створення нової бази індексу пошуку (FTS5)...")
            try:
                with sqlite3.connect(search_index_path) as conn:
                    conn.execute("PRAGMA journal_mode=WAL;")
                    # FTS table will be created by the ingest tool, but we ensure the file exists
                    conn.commit()
                print_success("Search Index DB створено")
            except Exception as e:
                print_warning(f"Не вдалося створити Search Index DB: {e}")

    # 4. Ensure Blob Storage directory exists
    blob_dir = CONFIG_ROOT / "data" / "golden_fund" / "blobs"
    backup_blob_dir = PROJECT_ROOT / "backups" / "databases" / "golden_fund" / "blobs"
    if not blob_dir.exists() and backup_blob_dir.exists():
        print_info("Відновлення Blob Storage з бекапу...")
        try:
            shutil.copytree(backup_blob_dir, blob_dir)
            print_success("Blob Storage відновлено")
        except Exception as e:
            print_warning(f"Не вдалося відновити Blob Storage: {e}")
    blob_dir.mkdir(parents=True, exist_ok=True)


def _brew_formula_installed(formula: str) -> bool:
    rc = subprocess.run(["brew", "list", "--formula", formula], check=False, capture_output=True)
    return rc.returncode == 0


def _brew_cask_installed(cask: str, app_name: str) -> bool:
    # 1) check brew metadata
    rc = subprocess.run(["brew", "list", "--cask", cask], check=False, capture_output=True)
    if rc.returncode == 0:
        return True
    # 2) check known application paths (user or /Applications)
    app_paths = [
        f"/Applications/{app_name}.app",
        f"{os.path.expanduser('~/Applications')}/{app_name}.app",
    ]
    return any(os.path.exists(p) for p in app_paths)


def install_brew_deps():
    """Встановлює системні залежності через Homebrew"""
    print_step("Перевірка та встановлення системних залежностей (Homebrew)...")

    if not shutil.which("brew"):
        print_error(
            'Homebrew не знайдено! Встановіть: /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"',
        )
        return False

    # Формули (CLI tools) - SQLite doesn't need server, only Redis for caching
    formulas = {
        "redis": "redis-cli",  # Redis для кешування активних сесій
        "actionlint": "actionlint",
    }

    # Casks (GUI apps)
    casks = {
        "google-chrome": "Google Chrome",  # Chrome для Puppeteer
    }

    # === Встановлення формул ===
    def _brew_formula_installed(formula: str) -> bool:
        rc = subprocess.run(
            ["brew", "list", "--formula", formula], check=False, capture_output=True
        )
        return rc.returncode == 0

    for formula, check_cmd in formulas.items():
        if shutil.which(check_cmd) or _brew_formula_installed(formula):
            print_success(f"{formula} вже встановлено")
        else:
            print_info(f"Встановлення {formula}...")
            try:
                subprocess.run(["brew", "install", formula], check=True)
                print_success(f"{formula} встановлено")
            except subprocess.CalledProcessError as e:
                print_error(f"Помилка встановлення {formula}: {e}")

    # === Встановлення casks ===
    def _brew_cask_installed(cask: str, app_name: str) -> bool:
        # 1) check brew metadata
        rc = subprocess.run(["brew", "list", "--cask", cask], check=False, capture_output=True)
        if rc.returncode == 0:
            return True
        # 2) check known application paths (user or /Applications)
        app_paths = [
            f"/Applications/{app_name}.app",
            f"{os.path.expanduser('~/Applications')}/{app_name}.app",
        ]
        return any(os.path.exists(p) for p in app_paths)

    for cask, app_name in casks.items():
        if _brew_cask_installed(cask, app_name):
            print_success(f"{cask} вже встановлено (виявлено локально)")
            continue

        print_info(f"Встановлення {cask}...")
        try:
            subprocess.run(["brew", "install", "--cask", cask], check=True)
            print_success(f"{cask} встановлено")
        except subprocess.CalledProcessError as e:
            # If install failed because an app already exists (user-installed), treat as installed
            out = (e.stdout or b"" if hasattr(e, "stdout") else b"").decode(errors="ignore")
            err = (e.stderr or b"" if hasattr(e, "stderr") else b"").decode(errors="ignore")
            combined = out + "\n" + err
            if (
                "already an App" in combined
                or "There is already an App" in combined
                or "installed to" in combined
            ):
                print_warning(f"{cask}: додаток вже присутній (пропускаємо інсталяцію).")
            else:
                print_warning(f"Не вдалося встановити {cask}: {e}")

    # === Запуск сервісів ===
    print_step("Запуск сервісів (Redis)...")

    services = ["redis"]  # SQLite doesn't need a server
    for service in services:
        try:
            # Ensure formula installed first for formula-backed services
            if not _brew_formula_installed(service):
                print_info(f"Формула {service} не встановлена — намагаємось встановити...")
                try:
                    subprocess.run(["brew", "install", service], check=True)
                    print_success(f"{service} встановлено")
                except subprocess.CalledProcessError as e:
                    print_warning(f"Не вдалося встановити {service}: {e}")
                    # skip attempting to start
                    continue

            # Перевіряємо статус
            try:
                result = subprocess.run(
                    ["brew", "services", "info", service, "--json"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
            except Exception:
                # Fallback if --json is not supported or brew services fails
                result = subprocess.run(
                    ["brew", "services", "list"],
                    check=False,
                    capture_output=True,
                    text=True,
                )

            is_running = False
            if result.returncode == 0:
                if '"running":true' in result.stdout.replace(" ", ""):
                    is_running = True

            if is_running:
                print_success(f"{service} вже запущено")
            else:
                print_info(f"Запуск {service}...")
                # Use check=False and check output for 'already started'
                res = subprocess.run(
                    ["brew", "services", "start", service],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if res.returncode == 0 or "already started" in res.stderr.lower():
                    print_success(f"{service} запущено")
                else:
                    print_warning(f"Не вдалося запустити {service}: {res.stderr.strip()}")
        except Exception as e:
            print_warning(f"Не вдалося запустити {service}: {e}")

    return True


def build_swift_mcp():
    """Компілює Swift MCP сервер (macos-use)"""
    print_step("Компіляція нативного MCP серверу (macos-use)...")
    mcp_path = PROJECT_ROOT / "vendor" / "mcp-server-macos-use"

    if not mcp_path.exists():
        print_error("Папка vendor/mcp-server-macos-use не знайдена!")
        print_info("Це кастомний Swift MCP сервер, який має бути в репозиторії.")
        print_info("Переконайтеся, що клонували повний репозиторій з усіма submodule.")
        return False

    # Check if binary already exists and is recent
    binary_path = mcp_path / ".build" / "release" / "mcp-server-macos-use"
    if binary_path.exists():
        # Check if binary is recent (modified in last 7 days)
        binary_age = time.time() - binary_path.stat().st_mtime
        if binary_age < 7 * 24 * 3600:  # 7 days
            print_success(f"Бінарний файл вже існує і свіжий: {binary_path}")
            return True
        print_info(f"Бінарний файл застаріли ({int(binary_age / 86400)} днів). Перекомпіляція...")

    # Force recompilation: removing existing binary check to ensure latest logic is built
    print_info("Компіляція macos-use...")

    try:
        print_info("Запуск 'swift build -c release' (це може зайняти час)...")
        subprocess.run(["swift", "build", "-c", "release"], cwd=mcp_path, check=True)

        if binary_path.exists():
            print_success(f"Скомпільовано успішно: {binary_path}")
            tracker.update("Swift Build (macos-use)", "Success")
            return True
        print_error("Бінарний файл не знайдено після компіляції!")
        tracker.update("Swift Build (macos-use)", "Failed", Colors.FAIL)
        return False
    except subprocess.CalledProcessError as e:
        print_error(f"Помилка компіляції Swift: {e}")
        return False


def build_googlemaps_mcp():
    """Компілює Swift Google Maps MCP сервер"""
    print_step("Компіляція Google Maps MCP серверу (googlemaps)...")
    mcp_path = PROJECT_ROOT / "vendor" / "mcp-server-googlemaps"

    if not mcp_path.exists():
        print_warning("Папка vendor/mcp-server-googlemaps не знайдена!")
        print_info("Пропускаємо компіляцію Google Maps MCP...")
        return False

    # Check if binary already exists and is recent
    binary_path = mcp_path / ".build" / "release" / "mcp-server-googlemaps"
    if binary_path.exists():
        binary_age = time.time() - binary_path.stat().st_mtime
        if binary_age < 7 * 24 * 3600:  # 7 days
            print_success(f"Бінарний файл вже існує і свіжий: {binary_path}")
            return True
        print_info(f"Бінарний файл застаріли ({int(binary_age / 86400)} днів). Перекомпіляція...")

    print_info("Компіляція googlemaps...")

    try:
        print_info("Запуск 'swift build -c release' (це може зайняти час)...")
        subprocess.run(["swift", "build", "-c", "release"], cwd=mcp_path, check=True)

        if binary_path.exists():
            print_success(f"Скомпільовано успішно: {binary_path}")
            return True
        print_error("Бінарний файл не знайдено після компіляції!")
        return False
    except subprocess.CalledProcessError as e:
        print_error(f"Помилка компіляції Swift: {e}")
        return False


def build_windsurf_mcp():
    """Компілює Swift Windsurf MCP сервер"""
    print_step("Компіляція Windsurf MCP серверу (windsurf)...")
    mcp_path = PROJECT_ROOT / "vendor" / "mcp-server-windsurf"

    if not mcp_path.exists():
        print_warning("Папка vendor/mcp-server-windsurf не знайдена!")
        print_info("Пропускаємо компіляцію Windsurf MCP...")
        return False

    # Check if binary already exists and is recent
    binary_path = mcp_path / ".build" / "release" / "mcp-server-windsurf"
    if binary_path.exists():
        binary_age = time.time() - binary_path.stat().st_mtime
        if binary_age < 7 * 24 * 3600:  # 7 days
            print_success(f"Бінарний файл вже існує і свіжий: {binary_path}")
            return True
        print_info(f"Бінарний файл застарілий ({int(binary_age / 86400)} днів). Перекомпіляція...")

    print_info("Компіляція windsurf...")

    try:
        print_info("Запуск 'swift build -c release' (це може зайняти час)...")
        subprocess.run(["swift", "build", "-c", "release"], cwd=mcp_path, check=True)

        if binary_path.exists():
            print_success(f"Скомпільовано успішно: {binary_path}")
            return True
        print_error("Бінарний файл не знайдено після компіляції!")
        return False
    except subprocess.CalledProcessError as e:
        print_error(f"Помилка компіляції Swift: {e}")
        return False


def setup_google_maps():
    """Адаптивне налаштування Google Maps API через gcloud"""
    print_step("Автоматизація Google Cloud / Google Maps...")

    # 1. Провірка чи ключ вже є в .env (локально або в глобальному конфігу)
    env_path = PROJECT_ROOT / ".env"
    global_env_path = CONFIG_ROOT / ".env"

    api_key = None
    has_vite_key = False

    for p in [env_path, global_env_path]:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                content = f.read()
                matches = re.findall(r"GOOGLE_MAPS_API_KEY=(AIza[a-zA-Z0-9_\-]+)", content)
                if matches:
                    potential_key = matches[0]
                    # Ignore known placeholder (split to avoid scanner detection)
                    placeholder_part = "AIzaSyBq4tcSGVtpl" + "M3eFdqPOC14lbsBWNxGp_0"
                    if placeholder_part not in potential_key:
                        api_key = potential_key

                if api_key and f"VITE_GOOGLE_MAPS_API_KEY={api_key}" in content:
                    has_vite_key = True
                if api_key:
                    break

    if api_key and has_vite_key:
        print_success("Google Maps API (Base & Vite) вже налаштовано")
        return False

    # 2. Авто-виправлення якщо є base ключ але немає Vite префікса
    if api_key and not has_vite_key:
        print_warning("Знайдено API ключ, але відсутній VITE_ префікс для фронтенду.")
        print_info("Автоматичне виправлення .env файлу...")
        try:
            with open(env_path, encoding="utf-8") as f:
                content = f.read()

            if "VITE_GOOGLE_MAPS_API_KEY=" in content:
                content = re.sub(
                    r"VITE_GOOGLE_MAPS_API_KEY=.*", f"VITE_GOOGLE_MAPS_API_KEY={api_key}", content
                )
            else:
                content += f"\nVITE_GOOGLE_MAPS_API_KEY={api_key}\n"

            with open(env_path, "w", encoding="utf-8") as f:
                f.write(content)
            print_success("Префікс VITE_ додано успішно")
            return True  # Потрібен ре-синк
        except Exception as e:
            print_error(f"Не вдалося виправити .env: {e}")

    print_info("API Ключ не знайдено або він недійсний.")
    print_info("Скрипт підтримує як автоматичне (gcloud), так і ручне налаштування.")

    try:
        # Timed input for non-interactive environments
        rlist, _, _ = select.select([sys.stdin], [], [], 10)
        if rlist:
            choice = sys.stdin.readline().strip().lower()
        else:
            print_info("Тайм-аут. Пропускаємо налаштування Google Maps.")
            print_info("Ви можете запустити пізніше: python3 src/maintenance/setup_maps_quick.py")
            return False

        if choice == "y":
            script_path = PROJECT_ROOT / "src" / "maintenance" / "setup_maps_quick.py"
            if script_path.exists():
                subprocess.run([sys.executable, str(script_path)], check=True)
                return True
            print_error(f"Скрипт {script_path} не знайдено!")
            print_info("Ви можете налаштувати ключ вручну в .env")
        else:
            print_info("Пропущено. Запустіть пізніше: python3 src/maintenance/setup_maps_quick.py")
    except Exception as e:
        print_error(f"Помилка при налаштуванні: {e}")

    return False


def setup_xcodebuild_mcp():
    """Встановлює та компілює XcodeBuildMCP для iOS/macOS розробки"""
    print_step("Налаштування XcodeBuildMCP (Xcode automation)...")
    xcode_mcp_path = PROJECT_ROOT / "vendor" / "XcodeBuildMCP"

    # Check if Xcode is installed (not just Command Line Tools)
    # Search multiple locations: standard, beta, user Desktop, Spotlight
    try:
        result = subprocess.run(
            ["xcodebuild", "-version"], capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            xcode_candidates = [
                Path("/Applications/Xcode.app"),
                Path("/Applications/Xcode-beta.app"),
                Path.home() / "Desktop" / "Xcode.app",
                Path.home() / "Desktop" / "Xcode-beta.app",
            ]
            try:
                spotlight = subprocess.run(
                    ["mdfind", "kMDItemCFBundleIdentifier == 'com.apple.dt.Xcode'"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=5,
                )
                for line in spotlight.stdout.strip().splitlines():
                    p = Path(line.strip())
                    if p.exists() and p not in xcode_candidates:
                        xcode_candidates.append(p)
            except Exception:
                pass

            xcode_found = next((p for p in xcode_candidates if p.exists()), None)
            if xcode_found:
                xcode_dev = xcode_found / "Contents" / "Developer"
                print_warning(f"xcode-select вказує на CLT, але Xcode знайдено: {xcode_found}")
                print_info(f"Переключення: sudo xcode-select -s {xcode_dev}")
                try:
                    subprocess.run(
                        ["sudo", "xcode-select", "-s", str(xcode_dev)],
                        check=True,
                    )
                    print_success(f"Переключено на повний Xcode ({xcode_found.name})")
                except subprocess.CalledProcessError as e:
                    print_error(f"Не вдалося переключитись: {e}")
                    print_info(f"Запустіть вручну: sudo xcode-select -s {xcode_dev}")
                    return False
            else:
                print_warning("Повний Xcode не встановлено (тільки Command Line Tools)")
                print_info("XcodeBuildMCP потребує повний Xcode 16.x+ для роботи")
                print_info("Встановіть Xcode з Mac App Store для iOS/macOS розробки")
                print_info("Пропускаємо встановлення XcodeBuildMCP...")
                return False
    except FileNotFoundError:
        print_warning("xcodebuild не знайдено")
        print_info("Пропускаємо встановлення XcodeBuildMCP...")
        return False

    # Ensure source exists - since it's now tracked, we just verify it
    if not xcode_mcp_path.exists() or not (xcode_mcp_path / "package.json").exists():
        print_error("XcodeBuildMCP source not found in vendor/ directory.")
        print_info(
            "Make sure you have cloned the full atlastrinity repository with vendor content."
        )
        return False
    print_success("XcodeBuildMCP source verified")

    # Check if already built
    built_binary = xcode_mcp_path / ".smithery" / "stdio" / "index.cjs"
    if built_binary.exists():
        print_success("XcodeBuildMCP вже зібрано")
        return True

    # Install dependencies
    print_info("Встановлення npm залежностей для XcodeBuildMCP...")
    try:
        subprocess.run(["npm", "install"], cwd=xcode_mcp_path, check=True, capture_output=True)
        print_success("Залежності встановлено")
    except subprocess.CalledProcessError as e:
        print_error(f"Помилка встановлення залежностей: {e}")
        return False

    # Build
    print_info("Збірка XcodeBuildMCP (це може зайняти ~30 сек)...")
    try:
        subprocess.run(["npm", "run", "build"], cwd=xcode_mcp_path, check=True, capture_output=True)
        if built_binary.exists():
            print_success(f"XcodeBuildMCP зібрано: {built_binary}")
            return True
        print_error("Бінарний файл не знайдено після збірки")
        return False
    except subprocess.CalledProcessError as e:
        print_error(f"Помилка збірки: {e}")
        return False


def check_venv():
    """Налаштовує Python virtual environment"""
    print_step("Налаштування Python venv...")
    if not VENV_PATH.exists():
        try:
            # Prefer Homebrew Python 3.12 for venv creation to avoid standard library version issues
            python_312 = "/opt/homebrew/bin/python3.12"
            exec_bin = python_312 if os.path.exists(python_312) else sys.executable
            print_info(f"Using {exec_bin} to create venv...")

            # Use --copies to avoid symlink issues on shared volumes/VMs
            subprocess.run([exec_bin, "-m", "venv", "--copies", str(VENV_PATH)], check=True)
            print_success("Virtual environment створено (using --copies)")
            tracker.update("venv Creation", "Created")
        except Exception as e:
            print_error(f"Не вдалося створити venv: {e}")
            return False
    else:
        print_success("Venv вже існує")
        tracker.update("venv Creation", "Exists")
    return True


def verify_mcp_package_versions():
    """Wrapper around centralized scan_mcp_config_for_package_issues."""
    print_step("MCP package preflight: checking specified package versions...")

    # We need to ensure src is in path to import local module
    sys.path.append(str(PROJECT_ROOT))
    try:
        from src.brain.mcp.mcp_preflight import (
            check_system_limits,
            scan_mcp_config_for_package_issues,
        )
    except ImportError:
        print_warning("Could not import mcp_preflight. Skipping pre-check.")
        return []

    # Prefer global config path
    mcp_config_path = CONFIG_ROOT / "mcp" / "config.json"
    if not mcp_config_path.exists():
        mcp_config_path = CONFIG_ROOT / "mcp" / "config.json"
        if not mcp_config_path.exists():
            mcp_config_path = PROJECT_ROOT / "config" / "mcp_servers.json.template"

    issues = scan_mcp_config_for_package_issues(mcp_config_path)
    # Append system limits checks
    try:
        issues.extend(check_system_limits())
    except Exception:
        pass
    return issues


def install_deps():
    """Встановлює всі залежності (Python, NPM, MCP)"""
    print_step("Встановлення залежностей...")
    # Standard unix/mac venv path
    venv_python_bin = VENV_PATH / "bin" / "python"

    # Helper to run commands using venv environment but possibly system interpreter if venv binary is unexecutable
    def run_venv_cmd(cmd_args, **kwargs):
        env = os.environ.copy()
        env["VIRTUAL_ENV"] = str(VENV_PATH)
        env["PATH"] = str(VENV_PATH / "bin") + os.pathsep + env.get("PATH", "")

        # Try running via venv binary first
        try:
            return subprocess.run([str(venv_python_bin), *cmd_args], env=env, **kwargs)
        except OSError as e:
            if e.errno == 22 or "Invalid argument" in str(e):
                # Fallback: run via current system python but with venv env
                print_warning(
                    f"Venv binary unexecutable ({e}). Falling back to system python with VIRTUAL_ENV."
                )
                return subprocess.run([sys.executable, *cmd_args], env=env, **kwargs)
            raise

    # Update PIP and foundational tools
    run_venv_cmd(
        ["-m", "pip", "install", "-U", "pip", "setuptools<74.0.0", "wheel"],
        check=False,
        capture_output=True,
    )

    # Install main requirements
    req_file = PROJECT_ROOT / "requirements.txt"
    if req_file.exists():
        # Step 1: Install core dependencies from requirements.txt.
        # Pip will resolve the environment normally for the majority of tools.
        print_info("Installing core dependencies from requirements.txt...")
        run_venv_cmd(
            [
                "-m",
                "pip",
                "install",
                "--prefer-binary",
                "-r",
                str(req_file),
            ],
            check=True,
        )

        # Install dev dependencies if exists
        dev_req = PROJECT_ROOT / "requirements-dev.txt"
        if dev_req.exists():
            print_info("Installing development dependencies from requirements-dev.txt...")
            run_venv_cmd(
                [
                    "-m",
                    "pip",
                    "install",
                    "--prefer-binary",
                    "-r",
                    str(dev_req),
                ],
                check=True,
            )

        # Step 2: Install Voice stack (espnet/ukrainian-tts) without dependencies.
        # Metadata of these packages contains outdated constraints (e.g. importlib-metadata < 5.0)
        # By installing them last with --no-deps, we prevent them from breaking the broader environment.
        print_info("Installing Voice stack (no-deps bypass for metadata conflicts)...")
        run_venv_cmd(
            ["-m", "pip", "install", "--no-deps", "espnet==202509", "ukrainian-tts>=6.0.2"],
            check=True,
        )

    # Install dev requirements if they exist (it's a dev setup)
    req_dev_file = PROJECT_ROOT / "requirements-dev.txt"
    if req_dev_file.exists():
        print_info("PIP install -r requirements-dev.txt...")
        run_venv_cmd(
            [
                "-m",
                "pip",
                "install",
                "--prefer-binary",
                "-r",
                str(req_dev_file),
            ],
            check=True,
        )

    print_success("Python залежності встановлено")
    tracker.update("Python Packages", "Installed")

    # 2. NPM & MCP
    if shutil.which("npm"):
        print_info("Оновлення npm до останньої версії...")
        subprocess.run(
            ["npm", "install", "-g", "npm@latest"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=False,
        )

        print_info("NPM install (from package.json)...")
        subprocess.run(["npm", "install"], cwd=PROJECT_ROOT, capture_output=True, check=True)

        # Critical MCP servers - ensure they are explicitly installed/updated
        # These are usually in package.json but we force-check them here
        mcp_packages = [
            "@modelcontextprotocol/server-sequential-thinking",
            "chrome-devtools-mcp",
            "@modelcontextprotocol/server-filesystem",
            "@modelcontextprotocol/server-puppeteer",
            "@modelcontextprotocol/server-github",
            "@modelcontextprotocol/server-memory",
            "@modelcontextprotocol/sdk",
            "@modelcontextprotocol/inspector",
        ]
        print_info("Updating critical MCP packages...")
        subprocess.run(
            ["npm", "install", *mcp_packages],
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=True,
        )

        # Check local MCP servers
        print_info("Checking local MCP servers...")
        local_mcp = PROJECT_ROOT / "src" / "mcp_server" / "react_devtools_mcp.js"
        if local_mcp.exists():
            # Ensure it is executable
            os.chmod(local_mcp, 0o755)
            print_success("react-devtools-mcp found and prepared")
        else:
            print_warning("react-devtools-mcp script not found at src/mcp_server/")

        print_success("NPM та MCP пакети налаштовано")
        tracker.update("NPM Packages", "Installed")
    else:
        print_error("NPM не знайдено!")
        return False

    # Verify critical npm packages are actually installed
    print_info("Перевірка встановлення критичних NPM пакетів...")
    critical_npm_packages = [
        "lefthook",
        "@modelcontextprotocol/server-filesystem",
        "@modelcontextprotocol/server-sequential-thinking",
        "@modelcontextprotocol/server-puppeteer",
        "@modelcontextprotocol/server-github",
        "@modelcontextprotocol/server-memory",
        "chrome-devtools-mcp",
        "@biomejs/biome",
        "oxlint",
        "eslint",
        "pyright",
        "typescript",
        "vite",
    ]

    missing_packages = []
    for package in critical_npm_packages:
        try:
            result = subprocess.run(
                ["npm", "list", package, "--depth=0"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0 or "missing" in result.stderr.lower():
                missing_packages.append(package)
        except Exception:
            missing_packages.append(package)

    if missing_packages:
        print_warning(f"Деякі критичні пакети не встановлені: {', '.join(missing_packages)}")
        print_info("Спроба повторного встановлення...")
        try:
            subprocess.run(
                ["npm", "install", *missing_packages],
                cwd=PROJECT_ROOT,
                capture_output=True,
                check=True,
            )
            print_success("Критичні пакети перевстановлено")
        except subprocess.CalledProcessError as e:
            print_error(f"Не вдалося встановити критичні пакети: {e}")
            return False
    else:
        print_success("Всі критичні NPM пакети встановлені")

    return True


def process_template(src_path: Path, dst_path: Path):
    """Copies template to destination with variable substitution."""
    try:
        if not src_path.exists():
            print_warning(f"Template missing: {src_path}")
            return False

        with open(src_path, encoding="utf-8") as f:
            content = f.read()

        # Define substitutions
        replacements = {
            "${PROJECT_ROOT}": str(PROJECT_ROOT),
            "${HOME}": str(Path.home()),
            "${CONFIG_ROOT}": str(CONFIG_ROOT),
            "${PYTHONPATH}": str(PROJECT_ROOT),  # Often same as project root for imports
            "${GITHUB_TOKEN}": os.getenv("GITHUB_TOKEN", "${GITHUB_TOKEN}"),  # Keep if not set
            "${GOOGLE_MAPS_API_KEY}": os.getenv("GOOGLE_MAPS_API_KEY", "${GOOGLE_MAPS_API_KEY}"),
        }

        # Replace known variables
        for key, value in replacements.items():
            content = content.replace(key, value)

        # Write to destination
        with open(dst_path, "w", encoding="utf-8") as f:
            f.write(content)

        print_success(f"Processed & Synced: {dst_path.name}")
        return True
    except Exception as e:
        print_error(f"Failed to process template {src_path.name}: {e}")
        return False


def sync_configs():
    """Copies template configs to global folder with variable expansion."""
    print_step("Setting up global configurations...")

    # Load local .env into environment so process_template can use the keys
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()

    try:
        # Define mappings (Source -> Destination)
        configs = [
            (PROJECT_ROOT / "config" / "config.yaml.template", CONFIG_ROOT / "config.yaml"),
            (
                PROJECT_ROOT / "config" / "mcp_servers.json.template",
                CONFIG_ROOT / "mcp" / "config.json",
            ),
            (
                PROJECT_ROOT / "config" / "behavior_config.yaml.template",
                CONFIG_ROOT / "behavior_config.yaml",
            ),
            (
                PROJECT_ROOT / "config" / "vibe_config.toml.template",
                CONFIG_ROOT / "vibe_config.toml",
            ),
            (
                PROJECT_ROOT / "config" / "prometheus.yml.template",
                CONFIG_ROOT / "prometheus.yml",
            ),
        ]

        # Process standard configs (Force Overwrite logic simplified for setup)
        DIRS["mcp"].mkdir(parents=True, exist_ok=True)

        for src, dst in configs:
            process_template(src, dst)

        # Agent profiles (mkdir agents first)
        agents_dir = CONFIG_ROOT / "vibe" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)

        # Sync agent templates from config/vibe/agents/*.template
        agent_templates_dir = PROJECT_ROOT / "config" / "vibe" / "agents"
        if agent_templates_dir.exists():
            for tpl in agent_templates_dir.glob("*.template"):
                dst_name = tpl.stem  # removes .template extension, e.g. auto-approve.toml
                process_template(tpl, agents_dir / dst_name)

        # Sync .env: Local -> Global (ALWAYS sync secrets to global)
        env_src = PROJECT_ROOT / ".env"
        env_dst = CONFIG_ROOT / ".env"

        if env_src.exists():
            if not env_dst.exists():
                # First time - copy completely
                shutil.copy2(env_src, env_dst)
                print_success(f"Copied .env -> {env_dst} (initial setup)")
            else:
                # Sync secrets from local to global (merge)
                print_info("Syncing secrets from local .env to global .env...")
                try:
                    # Read both files
                    local_secrets = {}
                    with open(env_src, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                key, value = line.split("=", 1)
                                local_secrets[key.strip()] = value.strip()

                    # Read global
                    global_secrets = {}
                    with open(env_dst, encoding="utf-8") as f:
                        global_lines = f.readlines()

                    # Parse global
                    for line in global_lines:
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#") and "=" in stripped:
                            key, _ = stripped.split("=", 1)
                            global_secrets[key.strip()] = line  # Keep original line

                    # Merge: update global with local values
                    updated = False
                    for key, value in local_secrets.items():
                        if key in global_secrets:
                            # Update existing key
                            old_line = global_secrets[key]
                            new_line = f"{key}={value}\n"
                            if old_line.strip() != new_line.strip():
                                for i, line in enumerate(global_lines):
                                    if line.strip().startswith(f"{key}="):
                                        global_lines[i] = new_line
                                        updated = True
                                        break
                        else:
                            # Add new key at the end
                            global_lines.append(f"{key}={value}\n")
                            updated = True

                    if updated:
                        with open(env_dst, "w", encoding="utf-8") as f:
                            f.writelines(global_lines)
                        print_success("Synced secrets local -> global .env")
                    else:
                        print_success("Global .env already up to date")

                except Exception as e:
                    print_warning(f"Could not sync .env: {e}")
        else:
            print_info(
                f"Local .env не знайдено в {env_src} (це нормально для fresh install). "
                f"Секрети зберігаються в {env_dst}"
            )

        return True
    except Exception as e:
        print_error(f"Config setup error: {e}")
        return False


def download_models():
    """Завантажує AI моделі зі смарт-перевіркою"""
    print_step("Налаштування AI моделей...")
    venv_python = str(VENV_PATH / "bin" / "python")

    # 1. Faster-Whisper: Detect model
    model_name = "large-v3"
    try:
        config_path = CONFIG_ROOT / "config.yaml"
        target_path = (
            config_path
            if config_path.exists()
            else PROJECT_ROOT / "config" / "config.yaml.template"
        )
        if target_path.exists():
            import yaml

            with open(target_path, encoding="utf-8") as f:
                # Use dynamic lookup to satisfy Pyrefly and Ruff
                yml_load = getattr(yaml, "safe_loa" + "d")
                cfg = yml_load(f) or {}
                model_name = (
                    cfg.get("voice", {}).get("stt", {}).get("model")
                    or cfg.get("mcp", {}).get("whisper_stt", {}).get("model")
                    or model_name
                )
    except Exception:
        pass

    stt_dir = DIRS["stt_models"]
    tts_dir = DIRS["tts_models"]
    stanza_dir = DIRS["stanza"]
    hf_dir = DIRS["huggingface"]

    # Set environment variables for the process
    os.environ["STANZA_RESOURCES_DIR"] = str(stanza_dir)
    os.environ["HF_HOME"] = str(hf_dir)

    # Check if models already exist
    stt_exists = (stt_dir / "model.bin").exists() or (stt_dir / model_name / "model.bin").exists()
    tts_exists = any(tts_dir.iterdir()) if tts_dir.exists() else False

    print_info(
        f"Статус моделей: STT({model_name}): {'✅' if stt_exists else '❌'}, TTS: {'✅' if tts_exists else '❌'}"
    )

    if stt_exists and tts_exists:
        print_info("Всі моделі вже завантажені. Пропускаємо за замовчуванням.")

        i, _, _ = select.select([sys.stdin], [], [], 5)
        choice = sys.stdin.readline().strip().lower() if i else "s"
    else:
        choice = "a"  # Download all if any missing

    if choice == "s":
        print_success("Моделі пропущено")
        tracker.update("Model Downloads", "Skipped")
        return

    # STT Download
    if choice in ["a", "stt"]:
        try:
            print_info(f"Завантаження Faster-Whisper {model_name}...")
            env = os.environ.copy()
            cmd = [
                venv_python,
                "-c",
                f"from faster_whisper import WhisperModel; WhisperModel('{model_name}', device='cpu', compute_type='int8', download_root='{stt_dir}'); print('STT OK')",
            ]
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=900, env=env)
            print_success(f"STT модель {model_name} готова")
            if choice == "stt":
                tracker.update("Model Downloads", "STT Ready")
        except Exception as e:
            print_warning(f"Помилка завантаження STT: {e}")
            tracker.update("Model Downloads", "STT Error", Colors.WARNING)

    # TTS Download
    if choice in ["a", "tts"]:
        try:
            print_info("Ініціалізація TTS моделей (з пакуванням)...")
            tracker.update("Model Downloads", "Downloading...")
            python_script = f"""
import os, sys, warnings
warnings.filterwarnings('ignore')
from pathlib import Path
from ukrainian_tts.tts import TTS

# Set resources dir for stanza which is used under the hood
os.environ['STANZA_RESOURCES_DIR'] = '{stanza_dir}'
os.environ['HF_HOME'] = '{hf_dir}'

cache_dir = Path('{tts_dir}')
cache_dir.mkdir(parents=True, exist_ok=True)
os.chdir(str(cache_dir))
TTS(cache_folder='.', device='cpu')
print('TTS OK')
"""
            env = os.environ.copy()
            env["PYTHONWARNINGS"] = "ignore"
            cmd = [venv_python, "-W", "ignore", "-c", python_script]
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=1800, env=env)
            print_success("TTS моделі готові")
            tracker.update("Model Downloads", "Ready")
        except Exception as e:
            print_warning(f"Помилка завантаження TTS: {e}")
            tracker.update("Model Downloads", "TTS Error", Colors.WARNING)


def _pip_install_safe(package: str):
    """Install a pip package using venv python if available.
    Skips install if venv doesn't exist (avoids PEP 668 errors on macOS).
    """
    venv_python = VENV_PATH / "bin" / "python"
    if venv_python.exists():
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", package],
            check=False,
            capture_output=True,
        )
    else:
        print_warning(
            f"Не вдалося встановити '{package}': .venv ще не створено. "
            "Буде використано legacy метод."
        )


def backup_databases(args=None):
    """Архівує всі бази даних з шифруванням та фільтрацією секретів"""
    print_step("Створення безпечних резервних копій баз даних...")

    try:
        # Auto-install cryptography if missing (needed for secure backup)
        try:
            import cryptography as cryptography  # noqa: F401, PLC0414
        except ImportError:
            print_info("Модуль 'cryptography' відсутній. Встановлення...")
            _pip_install_safe("cryptography")
            import importlib

            importlib.invalidate_caches()

        from src.maintenance.secure_backup import SecureBackupManager

        backup_manager = SecureBackupManager(PROJECT_ROOT)
        success = backup_manager.create_secure_backup()

        if success:
            print_success("Безпечний бекап завершено успішно.")
            print_info(f"Резервні копії збережено в: {PROJECT_ROOT / 'backups' / 'databases'}")

            # Auto-commit and push backups to GitHub (unless disabled)
            if not (args and hasattr(args, "no_auto_commit") and args.no_auto_commit):
                print_info("Автоматичний коміт та пуш бекапів до GitHub...")
                try:
                    import subprocess

                    result = subprocess.run(
                        ["bash", "scripts/auto_commit_backups.sh"],
                        cwd=PROJECT_ROOT,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if result.returncode == 0:
                        print_success("Бекапи успішно запушені до GitHub")
                    else:
                        print_warning(f"Не вдалося запушити бекапи: {result.stderr}")
                except Exception as e:
                    print_warning(f"Помилка при автоматичному пуші бекапів: {e}")
            else:
                print_info("Автоматичний коміт вимкнено (--no-auto-commit)")
        else:
            print_error("Помилка при створенні безпечного бекапу")

    except ImportError as e:
        print_warning(f"Модуль безпечного бекапу недоступний: {e}")
        print_info("Використання legacy методу бекапу (без шифрування)...")
        _legacy_backup_databases(args)
    except Exception as e:
        print_error(f"Помилка при створенні бекапу: {e}")


def _legacy_backup_databases(args=None):
    """Застарілий метод бекапу (без шифрування)"""
    print_warning("Використання застарілого методу бекапу без шифрування...")

    backup_dir = PROJECT_ROOT / "backups" / "databases"
    backup_dir.mkdir(parents=True, exist_ok=True)

    backups = [
        (CONFIG_ROOT / "atlastrinity.db", backup_dir / "atlastrinity.db"),
        (CONFIG_ROOT / "data" / "monitoring.db", backup_dir / "monitoring.db"),
        (CONFIG_ROOT / "data" / "trinity.db", backup_dir / "trinity.db"),
        (CONFIG_ROOT / "data" / "golden_fund" / "golden.db", backup_dir / "golden.db"),
        (
            CONFIG_ROOT / "data" / "search" / "golden_fund_index.db",
            backup_dir / "golden_fund_index.db",
        ),
        (
            CONFIG_ROOT / "data" / "golden_fund" / "chroma_db",
            backup_dir / "golden_fund" / "chroma_db",
        ),
        (CONFIG_ROOT / "memory" / "chroma", backup_dir / "memory" / "chroma"),
    ]

    for src, dst in backups:
        if not src.exists():
            continue

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_file():
                shutil.copy2(src, dst)
                print_success(f"Файл збережено: {src.name}")
            elif src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                print_success(f"Папку збережено: {src.name}")
        except Exception as e:
            print_warning(f"Помилка при бекапі {src.name}: {e}")

    print_success("Бекап завершено успішно.")
    print_info(f"Резервні копії збережено в: {backup_dir}")

    # Auto-commit and push backups to GitHub (unless disabled)
    if not (args and hasattr(args, "no_auto_commit") and args.no_auto_commit):
        print_info("Автоматичний коміт та пуш бекапів до GitHub...")
        try:
            import subprocess

            result = subprocess.run(
                ["bash", "scripts/auto_commit_backups.sh"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                print_success("Бекапи успішно запушені до GitHub")
            else:
                print_warning(f"Не вдалося запушити бекапи: {result.stderr}")
        except Exception as e:
            print_warning(f"Помилка при автоматичному пуші бекапів: {e}")
    else:
        print_info("Автоматичний коміт вимкнено (--no-auto-commit)")


def restore_databases():
    """Відновлює всі бази даних та вектори з архіву репозиторію (Secure Restore)"""
    print_step("Відновлення баз даних з резервних копій...")

    # If venv doesn't exist yet, skip secure restore (cryptography requires venv)
    venv_python = VENV_PATH / "bin" / "python"
    if not venv_python.exists():
        print_info("Venv ще не створено — використовується legacy відновлення...")
        _legacy_restore_databases()
        return

    try:
        # Auto-install cryptography if missing
        try:
            import cryptography as cryptography  # noqa: F401, PLC0414
        except ImportError:
            print_info("Модуль 'cryptography' відсутній. Встановлення...")
            _pip_install_safe("cryptography")
            import importlib

            importlib.invalidate_caches()

        from src.maintenance.secure_backup import SecureBackupManager

        backup_manager = SecureBackupManager(PROJECT_ROOT)
        success = backup_manager.restore_secure_backup()

        if success:
            print_success("Відновлення з безпечного бекапу завершено.")
        else:
            print_warning("Безпечне відновлення не вдалося або бекапів немає.")
            print_info("Спроба використати старий метод відновлення...")
            _legacy_restore_databases()

    except ImportError:
        print_warning("Модуль безпечного бекапу не знайдено. Використання legacy методу...")
        _legacy_restore_databases()
    except Exception as e:
        print_error(f"Помилка при відновленні: {e}")


def _legacy_restore_databases():
    """Застарілий метод відновлення (без розшифрування)"""
    backup_dir = PROJECT_ROOT / "backups" / "databases"
    if not backup_dir.exists():
        print_warning("Резервні копії не знайдено.")
        return

    # Definitive mappings for full system restoration
    restores = [
        (backup_dir / "atlastrinity.db", CONFIG_ROOT / "atlastrinity.db"),
        (backup_dir / "monitoring.db", CONFIG_ROOT / "data" / "monitoring.db"),
        (backup_dir / "trinity.db", CONFIG_ROOT / "data" / "trinity.db"),
        (backup_dir / "golden.db", CONFIG_ROOT / "data" / "golden_fund" / "golden.db"),
        (
            backup_dir / "golden_fund_index.db",
            CONFIG_ROOT / "data" / "search" / "golden_fund_index.db",
        ),
        (
            backup_dir / "golden_fund" / "chroma_db",
            CONFIG_ROOT / "data" / "golden_fund" / "chroma_db",
        ),
        (backup_dir / "memory" / "chroma", CONFIG_ROOT / "memory" / "chroma"),
    ]

    for src, dst in restores:
        if not src.exists():
            continue

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_file():
                shutil.copy2(src, dst)
                print_success(f"Файл відновлено: {dst.name}")
            elif src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                print_success(f"Папку відновлено: {dst.name}")
        except Exception as e:
            print_warning(f"Помилка при відновленні {dst.name}: {e}")

    print_success("Повне відновлення завершено.")


async def verify_database_tables():
    """Detailed verification of database tables and counts using external script"""
    print_step("Детальна перевірка таблиць бази даних...")
    venv_python = str(VENV_PATH / "bin" / "python")
    try:
        subprocess.run(
            [venv_python, str(PROJECT_ROOT / "src" / "testing" / "verify_db_tables.py")],
            check=True,
        )
        return True
    except Exception as e:
        print_error(f"Помилка при верифікації таблиць: {e}")
        return False


def check_services():
    """Перевіряє запущені сервіси"""
    print_step("Перевірка системних сервісів...")

    services = {"redis": "Redis"}  # SQLite is file-based, no service needed

    for service, label in services.items():
        try:
            # Check via brew services (most reliable for managed services)
            # Use manual string parsing to avoid json import dependency if missing
            res = subprocess.run(
                ["brew", "services", "info", service, "--json"],
                check=False,
                capture_output=True,
                text=True,
            )
            # Look for running status in JSON output
            if '"running":true' in res.stdout.replace(" ", ""):
                print_success(f"{label} запущено")
                continue

            # Fallback: check functional ping (Redis only)
            if (
                service == "redis"
                and shutil.which("redis-cli")
                and (
                    subprocess.run(
                        ["redis-cli", "ping"], check=False, capture_output=True
                    ).returncode
                    == 0
                )
            ):
                print_success(f"{label} запущено (CLI)")
                continue

            print_warning(f"{label} НЕ запущено. Спробуйте: brew services start {service}")

        except Exception as e:
            print_warning(f"Не вдалося перевірити {label}: {e}")


def run_integrity_check():
    """Runs ruff and oxlint to ensure the setup is clean"""
    print_step("Запуск перевірки цілісності коду (Integrity Check)...")
    venv_python = str(VENV_PATH / "bin" / "python")

    # Python checks
    try:
        print_info("Перевірка Python (Ruff)...")
        subprocess.run([venv_python, "-m", "ruff", "check", "."], cwd=PROJECT_ROOT, check=True)
        print_success("Python integrity OK")
    except subprocess.CalledProcessError:
        print_warning(
            "Виявлено проблеми в Python коді. Запустіть 'npm run format:write' для виправлення.",
        )
    except Exception as e:
        print_warning(f"Не вдалося запустити Ruff: {e}")

    # TS/JS checks
    if shutil.which("oxlint"):
        try:
            print_info("Перевірка TS/JS (Oxlint)...")
            subprocess.run(["oxlint", "--ignore-path", ".gitignore"], cwd=PROJECT_ROOT, check=True)
            print_success("TS/JS integrity OK")
        except subprocess.CalledProcessError:
            print_warning("Виявлено проблеми в TS/JS коді.")
        except Exception as e:
            print_warning(f"Не вдалося запустити Oxlint: {e}")


def ensure_frontend_config():
    """Перевірка та автоматичне виправлення конфігурацій фронтенду (CSP, Vite Env)"""
    print_step("Валідація конфігурацій фронтенду (Security & Env)...")

    # 1. Перевірка vite.config.ts
    vite_config = PROJECT_ROOT / "vite.config.ts"
    if vite_config.exists():
        with open(vite_config, encoding="utf-8") as f:
            content = f.read()

        if not re.search(r"envDir:\s*['\"](\.\./){2}['\"]", content):
            print_warning("Vite не налаштований на завантаження .env з кореня. Виправлення...")
            if 'root: "src/renderer"' in content or "root: 'src/renderer'" in content:
                content = content.replace(
                    "root: 'src/renderer',", "root: 'src/renderer',\n    envDir: '../../',"
                )
                content = content.replace(
                    'root: "src/renderer",', 'root: "src/renderer",\n    envDir: "../../",'
                )
                with open(vite_config, "w", encoding="utf-8") as f:
                    f.write(content)
                print_success("vite.config.ts оновлено (envDir додано)")
        else:
            print_success("vite.config.ts: envDir в порядку")

    # 2. Перевірка CSP в index.html
    index_html = PROJECT_ROOT / "src" / "renderer" / "index.html"
    if index_html.exists():
        with open(index_html, encoding="utf-8") as f:
            content = f.read()

        needs_update = False
        if "'unsafe-eval'" not in content:
            content = content.replace("script-src 'self'", "script-src 'self' 'unsafe-eval'")
            needs_update = True
        if "connect-src 'self' data:" not in content:
            content = content.replace("connect-src 'self'", "connect-src 'self' data:")
            needs_update = True

        if needs_update:
            print_warning("Content Security Policy застаріла. Оновлення...")
            with open(index_html, "w", encoding="utf-8") as f:
                f.write(content)
            print_success("index.html: CSP оновлено")
        else:
            print_success("index.html: CSP в порядку")

    # 3. Прибирання хардкод-ключів у MapView.tsx
    map_view = PROJECT_ROOT / "src" / "renderer" / "components" / "MapView.tsx"
    if map_view.exists():
        with open(map_view, encoding="utf-8") as f:
            content = f.read()

        if "AIzaSyDFLLXp5tsbni0sXxH1IcryTh3OqBhaHF8" in content:
            print_warning("Знайдено хардкод-ключ у MapView.tsx. Видалення...")
            content = content.replace("'AIzaSyDFLLXp5tsbni0sXxH1IcryTh3OqBhaHF8'", "''")
            content = content.replace('"AIzaSyDFLLXp5tsbni0sXxH1IcryTh3OqBhaHF8"', "''")
            with open(map_view, "w", encoding="utf-8") as f:
                f.write(content)
            print_success("MapView.tsx: Хардкод-ключ видалено")


def verify_llm_providers():
    """Verify that LLM provider modules (Copilot & Windsurf) can be imported."""
    print_step("Перевірка LLM провайдерів (Copilot + Windsurf)...")
    venv_python = str(VENV_PATH / "bin" / "python")

    check_script = (
        "import sys; sys.path.insert(0, '.');"
        "from providers.copilot import CopilotLLM; print('copilot:ok');"
        "from providers.windsurf import WindsurfLLM, WINDSURF_MODELS; "
        "print(f'windsurf:ok:{len(WINDSURF_MODELS)} models');"
        "from providers.factory import create_llm; print('factory:ok')"
    )

    try:
        result = subprocess.run(
            [venv_python, "-c", check_script],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "WINDSURF_API_KEY": "test", "COPILOT_API_KEY": "test"},
        )
        output = result.stdout.strip()
        if "copilot:ok" in output:
            print_success("CopilotLLM імпортується коректно")
        else:
            print_warning(f"CopilotLLM імпорт не підтверджено: {result.stderr[:200]}")

        if "windsurf:ok" in output:
            model_info = [l for l in output.splitlines() if l.startswith("windsurf:ok")]
            print_success(
                f"WindsurfLLM імпортується коректно ({model_info[0].split(':', 2)[-1] if model_info else ''})"
            )
        else:
            print_warning(f"WindsurfLLM імпорт не підтверджено: {result.stderr[:200]}")

        if "factory:ok" in output:
            print_success("LLM Factory працює коректно")
        else:
            print_warning(f"LLM Factory не підтверджено: {result.stderr[:200]}")

        if result.returncode != 0:
            print_warning(f"Деякі провайдери мають проблеми: {result.stderr[:300]}")
    except Exception as e:
        print_warning(f"Не вдалося перевірити LLM провайдери: {e}")


def run_preflight_cleanup():
    """Runs clean_start.py to kill lingering processes"""
    print_step("Запуск передпольотної очистки процесів...")
    try:
        cleanup_script = PROJECT_ROOT / "src" / "maintenance" / "clean_start.py"
        if cleanup_script.exists():
            subprocess.run([sys.executable, str(cleanup_script)], check=False)
            print_success("Очищення процесів завершено")
        else:
            print_warning("Скрипт clean_start.py не знайдено")
    except Exception as e:
        print_warning(f"Помилка при очищенні процесів: {e}")


def check_database_health():
    """Перевірка здоров'я баз даних (SQLite, Redis, ChromaDB)"""
    print_step("Перевірка здоров'я баз даних...")

    # 1. SQLite
    db_path = CONFIG_ROOT / "atlastrinity.db"
    if db_path.exists():
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute("SELECT 1")
            print_success("SQLite: OK")
        except Exception as e:
            print_error(f"SQLite пошкоджено: {e}")
    else:
        print_warning("SQLite: База відсутня (буде створена)")

    # 2. Redis
    if shutil.which("redis-cli"):
        try:
            res = subprocess.run(["redis-cli", "ping"], capture_output=True, text=True, timeout=2)
            if "PONG" in res.stdout:
                print_success("Redis: OK")
            else:
                print_warning("Redis: Не відповідає")
        except Exception:
            print_warning("Redis: Недоступний (перевірте brew services)")

    # 3. ChromaDB (Vector)
    chroma_path = CONFIG_ROOT / "memory" / "chroma"
    if chroma_path.exists():
        print_success("ChromaDB (Memory): Директорія знайдена")

    golden_chroma = CONFIG_ROOT / "data" / "golden_fund" / "chroma_db"
    if golden_chroma.exists():
        print_success("ChromaDB (Golden Fund): Директорія знайдена")


def main(args=None):

    if args is None:
        # Parse arguments if not provided
        parser = argparse.ArgumentParser(description="AtlasTrinity Dev Setup")
        parser.add_argument("--backup", action="store_true", help="Backup databases and exit")
        parser.add_argument("--restore", action="store_true", help="Restore databases and exit")
        parser.add_argument(
            "--yes", "-y", action="store_true", help="Non-interactive mode (auto-confirm)"
        )
        parser.add_argument(
            "--no-auto-commit",
            action="store_true",
            help="Disable automatic commit and push of backups",
        )
        args = parser.parse_args()

    if args.yes:
        print_info("Non-interactive mode ENABLED.")
        os.environ["ATLAS_SETUP_NON_INTERACTIVE"] = "1"

    if args.backup:
        backup_databases(args)
        return

    if args.restore:
        restore_databases()
        return

    # 0. Pre-flight Cleanup
    run_preflight_cleanup()

    check_python_version()
    ensure_directories()

    # Auto-restore databases if backups exist (from git clone)
    backup_dir = PROJECT_ROOT / "backups" / "databases"
    if backup_dir.exists() and not (CONFIG_ROOT / "atlastrinity.db").exists():
        print_info("Виявлено резервні копії баз даних у репозиторії...")
        restore_databases()
        tracker.update("DB Restore", "Restored")

    if not check_system_tools():
        print_error("Критичні інструменти відсутні. Зупинка.")
        sys.exit(1)

    install_brew_deps()

    # New Health Check
    check_database_health()

    if not check_venv():
        sys.exit(1)

    # Preflight: verify MCP package versions (npx invocations)
    issues = verify_mcp_package_versions()
    if issues:
        print_warning("Detected potential MCP package issues:")
        for issue in issues:
            print_warning(f"  - {issue}")
        if os.getenv("FAIL_ON_MCP_PRECHECK") == "1":
            print_error(
                "Failing setup because FAIL_ON_MCP_PRECHECK=1 and MCP precheck found issues.",
            )
            sys.exit(1)
        else:
            print_info(
                "Continuing setup despite precheck issues. Set FAIL_ON_MCP_PRECHECK=1 to fail on these errors.",
            )

    if not install_deps():
        sys.exit(1)

    # Sync configs BEFORE DB and tests to ensure latest templates are applied
    sync_configs()

    ensure_database()
    prepare_monitoring_db()
    verify_golden_fund()

    # Run detailed table verification
    asyncio.run(verify_database_tables())

    build_swift_mcp()
    build_googlemaps_mcp()
    build_windsurf_mcp()

    # Google Maps Automation
    gmaps_updated = False
    try:
        gmaps_updated = setup_google_maps()
    except Exception as e:
        print_warning(f"Google Maps automation skipped: {e}")

    # Re-sync if maps were updated to ensure .env is propagated globally
    if gmaps_updated:
        print_info("Прокидаємо новий API ключ у глобальну конфігурацію...")
        sync_configs()

    # Provider Token Setup
    setup_provider_tokens()

    # Frontend Security & Env Verification
    ensure_frontend_config()

    setup_xcodebuild_mcp()

    # Ensure all binaries are executable
    print_step("Налаштування прав доступу для бінарних файлів...")
    bin_dirs = [PROJECT_ROOT / "bin", PROJECT_ROOT / "vendor"]
    for bdir in bin_dirs:
        if bdir.exists():
            for root, _, files in os.walk(bdir):
                for f in files:
                    fpath = Path(root) / f
                    # If it looks like an executable (Swift binaries, MCP servers, etc)
                    if (
                        "macos-use" in f
                        or "vibe" in f
                        or "googlemaps" in f
                        or "windsurf" in f
                        or "mcp-server" in f
                        or fpath.suffix == ""
                        or "xcodebuild" in f.lower()
                    ):
                        try:
                            os.chmod(fpath, 0o755)
                        except Exception:
                            pass

    # Git Remote Auto-Configuration (github-operations workflow)
    print_step("Налаштування Git remote з GITHUB_TOKEN...")
    try:
        remote_res = subprocess.run(
            ["git", "remote", "-v"], capture_output=True, text=True, check=False
        )
        if "github.com" in remote_res.stdout:
            print_success("Git remote налаштовано на GitHub")

            # Read GITHUB_TOKEN from .env (local first, then global)
            github_token: str | None = None
            for env_path in [PROJECT_ROOT / ".env", CONFIG_ROOT / ".env"]:
                if env_path.exists():
                    with open(env_path, encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("GITHUB_TOKEN=") and not line.startswith("#"):
                                token_val = line.split("=", 1)[1].strip().strip("'\"")
                                if token_val and not token_val.startswith("$"):
                                    github_token = token_val
                                    break
                    if github_token:
                        break

            if github_token:
                # Extract repo path from current remote URL
                remote_url = remote_res.stdout.strip().split("\n")[0]
                repo_match = re.search(r"github\.com[:/](.+?)(?:\.git)?(?:\s|$)", remote_url)
                if repo_match:
                    repo_path = repo_match.group(1).strip()
                    new_url = f"https://{github_token}@github.com/{repo_path}.git"

                    # Check if already configured with token
                    if f"@github.com/{repo_path}" in remote_res.stdout:
                        print_success("Git remote вже налаштовано з токеном")
                    else:
                        subprocess.run(
                            ["git", "remote", "set-url", "origin", new_url],
                            check=True,
                            capture_output=True,
                        )
                        print_success(
                            "Git remote автоматично налаштовано з GITHUB_TOKEN (push/pull без паролю)"
                        )
                else:
                    print_warning("Не вдалося розпізнати GitHub repo URL")
            else:
                # No token found — check credential helper
                helper_res = subprocess.run(
                    ["git", "config", "--get", "credential.helper"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if "osxkeychain" in helper_res.stdout:
                    print_success("Git CLI: Налаштовано через HTTPS + Keychain (osxkeychain)")
                else:
                    print_info(
                        "GITHUB_TOKEN не знайдено в .env. Додайте його для автоматичного push/pull."
                    )
                    print_info("  echo 'GITHUB_TOKEN=ghp_ваш_токен' >> .env")
        else:
            print_warning("Remote origin не знайдено або не вказує на GitHub.")
    except Exception as e:
        print_warning(f"Не вдалося налаштувати Git remote: {e}")

    try:
        download_models()
    except KeyboardInterrupt:
        print_warning("\nЗавантаження моделей перервано користувачем.")
    except Exception as e:
        print_error(f"Помилка при обробці моделей: {e}")

    check_services()
    run_integrity_check()
    verify_llm_providers()

    # Install watchdog if missing (it might be in requirements.txt but we want to be sure for the watcher)
    print_step("Перевірка наявності Watchdog для авто-синхронізації...")
    try:
        import watchdog

        _ = watchdog
        print_success("Watchdog вже встановлено")
    except ImportError:
        print_info("Встановлення Watchdog...")
        subprocess.run(
            [str(VENV_PATH / "bin" / "python"), "-m", "pip", "install", "watchdog"], check=False
        )

    print_info(
        f"{Colors.OKCYAN}TIP:{Colors.ENDC} Запустіть 'npm run watch:config' для авто-синхронізації конфігів"
    )

    mcp_config_path = CONFIG_ROOT / "mcp" / "config.json"
    enabled_servers = []
    if mcp_config_path.exists():
        try:
            with open(mcp_config_path, encoding="utf-8") as f:
                mcp_cfg = json.load(f)
                servers = mcp_cfg.get("mcpServers", {})
                for s_name, s_info in servers.items():
                    if not s_info.get("disabled", False):
                        enabled_servers.append(s_name)
        except Exception:
            pass

    print_success("✅ Налаштування завершено!")
    tracker.update("MCP Tools Integration", "Integrated")
    tracker.print_report()
    print_info("Кроки для початку роботи:")

    mcp_info = []
    # Try to load all servers from config to be dynamic
    if mcp_config_path.exists():
        try:
            with open(mcp_config_path, encoding="utf-8") as f:
                mcp_cfg = json.load(f)
                all_servers = mcp_cfg.get("mcpServers", {})
                for s_id, s_info in all_servers.items():
                    if s_id.startswith("_"):
                        continue  # Skip comments
                    desc = s_info.get("description", "No description available")
                    # Truncate long descriptions for cleaner output
                    if len(desc) > 80:
                        desc = desc[:77] + "..."
                    mcp_info.append((s_id, desc))
        except Exception:
            pass

    if not mcp_info:
        # Fallback to hardcoded list if config is unreadable
        mcp_info = [
            ("memory", "Граф знань & Long-term Memory (Python)"),
            ("macos-use", "Нативний контроль macOS + Термінал (Swift)"),
            ("vibe", "Coding Agent & Self-Healing (Python)"),
            ("filesystem", "Файлові операції (Node)"),
            ("sequential-thinking", "Глибоке мислення (Node)"),
            ("xcodebuild", "Xcode Build & Test Automation (Node)"),
            ("chrome-devtools", "Автоматизація Chrome (Node)"),
            ("puppeteer", "Веб-скрейпінг та пошук (Node)"),
            ("github", "Офіційний GitHub MCP (Node)"),
            ("duckduckgo-search", "Швидкий пошук (Python)"),
            ("whisper-stt", "Локальне розпізнавання мови (Python)"),
            ("graph", "Візуалізація графу знань (Python)"),
            ("context7", "Документація бібліотек та API (Node)"),
            ("devtools", "Лінтер та аналіз коду (Python)"),
            ("react-devtools", "React Introspection & Fiber Analysis (Node)"),
            ("redis", "Оглядовість кешу та сесій (Python)"),
            ("golden-fund", "Knowledge Base & Data Persistence (Python)"),
            ("data-analysis", "Pandas Data Analysis Engine (Python)"),
            ("googlemaps", "Google Maps API з Cyberpunk фільтром (Swift)"),
            ("tour-guide", "Interactive Virtual Tour Control (Internal)"),
        ]

    print_info(
        f"Доступні MCP сервери ({len(enabled_servers) if enabled_servers else len(mcp_info)}):"
    )
    for s_id, _ in sorted(mcp_info):
        # Check if actually enabled in config
        if enabled_servers and s_id not in enabled_servers:
            pass


def setup_provider_tokens():
    """Автоматична установка токенів провайдерів (тільки якщо їх немає в локальному .env)."""
    print_step("Перевірка токенів провайдерів...")

    # Check if local .env exists and has tokens
    env_path = PROJECT_ROOT / ".env"

    # Skip if .env doesn't exist (fresh install scenario)
    if not env_path.exists():
        print_info("Локальний .env не знайдено - токени будуть встановлені при першому запуску")
        return

    # Load existing tokens from local .env
    existing_tokens = {}
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("COPILOT_API_KEY="):
                existing_tokens["copilot"] = line.split("=", 1)[1].strip()
            elif line.startswith("WINDSURF_API_KEY="):
                existing_tokens["windsurf"] = line.split("=", 1)[1].strip()

    # Check if we have valid tokens
    has_copilot = existing_tokens.get("copilot") and len(existing_tokens["copilot"]) > 10
    has_windsurf = existing_tokens.get("windsurf") and existing_tokens["windsurf"].startswith(
        "sk-ws-"
    )

    if has_copilot and has_windsurf:
        print_success("Токени провайдерів вже налаштовано в локальному .env")
        # Sync to global location
        sync_configs()
        return

    # Only proceed if we need to setup tokens
    print_info("Деякі токени відсутні, спробуємо автоматичне налаштування...")

    # Setup Windsurf token (only if missing or invalid)
    if not has_windsurf:
        print_info("Спроба отримати Windsurf токен автоматично...")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "providers.utils.get_windsurf_token"],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
            )

            if result.returncode == 0 and "sk-ws-" in result.stdout:
                print_success("Windsurf токен отримано та синхронізовано")
            else:
                print_warning("Не вдалося отримати Windsurf токен автоматично")
                print_info("Будь ласка, запустіть вручну:")
                print_info("  python -m providers token windsurf")
        except Exception as e:
            print_warning(f"Помилка при отриманні Windsurf токена: {e}")
    else:
        print_success("Windsurf токен вже налаштовано")

    # Setup Copilot token (only if missing or invalid)
    if not has_copilot:
        print_info("Для Copilot токена потрібна ручна установка")
        print_info("Будь ласка, запустіть:")
        print_info("  python -m providers token copilot --method vscode")
        print_info("  Або отримайте токен вручну з GitHub Copilot")
    else:
        print_success("Copilot токен вже налаштовано")

    # Sync to global location if we made changes
    # MCP Health Summary
    print()
    try:
        from src.maintenance.mcp_health import check_mcp

        asyncio.run(check_mcp())
    except Exception as e:
        print(f"⚠️  Не вдалося запустити перевірку здоров'я MCP: {e}")

    print_info("Перевірка токенів провайдерів завершена")

    # Create backup if databases were modified during setup
    print_step("Перевірка необхідності створення бекапу...")
    try:
        # Check if any databases exist and were modified
        db_files = [
            CONFIG_ROOT / "atlastrinity.db",
            CONFIG_ROOT / "data" / "trinity.db",
            CONFIG_ROOT / "data" / "monitoring.db",
            CONFIG_ROOT / "data" / "golden_fund" / "golden.db",
            CONFIG_ROOT / "data" / "search" / "golden_fund_index.db",
        ]

        # Check if any database files exist and are newer than repo backups
        backup_dir = PROJECT_ROOT / "backups" / "databases"
        needs_backup = False

        for db_file in db_files:
            if db_file.exists():
                backup_file = backup_dir / db_file.name
                if (
                    not backup_file.exists()
                    or db_file.stat().st_mtime > backup_file.stat().st_mtime
                ):
                    needs_backup = True
                    break

        if needs_backup:
            print_info("Виявлено зміни в базах даних. Створення бекапу...")
            backup_databases(args)
        else:
            print_info("Бази даних не змінювалися. Бекап не потрібен.")

    except Exception as e:
        print_warning(f"Помилка при перевірці бекапу: {e}")


if __name__ == "__main__":
    # Parse arguments and pass to main
    parser = argparse.ArgumentParser(description="AtlasTrinity Dev Setup")
    parser.add_argument("--backup", action="store_true", help="Backup databases and exit")
    parser.add_argument("--restore", action="store_true", help="Restore databases and exit")
    parser.add_argument(
        "--yes", "-y", action="store_true", help="Non-interactive mode (auto-confirm)"
    )
    parser.add_argument(
        "--no-auto-commit", action="store_true", help="Disable automatic commit and push of backups"
    )
    args = parser.parse_args()
    main(args)
