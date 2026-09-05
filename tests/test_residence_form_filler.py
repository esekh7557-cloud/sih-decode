from app.guided_services.form_filler import default_form_data
from app.guided_services.residence_form_filler import (
    _RESIDENCE_MODAL_ALIASES,
    native_date_value,
    portal_date_value,
    residence_demo_overrides,
    residence_modal_values,
)


def test_residence_modal_uses_shared_address_and_residence_defaults():
    data = default_form_data()
    data.update(
        {
            "address": "12, Church Road",
            "locality": "Altinho",
            "district": "North Goa",
            "taluka": "Tiswadi",
            "village": "Panaji",
            "pincode": "403001",
        }
    )

    values = residence_modal_values(data)

    assert values["house_no"] == "12, Church Road"
    assert values["rented_owned"] == "Owned"
    assert values["currently_staying"] == "Yes"
    assert values["period_of_stay"] == "Since"
    assert values["apply_to_concerned_office"] == "Yes"


def test_residence_modal_accepts_specific_overrides_and_has_all_scraped_fields():
    data = default_form_data()
    data.update(
        {
            "house_no": "Flat 4B",
            "rented_owned": "Rented",
            "period_of_stay": "For",
            "residence_from_date": "01-JAN-2020",
            "residence_to_date": "05-SEP-2026",
        }
    )

    values = residence_modal_values(data)

    assert values["house_no"] == "Flat 4B"
    assert values["rented_owned"] == "Rented"
    assert values["period_of_stay"] == "For"
    assert values["from_date"] == "01-JAN-2020"
    assert values["to_date"] == "05-SEP-2026"
    assert set(values) == set(_RESIDENCE_MODAL_ALIASES)


def test_residence_answers_are_kept_separate_from_income_demo_data():
    values = residence_demo_overrides()

    assert values["purpose"] == "Other"
    assert values["where_to_submit"] == "Education institute"
    assert values["residence_months"] == "5"
    assert values["rented_owned"] == "Owned"
    assert values["period_of_stay"] == "Since"
    assert values["residence_from_date"] == "25-MAR-2011"
    assert values["voter_id_no"] == ""


def test_residence_defaults_include_fields_missing_from_the_scraped_mapping():
    data = default_form_data()

    assert data["employment_details"]
    assert data["guardian_relation"] == "Father"


def test_native_date_value_converts_portal_date_formats():
    assert native_date_value("25-MAR-2011") == "2011-03-25"
    assert native_date_value("05/09/2026") == "2026-09-05"
    assert native_date_value("2026-09-05") == "2026-09-05"


def test_portal_date_value_uses_the_goa_online_date_picker_format():
    assert portal_date_value("2011-03-25") == "25-MAR-2011"
    assert portal_date_value("05/09/2026") == "05-SEP-2026"
