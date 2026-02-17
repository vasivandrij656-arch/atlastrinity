"""
Windsurf Traffic Sniffer & Protocol Dumper
==========================================

Passive interceptor for Windsurf IDE <-> Language Server (Connect-RPC/gRPC) traffic.
Runs as a transparent proxy between the IDE and the local Language Server.

Two modes:
  1. LOCAL LS PROXY: Sits between IDE and local LS (http, no TLS needed)
     - Auto-detects running LS port & CSRF token
     - Binds to a new port, you point IDE at this port instead
  2. CLOUD PROXY: Sits between LS/IDE and cloud API (requires TLS CA trust)
     - For intercepting server.self-serve.windsurf.com / inference.codeium.com

Usage:
  # Auto-detect LS and start sniffer proxy on port 18080
  python scripts/windsurf_sniffer.py

  # Specify LS port manually
  python scripts/windsurf_sniffer.py --ls-port 42100 --ls-csrf <token>

  # Custom listen port
  python scripts/windsurf_sniffer.py --port 18080

  # Save full dump to file
  python scripts/windsurf_sniffer.py --dump-file /tmp/windsurf_dump.ndjson

  # Also intercept outbound cloud traffic (HTTPS, needs mitmproxy CA)
  python scripts/windsurf_sniffer.py --cloud

Environment:
  WINDSURF_LS_PORT   - Language server port (auto-detected)
  WINDSURF_LS_CSRF   - Language server CSRF token (auto-detected)

Author: AtlasTrinity Team
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import http.client
import http.server
import io
import json
import os
import re
import signal
import socketserver
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ─── Colors ──────────────────────────────────────────────────────────────────


class C:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"


# ─── Known Endpoints ─────────────────────────────────────────────────────────

KNOWN_ENDPOINTS: dict[str, dict[str, str]] = {
    # Language Server endpoints
    "/exa.language_server_pb.LanguageServerService/RawGetChatMessage": {
        "name": "RawGetChatMessage",
        "direction": "LS",
        "desc": "Chat completion (streaming)",
    },
    "/exa.language_server_pb.LanguageServerService/GetChatMessage": {
        "name": "GetChatMessage",
        "direction": "LS",
        "desc": "Chat completion",
    },
    "/exa.language_server_pb.LanguageServerService/Heartbeat": {
        "name": "Heartbeat",
        "direction": "LS",
        "desc": "Keep-alive ping",
    },
    "/exa.language_server_pb.LanguageServerService/GetCompletions": {
        "name": "GetCompletions",
        "direction": "LS",
        "desc": "Code completions (autocomplete)",
    },
    "/exa.language_server_pb.LanguageServerService/AcceptCompletion": {
        "name": "AcceptCompletion",
        "direction": "LS",
        "desc": "User accepted a completion",
    },
    "/exa.language_server_pb.LanguageServerService/GetAuthToken": {
        "name": "GetAuthToken",
        "direction": "LS",
        "desc": "Auth token request",
    },
    "/exa.language_server_pb.LanguageServerService/CheckChatCapacity": {
        "name": "CheckChatCapacity",
        "direction": "LS",
        "desc": "Check model capacity/availability",
    },
    "/exa.language_server_pb.LanguageServerService/RecordEvent": {
        "name": "RecordEvent",
        "direction": "LS",
        "desc": "Telemetry event",
    },
    # Cascade-specific endpoints
    "/exa.language_server_pb.LanguageServerService/StartChatClientRequestStream": {
        "name": "StartChatClientRequestStream",
        "direction": "LS",
        "desc": "Cascade bidi-stream (main chat)",
    },
    "/exa.language_server_pb.LanguageServerService/SoftCancel": {
        "name": "SoftCancel",
        "direction": "LS",
        "desc": "Cancel ongoing request",
    },
    # Cloud API endpoints
    "/exa.api_server_pb.ApiServerService/GetChatMessage": {
        "name": "GetChatMessage",
        "direction": "Cloud",
        "desc": "Cloud chat completion",
    },
    "/exa.api_server_pb.ApiServerService/GetUser": {
        "name": "GetUser",
        "direction": "Cloud",
        "desc": "User info / auth check",
    },
}

# Role mapping for display
ROLE_NAMES = {0: "SYSTEM", 1: "USER", 2: "ASSISTANT"}

# ─── Connect-RPC Frame Decoder ──────────────────────────────────────────────


def decode_connect_rpc_frames(data: bytes) -> list[dict]:
    """Decode Connect-RPC streaming envelope frames.

    Each frame: 1 byte flags + 4 bytes big-endian length + payload
    Flags: 0x00 = data, 0x02 = trailer/error

    Heuristic: if data starts with '{' or '[', treat as plain JSON (not enveloped).

    Returns list of decoded frame dicts.
    """
    frames = []
    offset = 0
    frame_idx = 0

    # Heuristic: plain JSON detection (first byte is '{' or '[')
    if data and data[0] in (0x7B, 0x5B):  # '{' or '['
        try:
            parsed = json.loads(data)
            frames.append(
                {
                    "index": 0,
                    "flags": -1,
                    "flags_desc": "PLAIN_JSON",
                    "raw_length": len(data),
                    "json": parsed,
                    "format": "json",
                }
            )
            return frames
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass  # Not valid JSON, try envelope parsing

    while offset + 5 <= len(data):
        flags = data[offset]
        frame_len = int.from_bytes(data[offset + 1 : offset + 5], "big")
        frame_data = data[offset + 5 : offset + 5 + frame_len]
        offset += 5 + frame_len

        frame_info: dict = {
            "index": frame_idx,
            "flags": flags,
            "flags_desc": "TRAILER" if flags == 0x02 else "DATA",
            "raw_length": frame_len,
        }

        # Try JSON decode
        try:
            parsed = json.loads(frame_data)
            frame_info["json"] = parsed
            frame_info["format"] = "json"
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Try protobuf-like binary decode
            frame_info["hex"] = frame_data[:256].hex()
            frame_info["format"] = "binary"
            # Extract readable strings from binary
            try:
                text = frame_data.decode("utf-8", errors="replace")
                readable = re.findall(r"[\x20-\x7e]{4,}", text)
                if readable:
                    frame_info["readable_strings"] = readable
            except Exception:
                pass

        frames.append(frame_info)
        frame_idx += 1

    # If no frames decoded, try plain JSON
    if not frames and data:
        try:
            parsed = json.loads(data)
            frames.append(
                {
                    "index": 0,
                    "flags": -1,
                    "flags_desc": "PLAIN_JSON",
                    "raw_length": len(data),
                    "json": parsed,
                    "format": "json",
                }
            )
        except Exception:
            frames.append(
                {
                    "index": 0,
                    "flags": -1,
                    "flags_desc": "RAW",
                    "raw_length": len(data),
                    "hex": data[:512].hex(),
                    "format": "binary",
                }
            )

    return frames


def extract_chat_content(frames: list[dict]) -> dict:
    """Extract human-readable chat content from decoded frames.

    Returns dict with: messages, model, metadata, errors, delta_texts
    """
    result: dict = {
        "messages": [],
        "model": "",
        "metadata": {},
        "errors": [],
        "delta_texts": [],
        "full_response": "",
    }

    for frame in frames:
        if frame.get("format") != "json":
            continue
        fj = frame.get("json", {})

        # Error frame
        if frame.get("flags") == 0x02:
            err = fj.get("error", {})
            if err:
                result["errors"].append(
                    {
                        "code": err.get("code", "unknown"),
                        "message": err.get("message", ""),
                    }
                )
            continue

        # Request: chatMessages
        if "chatMessages" in fj:
            for msg in fj["chatMessages"]:
                role_num = msg.get("role", msg.get("source", -1))
                role_name = ROLE_NAMES.get(role_num, f"ROLE_{role_num}")
                content = msg.get("content", "")

                # Check for intent-based content (Cascade format)
                intent = msg.get("intent", {})
                if intent:
                    generic = intent.get("genericIntent", intent.get("intent_generic", {}))
                    if generic:
                        content = generic.get("text", content)

                result["messages"].append(
                    {
                        "role": role_name,
                        "content": content[:500] + ("..." if len(content) > 500 else ""),
                        "message_id": msg.get("messageId", ""),
                        "conversation_id": msg.get("conversationId", ""),
                    }
                )

        # Request: metadata
        if "metadata" in fj:
            result["metadata"] = fj["metadata"]

        # Request: modelName
        if "modelName" in fj:
            result["model"] = fj["modelName"]

        # Response: deltaMessage (streaming)
        dm = fj.get("deltaMessage", {})
        if dm:
            text = dm.get("text", "")
            if text:
                result["delta_texts"].append(text)
                result["full_response"] += text
            if dm.get("isError"):
                result["errors"].append({"code": "delta_error", "message": text})

        # Response: chatMessage (non-streaming)
        cm = fj.get("chatMessage", {})
        if cm:
            content = cm.get("content", "")
            if content:
                result["full_response"] = content

        # Response: text / content fields
        if "text" in fj and not dm and not cm:
            result["full_response"] += fj["text"]
        if "content" in fj and not dm and not cm:
            result["full_response"] += fj["content"]

    return result


# ─── Pretty Printer ──────────────────────────────────────────────────────────


def format_timestamp() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


def print_separator(char: str = "─", width: int = 90) -> None:
    print(f"{C.DIM}{char * width}{C.RESET}")


def print_request_header(method: str, path: str, req_num: int, content_type: str = "") -> None:
    ts = format_timestamp()
    ep_info = KNOWN_ENDPOINTS.get(path, {})
    name = ep_info.get("name", path.rsplit("/", maxsplit=1)[-1] if "/" in path else path)
    desc = ep_info.get("desc", "")
    direction = ep_info.get("direction", "?")

    print_separator("═")
    print(f"{C.BOLD}{C.BLUE}#{req_num} {method} {name}{C.RESET}  {C.DIM}({path}){C.RESET}")
    print(f"{C.DIM}{ts} | {direction} | {desc}{C.RESET}")
    if content_type:
        print(f"Content-Type: {content_type}")
    print_separator("─")


def print_request_body(frames: list[dict], chat: dict) -> None:
    """Print decoded request body."""
    if chat.get("model"):
        print(f"{C.YELLOW}Model:{C.RESET} {chat['model']}")

    if chat.get("metadata"):
        meta = chat["metadata"]
        parts = []
        for k in ["ideName", "ideVersion", "extensionVersion", "sessionId"]:
            if k in meta:
                parts.append(f"{k}={meta[k]}")
        if parts:
            print(f"{C.DIM}Meta: {', '.join(parts)}{C.RESET}")

    if chat.get("messages"):
        print(f"{C.BOLD}Messages:{C.RESET}")
        for msg in chat["messages"]:
            role = msg["role"]
            color = {
                "SYSTEM": C.MAGENTA,
                "USER": C.GREEN,
                "ASSISTANT": C.BLUE,
            }.get(role, C.WHITE)
            content = msg["content"]
            print(f"  {color}[{role}]{C.RESET} {content}")

    # Show raw frames for non-chat endpoints or binary data
    if not chat.get("messages") and not chat.get("model"):
        print(f"{C.DIM}Frames: {len(frames)}{C.RESET}")
        for frame in frames:
            if frame.get("format") == "json":
                compact = json.dumps(frame["json"], ensure_ascii=False)
                if len(compact) > 200:
                    compact = compact[:200] + "..."
                print(f"  {C.CYAN}JSON:{C.RESET} {compact}")
            elif frame.get("readable_strings"):
                print(f"  {C.YELLOW}Strings:{C.RESET}")
                for s in frame["readable_strings"]:
                    print(f"    {s}")
            elif frame.get("hex"):
                print(f"  {C.DIM}HEX:{C.RESET} {frame['hex'][:64]}...")


def print_response_body(
    frames: list[dict], chat: dict, status_code: int, elapsed_ms: float
) -> None:
    """Print decoded response body."""
    status_color = C.GREEN if 200 <= status_code < 300 else C.RED
    print(f"Status: {status_color}{status_code}{C.RESET} ({elapsed_ms:.1f}ms)")

    if chat.get("errors"):
        for err in chat["errors"]:
            print(f"{C.RED}Error ({err['code']}): {err['message']}{C.RESET}")

    if chat.get("full_response"):
        resp = chat["full_response"]
        # Truncate long responses for display
        if len(resp) > 500:
            display = resp[:500].replace("\n", " ") + "..."
        else:
            display = resp.replace("\n", " ")
        print(f"{C.BLUE}Response:{C.RESET} {display}")

    if chat.get("delta_texts") and len(chat["delta_texts"]) > 1:
        print(f"{C.DIM}(Streamed {len(chat['delta_texts'])} chunks){C.RESET}")

    # Show raw frames for non-chat responses or binary
    if not chat.get("full_response") and not chat.get("errors"):
        for frame in frames:
            if frame.get("format") == "json":
                compact = json.dumps(frame["json"], ensure_ascii=False)
                if len(compact) > 300:
                    compact = compact[:300] + "..."
                print(f"  {C.CYAN}JSON:{C.RESET} {compact}")
            elif frame.get("readable_strings"):
                print(f"  {C.YELLOW}Strings:{C.RESET}")
                for s in frame["readable_strings"]:
                    if len(s) > 100:
                        print(f"    {s[:100]}...")
                    else:
                        print(f"    {s}")


# ─── Dump Writer ─────────────────────────────────────────────────────────────


class DumpWriter:
    """Writes intercepted traffic to NDJSON file for later analysis."""

    def __init__(self, filepath: str | Path | None = None):
        self.filepath = Path(filepath) if filepath else None
        self._lock = threading.Lock()
        self._count = 0

        if self.filepath:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            # Write header
            with open(self.filepath, "w") as f:
                header = {
                    "type": "session_start",
                    "timestamp": datetime.datetime.now().isoformat(),
                    "tool": "windsurf_sniffer",
                    "version": "1.0",
                }
                f.write(json.dumps(header, ensure_ascii=False) + "\n")

    def write_exchange(
        self,
        req_num: int,
        method: str,
        path: str,
        req_headers: dict,
        req_body: bytes,
        req_frames: list[dict],
        req_chat: dict,
        resp_status: int,
        resp_headers: dict,
        resp_body: bytes,
        resp_frames: list[dict],
        resp_chat: dict,
        elapsed_ms: float,
    ) -> None:
        if not self.filepath:
            return

        with self._lock:
            self._count += 1
            entry = {
                "type": "exchange",
                "num": req_num,
                "timestamp": datetime.datetime.now().isoformat(),
                "endpoint": path,
                "endpoint_name": KNOWN_ENDPOINTS.get(path, {}).get("name", ""),
                "method": method,
                "elapsed_ms": round(elapsed_ms, 1),
                "request": {
                    "headers": req_headers,
                    "body_length": len(req_body),
                    "frames": _sanitize_frames_for_dump(req_frames),
                    "chat": req_chat,
                },
                "response": {
                    "status": resp_status,
                    "headers": resp_headers,
                    "body_length": len(resp_body),
                    "frames": _sanitize_frames_for_dump(resp_frames),
                    "chat": resp_chat,
                },
            }

            with open(self.filepath, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def _sanitize_frames_for_dump(frames: list[dict]) -> list[dict]:
    """Prepare frames for JSON serialization (remove non-serializable data)."""
    clean = []
    for f in frames:
        cf = dict(f)
        # hex is already a string, json is already serializable
        clean.append(cf)
    return clean


# ─── Language Server Detection ───────────────────────────────────────────────


def detect_language_server() -> tuple[int, str]:
    """Detect running Windsurf language server port and CSRF token."""
    try:
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            if "language_server_macos_arm" not in line or "grep" in line:
                continue
            csrf = ""
            m = re.search(r"--csrf_token\s+(\S+)", line)
            if m:
                csrf = m.group(1)
            parts = line.split()
            if len(parts) >= 2:
                pid = parts[1]
                try:
                    lsof = subprocess.run(
                        [
                            "lsof",
                            "-nP",
                            "-iTCP",
                            "-sTCP:LISTEN",
                            "-a",
                            "-p",
                            pid,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    port = 0
                    for ll in lsof.stdout.splitlines():
                        if "LISTEN" in ll:
                            m2 = re.search(r":(\d+)\s+\(LISTEN\)", ll)
                            if m2:
                                c = int(m2.group(1))
                                if port == 0 or c < port:
                                    port = c
                    if port and csrf:
                        return port, csrf
                except Exception:
                    pass
            break
    except Exception:
        pass
    return 0, ""


# ─── Sniffer Proxy Handler ──────────────────────────────────────────────────


class SnifferProxyHandler(http.server.BaseHTTPRequestHandler):
    """Transparent proxy that logs all traffic between IDE and Language Server."""

    # Class-level config (set before server starts)
    target_host: str = "127.0.0.1"
    target_port: int = 0
    target_csrf: str = ""
    request_counter: int = 0
    dump_writer: DumpWriter | None = None
    filter_heartbeat: bool = True
    cascade_only: bool = False
    verbose: bool = False
    _lock = threading.Lock()

    def log_message(self, format, *args):
        # Suppress default access log
        pass

    def _should_skip(self, path: str) -> bool:
        """Check if this request should be silently proxied without logging."""
        if self.cascade_only:
            # Only show Cascade-related endpoints
            is_cascade = "Cascade" in path or "ChatClientRequestStream" in path or "Queue" in path
            return not is_cascade

        if self.filter_heartbeat and "Heartbeat" in path:
            return True
        return bool("RecordEvent" in path and not self.verbose)

    def _get_request_num(self) -> int:
        with SnifferProxyHandler._lock:
            SnifferProxyHandler.request_counter += 1
            return SnifferProxyHandler.request_counter

    def do_POST(self):
        self._proxy_request("POST")

    def do_GET(self):
        self._proxy_request("GET")

    def do_OPTIONS(self):
        self._proxy_request("OPTIONS")

    def _proxy_request(self, method: str):
        path = self.path
        skip_log = self._should_skip(path)
        req_num = self._get_request_num()

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        req_body = self.rfile.read(content_length) if content_length > 0 else b""

        # Collect request headers
        req_headers = {}
        for key in self.headers:
            req_headers[key] = self.headers[key]
        content_type = req_headers.get("Content-Type", "")

        # Decode request
        req_frames: list[dict] = []
        req_chat: dict = {}
        if req_body and not skip_log:
            req_frames = decode_connect_rpc_frames(req_body)
            req_chat = extract_chat_content(req_frames)

        # Print request
        if not skip_log:
            print_request_header(method, path, req_num, content_type)
            print_request_body(req_frames, req_chat)

        # Forward to real Language Server
        start_time = time.monotonic()
        try:
            conn = http.client.HTTPConnection(self.target_host, self.target_port, timeout=600)

            # Forward headers, replacing CSRF if needed
            fwd_headers = dict(req_headers)
            # Ensure CSRF token is present
            if self.target_csrf and "x-codeium-csrf-token" not in fwd_headers:
                fwd_headers["x-codeium-csrf-token"] = self.target_csrf

            conn.request(method, path, body=req_body, headers=fwd_headers)
            resp = conn.getresponse()
            resp_body = resp.read()
            resp_status = resp.status
            resp_headers_dict = dict(resp.getheaders())
            conn.close()
        except Exception as e:
            elapsed_ms = (time.monotonic() - start_time) * 1000
            if not skip_log:
                traceback.print_exc()
            self.send_error(502, f"Proxy error: {e}")
            return

        elapsed_ms = (time.monotonic() - start_time) * 1000

        # Decode response for logging (handle gzip)
        resp_frames: list[dict] = []
        resp_chat: dict = {}
        
        log_body = resp_body
        is_gzip = resp_headers_dict.get("Content-Encoding") == "gzip"
        if is_gzip and log_body:
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(log_body)) as f:
                    log_body = f.read()
            except Exception:
                pass

        if log_body and not skip_log:
            resp_frames = decode_connect_rpc_frames(log_body)
            resp_chat = extract_chat_content(resp_frames)

        # Print response
        if not skip_log:
            print_response_body(resp_frames, resp_chat, resp_status, elapsed_ms)
            print_separator("─")

        # Write dump
        # Note: We dump even if skipped from display if dump is enabled? 
        # Actually usually filtering applies to dump too to keep it clean, 
        # but let's respect skip_log for now to avoid massive heartbeats in dumps.
        if self.dump_writer and not skip_log:
            self.dump_writer.write_exchange(
                req_num=req_num,
                method=method,
                path=path,
                req_headers=req_headers,
                req_body=req_body,
                req_frames=req_frames,
                req_chat=req_chat,
                resp_status=resp_status,
                resp_headers=resp_headers_dict,
                resp_body=resp_body,
                resp_frames=resp_frames,
                resp_chat=resp_chat,
                elapsed_ms=elapsed_ms,
            )

        # Send response back to IDE
        self.send_response(resp_status)
        for key, value in resp_headers_dict.items():
            # Skip hop-by-hop headers
            if key.lower() in ("transfer-encoding", "connection", "keep-alive"):
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)


# ─── Main ────────────────────────────────────────────────────────────────────


def run_sniffer(
    listen_port: int = 18080,
    ls_port: int = 0,
    ls_csrf: str = "",
    dump_file: str | None = None,
    filter_heartbeat: bool = True,
    cascade_only: bool = False,
    verbose: bool = False,
) -> None:
    """Start the sniffer proxy."""

    # Auto-detect LS if not provided
    if not ls_port or not ls_csrf:
        detected_port, detected_csrf = detect_language_server()
        if detected_port and detected_csrf:
            ls_port = ls_port or detected_port
            ls_csrf = ls_csrf or detected_csrf
        else:
            print(f"{C.RED}❌ Could not auto-detect Windsurf Language Server.{C.RESET}")
            print("Please ensure Windsurf is running.")
            sys.exit(1)

    print(f"{C.GREEN}✅ Detected Windsurf LS on port {ls_port}{C.RESET}")
    print(f"{C.DIM}CSRF: {ls_csrf[:15]}...{C.RESET}")

    # Verify LS is alive
    try:
        conn = http.client.HTTPConnection("127.0.0.1", ls_port, timeout=3)
        conn.request(
            "POST",
            "/exa.language_server_pb.LanguageServerService/Heartbeat",
            b"{}",
            {
                "Content-Type": "application/json",
                "x-codeium-csrf-token": ls_csrf,
            },
        )
        resp = conn.getresponse()
        resp.read()
        conn.close()
        if resp.status == 200:
            print(f"{C.GREEN}✨ Heartbeat successful{C.RESET}")
        else:
            print(f"{C.YELLOW}⚠️ Heartbeat returned {resp.status}{C.RESET}")
    except Exception as e:
        print(f"{C.RED}❌ Failed to connect to LS: {e}{C.RESET}")

    # Setup dump writer
    dump_writer = DumpWriter(dump_file) if dump_file else None
    if dump_writer:
        print(f"📁 Dumps will be written to: {C.BOLD}{dump_file}{C.RESET}")

    # Configure handler
    SnifferProxyHandler.target_host = "127.0.0.1"
    SnifferProxyHandler.target_port = ls_port
    SnifferProxyHandler.target_csrf = ls_csrf
    SnifferProxyHandler.dump_writer = dump_writer
    SnifferProxyHandler.filter_heartbeat = filter_heartbeat
    SnifferProxyHandler.cascade_only = cascade_only
    SnifferProxyHandler.verbose = verbose

    # Start server
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.ThreadingTCPServer(("127.0.0.1", listen_port), SnifferProxyHandler)

    print(f"\n🚀 {C.BOLD}Sniffer listening on port {listen_port}{C.RESET}")
    print(f"👉 Configure Windsurf to use: {C.CYAN}http://127.0.0.1:{listen_port}{C.RESET}")
    if cascade_only:
        print(f"🔍 Filter: {C.YELLOW}Cascade traffic only{C.RESET}")
    print_separator("═")
    print_separator("═")

    def shutdown_handler(signum, frame):
        print(f"\n\n🛑 {C.RED}Shutting down...{C.RESET}")
        if dump_writer and dump_writer.filepath:
            print(f"💾 Dump saved to {dump_writer.filepath}")
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(
        description="Windsurf Traffic Sniffer — passive interceptor for IDE ↔ LS traffic",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Auto-detect LS, listen on 18080
  %(prog)s --port 19000                       # Custom listen port
  %(prog)s --dump-file /tmp/ws_dump.ndjson    # Save full dump
  %(prog)s --cascade-only                     # Only show Cascade traffic
  %(prog)s --no-filter                        # Show heartbeats too
  %(prog)s --verbose                          # Show telemetry events
  %(prog)s --ls-port 42100 --ls-csrf TOKEN    # Manual LS config
        """,
    )
    parser.add_argument(
        "--port",
        type=int,
        default=18080,
        help="Port to listen on (default: 18080)",
    )
    parser.add_argument(
        "--ls-port",
        type=int,
        default=0,
        help="Language Server port (auto-detected if not set)",
    )
    parser.add_argument(
        "--ls-csrf",
        type=str,
        default="",
        help="Language Server CSRF token (auto-detected if not set)",
    )
    parser.add_argument(
        "--dump-file",
        type=str,
        default=None,
        help="Path to NDJSON dump file (default: none)",
    )
    parser.add_argument(
        "--auto-dump",
        action="store_true",
        help="Auto-create dump file in /tmp/windsurf_dump_<timestamp>.ndjson",
    )
    parser.add_argument(
        "--cascade-only",
        action="store_true",
        help="Only display/log Cascade-related traffic",
    )
    parser.add_argument(
        "--no-filter",
        action="store_true",
        help="Don't filter out heartbeat requests",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show telemetry and other noisy endpoints",
    )

    args = parser.parse_args()

    # Auto-dump
    dump_file = args.dump_file
    if args.auto_dump and not dump_file:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dump_file = f"/tmp/windsurf_dump_{ts}.ndjson"

    # Env fallbacks
    ls_port = args.ls_port or int(os.environ.get("WINDSURF_LS_PORT", "0"))
    ls_csrf = args.ls_csrf or os.environ.get("WINDSURF_LS_CSRF", "")

    run_sniffer(
        listen_port=args.port,
        ls_port=ls_port,
        ls_csrf=ls_csrf,
        dump_file=dump_file,
        filter_heartbeat=not args.no_filter,
        cascade_only=args.cascade_only,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
