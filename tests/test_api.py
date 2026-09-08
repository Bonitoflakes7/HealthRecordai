from io import BytesIO

from fastapi.testclient import TestClient

from backend.app.core import config
from backend.app.main import app


def test_health(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["phase"] == "phase-11-security"


def test_text_upload_is_extracted_and_retrievable(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/v1/records", files={"file": ("notes.txt", BytesIO(b"blood pressure 120/80"), "text/plain")})
        record_id = response.json()["id"]
        fetched = client.get(f"/api/v1/records/{record_id}")
    assert response.status_code == 201
    assert response.json()["status"] == "extracted"
    assert fetched.json()["text"] == "blood pressure 120/80"
    assert fetched.json()["structured"]["observations"][0]["name"] == "blood_pressure"


def test_patient_identity_is_separate_from_owner_identity(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/records",
            files={"file": ("notes.txt", BytesIO(b"Patient ID: PAT-001\nBlood pressure 120/80"), "text/plain")},
        )
        record = response.json()

    assert response.status_code == 201
    assert record["owner_id"] == "dev-user"
    assert record["patient_id"] == "PAT-001"
    assert record["structured"]["patient_id"] == "PAT-001"


def test_patient_id_form_value_is_validated(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/records",
            data={"patient_id": "Patient Name"},
            files={"file": ("notes.txt", BytesIO(b"hello"), "text/plain")},
        )

    assert response.status_code == 400
    assert "patient_id" in response.json()["detail"]


def test_search_returns_citation_for_extracted_text(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    with TestClient(app) as client:
        client.post("/api/v1/records", files={"file": ("notes.txt", BytesIO(b"The patient reports persistent fatigue."), "text/plain")})
        response = client.get("/api/v1/search", params={"q": "persistent fatigue"})
    assert response.status_code == 200
    assert response.json()["results"][0]["citation_id"].endswith("#chunk-0")


def test_ask_returns_grounded_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    with TestClient(app) as client:
        client.post("/api/v1/records", files={"file": ("notes.txt", BytesIO(b"The patient reports persistent fatigue."), "text/plain")})
        response = client.post("/api/v1/ask", json={"question": "What did the patient report?"})
    assert response.status_code == 200
    assert response.json()["mode"] == "extractive"
    assert response.json()["citations"][0]["citation_id"].endswith("#chunk-0")
    assert response.json()["conversation_id"]
    assert response.json()["citation_validation"]["status"] == "passed"


def test_urgent_question_is_stopped_before_retrieval(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/v1/ask", json={"question": "I have chest pain and can't breathe"})
    assert response.status_code == 200
    assert response.json()["mode"] == "safety"
    assert response.json()["safety_level"] == "urgent"
    assert "possible_emergency" in response.json()["safety_flags"]


def test_timeline_contains_normalized_record(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    with TestClient(app) as client:
        client.post(
            "/api/v1/records",
            files={"file": ("lab.txt", b"LABORATORY REPORT\n2026-01-14\nBlood pressure: 120/80", "text/plain")},
        )
        response = client.get("/api/v1/timeline")
    assert response.status_code == 200
    assert response.json()["events"][0]["document_type"] == "lab_report"


def test_analytics_returns_trend_and_signal(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    with TestClient(app) as client:
        client.post("/api/v1/records", files={"file": ("one.txt", b"LABORATORY REPORT\n2026-01-14\nBlood pressure: 190/121", "text/plain")})
        response = client.get("/api/v1/analytics")
    assert response.status_code == 200
    assert "blood_pressure_systolic" in [item["metric"] for item in response.json()["trends"]]
    assert response.json()["signals"][0]["code"] == "possible_severe_blood_pressure"


def test_invalid_pdf_is_marked_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/v1/records", files={"file": ("report.pdf", BytesIO(b"%PDF-fake"), "application/pdf")})
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


def test_upload_rejects_pdf_with_invalid_signature(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/v1/records", files={"file": ("report.pdf", BytesIO(b"not a pdf"), "application/pdf")})

    assert response.status_code == 400
    assert "signature" in response.json()["detail"]


def test_upload_rejects_mismatched_image_signature(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/v1/records", files={"file": ("scan.png", BytesIO(b"plain text"), "image/png")})

    assert response.status_code == 400
    assert "signature" in response.json()["detail"]


def test_upload_rejects_binary_text(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/v1/records", files={"file": ("notes.txt", BytesIO(b"hello\x00world"), "text/plain")})

    assert response.status_code == 400
    assert "binary" in response.json()["detail"]
