"""Keep the browser language picker and API language validation in sync."""
from pathlib import Path
import re

from app.i18n.phrases import PHRASES, SUPPORTED


EXPECTED_LANGUAGE_CODES = {"en", "hi", "te", "ta", "bn", "mr", "gu", "kn", "ml", "pa"}


def test_ten_languages_have_complete_api_phrases():
    assert set(SUPPORTED) == EXPECTED_LANGUAGE_CODES
    for phrase in PHRASES.values():
        assert EXPECTED_LANGUAGE_CODES <= set(phrase)


def test_browser_picker_matches_api_languages():
    source = (Path(__file__).parents[1] / "frontend" / "i18n.js").read_text(encoding="utf-8")
    picker = source.split("const languages = [", 1)[1].split("];", 1)[0]
    browser_codes = set(re.findall(r'\["([a-z]+)",', picker))
    assert browser_codes == EXPECTED_LANGUAGE_CODES
