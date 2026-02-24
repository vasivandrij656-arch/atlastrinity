"""AtlasTrinity TTS - Ukrainian Text-to-Speech

Uses robinhad/ukrainian-tts for agent voices:
- Atlas: Dmytro (male)
- Tetyana: Tetiana (female)
- Grisha: Mykyta (male)

NOTE: TTS models must be set up before first use via setup_dev.py
"""

import asyncio
import os
import re
import sys
import tempfile
import warnings

# Suppress PyTorch and ESPnet warnings triggered by ukrainian-tts
warnings.filterwarnings("ignore", message=".*torch.nn.utils.weight_norm is deprecated.*")
warnings.filterwarnings(
    "ignore", message=".*make_pad_mask with a list of lengths is not tracable.*"
)
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from src.brain.config import MODELS_DIR
from src.brain.config.config_loader import config
from src.brain.monitoring.logger import logger

# Lazy imports for optional dependencies
try:
    from ukrainian_tts.tts import TTS as UkrainianTTS  # type: ignore[reportAttributeAccessIssue]
    from ukrainian_tts.tts import Voices
except ImportError:
    UkrainianTTS = None  # type: ignore[reportAssignmentType]
    Voices = None  # type: ignore[reportAssignmentType]

# Lazy import to avoid loading heavy dependencies at startup
TTS_AVAILABLE = None
TTS = None


def _check_tts_available():
    global TTS_AVAILABLE
    if TTS_AVAILABLE is not None:
        return TTS_AVAILABLE

    try:
        import importlib.util

        if importlib.util.find_spec("ukrainian_tts") is not None:
            TTS_AVAILABLE = True
            print("[TTS] Ukrainian TTS available", file=sys.stderr)
        else:
            TTS_AVAILABLE = False
            print(
                "[TTS] Warning: ukrainian-tts not installed. Run: pip install git+https://github.com/robinhad/ukrainian-tts.git",
            )
    except Exception:
        TTS_AVAILABLE = False
        print(
            "[TTS] Warning: ukrainian-tts not installed. Run: pip install git+https://github.com/robinhad/ukrainian-tts.git",
        )
    return TTS_AVAILABLE


def _patch_tts_config(cache_dir: Path):
    """Ensures config.yaml in cache_dir uses absolute paths for stats_file.
    This fixes FileNotFoundError in espnet2 on some systems.
    """
    config_path = cache_dir / "config.yaml"
    if not config_path.exists():
        return

    try:
        content = config_path.read_text()

        # Regex to find 'stats_file: some_file.npz' anywhere in the file
        # We look for 'stats_file:' followed by a filename, potentially with whitespace
        pattern = r"(\s*stats_file:\s*)([^\s\n]+)"

        abs_stats_path = str(cache_dir / "feats_stats.npz")

        def replace_path(match):
            prefix = match.group(1)
            current_val = match.group(2)
            if current_val != abs_stats_path:
                print(
                    f"[TTS] Updating stats_file from '{current_val}' to '{abs_stats_path}'",
                    file=sys.stderr,
                )
                return f"{prefix}{abs_stats_path}"
            return match.group(0)

        new_content, count = re.subn(pattern, replace_path, content)

        if count > 0 and new_content != content:
            config_path.write_text(new_content)
            print(
                f"[TTS] Patched {config_path.name}: {count} occurrences updated.", file=sys.stderr
            )
        else:
            print(
                f"[TTS] {config_path.name} is already up to date or no stats_file found.",
                file=sys.stderr,
            )

    except Exception as e:
        print(f"[TTS] Warning: Failed to patch config.yaml: {e}", file=sys.stderr)


def sanitize_text_for_tts(text: str) -> str:
    """Cleans text for better TTS pronunciation.
    Removes/replaces characters and expands abbreviations.
    """

    # 1. Remove markdown links [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    # 2. Remove URLs (unpronounceable)
    text = re.sub(r"http[s]?://\S+", "", text)

    # 3. Remove code blocks and inline code
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)

    # 4. Expand Ukrainian abbreviations and units
    abbreviations = {
        # Temperature
        r"°C": " градусів Цельсія",
        r"°": " градусів",
        r"℃": " градусів Цельсія",
        # Distance
        r"\bкм\b": " кілометрів",
        r"\bм\b(?!\/)": " метрів",  # Not before /
        r"\bсм\b": " сантиметрів",
        r"\bмм\b": " міліметрів",
        # Time
        r"\bсек\b": " секунд",
        r"\bс\b(?=\s|\.|,|$)": " секунд",
        r"\bхв\b": " хвилин",
        r"\bгод\b": " годин",
        # Speed
        r"\bм/с\b": " метрів на секунду",
        r"\bкм/год\b": " кілометрів на годину",
        # Weight
        r"\bкг\b": " кілограмів",
        r"\bг\b(?=\s|\.|,|$)": " грамів",
        r"\bт\b(?=\s|\.|,|$)": " тонн",
        # Percent and numbers
        r"%": " відсотків",
        r"\bнр\b": " наприклад",
        r"\bтощо\b": " і так далі",
    }

    for pattern, replacement in abbreviations.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # 5. Replace special punctuation
    replacements = {
        "—": ",",
        "–": ",",
        "…": "",
        '"': "",
        "'": "",
        "«": "",
        "»": "",
        "/": " ",
        "@": " at ",
        "#": " номер ",
        "&": " і ",
        "*": "",
        "_": "",
        "|": ",",
        "<": "",
        ">": "",
        "{": "",
        "}": "",
        "[": "",
        "]": "",
        "(": ",",
        ")": ",",
        "+": " плюс ",
        "=": " дорівнює ",
    }

    for char, replacement in replacements.items():
        text = text.replace(char, replacement)

    # 6. Clean up spacing and punctuation
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"([,.!?])\1+", r"\1", text)
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    text = re.sub(r"([,.!?])([^\s])", r"\1 \2", text)

    # 7. Final Polish: Transliterate common English technical words if any remained
    common_trans = {
        r"\bjson\b": "джейсон",
        r"\bpython\b": "пайтон",
        r"\bcmd\b": "команда",
        r"\btop\b": "топ",
        r"\bapi\b": "апі",
        r"\bui\b": "інтерфейс",
        r"\bux\b": "користувацький досвід",
        r"\bgit\b": "гіт",
        r"\bpr\b": "піар",
        r"\brev\b": "ревю",
        r"\bvibe\b": "вайб",
        r"\batlas\b": "атлас",
        r"\btrinity\b": "трініті",
        r"\bgrisha\b": "гріша",
        r"\btetyana\b": "тетяна",
    }
    for pattern, replacement in common_trans.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text.strip()


@dataclass
class VoiceConfig:
    """Voice configuration for an agent"""

    name: str
    voice_id: str
    description: str


# Agent voice mappings
AGENT_VOICES = {
    "atlas": VoiceConfig(
        name="Atlas",
        voice_id="Dmytro",
        description="Male voice for Meta-Planner",
    ),
    "tetyana": VoiceConfig(
        name="Tetyana",
        voice_id="Tetiana",
        description="Female voice for Executor",
    ),
    "grisha": VoiceConfig(name="Grisha", voice_id="Mykyta", description="Male voice for Visor"),
}


class AgentVoice:
    """TTS wrapper for agent voices

    Usage:
        voice = AgentVoice("atlas")
        voice.speak("Hello, I am Atlas")
    """

    def __init__(self, agent_name: str, device: str | None = None):
        """Initialize voice for an agent

        Args:
            agent_name: One of 'atlas', 'tetyana', 'grisha'
            device: 'cpu', 'cuda', or 'mps' (Apple Silicon). If None, reads from config.yaml

        """
        self.agent_name = agent_name.lower()

        # Get device from config.yaml with fallback
        voice_config = config.get("voice.tts", {})
        self.device = device or voice_config.get("device", "mps")

        if self.agent_name not in AGENT_VOICES:
            raise ValueError(
                f"Unknown agent: {agent_name}. Must be one of: {list(AGENT_VOICES.keys())}",
            )

        self.config = AGENT_VOICES[self.agent_name]
        self._tts = None
        self._voice_enum = None  # Cache enum

        # Get voice enum
        if _check_tts_available():
            # Lazy import Voices as well
            try:
                from ukrainian_tts.tts import Voices

                self._voice_enum = getattr(Voices, self.config.voice_id, Voices.Dmytro)
                if self._voice_enum:
                    self._voice = self._voice_enum.value
                else:
                    self._voice = "Dmytro"
            except Exception as e:
                print(f"[TTS] Failed to import Voices: {e}", file=sys.stderr)
                # Set default voice
                self._voice = "Dmytro"
        else:
            self._voice = None

    @property
    def tts(self):
        """Lazy initialize TTS engine"""
        if self._tts is None and _check_tts_available():
            # Import only here to avoid issues during startup
            try:
                from ukrainian_tts.tts import TTS as UkrainianTTS

                global TTS
                TTS = UkrainianTTS
            except Exception as e:
                print(f"[TTS] Failed to import Ukrainian TTS: {e}", file=sys.stderr)
                return None

            # Models should already be in MODELS_DIR from setup_dev.py
            if not MODELS_DIR.exists():
                print(f"[TTS] ⚠️  Models directory not found: {MODELS_DIR}", file=sys.stderr)
                print("[TTS] Run setup_dev.py first to download TTS models", file=sys.stderr)
                return None

            required_files = ["model.pth", "feats_stats.npz", "spk_xvector.ark"]
            missing = [f for f in required_files if not (MODELS_DIR / f).exists()]

            if missing:
                print(f"[TTS] ⚠️  Missing TTS model files: {missing}", file=sys.stderr)
                print("[TTS] Run setup_dev.py to download them", file=sys.stderr)
                return None

            try:
                print("[TTS] Initializing engine on " + str(self.device) + "...", file=sys.stderr)
                print(
                    "downloading https://github.com/robinhad/ukrainian-tts/releases/download/v6.0.0",
                    file=sys.stderr,
                )
                _patch_tts_config(MODELS_DIR)
                self._tts = TTS(cache_folder=str(MODELS_DIR))
                print("downloaded.", file=sys.stderr)
                print(f"[TTS] ✅ {self.config.name} voice ready on {self.device}", file=sys.stderr)
            except Exception as e:
                print(f"[TTS] Error: {e}", file=sys.stderr)
                import traceback

                traceback.print_exc()
                return None
        return self._tts

    def speak(self, text: str, output_file: str | None = None) -> str | None:
        """Generate speech from text."""
        if not _check_tts_available() or not text:
            if not _check_tts_available() and text:
                print(f"[TTS] [{self.config.name}]: {text}", file=sys.stderr)
            return None

        # Clean text for better pronunciation
        text = sanitize_text_for_tts(text)
        if not text:
            return None

        # Determine output path
        output_file = output_file or self._get_default_output_path(text)

        try:
            success = self._perform_tts_generation(text, output_file)
            if success:
                print(f"[TTS] [{self.config.name}]: {text}", file=sys.stderr)
                return output_file
            return None
        except Exception as e:
            print(f"[TTS] Error generating speech: {e}", file=sys.stderr)
            return None

    def _get_default_output_path(self, text: str) -> str:
        """Generate a default temporary path for TTS output."""
        return os.path.join(
            tempfile.gettempdir(),
            f"tts_{self.agent_name}_{hash(text) % 10000}.wav",
        )

    def _perform_tts_generation(self, text: str, output_file: str) -> bool:
        """Execute the core TTS generation logic."""
        from ukrainian_tts.tts import Stress  # type: ignore[import-not-found]

        if not self.tts:
            return False

        with open(output_file, mode="wb") as f:
            self.tts.tts(
                text,
                cast("Any", self._voice),
                Stress.Dictionary.value,
                cast("Any", f),
            )
        return True

    def speak_and_play(self, text: str) -> bool:
        """Generate speech and play it immediately (macOS)

        Args:
            text: Ukrainian text to speak

        Returns:
            True if successfully played, False otherwise

        """
        audio_file = self.speak(text)

        if audio_file and os.path.exists(audio_file):
            return self._play_audio(audio_file)

        return False

    def _play_audio(self, file_path: str) -> bool:
        """Play audio file on macOS"""
        try:
            import subprocess

            subprocess.run(["afplay", file_path], check=True, capture_output=True)
            return True
        except Exception as e:
            print(f"[TTS] Error playing audio: {e}", file=sys.stderr)
            return False


class VoiceManager:
    """Centralized TTS manager for all agents"""

    def __init__(self, device: str = "cpu"):
        from collections import deque

        voice_config = config.get("voice.tts", {})
        self.enabled = voice_config.get("enabled", True)
        self.device = device
        self._tts = None
        self.is_speaking = False
        self.last_text = ""
        self.history: deque[str] = deque(maxlen=5)  # History of last spoken phrases
        self.last_speak_time = 0.0

        # Suppress tracer warnings specifically during voice operations
        import warnings

        warnings.filterwarnings("ignore", message=".*make_pad_mask.*")
        warnings.filterwarnings("ignore", message=".*torch.nn.utils.weight_norm.*")

        # Concurrency control

        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()

        self._current_process: asyncio.subprocess.Process | None = None  # Track current subprocess
        self._translator_llm = None  # Lazy loaded

    async def get_engine(self):
        if not self.enabled:
            print("[TTS] TTS is disabled in config", file=sys.stderr)
            return None
        await self._initialize_if_needed_async()
        return self._tts

    @property
    def engine(self):
        if not self.enabled:
            return None
        self._initialize_if_needed()
        return self._tts

    def _initialize_if_needed(self):
        if self._tts is None and _check_tts_available():
            try:
                self._load_engine_sync()
            except Exception as e:
                print(f"[TTS] Sync initialization error: {e}", file=sys.stderr)

    async def _initialize_if_needed_async(self):
        if self._tts is None:
            available = await asyncio.to_thread(_check_tts_available)
            if available:
                print(f"[TTS] Initializing engine on {self.device} (Async)...", file=sys.stderr)
                await asyncio.to_thread(self._load_engine_sync)
            else:
                print("[TTS] Voice engine skip: ukrainian-tts not installed.", file=sys.stderr)

    def _load_engine_sync(self):
        if self._tts is not None:
            return

        cache_dir = MODELS_DIR
        cache_dir.mkdir(parents=True, exist_ok=True)

        try:
            print("[TTS] Loading ukrainian-tts and Stanza resources...", file=sys.stderr)
            from contextlib import contextmanager

            @contextmanager
            def tmp_cwd(path):
                old_path = os.getcwd()
                os.chdir(path)
                try:
                    yield
                finally:
                    os.chdir(old_path)

            with tmp_cwd(str(cache_dir)):
                print("[TTS] Downloading/Verifying models in models/tts...", file=sys.stderr)
                _patch_tts_config(cache_dir)
                self._tts = UkrainianTTS(cache_folder=str(cache_dir), device=self.device)  # type: ignore[reportOptionalCall]
                print("[TTS] Engine object created successfully.", file=sys.stderr)
        except Exception as e:
            print(f"[TTS] Failed to initialize engine: {e}", file=sys.stderr)
            self._tts = None

    async def _get_translator(self):
        """Lazy load a small/fast model for translation defense."""
        if self._translator_llm is None:
            from src.brain.config import PROJECT_ROOT

            if str(PROJECT_ROOT) not in sys.path:
                sys.path.insert(0, str(PROJECT_ROOT))

            from src.providers.factory import create_llm

            # Use default model for translation as it's usually fast enough
            model = config.get("models.default", "gpt-4o")
            self._translator_llm = create_llm(
                model_name=model,
                max_tokens=1000,
                temperature=0.1,
            )
        return self._translator_llm

    async def translate_to_ukrainian(self, text: str) -> str:
        """Translates English-heavy text to Ukrainian as a last defense."""
        # Skip translation if text is empty
        if not text.strip():
            return text

        # Count Latin vs Cyrillic to avoid redundant translation of Ukrainian text
        latin_chars = len(re.findall(r"[a-zA-Z]", text))
        cyrillic_chars = len(re.findall(r"[а-яА-ЯёЁіІєЄїЇґҐ]", text))
        total_chars = len(text.strip())

        # If it's mostly Cyrillic, skip translation
        if cyrillic_chars > latin_chars * 2 or (
            total_chars > 0 and cyrillic_chars / total_chars > 0.7
        ):
            return text

        english_words = re.findall(r"[a-zA-Z]{3,}", text)
        # If very few English words and low Latin ratio, skip
        if len(english_words) < 2 and (total_chars > 0 and latin_chars / total_chars < 0.2):
            return text

        # Skip CLI / raw technical payload heuristics
        tech_keywords = {
            "git",
            "prs",
            "commit",
            "status",
            "diff",
            "merge",
            "branch",
            "error:",
            "info:",
            "warning:",
            "debug:",
            "role:",
            "content:",
            "name:",
            "src.",
            "brain.",
            "golden_fund.",
            "atlastrinity",
            "http:",
            "https:",
            "metadata",
            "payload",
            "json",
            "result:",
        }
        text_lower = text.lower().strip()

        # Immediate skip for standard log lines or technical paths
        if any(
            text_lower.startswith(kw) for kw in ["info:", "warning:", "debug:", "error:", "role:"]
        ):
            return text

        # Skip strings with very high dot/underscore density (likely paths/filenames)
        if total_chars > 0 and (text.count(".") + text.count("_")) / total_chars > 0.1:
            return text

        if any(kw in text_lower for kw in tech_keywords) and (
            len(english_words) > 5 or "{" in text
        ):
            # Heavy terminal output, JSON, or multi-keyword technical text
            return text

        logger.info(f"[TTS] 🔄 Translating English-heavy text to Ukrainian: {text[:50]}...")
        llm = await self._get_translator()

        prompt = f"""Task: Translate the following text into HIGH-QUALITY natural Ukrainian.
CRITICAL: ZERO English words. Localize technical terms, paths, and names.
The tone should be professional and guardian-like.

Text: {text}

Ukrainian:"""

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(
                    content="You are a professional Ukrainian translator. Zero English words allowed."
                ),
                HumanMessage(content=prompt),
            ]
            response = await llm.ainvoke(messages)
            translated = str(response.content).strip().strip('"')
            if translated:
                logger.info(f"[TTS] ✅ Translation complete: {translated[:50]}...")
                return translated
        except Exception as e:
            logger.warning(f"[TTS] Translation failed: {e}. Falling back to original text.")

        return text

    async def prepare_speech_text(self, text: str) -> str:
        """Prepares text for speech: sanitizes and translates if needed.
        This method is exposed so the Orchestrator can log exactly what will be spoken.
        """
        if not text:
            return ""

        # 1. Sanitize
        text = sanitize_text_for_tts(text)

        # 2. Translate if needed (force_ukrainian defense)
        if config.get("voice.tts.force_ukrainian", True):
            text = await self.translate_to_ukrainian(text)

        return text

    def stop(self):
        """Immediately stop current speech."""
        if self._stop_event:
            self._stop_event.set()

        # Kill current process if exists
        if self._current_process:
            try:
                self._current_process.terminate()
                print("[TTS] 🛑 Playback interrupted.", file=sys.stderr)
            except Exception as e:
                # Ignore errors during process termination
                logger.debug(f"[TTS] Error terminating playback process: {e}")
            self._current_process = None

        self.is_speaking = False

    async def stop_speaking(self):
        """Alias for stop() for orchestrator compatibility."""
        self.stop()

    async def close(self):
        """Shutdown the voice manager."""
        self.stop()
        await asyncio.sleep(0.1)

    async def speak(self, agent_id: str, text: str) -> str | None:
        """Centralized speak method for VoiceManager."""
        if not self.enabled:
            logger.debug(f"[TTS] [{agent_id.upper()}] Speech skipped (Muted).")
            return None

        self._stop_event.clear()

        async with self._lock:
            # Check interruption immediately
            if self._stop_event.is_set():
                return None

            if not _check_tts_available() or not text:
                print(f"[TTS] [{agent_id.upper()}] (Text-only): {text}", file=sys.stderr)
                return None

            # NOTE: text is already prepared by the orchestrator
            # (VoiceOrchestrationMixin._speak -> voice.prepare_speech_text)
            # Do NOT call prepare_speech_text() here to avoid double-sanitization
            # that causes TTS to speak different text than what appears in the chat panel.

            agent_id = agent_id.lower()
            if agent_id not in AGENT_VOICES:
                print(f"[TTS] Unknown agent: {agent_id}", file=sys.stderr)
                return None

            agent_conf = AGENT_VOICES[agent_id]
            voice_enum = getattr(Voices, agent_conf.voice_id).value

            try:
                # 1. Split text into manageable chunks
                chunks = self._chunk_text_for_tts(text)

                # 2. Start pipelined playback
                return await self._pipelined_playback(agent_id, agent_conf, chunks, voice_enum)
            except Exception as e:
                print(f"[TTS] Error: {e}", file=sys.stderr)
                return None

    def _chunk_text_for_tts(self, text: str) -> list[str]:
        """Split text into manageable chunks for TTS engine."""

        # Split by punctuation
        raw_chunks = re.split(r"([.!?]+(?:\s+|$))", text)
        processed_chunks = []
        for i in range(0, len(raw_chunks) - 1, 2):
            processed_chunks.append(raw_chunks[i] + raw_chunks[i + 1])
        if len(raw_chunks) % 2 == 1 and raw_chunks[-1]:
            processed_chunks.append(raw_chunks[-1])

        # Merge short chunks
        min_len = 40
        refined_chunks = []
        temp_chunk = ""
        for chunk in [c.strip() for c in processed_chunks if c.strip()]:
            if temp_chunk:
                temp_chunk += " " + chunk
            else:
                temp_chunk = chunk
            if len(temp_chunk) >= min_len:
                refined_chunks.append(temp_chunk)
                temp_chunk = ""

        if temp_chunk:
            if refined_chunks:
                refined_chunks[-1] += " " + temp_chunk
            else:
                refined_chunks.append(temp_chunk)

        return refined_chunks or [text]

    async def _pipelined_playback(
        self, agent_id: str, agent_conf: Any, chunks: list[str], voice_enum: Any
    ) -> str | None:
        """Handle pipelined generation and playback of speech chunks."""
        import time

        print(
            f"[TTS] [{agent_conf.name}] Starting pipelined playback for {len(chunks)} chunks...",
            file=sys.stderr,
        )

        # Generate first chunk
        current_file = await self._generate_chunk(chunks[0], 0, agent_id, voice_enum)
        if not current_file:
            return None

        for idx, chunk_text in enumerate(chunks):
            if self._stop_event.is_set():
                print(f"[TTS] [{agent_conf.name}] 🛑 Sequence cancelled.", file=sys.stderr)
                return "cancelled"

            # Start generating next chunk while playing current one
            next_gen_task = None
            if idx + 1 < len(chunks):
                next_gen_task = asyncio.create_task(
                    self._generate_chunk(chunks[idx + 1], idx + 1, agent_id, voice_enum)
                )

            if Path(current_file).exists():
                await self._speak_chunk(idx, len(chunks), chunk_text, current_file, agent_conf)
                Path(current_file).unlink()

            # Wait for next chunk to be ready
            if next_gen_task:
                current_file = await next_gen_task
                if not current_file:
                    return "cancelled"

        await asyncio.sleep(0.3)
        self.last_speak_time = time.time()
        return "pipelined_playback_completed"

    async def _generate_chunk(
        self, text: str, idx: int, agent_id: str, voice_enum: Any
    ) -> Path | None:
        """Generate a single chunk of audio."""
        from ukrainian_tts.tts import Stress

        if self._stop_event.is_set():
            return None

        c_id = f"{agent_id}_{idx}_{hash(text) % 10000}"
        c_file = Path(tempfile.gettempdir()) / f"tts_{c_id}.wav"

        def _do_gen():
            if self.engine:
                with c_file.open(mode="wb") as f:
                    self.engine.tts(
                        text, cast("Any", voice_enum), Stress.Dictionary.value, cast("Any", f)
                    )

        await asyncio.to_thread(_do_gen)
        return c_file

    async def _speak_chunk(
        self, idx: int, total: int, text: str, file_path: Path, agent_conf: Any
    ) -> None:
        """Play a single chunk of audio and manage state."""
        print(
            f"[TTS] [{agent_conf.name}] 🔊 Speaking chunk {idx + 1}/{total}: {text[:50]}...",
            file=sys.stderr,
        )
        self.last_text = text.strip().lower()
        self.history.append(self.last_text)
        self.is_speaking = True

        try:
            self._current_process = await asyncio.create_subprocess_exec(
                "afplay",
                str(file_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await self._current_process.communicate()
        except asyncio.CancelledError:
            print(f"[TTS] [{agent_conf.name}] 🛑 Playback cancelled.", file=sys.stderr)
            if self._current_process:
                self._current_process.terminate()
            raise
        except Exception as e:
            print(f"[TTS] [{agent_conf.name}] ⚠ Playback error: {e}", file=sys.stderr)
        finally:
            self.is_speaking = False
            self._current_process = None
