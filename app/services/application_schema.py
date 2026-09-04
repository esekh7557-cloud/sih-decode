"""Configured application fields used by the guided-services intake flow."""
from __future__ import annotations

from typing import Any

from app.services.catalog import get_service


_CHOICE = {
    "applying_for": [("Self", "Self"), ("Minor", "Minor")],
    "title": [("Mr.", "Mr."), ("Mrs.", "Mrs."), ("Ms.", "Ms.")],
    "gender": [("female", "Female"), ("male", "Male"), ("other", "Other")],
    "marital_status": [("Unmarried", "Unmarried"), ("Married", "Married")],
    "guardian_relation": [
        ("Father", "Father"),
        ("Husband", "Husband"),
        ("Wife", "Wife"),
        ("Guardian", "Guardian"),
    ],
    "occupation": [
        ("farmer", "Farmer"),
        ("salaried", "Salaried employee"),
        ("artisan", "Artisan / craftsperson"),
        ("small_business", "Small-business owner"),
        ("unemployed", "Unemployed"),
        ("pensioner", "Pensioner"),
        ("student", "Student"),
    ],
    "caste_category": [
        (value, value.title() if value != "MINORITY" else "Minority")
        for value in ("GENERAL", "SC", "ST", "OBC", "NT", "VJNT", "SBC", "MINORITY")
    ],
    "previous_certificate": [("No", "No"), ("Yes", "Yes")],
    "immovable_property": [("No", "No"), ("Yes", "Yes")],
    "id_proof_type": [
        ("Aadhar Card", "Aadhaar Card"),
        ("PAN Card", "PAN Card"),
        ("Voter ID", "Voter ID"),
    ],
    "certify": [("Yes", "Yes"), ("No", "No")],
}

_NUMBER_FIELDS = {
    "annual_income",
    "residence_period",
    "family_size",
    "earning_members",
    "children_count",
    "property_value",
    "other_income",
    "part_no",
    "serial_no",
    "electoral_year",
}

_EMAIL_FIELDS = {"email"}
_TEL_FIELDS = {"mobile"}
_TEXTAREA_FIELDS = {"address", "property_details"}

_LABELS = {
    "applying_for": "Who are you applying for?",
    "purpose": "Which purpose do you need the income certificate for?",
    "residence_period": "How many years have you been residing in Goa?",
    "title": "What is your title?",
    "name": "What is the applicant's full name?",
    "place_of_birth": "Where was the applicant born?",
    "dob": "What is the applicant's date of birth?",
    "gender": "What is the applicant's gender?",
    "marital_status": "What is the applicant's marital status?",
    "guardian_relation": "What is the applicant's relation to the guardian?",
    "father_name": "What is the father's, husband's, or guardian's name?",
    "mobile": "What mobile number should be used for this application?",
    "email": "What email address should be used?",
    "occupation": "What is the applicant's occupation?",
    "annual_income": "What is the family's total annual income in rupees?",
    "caste_category": "What is the applicant's caste category?",
    "address": "What is the applicant's full address?",
    "locality": "What is the locality, area, or ward?",
    "district": "What is the district?",
    "taluka": "What is the taluka?",
    "village": "What is the village or city?",
    "pincode": "What is the six-digit pincode?",
    "family_size": "How many people are in the family?",
    "earning_members": "How many family members earn?",
    "children_count": "How many children are in the family?",
    "previous_certificate": "Has an income certificate been issued recently?",
    "immovable_property": "Does the family have any immovable property?",
    "property_value": "What is the value of the property? Enter 0 if none.",
    "other_income": "What is the income from other sources? Enter 0 if none.",
    "part_no": "What is the electoral roll part number?",
    "serial_no": "What is the electoral roll serial number?",
    "electoral_year": "What is the electoral roll year?",
    "constituency": "What is the electoral constituency?",
    "ration_card": "What is the ration card number?",
    "property_details": "Describe the property, or enter None.",
    "id_proof_type": "Which ID proof will you use?",
    "id_proof_no": "What is the ID proof number?",
    "certify": "Do you certify that the information provided is correct?",
}


def _field_type(key: str) -> str:
    if key in _CHOICE:
        return "radio" if key in {"previous_certificate", "immovable_property", "certify"} else "select"
    if key in _NUMBER_FIELDS:
        return "number"
    if key in _EMAIL_FIELDS:
        return "email"
    if key in _TEL_FIELDS:
        return "tel"
    if key in _TEXTAREA_FIELDS:
        return "textarea"
    return "text"


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def required_application_fields(service_id: str, profile: Any) -> dict:
    """Return the configured required fields and typed missing-field details."""
    service = get_service(service_id)
    if not service:
        return {"service_id": service_id, "fields": [], "missing_fields": []}

    configured = service.get("application_fields") or []
    profile_data = profile.model_dump()
    fields = []
    missing_fields = []
    for key in configured:
        key = str(key)
        value = profile_data.get(key, "")
        missing = not _present(value)
        if missing:
            missing_fields.append(key)
        item = {
            "key": key,
            "label": _LABELS.get(key, key.replace("_", " ").capitalize()),
            "question": _LABELS.get(key, f"What is the {key.replace('_', ' ')}?"),
            "type": _field_type(key),
            "options": [{"value": value, "label": label} for value, label in _CHOICE.get(key, [])],
            "value": value if _present(value) else "",
            "required": True,
            "missing": missing,
        }
        if key in _NUMBER_FIELDS:
            item["min"] = "0"
        if key == "pincode":
            item["inputmode"] = "numeric"
            item["max_length"] = 6
        fields.append(item)

    return {
        "service_id": service_id,
        "service": service.get("name", service_id),
        "fields": fields,
        "missing_fields": missing_fields,
    }
