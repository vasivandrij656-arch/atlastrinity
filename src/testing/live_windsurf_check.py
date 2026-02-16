import requests
import json
import uuid
import time
import struct

def make_envelope(payload):
    jsonData = json.dumps(payload).encode('utf-8')
    envelope = bytearray()
    envelope.append(0x00)  # flags
    envelope.extend(struct.pack('>I', len(jsonData)))
    envelope.extend(jsonData)
    return envelope

def parse_streaming_frames(data):
    resultText = ""
    offset = 0
    while offset + 5 <= len(data):
        flags = data[offset]
        frameLen = struct.unpack('>I', data[offset + 1:offset + 5])[0]
        frameData = data[offset + 5 : offset + 5 + frameLen]
        offset += 5 + frameLen
        try:
            fj = json.loads(frameData)
            if flags == 0x02: continue
            if "deltaMessage" in fj:
                resultText += fj["deltaMessage"].get("text", "")
            elif "text" in fj:
                resultText += fj["text"]
            elif "content" in fj:
                resultText += fj["content"]
            elif "chatMessage" in fj:
                resultText += fj["chatMessage"].get("content", "")
        except: continue
    return resultText

url = "http://127.0.0.1:57796/exa.language_server_pb.LanguageServerService/RawGetChatMessage"
headers = {
    "Content-Type": "application/connect+json",
    "Connect-Protocol-Version": "1",
    "x-codeium-csrf-token": "6b3fcb78-9de8-4148-8aa5-844524fbcf81"
}

payload = {
    "chatMessages": [{
        "messageId": str(uuid.uuid4()),
        "source": 1,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "conversationId": str(uuid.uuid4()),
        "intent": {"generic": {"text": "Reply with exactly 'ATLAS_ACK' and nothing else."}}
    }],
    "metadata": {
        "ideName": "windsurf",
        "ideVersion": "1.9552.21",
        "extensionVersion": "1.48.2",
        "apiKey": "sk-ws-01-3vQio5CLce8beK1OqKX1zvWmP-nTjOV3JpO3O5v3tI6Yy7SIRWJyanWHnCpjDnCKIOd1JVKFww8DKfmu5yRqVqGbazlrug"
    },
    "chatModelName": "MODEL_CHAT_11121"
}

resp = requests.post(url, headers=headers, data=bytes(make_envelope(payload)), timeout=30)
if resp.status_code == 200:
    print(parse_streaming_frames(resp.content))
else:
    print(f"Error: {resp.status_code}")
    print(resp.text)
