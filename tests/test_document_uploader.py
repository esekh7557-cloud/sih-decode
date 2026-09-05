from pathlib import Path

from app.guided_services.document_uploader import (
    _document_label_for_filename,
    _matching_documents,
    _portal_row_aliases,
    document_source_directory,
    missing_required_sections,
)
from app.guided_services import document_uploader
from app.main import _canonical_scan_filename


def test_selected_document_type_can_name_a_random_uploaded_file():
    assert _canonical_scan_filename("Aadhaar Card", "IMG_1234.jpg") == "aadharcard.jpg"
    assert _canonical_scan_filename("Birth Certificate", "phone-photo.webp") == "birthcertificate.webp"
    assert _canonical_scan_filename("Affidavit on stamp paper", "scan.png") == "affidavit.png"
    assert _canonical_scan_filename("Residence Proof", "scan.pdf") == "residencecertificate.pdf"


def test_uploader_recognises_canonical_documents():
    assert _document_label_for_filename(Path("aadharcard.jpg")) == "Aadhaar Card"
    assert _document_label_for_filename(Path("birthcertificate.png")) == "Birth Certificate"
    assert _document_label_for_filename(Path("residencecertificate.webp")) == "Residence Certificate"


def test_uploader_recognises_descriptive_document_library_filenames():
    assert _document_label_for_filename(Path("Affidavit on a stamp paper.png")) == "Affidavit"
    assert _document_label_for_filename(Path("PAN card - Id proof.jpg")) == "PAN Card"


def test_configured_document_source_overrides_session_scan_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("JANSEVA_DOCUMENT_SOURCE_DIR", str(tmp_path))
    assert document_source_directory("session-id") == tmp_path


def test_session_scans_are_preferred_over_the_shared_document_library(monkeypatch, tmp_path):
    monkeypatch.delenv("JANSEVA_DOCUMENT_SOURCE_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    session_folder = tmp_path / "scans" / "session-id"
    session_folder.mkdir(parents=True)

    assert document_source_directory("session-id") == session_folder


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


def test_all_required_portal_sections_need_one_supported_document(tmp_path):
    for filename in (
        "affidavit_on_stamp_paper.pdf",
        "birthcertificate.jpg",
        "aadharcard.jpg",
        "photograph.jpg",
        "electricitybill.pdf",
    ):
        (tmp_path / filename).write_bytes(b"document")

    assert missing_required_sections(_matching_documents(tmp_path)) == []

    (tmp_path / "photograph.jpg").unlink()
    assert missing_required_sections(_matching_documents(tmp_path)) == ["Photograph"]


def test_uploader_reports_non_requested_portal_documents_as_skipped(monkeypatch, tmp_path):
    """A service can ask for fewer documents than exist in the shared library."""
    for filename in ("aadharcard.jpg", "birthcertificate.jpg", "photograph.jpg"):
        (tmp_path / filename).write_bytes(b"document")

    class FakeDriver:
        window_handles = []
        title = "Goa Online"

    from selenium import webdriver

    outcomes = iter(
        (
            ("uploaded", ""),
            ("skipped", "The current portal form does not request this document."),
            ("failed", "The portal upload dialog has no Save or Submit button."),
            ("failed", "The portal upload dialog has no Save or Submit button."),
        )
    )
    monkeypatch.setattr(webdriver, "Edge", lambda options: FakeDriver())
    monkeypatch.setattr(document_uploader.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        document_uploader,
        "_upload_single_document",
        lambda *args: next(outcomes),
    )

    result = document_uploader.upload_documents(tmp_path)

    assert result["uploaded"] == 1
    assert result["failed"] == 1
    assert result["skipped"] == 1
    assert result["failed_documents"] == ["Photograph"]
    assert result["skipped_documents"] == ["Birth Certificate"]
    assert result["failure_details"] == {
        "Photograph": "The portal upload dialog has no Save or Submit button."
    }
