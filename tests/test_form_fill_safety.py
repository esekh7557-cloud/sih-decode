import asyncio

import pytest
from fastapi import HTTPException

from app.agent.executor import execute_form_fill
from app.main import api_execute_form
from app.services import generic_form_filler


def test_generic_filler_never_sends_display_masks_to_cdp(monkeypatch):
    calls = []
    monkeypatch.setattr(
        generic_form_filler,
        "evaluate_open_form",
        lambda expression, port: calls.append((expression, port)) or ["Full name"],
    )

    changed = generic_form_filler.fill_open_form([
        {"key": "full_name", "label": "Full name", "type": "text", "value": "Asha Patil"},
        {"key": "id_proof_no", "label": "ID proof number", "type": "text", "value": "XXXX XXXX 1234"},
        {"key": "identity", "label": "Identity number", "type": "text", "value": "••••1234"},
        {"key": "legacy_identity", "label": "Identity number", "type": "text", "value": "â€¢â€¢â€¢â€¢1234"},
    ], port=9333)

    assert changed == ["Full name"]
    assert len(calls) == 1
    expression, port = calls[0]
    assert port == 9333
    assert "Asha Patil" in expression
    assert "XXXX XXXX 1234" not in expression
    assert "••••1234" not in expression
    assert "â€¢â€¢â€¢â€¢1234" not in expression
    assert ".click(" not in generic_form_filler._FILL_REVIEWED_FIELDS


def test_retired_executor_endpoint_refuses_unreviewed_automation():
    with pytest.raises(RuntimeError, match="disabled"):
        asyncio.run(execute_form_fill("https://example.gov.in", {"name": "Asha"}))

    with pytest.raises(HTTPException) as execution_error:
        asyncio.run(api_execute_form(None))
    assert execution_error.value.status_code == 410
