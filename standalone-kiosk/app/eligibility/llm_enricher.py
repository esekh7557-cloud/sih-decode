"""Optional LLM second pass over rule-based eligibility results (OpenRouter).

Design rules:
- The API key is read ONLY from the OPENROUTER_API_KEY environment variable.
  Never hardcode or commit keys.
- Graceful degradation: if the key is missing, or the call fails, times out,
  or returns malformed output, the rule-based results are returned unchanged.
- The LLM may only ADD candidate schemes; every addition is flagged
  verify_manually=True and must be confirmed by office staff. It can never
  remove or override a rule-based result.
- No PII is sent: name, mobile, Aadhaar, DOB and address are stripped first.
"""
from __future__ import annotations

import json
import os
from typing import List

import httpx

from app.core.profile import CitizenProfile
from app.eligibility.rules import SchemeResult

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
_PII_FIELDS = {"name", "father_name", "mobile", "aadhaar_last4", "address", "dob"}

_PROMPT = (
    "You are an expert on Indian central and Maharashtra state government welfare schemes. "
    "Given this citizen profile: {profile}. The citizen already qualifies for: {known}. "
    "List ONLY ADDITIONAL schemes they may qualify for. Respond with a JSON array only, "
    'each item: {{"scheme_name": "...", "eligibility_reason": "...", '
    '"how_to_apply": "...", "estimated_benefit": "..."}}. '
    "If there are none, respond with []."
)


async def enrich(
    profile: CitizenProfile,
    rule_results: List[SchemeResult],
    language: str = "hi",
) -> List[SchemeResult]:
    """Merge LLM-suggested schemes (flagged for manual verification) into results."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return rule_results

    profile_data = profile.model_dump(exclude=_PII_FIELDS)
    known = [r.scheme_name for r in rule_results]
    payload = {
        "model": os.getenv("OPENROUTER_MODEL", "openrouter/free"),
        "messages": [
            {"role": "user", "content": _PROMPT.format(profile=json.dumps(profile_data), known=json.dumps(known))}
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(ENDPOINT, headers={"Authorization": f"Bearer {api_key}"}, json=payload)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            start, end = content.find("["), content.rfind("]")
            extra = json.loads(content[start : end + 1]) if start != -1 and end != -1 and start < end else []
    except Exception:
        return rule_results  # LLM is best-effort only

    seen = {r.scheme_name.strip().lower() for r in rule_results}
    merged = list(rule_results)
    for item in extra if isinstance(extra, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("scheme_name", "")).strip()
        if not name or name.lower() in seen:
            continue
        merged.append(
            SchemeResult(
                scheme_name=name,
                eligibility_reason=str(item.get("eligibility_reason", "")),
                how_to_apply=str(item.get("how_to_apply", "")),
                estimated_benefit=str(item.get("estimated_benefit", "")),
                verify_manually=True,
            )
        )
    return merged
