import asyncio
import hashlib
import re
import sys
import time
from datetime import datetime
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage

from src.brain.behavior.behavior_engine import behavior_engine
from src.brain.monitoring.logger import logger

if TYPE_CHECKING:
    from src.brain.voice.tts import VoiceManager


class VoiceOrchestrationMixin:
    """Mixin to handle voice feedback and log callbacks for the Trinity orchestrator."""

    # Optional attributes that may be provided by implementing classes
    _spoken_history: dict[str, float] = {}
    _last_live_speech_time: int | None = None
    voice: "VoiceManager"  # Type hint for checks, actual value provided by implementer

    async def _speak(self, agent_id: str, text: str, *, chat_visible: bool = True) -> None:
        """Voice wrapper with config-driven sanitization.

        Args:
            agent_id: The agent whose voice to use.
            text: Text to speak.
            chat_visible: If True (default), the message is also added to the chat
                          panel via handle_chat_log(). Set to False for internal
                          status messages that should only be spoken, not displayed.
        """
        voice_config = behavior_engine.get_output_processing("voice")

        # Deduplication Logic
        msg_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        now = time.time()
        last_time = getattr(self, "_spoken_history", {}).get(msg_hash, 0)

        if now - last_time < 60:
            logger.info(f"[VOICE] Skipping duplicate message (Cooldown active): '{text[:50]}...'")
            return

        if not hasattr(self, "_spoken_history"):
            self._spoken_history = {}
        self._spoken_history[msg_hash] = now

        # Cleanup old history
        if len(self._spoken_history) > 100:
            current_time = now
            self._spoken_history = {
                k: v for k, v in self._spoken_history.items() if current_time - v < 120
            }

        # TTS processing
        processed_text = text
        for rule in voice_config.get("sanitization_rules", []):
            pattern = rule.get("pattern")
            replacement = rule.get("replacement", "")
            if pattern:
                processed_text = re.sub(pattern, replacement, processed_text)

        processed_text = processed_text.strip()

        # Length limits
        max_len = voice_config.get("max_length", 500)
        if len(processed_text) < 10:
            logger.info(
                f"[VOICE] Text too short for TTS ({len(processed_text)} chars), skipping voice"
            )
            return

        if len(processed_text) > max_len:
            logger.info(
                f"[VOICE] Text too long for TTS ({len(processed_text)} chars), truncating for voice"
            )
            processed_text = processed_text[:max_len]

        # This relies on self.voice (VoiceManager) being available on Trinity
        if hasattr(self, "voice"):
            final_text = await self.voice.prepare_speech_text(processed_text)
        else:
            final_text = processed_text

        if not final_text:
            return

        print(f"[{agent_id.upper()}] Speaking: {final_text[:100]}", file=sys.stderr)

        try:
            if chat_visible and hasattr(self, "handle_chat_log"):
                await self.handle_chat_log(agent_id, final_text)

            if hasattr(self, "voice"):
                await self.voice.speak(agent_id, final_text)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"TTS Error: {e}", file=sys.stderr)

    async def _save_chat_message(
        self, role: str, content: str, agent_id: str | None = None
    ) -> None:
        """Optional: Save chat message - implementing classes should override this."""

    async def _log(self, text: str, source: str, type: str = "voice") -> None:
        """Optional: Log message - implementing classes should override this."""

    def stop(self) -> None:
        """Optional: Stop speech - implementing classes should override this."""

    async def _mcp_log_voice_callback(self, msg: str, server_name: str, level: str) -> None:
        """Callback to handle live log notifications from MCP servers."""
        now = time.time()

        significant_markers = ["[VIBE-THOUGHT]", "[VIBE-ACTION]", "[VIBE-LIVE]"]
        if server_name == "vibe" and any(marker in msg for marker in significant_markers):
            speech_text = msg
            for marker in significant_markers:
                speech_text = speech_text.replace(marker, "")
            speech_text = re.sub(r"[^\w\s\.,!\?]", "", speech_text).strip()

            if len(speech_text) > 5:
                # Use 'atlas' for status updates
                if hasattr(self, "_last_live_speech_time"):
                    self._last_live_speech_time = int(now)
                if hasattr(self, "_speak"):
                    asyncio.create_task(self._speak("atlas", speech_text, chat_visible=False))

    async def handle_voice_feedback(self, agent_id: str, text: str) -> None:
        """Handle voice feedback and route to appropriate handlers."""
        await self._speak(agent_id, text)

    async def handle_chat_log(self, agent_id: str, text: str) -> None:
        """Handle chat message logging."""
        state = getattr(self, "state", None)
        if state is not None and "messages" in state:
            msg = AIMessage(content=text, name=agent_id.upper())
            msg.additional_kwargs["timestamp"] = datetime.now().timestamp()
            state["messages"].append(msg)

            # This relies on _save_chat_message being available on self (Trinity)
            if hasattr(self, "_save_chat_message"):
                await self._save_chat_message("ai", text, agent_id)

        # This relies on _log being available on self (Trinity)
        if hasattr(self, "_log"):
            await self._log(text, source=agent_id, type="voice")

    async def stop_all_speech(self) -> None:
        """Stop all speech activity."""
        # This relies on self.stop() being available on Trinity
        if hasattr(self, "stop"):
            self.stop()
            logger.info("[VoiceManager] Stopped speaking.")
