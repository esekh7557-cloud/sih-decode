from fastapi.testclient import TestClient

import app.main as main


def test_guided_services_page_and_assets_are_served_by_main_app():
    client = TestClient(main.app)

    page = client.get("/guided-services")
    css = client.get("/guided-services/style.css")
    javascript = client.get("/guided-services/app.js")

    assert page.status_code == 200
    assert "/guided-services/app.js" in page.text
    assert css.status_code == 200
    assert javascript.status_code == 200
    assert 'const API = "/guided-services"' in javascript.text


def test_guided_services_reuses_main_session(monkeypatch):
    monkeypatch.setenv("JANSEVA_EXTRACTION_MODE", "mock")
    client = TestClient(main.app)

    created = client.post("/sessions").json()
    session_id = created["session_id"]

    guided_session = client.get(f"/guided-services/sessions/{session_id}")

    assert guided_session.status_code == 200
    assert guided_session.json()["session_id"] == session_id


def test_guided_scan_updates_the_shared_main_profile(monkeypatch):
    monkeypatch.setenv("JANSEVA_EXTRACTION_MODE", "mock")
    client = TestClient(main.app)
    session_id = client.post("/sessions").json()["session_id"]

    response = client.post(
        f"/guided-services/sessions/{session_id}/scan",
        json={
            "expected_type": "Aadhaar Card",
            "images": [{"name": "demo.png", "data": "data:image/png;base64,AA=="}],
        },
    )

    assert response.status_code == 200
    assert response.json()["summary"]["name"] == "Demo Citizen"
    assert main.store.get(session_id).profile.name == "Demo Citizen"


def test_dashboard_upload_uses_the_guided_services_automation(monkeypatch):
    client = TestClient(main.app)
    session_id = client.post("/sessions").json()["session_id"]
    monkeypatch.setattr(
        "app.guided_services.document_uploader._matching_documents",
        lambda _: [
            ("Affidavit", "C:/scans/affidavit.pdf"),
            ("Birth Certificate", "C:/scans/birthcertificate.jpg"),
            ("Aadhaar Card", "C:/scans/aadharcard.jpg"),
            ("Photograph", "C:/scans/photograph.jpg"),
            ("Electricity Bill", "C:/scans/electricitybill.pdf"),
        ],
    )
    monkeypatch.setattr(
        "app.guided_services.document_uploader.upload_documents",
        lambda *_: {"found": 5, "uploaded": 5, "failed": 0, "failed_documents": []},
    )

    response = client.post(f"/sessions/{session_id}/automate_upload")

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert client.get(f"/sessions/{session_id}/upload-status").status_code == 200
    assert client.post("/guided-services/sessions/missing/automate_upload").status_code == 404
    assert client.post("/guided-services/api/analyze-form").status_code == 404
    assert client.post("/guided-services/api/execute-form").status_code == 404


def test_upload_requires_one_document_for_each_required_section(monkeypatch):
    client = TestClient(main.app)
    session_id = client.post("/sessions").json()["session_id"]
    monkeypatch.setattr(
        "app.guided_services.document_uploader._matching_documents",
        lambda _: [("Aadhaar Card", "C:/scans/aadharcard.jpg")],
    )

    response = client.post(f"/sessions/{session_id}/automate_upload")

    assert response.status_code == 400
    assert "Affidavit on stamp paper" in response.json()["detail"]
    assert "Residence Proof" in response.json()["detail"]


def test_dashboard_launches_the_debug_browser_used_by_upload(monkeypatch):
    client = TestClient(main.app)
    session_id = client.post("/sessions").json()["session_id"]
    client.post(f"/sessions/{session_id}/service", json={"service_id": "CERT_INC"})
    monkeypatch.setattr(
        "app.guided_services.router.guided_launch_browser",
        lambda sid, body: {"status": "success", "message": "Browser launched", "service_id": body.service_id},
    )

    response = client.post(
        f"/sessions/{session_id}/launch_browser",
        json={"service_id": "CERT_INC"},
    )

    assert response.status_code == 200
    assert response.json()["service_id"] == "CERT_INC"


def test_guided_upload_status_starts_idle_for_a_valid_session():
    client = TestClient(main.app)
    session_id = client.post("/guided-services/sessions").json()["session_id"]

    response = client.get(f"/guided-services/sessions/{session_id}/upload-status")

    assert response.status_code == 200
    assert response.json()["status"] == "idle"


def test_guided_launch_browser_uses_selected_service_portal_url(monkeypatch, tmp_path):
    client = TestClient(main.app)
    session_id = client.post("/guided-services/sessions").json()["session_id"]
    client.post(
        f"/guided-services/sessions/{session_id}/service",
        json={"service_id": "CERT_INC"},
    )
    captured = {}

    monkeypatch.setattr(
        "app.guided_services.router._automation_profile_dir",
        lambda: tmp_path / "edge-profile",
    )
    monkeypatch.setattr(
        "app.guided_services.router.shutil.which",
        lambda _: r"C:\\Microsoft\\Edge\\msedge.exe",
    )

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs

    monkeypatch.setattr("app.guided_services.router.subprocess.Popen", fake_popen)

    response = client.post(f"/guided-services/sessions/{session_id}/launch_browser")

    assert response.status_code == 200
    assert captured["command"][-1] == (
        "https://goaonline.gov.in/Appln/UIL/deptServices"
        "?__DocId=REV&__ServiceId=REV07"
    )
    assert captured["kwargs"]["shell"] is False


def test_residence_certificate_uses_rev05_portal_url():
    assert main._portal_url(main._application_service("RESIDENCE")) == (
        "https://goaonline.gov.in/Appln/UIL/deptServices?__DocId=REV&__ServiceId=REV05"
    )


def test_income_required_fields_include_types_and_choices():
    client = TestClient(main.app)
    session_id = client.post("/guided-services/sessions").json()["session_id"]

    response = client.get(
        f"/guided-services/sessions/{session_id}/required-fields?service_id=CERT_INC"
    )

    assert response.status_code == 200
    fields = {field["key"]: field for field in response.json()["fields"]}
    assert {"name", "purpose", "annual_income", "id_proof_type", "certify"} <= fields.keys()
    assert fields["applying_for"]["type"] == "select"
    assert fields["applying_for"]["options"][0]["label"] == "Self"
    assert fields["purpose"]["type"] == "text"
    assert fields["purpose"]["options"] == []
    assert fields["annual_income"]["type"] == "number"
    assert fields["previous_certificate"]["type"] == "radio"
