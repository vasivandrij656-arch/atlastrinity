from __future__ import annotations

import json
import os
import re
import struct
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

import grpc
import httpx
import requests
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

# Session watcher for proactive LS detection
try:
    from src.providers.utils.windsurf_session_watcher import WindsurfSessionWatcher

    _SESSION_WATCHER_AVAILABLE = True
except ImportError:
    _SESSION_WATCHER_AVAILABLE = False

# Type aliases
ContentItem = str | dict[str, Any]

# Load environment variables from global .env
try:
    from dotenv import load_dotenv

    load_dotenv("/Users/dev/.config/atlastrinity/.env", override=True)
except ImportError:
    pass  # dotenv not available, use system env vars

# ─── Windsurf Models (loaded from config/all_models.json) ────────────────────
# Single source of truth: config/all_models.json, loaded via model_registry

try:
    from src.providers.utils.model_registry import get_windsurf_models

    WINDSURF_MODELS: dict[str, str] = get_windsurf_models()
except Exception:
    # Fallback if model_registry or all_models.json is unavailable
    WINDSURF_MODELS = {
        "swe-1.5": "MODEL_SWE_1_5",
        "deepseek-v3": "MODEL_DEEPSEEK_V3",
        "deepseek-r1": "MODEL_DEEPSEEK_R1",
        "swe-1": "MODEL_SWE_1",
        "grok-code-fast-1": "MODEL_GROK_CODE_FAST_1",
        "kimi-k2.5": "kimi-k2-5",
        "windsurf-fast": "MODEL_CHAT_11121",
    }

# For backward compat
WINDSURF_FREE_MODELS = WINDSURF_MODELS

# Default model
WINDSURF_DEFAULT_MODEL = "windsurf-fast"

# Windsurf Connect-RPC source enum (proto: ChatMessageSource)
SOURCE_SYSTEM = 0
SOURCE_USER = 1
SOURCE_ASSISTANT = 2

# Backward compat aliases
ROLE_SYSTEM = SOURCE_SYSTEM
ROLE_USER = SOURCE_USER
ROLE_ASSISTANT = SOURCE_ASSISTANT

# Language Server endpoints (Connect-RPC / HTTP)
LS_RAW_CHAT = "/exa.language_server_pb.LanguageServerService/RawGetChatMessage"
LS_CHECK_CAPACITY = "/exa.language_server_pb.LanguageServerService/CheckChatCapacity"
LS_HEARTBEAT = "/exa.language_server_pb.LanguageServerService/Heartbeat"

# Language Server gRPC service path prefix
# Language Server gRPC service path prefix
# Language Server gRPC service path prefix
_GRPC_SVC = "/exa.language_server_pb.LanguageServerService/"


# Cascade default model — pick first non-legacy UID from WINDSURF_MODELS
_NON_LEGACY = [v for _, v in WINDSURF_MODELS.items() if v != "MODEL_CHAT_11121"]
CASCADE_DEFAULT_MODEL = _NON_LEGACY[0] if _NON_LEGACY else "MODEL_SWE_1_5"

# Map display names to Cascade-compatible model UIDs
# CASCADE_MODEL_MAP mirrors WINDSURF_MODELS — single source of truth
CASCADE_MODEL_MAP: dict[str, str] = dict(WINDSURF_MODELS)

# Max seconds to wait for Cascade AI response
CASCADE_TIMEOUT = 90

# Seconds to wait for first cascade frame before aborting
CASCADE_EARLY_ABORT = 15

# Mode fallback chain — ordered list of alternative modes to try on failure
_FALLBACK_CHAIN: dict[str, list[str]] = {
    "cascade": ["local", "proxy", "direct"],
    "local": ["cascade", "proxy", "direct"],
    "proxy": ["direct"],
    "direct": ["proxy"],
}

# ─── Proto Binary Helpers ────────────────────────────────────────────────────


def _proto_varint(val: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    r = b""
    while val > 0x7F:
        r += bytes([(val & 0x7F) | 0x80])
        val >>= 7
    r += bytes([val])
    return r


def _proto_str(field_num: int, s: str) -> bytes:
    """Encode a string field in protobuf binary format."""
    b = s.encode("utf-8")
    return _proto_varint((field_num << 3) | 2) + _proto_varint(len(b)) + b


def _proto_msg(field_num: int, inner: bytes) -> bytes:
    """Encode a sub-message field in protobuf binary format."""
    return _proto_varint((field_num << 3) | 2) + _proto_varint(len(inner)) + inner


def _proto_int(field_num: int, val: int) -> bytes:
    """Encode a varint field in protobuf binary format."""
    return _proto_varint((field_num << 3) | 0) + _proto_varint(val)


def _proto_extract_string(data: bytes, target_field: int) -> str:
    """Extract first string at target_field from proto binary."""
    offset = 0
    while offset < len(data):
        tag = 0
        shift = 0
        while offset < len(data):
            b = data[offset]
            offset += 1
            tag |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break
        fn = tag >> 3
        wt = tag & 0x07
        if fn == 0:
            break
        if wt == 0:  # varint
            while offset < len(data) and data[offset] & 0x80:
                offset += 1
            if offset < len(data):
                offset += 1
        elif wt == 2:  # length-delimited
            ln = 0
            s = 0
            while offset < len(data):
                b = data[offset]
                offset += 1
                ln |= (b & 0x7F) << s
                s += 7
                if not (b & 0x80):
                    break
            payload = data[offset : offset + ln]
            offset += ln
            if fn == target_field:
                try:
                    return payload.decode("utf-8")
                except UnicodeDecodeError:
                    pass
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        else:
            break
    return ""


def _proto_find_strings(data: bytes, min_len: int = 4) -> list[str]:
    """Recursively extract all readable strings from proto binary."""
    results: list[str] = []
    offset = 0
    while offset < len(data):
        tag = 0
        shift = 0
        while offset < len(data):
            b = data[offset]
            offset += 1
            tag |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break
        fn = tag >> 3
        wt = tag & 0x07
        if fn == 0 or fn > 200:
            break
        if wt == 0:
            while offset < len(data) and data[offset] & 0x80:
                offset += 1
            if offset < len(data):
                offset += 1
        elif wt == 2:
            ln = 0
            s = 0
            while offset < len(data):
                b = data[offset]
                offset += 1
                ln |= (b & 0x7F) << s
                s += 7
                if not (b & 0x80):
                    break
            payload = data[offset : offset + ln]
            offset += ln
            try:
                text = payload.decode("utf-8")
                if len(text) >= min_len and all(32 <= ord(c) < 127 or c in "\n\r\t" for c in text):
                    results.append(text)
            except UnicodeDecodeError:
                pass
            # Always recurse into sub-messages
            results.extend(_proto_find_strings(payload, min_len))
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        else:
            break
    return results


def _build_metadata_proto(api_key: str, session_id: str) -> bytes:
    """Build Metadata proto binary (exa.codeium_common_pb.Metadata)."""
    return (
        _proto_str(1, "windsurf")
        + _proto_str(2, "1.9552.21")
        + _proto_str(3, api_key)
        + _proto_str(4, "en")
        + _proto_str(7, "1.107.0")
        + _proto_int(9, 1)
        + _proto_str(10, session_id)
    )


# ─── Language Server Auto-Detection ──────────────────────────────────────────


def _detect_language_server() -> tuple[int, str]:
    """Detect running Windsurf language server port and CSRF token.

    Returns:
        (port, csrf_token) — port=0 if not detected.
    """
    try:
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            if "language_server_macos_arm" not in line or "grep" in line:
                continue
            csrf_token = ""
            m = re.search(r"--csrf_token\s+(\S+)", line)
            if m:
                csrf_token = m.group(1)
            parts = line.split()
            if len(parts) >= 2:
                pid = parts[1]
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


def _ls_heartbeat(port: int, csrf: str) -> bool:
    """Quick heartbeat check to verify LS is responding."""
    try:
        r = requests.post(
            f"http://127.0.0.1:{port}{LS_HEARTBEAT}",
            headers={"Content-Type": "application/json", "x-codeium-csrf-token": csrf},
            json={},
            timeout=3,
        )
        return r.status_code == 200
    except Exception:
        return False


class WindsurfLLM(BaseChatModel):
    """Windsurf/Codeium LLM provider.

    Supports three modes (auto-selected in order of preference):
    1. Local LS mode: Communicates with the running Windsurf IDE language server
       via Connect-RPC on localhost. Uses the same auth as the IDE.
    2. Proxy mode: Sends OpenAI-compatible requests to a local proxy
       (windsurf_proxy.py on port 8085) which translates to Windsurf Connect-RPC API.
    3. Direct mode: Sends Connect-RPC requests directly to Windsurf API server.

    Only FREE tier models are available to avoid premium credit consumption.

    Environment variables:
        WINDSURF_API_KEY     - Windsurf API key (sk-ws-...)
        WINDSURF_MODEL       - Default model name
        WINDSURF_PROXY_URL   - Proxy URL (default: http://127.0.0.1:8085)
        WINDSURF_DIRECT      - Set to "true" to bypass proxy and call API directly
        WINDSURF_INSTALL_ID  - Installation ID (from Windsurf DB)
        WINDSURF_API_SERVER  - API server URL (default: https://server.self-serve.windsurf.com)
        WINDSURF_LS_PORT     - Language server port (auto-detected if not set)
        WINDSURF_LS_CSRF     - Language server CSRF token (auto-detected if not set)
        WINDSURF_MODE        - Force mode: "local", "proxy", or "direct"
    """

    model_name: str | None = None
    vision_model_name: str | None = None
    api_key: str | None = None
    max_tokens: int = 4096
    proxy_url: str = "http://127.0.0.1:8085"
    direct_mode: bool = False
    api_server: str = "https://server.self-serve.windsurf.com"
    installation_id: str = ""
    _tools: list[Any] | None = PrivateAttr(default=None)
    # Local LS mode fields
    ls_port: int = 0
    ls_csrf: str = ""
    _mode: str = PrivateAttr(default="proxy")  # "local", "proxy", "direct", or "cascade"
    _is_test_mode: bool = PrivateAttr(default=False)

    def __init__(
        self,
        model_name: str | None = None,
        vision_model_name: str | None = None,
        api_key: str | None = None,
        max_tokens: int | None = None,
        proxy_url: str | None = None,
        direct_mode: bool | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        # STRICT CONFIGURATION: No hardcoded defaults
        from src.brain.config.config_loader import config

        # Model
        self.model_name = model_name or os.getenv("WINDSURF_MODEL") or config.get("models.default")
        if not self.model_name:
            # Absolute fallback if config is broken
            self.model_name = WINDSURF_DEFAULT_MODEL

        # vision_model_name accepted for CopilotLLM API compatibility (Windsurf models don't support vision)
        # Use config if available as fallback for compatibility
        self.vision_model_name = vision_model_name or config.get("models.vision")

        # Validate model is known
        if self.model_name not in WINDSURF_MODELS:
            available = ", ".join(sorted(WINDSURF_MODELS.keys()))
            print(
                f"Warning: unknown Windsurf model '{self.model_name}'. Available: {available}",
                file=sys.stderr,
            )

        self.max_tokens = max_tokens or 4096

        # API key — allow dummy/test keys for testing without real API
        ws_key = api_key or os.getenv("WINDSURF_API_KEY")
        if not ws_key:
            raise RuntimeError(
                "WINDSURF_API_KEY environment variable must be set. "
                "Run: python tools/get_windsurf_token.py --key-only"
            )
        self.api_key = ws_key
        self._is_test_mode = str(ws_key).lower() in {"dummy", "test", "test-key"}

        # Installation ID
        self.installation_id = os.getenv("WINDSURF_INSTALL_ID", "")

        # Proxy URL
        self.proxy_url = proxy_url or os.getenv("WINDSURF_PROXY_URL", "http://127.0.0.1:8085")

        # API server for direct mode
        self.api_server = os.getenv("WINDSURF_API_SERVER", "https://server.self-serve.windsurf.com")

        # Mode selection
        forced_mode = os.getenv("WINDSURF_MODE", "").lower()
        if forced_mode in ("cascade", "local", "proxy", "direct"):
            self._mode = forced_mode
        elif direct_mode or os.getenv("WINDSURF_DIRECT", "").lower() == "true":
            self._mode = "direct"
        else:
            self._mode = "proxy"

        # Auto-detect local LS if mode needs it or auto-detection
        ls_available = False
        if self._mode in ("cascade", "local") or forced_mode == "":
            # Try session watcher first (O(1), no subprocess)
            ls_port = 0
            ls_csrf = ""
            if _SESSION_WATCHER_AVAILABLE:
                watcher = WindsurfSessionWatcher.instance()
                watcher.start()
                w_port, w_csrf, _ = watcher.get_session()
                if w_port and w_csrf:
                    ls_port = w_port
                    ls_csrf = w_csrf

            # Fallback to env vars and manual detection
            if not ls_port or not ls_csrf:
                ls_port = int(os.getenv("WINDSURF_LS_PORT", "0"))
                ls_csrf = os.getenv("WINDSURF_LS_CSRF", "")
            if not ls_port or not ls_csrf:
                detected_port, detected_csrf = _detect_language_server()
                if not ls_port:
                    ls_port = detected_port
                if not ls_csrf:
                    ls_csrf = detected_csrf
            if ls_port and ls_csrf and _ls_heartbeat(ls_port, ls_csrf):
                self.ls_port = ls_port
                self.ls_csrf = ls_csrf
                ls_available = True
                # Prefer cascade mode (uses Cascade quota, bypasses Chat API block)
                if forced_mode == "cascade":
                    self._mode = "cascade"
                elif forced_mode == "":
                    if (self.model_name or "") in CASCADE_MODEL_MAP:
                        self._mode = "cascade"
                    else:
                        self._mode = "local"
                else:
                    self._mode = "local"

        # Degrade gracefully: if cascade/local requested but LS not available
        if self._mode in ("cascade", "local") and not ls_available:
            print(
                f"Warning: WINDSURF_MODE={forced_mode} but Windsurf LS not available, "
                f"falling back to proxy mode",
                file=sys.stderr,
            )
            self._mode = "proxy"

        self.direct_mode = self._mode == "direct"

    @property
    def _llm_type(self) -> str:
        return "windsurf-chat"

    def bind_tools(self, tools: Any, **kwargs: Any) -> WindsurfLLM:
        if isinstance(tools, list):
            self._tools = tools
        else:
            self._tools = [tools]
        return self

    def _has_image(self, messages: list[BaseMessage]) -> bool:
        """Check if any message contains image content."""
        for m in messages:
            c = getattr(m, "content", None)
            if isinstance(c, list):
                for item in c:
                    if isinstance(item, dict) and item.get("type") == "image_url":
                        return True
        return False

    # ─── Message Formatting ──────────────────────────────────────────────

    def _build_openai_payload(self, messages: list[BaseMessage], stream: bool = False) -> dict:
        """Build OpenAI-compatible payload for proxy mode."""
        formatted_messages = []
        system_content = "You are a helpful AI assistant."

        # Tool instructions
        tool_instructions = ""
        if self._tools:
            tools_desc_lines: list[str] = []
            for tool in self._tools:
                if isinstance(tool, dict):
                    name = tool.get("name", "tool")
                    description = tool.get("description", "")
                else:
                    name = getattr(tool, "name", getattr(tool, "__name__", "tool"))
                    description = getattr(tool, "description", "")
                if name:
                    tools_desc_lines.append(f"- {name}: {description}")
            tools_desc = "\n".join(tools_desc_lines)

            tool_instructions = (
                "CRITICAL: If you need to use tools, you MUST respond ONLY in the following JSON format. "
                "Any other text outside the JSON will cause a system error.\n\n"
                "AVAILABLE TOOLS:\n"
                f"{tools_desc}\n\n"
                "JSON FORMAT (ONLY IF USING TOOLS):\n"
                "{\n"
                '  "tool_calls": [\n'
                '    { "name": "tool_name", "args": { ... } }\n'
                "  ],\n"
                '  "final_answer": "Immediate feedback in UKRAINIAN (e.g., \'Зараз перевірю...\')."\n'
                "}\n\n"
                "If text response is enough (no tools needed), answer normally in Ukrainian.\n"
                "If you ALREADY checked results (ToolMessages provided), provide a final summary in plain text.\n"
            )

        for m in messages:
            role = "user"
            if isinstance(m, SystemMessage):
                role = "system"
                content = m.content if isinstance(m.content, str) else str(m.content)
                system_content = content + ("\n\n" + tool_instructions if tool_instructions else "")
                continue
            if isinstance(m, AIMessage):
                role = "assistant"
            elif isinstance(m, ToolMessage):
                # ToolMessage results → user role with prefix for models without native tool support
                role = "user"
                tool_name = getattr(m, "name", "tool")
                content = m.content if isinstance(m.content, str) else str(m.content)
                formatted_messages.append(
                    {"role": role, "content": f"[Tool Result: {tool_name}]: {content}"}
                )
                continue
            elif isinstance(m, HumanMessage):
                role = "user"

            content = m.content
            # Windsurf free models don't support vision — strip images
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "image_url":
                            text_parts.append(
                                "[Image content not supported by Windsurf free models]"
                            )
                    elif isinstance(item, str):
                        text_parts.append(item)
                content = " ".join(text_parts)

            formatted_messages.append({"role": role, "content": content})

        final_messages = [{"role": "system", "content": system_content}, *formatted_messages]

        return {
            "model": self.model_name,
            "messages": final_messages,
            "temperature": 0.1,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }

    def _build_connect_rpc_payload(self, messages: list[BaseMessage]) -> dict:
        """Build Connect-RPC payload for Windsurf RawGetChatMessage.

        Proto schema (RawGetChatMessageRequest):
          f1: Metadata, f2: repeated ChatMessage, f5: chatModelName
        ChatMessage:
          f1: messageId, f2: source(enum), f3: Timestamp, f4: conversationId,
          f5: ChatMessageIntent { f1: IntentGeneric { f1: text } }
        """
        now_rfc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conv_id = str(uuid.uuid4())
        chat_messages = []

        for m in messages:
            if isinstance(m, SystemMessage):
                source = SOURCE_SYSTEM
            elif isinstance(m, AIMessage):
                source = SOURCE_ASSISTANT
            else:
                source = SOURCE_USER

            content = m.content
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif isinstance(item, str):
                        text_parts.append(item)
                content = " ".join(text_parts)

            chat_messages.append(
                {
                    "messageId": str(uuid.uuid4()),
                    "source": source,
                    "timestamp": now_rfc,
                    "conversationId": conv_id,
                    "intent": {"generic": {"text": content}},
                }
            )

        model_id = WINDSURF_MODELS.get(
            self.model_name or WINDSURF_DEFAULT_MODEL,
            self.model_name or WINDSURF_DEFAULT_MODEL,
        )

        return {
            "chatMessages": chat_messages,
            "metadata": self._build_ls_metadata(),
            "chatModelName": model_id,
        }

    # ─── Proxy Mode ──────────────────────────────────────────────────────

    def _call_proxy(self, payload: dict) -> dict:
        """Send OpenAI-compatible request to local proxy with retry logic."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            retry=retry_if_exception_type(
                (requests.exceptions.Timeout, requests.exceptions.ConnectionError),
            ),
            reraise=True,
        )
        def _do_post() -> requests.Response:
            return requests.post(
                f"{self.proxy_url}/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=300,
            )

        response = _do_post()
        response.raise_for_status()
        return response.json()

    async def _call_proxy_async(self, payload: dict) -> dict:
        """Async OpenAI-compatible request to local proxy with retry logic."""
        import tenacity

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        @tenacity.retry(
            stop=tenacity.stop_after_attempt(3),
            wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
            retry=tenacity.retry_if_exception_type(
                (
                    httpx.ConnectError,
                    httpx.TimeoutException,
                    httpx.NetworkError,
                    httpx.RemoteProtocolError,
                ),
            ),
            reraise=True,
        )
        async def _do_post(client: httpx.AsyncClient) -> httpx.Response:
            return await client.post(
                f"{self.proxy_url}/v1/chat/completions",
                headers=headers,
                json=payload,
            )

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0)) as client:
            response = await _do_post(client)
            response.raise_for_status()
            return response.json()

    # ─── Local Language Server Mode ────────────────────────────────────────

    def _build_ls_metadata(self) -> dict:
        """Build metadata dict for LS requests."""
        return {
            "ideName": "windsurf",
            "ideVersion": "1.107.0",
            "extensionVersion": "1.9552.21",
            "locale": "en",
            "sessionId": f"atlastrinity-{os.getpid()}",
            "requestId": str(int(time.time())),
            "apiKey": self.api_key,
        }

    @staticmethod
    def _make_envelope(payload_dict: dict) -> bytes:
        """Wrap JSON payload in Connect streaming envelope (flags + length + data)."""
        payload_bytes = json.dumps(payload_dict).encode("utf-8")
        return struct.pack(">BI", 0, len(payload_bytes)) + payload_bytes

    @staticmethod
    def _parse_streaming_frames(data: bytes) -> tuple[str, str | None]:
        """Parse Connect-RPC streaming frames.

        Returns:
            (result_text, error_message_or_None)
        """
        result_text = ""
        error_msg = None
        offset = 0
        while offset + 5 <= len(data):
            flags = data[offset]
            frame_len = int.from_bytes(data[offset + 1 : offset + 5], "big")
            frame_data = data[offset + 5 : offset + 5 + frame_len]
            offset += 5 + frame_len
            try:
                fj = json.loads(frame_data)
            except json.JSONDecodeError:
                continue
            if flags == 0x02:  # Trailer
                err = fj.get("error", {})
                if err:
                    error_msg = f"{err.get('code', 'unknown')}: {err.get('message', '')}"
                continue
            # Data frame
            dm = fj.get("deltaMessage", {})
            if dm:
                if dm.get("isError"):
                    error_msg = dm.get("text", "unknown error")
                else:
                    result_text += dm.get("text", "")
            elif "text" in fj:
                result_text += fj["text"]
            elif "content" in fj:
                result_text += fj["content"]
            elif "chatMessage" in fj:
                result_text += fj["chatMessage"].get("content", "")
        return result_text, error_msg

    def _refresh_ls_connection(self) -> bool:
        """Re-detect LS port/CSRF if the current connection is stale."""
        # Fast path: current connection is still alive
        if self.ls_port and self.ls_csrf and _ls_heartbeat(self.ls_port, self.ls_csrf):
            return True

        # Try session watcher (O(1), no subprocess)
        if _SESSION_WATCHER_AVAILABLE:
            watcher = WindsurfSessionWatcher.instance()
            session = watcher.force_refresh()
            if session and session.is_valid:
                self.ls_port = session.port
                self.ls_csrf = session.csrf
                if session.api_key:
                    self.api_key = session.api_key
                return True

        # Fallback: manual detection
        detected_port, detected_csrf = _detect_language_server()
        if detected_port and detected_csrf and _ls_heartbeat(detected_port, detected_csrf):
            self.ls_port = detected_port
            self.ls_csrf = detected_csrf
            return True
        return False

    def _call_local_ls(self, payload: dict) -> str:
        """Send chat request via local language server's RawGetChatMessage.

        The payload should already be in Connect-RPC format from
        _build_connect_rpc_payload (with chatMessages, metadata, chatModelName).
        """
        if not self._refresh_ls_connection():
            raise RuntimeError("Windsurf language server not available")

        envelope = self._make_envelope(payload)
        headers = {
            "Content-Type": "application/connect+json",
            "Connect-Protocol-Version": "1",
            "x-codeium-csrf-token": self.ls_csrf,
        }

        response = requests.post(
            f"http://127.0.0.1:{self.ls_port}{LS_RAW_CHAT}",
            headers=headers,
            data=envelope,
            timeout=300,
            stream=True,
        )
        data = b""
        for chunk in response.iter_content(chunk_size=4096):
            data += chunk

        result_text, error_msg = self._parse_streaming_frames(data)
        if error_msg:
            raise RuntimeError(f"Windsurf LS error: {error_msg}")
        return result_text

    async def _call_local_ls_async(self, payload: dict) -> str:
        """Async version of local LS call."""
        if not self._refresh_ls_connection():
            raise RuntimeError("Windsurf language server not available")

        envelope = self._make_envelope(payload)
        headers = {
            "Content-Type": "application/connect+json",
            "Connect-Protocol-Version": "1",
            "x-codeium-csrf-token": self.ls_csrf,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0)) as client:
            response = await client.post(
                f"http://127.0.0.1:{self.ls_port}{LS_RAW_CHAT}",
                headers=headers,
                content=envelope,
            )

        result_text, error_msg = self._parse_streaming_frames(response.content)
        if error_msg:
            raise RuntimeError(f"Windsurf LS error: {error_msg}")
        return result_text

    # ─── Direct Mode (Connect-RPC) ───────────────────────────────────────

    def _call_direct(self, payload: dict) -> str:
        """Send Connect-RPC request directly to Windsurf API."""
        url = f"{self.api_server}/exa.api_server_pb.ApiServerService/GetChatMessage"
        headers = {
            "Content-Type": "application/connect+json",
            "Connect-Protocol-Version": "1",
            "Authorization": f"Basic {self.api_key}",
        }
        response = requests.post(url, headers=headers, json=payload, timeout=300)

        data = response.content
        if not data:
            raise RuntimeError("Empty response from Windsurf API")

        result_text, error_msg = self._parse_streaming_frames(data)
        if error_msg:
            raise RuntimeError(f"Windsurf API error: {error_msg}")
        return result_text

    async def _call_direct_async(self, payload: dict) -> str:
        """Async Connect-RPC request to Windsurf API."""
        url = f"{self.api_server}/exa.api_server_pb.ApiServerService/GetChatMessage"
        headers = {
            "Content-Type": "application/connect+json",
            "Connect-Protocol-Version": "1",
            "Authorization": f"Basic {self.api_key}",
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0)) as client:
            response = await client.post(url, headers=headers, json=payload)

        data = response.content
        if not data:
            raise RuntimeError("Empty response from Windsurf API")

        result_text, error_msg = self._parse_streaming_frames(data)
        if error_msg:
            raise RuntimeError(f"Windsurf API error: {error_msg}")
        return result_text

    # ─── Cascade Mode (gRPC via local LS) ────────────────────────────────

    def _call_cascade(self, messages: list[BaseMessage]) -> str:
        """Send chat via Cascade pipeline through the local Language Server.

        Flow:
          1. StartCascade → cascadeId
          2. StreamCascadeReactiveUpdates (background, protocol_version=1)
          3. QueueCascadeMessage (items + cascade_config with model)
          4. InterruptWithQueuedMessage → triggers AI processing
          5. Collect AI response text from stream frames
        """
        if not self._refresh_ls_connection():
            raise RuntimeError("Windsurf language server not available")

        session_id = f"atlastrinity-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        meta = _build_metadata_proto(self.api_key or "", session_id)
        grpc_md = (("x-codeium-csrf-token", self.ls_csrf),)

        channel = grpc.insecure_channel(f"127.0.0.1:{self.ls_port}")
        try:
            grpc.channel_ready_future(channel).result(timeout=10)
        except grpc.FutureTimeoutError:
            channel.close()
            raise RuntimeError("Cannot connect to Windsurf LS gRPC")

        _id = lambda x: x  # noqa: E731
        try:
            # Step 1: StartCascade
            start_rpc = channel.unary_unary(
                f"{_GRPC_SVC}StartCascade",
                request_serializer=_id,
                response_deserializer=_id,
            )
            resp = start_rpc(_proto_msg(1, meta), metadata=grpc_md, timeout=15)
            cascade_id = _proto_extract_string(resp, 1)
            if not cascade_id:
                raise RuntimeError("StartCascade returned no cascadeId")

            # Step 2: Start streaming reactive updates
            stream_rpc = channel.unary_stream(
                f"{_GRPC_SVC}StreamCascadeReactiveUpdates",
                request_serializer=_id,
                response_deserializer=_id,
            )
            stream_req = _proto_int(1, 1) + _proto_str(2, cascade_id)
            raw_frames: list[bytes] = []
            stream_done = threading.Event()

            def _listen() -> None:
                try:
                    for frame in stream_rpc(
                        stream_req, metadata=grpc_md, timeout=CASCADE_TIMEOUT + 30
                    ):
                        raw_frames.append(frame)
                except grpc.RpcError:
                    pass
                stream_done.set()

            listener = threading.Thread(target=_listen, daemon=True)
            listener.start()
            time.sleep(0.3)

            # Step 3: QueueCascadeMessage
            # Combine all messages into a single user prompt
            tool_instructions = ""
            if self._tools:
                tools_desc_lines: list[str] = []
                for tool in self._tools:
                    if isinstance(tool, dict):
                        name = tool.get("name", "tool")
                        description = tool.get("description", "")
                    else:
                        name = getattr(tool, "name", getattr(tool, "__name__", "tool"))
                        description = getattr(tool, "description", "")
                    if name:
                        tools_desc_lines.append(f"- {name}: {description}")
                tools_desc = "\n".join(tools_desc_lines)

                tool_instructions = (
                    "CRITICAL: If you need to use tools, you MUST respond ONLY in the following JSON format. "
                    "Any other text outside the JSON will cause a system error.\n\n"
                    "AVAILABLE TOOLS:\n"
                    f"{tools_desc}\n\n"
                    "JSON FORMAT (ONLY IF USING TOOLS):\n"
                    "{\n"
                    '  "tool_calls": [\n'
                    '    { "name": "tool_name", "args": { ... } }\n'
                    "  ],\n"
                    '  "final_answer": "Immediate feedback in UKRAINIAN (e.g., \'Зараз перевірю...\')."\n'
                    "}\n\n"
                    "If text response is enough (no tools needed), answer normally in Ukrainian.\n"
                    "If you ALREADY checked results (ToolMessages provided), provide a final summary in plain text.\n"
                )

            prompt_parts: list[str] = []
            for m in messages:
                content = m.content
                if isinstance(content, list):
                    text_parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif isinstance(item, str):
                            text_parts.append(item)
                    content = " ".join(text_parts)
                if isinstance(m, SystemMessage):
                    system_content = str(content)
                    if tool_instructions:
                        system_content = system_content + "\n\n" + tool_instructions
                    prompt_parts.insert(0, f"[System]: {system_content}")
                elif isinstance(m, AIMessage):
                    prompt_parts.append(f"[Assistant]: {content}")
                else:
                    prompt_parts.append(content)
            user_text = "\n\n".join(prompt_parts)

            # Resolve model UID for Cascade
            from src.brain.config.config_loader import config

            fallback_model = config.get("models.default") or CASCADE_DEFAULT_MODEL
            model_uid = CASCADE_MODEL_MAP.get(self.model_name or "", fallback_model)

            queue_rpc = channel.unary_unary(
                f"{_GRPC_SVC}QueueCascadeMessage",
                request_serializer=_id,
                response_deserializer=_id,
            )
            # QueueCascadeMessageRequest: f1=metadata, f2=cascade_id,
            #   f3=items(repeated TextOrScopeItem), f5=cascade_config
            # TextOrScopeItem: oneof chunk { f1=text(str) }
            # CascadeConfig.f1=PlannerConfig, PlannerConfig.f34=plan_model_uid, f35=requested_model_uid
            # TextOrScopeItem: oneof chunk { f1=text(str) }
            # CascadeConfig.f1=PlannerConfig, PlannerConfig.f34=plan_model_uid, f35=requested_model_uid
            item_proto = _proto_str(1, user_text)
            
            # PlannerConfig
            # 34: plan_model_uid, 35: requested_model_uid
            planner_parts = [
                _proto_str(34, model_uid),
                _proto_str(35, model_uid),
                # Action Phase Flags from main.swift
                _proto_int(11, 1),  # enable_cortex_reasoning
                _proto_int(12, 1),  # enable_action_phase
                _proto_int(13, 1),  # enable_tool_execution
                _proto_int(14, 1),  # enable_file_operations
                _proto_int(15, 1),  # enable_autonomous_execution
            ]

            # CortexConfig (Field 20 of PlannerConfig)
            cortex_config = (
                _proto_int(1, 1)  # enable_autonomous_tools
                + _proto_int(2, 1)  # enable_file_creation
                + _proto_int(3, 1)  # enable_file_modification
                + _proto_int(4, 1)  # enable_workspace_scoped_actions
                + _proto_int(5, 180) # action_timeout_seconds
            )
            planner_parts.append(_proto_msg(20, cortex_config))
            
            planner_proto = b"".join(planner_parts)
            cascade_config = _proto_msg(1, planner_proto)

            queue_req = (
                _proto_msg(1, meta)
                + _proto_str(2, cascade_id)
                + _proto_msg(3, item_proto)
                + _proto_msg(5, cascade_config)
            )
            queue_resp = queue_rpc(queue_req, metadata=grpc_md, timeout=15)
            queue_id = _proto_extract_string(queue_resp, 1)
            if not queue_id:
                raise RuntimeError("QueueCascadeMessage returned no queueId")

            # Step 4: InterruptWithQueuedMessage → triggers processing
            interrupt_rpc = channel.unary_unary(
                f"{_GRPC_SVC}InterruptWithQueuedMessage",
                request_serializer=_id,
                response_deserializer=_id,
            )
            interrupt_req = (
                _proto_msg(1, meta) + _proto_str(2, cascade_id) + _proto_str(3, queue_id)
            )
            interrupt_rpc(interrupt_req, metadata=grpc_md, timeout=15)

            # Step 5: Wait for AI response in stream
            prev_count = 0
            stable_ticks = 0
            elapsed_no_frames = 0
            for _ in range(CASCADE_TIMEOUT // 2):
                time.sleep(2)
                cur = len(raw_frames)
                # Early abort: if no frames at all after CASCADE_EARLY_ABORT seconds
                if cur == 0:
                    elapsed_no_frames += 2
                    if elapsed_no_frames >= CASCADE_EARLY_ABORT:
                        raise RuntimeError(
                            f"Cascade stream timeout: no frames received after {CASCADE_EARLY_ABORT}s"
                        )
                elif cur > 3 and cur == prev_count:
                    stable_ticks += 1
                    if stable_ticks >= 3:
                        break
                else:
                    stable_ticks = 0
                prev_count = cur

            # Step 6: Extract AI response text from stream frames
            return self._extract_cascade_response(raw_frames, user_text)

        finally:
            channel.close()

    @staticmethod
    def _extract_proto_strings_at_field(data: bytes, target_fn: int) -> list[str]:
        """Extract all string values at a specific proto field number (top-level only)."""
        results: list[str] = []
        offset = 0
        while offset < len(data):
            tag = 0
            shift = 0
            while offset < len(data):
                b = data[offset]
                offset += 1
                tag |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80):
                    break
            fn = tag >> 3
            wt = tag & 0x07
            if fn == 0 or fn > 200:
                break
            if wt == 0:
                while offset < len(data) and data[offset] & 0x80:
                    offset += 1
                if offset < len(data):
                    offset += 1
            elif wt == 2:
                ln = 0
                s = 0
                while offset < len(data):
                    b = data[offset]
                    offset += 1
                    ln |= (b & 0x7F) << s
                    s += 7
                    if not (b & 0x80):
                        break
                payload = data[offset : offset + ln]
                offset += ln
                if fn == target_fn:
                    try:
                        text = payload.decode("utf-8")
                        results.append(text)
                    except UnicodeDecodeError:
                        pass
            elif wt == 1:
                offset += 8
            elif wt == 5:
                offset += 4
            else:
                break
        return results

    @staticmethod
    def _check_cascade_errors(frames: list[bytes]):
        """Check for known error messages in Cascade frames."""
        for frame in frames:
            if b"permission_denied" in frame or b"not enough credits" in frame:
                raise RuntimeError("Windsurf Cascade: not enough credits (quota exhausted)")
            if b"resource_exhausted" in frame:
                raise RuntimeError("Windsurf Cascade: resource exhausted (quota limit)")

    @staticmethod
    def _find_proto_candidates(data: bytes, target_tags: tuple[int, ...]) -> list[str]:
        """Scan for length-delimited strings at target field tags (wire type 2)."""
        results: list[str] = []
        offset = 0
        while offset < len(data):
            try:
                # Read tag (varint)
                tag = 0
                shift = 0
                while offset < len(data):
                    b = data[offset]
                    offset += 1
                    tag |= (b & 0x7F) << shift
                    shift += 7
                    if not (b & 0x80):
                        break

                fn = tag >> 3
                if fn == 0:
                    continue

                wt = tag & 0x07
                if wt == 0:  # Varint
                    while offset < len(data) and data[offset] & 0x80:
                        offset += 1
                    if offset < len(data):
                        offset += 1
                elif wt == 2:  # Length-delimited
                    ln = 0
                    s = 0
                    while offset < len(data):
                        b = data[offset]
                        offset += 1
                        ln |= (b & 0x7F) << s
                        s += 7
                        if not (b & 0x80):
                            break
                    if ln < 0 or ln > len(data) - offset:
                        continue
                    payload = data[offset : offset + ln]
                    offset += ln
                    if tag in target_tags:
                        try:
                            results.append(payload.decode("utf-8"))
                        except UnicodeDecodeError:
                            pass
                elif wt == 1:  # 64-bit
                    offset += 8
                elif wt == 5:  # 32-bit
                    offset += 4
                elif wt in {3, 4}:  # Start/End group (deprecated)
                    continue
                else:
                    break
            except Exception:
                break
        return results

    @staticmethod
    def _parse_proto_length(window: bytes, offset: int) -> tuple[int, int]:
        """Parse varint length from proto window."""
        ln = 0
        shift = 0
        while offset < len(window):
            b = window[offset]
            offset += 1
            ln |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break
        return ln, offset

    @staticmethod
    def _extract_cascade_response(frames: list[bytes], user_text: str) -> str:
        """Extract the AI assistant's response text from Cascade stream frames.

        Strategy:
        1. Check for error messages (permission_denied, not enough credits)
        2. Find the bot response near bot-<uuid> marker:
           The AI response text is encoded at proto field 15 (tag 0x7A,
           wire type 2) inside nested sub-messages that also contain
           the bot-<uuid> identifier.  The response appears in items
           structured as: 0a [sub-msg] → 08 [varint] 12 [sub-msg] → 7a [len] text.
           We also scan field 5 (0x2A) and field 4 (0x22) as fallback.
        3. Fallback: search for readable text in the last frames.
        """
        # Phase 1: Check for errors in all frames
        for frame in frames:
            if b"permission_denied" in frame or b"not enough credits" in frame:
                raise RuntimeError("Windsurf Cascade: not enough credits (quota exhausted)")
            if b"resource_exhausted" in frame:
                raise RuntimeError("Windsurf Cascade: resource exhausted (quota limit)")

        # Phase 2: Find bot response using proto byte pattern
        # Target tags: 0x7A = field 15 wire type 2, 0x2A = field 5, 0x22 = field 4
        target_tags = (0x7A, 0x2A, 0x22)
        for i in range(len(frames) - 1, 1, -1):  # Search backwards
            frame = frames[i]
            bot_idx = frame.find(b"bot-")
            if bot_idx < 0:
                continue

            # Search in a window before bot- marker
            search_start = max(0, bot_idx - 2000)
            window = frame[search_start:bot_idx]

            # Scan for length-delimited strings at target field tags
            candidates = WindsurfLLM._find_proto_candidates(window, target_tags)

            # Filter candidates: skip UUIDs, model names, noise, binary garbage
            filtered: list[str] = []
            user_stripped = user_text.strip()
            for c in candidates:
                c = c.strip()
                if not c:
                    continue
                # Reject strings with control characters (binary proto fragments)
                if any(ord(ch) < 32 and ch not in "\n\r\t" for ch in c):
                    continue
                if c.count("-") >= 4 and len(c) < 50:
                    continue  # UUID
                if c.startswith(("MODEL_", "file://", "http", "bot-")):
                    continue
                if user_stripped and c == user_stripped:
                    continue  # Exact user input echo
                filtered.append(c)

            if filtered:
                # Return the longest printable candidate (dedup by content)
                return max(filtered, key=len)

        # Phase 3: Fallback - look for readable text in the last frames
        for i in range(len(frames) - 1, max(1, len(frames) - 5), -1):
            strings = _proto_find_strings(frames[i], min_len=5)
            for s in strings:
                s = s.strip()
                if (
                    len(s) > 2
                    and s.count("-") < 3
                    and not s.startswith(("file://", "http", "MODEL_", "{", "<"))
                ):
                    return s

        return ""

    # ─── Result Processing ───────────────────────────────────────────────

    def _process_openai_result(self, data: dict, messages: list[BaseMessage]) -> ChatResult:
        """Process OpenAI-compatible response (from proxy)."""
        if not data.get("choices"):
            return ChatResult(
                generations=[
                    ChatGeneration(message=AIMessage(content="[WINDSURF] No response choice.")),
                ],
            )

        content = data["choices"][0]["message"]["content"]
        return self._process_content(content)

    def _process_content(self, content: str) -> ChatResult:
        """Process raw content string, extracting tool calls if needed."""
        if not self._tools:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

        tool_calls = []
        final_answer = ""
        try:
            json_start = content.find("{")
            json_end = content.rfind("}")
            if json_start >= 0 and json_end >= 0:
                parse_candidate = content[json_start : json_end + 1]
                parsed = json.loads(parse_candidate)
            else:
                parsed = json.loads(content)

            if isinstance(parsed, dict):
                calls = parsed.get("tool_calls") or []
                for idx, call in enumerate(calls):
                    tool_calls.append(
                        {
                            "id": f"call_{idx}",
                            "type": "tool_call",
                            "name": call.get("name"),
                            "args": call.get("args") or {},
                        },
                    )
                final_answer = str(parsed.get("final_answer", ""))
        except Exception:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])

        if tool_calls:
            return ChatResult(
                generations=[
                    ChatGeneration(message=AIMessage(content=final_answer, tool_calls=tool_calls)),
                ],
            )
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=final_answer or content))],
        )

    # ─── Test / Dummy Mode ─────────────────────────────────────────────

    def _generate_test_response(self, messages: list[BaseMessage]) -> ChatResult:
        """Generate synthetic response for test/dummy mode without real API calls."""
        # Extract last user message content for echo-style test response
        user_content = ""
        for m in reversed(messages):
            if isinstance(m, HumanMessage):
                c = m.content
                if isinstance(c, list):
                    parts = []
                    for item in c:
                        if isinstance(item, dict) and item.get("type") == "text":
                            parts.append(item.get("text", ""))
                        elif isinstance(item, str):
                            parts.append(item)
                    user_content = " ".join(parts)
                else:
                    user_content = str(c)
                break

        # If tools are bound, return a synthetic tool call response
        if self._tools and user_content:
            test_content = f"[WINDSURF TEST] Received: {user_content}"
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content=test_content))],
            )

        content = f"[WINDSURF TEST] Echo: {user_content}" if user_content else "[WINDSURF TEST] OK"
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=content))],
        )

    def _internal_text_invoke(self, messages: list[BaseMessage]) -> AIMessage:
        """Internal text-only invoke for fallback scenarios (no image processing)."""
        try:
            result = self._generate(messages)
            if result.generations:
                gen = result.generations[0]
                if hasattr(gen, "message"):
                    return gen.message  # type: ignore[return-value]
            return AIMessage(content="[No response generated]")
        except Exception as e:
            return AIMessage(content=f"[Internal invoke error] {e}")

    # ─── LangChain Interface ─────────────────────────────────────────────

    def _call_mode(self, mode: str, messages: list[BaseMessage]) -> ChatResult:
        """Execute a single mode attempt and return ChatResult."""
        if mode == "cascade":
            try:
                content = self._call_cascade(messages)
                return self._process_content(content)
            except RuntimeError as e:
                if "not enough credits" in str(e).lower() and self._refresh_ls_connection():
                    payload = self._build_connect_rpc_payload(messages)
                    content = self._call_local_ls(payload)
                    return self._process_content(content)
                raise
        elif mode == "local":
            payload = self._build_connect_rpc_payload(messages)
            content = self._call_local_ls(payload)
            return self._process_content(content)
        elif mode == "direct":
            payload = self._build_connect_rpc_payload(messages)
            content = self._call_direct(payload)
            return self._process_content(content)
        else:  # proxy
            payload = self._build_openai_payload(messages)
            data = self._call_proxy(payload)
            return self._process_openai_result(data, messages)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,  # noqa: ARG002
        **kwargs: Any,
    ) -> ChatResult:
        """Synchronous generation with automatic mode fallback."""
        # Test/dummy mode: return synthetic response without real API calls
        if self._is_test_mode:
            return self._generate_test_response(messages)

        # Try primary mode, then fallback chain
        modes_to_try = [self._mode, *_FALLBACK_CHAIN.get(self._mode, [])]
        last_error: Exception | None = None

        for mode in modes_to_try:
            # Skip LS-dependent modes if LS is not available
            if mode in ("cascade", "local") and not (self.ls_port and self.ls_csrf):
                continue
            try:
                result = self._call_mode(mode, messages)
                if mode != self._mode:
                    print(
                        f"Warning: Windsurf '{self._mode}' failed, succeeded via '{mode}'",
                        file=sys.stderr,
                    )
                return result
            except Exception as e:
                last_error = e
                print(
                    f"Warning: Windsurf mode '{mode}' failed: {e}",
                    file=sys.stderr,
                )

        return ChatResult(
            generations=[
                ChatGeneration(message=AIMessage(content=f"[WINDSURF ERROR] {last_error}"))
            ],
        )

    async def _call_mode_async(self, mode: str, messages: list[BaseMessage]) -> ChatResult:
        """Execute a single mode attempt asynchronously."""
        import asyncio

        if mode == "cascade":
            content = await asyncio.to_thread(self._call_cascade, messages)
            return self._process_content(content)
        if mode == "local":
            payload = self._build_connect_rpc_payload(messages)
            content = await self._call_local_ls_async(payload)
            return self._process_content(content)
        if mode == "direct":
            payload = self._build_connect_rpc_payload(messages)
            content = await self._call_direct_async(payload)
            return self._process_content(content)
        # proxy
        payload = self._build_openai_payload(messages)
        data = await self._call_proxy_async(payload)
        return self._process_openai_result(data, messages)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,  # noqa: ARG002
        **kwargs: Any,
    ) -> ChatResult:
        """Asynchronous generation with automatic mode fallback."""
        # Test/dummy mode: return synthetic response without real API calls
        if self._is_test_mode:
            return self._generate_test_response(messages)

        modes_to_try = [self._mode, *_FALLBACK_CHAIN.get(self._mode, [])]
        last_error: Exception | None = None

        for mode in modes_to_try:
            if mode in ("cascade", "local") and not (self.ls_port and self.ls_csrf):
                continue
            try:
                result = await self._call_mode_async(mode, messages)
                if mode != self._mode:
                    print(
                        f"Warning: Windsurf '{self._mode}' failed, succeeded via '{mode}'",
                        file=sys.stderr,
                    )
                return result
            except Exception as e:
                last_error = e
                print(
                    f"Warning: Windsurf mode '{mode}' failed: {e}",
                    file=sys.stderr,
                )

        return ChatResult(
            generations=[
                ChatGeneration(message=AIMessage(content=f"[WINDSURF ERROR] {last_error}"))
            ],
        )

    def _call_mode_stream(
        self, mode: str, messages: list[BaseMessage], on_delta: Callable[[str], None] | None = None
    ) -> str:
        """Execute a single mode for streaming, returning raw content string."""
        if mode == "cascade":
            try:
                return self._call_cascade(messages)
            except RuntimeError as e:
                if "not enough credits" in str(e).lower() and self._refresh_ls_connection():
                    payload = self._build_connect_rpc_payload(messages)
                    return self._call_local_ls(payload)
                raise
        elif mode == "local":
            payload = self._build_connect_rpc_payload(messages)
            return self._call_local_ls(payload)
        elif mode == "direct":
            payload = self._build_connect_rpc_payload(messages)
            return self._call_direct(payload)
        else:  # proxy
            payload = self._build_openai_payload(messages, stream=True)
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
            response = requests.post(
                f"{self.proxy_url}/v1/chat/completions",
                headers=headers,
                json=payload,
                stream=True,
                timeout=300,
            )
            response.raise_for_status()
            content = ""
            for line in response.iter_lines():
                if not line:
                    continue
                content = self._parse_windsurf_openai_line(line, content, on_delta)
            return content

    def invoke_with_stream(
        self,
        messages: list[BaseMessage],
        *,
        on_delta: Callable[[str], None] | None = None,
    ) -> AIMessage:
        """Streaming invoke with automatic mode fallback."""
        modes_to_try = [self._mode, *_FALLBACK_CHAIN.get(self._mode, [])]
        last_error: Exception | None = None

        for mode in modes_to_try:
            if mode in ("cascade", "local") and not (self.ls_port and self.ls_csrf):
                continue
            try:
                content = self._call_mode_stream(mode, messages, on_delta)
                if mode != self._mode:
                    print(
                        f"Warning: Windsurf '{self._mode}' failed, succeeded via '{mode}'",
                        file=sys.stderr,
                    )
                return self._build_windsurf_ai_message(content)
            except Exception as e:
                last_error = e
                print(
                    f"Warning: Windsurf stream mode '{mode}' failed: {e}",
                    file=sys.stderr,
                )

        return AIMessage(content=f"[WINDSURF ERROR] {last_error}")



    @staticmethod
    def _parse_windsurf_openai_line(
        line: bytes, content: str, on_delta: Callable[[str], None] | None
    ) -> str:
        decoded = line.decode("utf-8")
        if not decoded.startswith("data: "):
            return content
        data_str = decoded[6:]
        if data_str.strip() == "[DONE]":
            return content
        try:
            data = json.loads(data_str)
            delta = data["choices"][0].get("delta", {})
            piece = delta.get("content")
            if piece:
                content += piece
                if on_delta:
                    on_delta(piece)
        except (json.JSONDecodeError, KeyError, IndexError):
            pass
        return content

    def _build_windsurf_ai_message(self, content: str) -> AIMessage:
        tool_calls = []
        if self._tools and content:
            try:
                json_start = content.find("{")
                json_end = content.rfind("}")
                if json_start >= 0 and json_end >= 0:
                    parsed = json.loads(content[json_start : json_end + 1])
                    if isinstance(parsed, dict):
                        calls = parsed.get("tool_calls") or []
                        for idx, call in enumerate(calls):
                            name = call.get("name")
                            if name:
                                tool_calls.append(
                                    {
                                        "id": f"call_{idx}",
                                        "type": "tool_call",
                                        "name": name,
                                        "args": call.get("args") or {},
                                    }
                                )
                        final_answer = str(parsed.get("final_answer", ""))
                        if tool_calls or final_answer:
                            content = final_answer or ""
            except Exception:
                pass
        return AIMessage(content=content, tool_calls=tool_calls)
