"""Citizen profile model and identity validators.

Security: only the LAST 4 digits of Aadhaar are ever stored or displayed.
"""
from __future__ import annotations

import re
from typing import List, Optional

from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field, model_validator
import yaml

_SAMPLE_PROFILE_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_profile.yaml"

# ---------------------------------------------------------------------------
# Verhoeff checksum (the algorithm used by Aadhaar numbers)
# ---------------------------------------------------------------------------
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_validate(number: str) -> bool:
    """Return True if the digit string has a valid Verhoeff checksum."""
    if not number.isdigit():
        return False
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_generate(number: str) -> str:
    """Return the Verhoeff check digit for the given digit string."""
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


def validate_aadhaar(aadhaar: str) -> bool:
    """Aadhaar: 12 digits, first digit 2-9, valid Verhoeff checksum."""
    digits = re.sub(r"\s", "", aadhaar)
    return len(digits) == 12 and digits.isdigit() and digits[0] not in "01" and verhoeff_validate(digits)


def validate_pan(pan: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan.strip().upper()))


def validate_mobile(mobile: str) -> bool:
    cleaned = re.sub(r"[\s\-\+]", "", mobile)
    if cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = cleaned[1:]
    return bool(re.fullmatch(r"[6-9][0-9]{9}", cleaned))


def mask_aadhaar(aadhaar: str) -> str:
    """Always display Aadhaar as 'XXXX XXXX 1234'."""
    digits = re.sub(r"\s", "", aadhaar)
    return f"XXXX XXXX {digits[-4:]}" if len(digits) >= 4 else "XXXX"


class Child(BaseModel):
    gender: str  # "male" | "female"
    age: int


class CitizenProfile(BaseModel):
    """Everything the kiosk knows about the citizen for ONE session.

    Held in memory only; wiped when the session ends.
    """

    name: str = ""
    father_name: str = ""
    dob: str = ""
    age: Optional[int] = None
    gender: str = ""  # male | female | other
    mobile: str = ""
    aadhaar_last4: str = ""
    address: str = ""
    village: str = ""
    taluka: str = ""
    district: str = ""
    state: str = "Maharashtra"
    residence_area: str = "rural"  # rural | urban
    occupation: str = ""  # farmer | salaried | artisan | small_business | unemployed | pensioner | student
    employment_sector: str = ""  # organized | unorganized
    annual_income: Optional[int] = None
    caste_category: str = ""  # SC | ST | OBC | NT | VJNT | SBC | MINORITY | GENERAL
    family_size: Optional[int] = None
    land_acres: float = 0.0
    house_type: str = ""  # pucca | kutcha | homeless
    has_lpg_connection: bool = True
    
    # --- Goa Portal Specific New Fields ---
    applying_for: str = ""
    purpose: str = ""
    residence_period: str = ""
    title: str = ""
    place_of_birth: str = ""
    marital_status: str = ""
    guardian_relation: str = ""
    email: str = ""
    locality: str = ""
    pincode: str = ""
    earning_members: Optional[int] = None
    children_count: Optional[int] = None
    previous_certificate: str = ""
    immovable_property: str = ""
    property_value: str = ""
    other_income: str = ""
    part_no: str = ""
    serial_no: str = ""
    electoral_year: str = ""
    constituency: str = ""
    ration_card: str = ""
    property_details: str = ""
    id_proof_type: str = ""
    id_proof_no: str = ""
    certify: str = ""
    # --------------------------------------
    is_bpl: bool = False
    is_student: bool = False
    is_entrepreneur: bool = False
    is_pregnant: bool = False
    is_first_child: bool = False
    children: List[Child] = Field(default_factory=list)

    @model_validator(mode="after")
    def compute_age(self) -> CitizenProfile:
        if self.dob and self.age is None:
            try:
                dob_date = datetime.strptime(self.dob.strip(), "%d/%m/%Y")
                today = datetime.today()
                self.age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
            except ValueError:
                pass
        return self

    def set_aadhaar(self, aadhaar: str) -> bool:
        """Validate Aadhaar and store ONLY the last 4 digits."""
        if not validate_aadhaar(aadhaar):
            return False
        self.aadhaar_last4 = re.sub(r"\s", "", aadhaar)[-4:]
        return True

    def to_bookmarklet_dict(self) -> dict:
        """Convert profile to the exact dictionary expected by the portal auto-fill bookmarklet."""
        return {
            "applying_for": self.applying_for or "Self",
            "purpose": self.purpose or "economically weaker section",
            "residence_period": int(self.residence_period) if str(self.residence_period).isdigit() else (self.residence_period or 15),
            "title": self.title or ("Mr." if self.gender.lower() == "male" else ("Mrs." if self.gender.lower() == "female" else "Mr.")),
            "name": self.name or "",
            "place_of_birth": self.place_of_birth or self.village or "",
            "dob": self.dob or "",
            "gender": self.gender or "male",
            "marital_status": self.marital_status or "Married",
            "guardian_relation": self.guardian_relation or "Father",
            "father_name": self.father_name or "",
            "mobile": self.mobile or "",
            "email": self.email or "",
            "occupation": self.occupation or "employed",
            "caste_category": self.caste_category or "GENERAL",
            "address": self.address or "",
            "locality": self.locality or self.village or "",
            "district": self.district or "",
            "taluka": self.taluka or "",
            "village": self.village or "",
            "pincode": self.pincode or "",
            "family_size": self.family_size or 4,
            "earning_members": self.earning_members or 1,
            "children_count": self.children_count or len(self.children) or 2,
            "previous_certificate": self.previous_certificate or "No",
            "immovable_property": self.immovable_property or "no",
            "property_value": str(self.property_value or "0"),
            "other_income": str(self.other_income or "0"),
            "part_no": str(self.part_no or "12"),
            "serial_no": str(self.serial_no or "345"),
            "electoral_year": str(self.electoral_year or "2023"),
            "constituency": self.constituency or self.taluka or "",
            "ration_card": self.ration_card or "",
            "property_details": self.property_details or "None",
            "id_proof_type": self.id_proof_type or "aadhaar card",
            "id_proof_no": self.id_proof_no or (f"XXXX XXXX {self.aadhaar_last4}" if self.aadhaar_last4 else ""),
            "certify": self.certify or "click it"
        }


def sample_profile() -> CitizenProfile:
    """Load the editable local starter profile for new demo sessions."""
    try:
        with open(_SAMPLE_PROFILE_PATH, encoding="utf-8") as handle:
            values = yaml.safe_load(handle) or {}
        allowed = set(CitizenProfile.model_fields)
        return CitizenProfile.model_validate({key: value for key, value in values.items() if key in allowed})
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        return CitizenProfile()
