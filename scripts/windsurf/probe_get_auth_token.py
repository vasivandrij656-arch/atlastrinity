#!/usr/bin/env python3
"""
Probe the GetAuthToken endpoint on the Windsurf Language Server.

Purpose: Discover what the LS returns for GetAuthToken requests.
This endpoint is documented in the sniffer but never called by Atlas Trinity.

Usage:
    python scripts/windsurf/probe_get_auth_token.py
"""

from __future__ import annotations

import json
import os
import struct
import sys
from pathlib import Path

# Add project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests

# Load env
try:
    from dotenv import load_dotenv
    load_dotenv("/Users/dev/.config/atlastrinity/.env", override=True)
except ImportError:
    pass

from src.providers.utils.windsurf_session_watcher import detect_ls_process, ls_heartbeat

# ─── Constants ──────────────────────────────────────────────────────────────

GET_AUTH_TOKEN = "/exa.language_server_pb.LanguageServerService/GetAuthToken"
HEARTBEAT = "/exa.language_server_pb.LanguageServerService/Heartbeat"

# ─── Proto Helpers ──────────────────────────────────────────────────────────

def proto_varint(val: int) -> bytes:
    r = b""
    while val > 0x7F:
        r += bytes([(val & 0x7F) | 0x80])
        val >>= 7
    r += bytes([val])
    return r

def proto_str(field_num: int, s: str) -> bytes:
    b = s.encode("utf-8")
    return proto_varint((field_num << 3) | 2) + proto_varint(len(b)) + b

def proto_msg(field_num: int, inner: bytes) -> bytes:
    return proto_varint((field_num << 3) | 2) + proto_varint(len(inner)) + inner

def proto_int(field_num: int, val: int) -> bytes:
    return proto_varint((field_num << 3) | 0) + proto_varint(val)

def make_connect_envelope(payload: bytes) -> bytes:
    """Wrap payload in Connect-RPC streaming envelope (1 byte flags + 4 bytes length)."""
    return b'\x00' + struct.pack('>I', len(payload)) + payload

def decode_proto_strings(data: bytes, min_len: int = 2) -> list[str]:
    """Extract readable strings from protobuf binary."""
    results = []
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
            payload = data[offset:offset + ln]
            offset += ln
            try:
                text = payload.decode("utf-8")
                if len(text) >= min_len and all(32 <= ord(c) < 127 or c in "\n\r\t" for c in text):
                    results.append(f"  field {fn}: \"{text}\"")
            except UnicodeDecodeError:
                pass
            results.extend([f"  {s}" for s in decode_proto_strings(payload, min_len)])
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        else:
            break
    return results


# ─── Test Variations ────────────────────────────────────────────────────────

def probe(port: int, csrf: str, api_key: str, install_id: str) -> None:
    """Probe GetAuthToken with multiple payload variants."""
    
    base_headers = {
        "x-codeium-csrf-token": csrf,
    }

    # Build metadata proto (same as used in chat/cascade)
    meta = (
        proto_str(1, "windsurf")
        + proto_str(2, "1.9552.21")
        + proto_str(3, api_key)
        + proto_str(4, "en")
        + proto_str(7, "1.107.0")
        + proto_int(9, 1)
        + proto_str(10, f"probe-{os.getpid()}")
    )

    test_cases = [
        # Test 1: Empty JSON body (Connect-RPC JSON format)
        {
            "name": "Empty JSON",
            "headers": {**base_headers, "Content-Type": "application/json"},
            "body": b"{}",
        },
        # Test 2: JSON with metadata
        {
            "name": "JSON with metadata",
            "headers": {**base_headers, "Content-Type": "application/json"},
            "body": json.dumps({
                "metadata": {
                    "ideName": "windsurf",
                    "ideVersion": "1.107.0",
                    "extensionVersion": "1.9552.21",
                    "apiKey": api_key,
                    "sessionId": f"probe-{os.getpid()}",
                }
            }).encode(),
        },
        # Test 3: Connect-RPC JSON envelope
        {
            "name": "Connect-RPC JSON envelope",
            "headers": {
                **base_headers,
                "Content-Type": "application/connect+json",
                "Connect-Protocol-Version": "1",
            },
            "body": make_connect_envelope(json.dumps({
                "metadata": {
                    "ideName": "windsurf",
                    "ideVersion": "1.107.0",
                    "extensionVersion": "1.9552.21",
                    "apiKey": api_key,
                }
            }).encode()),
        },
        # Test 4: gRPC binary with metadata proto
        {
            "name": "gRPC binary with metadata",
            "headers": {
                **base_headers,
                "Content-Type": "application/grpc",
                "TE": "trailers",
            },
            "body": make_connect_envelope(proto_msg(1, meta)),
        },
        # Test 5: gRPC binary empty
        {
            "name": "gRPC binary empty",
            "headers": {
                **base_headers,
                "Content-Type": "application/grpc",
                "TE": "trailers",
            },
            "body": make_connect_envelope(b""),
        },
    ]

    for tc in test_cases:
        print(f"\n{'='*60}")
        print(f"📡 Test: {tc['name']}")
        print(f"{'='*60}")

        try:
            r = requests.post(
                f"http://127.0.0.1:{port}{GET_AUTH_TOKEN}",
                headers=tc["headers"],
                data=tc["body"],
                timeout=10,
            )
            print(f"   Status: {r.status_code}")
            print(f"   Content-Type: {r.headers.get('Content-Type', 'N/A')}")
            print(f"   Body length: {len(r.content)} bytes")
            
            if r.content:
                # Try JSON decode
                try:
                    parsed = json.loads(r.content)
                    print(f"   JSON: {json.dumps(parsed, indent=2)[:500]}")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass

                # Try Connect-RPC envelope decode
                if len(r.content) >= 5:
                    flags = r.content[0]
                    frame_len = struct.unpack('>I', r.content[1:5])[0]
                    if len(r.content) >= 5 + frame_len:
                        payload = r.content[5:5 + frame_len]
                        print(f"   Envelope: flags={flags}, payload_len={frame_len}")
                        try:
                            parsed = json.loads(payload)
                            print(f"   Envelope JSON: {json.dumps(parsed, indent=2)[:500]}")
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            # Try proto decode
                            strings = decode_proto_strings(payload)
                            if strings:
                                print(f"   Proto strings:")
                                for s in strings[:20]:
                                    print(f"     {s}")
                            else:
                                print(f"   Raw hex: {payload[:128].hex()}")

                # Fallback: raw hex
                if r.status_code != 200:
                    print(f"   Raw: {r.content[:200]}")

        except requests.exceptions.Timeout:
            print(f"   ⏰ Timeout")
        except Exception as e:
            print(f"   ❌ Error: {e}")


# ─── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    print("🔍 Probing Windsurf GetAuthToken endpoint")
    print("=" * 60)

    # Detect LS
    port, csrf = detect_ls_process()
    if not port or not csrf:
        print("❌ Windsurf Language Server not detected. Is Windsurf running?")
        sys.exit(1)

    if not ls_heartbeat(port, csrf):
        print(f"❌ LS detected on port {port} but heartbeat failed")
        sys.exit(1)

    print(f"✅ LS alive on port {port}")
    print(f"   CSRF: {csrf[:20]}...")

    api_key = os.getenv("WINDSURF_API_KEY", "")
    install_id = os.getenv("WINDSURF_INSTALL_ID", "")
    if api_key:
        print(f"   API Key: {api_key[:15]}...")
    else:
        print("   ⚠ No API key in env, probing without auth")

    probe(port, csrf, api_key, install_id)

    print(f"\n{'='*60}")
    print("✅ Probe complete")


if __name__ == "__main__":
    main()
