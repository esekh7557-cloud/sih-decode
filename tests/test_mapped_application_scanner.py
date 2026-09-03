from app.main import application_readiness, store


def test_mapped_application_keeps_choice_metadata_from_different_dom_keys():
    """A verified mapping must not discard scanner choices just because IDs differ."""
    session = store.create(sample=False)
    try:
        session.discovered_forms["CERT_INC"] = {
            "title": "Goa Online",
            "url": "https://services.goaonline.gov.in/example",
            "documents": [],
            "fields": [
                {
                    "key": "wmcapplying_rdltype",
                    "label": "Applying for:",
                    "type": "radio",
                    "required": True,
                    "options": [
                        {"value": "radio22", "label": "Self"},
                        {"value": "radio23", "label": "Relative or others"},
                    ],
                },
                {
                    "key": "drppurpose",
                    "label": "Purpose",
                    "type": "select",
                    "required": True,
                    "options": [
                        {"value": "15", "label": "Construction/Repair Of Toilet"},
                        {"value": "8", "label": "Economically Weaker Sections"},
                    ],
                },
            ],
        }

        plan = application_readiness(session.id, "CERT_INC")
        fields = {field["key"]: field for field in plan["fields"]}

        # The stable keys are retained for profile reuse and the verified
        # autofill mapping, while the DOM scanner supplies the question type
        # and choices that the frontend needs to render.
        assert fields["applying_for"]["type"] == "radio"
        assert fields["applying_for"]["options"] == [
            {"value": "radio22", "label": "Self"},
            {"value": "radio23", "label": "Relative or others"},
        ]
        assert fields["purpose"]["type"] == "select"
        assert fields["purpose"]["options"] == [
            {"value": "15", "label": "Construction/Repair Of Toilet"},
            {"value": "8", "label": "Economically Weaker Sections"},
        ]
    finally:
        store.wipe(session.id)


def test_option_labels_match_a_mapped_radio_group_without_a_group_alias():
    """Some legacy mappings list choice labels instead of the group heading."""
    session = store.create(sample=False)
    try:
        session.discovered_forms["CASTE"] = {
            "title": "Goa Online",
            "url": "https://services.goaonline.gov.in/example",
            "documents": [],
            "fields": [
                {
                    "key": "wmcapplying_rdltype",
                    "label": "Applying for:",
                    "type": "radio",
                    "required": True,
                    "options": [
                        {"value": "radio22", "label": "Self"},
                        {"value": "radio23", "label": "Relative or others"},
                    ],
                },
            ],
        }

        plan = application_readiness(session.id, "CASTE")
        fields = {field["key"]: field for field in plan["fields"]}

        assert fields["applying_for"]["type"] == "radio"
        assert [choice["label"] for choice in fields["applying_for"]["options"]] == [
            "Self",
            "Relative or others",
        ]
    finally:
        store.wipe(session.id)


def test_scanned_no_upload_form_does_not_force_configured_documents():
    session = store.create(sample=False)
    try:
        session.discovered_forms["CERT_INC"] = {
            "title": "No-upload form",
            "url": "https://services.goaonline.gov.in/example",
            "documents": [],
            "fields": [{"key": "name", "label": "Applicant name", "type": "text", "required": True}],
        }
        plan = application_readiness(session.id, "CERT_INC")
        assert plan["documents"] == []
        assert plan["document_uploads_detected"] is False
    finally:
        store.wipe(session.id)
