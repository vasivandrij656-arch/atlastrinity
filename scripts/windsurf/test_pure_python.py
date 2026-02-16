import os
import json
import time
import uuid
import struct
import subprocess
import requests

# Configuration
LS_RAW_CHAT = "/exa.language_server_pb.LanguageServerService/RawGetChatMessage"
IDE_VERSION = "1.9552.21"
EXTENSION_VERSION = "1.48.2"

# Standard Proto Helpers
def _proto_varint(val):
    r = b""
    while val > 0x7F:
        r += bytes([(val & 0x7F) | 0x80])
        val >>= 7
    r += bytes([val])
    return r

def _proto_str(field_num, s):
    b = s.encode("utf-8")
    return _proto_varint((field_num << 3) | 2) + _proto_varint(len(b)) + b

def _proto_int(field_num, val):
    return _proto_varint((field_num << 3) | 0) + _proto_varint(val)

def _proto_msg(field_num, inner):
    return _proto_varint((field_num << 3) | 2) + _proto_varint(len(inner)) + inner

def _build_metadata_proto(api_key, session_id):
    return (
        _proto_str(1, "windsurf")
        + _proto_str(2, "1.48.2")
        + _proto_str(3, api_key)
        + _proto_str(4, "en")
        + _proto_str(7, "1.9552.21")
        + _proto_int(9, 1)
        + _proto_str(10, session_id)
    )

def detect_ls():
    """Detect running Windsurf LS port and CSRF token."""
    print("🔍 Detecting Windsurf LS...")
    try:
        # Grep for the Windsurf language server process
        cmd = ["ps", "aux"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        candidates = []
        for line in result.stdout.splitlines():
            if "language_server" in line and "windsurf" in line.lower() and "grep" not in line:
                candidates.append(line)
        
        if not candidates:
            print("❌ No Windsurf LS process found.")
            return None, None

        # Pick the most likely candidate (prioritize 'Windsurf.app')
        target_line = candidates[0]
        for c in candidates:
            if "Windsurf.app" in c:
                target_line = c
                break
        
        print(f"   Target Process: {target_line[:100]}...")

        # Extract CSRF
        csrf_token = None
        if "--csrf_token" in target_line:
            parts = target_line.split("--csrf_token")
            if len(parts) > 1:
                csrf_token = parts[1].strip().split()[0]
        
        # Extract PID
        parts = target_line.split()
        pid = parts[1]
        
        # Get Port
        cmd = ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", pid]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        port = None
        for line in result.stdout.splitlines():
            if "LISTEN" in line:
                # Format: command PID user ... TCP *:52838 (LISTEN)
                # Find the port number after colon
                try:
                    port_part = line.split(":")[-1].split()[0]
                    port = int(port_part)
                    # We want the lowest port usually, or the one that isn't ephemeral?
                    # Windsurf usually binds to one port for LS.
                    break 
                except:
                    continue
        
        return port, csrf_token
            
    except Exception as e:
        print(f"❌ Detection failed: {e}")
        return None, None

def make_envelope(payload):
    """Create Connect-RPC envelope."""
    json_data = json.dumps(payload).encode("utf-8")
    # Flag (1 byte) + Length (4 bytes big-endian) + Data
    header = struct.pack(">BI", 0, len(json_data))
    return header + json_data

def parse_frames(data):
    """Parse Connect-RPC response frames."""
    offset = 0
    text_content = ""
    error_msg = None
    
    while offset + 5 <= len(data):
        flag = data[offset]
        length = struct.unpack(">I", data[offset+1:offset+5])[0]
        chunk = data[offset+5:offset+5+length]
        offset += 5 + length
        
        try:
            msg = json.loads(chunk)
            if flag == 2: # End/Error
                if "error" in msg:
                    error_msg = json.dumps(msg["error"])
            elif flag == 0 or flag == 1: # Data
                if "text" in msg:
                    text_content += msg["text"]
                elif "content" in msg:
                    text_content += msg["content"]
                elif "chatMessage" in msg:
                    text_content += msg["chatMessage"].get("content", "")
                elif "deltaMessage" in msg:
                    text_content += msg["deltaMessage"].get("text", "")
        except:
            continue
            
    return text_content, error_msg

def main():
    # Get Env
    api_key = os.environ.get("WINDSURF_API_KEY")
    install_id = os.environ.get("WINDSURF_INSTALL_ID")
    
    if not api_key:
        print("❌ WINDSURF_API_KEY not found.")
        return

    port, csrf = detect_ls()
    if not port or not csrf:
        print("❌ Could not detect LS port or CSRF.")
        return
        
    print(f"✅ Found LS at port {port} with CSRF {csrf[:8]}...")
    url = f"http://127.0.0.1:{port}{LS_RAW_CHAT}"

    # Prepare Payload
    conv_id = str(uuid.uuid4())
    msg_id = str(uuid.uuid4())
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    metadata = {
        "ideName": "windsurf",
        "ideVersion": IDE_VERSION,
        "extensionVersion": EXTENSION_VERSION,
        "locale": "en",
        "sessionId": f"atlastrinity-python-{os.getpid()}",
        "requestId": str(int(time.time())),
        "apiKey": api_key,
    }
    if install_id:
        metadata["installationId"] = install_id

    payload = {
        "chatMessages": [
            {
                "messageId": msg_id,
                "source": 1, # USER
                "timestamp": now,
                "conversationId": conv_id,
                "intent": {"generic": {"text": "Hello, this is a test from Python."}}
            }
        ],
        "metadata": metadata,
        "chatModelName": "MODEL_SWE_1_5" 
    }
    
    headers = {
        "Content-Type": "application/connect+json",
        "Connect-Protocol-Version": "1",
        "x-codeium-csrf-token": csrf
    }
    
    print("📨 Sending request (windsurf-fast)...")
    payload["chatModelName"] = "MODEL_CHAT_11121" # windsurf-fast
    
    try:
        resp = requests.post(
            url, 
            headers=headers, 
            data=make_envelope(payload),
            stream=True
        )
        
        print(f"📥 Status: {resp.status_code}")
        full_data = b""
        for chunk in resp.iter_content(chunk_size=None):
            full_data += chunk  
        text, error = parse_frames(full_data)
        if error:
            print(f"❌ Backend Error (windsurf-fast): {error}")
        else:
            print(f"✅ Response (windsurf-fast): {text}")

    except Exception as e:
        print(f"❌ Exception: {e}")

    # Test Cascade
    print("\n🌊 Testing StartCascade with Connect+Proto...")
    cascade_url = f"http://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/StartCascade"
    
    # Payload: Field 1 is metadata
    # Metadata is a sub-message containing fields 1,2,3...
    session_id = f"atlastrinity-python-{os.getpid()}"
    meta_bytes = _build_metadata_proto(api_key, session_id)
    
    # Request body: Field 1 is Metadata
    payload_proto = _proto_msg(1, meta_bytes)
    
    # Wrap in Connect Envelope
    # Flag=0, Length=...
    envelope = struct.pack(">BI", 0, len(payload_proto)) + payload_proto
    
    headers_proto = {
        "Content-Type": "application/grpc",
        "TE": "trailers",
        "x-codeium-csrf-token": csrf
    }
    
    try:
        resp = requests.post(
            cascade_url,
            headers=headers_proto,
            data=envelope
        )
        print(f"📥 Cascade Status: {resp.status_code}")
        
        if resp.status_code == 200:
             # Parse response
             # It assumes standard Connect envelope response
             # We should look for Field 1 -> Cascade ID
             content = resp.content
             if len(content) > 5:
                 flag = content[0]
                 length = struct.unpack(">I", content[1:5])[0]
                 data = content[5:5+length]
                 
                 # Extract string at field 1
                 cascade_id = _proto_extract_string(data, 1)
                 print(f"✅ Cascade ID: {cascade_id}")
             else:
                 print(f"⚠️ Response too short: {content}")
        else:
             print(f"❌ Cascade Error: {resp.text}")

    except Exception as e:
        print(f"❌ Exception: {e}")

# Add extraction helper
def _proto_extract_string(data, target_field):
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
        if fn == 0: break
        
        if wt == 0: 
            while offset < len(data) and data[offset] & 0x80: offset += 1
            if offset < len(data): offset += 1
        elif wt == 2:
            ln = 0
            s = 0
            while offset < len(data):
                b = data[offset]
                offset += 1
                ln |= (b & 0x7F) << s
                s += 7
                if not (b & 0x80): break
            payload = data[offset:offset+ln]
            offset += ln
            if fn == target_field:
                return payload.decode("utf-8", errors="ignore")
        elif wt == 1: offset += 8
        elif wt == 5: offset += 4
        else: break
    return ""

if __name__ == "__main__":
    main()
