"""Deterministic, rule-based scheme eligibility engine.

These rules are the SOURCE OF TRUTH. The optional LLM enricher
(llm_enricher.py) may only ADD extra candidates flagged for manual
verification - it can never remove or override these results.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from app.core.profile import CitizenProfile

LAKH = 100_000


@dataclass
class SchemeResult:
    scheme_name: str
    eligibility_reason: str
    how_to_apply: str
    estimated_benefit: str
    verify_manually: bool = False


@dataclass
class Scheme:
    name: str
    how_to_apply: str
    estimated_benefit: str
    predicate: Callable[[CitizenProfile], Optional[str]]
    states: Optional[List[str]] = None  # None = central scheme


def _has_girl_child_below(p: CitizenProfile, age: int) -> bool:
    return any(c.gender == "female" and c.age < age for c in p.children)


# --- Central scheme predicates (return reason string, or None) -------------

def _pm_kisan(p: CitizenProfile) -> Optional[str]:
    if p.occupation == "farmer" and p.land_acres > 0:
        return "Farmer with cultivable land (income no bar)"
    return None


def _pm_awas(p: CitizenProfile) -> Optional[str]:
    if p.house_type in ("kutcha", "homeless") and (
        p.is_bpl or (p.annual_income is not None and p.annual_income <= 6 * LAKH)
    ):
        return "No pucca house and family in BPL/EWS/LIG income band"
    return None


def _ujjwala(p: CitizenProfile) -> Optional[str]:
    if p.gender == "female" and p.is_bpl and not p.has_lpg_connection:
        return "BPL woman without an LPG connection"
    return None


def _ayushman(p: CitizenProfile) -> Optional[str]:
    if p.annual_income is not None and p.annual_income <= 5 * LAKH:
        return "Family income upto Rs 5 lakh"
    return None


def _vishwakarma(p: CitizenProfile) -> Optional[str]:
    if p.occupation == "artisan" and (p.age or 0) >= 18:
        return "Artisan/craftsperson aged 18 or above"
    return None


def _sukanya(p: CitizenProfile) -> Optional[str]:
    if _has_girl_child_below(p, 10):
        return "Has a girl child below 10 years"
    return None


def _atal_pension(p: CitizenProfile) -> Optional[str]:
    if p.age is not None and 18 <= p.age <= 40 and p.employment_sector == "unorganized":
        return "Aged 18-40 and works in the unorganized sector"
    return None


def _mudra(p: CitizenProfile) -> Optional[str]:
    if p.is_entrepreneur or p.occupation == "small_business":
        return "Runs or is starting a small business"
    return None


def _standup(p: CitizenProfile) -> Optional[str]:
    if p.is_entrepreneur and (p.caste_category in ("SC", "ST") or p.gender == "female"):
        return "SC/ST or woman entrepreneur"
    return None


def _matru_vandana(p: CitizenProfile) -> Optional[str]:
    if p.is_pregnant and p.is_first_child and (p.age or 0) >= 19:
        return "Pregnant with first child, aged 19 or above"
    return None


# --- Maharashtra state scheme predicates ------------------------------------

def _ramai_awas(p: CitizenProfile) -> Optional[str]:
    if p.caste_category in ("SC", "NT") and p.is_bpl:
        return "SC/NT family in BPL category"
    return None


def _gharkul(p: CitizenProfile) -> Optional[str]:
    if p.residence_area == "rural" and p.house_type == "homeless":
        return "Rural homeless family"
    return None


def _phule_arogya(p: CitizenProfile) -> Optional[str]:
    if p.annual_income is not None and p.annual_income <= 1.5 * LAKH:
        return "Family income upto Rs 1.5 lakh"
    return None


def _mahadbt(p: CitizenProfile) -> Optional[str]:
    if (p.is_student or p.occupation == "student") and p.caste_category in ("SC", "ST", "OBC", "NT", "VJNT", "SBC", "MINORITY"):
        return "Student from SC/ST/OBC/NT/minority category"
    return None


def _shetkari(p: CitizenProfile) -> Optional[str]:
    if p.occupation == "farmer" and p.land_acres > 0:
        return "Farmer holding land in Maharashtra"
    return None


def _kanya_bhagyashree(p: CitizenProfile) -> Optional[str]:
    if _has_girl_child_below(p, 18) and p.annual_income is not None and p.annual_income <= 7.5 * LAKH:
        return "Girl child with family income upto Rs 7.5 lakh"
    return None


SCHEMES: List[Scheme] = [
    Scheme("PM-KISAN", "pmkisan.gov.in or nearest CSC", "Rs 6,000/year in 3 installments", _pm_kisan),
    Scheme("PM Awas Yojana", "Gram Panchayat / pmaymis.gov.in", "Rs 1.2-2.5 lakh housing assistance", _pm_awas),
    Scheme("Ujjwala Yojana", "Nearest LPG distributor with BPL card", "Free LPG connection + first refill", _ujjwala),
    Scheme("Ayushman Bharat", "Ayushman card at CSC / empanelled hospital", "Rs 5 lakh/year family health cover", _ayushman),
    Scheme("PM Vishwakarma", "pmvishwakarma.gov.in or CSC", "Rs 15,000 toolkit + training stipend + low-cost loans", _vishwakarma),
    Scheme("Sukanya Samriddhi Yojana", "Any post office or bank", "High-interest savings account for the girl child", _sukanya),
    Scheme("Atal Pension Yojana", "Any bank branch", "Rs 1,000-5,000/month pension after age 60", _atal_pension),
    Scheme("PM Mudra Yojana", "Any bank under Mudra", "Business loan up to Rs 10 lakh", _mudra),
    Scheme("Stand-Up India", "standupmitra.in or bank branch", "Loan Rs 10 lakh - Rs 1 crore for a new enterprise", _standup),
    Scheme("PM Matru Vandana Yojana", "Anganwadi / ASHA worker", "Rs 5,000 maternity cash benefit", _matru_vandana),
    # Maharashtra state schemes
    Scheme("Ramai Awas Yojana", "Gram Panchayat / Social Justice Department", "Housing assistance for SC/NT families", _ramai_awas, states=["Maharashtra"]),
    Scheme("Gharkul Yojana", "Gram Panchayat", "Rural housing assistance", _gharkul, states=["Maharashtra"]),
    Scheme("Mahatma Phule Jan Arogya Yojana", "Empanelled hospital / Aarogyamitra", "Cashless health cover for low-income families", _phule_arogya, states=["Maharashtra"]),
    Scheme("MahaDBT Scholarship", "mahadbt.maharashtra.gov.in", "Tuition + maintenance scholarship", _mahadbt, states=["Maharashtra"]),
    Scheme("Shetkari Sanman Yojana", "Taluka agriculture office", "Direct income support for Maharashtra farmers", _shetkari, states=["Maharashtra"]),
    Scheme("Majhi Kanya Bhagyashree", "District Women & Child Development office", "Rs 50,000 deposit for the girl child", _kanya_bhagyashree, states=["Maharashtra"]),
]


def check_eligibility(profile: CitizenProfile) -> List[SchemeResult]:
    """Return every scheme the citizen provably qualifies for, with reasons."""
    results: List[SchemeResult] = []
    for scheme in SCHEMES:
        if scheme.states and not any(profile.state.strip().lower() == s.strip().lower() for s in scheme.states):
            continue
        reason = scheme.predicate(profile)
        if reason:
            results.append(
                SchemeResult(
                    scheme_name=scheme.name,
                    eligibility_reason=reason,
                    how_to_apply=scheme.how_to_apply,
                    estimated_benefit=scheme.estimated_benefit,
                )
            )
    return results
