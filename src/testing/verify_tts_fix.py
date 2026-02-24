import asyncio
import os
import sys
from pathlib import Path


# Mock behavior_engine and logger
class MockLogger:
    def info(self, msg):
        print(f"INFO: {msg}")

    def debug(self, msg):
        print(f"DEBUG: {msg}")

    def warning(self, msg):
        print(f"WARNING: {msg}")


class MockBehaviorEngine:
    def get_output_processing(self, cat):
        return {"sanitization_rules": [], "max_length": 500}


# Add project root to sys.path
PROJECT_ROOT = Path("/Users/dev/Documents/GitHub/atlastrinity")
sys.path.append(str(PROJECT_ROOT))

# Import the actual components
from src.brain.voice.orchestration_utils import VoiceOrchestrationMixin
from src.brain.voice.tts import VoiceManager, sanitize_text_for_tts


class MockTrinity(VoiceOrchestrationMixin):
    def __init__(self):
        self.voice = VoiceManager()
        self._spoken_history = {}

    async def handle_chat_log(self, agent_id, text):
        print(f"CHAT [{agent_id.upper()}]: {text}")

    async def _log(self, text: str, source: str, type: str = "voice") -> None:
        pass

    def stop(self):
        pass


async def test_filtering():
    trinity = MockTrinity()

    print("\n--- Testing Vibe Server Marker Filtering Simulation ---")
    # Simulate a Vibe log that SHOULD NOT be spoken
    test_logs = [
        "INFOsrc.brain.monitoring.trace",
        "INFOgolden_fund.storage.sql",
        "DEBUGbrain.core.server",
        "role system, content...",
        '  File "vibe_server.py", line 100',
    ]

    for log in test_logs:
        print(f"Processing technical log: {log}")
        # The marker logic is inside vibe_server.py, let's assume it bypasses it
        # and we test the secondary filter in orchestration_utils.py
        await trinity._mcp_log_voice_callback(f"[VIBE-LIVE] {log}", "vibe", "info")

    print("\n--- Testing Human-like Progress Simulation ---")
    human_logs = [
        "Запускаю процес імітації...",
        "Наповнюю систему даними про справи",
        "Процес завершено успішно.",
    ]
    for log in human_logs:
        print(f"Processing human log: {log}")
        await trinity._mcp_log_voice_callback(f"[VIBE-LIVE] {log}", "vibe", "info")

    print("\n--- Testing TTS Technical Guard ---")
    # Test tts.py prepare_speech_text technical English guard
    tech_english = "INFO src.brain.monitoring.****MASKED_SECRET****"
    prepared = await trinity.voice.prepare_speech_text(tech_english)
    print(f"Original: {tech_english}")
    print(f"Prepared: '{prepared}' (Expected: '')")


if __name__ == "__main__":
    asyncio.run(test_filtering())
