from app.core.profile import Child, CitizenProfile
from app.eligibility.rules import check_eligibility


def names(profile):
    return {r.scheme_name for r in check_eligibility(profile)}


def test_farmer_in_maharashtra_gets_central_and_state_schemes():
    p = CitizenProfile(occupation="farmer", land_acres=2.0, state="Maharashtra", age=45)
    got = names(p)
    assert "PM-KISAN" in got
    assert "Shetkari Sanman Yojana" in got


def test_bpl_woman_without_lpg():
    p = CitizenProfile(
        gender="female", is_bpl=True, has_lpg_connection=False, annual_income=80_000, age=30
    )
    got = names(p)
    assert "Ujjwala Yojana" in got
    assert "Ayushman Bharat" in got  # income below 5 lakh
    assert "Mahatma Phule Jan Arogya Yojana" in got  # income below 1.5 lakh, MH default


def test_sc_student_gets_mahadbt():
    p = CitizenProfile(is_student=True, caste_category="SC", age=19)
    assert "MahaDBT Scholarship" in names(p)


def test_state_schemes_excluded_outside_maharashtra():
    p = CitizenProfile(occupation="farmer", land_acres=1.0, state="Gujarat")
    got = names(p)
    assert "PM-KISAN" in got
    assert "Shetkari Sanman Yojana" not in got


def test_girl_child_schemes():
    p = CitizenProfile(children=[Child(gender="female", age=4)], annual_income=300_000)
    got = names(p)
    assert "Sukanya Samriddhi Yojana" in got
    assert "Majhi Kanya Bhagyashree" in got


def test_reasons_are_present():
    p = CitizenProfile(occupation="farmer", land_acres=1.0)
    for r in check_eligibility(p):
        assert r.eligibility_reason
        assert r.how_to_apply
        assert r.estimated_benefit
        assert r.verify_manually is False  # rule-based results are authoritative


def test_empty_profile_qualifies_for_nothing():
    assert names(CitizenProfile()) == set()
