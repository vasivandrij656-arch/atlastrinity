#!/usr/bin/env python3
"""
Windsurf Cascade Traffic Analyzer
=================================

Analyzes NDJSON dump files produced by windsurf_sniffer.py to decode and visualize
the binary Protobuf structures used in Cascade communication.

Key goals:
1. Identify the exact structure of CascadeItem (field IDs, types)
2. Compare unary QueueCascadeMessage vs bidi StartChatClientRequestStream
3. Find flags like enable_cortex_reasoning, enable_action_phase

Usage:
    python scripts/windsurf/analyze_cascade_traffic.py <dump_file.ndjson>
"""

import argparse
import json
import struct
from dataclasses import dataclass
from typing import Any

# ─── Colors ─────────────────────────────────────────────────────────────────


class C:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


# ─── Proto Decoder ──────────────────────────────────────────────────────────


@dataclass
class ProtoField:
    field_num: int
    wire_type: int
    value: Any
    sub_fields: list["ProtoField"] | None = None


def decode_proto(data: bytes, depth: int = 0) -> list[ProtoField]:
    """Recursively decode protobuf binary data."""
    fields = []
    offset = 0

    while offset < len(data):
        # Read tag
        tag = 0
        shift = 0
        start_offset = offset
        while offset < len(data):
            b = data[offset]
            offset += 1
            tag |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                break

        if offset > start_offset + 10:  # Safety break for bad varints
            break

        field_num = tag >> 3
        wire_type = tag & 0x07

        if field_num == 0:
            break

        value = None
        sub_fields = None

        if wire_type == 0:  # Varint
            val = 0
            shift = 0
            while offset < len(data):
                b = data[offset]
                offset += 1
                val |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80):
                    break
            value = val

        elif wire_type == 1:  # 64-bit
            if offset + 8 <= len(data):
                val = struct.unpack("<Q", data[offset : offset + 8])[0]
                # Try double
                try:
                    dbl = struct.unpack("<d", data[offset : offset + 8])[0]
                    value = f"Int64={val} / Double={dbl}"
                except:
                    value = val
                offset += 8

        elif wire_type == 2:  # Length-delimited
            ln = 0
            shift = 0
            while offset < len(data):
                b = data[offset]
                offset += 1
                ln |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80):
                    break

            if offset + ln <= len(data):
                payload = data[offset : offset + ln]
                offset += ln

                # Heuristic: is it a string?
                try:
                    text = payload.decode("utf-8")
                    # Check if looks like valid text (no excessive control chars)
                    if all(32 <= ord(c) < 127 or c in "\n\r\t" for c in text):
                        value = text
                    else:
                        value = f"<{len(payload)} bytes binary>"
                        # Recursively decode if it looks like a message
                        # (simplistic check: doesn't crash decoder)
                        try:
                            sub = decode_proto(payload, depth + 1)
                            if sub:
                                sub_fields = sub
                        except:
                            pass
                except UnicodeDecodeError:
                    value = f"<{len(payload)} bytes binary>"
                    # Try recursive decode
                    try:
                        sub = decode_proto(payload, depth + 1)
                        if sub:
                            sub_fields = sub
                    except:
                        pass
            else:
                value = "<truncated>"

        elif wire_type == 5:  # 32-bit
            if offset + 4 <= len(data):
                val = struct.unpack("<I", data[offset : offset + 4])[0]
                try:
                    flt = struct.unpack("<f", data[offset : offset + 4])[0]
                    value = f"Int32={val} / Float={flt}"
                except:
                    value = val
                offset += 4

        else:
            value = f"<unknown wire type {wire_type}>"
            break  # Stop on unknown wire type to avoid garbage

        fields.append(ProtoField(field_num, wire_type, value, sub_fields))

    return fields


def print_proto(fields: list[ProtoField], indent: int = 0):
    """Pretty-print decoded proto fields."""
    prefix = "  " * indent
    for f in fields:
        # Highlight interesting fields based on known protocol
        name_hint = ""

        # Heuristics for Windsurf protocol
        if f.field_num == 1 and isinstance(f.value, str) and "windsurf" in f.value:
            name_hint = " (ideName?)"
        elif f.field_num == 3 and isinstance(f.value, str) and f.value.startswith("sk-ws-"):
            name_hint = " (apiKey)"
        elif f.field_num == 10 and isinstance(f.value, str) and "user-" in f.value:
            name_hint = " (sessionId?)"

        # We use str(f.value) which is fine
        val_str = str(f.value)
        if len(val_str) > 100:
            val_str = val_str[:100] + "..."

        color = C.CYAN if f.sub_fields else C.GREEN
        print(f"{prefix}{color}{f.field_num}{C.RESET}: {val_str}{C.DIM}{name_hint}{C.RESET}")

        if f.sub_fields:
            print_proto(f.sub_fields, indent + 1)


# ─── Frame Handling ─────────────────────────────────────────────────────────

import gzip
import io


def decode_frames(raw_data: str | bytes, is_gzip: bool = False) -> bytes:
    """Decode Connect-RPC frames or raw bytes."""
    if isinstance(raw_data, str):
        # Handle string input (usually not expected for binary/hex logic flow)
        return b""

    if is_gzip:
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw_data)) as f:
                raw_data = f.read()
        except Exception:
            pass  # Not gzip or failed

    # Check for Connect-RPC envelopes
    # 1 byte flags + 4 bytes length
    if len(raw_data) > 5:
        _ = raw_data[0]  # Connect-RPC flags byte (0=compressed, 1=uncompressed, etc.)
        try:
            length = struct.unpack(">I", raw_data[1:5])[0]
            if 5 + length <= len(raw_data):
                return raw_data[5 : 5 + length]
        except:
            pass

    return raw_data


# ─── Analyzer ───────────────────────────────────────────────────────────────


def analyze_dump(filepath: str, show_all: bool = False):
    print(f"📂 Analyzing {C.BOLD}{filepath}{C.RESET}...")

    with open(filepath) as f:
        for line in f:
            try:
                entry = json.loads(line)
            except:
                continue

            if entry.get("type") != "exchange":
                continue

            endpoint = entry.get("endpoint", "")
            method = entry.get("method", "")

            # Filter logic
            is_interesting = (
                "Cascade" in endpoint
                or "ChatClientRequestStream" in endpoint
                or "Queue" in endpoint
            )

            if not is_interesting and not show_all:
                continue

            print(f"\n{C.YELLOW}═" * 80 + f"{C.RESET}")
            print(f"{C.BOLD}{method} {endpoint}{C.RESET}")
            print(f"{C.DIM}Timestamp: {entry.get('timestamp')}{C.RESET}")

            req = entry.get("request", {})
            frames = req.get("frames", [])

            if frames:
                print(f"\n{C.BLUE}Request Payload ({len(frames)} frames):{C.RESET}")
                for i, frame in enumerate(frames):
                    if "hex" in frame:
                        data = bytes.fromhex(frame["hex"])
                        payload = decode_frames(data)
                        fields = decode_proto(payload)
                        print(f"  Frame {i} ({len(payload)} bytes):")
                        print_proto(fields, indent=2)
                    elif "json" in frame:
                        print(f"  Frame {i} (JSON): {json.dumps(frame['json'])[:100]}...")

            resp = entry.get("response", {})
            resp_frames = resp.get("frames", [])
            is_gzip = resp.get("headers", {}).get("Content-Encoding") == "gzip"

            if resp_frames:
                print(f"\n{C.GREEN}Response Payload ({len(resp_frames)} frames):{C.RESET}")
                for i, frame in enumerate(resp_frames):
                    if "hex" in frame:
                        data = bytes.fromhex(frame["hex"])
                        payload = decode_frames(data, is_gzip=is_gzip)

                        # Try JSON decode first (often it's JSON inside gzip)
                        try:
                            json_obj = json.loads(payload)
                            print(f"  Frame {i} (JSON): {json.dumps(json_obj)[:100]}...")
                            continue
                        except:
                            pass

                        # Try proto
                        fields = decode_proto(payload)
                        if fields:
                            print(f"  Frame {i} (Proto, {len(payload)} bytes):")
                            print_proto(fields, indent=2)
                        else:
                            print(f"  Frame {i} (Raw, {len(payload)} bytes): {payload[:50]}...")

                    elif "json" in frame:
                        print(f"  Frame {i} (JSON): {json.dumps(frame['json'])[:100]}...")


def main():
    parser = argparse.ArgumentParser(description="Analyze Windsurf traffic dumps")
    parser.add_argument("dump_file", help="Path to .ndjson dump file")
    parser.add_argument(
        "--all", action="store_true", help="Show all endpoints (default: cascade only)"
    )

    args = parser.parse_args()
    analyze_dump(args.dump_file, args.all)


if __name__ == "__main__":
    main()
