import asyncio

from app.main import AssistantIn, citizen_assistant, store


async def _no_enrichment(profile, results, language):
    return results


def test_scholarship_request_collects_missing_details_and_saves_them(monkeypatch):
    monkeypatch.setattr("app.main.enrich", _no_enrichment)
    session = store.create(sample=False)
    try:
        first = asyncio.run(citizen_assistant(session.id, AssistantIn(message="I want to get a scholarship")))

        assert first["pending_request"]["intent"] == "scholarship"
        assert "age" in first["pending_request"]["missing_fields"]
        assert "annual family income" in first["reply"]

        second = asyncio.run(
            citizen_assistant(
                session.id,
                AssistantIn(
                    message="I am 19, a student, SC, my family income is ₹2 lakh, and I live in Maharashtra."
                ),
            )
        )

        assert second["pending_request"] is None
        assert second["saved_profile_fields"]
        assert second["profile"]["age"] == 19
        assert second["profile"]["occupation"] == "student"
        assert second["profile"]["annual_income"] == 200000
        assert second["profile"]["caste_category"] == "SC"
        assert any(item["scheme_name"] == "MahaDBT Scholarship" for item in second["recommendations"])
    finally:
        store.wipe(session.id)


def test_scholarship_search_waits_for_details_and_uses_safe_profile_context(monkeypatch):
    monkeypatch.setattr("app.main.enrich", _no_enrichment)
    searches = []

    async def _fake_guidance(message, state="", profile=None):
        searches.append((message, state, profile))
        return {
            "searched": True,
            "configured": True,
            "notice": "Official results found.",
            "steps": [],
            "sources": [{"title": "National Scholarship Portal", "url": "https://scholarships.gov.in/", "snippet": ""}],
        }

    monkeypatch.setattr("app.main.get_live_guidance", _fake_guidance)
    session = store.create(sample=False)
    try:
        first = asyncio.run(citizen_assistant(session.id, AssistantIn(message="I want a scholarship")))
        assert first["pending_request"] is not None
        assert searches == []

        second = asyncio.run(
            citizen_assistant(
                session.id,
                AssistantIn(message="I am 19, a student, SC, my family income is Rs 2 lakh, and I live in Maharashtra."),
            )
        )
        assert second["pending_request"] is None
        assert len(searches) == 1
        topic, state, profile = searches[0]
        assert topic == "I want a scholarship"
        assert state == "Maharashtra"
        assert profile["age"] == 19
        assert profile["occupation"] == "student"
        assert profile["annual_income"] == 200000
        assert second["live_guidance"]["sources"]
    finally:
        store.wipe(session.id)
