import sys
import os
import pytest
from fastapi.testclient import TestClient

# 프로젝트 루트 경로 설정
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app, save_data, load_data, TodoItem

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_and_teardown():
    # 테스트 전 초기화
    save_data([])
    yield
    # 테스트 후 정리
    save_data([])

def test_get_todos_empty():
    response = client.get("/todos")
    assert response.status_code == 200
    assert response.json() == []

def test_get_todos_with_items():
    todo = TodoItem(title="Test", description="Test description", completed=False, tags=[])
    save_data([{"id": 1, **todo.dict()}])
    response = client.get("/todos")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Test"

def test_create_todo():
    todo = {
        "title": "Test",
        "description": "Test description",
        "completed": False,
        "tags": []
    }
    response = client.post("/todos", json=todo)
    assert response.status_code == 200
    assert response.json()["title"] == "Test"

def test_create_todo_invalid():
    # 누락된 필드 (description 등)
    todo = {"title": "Test"}
    response = client.post("/todos", json=todo)
    assert response.status_code == 422

def test_update_todo():
    todo = TodoItem(title="Test", description="Test description", completed=False, tags=[])
    save_data([{"id": 1, **todo.dict()}])
    updated_todo = {
        "title": "Updated",
        "description": "Updated description",
        "completed": True,
        "tags": ["updated"]
    }
    response = client.put("/todos/1", json=updated_todo)
    assert response.status_code == 200
    assert response.json()["title"] == "Updated"

def test_update_todo_not_found():
    updated_todo = {
        "title": "Updated",
        "description": "Updated description",
        "completed": True,
        "tags": []
    }
    response = client.put("/todos/1", json=updated_todo)
    assert response.status_code == 404

def test_delete_todo():
    todo = TodoItem(title="Test", description="Test description", completed=False, tags=[])
    save_data([{"id": 1, **todo.dict()}])
    response = client.delete("/todos/1")
    assert response.status_code == 200
    assert response.json()["message"] == "Todo deleted successfully"

def test_delete_todo_not_found():
    response = client.delete("/todos/1")
    assert response.status_code == 200
    assert response.json()["message"] == "Todo deleted successfully"
