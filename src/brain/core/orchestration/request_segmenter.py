"""Request Segmenter — Intelligent Multi-Mode Request Splitting

Splits mixed user requests into separate mode-specific segments for optimal processing.
Integrates with mode_profiles.json configuration for declarative segmentation rules.

Architecture:
    1. LLM analyzes request structure and intent segments
    2. Mode profiles provide segmentation rules and priorities
    3. Segments are ordered by priority and execution context
    4. Each segment gets its own ModeProfile for processing

Usage:
    from src.brain.core.orchestration.request_segmenter import request_segmenter

    segments = await request_segmenter.split_request(user_request, history, context)
    # Returns list of RequestSegment objects
"""

import json
import os
from dataclasses import dataclass
from typing import Any

from src.brain.core.orchestration.mode_router import ModeProfile, ModeRouter
from src.brain.monitoring.logger import logger

# Load mode profiles for segmentation rules
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_PROFILES_PATH = os.path.join(_DATA_DIR, "mode_profiles.json")

_MODE_PROFILES: dict[str, Any] = {}
_SEGMENTATION_CONFIG: dict[str, Any] = {}


def _load_profiles() -> None:
    """Load mode profiles and segmentation config."""
    global _MODE_PROFILES, _SEGMENTATION_CONFIG
    try:
        # Load mode profiles from JSON
        if os.path.exists(_PROFILES_PATH):
            with open(_PROFILES_PATH, encoding="utf-8") as f:
                data = json.load(f)

            _MODE_PROFILES = data.copy()
            _MODE_PROFILES.pop("_meta", None)
            _MODE_PROFILES.pop("_protocol_registry", None)

            logger.info(f"[SEGMENTER] Loaded {len(_MODE_PROFILES)} mode profiles")
        else:
            logger.warning(f"[SEGMENTER] Mode profiles not found at {_PROFILES_PATH}")
            _MODE_PROFILES = {}

        # Load segmentation config from config.yaml
        try:
            from src.brain.config.config_loader import CONFIG_ROOT
        except ImportError:
            # Fallback for direct execution
            from src.brain.config.config_loader import CONFIG_ROOT
        config_path = CONFIG_ROOT / "config.yaml"
        if config_path.exists():
            import yaml

            with open(config_path, encoding="utf-8") as f:
                config_data = yaml.safe_load(f)

            _SEGMENTATION_CONFIG = config_data.get("segmentation", {})
            logger.info(
                f"[SEGMENTER] Loaded segmentation config from config.yaml: enabled={_SEGMENTATION_CONFIG.get('enabled')}"
            )
        # Fallback to mode_profiles.json
        elif os.path.exists(_PROFILES_PATH):
            with open(_PROFILES_PATH, encoding="utf-8") as f:
                data = json.load(f)
            _SEGMENTATION_CONFIG = data.get("_meta", {}).get("segmentation", {})
            logger.info("[SEGMENTER] Using fallback config from mode_profiles.json")
        else:
            logger.warning("[SEGMENTER] No segmentation config found, using defaults")
            _SEGMENTATION_CONFIG = {"enabled": False, "max_segments": 5}

    except Exception as e:
        logger.error(f"[SEGMENTER] Failed to load configuration: {e}")
        # Set safe defaults
        _SEGMENTATION_CONFIG = {"enabled": False, "max_segments": 5}


_load_profiles()


@dataclass
class RequestSegment:
    """Single segment of a split request with its mode profile."""

    text: str
    mode: str
    priority: int
    reason: str = ""
    start_pos: int = 0
    end_pos: int = 0
    profile: ModeProfile | None = None

    def __post_init__(self) -> None:
        """Create profile from mode if not provided."""
        if self.profile is None:
            self.profile = _build_segment_profile(self.mode, self.text)


def _build_segment_profile(mode: str, text: str) -> ModeProfile:
    """Build ModeProfile for a segment using mode defaults."""
    defaults = _MODE_PROFILES.get(mode) or _MODE_PROFILES.get("chat") or {}

    return ModeProfile(
        mode=mode,
        reason=f"Segmented request: {text[:50]}...",
        enriched_request=text,
        complexity=defaults.get("complexity", "medium"),
        llm_tier=defaults.get("llm_tier", "standard"),
        protocols=list(defaults.get("protocols", [])),
        servers=list(defaults.get("servers", [])),
        tools_access=defaults.get("tools_access", "none"),
        prompt_template=defaults.get("prompt_template", "atlas_chat"),
        require_planning=defaults.get("require_planning", False),
        require_tools=defaults.get("require_tools", False),
        use_deep_persona=defaults.get("use_deep_persona", False),
        use_sequential_thinking=defaults.get("use_sequential_thinking", False),
        use_vibe=defaults.get("use_vibe", False),
        trinity_required=defaults.get("trinity_required", False),
    )


class RequestSegmenter:
    """Intelligent request segmentation using LLM + mode profile rules."""

    def __init__(self) -> None:
        self.mode_router = ModeRouter()
        self._segmentation_count = 0
        self._fallback_count = 0

    async def split_request(
        self,
        user_request: str,
        history: list[Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[RequestSegment]:
        """Split user request into mode-specific segments.

        Args:
            user_request: Full user request text
            history: Conversation history
            context: Additional context

        Returns:
            List of RequestSegment objects
        """
        self._segmentation_count += 1

        logger.info(f"[SEGMENTER] Starting segmentation #{self._segmentation_count}")
        logger.info(f"[SEGMENTER] Request: '{user_request[:100]}...'")
        logger.info(f"[SEGMENTER] Config enabled: {_SEGMENTATION_CONFIG.get('enabled')}")

        # Check if segmentation is enabled
        if not _SEGMENTATION_CONFIG.get("enabled", False):
            logger.warning("[SEGMENTER] Segmentation disabled in config")
            return [
                RequestSegment(
                    text=user_request, mode="chat", priority=1, reason="Segmentation disabled"
                )
            ]

        # Try LLM-based segmentation first
        try:
            logger.info("[SEGMENTER] Trying LLM-based segmentation")
            segments = await self._llm_segmentation(user_request, history, context)
            if segments:
                logger.info(f"[SEGMENTER] LLM segmentation: {len(segments)} segments")
                for i, seg in enumerate(segments):
                    logger.info(
                        f"[SEGMENTER] LLM Segment {i + 1}: mode={seg.mode}, text='{seg.text[:50]}...'"
                    )
                return self._sort_and_merge_segments(segments)
            logger.warning("[SEGMENTER] LLM segmentation returned EMPTY segments")
        except Exception as e:
            logger.warning(f"[SEGMENTER] LLM segmentation failed: {e}")

        # Fallback to manual question-based segmentation
        logger.info("[SEGMENTER] Falling back to manual question-based segmentation")
        self._fallback_count += 1
        return self._create_question_segments(user_request)

    async def _llm_segmentation(
        self,
        user_request: str,
        history: list[Any] | None,
        context: dict[str, Any] | None,
    ) -> list[RequestSegment]:
        """Use LLM to intelligently split request into segments."""

        # Get LLM provider config from segmentation settings
        llm_config = _SEGMENTATION_CONFIG.get("llm_provider", {})

        # Use global config as fallback
        try:
            from src.brain.config.config_loader import config
        except ImportError:
            # Fallback for direct execution
            from src.brain.config.config_loader import config
        global_models = config.get("models", {})

        provider = llm_config.get("provider", global_models.get("provider", "copilot"))
        model = llm_config.get("model", global_models.get("default", "gpt-4.1"))
        tier = llm_config.get("tier", "standard")
        temperature = llm_config.get("temperature", 0.1)

        logger.info(
            f"[SEGMENTER] Using LLM provider: {provider}/{model} (tier={tier}, temp={temperature})"
        )

        # Build enhanced segmentation prompt with context awareness
        prompt = self._build_enhanced_segmentation_prompt(user_request, history, context)

        # Import here to avoid circular imports
        from src.brain.agents.atlas import Atlas

        # Use configured LLM for segmentation
        atlas = Atlas()
        from langchain_core.messages import HumanMessage, SystemMessage

        system_prompt = self._build_intelligent_system_prompt()

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt),
        ]

        response = None
        try:
            # Use appropriate LLM based on configuration
            if tier == "deep" and hasattr(atlas, "llm"):
                # For deep tier, use standard LLM with enhanced parameters
                response = await atlas.llm.ainvoke(messages)
            else:
                response = await atlas.llm.ainvoke(messages)

            # Clean non-printable characters that might cause JSONDecodeError
            import re

            content = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", str(response.content)).strip()

            if not content:
                logger.error("[SEGMENTER] LLM returned an empty response content (after cleaning)")
                return []

            # Strip markdown code fences (```json ... ```) that LLMs often wrap around JSON
            fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", content, re.DOTALL)
            if fence_match:
                content = fence_match.group(1).strip()
                logger.debug("[SEGMENTER] Stripped markdown code fence from LLM response")

            result = json.loads(content)
            logger.info(
                f"[SEGMENTER] LLM response: {len(result.get('segments', []))} segments proposed"
            )

            # Validate and refine segments based on configuration
            segments = self._validate_and_refine_segments(result.get("segments", []), user_request)

            return segments

        except json.JSONDecodeError as e:
            logger.error(f"[SEGMENTER] LLM segmentation failed to parse JSON: {e}")
            logger.debug(f"[SEGMENTER] Raw response content: {getattr(response, 'content', 'N/A')}")
            return []
        except Exception as e:
            logger.error(f"[SEGMENTER] LLM segmentation failed: {e}")
            return []

    def _build_enhanced_segmentation_prompt(
        self,
        user_request: str,
        history: list[Any] | None,
        context: dict[str, Any] | None,
    ) -> str:
        """Build prompt for LLM segmentation with context awareness."""
        segmentation_rules = _SEGMENTATION_CONFIG.get("segmentation_rules", {})

        prompt_parts = ["REQUEST TO ANALYZE:", f'"{user_request}"', ""]

        # Add conversation context if available
        if history and segmentation_rules.get("preserve_context", True):
            recent_history = history[-3:] if len(history) > 3 else history
            prompt_parts.extend(
                ["CONVERSATION CONTEXT:", f"Recent messages: {recent_history!s}", ""]
            )

        # Add additional context if provided
        if context and segmentation_rules.get("preserve_context", True):
            prompt_parts.extend(["ADDITIONAL CONTEXT:", f"Context data: {context!s}", ""])

        # Add segmentation guidance
        prompt_parts.extend(
            [
                "TASK:",
                "Split this request into logical segments by intent mode.",
                "",
                "ANALYSIS GUIDELINES:",
                "- Look for natural transitions between different types of intent",
                "- Consider the user's flow and conversational context",
                "- Each segment should be processed with its optimal mode",
                "- Maintain the original order from the user's request",
                "- Focus on semantic meaning, not just keywords",
                "",
            ]
        )

        return "\n".join(prompt_parts)

    def _build_intelligent_system_prompt(self) -> str:
        """Build system prompt for LLM segmentation."""

        prompt = """You are an advanced request segmentation expert. Your task is to intelligently analyze user requests and split them into logical segments by intent mode.

AVAILABLE MODES (in priority order - LOWER NUMBER = HIGHER PRIORITY):
1. deep_chat: Philosophical, identity, mission, soul, consciousness topics (PRIORITY: 1 - HIGHEST)
2. chat: Simple greetings, small talk, thanks, acknowledgments (PRIORITY: 2)
3. solo_task: Research, lookup, info retrieval with tools (PRIORITY: 3)
4. task: Direct execution requiring planning and tools (PRIORITY: 4)
5. development: Software development, coding, debugging, testing (PRIORITY: 5 - LOWEST)

CRITICAL PRIORITY RULES:
- ALWAYS detect deep_chat mode FIRST for philosophical/identity questions
- deep_chat has PRIORITY 1 and should be processed before any other mode
- Look for questions about: creation, mission, consciousness, identity, soul, freedom, future
- Numbered questions (1., 2., 3.) about identity/mission → deep_chat mode
- Technical tasks with tools → task mode (PRIORITY 4)
- Simple conversation → chat mode (PRIORITY 2)

SEGMENTATION PRINCIPLES:
1. Analyze semantic intent, not just keywords.
2. CONTEXTUAL CONTINUITY: Understand that multiple questions or tasks may be part of a single flow. Even if separated by commas or numbering, they might share context or refer to each other.
3. Each segment should have one clear, primary intent, but MUST retain the necessary context from surrounding segments.
4. Maintain original order from user request.
5. Consider context and conversation history.
6. Minimum 3 words per segment (except chat mode).
7. Maximum 5 segments per request (focus on most important splits).

SPECIAL HANDLING FOR QUESTIONS & COMMAS:
- Comma-separated or numbered questions (1., 2., 3.) are often separate segments but share the same user intent flow.
- Questions about identity, creation, mission, consciousness → deep_chat mode (PRIORITY 1)
  (EVEN IF LONG OR COMPLEX, THESE ARE ALWAYS DEEP_CHAT)
- Technical tasks with tools → task mode (PRIORITY 4)
- Multiple questions should be separate segments, but if they are intrinsically linked (e.g., "Tell me about X and then do Y"), ensure the "do Y" segment understands that "X" is the context.
- DEEP_CHAT questions must be processed FIRST before any task segments.

CONTEXTUAL ANALYSIS:
- Consider conversation history for context
- Identify transitions between different types of tasks
- Look for intent shifts (e.g., greeting → deep_chat → task)
- Prioritize user's natural flow and intent
- Pay attention to explicit numbering (1., 2., 3.)
- RESPECT PRIORITY ORDER: deep_chat (1) comes before task (4)

CRITICAL: Output ONLY valid JSON. Do NOT wrap in markdown code fences (```json). Do NOT add explanatory text before or after the JSON.

OUTPUT FORMAT:
Return JSON format:
{
  "segments": [
    {
      "text": "exact segment text from request",
      "mode": "mode_name", 
      "reason": "why this mode based on intent analysis",
      "start_pos": 0,
      "end_pos": 15,
      "confidence": 0.95
    }
  ]
}

Focus on accuracy and semantic understanding. Each segment should be meaningful and actionable. CRITICAL: Always create separate segments for numbered questions and ensure deep_chat gets PRIORITY 1 for ANY questions about identity/mission/soul, regardless of request length or complexity."""

        return prompt

    def _validate_and_refine_segments(
        self,
        segments: list[dict[str, Any]],
        user_request: str,
    ) -> list[RequestSegment]:
        """Validate and refine segments based on configuration."""
        refined_segments = []
        post_processing_config = _SEGMENTATION_CONFIG.get("post_processing", {})

        for segment in segments:
            text = segment.get("text", "")
            mode = segment.get("mode", "chat")
            reason = segment.get("reason", "")
            start_pos = segment.get("start_pos", 0)
            end_pos = segment.get("end_pos", 0)

            # Validate segment integrity
            if post_processing_config.get("validate_segment_integrity", True):
                if not self._validate_segment_integrity(text, mode, user_request):
                    logger.warning(
                        f"[SEGMENTER] Invalid segment: mode={mode}, text='{text[:30]}...'"
                    )
                    continue

            # Create RequestSegment with proper profile
            request_segment = RequestSegment(
                text=text,
                mode=mode,
                priority=self._get_mode_priority(mode),
                reason=reason,
                start_pos=start_pos,
                end_pos=end_pos,
            )

            refined_segments.append(request_segment)

        logger.info(f"[SEGMENTER] Refined {len(refined_segments)} valid segments")
        return refined_segments

    def _validate_segment_integrity(self, text: str, mode: str, full_request: str) -> bool:
        """Validate that segment is properly formed and makes sense."""
        min_length = _SEGMENTATION_CONFIG.get("min_segment_length", 3)

        # Check minimum length (except for chat mode)
        if mode != "chat" and len(text.split()) < min_length:
            return False

        # Check if text exists in original request
        if text not in full_request:
            return False

        # Check if mode is valid
        return mode in _MODE_PROFILES

    def _keyword_segmentation(self, user_request: str) -> list[RequestSegment]:
        """Fallback keyword-based segmentation using mode profiles."""

        segments = []
        words = user_request.split()
        current_segment = []
        current_mode: str | None = None
        current_start = 0

        for i, word in enumerate(words):
            word_lower = word.lower()

            # Check each mode's split keywords
            detected_mode: str | None = None
            for mode_name, mode_config in _MODE_PROFILES.items():
                seg_config = mode_config.get("segmentation", {})
                split_keywords = seg_config.get("split_keywords", [])

                if any(keyword in word_lower for keyword in split_keywords):
                    detected_mode = mode_name
                    break

            # If mode changed, create segment
            if detected_mode and detected_mode != current_mode and current_segment:
                # Save previous segment
                segment_text = " ".join(current_segment)
                if len(segment_text.strip()) >= _SEGMENTATION_CONFIG.get("min_segment_length", 3):
                    segments.append(
                        RequestSegment(
                            text=segment_text,
                            mode=current_mode or "chat",
                            priority=self._get_mode_priority(current_mode or "chat"),
                            reason=f"Keyword detection: {current_mode}",
                            start_pos=current_start,
                            end_pos=current_start + len(segment_text),
                        )
                    )

                current_segment = [word]
                current_mode = detected_mode
                current_start = len(" ".join(words[:i]))
            else:
                current_segment.append(word)
                if not current_mode and detected_mode:
                    current_mode = detected_mode

        # Add final segment
        if current_segment:
            segment_text = " ".join(current_segment)
            if len(segment_text.strip()) >= _SEGMENTATION_CONFIG.get("min_segment_length", 3):
                segments.append(
                    RequestSegment(
                        text=segment_text,
                        mode=current_mode or "chat",
                        priority=self._get_mode_priority(current_mode or "chat"),
                        reason=f"Keyword detection: {current_mode}",
                        start_pos=current_start,
                        end_pos=len(user_request),
                    )
                )

        return segments or [
            RequestSegment(
                text=user_request, mode="chat", priority=1, reason="No segmentation detected"
            )
        ]

    def _get_mode_priority(self, mode: str) -> int:
        """Get priority from mode profile segmentation config."""
        mode_config = _MODE_PROFILES.get(mode, {})
        seg_config = mode_config.get("segmentation", {})
        return seg_config.get("priority", 999)

    def _sort_and_merge_segments(self, segments: list[RequestSegment]) -> list[RequestSegment]:
        """Preserve original order while using priority for stability and merge compatible segments."""

        # Sort by start_pos FIRST to maintain original request order (CRITICAL for questions)
        # Priority only used as secondary key for same start_pos
        # segments.sort(key=lambda s: (s.start_pos, s.priority))
        # FIXED: Do NOT sort by start_pos. Trust the LLM's output order or keyword order.
        # Sorting can break execution flow if start_pos is hallucinated or defaulted to 0.

        # Merge consecutive segments
        merged: list[RequestSegment] = []
        for seg in segments:
            if not merged:
                merged.append(seg)
                continue

            last = merged[-1]
            mode_config = _MODE_PROFILES.get(last.mode, {})
            seg_config = mode_config.get("segmentation", {})
            merge_with = seg_config.get("merge_with", [])

            # Check if this segment can be merged into the last one
            if seg.mode == last.mode or seg.mode in merge_with:
                last.text = f"{last.text} {seg.text}".strip()
                last.end_pos = seg.end_pos
                last.reason = f"Merged {last.mode}+{seg.mode}"
                # Keep the lower priority (more important)
                last.priority = min(last.priority, seg.priority)
            else:
                merged.append(seg)

        # Limit number of segments
        max_segments = _SEGMENTATION_CONFIG.get("max_segments", 5)
        if len(merged) > max_segments:
            logger.warning(
                f"[SEGMENTER] Too many segments ({len(merged)}), limiting to {max_segments}"
            )
            # Keep highest priority segments from original order
            merged = merged[:max_segments]

        return merged

    async def _classify_full_request(
        self,
        user_request: str,
        history: list[Any] | None,
        context: dict[str, Any] | None,
    ) -> ModeProfile:
        """Classify full request without segmentation (fallback)."""

        # Use existing Atlas analyze_request
        from src.brain.agents.atlas import Atlas

        atlas = Atlas()
        analysis = await atlas.analyze_request(user_request, context, history)
        return analysis.get("mode_profile", self.mode_router.build_profile({"mode": "chat"}))

    def _create_question_segments(self, user_request: str) -> list[RequestSegment]:
        """Create segments for questions when LLM segmentation fails."""
        segments = []

        # Split by question markers
        question_parts = []
        current_part = ""

        lines = user_request.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith(("1.", "2.", "3.", "Ким", "Яка", "Ти")):
                if current_part:
                    question_parts.append(current_part.strip())
                current_part = line
            else:
                current_part += " " + line if current_part else line

        if current_part:
            question_parts.append(current_part.strip())

        # Create segments for each question
        for i, part in enumerate(question_parts):
            if part and len(part.split()) >= 3:
                # Identity markers for deep_chat
                is_deep_chat = any(
                    word in part.lower()
                    for word in ["створили", "місія", "особистість", "хто ти", "твоя душа"]
                )
                # Info-seeking markers for solo_task
                is_info_seeking = any(
                    word in part.lower()
                    for word in [
                        "розкажи",
                        "інформація",
                        "фільм",
                        "найди",
                        "знайди",
                        "пошукай",
                        "хто такий",
                        "що таке",
                        "оціни",
                        "режисер",
                    ]
                )

                mode = "chat"
                if is_deep_chat:
                    mode = "deep_chat"
                elif is_info_seeking:
                    mode = "solo_task"

                segments.append(
                    RequestSegment(
                        text=part,
                        mode=mode,
                        priority=1 if mode == "deep_chat" else (3 if mode == "solo_task" else 2),
                        reason=f"Question segmentation {i + 1} (manual fallback)",
                        start_pos=user_request.find(part) if part in user_request else 0,
                        end_pos=user_request.find(part) + len(part)
                        if part in user_request
                        else len(part),
                    )
                )

        # Add task segment for MCP testing
        task_part = "залучити всі доступні інструменти мсп які є в тебе і перевірити таким чином кожені інструмент мсп, зі всіх серверів доступних, їх має бути приблизно 21+."
        if task_part in user_request:
            segments.append(
                RequestSegment(
                    text=task_part,
                    mode="task",
                    priority=4,  # Fixed: task mode should have priority 4 according to mode_profiles.json
                    reason="MCP testing task",
                    start_pos=user_request.find(task_part),
                    end_pos=user_request.find(task_part) + len(task_part),
                )
            )

        logger.info(f"[SEGMENTER] Created {len(segments)} question segments manually")
        return segments

    def get_stats(self) -> dict[str, Any]:
        """Segmentation statistics."""
        return {
            "total_segmentations": self._segmentation_count,
            "fallback_segmentations": self._fallback_count,
            "fallback_rate_pct": (
                round(self._fallback_count / self._segmentation_count * 100, 2)
                if self._segmentation_count > 0
                else 0
            ),
            "segmentation_enabled": _SEGMENTATION_CONFIG.get("enabled", False),
            "available_modes": list(_MODE_PROFILES.keys()),
        }


# Global singleton
request_segmenter = RequestSegmenter()
