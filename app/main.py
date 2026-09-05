"""Saarthi kiosk backend - FastAPI orchestrator for the six-state flow.

GREET -> IDENTIFY -> CHECKLIST -> SCAN -> FILL -> DELIVER

Responses follow the kiosk action protocol:
{"action": "speak|menu|ask|confirm|complete", ..., "language": "hi"}
"""
import os
import re
import shutil
import subprocess
import importlib
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote, urlparse
from urllib.request import Request as UrlRequest, urlopen

# Load .env file automatically
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Union, Any

from app.core.profile import mask_aadhaar, validate_mobile
from app.core.session import Session, SessionStore, State
from app.docgen.generator import generate_application, generate_schemes_sheet, OUTPUT_DIR
from app.eligibility.llm_enricher import enrich
from app.eligibility.rules import LAKH, check_eligibility
from app.i18n.phrases import SUPPORTED, get_phrase
from app.ocr.scanner import CONFIDENCE_THRESHOLD, get_scanner
from app.printing.printer import print_document
from app.services.catalog import build_checklist, get_service, list_services
from app.services.application_schema import required_application_fields
from app.services.web_search import get_live_guidance, wants_live_search

PORTAL_URLS = {
    "goa_online": "https://services.goaonline.gov.in/",
}

DEFAULT_APPLICATION_FIELDS = ("name", "dob", "mobile", "address")
LIVE_APPLICATION_KEY = "__live_guidance__"

ASSISTANT_FIELD_LABELS = {
    "age": "your age",
    "state": "your state",
    "gender": "your gender",
    "occupation": "whether you are a student",
    "annual_income": "your annual family income",
    "caste_category": "your social category",
}

ASSISTANT_FIELD_OPTIONS = {
    "gender": [("female", "Female"), ("male", "Male"), ("other", "Other")],
    "state": [("Goa", "Goa"), ("Maharashtra", "Maharashtra"), ("Gujarat", "Gujarat"), ("Other", "Other")],
    "occupation": [
        ("farmer", "Farmer"),
        ("salaried", "Salaried employee"),
        ("artisan", "Artisan / craftsperson"),
        ("small_business", "Small-business owner"),
        ("unemployed", "Unemployed"),
        ("pensioner", "Pensioner"),
        ("student", "Student"),
    ],
    "caste_category": [(value, value.title() if value != "MINORITY" else "Minority") for value in ("GENERAL", "SC", "ST", "OBC", "NT", "VJNT", "SBC", "MINORITY")],
}

# These are the minimum profile facts needed to make a useful scholarship
# recommendation. The assistant can collect several in one natural-language
# answer, so the citizen does not have to navigate back to the form.
SCHOLARSHIP_FIELDS = ("age", "state", "occupation", "annual_income", "caste_category")


def _apply_extracted_aadhaar(session: Session, fields: dict) -> None:
    """Store only a validated, masked Aadhaar value from model output."""
    aadhaar = fields.pop("aadhaar_number", None)
    if aadhaar is None:
        return
    aadhaar_text = str(aadhaar).strip()
    if session.profile.set_aadhaar(aadhaar_text):
        fields["aadhaar"] = mask_aadhaar(aadhaar_text)

app = FastAPI(title="Saarthi Kiosk", version="0.1.0")
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


@app.get("/pdf-filler", include_in_schema=False)
def pdf_filler_page():
    raise HTTPException(410, "PDF form filling has been removed from Saarthi")


@app.get("/pdf-filler.html", include_in_schema=False)
def pdf_filler_html_page():
    raise HTTPException(410, "PDF form filling has been removed from Saarthi")


@app.get("/application", include_in_schema=False)
def application_page():
    raise HTTPException(410, "The browser form-filling and document-upload workflow has been removed")


@app.get("/application.html", include_in_schema=False)
def application_html_page():
    raise HTTPException(410, "The browser form-filling and document-upload workflow has been removed")


@app.get("/application/{step}", include_in_schema=False)
def application_step_page(step: str):
    raise HTTPException(410, "The browser form-filling and document-upload workflow has been removed")


@app.get("/style.css", include_in_schema=False)
def serve_css():
    return FileResponse(str(_FRONTEND / "style.css"), media_type="text/css", headers=NO_CACHE)


@app.get("/application.css", include_in_schema=False)
def serve_application_css():
    raise HTTPException(410, "The browser form-filling and document-upload workflow has been removed")


@app.get("/app.js", include_in_schema=False)
def serve_js():
    return FileResponse(str(_FRONTEND / "app.js"), media_type="application/javascript", headers=NO_CACHE)


@app.get("/i18n.js", include_in_schema=False)
def serve_i18n_js():
    return FileResponse(str(_FRONTEND / "i18n.js"), media_type="application/javascript", headers=NO_CACHE)


@app.get("/application.js", include_in_schema=False)
def serve_application_js():
    raise HTTPException(410, "The browser form-filling and document-upload workflow has been removed")


@app.get("/pdf-filler.css", include_in_schema=False)
def serve_pdf_filler_css():
    raise HTTPException(410, "PDF form filling has been removed from Saarthi")


@app.get("/pdf-filler.js", include_in_schema=False)
def serve_pdf_filler_js():
    raise HTTPException(410, "PDF form filling has been removed from Saarthi")





# --- Utility endpoints ---

@app.get("/health")
def health():
    return {"status": "ok", "service": "Saarthi Kiosk"}


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
        "profile": s.profile.model_dump(),
        "eligibility": [item.__dict__ for item in s.eligibility],
        "pending_request": s.assistant_context or None,
    }


def _session(sid: str) -> Session:
    s = store.get(sid)
    if s is None:
        raise HTTPException(404, "Session not found or already wiped")
    return s


class PdfFormValuesIn(BaseModel):
    values: Dict[str, Any]


@app.post("/sessions/{sid}/pdf-filler/inspect", include_in_schema=False)
async def inspect_pdf_form(sid: str, file: UploadFile = File(...)):
    """Retired PDF form-filling endpoint."""
    raise HTTPException(410, "PDF form filling has been removed from Saarthi")


@app.post("/sessions/{sid}/pdf-filler/fill", include_in_schema=False)
def fill_pdf_form(sid: str, body: PdfFormValuesIn):
    """Retired PDF form-filling endpoint."""
    raise HTTPException(410, "PDF form filling has been removed from Saarthi")


# --- STATE 1: GREET ---------------------------------------------------------

@app.post("/sessions")
def create_session():
    s = store.create()
    return {
        "session_id": s.id,
        "action": "menu",
        "title": get_phrase("greeting"),
        "options": [{"id": lang, "label": lang} for lang in SUPPORTED],
        "language": "en",
        "profile": s.profile.model_dump(),
        "sample_profile": True,
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
    s.profile.state = body.state.strip()
    s.state = State.IDENTIFY
    return {
        "action": "menu",
        "options": [{"id": k, "label": v["name"]} for k, v in list_services(body.state).items()],
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
        
    _apply_extracted_aadhaar(s, fields)
        
    for k, v in fields.items():
        if hasattr(s.profile, k) and v is not None and v != "":
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
    document_types: List[str] = Field(default_factory=list)
    images: Optional[List[Union[str, ImageItem, Dict[str, Any]]]] = None


def _canonical_scan_filename(expected_type: str | None, file_name: str) -> str:
    """Give known document types a stable filename for portal uploading.

    The browser uploader identifies documents from their filenames.  Users can
    upload a file called ``IMG_1234.jpg`` while selecting "Aadhaar Card", so
    relying on the original filename makes later document rows get skipped.
    """
    suffix = Path(file_name).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".pdf"}:
        suffix = ".png"

    normalized = re.sub(r"[^a-z0-9]", "", str(expected_type or "").lower())
    names = {
        "aadhaar": "aadharcard",
        "aadhaarcard": "aadharcard",
        "aadhar": "aadharcard",
        "aadharcard": "aadharcard",
        "identityproof": "aadharcard",
        "idproof": "aadharcard",
        "voterid": "voterid",
        "voteridcard": "voterid",
        "electioncard": "electioncard",
        "epic": "epic",
        "pancard": "pancard",
        "birthcertificate": "birthcertificate",
        "ageproof": "birthcertificate",
        "photograph": "photograph",
        "photo": "photograph",
        "passportsizephotograph": "photograph",
        "incomecertificate": "incomecertificate",
        "residencecertificate": "residencecertificate",
        "residenceproof": "residencecertificate",
        "castecertificate": "castecertificate",
        "rationcard": "rationcard",
        "electricitybill": "electricitybill",
        "affidavit": "affidavit",
        "affidavitonstamppaper": "affidavit",
        "affidavitonastamppaper": "affidavit",
        "selfdeclaration": "selfdeclaration",
    }
    basename = names.get(normalized)
    if not basename:
        # Service requirements sometimes append a category, for example
        # "Voter Id card - Id proof" or "PAN card - Id proof".
        if "voterid" in normalized or "electioncard" in normalized or normalized == "epic":
            basename = "voterid"
        elif "pancard" in normalized:
            basename = "pancard"
        elif "aadhaar" in normalized or "aadhar" in normalized:
            basename = "aadharcard"
        elif "birthcertificate" in normalized:
            basename = "birthcertificate"
        elif "photograph" in normalized or normalized == "photo":
            basename = "photograph"
        elif "identityproof" in normalized or "idproof" in normalized:
            basename = "aadharcard"
    if basename:
        return basename + suffix

    return re.sub(r"[^a-zA-Z0-9._-]", "_", file_name) or "document.png"

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
                clean_name = _canonical_scan_filename(body.expected_type, file_name)
                
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
        
    _apply_extracted_aadhaar(s, fields)
        
    for k, v in fields.items():
        if hasattr(s.profile, k) and v is not None and v != "":
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
    document_types = list(dict.fromkeys(
        document_type.strip()
        for document_type in [body.expected_type or "Document", *body.document_types]
        if document_type and document_type.strip()
    ))
    s.document_extractions.extend(
        {
            "document_type": document_type,
            "fields": extra_fields,
        }
        for document_type in document_types
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
    try:
        from app.ocr.ai_extractor import extract_data_from_images
        return await extract_data_from_images(body.images, model=body.model)
    except Exception as exc:
        raise HTTPException(
            502,
            "Document extraction is unavailable. Check the extraction dependencies and OPENROUTER_API_KEY.",
        ) from exc


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


def _assistant_intent(message: str) -> Optional[str]:
    """Identify the small set of intents that need conversational intake."""
    message_lower = message.lower()
    if any(term in message_lower for term in ("scholarship", "stipend", "tuition", "education grant")):
        return "scholarship"
    if any(term in message_lower for term in ("scheme", "schemes", "yojana", "benefit", "eligible", "eligibility")):
        return "scheme"
    return None


def _missing_assistant_fields(profile, intent: str) -> list[str]:
    """Return fields that are missing for the current request, in question order."""
    if intent == "scholarship":
        missing = []
        if profile.age is None:
            missing.append("age")
        if not profile.state:
            missing.append("state")
        if not (profile.is_student or profile.occupation == "student"):
            missing.append("occupation")
        if profile.annual_income is None:
            missing.append("annual_income")
        if not profile.caste_category:
            missing.append("caste_category")
        return missing
    return [
        field for field in ("state", "age", "gender", "occupation", "annual_income")
        if getattr(profile, field) in (None, "")
    ]


def _income_value(text: str) -> Optional[int]:
    """Extract an annual income written as rupees or lakhs."""
    amount_pattern = r"(?:₹|rs\.?|inr\s*)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(lakh|lakhs|lac|lacs)?"
    labelled = re.search(
        r"(?:annual\s+family\s+income|family\s+income|annual\s+income|income)"
        r"\s*(?:is|of|:)?\s*" + amount_pattern,
        text.lower(),
    )
    match = labelled or (re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:lakh|lakhs|lac|lacs)", text.lower()) if re.search(r"[0-9]+(?:\.[0-9]+)?\s*(?:lakh|lakhs|lac|lacs)", text.lower()) else None)
    if not match:
        return None
    try:
        raw_amount = match.group(1).replace(",", "")
        amount = float(raw_amount)
        unit = (match.group(2) or "").lower() if match.lastindex and match.lastindex >= 2 else ""
        return int(amount * LAKH) if unit in {"lakh", "lakhs", "lac", "lacs"} else int(amount)
    except (TypeError, ValueError):
        return None


def _extract_assistant_updates(message: str, fields: Optional[list[str]] = None) -> dict:
    """Extract only unambiguous profile answers from a conversational reply.

    This deliberately handles common kiosk answers without pretending to be a
    general-purpose NLP system. Anything unclear remains for the citizen to
    confirm in the profile form.
    """
    text = message.strip()
    lower = text.lower()
    wanted = set(fields or ("age", "state", "gender", "occupation", "annual_income", "caste_category"))
    updates: dict = {}

    if "age" in wanted:
        age_match = re.search(r"(?:i\s*am|age\s*(?:is|:)?|aged)\s*(\d{1,3})\b", lower)
        if not age_match and re.fullmatch(r"\d{1,3}", lower):
            age_match = re.match(r"\d{1,3}", lower)
        if age_match and 0 <= int(age_match.group(1)) <= 120:
            updates["age"] = int(age_match.group(1))

    if "annual_income" in wanted:
        income = _income_value(text)
        if income is None and "age" not in wanted and re.fullmatch(r"(?:₹|rs\.?\s*)?[0-9][0-9,]*", lower):
            try:
                income = int(re.sub(r"[^0-9]", "", lower))
            except ValueError:
                income = None
        if income is not None and income >= 0:
            updates["annual_income"] = income

    if "state" in wanted:
        states = {"maharashtra": "Maharashtra", "goa": "Goa", "gujarat": "Gujarat"}
        for name, value in states.items():
            if re.search(rf"\b{re.escape(name)}\b", lower):
                updates["state"] = value
                break

    if "gender" in wanted:
        if re.search(r"\b(female|woman|girl)\b", lower):
            updates["gender"] = "female"
        elif re.search(r"\b(male|man|boy)\b", lower):
            updates["gender"] = "male"
        elif re.search(r"\b(other|non[- ]binary)\b", lower):
            updates["gender"] = "other"

    if "occupation" in wanted:
        occupation_aliases = (
            (r"\b(student|studying|college student|school student)\b", "student"),
            (r"\b(farmer|agriculturist)\b", "farmer"),
            (r"\b(artisan|craftsperson)\b", "artisan"),
            (r"\b(small business|business owner|entrepreneur)\b", "small_business"),
            (r"\b(salaried|employee)\b", "salaried"),
            (r"\bunemployed\b", "unemployed"),
            (r"\bpensioner\b", "pensioner"),
        )
        for pattern, occupation in occupation_aliases:
            if re.search(pattern, lower):
                updates["occupation"] = occupation
                if occupation == "student":
                    updates["is_student"] = True
                break

    if "caste_category" in wanted:
        categories = ("VJNT", "MINORITY", "GENERAL", "OBC", "SC", "ST", "NT", "SBC")
        for category in categories:
            if re.search(rf"\b{re.escape(category.lower())}\b", lower):
                updates["caste_category"] = category
                break

    return updates


def _merge_assistant_updates(s: Session, updates: dict) -> None:
    if not updates:
        return
    data = s.profile.model_dump()
    data.update({key: value for key, value in updates.items() if key in data})
    s.profile = type(s.profile).model_validate(data)


def _assistant_follow_up(intent: str, missing: list[str], profile, saved: dict) -> str:
    request_name = "scholarship" if intent == "scholarship" else "scheme recommendations"
    labels = [ASSISTANT_FIELD_LABELS[field] for field in missing]
    saved_text = ""
    if saved:
        saved_labels = []
        for field in saved:
            if field in ASSISTANT_FIELD_LABELS:
                saved_labels.append(ASSISTANT_FIELD_LABELS[field].replace("your ", ""))
        if saved_labels:
            saved_text = " I saved " + ", ".join(saved_labels) + " from your answer."
    return (
        f"I can help you find the right {request_name}.{saved_text} "
        f"To narrow it down, I still need {', '.join(labels)}. "
        "You can reply in one message, for example: ‘I am 19, a student, SC, "
        "my family income is ₹2 lakh, and I live in Maharashtra.’"
    )


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

    previous_context = s.assistant_context
    detected_intent = _assistant_intent(message)
    message_lower = message.lower()
    is_new_service_request = any(
        term in message_lower for term in ("certificate", "document", "income certificate", "residence", "caste")
    )
    intent = detected_intent or (None if is_new_service_request else previous_context.get("intent"))

    # A follow-up answer is applied to the profile before eligibility is
    # calculated. This is what lets the assistant learn from chat, while the
    # existing profile form remains the single place where those details live.
    saved_updates = {}
    if intent:
        intent_fields = list(SCHOLARSHIP_FIELDS if intent == "scholarship" else ("state", "age", "gender", "occupation", "annual_income"))
        fields = previous_context.get("missing_fields") or intent_fields
        saved_updates = _extract_assistant_updates(message, fields)
        _merge_assistant_updates(s, saved_updates)

    results = check_eligibility(s.profile)
    results = await enrich(s.profile, results, s.language)
    s.eligibility = results

    gaps = _profile_gaps(s.profile)
    intent_missing = _missing_assistant_fields(s.profile, intent) if intent else []
    service_terms = ("certificate", "certificates", "document", "income certificate", "residence", "caste")
    scheme_terms = ("scheme", "schemes", "yojana", "eligible", "eligibility", "benefit", "apply", "kisan", "awas", "ujjwala", "ayushman", "mudra", "scholarship")

    requested = _requested_matches(message, results)
    live_guidance = None
    application_service_id = None
    # Search only after the request-specific intake is complete. This avoids
    # showing an unqualified portal before we have the facts needed to find a
    # relevant scheme. Scholarship intent always triggers an official-source
    # search once its required details have been collected.
    should_search = not intent_missing and (wants_live_search(message) or intent in {"scholarship", "scheme"})
    if should_search:
        search_topic = previous_context.get("request") or message
        live_guidance = await get_live_guidance(
            search_topic,
            s.profile.state,
            s.profile.model_dump(),
        )

    available_services = list_services(s.profile.state)
    for candidate_id, candidate in available_services.items():
        if str(candidate.get("name", "")).lower() in message_lower:
            application_service_id = candidate_id
            break

    recommendations = results
    if intent and intent_missing:
        # Keep the request alive until its missing facts have been answered.
        s.assistant_context = {
            "intent": intent,
            "fields": intent_fields,
            "missing_fields": intent_missing,
            "request": previous_context.get("request") or message,
        }
        gaps = [ASSISTANT_FIELD_LABELS.get(field, field) for field in intent_missing]
        reply = _assistant_follow_up(intent, intent_missing, s.profile, saved_updates)
    elif intent and not application_service_id:
        # The request is complete. Clear the pending state so a later generic
        # question starts a fresh conversation.
        s.assistant_context = {}
        recommendations = results
        if intent == "scholarship":
            scholarship_results = [item for item in results if "scholar" in item.scheme_name.lower()]
            if scholarship_results:
                recommendations = scholarship_results
        if recommendations:
            reply = (
                "Thanks — I saved the details you shared. Based on your updated profile, "
                f"I found {len(recommendations)} {('scholarship' if intent == 'scholarship' else 'scheme')} match"
                f"{'es' if len(recommendations) != 1 else ''}. Review the cards below for the benefit, reason, and application route."
            )
        else:
            reply = (
                "Thanks — I saved the details you shared. I could not confirm a matching "
                f"{('scholarship' if intent == 'scholarship' else 'scheme')} from the verified rules yet. "
                "Please review the profile and ask me to check again if any detail changes."
            )
    else:
        recommendations = results

    if intent and intent_missing:
        # The follow-up question above is the response for an incomplete
        # intent, even if the text also contains a generic scheme keyword.
        pass
    elif application_service_id:
        reply = (
            f"I found the {available_services[application_service_id]['name']} service. I have opened its checklist in the Services panel, "
            "including the documents, fee, processing time, and official guidance."
        )
    elif intent:
        # A complete intent already has a tailored response from the block
        # above. Keep it instead of falling through to generic wording.
        pass
    elif requested:
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

    if intent and not intent_missing and not application_service_id and intent == "scholarship":
        recommendations = [item for item in results if "scholar" in item.scheme_name.lower()] or results

    return {
        "action": "assistant",
        "reply": reply,
        "recommendations": [item.__dict__ for item in recommendations],
        "profile_gaps": gaps,
        "saved_profile_fields": list(saved_updates),
        "profile": s.profile.model_dump(),
        "pending_request": {
            "intent": intent,
            "missing_fields": intent_missing,
            "question_field": intent_missing[0] if intent_missing else None,
            "question_options": [
                {"value": value, "label": label}
                for value, label in ASSISTANT_FIELD_OPTIONS.get(intent_missing[0], [])
            ] if intent_missing else [],
        } if intent and intent_missing else None,
        "services": [{"id": key, "label": value["name"]} for key, value in available_services.items()],
        "application_service_id": application_service_id,
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
        resp["note"] = "Printer unavailable - download the PDF using the link above"
    return resp











@app.post("/sessions/{sid}/automate_upload", include_in_schema=False)
def trigger_upload_automation(sid: str):
    """Start the shared Guided Services document uploader for this session.

    The dashboard keeps its original URL so existing application flows work,
    while the implementation stays in the namespaced Guided Services module.
    """
    from app.guided_services.router import guided_automate_upload

    return guided_automate_upload(sid)


@app.get("/sessions/{sid}/upload-status", include_in_schema=False)
def upload_automation_status(sid: str):
    """Return status for an upload started from the dashboard."""
    from app.guided_services.router import guided_upload_status

    return guided_upload_status(sid)


@app.get("/sessions/{sid}/gaps")
def get_gaps(sid: str):
    """Return typed missing fields required for the selected government form."""
    s = _session(sid)
    if s.service_id == "CERT_INC":
        return required_application_fields(s.service_id, s.profile)

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
    return {"service_id": s.service_id, "fields": [], "missing_fields": missing}




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

from pydantic import BaseModel
import shutil
import tempfile
from pathlib import Path
from fastapi import Request, HTTPException, UploadFile

@app.post("/api/execute-form", include_in_schema=False)
async def api_execute_form(_: Request):
    """Retired unsafe browser agent endpoint.

    Arbitrary multipart data cannot be verified as the citizen's reviewed
    application plan. The old agent could upload files and submit a form, so
    it is deliberately unavailable instead of attempting a best-effort map.
    """
    raise HTTPException(status_code=410, detail="Browser form filling and submission have been removed from Saarthi")


class UploadDocsIn(BaseModel):
    folder: str
    port: int = 9222

@app.post("/api/upload_documents", include_in_schema=False)
def api_upload_documents(body: UploadDocsIn):
    """Retired browser document-upload endpoint."""
    raise HTTPException(status_code=410, detail="Browser document upload has been removed from Saarthi")





class FormFillIn(BaseModel):
    port: int = 9222
    service_id: str

class ApplicationServiceIn(BaseModel):
    service_id: str


class ApplicationDetailsIn(BaseModel):
    details: Dict[str, Any]


def _browser_automation_removed() -> None:
    """Fail closed for the retired portal form workflow."""
    raise HTTPException(410, "Browser form filling and document upload have been removed from Saarthi")


def _application_service(service_id: str) -> dict:
    service = get_service(service_id)
    if not service:
        raise HTTPException(404, "Unknown government service")
    return service


def _portal_url(service: dict) -> str:
    return str(service.get("portal_url") or PORTAL_URLS.get(service.get("portal"), "")).strip()


def _chrome_executable() -> str:
    """Locate Chrome even when it is not included in the shell PATH."""
    candidates = [shutil.which("chrome.exe")]
    for root in (os.getenv("PROGRAMFILES"), os.getenv("PROGRAMFILES(X86)"), os.getenv("LOCALAPPDATA")):
        if root:
            candidates.append(str(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise HTTPException(500, "Google Chrome is required to open an official portal, but it was not found on this computer")


def _reuse_running_chrome(url: str) -> bool:
    """Open a tab in the existing automation browser so its login stays active."""
    endpoint = "http://127.0.0.1:9222/json/new?" + quote(url, safe="")
    try:
        with urlopen(UrlRequest(endpoint, method="PUT"), timeout=1.5) as response:
            return 200 <= response.status < 300
    except (OSError, URLError):
        return False


def _launch_chrome(sid: str, url: str) -> None:
    """Reuse one Chrome profile and preserve the portal's login cookies."""
    if _reuse_running_chrome(url):
        return

    # This is intentionally stable across Saarthi session renewals. Creating
    # a profile named after every in-memory session logs the citizen out when
    # the development server reloads or the dashboard renews its session ID.
    profile_dir = Path.cwd() / ".janseva-browser" / "portal-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    command = [
        _chrome_executable(),
        "--new-window",
        "--no-first-run",
        "--no-default-browser-check",
        "--remote-debugging-port=9222",
        "--remote-allow-origins=http://localhost",
        f"--user-data-dir={profile_dir}",
        url,
    ]
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    subprocess.Popen(command, shell=False, creationflags=creation_flags)


def _mapping_for_service(service: dict) -> tuple[str | None, dict]:
    """Load a verified field mapping when the service declares one.

    A service without a mapping remains usable for document preparation and
    official-portal guidance; it simply does not get automated form filling.
    """
    mapping_name = str(service.get("automation_mapping") or "").strip()
    if not mapping_name:
        return None, {}
    try:
        module = importlib.import_module(f"app.docgen.mappings.{mapping_name}")
        mapping = getattr(module, "MAPPING", {})
        return mapping_name, mapping if isinstance(mapping, dict) else {}
    except (ImportError, AttributeError):
        return None, {}


def _display_label(key: str, mapping: dict) -> str:
    labels = mapping.get(key, [])
    if labels:
        label = str(labels[0]).replace("_", " ").strip()
        if len(label) > 2 and not label.lower().startswith("drp"):
            return label
    return key.replace("_", " ").capitalize()


def _application_field_keys(service: dict, mapping: dict, discovered: dict | None = None) -> list[str]:
    configured = service.get("application_fields")
    if isinstance(configured, list) and configured:
        return [str(key) for key in configured]
    if mapping:
        return list(mapping.keys())
    if discovered and isinstance(discovered.get("fields"), list):
        return [str(field.get("key")) for field in discovered["fields"] if field.get("key")]
    return list(DEFAULT_APPLICATION_FIELDS)


def _normalise_portal_field_text(value: Any) -> str:
    """Make portal labels, mapping aliases, and DOM names comparable."""
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _field_option_labels(field: dict) -> set[str]:
    """Return normalised visible labels for one scanned choice control."""
    labels: set[str] = set()
    for option in field.get("options", []):
        if isinstance(option, dict):
            value = option.get("label") or option.get("value")
        else:
            value = option
        normalised = _normalise_portal_field_text(value)
        if normalised:
            labels.add(normalised)
    return labels


def _mapped_scanned_field(
    application_key: str,
    mapping: dict,
    discovered_by_key: dict[str, dict],
    discovered_fields: list[dict],
) -> dict:
    """Find the DOM field behind a stable application/mapping key.

    Portal controls use implementation-specific names such as ``drpPurpose_``
    while the reviewed application plan deliberately uses stable keys such as
    ``purpose``.  A direct-key lookup therefore loses the scanned control's
    type, choices and constraints for mapped services.  Match by visible
    labels first, then by an unambiguous radio/checkbox option group.
    """
    direct = discovered_by_key.get(application_key)
    if direct:
        return direct
    if not mapping:
        return {}

    aliases = [application_key, _display_label(application_key, mapping)]
    configured_aliases = mapping.get(application_key, [])
    if isinstance(configured_aliases, (list, tuple, set)):
        aliases.extend(configured_aliases)
    elif configured_aliases:
        aliases.append(configured_aliases)
    aliases = {
        normalised
        for alias in aliases
        if (normalised := _normalise_portal_field_text(alias))
    }
    if not aliases:
        return {}

    best_field: dict = {}
    best_score = 0
    for field in discovered_fields:
        label = _normalise_portal_field_text(field.get("label"))
        dom_key = _normalise_portal_field_text(field.get("key"))
        placeholder = _normalise_portal_field_text(field.get("placeholder"))
        score = 0

        # Exact visible labels are the most reliable signal. DOM keys and
        # placeholders are useful fallbacks for portals with imperfect labels.
        for alias in aliases:
            if alias == label:
                score = max(score, 120)
            elif alias == dom_key:
                score = max(score, 115)
            elif alias == placeholder:
                score = max(score, 105)
            elif len(alias) >= 5 and (alias in label or alias in dom_key or alias in placeholder):
                score = max(score, 80)

        # Some portals label a radio group only through its choices. Caste
        # Certificate's mapping, for example, names "Self" and "Relative or
        # others" rather than the group heading. Require two matched choices
        # so a single generic word cannot bind an unrelated field.
        option_matches = len(aliases & _field_option_labels(field))
        if field.get("type") in {"radio", "checkbox"} and option_matches >= 2:
            score = max(score, 110 + min(option_matches, 5))

        if score > best_score:
            best_field, best_score = field, score
    return best_field


def _profile_suggestion(label: str, profile: dict) -> Any:
    """Suggest a saved profile value for a discovered field; never store it silently."""
    label = label.lower()
    aliases = (
        (("applicant name", "full name", "name of applicant"), "name"),
        (("date of birth", "dob"), "dob"),
        (("mobile", "phone"), "mobile"),
        (("email",), "email"),
        (("father", "husband", "guardian"), "father_name"),
        (("gender",), "gender"),
        (("occupation",), "occupation"),
        (("address", "house", "flat"), "address"),
        (("district",), "district"),
        (("taluka",), "taluka"),
        (("village", "city", "town"), "village"),
        (("pincode", "pin code", "postal"), "pincode"),
        (("income",), "annual_income"),
        (("caste", "category"), "caste_category"),
    )
    for terms, key in aliases:
        if any(term in label for term in terms) and profile.get(key) not in (None, ""):
            return profile[key]
    return ""


def _safe_application_value(field: str, value: Any) -> Any:
    if value in (None, ""):
        return ""
    if field == "id_proof_no":
        text = str(value)
        return "••••" + text[-4:] if len(text) >= 4 else "••••"
    return value


def _field_input_metadata(field: dict) -> dict:
    """Return only UI hints read from a visible portal control.

    These hints let the preparation screen ask the same kind of question as
    the portal (date, number, long text, choices, etc.) without reading or
    exposing any portal value.
    """
    return {
        "placeholder": str(field.get("placeholder") or ""),
        "min": str(field.get("min") or ""),
        "max": str(field.get("max") or ""),
        "step": str(field.get("step") or ""),
        "pattern": str(field.get("pattern") or ""),
        "max_length": field.get("max_length"),
    }


def _extracted_application_values(session: Session) -> Dict[str, Any]:
    """Combine document-only values so portal fields can reuse OCR results."""
    values: Dict[str, Any] = {}
    for extraction in session.document_extractions:
        fields = extraction.get("fields", {}) if isinstance(extraction, dict) else {}
        if not isinstance(fields, dict):
            continue
        values.update({key: value for key, value in fields.items() if value not in (None, "")})
    return values


@app.get('/sessions/{sid}/applications/{service_id}/readiness')
def application_readiness(sid: str, service_id: str):
    """Return a configuration-driven, reviewable application plan."""
    s = _session(sid)
    service = _application_service(service_id)
    profile = s.profile.model_dump()
    mapping_name, mapping = _mapping_for_service(service)
    saved_details = s.application_details.get(service_id, {})
    extracted_details = _extracted_application_values(s)
    discovered = s.discovered_forms.get(service_id, {})
    discovered_fields = [
        field for field in discovered.get("fields", [])
        if isinstance(field, dict) and field.get("key")
    ]
    discovered_by_key = {
        str(field.get("key")): field
        for field in discovered_fields
    }
    fields, missing_fields = [], []
    for key in _application_field_keys(service, mapping, discovered):
        discovered_field = _mapped_scanned_field(
            key, mapping, discovered_by_key, discovered_fields
        )
        value = saved_details.get(key, profile.get(key, ""))
        if value in (None, ""):
            value = extracted_details.get(key, "")
        if value in (None, "") and discovered_field:
            value = _profile_suggestion(str(discovered_field.get("label", "")), profile)
        required = bool(discovered_field.get("required")) if discovered_field and not mapping else True
        missing = required and value in (None, "")
        if missing:
            missing_fields.append(key)
        fields.append({
            "key": key,
            "label": str(discovered_field.get("label") or _display_label(key, mapping)),
            "value": _safe_application_value(key, value),
            "missing": missing,
            "required": required,
            "type": str(discovered_field.get("type", "text")),
            "options": discovered_field.get("options", []),
            **_field_input_metadata(discovered_field),
        })

    document_types = sorted({
        str(item.get("document_type", ""))
        for item in s.document_extractions
        if item.get("document_type")
    })
    configured_documents = [doc["name"] for doc in service.get("documents", [])]
    discovered_documents = [str(item) for item in discovered.get("documents", [])]
    documents = discovered_documents if discovered else configured_documents
    return {
        "service_id": service_id,
        "service": service["name"],
        "portal_url": _portal_url(service),
        "documents": documents,
        "document_uploads_detected": bool(discovered_documents) if discovered else None,
        "uploaded_document_types": document_types,
        "fields": fields,
        "missing_fields": missing_fields,
        "ready_to_fill": False,
        "automation_available": False,
        "form_scanned": bool(discovered),
        "scanned_form": {"title": discovered.get("title"), "url": discovered.get("url")} if discovered else None,
        "automation_message": "Browser form filling has been removed. Use the official portal to enter and review the application yourself.",
        "safety_note": "Saarthi never receives OTPs or CAPTCHAs and never submits the final application.",
    }


@app.post('/sessions/{sid}/applications/{service_id}/details')
def save_application_details(sid: str, service_id: str, body: ApplicationDetailsIn):
    """Save reviewed answers for one service without polluting the base profile."""
    s = _session(sid)
    service = _application_service(service_id)
    _, mapping = _mapping_for_service(service)
    allowed = set(_application_field_keys(service, mapping, s.discovered_forms.get(service_id)))
    details = {
        key: value.strip() if isinstance(value, str) else value
        for key, value in body.details.items()
        if key in allowed and value not in (None, "")
    }
    if "mobile" in details and not validate_mobile(str(details["mobile"])):
        raise HTTPException(400, "Invalid mobile number")
    s.application_details.setdefault(service_id, {}).update(details)

    # Reuse answers that are part of the citizen profile for eligibility and
    # later services, while keeping portal-only values service-specific.
    profile_data = s.profile.model_dump()
    profile_data.update({key: value for key, value in details.items() if key in profile_data})
    s.profile = type(s.profile).model_validate(profile_data)
    return application_readiness(sid, service_id)


@app.post('/sessions/{sid}/applications/{service_id}/scan-open-form', include_in_schema=False)
def scan_open_application_form(sid: str, service_id: str, port: int = 9222):
    """Inspect the form currently open in the citizen's local Saarthi browser."""
    _browser_automation_removed()


@app.post('/sessions/{sid}/launch_browser', include_in_schema=False)
def launch_browser_endpoint(sid: str, body: ApplicationServiceIn):
    """Open a session-specific, debuggable Chrome window for citizen login."""
    from app.guided_services.router import BrowserLaunchIn, guided_launch_browser

    return guided_launch_browser(sid, BrowserLaunchIn(service_id=body.service_id))

@app.post('/sessions/{sid}/automate_fill', include_in_schema=False)
def trigger_fill_automation(sid: str, body: FormFillIn):
    _browser_automation_removed()


# --- LIVE-GUIDANCE APPLICATIONS --------------------------------------------

class LiveApplicationIn(BaseModel):
    title: str
    url: str


def _valid_live_application_url(value: str) -> str:
    """Accept only an official government page returned by live guidance."""
    url = value.strip()
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    is_official = host == "gov.in" or host.endswith(".gov.in") or host in {
        "myscheme.gov.in", "umang.gov.in", "goaonline.gov.in",
    }
    if parsed.scheme not in {"http", "https"} or not host or not is_official:
        raise HTTPException(400, "Choose an official government website from the live guidance list")
    return url


def _live_application_plan(s: Session) -> dict:
    if not s.live_application:
        raise HTTPException(404, "No live-guidance application has been selected")

    profile = s.profile.model_dump()
    saved_details = s.application_details.get(LIVE_APPLICATION_KEY, {})
    extracted_details = _extracted_application_values(s)
    discovered = s.discovered_forms.get(LIVE_APPLICATION_KEY, {})
    scanned_fields = [
        field for field in discovered.get("fields", [])
        if isinstance(field, dict) and field.get("key") and field.get("type") != "file"
    ]
    if scanned_fields:
        form_fields = scanned_fields
    else:
        form_fields = [
            {"key": key, "label": key.replace("_", " ").capitalize(), "type": "text", "required": True}
            for key in DEFAULT_APPLICATION_FIELDS
        ]

    fields, missing_fields = [], []
    for field in form_fields:
        key = str(field["key"])
        label = str(field.get("label") or key.replace("_", " ").capitalize())
        value = saved_details.get(key, profile.get(key, ""))
        if value in (None, ""):
            value = extracted_details.get(key, "")
        if value in (None, ""):
            value = _profile_suggestion(label, profile)
        required = bool(field.get("required", True))
        missing = required and value in (None, "")
        if missing:
            missing_fields.append(key)
        fields.append({
            "key": key,
            "label": label,
            "value": _safe_application_value(key, value),
            "missing": missing,
            "required": required,
            "type": str(field.get("type", "text")),
            "options": field.get("options", []),
            **_field_input_metadata(field),
        })

    document_types = sorted({
        str(item.get("document_type", ""))
        for item in s.document_extractions
        if item.get("document_type")
    })
    return {
        "application_type": "live_guidance",
        "service_id": LIVE_APPLICATION_KEY,
        "service": s.live_application["title"],
        "portal_url": s.live_application["url"],
        "documents": [str(item) for item in discovered.get("documents", []) if str(item).strip()],
        "document_uploads_detected": bool(discovered.get("documents")) if discovered else None,
        "uploaded_document_types": document_types,
        "fields": fields,
        "missing_fields": missing_fields,
        "ready_to_fill": False,
        "automation_available": False,
        "form_scanned": bool(discovered),
        "scanned_form": {"title": discovered.get("title"), "url": discovered.get("url")} if discovered else None,
        "automation_message": "Browser form filling has been removed. Use the official portal to enter and review the application yourself.",
        "safety_note": "Saarthi never reads passwords, OTPs, CAPTCHAs, or existing form values, and never submits the final application.",
    }


@app.post('/sessions/{sid}/live-application')
def start_live_application(sid: str, body: LiveApplicationIn):
    s = _session(sid)
    s.live_application = {
        "title": body.title.strip()[:160] or "Official government application",
        "url": _valid_live_application_url(body.url),
    }
    s.application_details.pop(LIVE_APPLICATION_KEY, None)
    s.discovered_forms.pop(LIVE_APPLICATION_KEY, None)
    return _live_application_plan(s)


@app.get('/sessions/{sid}/live-application/readiness')
def live_application_readiness(sid: str):
    return _live_application_plan(_session(sid))


@app.post('/sessions/{sid}/live-application/details')
def save_live_application_details(sid: str, body: ApplicationDetailsIn):
    s = _session(sid)
    plan = _live_application_plan(s)
    allowed = {str(field["key"]) for field in plan["fields"]}
    details = {
        key: value.strip() if isinstance(value, str) else value
        for key, value in body.details.items()
        if key in allowed and value not in (None, "")
    }
    s.application_details.setdefault(LIVE_APPLICATION_KEY, {}).update(details)
    profile_data = s.profile.model_dump()
    profile_data.update({key: value for key, value in details.items() if key in profile_data})
    s.profile = type(s.profile).model_validate(profile_data)
    return _live_application_plan(s)


@app.post('/sessions/{sid}/live-application/launch', include_in_schema=False)
def launch_live_application(sid: str):
    _browser_automation_removed()


@app.post('/sessions/{sid}/live-application/scan-open-form', include_in_schema=False)
def scan_live_application_form(sid: str, port: int = 9222):
    _browser_automation_removed()


@app.post('/sessions/{sid}/live-application/automate-fill', include_in_schema=False)
def automate_live_application_fill(sid: str, port: int = 9222):
    _browser_automation_removed()


# The former standalone server is now an in-process page.  Its router is
# namespaced so it can reuse this app's SessionStore without colliding with
# the main website's routes.
from app.guided_services.router import router as guided_services_router

app.include_router(guided_services_router)
