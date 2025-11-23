import requests
import json

BASE_URL = "http://localhost:8000/api"

def test_chat():
    print("Testing Chat Endpoint...")
    payload = {
        "message": "Hello, who are you?",
        "user_id": 1
    }
    try:
        response = requests.post(f"{BASE_URL}/chat", json=payload)
        if response.status_code == 200:
            data = response.json()
            print("✅ Chat endpoint working")
            print(f"   Response: {data['response']}")
        else:
            print(f"❌ Chat endpoint failed: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ Chat endpoint error: {e}")

if __name__ == "__main__":
    test_chat()
