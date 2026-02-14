"""
Secure Backup Utilities for AtlasTrinity
Provides encryption and secret filtering for backup operations
"""

import hashlib
import json
import os
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Any

try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None  # Lazy: will be imported after pip install if needed


class SecureBackupManager:
    """Manages secure backups with encryption and secret filtering"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.backup_dir = project_root / "backups" / "databases"
        self.config_root = Path.home() / ".config" / "atlastrinity"

        # Secret patterns to filter/remove
        self.secret_patterns = [
            r"AIza[a-zA-Z0-9_-]{30,40}",  # Google Maps API keys (typically 39, but can vary)
            r"ghp_[a-zA-Z0-9_]{20,40}",  # GitHub personal access tokens
            r"ghu_[a-zA-Z0-9]{36}",  # GitHub user tokens
            r"gho_[a-zA-Z0-9]{36}",  # GitHub OAuth tokens
            r"ghr_[a-zA-Z0-9]{36}",  # GitHub refresh tokens
            r"sHmSGqHcHcnrIyhsPBGRy5OOqo484EAN",  # Mistral API key example
            r"[a-f0-9]{32,64}",  # Generic API keys (hex)
            r"Bearer\s+[a-zA-Z0-9_-]+",  # Bearer tokens
            r"sk-[a-zA-Z0-9]{24,}",  # Stripe keys
            r"xoxb-[0-9]{10,}-[0-9]{10,}-[a-zA-Z0-9]{24,}",  # Slack bot tokens
        ]

        # Files to completely exclude from backups
        self.exclude_files = {
            ".env",
            ".env.local",
            ".env.production",
            "config.yaml",
            "behavior_config.yaml",
            "mcp_servers.json",
            "vibe_config.toml",
        }

    def generate_key(self) -> bytes:
        """Generate encryption key for backup"""
        if Fernet is None:
            raise ImportError("cryptography package is required for secure backup")
        return Fernet.generate_key()

    def get_backup_key(self) -> bytes:
        """Get or create backup encryption key"""
        key_file = self.config_root / ".backup_key"

        if key_file.exists():
            with open(key_file, "rb") as f:
                return f.read()
        else:
            key = self.generate_key()
            key_file.parent.mkdir(parents=True, exist_ok=True)
            with open(key_file, "wb") as f:
                f.write(key)
            # Set restrictive permissions
            os.chmod(key_file, 0o600)
            return key

    def encrypt_file(self, input_path: Path, output_path: Path, key: bytes) -> bool:
        """Encrypt a file with Fernet encryption"""
        if Fernet is None:
            raise ImportError("cryptography package is required for encryption")
        try:
            fernet = Fernet(key)

            with open(input_path, "rb") as f:
                data = f.read()

            encrypted_data = fernet.encrypt(data)

            with open(output_path, "wb") as f:
                f.write(encrypted_data)

            return True
        except Exception:
            return False

    def decrypt_file(self, input_path: Path, output_path: Path, key: bytes) -> bool:
        """Decrypt a file with Fernet encryption"""
        if Fernet is None:
            raise ImportError("cryptography package is required for decryption")
        try:
            fernet = Fernet(key)

            with open(input_path, "rb") as f:
                encrypted_data = f.read()

            decrypted_data = fernet.decrypt(encrypted_data)

            with open(output_path, "wb") as f:
                f.write(decrypted_data)

            return True
        except Exception:
            return False

    def filter_sqlite_secrets(self, db_path: Path, output_path: Path) -> bool:
        """Create a cleaned SQLite database with secrets removed/replaced"""
        try:
            # Connect to source database
            source_conn = sqlite3.connect(str(db_path))

            # Create new clean database
            clean_conn = sqlite3.connect(str(output_path))

            # Get all table names (exclude system tables)
            cursor = source_conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
            )
            tables = [row[0] for row in cursor.fetchall()]

            for table in tables:
                # SKIP shadow tables or already created tables
                # FTS5 shadow tables: *_data, *_idx, *_content, *_docsize, *_config
                # SQLite virtual tables create these automatically
                cursor_check = clean_conn.cursor()
                cursor_check.execute(
                    f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}';"
                )
                if cursor_check.fetchone():
                    # Table already created (likely a shadow table from a virtual table definition)
                    continue

                # Get table schema
                cursor.execute(
                    f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}';"
                )
                schema = cursor.fetchone()[0]

                # Create table in clean database
                clean_conn.execute(schema)

                # Get table data
                cursor.execute(f"SELECT * FROM {table};")
                columns = [description[0] for description in cursor.description]
                rows = cursor.fetchall()

                # Clean each row
                clean_rows = []
                for row in rows:
                    clean_row = []
                    for value in row:
                        if isinstance(value, str):
                            # Apply secret filtering
                            cleaned_value = self._filter_secrets_from_text(value)
                            clean_row.append(cleaned_value)
                        else:
                            clean_row.append(value)
                    clean_rows.append(tuple(clean_row))

                # Insert cleaned data
                if clean_rows:
                    placeholders = ",".join(["?" for _ in columns])
                    clean_conn.executemany(
                        f"INSERT INTO {table} VALUES ({placeholders})", clean_rows
                    )

            # Commit and close
            clean_conn.commit()
            source_conn.close()
            clean_conn.close()

            return True

        except Exception:
            return False

    def _filter_secrets_from_text(self, text: str) -> str:
        """Remove or replace secrets from text"""
        if not text:
            return text

        cleaned = text

        # Apply all secret patterns
        for pattern in self.secret_patterns:
            # Replace with placeholder
            cleaned = re.sub(pattern, "[REDACTED_SECRET]", cleaned, flags=re.IGNORECASE)

        return cleaned

    def should_exclude_file(self, file_path: Path) -> bool:
        """Check if file should be completely excluded from backup"""
        return file_path.name in self.exclude_files

    def create_secure_backup(self) -> bool:
        """Create secure backup with encryption and secret filtering"""

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        key = self.get_backup_key()

        # Define backup mappings with security options
        backup_mappings: list[dict[str, Any]] = [
            {
                "source": self.config_root / "atlastrinity.db",
                "dest": self.backup_dir / "atlastrinity.db.encrypted",
                "encrypt": True,
                "filter_sqlite": True,
            },
            {
                "source": self.config_root / "data" / "monitoring.db",
                "dest": self.backup_dir / "monitoring.db.encrypted",
                "encrypt": True,
                "filter_sqlite": True,
            },
            {
                "source": self.config_root / "data" / "trinity.db",
                "dest": self.backup_dir / "trinity.db.encrypted",
                "encrypt": True,
                "filter_sqlite": True,
            },
            {
                "source": self.config_root / "data" / "golden_fund" / "golden.db",
                "dest": self.backup_dir / "golden_fund.db.encrypted",
                "encrypt": True,
                "filter_sqlite": True,
            },
            {
                "source": self.config_root / "data" / "search" / "golden_fund_index.db",
                "dest": self.backup_dir / "golden_fund_index.db.encrypted",
                "encrypt": True,
                "filter_sqlite": True,
            },
            {
                "source": self.config_root / "data" / "golden_fund" / "chroma_db",
                "dest": self.backup_dir / "golden_fund" / "chroma_db",
                "encrypt": False,
                "filter_sqlite": False,  # Directory
            },
            {
                "source": self.config_root / "data" / "golden_fund" / "blobs",
                "dest": self.backup_dir / "golden_fund" / "blobs",
                "encrypt": False,
                "filter_sqlite": False,  # Directory (JSON blob files)
            },
            {
                "source": self.config_root / "data" / "golden_fund" / "raw",
                "dest": self.backup_dir / "golden_fund" / "raw",
                "encrypt": False,
                "filter_sqlite": False,  # Directory (raw ingested files)
            },
            {
                "source": self.config_root / "memory" / "chroma",
                "dest": self.backup_dir / "memory" / "chroma",
                "encrypt": False,
                "filter_sqlite": False,  # Directory
            },
        ]

        success_count = 0

        for mapping in backup_mappings:
            source = mapping["source"]
            dest = mapping["dest"]

            if not source.exists():
                # Chroma directories may not exist on fresh installs - this is normal
                if "chroma" in source.name:
                    pass
                else:
                    pass
                continue

            try:
                dest.parent.mkdir(parents=True, exist_ok=True)

                if source.is_file():
                    if mapping.get("filter_sqlite", False):
                        # Create filtered SQLite first
                        temp_filtered = dest.parent / f"{source.name}.filtered"
                        if self.filter_sqlite_secrets(source, temp_filtered):
                            if mapping.get("encrypt", False):
                                if self.encrypt_file(temp_filtered, dest, key):
                                    success_count += 1
                                else:
                                    pass
                            else:
                                shutil.move(temp_filtered, dest)
                                success_count += 1
                            # Clean up temp file
                            temp_filtered.unlink(missing_ok=True)
                        else:
                            pass
                    elif mapping.get("encrypt", False):
                        if self.encrypt_file(source, dest, key):
                            success_count += 1
                        else:
                            pass
                    else:
                        shutil.copy2(source, dest)
                        success_count += 1

                elif source.is_dir():
                    # For directories, copy contents (no encryption for folders)
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(source, dest)
                    success_count += 1

            except Exception:
                pass

        # Save backup metadata
        metadata = {
            "timestamp": str(Path().resolve().stat().st_mtime),
            "encrypted_files": [m["dest"].name for m in backup_mappings if m.get("encrypt")],
            "key_hash": hashlib.sha256(key).hexdigest(),
            "total_files": success_count,
        }

        metadata_path = self.backup_dir / "backup_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        return True

    def restore_secure_backup(self) -> bool:
        """Restore from secure backup with decryption"""

        key = self.get_backup_key()
        metadata_path = self.backup_dir / "backup_metadata.json"

        if not metadata_path.exists():
            return False

        # Load metadata (for future use)
        with open(metadata_path) as f:
            json.load(f)  # Metadata loaded but not currently used

        # Restore mappings (reverse of backup)
        restore_mappings: list[dict[str, Any]] = [
            {
                "source": self.backup_dir / "atlastrinity.db.encrypted",
                "dest": self.config_root / "atlastrinity.db",
                "encrypted": True,
            },
            {
                "source": self.backup_dir / "monitoring.db.encrypted",
                "dest": self.config_root / "data" / "monitoring.db",
                "encrypted": True,
            },
            {
                "source": self.backup_dir / "trinity.db.encrypted",
                "dest": self.config_root / "data" / "trinity.db",
                "encrypted": True,
            },
            {
                "source": self.backup_dir / "golden_fund.db.encrypted",
                "dest": self.config_root / "data" / "golden_fund" / "golden.db",
                "encrypted": True,
            },
            {
                "source": self.backup_dir / "golden_fund_index.db.encrypted",
                "dest": self.config_root / "data" / "search" / "golden_fund_index.db",
                "encrypted": True,
            },
            {
                "source": self.backup_dir / "golden_fund" / "chroma_db",
                "dest": self.config_root / "data" / "golden_fund" / "chroma_db",
                "encrypted": False,
            },
            {
                "source": self.backup_dir / "golden_fund" / "blobs",
                "dest": self.config_root / "data" / "golden_fund" / "blobs",
                "encrypted": False,
            },
            {
                "source": self.backup_dir / "golden_fund" / "raw",
                "dest": self.config_root / "data" / "golden_fund" / "raw",
                "encrypted": False,
            },
            {
                "source": self.backup_dir / "memory" / "chroma",
                "dest": self.config_root / "memory" / "chroma",
                "encrypted": False,
            },
        ]

        success_count = 0

        for mapping in restore_mappings:
            source = mapping["source"]
            dest = mapping["dest"]

            if not source.exists():
                # Chroma directories may not have been backed up - this is normal
                if "chroma" in source.name:
                    pass
                else:
                    pass
                continue

            try:
                dest.parent.mkdir(parents=True, exist_ok=True)

                if source.is_file():
                    if mapping.get("encrypted", False):
                        temp_decrypted = dest.parent / f"{source.name}.temp"
                        if self.decrypt_file(source, temp_decrypted, key):
                            shutil.move(temp_decrypted, dest)
                            success_count += 1
                        else:
                            pass
                        temp_decrypted.unlink(missing_ok=True)
                    else:
                        shutil.copy2(source, dest)
                        success_count += 1

                elif source.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(source, dest)
                    success_count += 1

            except Exception:
                pass

        return True


if __name__ == "__main__":
    import sys

    manager = SecureBackupManager(Path(__file__).resolve().parent.parent.parent)
    if "--restore" in sys.argv:
        manager.restore_secure_backup()
    else:
        manager.create_secure_backup()
