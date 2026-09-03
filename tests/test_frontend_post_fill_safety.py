from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def _function_body(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    end = source.find("\nfunction ", start + 1)
    return source[start:] if end < 0 else source[start:end]


def test_dedicated_application_flow_requires_a_post_fill_document_click():
    source = (FRONTEND / "application.js").read_text(encoding="utf-8")
    body = _function_body(source, "renderReviewStep")
    success = body[body.index("const result = await api(path"):body.index("} catch")]

    # Reaching the document/upload page is deliberately nested inside the
    # citizen's post-fill confirmation click, rather than happening when the
    # fill endpoint returns.
    confirmation = success.index('documents.addEventListener("click"')
    transition = success.index('goToApplicationStep("submit"')
    assert confirmation < transition
    assert "automate_upload" not in success


def test_dashboard_catalog_and_live_fill_pause_at_post_fill_review():
    source = (FRONTEND / "app.js").read_text(encoding="utf-8")
    for function_name, endpoint in (
        ("renderApplicationReview", '"/sessions/" + sessionId + "/automate_fill"'),
        ("renderLiveApplicationReview", '"/sessions/" + sessionId + "/live-application/automate-fill"'),
    ):
        body = _function_body(source, function_name)
        success = body[body.index(endpoint):body.index("} catch", body.index(endpoint))]

        assert "renderPostFillReview" in success
        assert "renderDocumentUploadStep(" not in success
        assert "automate_upload" not in success
