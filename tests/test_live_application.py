from app.main import (
    LIVE_APPLICATION_KEY,
    LiveApplicationIn,
    live_application_readiness,
    start_live_application,
    store,
)


def test_live_guidance_application_uses_scanned_requirements():
    session = store.create()
    try:
        initial = start_live_application(
            session.id,
            LiveApplicationIn(title="Official scholarship", url="https://myscheme.gov.in/example"),
        )
        assert initial["application_type"] == "live_guidance"
        assert initial["form_scanned"] is False

        session.discovered_forms[LIVE_APPLICATION_KEY] = {
            "title": "Scholarship application",
            "url": "https://myscheme.gov.in/example/form",
            "fields": [
                {"key": "full_name", "label": "Full name", "type": "text", "required": True},
                {"key": "course", "label": "Course", "type": "text", "required": True},
                {"key": "income_certificate", "label": "Income certificate", "type": "file", "required": True},
            ],
            "documents": ["Income Certificate", "Caste Certificate"],
        }
        session.profile.name = "Asha Patil"

        plan = live_application_readiness(session.id)
        assert plan["form_scanned"] is True
        assert plan["documents"] == ["Income Certificate", "Caste Certificate"]
        assert [field["key"] for field in plan["fields"]] == ["full_name", "course"]
        assert plan["missing_fields"] == ["course"]
    finally:
        store.wipe(session.id)
