import binascii

import requests

# HEX from line 2 of protobuf.jsonl (truncated to essential part)
# 00000002470ac404...
# I'll rebuild a valid small one based on the structure.

def make_payload(json_str):
    json_bytes = json_str.encode('utf-8')
    # Protobuf wrapper (Tag 1, Type 2)
    def to_varint(n):
        res = []
        while n > 127:
            res.append((n & 0x7f) | 0x80)
            n >>= 7
        res.append(n)
        return bytes(res)
    
    proto_data = b'\x0a' + to_varint(len(json_bytes)) + json_bytes
    # Connect envelope (Flags 0, Length 4 bytes BE)
    import struct
    envelope = struct.pack(">BI", 0, len(proto_data)) + proto_data
    return envelope

# Smallest valid JSON payload
json_payload = '{"chatMessages":[{"messageId":"123","source":1,"intent":{"generic":{"text":"Hello"}},"timestamp":"2026-02-16T19:32:31Z","conversationId":"7D1BFD57-7EC8-4B0E-B92A-16F71487F5E0"}],"metadata":{"apiKey":"sk-ws-01-3vQio5CLce8beK1OqKX1zvWmP-nTjOV3JpO3O5v3tI6Yy7SIRWJyanWHnCpjDnCKIOd1JVKFww8DKfmu5yRqVqGbazlrug","ideVersion":"1.107.0","extensionVersion":"1.9552.21","locale":"en","sessionId":"test-session","ideName":"windsurf","requestId":"1771270351"},"chatModelName":"MODEL_SWE_1_5"}'

url = "http://127.0.0.1:63121/exa.language_server_pb.LanguageServerService/RawGetChatMessage"
headers = {
    "Content-Type": "application/connect+proto",
    "Connect-Protocol-Version": "1",
    "x-codeium-csrf-token": "56ee1646-1102-43bd-862e-ae6ebe0d2546" # From previous ps aux
}

payload = make_payload(json_payload)
print(f"Sending payload of size {len(payload)}...")
response = requests.post(url, data=payload, headers=headers, stream=True)

print(f"Status: {response.status_code}")
for chunk in response.iter_content(chunk_size=1024):
    if chunk:
        print(f"Received chunk: {binascii.hexlify(chunk)}")
