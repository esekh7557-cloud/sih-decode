"""Routes for the integrated standalone guided-services experience.

The router is mounted under ``/guided-services`` but deliberately uses the
main application's session store and shared profile/OCR/document services.
The standalone automation tools live in this package and are only reachable
through this namespace.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field


router = APIRouter(prefix="/guided-services", tags=["guided-services"])
_FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "guided-services"
_GUIDED_STATES = {"Goa", "Other"}
_UPLOAD_JOBS: dict[str, dict[str, Any]] = {}
_UPLOAD_JOBS_LOCK = threading.Lock()


def _main():
    # Import lazily so app.main can include this router after its shared
    # application state and route functions have been defined.
    from app import main

    return main


def _automation_profile_dir() -> Path:
    return Path(
        os.getenv(
            "JANSEVA_BROWSER_PROFILE_DIR",
            str(Path.cwd() / ".janseva-browser" / "edge-debug-profile"),
        )
    ).expanduser()


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
def guided_services_page():
    return FileResponse(str(_FRONTEND / "index.html"), headers=_main().NO_CACHE)


@router.get("/style.css", include_in_schema=False)
def guided_services_css():
    return FileResponse(
        str(_FRONTEND / "style.css"),
        media_type="text/css",
        headers=_main().NO_CACHE,
    )


@router.get("/app.js", include_in_schema=False)
def guided_services_js():
    return FileResponse(
        str(_FRONTEND / "app.js"),
        media_type="application/javascript",
        headers=_main().NO_CACHE,
    )


@router.get("/i18n.js", include_in_schema=False)
def guided_services_i18n_js():
    return FileResponse(
        _FRONTEND.parent / "i18n.js",
        media_type="application/javascript",
        headers=_main().NO_CACHE,
    )


@router.get("/health")
def guided_services_health():
    return {
        "status": "ok",
            "service": "Saarthi integrated guided services",
        "guided_services_version": "integrated",
    }


class LanguageIn(BaseModel):
    language: str


class StateIn(BaseModel):
    state: str


class ServiceIn(BaseModel):
    service_id: str


class ScanChatIn(BaseModel):
    user_answer: str
    expected_type: str | None = None


class ImageItem(BaseModel):
    name: str
    data: str


class ScanIn(BaseModel):
    expected_type: Optional[str] = None
    document_types: List[str] = Field(default_factory=list)
    images: Optional[List[Union[str, ImageItem, Dict[str, Any]]]] = None


class DirectExtractIn(BaseModel):
    images: list[str]
    model: str | None = None


class UploadDocsIn(BaseModel):
    folder: str = str(Path.cwd() / "data")
    port: int = 9222


class FormFillIn(BaseModel):
    port: int = 9222
    certificate_type: str = "income_certificate"
    data: Dict[str, Any] = Field(default_factory=dict)


class BrowserLaunchIn(BaseModel):
    # Keep this optional for callers of the original guided-services page;
    # the selected service on the server remains the fallback source of truth.
    service_id: Optional[str] = None


@router.get("/services")
def guided_services_list(state: str = Query(None)):
    if state and state not in _GUIDED_STATES:
        raise HTTPException(400, "Choose Goa or Other")

    # Existing services are currently Goa services.
    built_in = [] if state == "Other" else _main().api_list_services(state)
    return built_in
@router.get("/sessions/{sid}")
def guided_get_session(sid: str):
    return _main().get_session(sid)


@router.post("/sessions")
def guided_create_session():
    return _main().create_session()


@router.post("/sessions/{sid}/language")
def guided_set_language(sid: str, body: LanguageIn):
    return _main().set_language(sid, body)


@router.post("/sessions/{sid}/state")
def guided_set_state(sid: str, body: StateIn):
    return _main().set_state(sid, body)


@router.post("/sessions/{sid}/service")
def guided_select_service(sid: str, body: ServiceIn):
    return _main().select_service(sid, body)


@router.post("/sessions/{sid}/checklist/confirm")
def guided_confirm_checklist(sid: str):
    return _main().confirm_checklist(sid)


@router.post("/sessions/{sid}/scan_chat")
async def guided_scan_chat(sid: str, body: ScanChatIn):
    return await _main().scan_chat(sid, body)


@router.post("/sessions/{sid}/scan")
async def guided_scan(sid: str, body: ScanIn):
    return await _main().scan(sid, body)


@router.post("/api/extract")
async def guided_extract_documents(body: DirectExtractIn):
    return await _main().extract_documents(body)


@router.post("/sessions/{sid}/profile")
async def guided_update_profile(sid: str, updates: dict):
    return await _main().update_profile(sid, updates)


@router.post("/sessions/{sid}/confirm")
def guided_confirm_and_deliver(sid: str, purpose: str = ""):
    return _main().confirm_and_deliver(sid, purpose)


@router.get("/sessions/{sid}/gaps")
def guided_get_gaps(sid: str):
    return _main().get_gaps(sid)


@router.get("/sessions/{sid}/required-fields")
def guided_required_fields(sid: str, service_id: str | None = None):
    session = _main()._session(sid)
    if service_id and service_id != session.service_id:
        _main()._application_service(service_id)
        return _main().required_application_fields(service_id, session.profile)
    return _main().get_gaps(sid)


@router.post("/sessions/{sid}/another")
def guided_another_task(sid: str):
    return _main().another_task(sid)


@router.delete("/sessions/{sid}")
def guided_end_session(sid: str):
    return _main().end_session(sid)


@router.post("/sessions/{sid}/launch_browser")
def guided_launch_browser(sid: str, body: BrowserLaunchIn | None = None):
    main = _main()
    session = main._session(sid)
    try:
        service_id = (body.service_id if body else None) or session.service_id
        if not service_id:
            raise HTTPException(400, "Select a government service before opening its official portal")

        service = main._application_service(service_id)
        url = main._portal_url(service)
        if not url:
            raise HTTPException(503, "The selected government service does not have an official portal URL configured")

        profile_dir = _automation_profile_dir()
        profile_dir.mkdir(parents=True, exist_ok=True)
        # Pass the URL as its own process argument.  The Income Certificate
        # URL contains an ampersand in its query string; a shell command can
        # interpret that character as a command separator on Windows.
        edge_candidates = [shutil.which("msedge.exe")]
        for root in (
            os.getenv("PROGRAMFILES"),
            os.getenv("PROGRAMFILES(X86)"),
            os.getenv("LOCALAPPDATA"),
        ):
            if root:
                edge_candidates.append(
                    str(Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe")
                )
        edge = next(
            (candidate for candidate in edge_candidates if candidate and Path(candidate).is_file()),
            "msedge.exe",
        )
        command = [
            edge,
            "--new-window",
            "--remote-debugging-port=9222",
            f"--user-data-dir={profile_dir}",
            url,
        ]
        subprocess.Popen(command, shell=False)
        return {"status": "success", "message": "Browser launched"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Failed to launch browser: {exc}") from exc


@router.get("/sessions/{sid}/automate_fill/requirements")
def guided_automate_fill_requirements(sid: str):
    _main()._session(sid)
    from app.guided_services.form_filler import default_form_data, missing_form_data

    data = default_form_data()
    missing = [{**item, "missing": True} for item in missing_form_data(data)]
    return {"fields": missing, "missing_fields": [item["key"] for item in missing]}


@router.post("/sessions/{sid}/automate_fill")
def guided_automate_fill(sid: str, body: FormFillIn):
    _main()._session(sid)
    from app.guided_services.form_filler import fill_form

    threading.Thread(
        target=fill_form,
        args=(sid, body.port, body.certificate_type, body.data),
        daemon=True,
    ).start()
    return {"action": "filling", "message": "Selenium form filling started"}


@router.post("/sessions/{sid}/automate_upload")
def guided_automate_upload(sid: str):
    _main()._session(sid)
    from app.guided_services.document_uploader import _matching_documents, upload_documents

    scan_dir = str(Path.cwd() / "scans" / sid)
    if not _matching_documents(Path(scan_dir)):
        raise HTTPException(
            400,
            "No recognised scanned documents are available. Add and extract a labelled document before uploading.",
        )

    with _UPLOAD_JOBS_LOCK:
        previous = _UPLOAD_JOBS.get(sid, {})
        if previous.get("status") == "running":
            return {"action": "uploading", "status": "running", "message": "Document upload is already running"}
        _UPLOAD_JOBS[sid] = {"status": "running", "result": None, "error": None}

    def run_upload():
        try:
            result = upload_documents(scan_dir, 9222)
            with _UPLOAD_JOBS_LOCK:
                _UPLOAD_JOBS[sid] = {"status": "completed", "result": result, "error": None}
        except Exception as exc:
            print(f"Upload failed: {exc}")
            with _UPLOAD_JOBS_LOCK:
                _UPLOAD_JOBS[sid] = {"status": "failed", "result": None, "error": str(exc)}

    threading.Thread(target=run_upload, daemon=True).start()
    return {"action": "uploading", "status": "running"}


@router.get("/sessions/{sid}/upload-status")
def guided_upload_status(sid: str):
    _main()._session(sid)
    with _UPLOAD_JOBS_LOCK:
        status = _UPLOAD_JOBS.get(sid)
        return status or {"status": "idle", "result": None, "error": None}


@router.post("/api/upload_documents")
def guided_upload_documents(body: UploadDocsIn):
    from app.guided_services.document_uploader import upload_documents

    def run_upload():
        try:
            upload_documents(body.folder, body.port)
        except Exception as exc:
            print(f"Document upload failed: {exc}")

    threading.Thread(target=run_upload, daemon=True).start()
    return {
        "action": "uploading",
        "message": f"Document upload started from: {body.folder}",
        "instructions": [
            "Make sure Edge is started with --remote-debugging-port=9222",
            "Make sure you are on the Document Upload page",
            f"Files are being read from: {body.folder}",
        ],
    }
