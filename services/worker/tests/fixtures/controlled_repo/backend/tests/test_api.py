from backend.app import app, TASKS_STORE

def test_health_check():
    from fastapi.testclient import TestClient
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_list_tasks():
    from fastapi.testclient import TestClient
    client = TestClient(app)
    response = client.get("/tasks")
    assert response.status_code == 200
    assert "tasks" in response.json()
    assert len(response.json()["tasks"]) >= 2
