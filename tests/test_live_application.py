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


def test_live_application_reuses_document_extracted_fields_before_asking():
    session = store.create()
    try:
        start_live_application(
            session.id,
            LiveApplicationIn(title="Official scholarship", url="https://myscheme.gov.in/example"),
        )
        session.discovered_forms[LIVE_APPLICATION_KEY] = {
            "title": "Scholarship application",
            "url": "https://myscheme.gov.in/example/form",
            "fields": [
                {"key": "course", "label": "Course", "type": "text", "required": True},
                {"key": "college", "label": "College", "type": "text", "required": True},
            ],
            "documents": ["College ID"],
        }
        session.document_extractions.append(
            {"document_type": "College ID", "fields": {"course": "BSc Computer Science"}}
        )

        plan = live_application_readiness(session.id)

        assert plan["fields"][0]["value"] == "BSc Computer Science"
        assert plan["fields"][0]["missing"] is False
        assert plan["missing_fields"] == ["college"]
    finally:
        store.wipe(session.id)


def test_live_application_keeps_scanned_question_type_choices_and_constraints():
    session = store.create()
    try:
        start_live_application(
            session.id,
            LiveApplicationIn(title="Official scholarship", url="https://myscheme.gov.in/example"),
        )
        session.discovered_forms[LIVE_APPLICATION_KEY] = {
            "title": "Scholarship application",
            "url": "https://myscheme.gov.in/example/form",
            "fields": [
                {
                    "key": "study_mode",
                    "label": "Study mode",
                    "type": "radio",
                    "required": True,
                    "options": [
                        {"value": "full_time", "label": "Full time"},
                        {"value": "part_time", "label": "Part time"},
                    ],
                },
                {
                    "key": "completion_date",
                    "label": "Course completion date",
                    "type": "date",
                    "required": True,
                    "min": "2020-01-01",
                    "max": "2030-12-31",
                },
            ],
            "documents": [],
        }

        plan = live_application_readiness(session.id)
        choice, date = plan["fields"]
        assert choice["type"] == "radio"
        assert choice["options"][0] == {"value": "full_time", "label": "Full time"}
        assert date["type"] == "date"
        assert date["min"] == "2020-01-01"
        assert date["max"] == "2030-12-31"
    finally:
        store.wipe(session.id)


def test_live_application_marks_no_upload_form():
    session = store.create(sample=False)
    try:
        start_live_application(
            session.id,
            LiveApplicationIn(title="Official application", url="https://myscheme.gov.in/example"),
        )
        session.discovered_forms[LIVE_APPLICATION_KEY] = {
            "title": "No-upload form",
            "url": "https://myscheme.gov.in/example/form",
            "fields": [{"key": "name", "label": "Name", "type": "text", "required": True}],
            "documents": [],
        }
        plan = live_application_readiness(session.id)
        assert plan["documents"] == []
        assert plan["document_uploads_detected"] is False
    finally:
        store.wipe(session.id)
