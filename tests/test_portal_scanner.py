import pytest

from app.services import portal_scanner


def test_scanner_explains_goa_error_registration_id(monkeypatch):
    monkeypatch.setattr(
        portal_scanner,
        "evaluate_open_form",
        lambda expression, port: {
            "title": "Some Error",
            "text": "Sorry could not process your request !! Error Registration Id: 6176864",
            "fields": [],
            "documents": [],
            "url": "https://services.goaonline.gov.in/expired",
        },
    )
    with pytest.raises(RuntimeError, match=r"registration ID 6176864"):
        portal_scanner.scan_open_form(9222)
