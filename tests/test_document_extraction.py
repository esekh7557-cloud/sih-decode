import asyncio

from fastapi.testclient import TestClient

import app.main as main
from app.core.profile import verhoeff_generate
from app.ocr.scanner import ScanResult


def _valid_aadhaar() -> str:
    stem = "23456789012"
    return stem + verhoeff_generate(stem)


def test_scan_handles_numeric_aadhaar_from_model(monkeypatch):
    aadhaar = _valid_aadhaar()

    class Scanner:
        async def scan(self, *args, **kwargs):
            return ScanResult(
                document_type="Aadhaar Card",
                raw_text="{}",
                fields={"aadhaar_number": int(aadhaar), "name": "Test Citizen"},
                confidence=0.95,
            )

    monkeypatch.setattr(main, "get_scanner", lambda: Scanner())
    client = TestClient(main.app)
    session_id = client.post("/sessions").json()["session_id"]

    response = client.post(
        f"/sessions/{session_id}/scan",
        json={
            "expected_type": "Aadhaar Card",
            "document_types": ["Aadhaar Card", "Identity Proof"],
            "images": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["summary"]["aadhaar"] == "XXXX XXXX " + aadhaar[-4:]
    saved_types = {item["document_type"] for item in main.store.get(session_id).document_extractions}
    assert saved_types == {"Aadhaar Card", "Identity Proof"}


def test_mock_extraction_mode_does_not_call_openrouter(monkeypatch):
    monkeypatch.setenv("JANSEVA_EXTRACTION_MODE", "mock")
    scanner = main.get_scanner()

    result = asyncio.run(scanner.scan("Aadhaar Card", images=["not-used-in-mock-mode"]))

    assert result.confidence == 0.95
    assert result.fields["name"] == "Demo Citizen"
