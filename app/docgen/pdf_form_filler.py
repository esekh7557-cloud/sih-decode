"""Inspect and fill AcroForm PDF fields using reviewed citizen data."""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from app.core.profile import CitizenProfile


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _profile_values(profile: CitizenProfile) -> dict[str, Any]:
    values = profile.model_dump()
    values.update({
        "full_name": profile.name,
        "applicant_name": profile.name,
        "phone": profile.mobile,
        "mobile_number": profile.mobile,
        "income": profile.annual_income,
        "annual_family_income": profile.annual_income,
        "category": profile.caste_category,
        "pin_code": profile.pincode,
        "postal_code": profile.pincode,
        "id_proof_no": f"XXXX XXXX {profile.aadhaar_last4}" if profile.aadhaar_last4 else profile.id_proof_no,
    })
    return values


def _suggestion(field_name: str, profile: CitizenProfile) -> Any:
    values = _profile_values(profile)
    target = _normalise(field_name)
    aliases = {
        "name": ("name", "fullname", "applicantname", "beneficiaryname"),
        "father_name": ("fathername", "fathersname", "guardianname"),
        "dob": ("dob", "dateofbirth", "birthdate"),
        "mobile": ("mobile", "mobilenumber", "phone", "phonenumber"),
        "email": ("email", "emailaddress"),
        "address": ("address", "fulladdress", "residentialaddress"),
        "village": ("village", "town", "city"),
        "district": ("district",),
        "taluka": ("taluka", "tehsil", "block"),
        "state": ("state",),
        "pincode": ("pincode", "zipcode", "postalcode"),
        "gender": ("gender", "sex"),
        "occupation": ("occupation", "occupationalstatus"),
        "annual_income": ("income", "annualincome", "annualfamilyincome", "familyincome"),
        "caste_category": ("caste", "category", "socialcategory"),
    }
    for key, names in aliases.items():
        if target in names or any(name in target for name in names):
            return values.get(key, "")
    for key, value in values.items():
        if _normalise(key) == target:
            return value
    return ""


def _options(field: dict[str, Any]) -> list[str]:
    raw = field.get("/Opt", []) or []
    if not isinstance(raw, list):
        return []
    options = []
    for option in raw:
        if isinstance(option, list) and option:
            option = option[-1]
        text = str(option)
        if text and text not in options:
            options.append(text)
    return options[:40]


def inspect_pdf(path: str | Path, profile: CitizenProfile) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF support is not installed. Install the project requirements and try again.") from exc

    reader = PdfReader(str(path))
    fields = reader.get_fields() or {}
    result = []
    for name, field in fields.items():
        field_name = str(name)
        field_type = str(field.get("/FT", "/Tx"))
        value = field.get("/V", "")
        if value in (None, "/Off"):
            value = ""
        suggested = _suggestion(field_name, profile)
        result.append({
            "name": field_name,
            "label": re.sub(r"[_./-]+", " ", field_name).strip().title(),
            "type": {"/Btn": "checkbox", "/Ch": "choice", "/Tx": "text"}.get(field_type, "text"),
            "value": str(value),
            "suggested_value": "" if suggested is None else str(suggested),
            "options": _options(field),
        })
    return {"filename": Path(path).name, "field_count": len(result), "fields": result}


def fill_pdf(path: str | Path, values: dict[str, Any], output_dir: str | Path) -> str:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError as exc:
        raise RuntimeError("PDF support is not installed. Install the project requirements and try again.") from exc

    reader = PdfReader(str(path))
    known_fields = reader.get_fields() or {}
    safe_values = {str(key): str(value) for key, value in values.items() if str(key) in known_fields}
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    for page in writer.pages:
        writer.update_page_form_field_values(page, safe_values, auto_regenerate=True)

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    output_path = destination / f"filled_form_{uuid.uuid4().hex[:10]}.pdf"
    with open(output_path, "wb") as handle:
        writer.write(handle)
    return str(output_path)
