import requests
import binascii

# Read hex from file to avoid copy-paste errors
with open("scripts/windsurf/current_payload.hex", "r") as f:
    hex_payload = f.read().strip()

binary_payload = binascii.unhexlify(hex_payload)

url = "http://127.0.0.1:63121/exa.language_server_pb.LanguageServerService/RawGetChatMessage"
headers = {
    "Content-Type": "application/grpc",
    "x-codeium-csrf-token": "56ee1646-1102-43bd-862e-ae6ebe0d2546",
}

print(f"Sending request to {url}...")
resp = requests.post(url, headers=headers, data=binary_payload, timeout=30)
if resp.status_code == 200:
    print("Success! (Status 200)")
    print(f"Response length: {len(resp.content)}")
    print(f"Response Hex (first 100): {resp.content[:100].hex()}")
else:
    print(f"Error: {resp.status_code}")
    print(resp.text)
