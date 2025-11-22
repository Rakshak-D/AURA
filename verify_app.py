import requests
import time
import sys

BASE_URL = "http://localhost:8000"

def test_health():
    print("Testing Health/Root...")
    try:
        response = requests.get(BASE_URL + "/")
        if response.status_code == 200:
            print("✅ Root endpoint accessible")
        else:
            print(f"❌ Root endpoint failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Root endpoint error: {e}")

def test_tasks():
    print("\nTesting Tasks API...")
    try:
        # Create Task
        task_data = {
            "title": "Test Task",
            "description": "This is a test task",
            "priority": "high"
        }
        response = requests.post(BASE_URL + "/api/tasks", json=task_data)
        if response.status_code == 200:
            task = response.json()
            print(f"✅ Task created: {task['id']}")
            
            # List Tasks
            response = requests.get(BASE_URL + "/api/tasks")
            tasks = response.json()
            if len(tasks) > 0:
                print(f"✅ Tasks listed: {len(tasks)} found")
            else:
                print("❌ No tasks found after creation")
                
            # Delete Task
            requests.delete(f"{BASE_URL}/api/tasks/{task['id']}")
            print("✅ Task deleted")
        else:
            print(f"❌ Task creation failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Tasks API error: {e}")

def test_chat():
    print("\nTesting Chat API...")
    try:
        chat_data = {"message": "Hello, who are you?"}
        response = requests.post(BASE_URL + "/api/chat", json=chat_data)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Chat response: {data['response'][:50]}...")
        else:
            print(f"❌ Chat failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Chat API error: {e}")

def test_analytics():
    print("\nTesting Analytics API...")
    try:
        response = requests.get(BASE_URL + "/api/analytics")
        if response.status_code == 200:
            print("✅ Analytics loaded")
        else:
            print(f"❌ Analytics failed: {response.status_code}")
    except Exception as e:
        print(f"❌ Analytics API error: {e}")

if __name__ == "__main__":
    # Wait for server to start
    print("Waiting for server to be ready...")
    for i in range(10):
        try:
            requests.get(BASE_URL + "/")
            break
        except:
            time.sleep(1)
    
    test_health()
    test_tasks()
    test_chat()
    test_analytics()
