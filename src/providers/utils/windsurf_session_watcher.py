"""
Windsurf Session Watcher
========================

Background daemon thread that proactively monitors the Windsurf Language Server
session (port + CSRF token), detects changes, and updates environment variables.

This eliminates the "stale session" problem where LS restarts invalidate the
cached port/CSRF, causing request failures until the next reactive refresh.

Usage:
    from src.providers.utils.windsurf_session_watcher import WindsurfSessionWatcher

    watcher = WindsurfSessionWatcher.instance()
    watcher.start()

    # Get current session info (O(1), no subprocess calls)
    port, csrf, api_key = watcher.get_session()

    # Register callback for session changes
    watcher.on_session_change(lambda old, new: print(f"Session changed: {old} -> {new}"))

    # Stop when done
    watcher.stop()
"""

from __future__ import annotations

import atexit
import logging
import os
import re
import sqlite3
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("windsurf.session_watcher")

# ─── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_POLL_INTERVAL = 30  # seconds
LS_HEARTBEAT_ENDPOINT = "/exa.language_server_pb.LanguageServerService/Heartbeat"
STATE_DB_PATH = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Windsurf"
    / "User"
    / "globalStorage"
    / "state.vscdb"
)
ENV_FILE_PATH = Path("/Users/dev/.config/atlastrinity/.env")


# ─── Session Data ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WindsurfSession:
    """Immutable snapshot of a Windsurf LS session."""

    port: int
    csrf: str
    api_key: str
    install_id: str

    @property
    def is_valid(self) -> bool:
        return self.port > 0 and bool(self.csrf) and bool(self.api_key)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WindsurfSession):
            return False
        return self.port == other.port and self.csrf == other.csrf

    def __hash__(self) -> int:
        return hash((self.port, self.csrf))


# ─── Detection Functions ──────────────────────────────────────────────────────


def detect_ls_process() -> tuple[int, str]:
    """Detect running Windsurf language server port and CSRF token.

    Returns:
        (port, csrf_token) — port=0 if not detected.
    """
    try:
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            if "language_server_macos_arm" not in line or "grep" in line:
                continue

            # Extract CSRF token
            csrf_token = ""
            m = re.search(r"--csrf_token\s+(\S+)", line)
            if m:
                csrf_token = m.group(1)

            # Get PID
            parts = line.split()
            if len(parts) < 2:
                continue
            pid = parts[1]

            # Find port via lsof
            try:
                lsof = subprocess.run(
                    ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", pid],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                port = 0
                for ll in lsof.stdout.splitlines():
                    if "LISTEN" in ll:
                        m2 = re.search(r":(\d+)\s+\(LISTEN\)", ll)
                        if m2:
                            candidate = int(m2.group(1))
                            if port == 0 or candidate < port:
                                port = candidate
                if port and csrf_token:
                    return port, csrf_token
            except Exception:
                pass
            break
    except Exception:
        pass
    return 0, ""


def ls_heartbeat(port: int, csrf: str) -> bool:
    """Quick heartbeat check to verify LS is responding."""
    try:
        r = requests.post(
            f"http://127.0.0.1:{port}{LS_HEARTBEAT_ENDPOINT}",
            headers={
                "Content-Type": "application/json",
                "x-codeium-csrf-token": csrf,
            },
            json={},
            timeout=3,
        )
        return r.status_code == 200
    except Exception:
        return False


def read_api_key_from_db() -> tuple[str, str]:
    """Read API key and install ID from Windsurf state database.

    Returns:
        (api_key, install_id) — empty strings if not found.
    """
    if not STATE_DB_PATH.exists():
        return "", ""
    try:
        conn = sqlite3.connect(str(STATE_DB_PATH), timeout=3)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM ItemTable WHERE key = 'codeium.accountInfo'")
        result = cursor.fetchone()
        conn.close()

        if not result:
            return "", ""

        account_info = result[0]
        api_key_match = re.search(r'"apiKey":"(sk-ws-[^"]+)"', account_info)
        install_id_match = re.search(r'"installationId":"([^"]+)"', account_info)

        api_key = api_key_match.group(1) if api_key_match else ""
        install_id = install_id_match.group(1) if install_id_match else ""
        return api_key, install_id
    except Exception as e:
        logger.debug("Failed to read state.vscdb: %s", e)
        return "", ""


def sync_env_file(session: WindsurfSession) -> bool:
    """Update .env file with current session parameters.

    Returns True on success.
    """
    if not ENV_FILE_PATH.exists():
        return False

    try:
        content = ENV_FILE_PATH.read_text()
        lines = content.split("\n")
        updated = []
        keys_seen: set[str] = set()
        env_map = {
            "WINDSURF_API_KEY": session.api_key,
            "WINDSURF_INSTALL_ID": session.install_id,
            "WINDSURF_LS_PORT": str(session.port),
            "WINDSURF_LS_CSRF": session.csrf,
        }

        for line in lines:
            key = line.split("=", 1)[0].strip() if "=" in line else ""
            if key in env_map:
                updated.append(f"{key}={env_map[key]}")
                keys_seen.add(key)
            else:
                updated.append(line)

        # Add missing keys
        for key, val in env_map.items():
            if key not in keys_seen:
                updated.append(f"{key}={val}")

        ENV_FILE_PATH.write_text("\n".join(updated))
        return True
    except Exception as e:
        logger.warning("Failed to sync .env: %s", e)
        return False


# ─── Session Watcher ──────────────────────────────────────────────────────────


SessionChangeCallback = Callable[[WindsurfSession | None, WindsurfSession], Any]


class WindsurfSessionWatcher:
    """Background daemon that monitors the Windsurf LS session.

    Singleton — use WindsurfSessionWatcher.instance() to get the shared instance.
    """

    _singleton: WindsurfSessionWatcher | None = None
    _singleton_lock = threading.Lock()

    def __init__(self, poll_interval: int = DEFAULT_POLL_INTERVAL) -> None:
        self._lock = threading.Lock()
        self._session: WindsurfSession | None = None
        self._poll_interval = poll_interval
        self._running = False
        self._thread: threading.Thread | None = None
        self._callbacks: list[SessionChangeCallback] = []
        self._stop_event = threading.Event()

    @classmethod
    def instance(cls, poll_interval: int = DEFAULT_POLL_INTERVAL) -> WindsurfSessionWatcher:
        """Get or create the singleton watcher instance."""
        with cls._singleton_lock:
            if cls._singleton is None:
                cls._singleton = cls(poll_interval=poll_interval)
            return cls._singleton

    def start(self) -> None:
        """Start the background watcher thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_event.clear()

        # Do an initial detection synchronously
        self._detect_and_update()

        # Start background thread
        self._thread = threading.Thread(
            target=self._run_loop, name="windsurf-session-watcher", daemon=True
        )
        self._thread.start()
        atexit.register(self.stop)
        logger.info(
            "Session watcher started (interval=%ds, session=%s)",
            self._poll_interval,
            "valid" if self._session and self._session.is_valid else "none",
        )

    def stop(self) -> None:
        """Stop the background watcher thread."""
        with self._lock:
            if not self._running:
                return
            self._running = False

        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("Session watcher stopped")

    def get_session(self) -> tuple[int, str, str]:
        """Get current session (port, csrf, api_key). O(1), thread-safe."""
        with self._lock:
            if self._session and self._session.is_valid:
                return self._session.port, self._session.csrf, self._session.api_key
            return 0, "", ""

    def get_full_session(self) -> WindsurfSession | None:
        """Get full session object. Thread-safe."""
        with self._lock:
            return self._session

    def on_session_change(self, callback: SessionChangeCallback) -> None:
        """Register a callback for session changes.

        Callback signature: (old_session: WindsurfSession | None, new_session: WindsurfSession) -> Any
        """
        with self._lock:
            self._callbacks.append(callback)

    def force_refresh(self) -> WindsurfSession | None:
        """Force an immediate session re-detection.

        Returns the new session, or None if detection failed.
        """
        return self._detect_and_update()

    def _run_loop(self) -> None:
        """Background polling loop."""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._poll_interval)
            if self._stop_event.is_set():
                break
            try:
                self._detect_and_update()
            except Exception as e:
                logger.debug("Watcher poll error: %s", e)

    def _detect_and_update(self) -> WindsurfSession | None:
        """Detect current LS session and update if changed."""
        # Step 1: Check if current session is still alive
        with self._lock:
            current = self._session

        if current and current.is_valid and ls_heartbeat(current.port, current.csrf):
            return current

        # Step 2: Re-detect LS process
        port, csrf = detect_ls_process()
        if not port or not csrf:
            logger.debug("LS not detected")
            return None

        # Step 3: Verify with heartbeat
        if not ls_heartbeat(port, csrf):
            logger.debug("LS detected on port %d but heartbeat failed", port)
            return None

        # Step 4: Read API key (use env first, fall back to DB)
        api_key = os.getenv("WINDSURF_API_KEY", "")
        install_id = os.getenv("WINDSURF_INSTALL_ID", "")
        if not api_key:
            api_key, install_id = read_api_key_from_db()

        new_session = WindsurfSession(port=port, csrf=csrf, api_key=api_key, install_id=install_id)

        # Step 5: Check for changes
        with self._lock:
            old_session = self._session
            if new_session != old_session:
                self._session = new_session
                changed = True
            else:
                changed = False
            callbacks = list(self._callbacks) if changed else []

        if changed:
            logger.info(
                "Session changed: port=%d, csrf=%s...",
                new_session.port,
                new_session.csrf[:12] if new_session.csrf else "none",
            )
            # Update environment variables
            os.environ["WINDSURF_LS_PORT"] = str(new_session.port)
            os.environ["WINDSURF_LS_CSRF"] = new_session.csrf
            if new_session.api_key:
                os.environ["WINDSURF_API_KEY"] = new_session.api_key
            if new_session.install_id:
                os.environ["WINDSURF_INSTALL_ID"] = new_session.install_id

            # Sync to .env file
            sync_env_file(new_session)

            # Fire callbacks
            for cb in callbacks:
                try:
                    cb(old_session, new_session)
                except Exception as e:
                    logger.debug("Session change callback error: %s", e)

        return new_session
