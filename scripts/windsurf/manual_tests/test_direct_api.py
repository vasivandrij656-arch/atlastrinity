import asyncio
import os


import requests


async def test_direct_api():
    print("🧪 Testing Direct API Mode...")

    # Get credentials
    api_key = os.getenv("WINDSURF_API_KEY")
    install_id = os.getenv("WINDSURF_INSTALL_ID")

    if not api_key:
        print("❌ WINDSURF_API_KEY not set")
        return False

    if not install_id:
        print("❌ WINDSURF_INSTALL_ID not set")
        return False

    print(f"✅ API Key: {api_key[:20]}...")
    print(f"✅ Install ID: {install_id}")

    # Test direct API call
    url = "https://server.self-serve.windsurf.com/exa.api_server_pb.ApiServerService/GetChatMessage"
    headers = {
        "Content-Type": "application/connect+json",
        "Connect-Protocol-Version": "1",
        "Authorization": f"Basic {api_key}",
    }

    payload = {
        "chatMessages": [
            {
                "messageId": "test-message-123",
                "source": 1,  # USER
                "timestamp": "2025-02-16T20:00:00.000Z",
                "conversationId": "test-conv-123",
                "intent": {
                    "generic": {"text": "Create test_direct.txt with content 'Direct API works'"}
                },
            }
        ],
        "metadata": {
            "ideName": "windsurf",
            "ideVersion": "1.107.0",
            "extensionVersion": "1.9552.21",
            "apiKey": api_key,
            "language": "en",
            "installationId": install_id,
        },
        "chatModelName": "windsurf-fast",
    }

    try:
        print("🔄 Sending Direct API request...")
        response = requests.post(url, headers=headers, json=payload, timeout=30)

        print(f"📊 Status Code: {response.status_code}")
        print(f"📊 Response Headers: {dict(response.headers)}")

        if response.status_code == 200:
            print("✅ Direct API Success!")
            print(f"📝 Response: {response.text[:500]}...")

            # Check for file creation
            await asyncio.sleep(2)
            if os.path.exists("/Users/dev/Documents/GitHub/atlastrinity/test_direct.txt"):
                print("✅ File created via Direct API!")
                return True
            print("⚠️ API worked but no file created")
            return True
        print(f"❌ Direct API Error: {response.status_code}")
        print(f"📝 Error Response: {response.text}")
        return False

    except Exception as e:
        print(f"❌ Exception: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_direct_api())
    if success:
        print("\n🎉 Direct API Mode: SUCCESS!")
    else:
        print("\n❌ Direct API Mode: FAILED")
