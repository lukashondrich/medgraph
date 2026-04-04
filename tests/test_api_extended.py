"""Tests for extended API endpoints (Phase 5).

Covers patient gallery endpoints and patient-aware chat.
"""

import pytest
from fastapi.testclient import TestClient

from src.api import app


@pytest.fixture
def client():
    return TestClient(app)


class TestPatientEndpoints:
    def test_get_patients_returns_list(self, client):
        resp = client.get("/api/patients")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 5

    def test_get_patients_has_required_fields(self, client):
        resp = client.get("/api/patients")
        data = resp.json()
        for p in data:
            assert "patient_id" in p
            assert "name" in p
            assert "headline" in p

    def test_get_patient_by_id(self, client):
        # Get gallery first to find a valid ID
        gallery = client.get("/api/patients").json()
        patient_id = gallery[0]["patient_id"]

        resp = client.get(f"/api/patients/{patient_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == patient_id
        assert "conditions" in data
        assert "medications" in data

    def test_get_nonexistent_patient_404(self, client):
        resp = client.get("/api/patients/nonexistent-uuid")
        assert resp.status_code == 404

    def test_health_check(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestChatWithPatient:
    def test_chat_accepts_patient_id(self, client):
        """POST /api/chat accepts patient_id field without error."""
        # We won't actually run the full pipeline (requires LLM),
        # just verify the endpoint accepts the parameter
        from unittest.mock import patch, AsyncMock
        import json

        router_resp = AsyncMock()
        router_resp.choices = [AsyncMock()]
        router_resp.choices[0].message.content = json.dumps({
            "agents": ["symptom"],
            "reasoning": "test",
            "confidence": 0.9,
        })

        specialist_resp = AsyncMock()
        specialist_resp.choices = [AsyncMock()]
        specialist_resp.choices[0].message.content = "Test symptom response"

        synth_resp = AsyncMock()
        synth_resp.choices = [AsyncMock()]
        synth_resp.choices[0].message.content = "Final response"

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock:
            mock.side_effect = [router_resp, specialist_resp, synth_resp]

            gallery = client.get("/api/patients").json()
            patient_id = gallery[0]["patient_id"]

            resp = client.post("/api/chat", json={
                "message": "Should I take ibuprofen?",
                "patient_id": patient_id,
            })
            assert resp.status_code == 200
