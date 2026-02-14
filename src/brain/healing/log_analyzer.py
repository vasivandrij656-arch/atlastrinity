"""Background Log Analyzer for Self-Healing System.

Runs in a background thread, continuously watching brain.log and other system logs.
Extracts structured improvement notes: error patterns, slow operations, repeated
warnings, and resource bottlenecks. These notes feed the IMPROVE mode of the hypermodule.
"""

import json
import logging
import re
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.brain.healing.modes import HealingPriority, ImprovementNote

logger = logging.getLogger("brain.healing.log_analyzer")

# Pattern definitions for log analysis
ERROR_PATTERNS = [
    (re.compile(r"ERROR.*?(\w+Error): (.+)"), "error_pattern"),
    (re.compile(r"CRITICAL.*?(.+)"), "error_pattern"),
    (re.compile(r"Exception.*?(\w+): (.+)"), "error_pattern"),
]

SLOW_PATTERNS = [
    (re.compile(r"timeout|timed?\s*out", re.IGNORECASE), "slow_operation"),
    (re.compile(r"took (\d+(?:\.\d+)?)\s*s(?:econds)?", re.IGNORECASE), "slow_operation"),
]

WARNING_PATTERNS = [
    (re.compile(r"WARNING.*?(.+)"), "repeated_warning"),
    (re.compile(r"WARN.*?(.+)"), "repeated_warning"),
]

RESOURCE_PATTERNS = [
    (re.compile(r"memory.*?(\d+)%", re.IGNORECASE), "resource_bottleneck"),
    (re.compile(r"disk.*?full|no space left", re.IGNORECASE), "resource_bottleneck"),
    (re.compile(r"connection.*?refused|reset|broken", re.IGNORECASE), "resource_bottleneck"),
    (re.compile(r"too many open files", re.IGNORECASE), "resource_bottleneck"),
]

# File path extraction pattern
FILE_PATH_PATTERN = re.compile(r'(?:File "([^"]+)", line (\d+))|(\b\w+/[\w/]+\.py\b)')


class LogAnalyzer:
    """Watches logs in a background thread, extracts improvement notes.

    Notes are persisted to ~/.config/atlastrinity/memory/improvement_notes.json
    and consumed by the ImprovementEngine.
    """

    def __init__(
        self,
        logs_dir: Path | None = None,
        notes_path: Path | None = None,
        check_interval: int = 60,
    ):
        self.logs_dir = logs_dir or Path.home() / ".config" / "atlastrinity" / "logs"
        self.notes_path = (
            notes_path
            or Path.home() / ".config" / "atlastrinity" / "memory" / "improvement_notes.json"
        )
        self.check_interval = check_interval

        self._running = False
        self._thread: threading.Thread | None = None
        self._last_position: dict[str, int] = {}  # file -> last read position
        self._notes: list[ImprovementNote] = []
        self._note_index: dict[str, ImprovementNote] = {}  # description hash -> note
        self._error_counter: Counter = Counter()
        self._lock = threading.Lock()

        # Load persisted notes
        self._load_notes()

    def start(self) -> None:
        """Start background log analysis thread."""
        if self._running:
            logger.warning("[LogAnalyzer] Already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="LogAnalyzer")
        self._thread.start()
        logger.info("[LogAnalyzer] Background log analysis started")

    def stop(self) -> None:
        """Gracefully stop analyzer."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._save_notes()
        logger.info("[LogAnalyzer] Background log analysis stopped")

    def analyze_chunk(self, lines: list[str]) -> list[ImprovementNote]:
        """Analyze a chunk of log lines, extract patterns/errors/bottlenecks.

        Returns:
            List of new or updated ImprovementNote objects.
        """
        new_notes: list[ImprovementNote] = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Extract file path if present
            source_file, source_line = self._extract_file_info(line)

            # Check all pattern categories
            for patterns, category in [
                (ERROR_PATTERNS, "error_pattern"),
                (SLOW_PATTERNS, "slow_operation"),
                (WARNING_PATTERNS, "repeated_warning"),
                (RESOURCE_PATTERNS, "resource_bottleneck"),
            ]:
                for pattern, _ in patterns:
                    match = pattern.search(line)
                    if match:
                        description = self._clean_description(match.group(0), category)
                        note = self._upsert_note(
                            category=category,
                            description=description,
                            source_file=source_file,
                            source_line=source_line,
                        )
                        if note:
                            new_notes.append(note)
                        break  # Only one match per pattern category per line

        return new_notes

    def get_pending_notes(self) -> list[ImprovementNote]:
        """Get notes not yet addressed, sorted by priority and occurrences."""
        with self._lock:
            pending = [n for n in self._notes if not n.addressed]
            return sorted(
                pending,
                key=lambda n: (n.severity.value, -n.occurrences),
            )

    def get_all_notes(self) -> list[ImprovementNote]:
        """Get all notes."""
        with self._lock:
            return list(self._notes)

    def mark_addressed(self, note_id: str, fix_applied: str) -> bool:
        """Mark a note as addressed."""
        with self._lock:
            for note in self._notes:
                if note.id == note_id:
                    note.addressed = True
                    note.fix_applied = fix_applied
                    self._save_notes()
                    return True
        return False

    def get_stats(self) -> dict[str, Any]:
        """Get analysis statistics."""
        with self._lock:
            total = len(self._notes)
            pending = sum(1 for n in self._notes if not n.addressed)
            by_category = defaultdict(int)
            for n in self._notes:
                by_category[n.category] += 1
            return {
                "total_notes": total,
                "pending": pending,
                "addressed": total - pending,
                "by_category": dict(by_category),
                "running": self._running,
            }

    # --- Private methods ---

    def _run_loop(self) -> None:
        """Main background loop."""
        while self._running:
            try:
                self._scan_logs()
            except Exception as e:
                logger.error(f"[LogAnalyzer] Scan error: {e}")

            # Sleep in small intervals to allow quick shutdown
            for _ in range(self.check_interval):
                if not self._running:
                    break
                time.sleep(1)

    def _scan_logs(self) -> None:
        """Scan all log files for new lines."""
        if not self.logs_dir.exists():
            return

        log_files = [
            self.logs_dir / "brain.log",
            self.logs_dir / "vibe_server.log",
            self.logs_dir / "orchestrator.log",
            self.logs_dir / "ci_failure.log",
        ]

        for log_file in log_files:
            if not log_file.exists():
                continue

            file_key = str(log_file)
            last_pos = self._last_position.get(file_key, 0)
            current_size = log_file.stat().st_size

            # Handle log rotation (file got smaller)
            if current_size < last_pos:
                last_pos = 0

            if current_size == last_pos:
                continue

            try:
                with open(log_file, encoding="utf-8", errors="replace") as f:
                    f.seek(last_pos)
                    new_lines = f.readlines()
                    new_pos = f.tell()

                if new_lines:
                    self.analyze_chunk(new_lines)

                self._last_position[file_key] = new_pos
            except Exception as e:
                logger.debug(f"[LogAnalyzer] Error reading {log_file}: {e}")

        # Save notes periodically
        self._save_notes()

    def _upsert_note(
        self,
        category: str,
        description: str,
        source_file: str | None,
        source_line: int | None,
    ) -> ImprovementNote | None:
        """Insert or update a note. Returns the note if new, None if updated."""
        # Create a hash key for deduplication
        key = f"{category}:{description[:100]}"

        with self._lock:
            if key in self._note_index:
                existing = self._note_index[key]
                existing.occurrences += 1
                existing.last_seen = datetime.now()
                # Escalate priority if recurring
                if (
                    existing.occurrences >= 10
                    and existing.severity.value > HealingPriority.HIGH.value
                ):
                    existing.severity = HealingPriority.HIGH
                elif (
                    existing.occurrences >= 50
                    and existing.severity.value > HealingPriority.CRITICAL.value
                ):
                    existing.severity = HealingPriority.CRITICAL
                return None  # Updated, not new

            note = ImprovementNote(
                id=f"note_{uuid4().hex[:8]}",
                category=category,
                description=description,
                source_file=source_file,
                source_line=source_line,
                severity=self._infer_severity(category),
            )
            self._notes.append(note)
            self._note_index[key] = note
            return note

    def _infer_severity(self, category: str) -> HealingPriority:
        """Infer initial severity from category."""
        severity_map = {
            "error_pattern": HealingPriority.HIGH,
            "slow_operation": HealingPriority.MEDIUM,
            "repeated_warning": HealingPriority.LOW,
            "resource_bottleneck": HealingPriority.HIGH,
        }
        return severity_map.get(category, HealingPriority.MEDIUM)

    def _clean_description(self, raw: str, category: str) -> str:
        """Clean and truncate description."""
        # Remove timestamps and log-level prefixes
        cleaned = re.sub(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[,.]?\d*\s*", "", raw)
        cleaned = re.sub(r"^(ERROR|WARNING|WARN|CRITICAL|INFO)\s*[-:]\s*", "", cleaned)
        return cleaned[:200].strip()

    def _extract_file_info(self, line: str) -> tuple[str | None, int | None]:
        """Extract source file and line number from log line."""
        match = FILE_PATH_PATTERN.search(line)
        if match:
            if match.group(1):  # File "path", line N
                return match.group(1), int(match.group(2))
            if match.group(3):  # bare path/to/file.py
                return match.group(3), None
        return None, None

    def _load_notes(self) -> None:
        """Load persisted notes from disk."""
        try:
            if self.notes_path.exists():
                with open(self.notes_path, encoding="utf-8") as f:
                    data = json.load(f)
                self._notes = [ImprovementNote.from_dict(d) for d in data]
                self._note_index = {f"{n.category}:{n.description[:100]}": n for n in self._notes}
                logger.info(f"[LogAnalyzer] Loaded {len(self._notes)} notes from disk")
        except Exception as e:
            logger.debug(f"[LogAnalyzer] Could not load notes: {e}")

    def _save_notes(self) -> None:
        """Persist notes to disk."""
        try:
            self.notes_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                data = [n.to_dict() for n in self._notes]
            with open(self.notes_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"[LogAnalyzer] Could not save notes: {e}")


# Singleton
log_analyzer = LogAnalyzer()
