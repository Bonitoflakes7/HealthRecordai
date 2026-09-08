from fastapi.testclient import TestClient

from backend.app.core import config
from backend.app.main import app


def test_authentication_and_patient_isolation(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    monkeypatch.setattr(config.settings, "conversation_db_path", None)
    monkeypatch.setattr(config.settings, "auth_enabled", True)
    monkeypatch.setattr(config.settings, "auth_secret_key", "test-secret-key-012345678901234567890123")
    with TestClient(app) as client:
        assert client.get("/api/v1/records").status_code == 401
        first = client.post("/api/v1/auth/register", json={"username": "alice", "password": "correct horse battery"})
        second = client.post("/api/v1/auth/register", json={"username": "bob", "password": "correct horse battery"})
        alice = client.post("/api/v1/auth/token", data={"username": "alice", "password": "correct horse battery"}).json()["access_token"]
        bob = client.post("/api/v1/auth/token", data={"username": "bob", "password": "correct horse battery"}).json()["access_token"]
        record = client.post("/api/v1/records", headers={"Authorization": f"Bearer {alice}"}, files={"file": ("private.txt", b"private fatigue note", "text/plain")}).json()
        assert client.get("/api/v1/records", headers={"Authorization": f"Bearer {alice}"}).json()["total"] == 1
        assert client.get("/api/v1/records", headers={"Authorization": f"Bearer {bob}"}).json()["total"] == 0
        assert client.get(f"/api/v1/records/{record['id']}", headers={"Authorization": f"Bearer {bob}"}).status_code == 404
        events = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {alice}"}).json()["events"]
        assert any(event["action"] == "record.upload" for event in events)
        assert first.status_code == 201 and second.status_code == 201
