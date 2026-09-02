"""JanSeva AI kiosk backend - FastAPI orchestrator for the six-state flow.

GREET -> IDENTIFY -> CHECKLIST -> SCAN -> FILL -> DELIVER

Responses follow the kiosk action protocol:
{"action": "speak|menu|ask|confirm|complete", ..., "language": "hi"}
"""
import os
import time
from pathlib import Path

# Load .env file automatically
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

from fastapi import FastAPI, HTTPException, Request, UploadFile, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Union, Any

from app.core.profile import mask_aadhaar, validate_mobile
from app.core.session import Session, SessionStore, State
from app.docgen.generator import generate_application, generate_schemes_sheet, OUTPUT_DIR
from app.eligibility.llm_enricher import enrich
from app.eligibility.rules import check_eligibility
from app.i18n.phrases import SUPPORTED, get_phrase
from app.ocr.scanner import CONFIDENCE_THRESHOLD, get_scanner
from app.printing.printer import make_qr, print_document
from app.services.catalog import build_checklist, get_service, list_services
from app.services.web_search import get_live_guidance, wants_live_search
from app.agent.analyzer import analyze_form
from app.agent.executor import execute_form_fill

app = FastAPI(title="JanSeva AI Kiosk", version="0.1.0")
store = SessionStore()

# --- CORS (allow frontend to call API) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Static files for generated output (PDFs, HTML, QR) and sample scans ---
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")
_SCANS_DIR = Path(__file__).resolve().parent.parent / "scans"
_SCANS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/scans", StaticFiles(directory=str(_SCANS_DIR)), name="scans")

# --- Serve frontend ---
_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate, max-age=0", "Pragma": "no-cache"}


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(str(_FRONTEND / "index.html"), headers=NO_CACHE)


@app.get("/style.css", include_in_schema=False)
def serve_css():
    return FileResponse(str(_FRONTEND / "style.css"), media_type="text/css", headers=NO_CACHE)


@app.get("/app.js", include_in_schema=False)
def serve_js():
    return FileResponse(str(_FRONTEND / "app.js"), media_type="application/javascript", headers=NO_CACHE)





# --- Utility endpoints ---

@app.get("/health")
def health():
    return {"status": "ok", "service": "JanSeva AI Kiosk"}


@app.get("/services")
def api_list_services(state: str = Query(None)):
    from app.services.catalog import list_services
    return [{"id": k, "label": v["name"]} for k, v in list_services(state).items()]


@app.get("/sessions/{sid}")
def get_session(sid: str):
    s = _session(sid)
    return {
        "session_id": s.id,
        "state": s.state.value,
        "language": s.language,
        "service_id": s.service_id,
        "completed": s.completed,
    }


def _session(sid: str) -> Session:
    s = store.get(sid)
    if s is None:
        raise HTTPException(404, "Session not found or already wiped")
    return s


# --- STATE 1: GREET ---------------------------------------------------------

@app.post("/sessions")
def create_session():
    s = store.create()
    return {
        "session_id": s.id,
        "action": "menu",
        "title": get_phrase("greeting"),
        "options": [{"id": lang, "label": lang} for lang in SUPPORTED],
        "language": "hi",
    }


class LanguageIn(BaseModel):
    language: str


@app.post("/sessions/{sid}/language")
def set_language(sid: str, body: LanguageIn):
    s = _session(sid)
    if body.language not in SUPPORTED:
        raise HTTPException(400, f"Unsupported language; choose one of {SUPPORTED}")
    s.language = body.language
    return {
        "action": "state_selection",
        "title": get_phrase("greeting", s.language),
        "language": s.language,
    }

class StateIn(BaseModel):
    state: str

@app.post("/sessions/{sid}/state")
def set_state(sid: str, body: StateIn):
    s = _session(sid)
    # Future logic: list_services can take body.state to filter by state catalog
    s.state = State.IDENTIFY
    return {
        "action": "menu",
        "options": [{"id": k, "label": v["name"]} for k, v in list_services().items()],
    }



# --- STATE 2 -> 3: IDENTIFY / CHECKLIST -------------------------------------

class ServiceIn(BaseModel):
    service_id: str


@app.post("/sessions/{sid}/service")
def select_service(sid: str, body: ServiceIn):
    s = _session(sid)
    if not get_service(body.service_id):
        raise HTTPException(404, "Unknown service")
    s.service_id = body.service_id
    s.state = State.CHECKLIST
    checklist = build_checklist(body.service_id, s.profile.occupation or None)
    return {
        "action": "confirm",
        "message": get_phrase("confirm", s.language),
        "summary": checklist,
        "language": s.language,
    }


@app.post("/sessions/{sid}/checklist/confirm")
def confirm_checklist(sid: str):
    s = _session(sid)
    s.state = State.SCAN
    return {
        "action": "ask",
        "question": get_phrase("consent", s.language),
        "input_type": "select",
        "language": s.language,
    }


# --- STATE 4: SCAN ----------------------------------------------------------

class ScanChatIn(BaseModel):
    user_answer: str
    expected_type: str | None = None

@app.post("/sessions/{sid}/scan_chat")
async def scan_chat(sid: str, body: ScanChatIn):
    s = _session(sid)
    s.chat_history.append({"role": "user", "content": body.user_answer})
    
    # Pass all images associated with this session so the AI can see the document context
    images = list(s.scans.values())
    result = await get_scanner().scan(body.expected_type, images=images, chat_history=s.chat_history)
    
    if result.confidence < CONFIDENCE_THRESHOLD:
        q = get_phrase("scan_request", s.language, doc=body.expected_type)
        s.chat_history.append({"role": "assistant", "content": q})
        return {
            "action": "ask",
            "questions": [q],
            "input_type": "scan",
            "language": s.language,
        }
        
    fields = dict(result.fields)
    if fields.get("action") == "ask":
        qs = fields.get("questions", [get_phrase("scan_request", s.language, doc=body.expected_type or "document")])
        if isinstance(qs, str):
            qs = [qs]
        elif not isinstance(qs, list):
            qs = [str(qs)]
            
        s.chat_history.append({"role": "assistant", "content": "\n".join(qs)})
        return {
            "action": "ask",
            "questions": qs,
            "input_type": "scan",
            "language": s.language,
        }
        
    aadhaar = fields.pop("aadhaar_number", None)
    if aadhaar:
        s.profile.set_aadhaar(aadhaar)
        fields["aadhaar"] = mask_aadhaar(aadhaar)
        
    for k, v in fields.items():
        if hasattr(s.profile, k) and v:
            try:
                setattr(s.profile, k, v)
            except Exception:
                pass
                
    if result.image_path:
        s.artifacts.append(result.image_path)
                
    return {
        "action": "speak",
        "text": get_phrase("scan_success", s.language),
        "summary": fields,
        "language": s.language,
    }


class ImageItem(BaseModel):
    name: str
    data: str

class ScanIn(BaseModel):
    expected_type: Optional[str] = None
    images: Optional[List[Union[str, ImageItem, Dict[str, Any]]]] = None

@app.post("/sessions/{sid}/scan")
async def scan(sid: str, body: ScanIn):
    s = _session(sid)
    
    # --- DEBUG ---
    scanner = get_scanner()
    print(f"[DEBUG SCAN] Scanner type: {type(scanner).__name__}")
    print(f"[DEBUG SCAN] images provided: {body.images is not None and len(body.images) if body.images else 0}")
    print(f"[DEBUG SCAN] expected_type: {body.expected_type}")
    # --- END DEBUG ---
    
    # --- Save all images locally for Stage 2 Upload and Future Use ---
    raw_b64_images = []
    if body.images and len(body.images) > 0:
        import base64
        import re
        scan_dir = Path.cwd() / "scans" / sid
        scan_dir.mkdir(parents=True, exist_ok=True)
        
        for idx, img_item in enumerate(body.images):
            try:
                # Handle both new format (dict/ImageItem) and old format (string)
                if isinstance(img_item, dict):
                    file_name = img_item.get("name", f"document_{idx}.png")
                    img_data = img_item.get("data", "")
                elif hasattr(img_item, "name") and hasattr(img_item, "data"):
                    file_name = img_item.name
                    img_data = img_item.data
                else:
                    file_name = f"{(body.expected_type or 'document').lower().replace(' ', '_')}_{idx}.png"
                    img_data = str(img_item)
                
                # Standardize common filenames
                clean_name = file_name.lower().replace(" ", "_")
                if "aadhaar" in clean_name or "aadhar" in clean_name:
                    clean_name = "aadharcard.png"
                elif "pan" in clean_name and "card" in clean_name:
                    clean_name = "pancard.png"
                
                # Avoid overwriting if same name exists by appending index if needed, 
                # but for Aadhaar/PAN we usually want to overwrite or keep them consistent.
                
                raw_b64_images.append(img_data)
                
                b64_data = img_data.split(",")[1] if "," in img_data else img_data
                decoded_img = base64.b64decode(b64_data)
                
                image_path = scan_dir / clean_name
                
                with open(image_path, "wb") as f:
                    f.write(decoded_img)
                    
                s.scans[clean_name] = str(image_path.absolute())
            except Exception as e:
                print(f"Failed to save scan locally: {e}")
    # -------------------------------------------------
    
    try:
        result = await get_scanner().scan(
            body.expected_type,
            images=raw_b64_images,
            chat_history=s.chat_history,
        )
    except Exception as e:
        raise HTTPException(
            502,
            "Document extraction is unavailable. Check OPENROUTER_API_KEY and install the project dependencies.",
        ) from e
    if result.confidence < CONFIDENCE_THRESHOLD:
        q = get_phrase("scan_request", s.language, doc=body.expected_type)
        s.chat_history.append({"role": "assistant", "content": q})
        return {
            "action": "ask",
            "questions": [q],
            "input_type": "scan",
            "language": s.language,
        }
    fields = dict(result.fields)
    if fields.get("action") == "ask":
        qs = fields.get("questions", [get_phrase("scan_request", s.language, doc=body.expected_type or "document")])
        if isinstance(qs, str):
            qs = [qs]
        elif not isinstance(qs, list):
            qs = [str(qs)]
            
        s.chat_history.append({"role": "assistant", "content": "\n".join(qs)})
        return {
            "action": "ask",
            "questions": qs,
            "input_type": "scan",
            "language": s.language,
        }
        
    aadhaar = fields.pop("aadhaar_number", None)
    if aadhaar:
        s.profile.set_aadhaar(aadhaar)
        fields["aadhaar"] = mask_aadhaar(aadhaar)
        
    for k, v in fields.items():
        if hasattr(s.profile, k) and v:
            try:
                setattr(s.profile, k, v)
            except Exception:
                pass

    profile_fields = set(type(s.profile).model_fields)
    ignored_extraction_fields = {"action", "questions", "document_type"}
    extra_fields = {
        key: value
        for key, value in fields.items()
        if key not in profile_fields and key not in ignored_extraction_fields and key != "aadhaar"
    }
    if extra_fields:
        s.document_extractions.append(
            {
                "document_type": body.expected_type or "Document",
                "fields": extra_fields,
            }
        )
                
    if result.image_path:
        s.artifacts.append(result.image_path)
    return {
        "action": "confirm",
        "message": get_phrase("confirm", s.language),
        "summary": fields,
        "extra_fields": extra_fields,
        "language": s.language,
    }


class DirectExtractIn(BaseModel):
    images: list[str]
    model: str | None = None

@app.post("/api/extract")
async def extract_documents(body: DirectExtractIn):
    """Direct standalone AI document information extractor."""
    from app.ocr.ai_extractor import extract_data_from_images
    return await extract_data_from_images(body.images, model=body.model)


@app.post("/sessions/{sid}/profile")
async def update_profile(sid: str, updates: dict):
    """Merge collected answers into the profile, then AUTOMATICALLY run the
    hybrid scheme eligibility check (rules first, optional LLM enrichment)."""
    s = _session(sid)
    if "mobile" in updates and updates["mobile"] and not validate_mobile(str(updates["mobile"])):
        raise HTTPException(400, "Invalid mobile number")
    if "aadhaar" in updates:
        if not s.profile.set_aadhaar(str(updates.pop("aadhaar"))):
            raise HTTPException(400, "Invalid Aadhaar number")
    data = s.profile.model_dump()
    data.update({k: v for k, v in updates.items() if k in data and k != "aadhaar_last4"})
    s.profile = type(s.profile).model_validate(data)

    results = check_eligibility(s.profile)
    results = await enrich(s.profile, results, s.language)
    s.eligibility = results
    s.state = State.FILL
    return {
        "action": "speak",
        "text": get_phrase("scheme_discovery", s.language, count=len(results)),
        "schemes_found": [r.__dict__ for r in results],
        "language": s.language,
    }


class AssistantIn(BaseModel):
    message: str


def _profile_gaps(profile) -> list[str]:
    """Return the most useful fields to collect before running scheme guidance."""
    fields = {
        "state": profile.state,
        "age": profile.age,
        "gender": profile.gender,
        "occupation": profile.occupation,
        "annual income": profile.annual_income,
    }
    return [name for name, value in fields.items() if value in (None, "")]


def _requested_matches(message: str, results: list) -> list:
    """Find eligible schemes that are explicitly mentioned in a citizen query."""
    normalized_message = " ".join(
        token for token in message.lower().replace("-", " ").split() if len(token) > 1
    )
    matches = []
    for result in results:
        scheme_words = [
            word for word in result.scheme_name.lower().replace("-", " ").split() if len(word) > 1
        ]
        if result.scheme_name.lower() in message.lower() or (
            scheme_words and len(set(scheme_words) & set(normalized_message.split())) >= min(2, len(scheme_words))
        ):
            matches.append(result)
    return matches


@app.post("/sessions/{sid}/assistant")
async def citizen_assistant(sid: str, body: AssistantIn):
    """Answer citizen intent with profile-aware, auditable scheme guidance.

    Rule-based results remain authoritative. The optional LLM enrichment can
    only add manually-verifiable candidates, as in the profile endpoint.
    """
    s = _session(sid)
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "Please enter a question or a scheme name")

    results = check_eligibility(s.profile)
    results = await enrich(s.profile, results, s.language)
    s.eligibility = results

    message_lower = message.lower()
    gaps = _profile_gaps(s.profile)
    service_terms = ("certificate", "certificates", "document", "income certificate", "residence", "caste")
    scheme_terms = ("scheme", "schemes", "yojana", "eligible", "eligibility", "benefit", "apply", "kisan", "awas", "ujjwala", "ayushman", "mudra", "scholarship")

    requested = _requested_matches(message, results)
    live_guidance = None
    if wants_live_search(message):
        live_guidance = await get_live_guidance(message, s.profile.state)

    if requested:
        reply = (
            f"You appear eligible for {', '.join(item.scheme_name for item in requested)}. "
            "Review the benefit and application route below before applying."
        )
    elif any(term in message_lower for term in service_terms):
        available = list_services(s.profile.state)
        reply = (
            "I can prepare a checklist for a certificate application. "
            f"Choose one of the {len(available)} available services in the Services panel."
        )
    elif any(term in message_lower for term in scheme_terms):
        if gaps:
            reply = (
                "I can give a more accurate recommendation after a few more details. "
                f"Please add: {', '.join(gaps)}. I have shown the current matches below."
            )
        elif results:
            reply = (
                f"Based on your details, I found {len(results)} scheme match"
                f"{'es' if len(results) != 1 else ''}. "
                "Each card explains why it matches and where to apply."
            )
        else:
            reply = (
                "I could not confirm a scheme match from the current rules. "
                "You can add more details or ask an operator to verify state-specific schemes."
            )
    else:
        reply = (
            "I can help you find schemes, understand a certificate checklist, or prepare an application. "
            "Try asking: 'Which schemes can I apply for?' or 'I need an income certificate.'"
        )

    if live_guidance:
        if live_guidance["sources"]:
            reply += " I found official websites and application steps below."
        else:
            reply += f" {live_guidance['notice']}"

    return {
        "action": "assistant",
        "reply": reply,
        "recommendations": [item.__dict__ for item in results],
        "profile_gaps": gaps,
        "services": [{"id": key, "label": value["name"]} for key, value in list_services(s.profile.state).items()],
        "live_guidance": live_guidance,
        "language": s.language,
    }


# --- STATE 5 -> 6: FILL / DELIVER --------------------------------------------

@app.post("/sessions/{sid}/confirm")
def confirm_and_deliver(sid: str, purpose: str = ""):
    """Citizen said 'haan, sab sahi hai': generate, print, deliver."""
    s = _session(sid)
    service = get_service(s.service_id or "") or {"name": "Application"}
    path = generate_application(service["name"], s.profile, purpose, s.language)
    s.artifacts.append(path)
    printed = print_document(path, copies=2)

    if s.eligibility:
        schemes_path = generate_schemes_sheet(s.eligibility, s.language)
        s.artifacts.append(schemes_path)
        print_document(schemes_path, copies=1)

    s.state = State.DELIVER
    s.completed = True
    resp = {
        "action": "complete",
        "summary": get_phrase("completion", s.language),
        "receipt": path,
        "schemes_found": [r.__dict__ for r in s.eligibility] if s.eligibility else [],
        "profile": s.profile.model_dump(),
        "language": s.language,
    }
    if not printed:
        import os
        base_url = os.getenv("JANSEVA_BASE_URL", "http://127.0.0.1:8080")
        filename = os.path.basename(path)
        download_url = f"{base_url}/output/{filename}"
        qr_path = make_qr(download_url)
        resp["qr"] = f"output/{os.path.basename(qr_path)}"
        resp["note"] = "Printer unavailable - scan QR to download the PDF"
    return resp











@app.post("/sessions/{sid}/automate_upload")
def trigger_upload_automation(sid: str):
    """Trigger physical kiosk OS automation to orchestrate file uploads."""
    s = _session(sid)
    
    from app.docgen.document_uploader import upload_documents
    import threading
    import os
    
    scan_dir = os.path.join(os.getcwd(), "scans", sid)
    
    def run_upload():
        try:
            upload_documents(scan_dir, 9222)
        except Exception as e:
            print(f"Upload failed: {e}")

    threading.Thread(target=run_upload, daemon=True).start()
    return {"action": "uploading"}
    return {"action": "uploading"}


@app.get("/sessions/{sid}/gaps")
def get_gaps(sid: str):
    """Return the missing fields required for the Goa portal."""
    s = _session(sid)
    required = [
        "applying_for", "purpose", "residence_period", "title", "name",
        "place_of_birth", "dob", "gender", "marital_status", "guardian_relation",
        "father_name", "mobile", "email", "occupation", "caste_category",
        "address", "locality", "district", "taluka", "village", "pincode",
        "family_size", "earning_members", "children_count", "previous_certificate",
        "immovable_property", "property_value", "other_income", "part_no",
        "serial_no", "electoral_year", "constituency", "ration_card",
        "property_details", "id_proof_type", "id_proof_no", "certify"
    ]
    data = s.profile.model_dump()
    missing = [k for k in required if data.get(k) in (None, "")]
    return {"missing_fields": missing}




@app.post("/sessions/{sid}/another")
def another_task(sid: str):
    s = _session(sid)
    s.restart_service()
    return {
        "action": "menu",
        "title": get_phrase("greeting", s.language),
        "options": [{"id": k, "label": v["name"]} for k, v in list_services().items()],
        "language": s.language,
    }


@app.delete("/sessions/{sid}")
def end_session(sid: str):
    """Wipe ALL citizen data: scans, PDFs, profile. Zero-PII audit log only."""
    s = store.get(sid)
    lang = s.language if s else "hi"
    store.wipe(sid)
    return {"action": "speak", "text": get_phrase("completion", lang), "language": lang}


# --- CUA AGENT ENDPOINTS ---------------------------------------------------

from app.agent.analyzer import analyze_form
from app.agent.executor import execute_form_fill
from pydantic import BaseModel
import shutil
import tempfile
from pathlib import Path
from fastapi import Request, HTTPException, UploadFile

class AnalyzeRequest(BaseModel):
    url: str

@app.post("/api/analyze-form")
async def api_analyze_form(req: AnalyzeRequest):
    """Trigger the CUA to navigate to the URL and extract the form schema."""
    try:
        schema = await analyze_form(req.url)
        return schema.model_dump()
    except Exception as e:
        raise HTTPException(500, f"Failed to analyze form: {str(e)}")

@app.post("/api/execute-form")
async def api_execute_form(request: Request):
    """Trigger the CUA to fill the form using the provided structured data."""
    try:
        form = await request.form()
        url = form.get("url")
        if not url:
            raise HTTPException(400, "URL is required")
            
        data = {}
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            
            for key, value in form.multi_items():
                if key == "url":
                    continue
                if isinstance(value, UploadFile):
                    if value.filename:
                        safe_name = Path(value.filename).name
                        temp_file_path = temp_dir_path / safe_name
                        with open(temp_file_path, "wb") as f:
                            shutil.copyfileobj(value.file, f)
                        data[key] = str(temp_file_path.absolute())
                    else:
                        data[key] = ""
                else:
                    data[key] = value
                    
            result = await execute_form_fill(str(url), data)
            
        return {"status": "success", "message": result}
    except Exception as e:
        raise HTTPException(500, f"Failed to execute form fill: {str(e)}")


class UploadDocsIn(BaseModel):
    folder: str = r"C:\Users\Vedant\Desktop\data"
    port: int = 9222

@app.post("/api/upload_documents")
def api_upload_documents(body: UploadDocsIn):
    """Trigger Selenium-based document upload from a local folder."""
    from app.docgen.document_uploader import upload_documents
    import threading

    def run_upload():
        upload_documents(body.folder, body.port)

    threading.Thread(target=run_upload, daemon=True).start()
    return {
        "action": "uploading",
        "message": f"Document upload started from: {body.folder}",
        "instructions": [
            "Make sure Chrome is started with: chrome.exe --remote-debugging-port=9222",
            "Make sure you are on the Document Upload page",
            f"Files are being read from: {body.folder}",
        ]
    }





class FormFillIn(BaseModel):
    port: int = 9222
    certificate_type: str = "income_certificate"

@app.post('/sessions/{sid}/launch_browser')
def launch_browser_endpoint(sid: str):
    import subprocess
    import os
    try:
        profile_dir = r"C:\Users\Vedant\Desktop\edge-debug-profile"
        url = "https://goaonline.gov.in/Appln/UIP/DeptServices?__ns=Revenue"
        cmd = f'start msedge --remote-debugging-port=9222 "--user-data-dir={profile_dir}" "{url}"'
        subprocess.Popen(cmd, shell=True)
        return {'status': 'success', 'message': 'Browser launched'}
    except Exception as e:
        raise HTTPException(500, f"Failed to launch browser: {e}")

@app.post('/sessions/{sid}/automate_fill')
def trigger_fill_automation(sid: str, body: FormFillIn):
    from app.docgen.form_filler import fill_form
    import threading
    threading.Thread(target=fill_form, args=(sid, body.port, body.certificate_type), daemon=True).start()
    return {'action': 'filling', 'message': 'Selenium form filling started'}
