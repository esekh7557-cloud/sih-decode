import asyncio

from app.main import AssistantIn, citizen_assistant, store


async def _no_enrichment(profile, results, language):
    return results


def test_assistant_returns_choices_for_structured_follow_up(monkeypatch):
    monkeypatch.setattr("app.main.enrich", _no_enrichment)
    session = store.create(sample=False)
    try:
        result = asyncio.run(citizen_assistant(session.id, AssistantIn(message="I want a scholarship")))

        assert result["pending_request"]["question_options"] == []
        session.profile.age = 19
        session.profile.state = ""
        result = asyncio.run(citizen_assistant(session.id, AssistantIn(message="I am a student")))
        assert result["pending_request"]["question_field"] == "state"
        assert {item["value"] for item in result["pending_request"]["question_options"]} >= {"Goa", "Maharashtra"}
    finally:
        store.wipe(session.id)
