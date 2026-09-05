from pathlib import Path

from app.guided_services.document_uploader import (
    _document_label_for_filename,
    _matching_documents,
    _portal_row_aliases,
)
from app.main import _canonical_scan_filename


def test_selected_document_type_can_name_a_random_uploaded_file():
    assert _canonical_scan_filename("Aadhaar Card", "IMG_1234.jpg") == "aadharcard.jpg"
    assert _canonical_scan_filename("Birth Certificate", "phone-photo.webp") == "birthcertificate.webp"


def test_uploader_recognises_canonical_documents():
    assert _document_label_for_filename(Path("aadharcard.jpg")) == "Aadhaar Card"
    assert _document_label_for_filename(Path("birthcertificate.png")) == "Birth Certificate"
    assert _document_label_for_filename(Path("residencecertificate.webp")) == "Residence Certificate"


def test_identity_proof_row_alias_is_supported():
    assert "identity proof" in _portal_row_aliases("Aadhaar Card")


def test_duplicate_document_scans_are_uploaded_once_per_portal_category(tmp_path):
    older = tmp_path / "aadharcard.jpg"
    newer = tmp_path / "aadharcard.jpeg"
    older.write_bytes(b"old")
    newer.write_bytes(b"new")

    matches = _matching_documents(tmp_path)

    assert len(matches) == 1
    assert matches[0][0] == "Aadhaar Card"
    assert matches[0][1].endswith("aadharcard.jpeg")
