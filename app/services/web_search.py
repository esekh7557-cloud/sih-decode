"""Official-source live guidance for government services and schemes.

Searches are deliberately limited to recognised government domains. Search
queries may include broad eligibility facts, but never identity or contact
details such as a name, phone number, Aadhaar, or address.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlparse

import httpx

SEARCH_ENDPOINT = "https://google.serper.dev/search"
MAX_SOURCES = 4
_OFFICIAL_HOSTS = {"myscheme.gov.in", "umang.gov.in", "goaonline.gov.in"}
_LIVE_SEARCH_TERMS = (
    "apply",
    "application",
    "how to",
    "steps",
    "website",
    "portal",
    "register",
    "registration",
    "deadline",
    "document",
    "certificate",
    "scheme",
    "yojana",
)


def wants_live_search(message: str) -> bool:
    return any(term in message.lower() for term in _LIVE_SEARCH_TERMS)


def _is_official_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in _OFFICIAL_HOSTS or host == "gov.in" or host.endswith(".gov.in")


def _safe_query(message: str, state: str, profile: dict | None = None) -> str:
    """Remove obvious identifier patterns before sending a query externally."""
    sanitized = re.sub(r"\b\d{10,16}\b", "[redacted]", message)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    location = f"{state.strip()} " if state and state.strip().lower() != "other" else ""
    profile_terms = []
    profile = profile or {}
    if profile.get("age") not in (None, ""):
        profile_terms.append(f"age {profile['age']}")
    for key in ("gender", "occupation", "caste_category"):
        value = str(profile.get(key) or "").strip()
        if value and value.lower() not in {"other", "unknown"}:
            profile_terms.append(value.replace("_", " "))
    income = profile.get("annual_income")
    if income not in (None, ""):
        try:
            amount = float(income)
            profile_terms.append(
                "low income" if amount <= 250000 else
                "middle income" if amount <= 800000 else "higher income"
            )
        except (TypeError, ValueError):
            pass
    return " ".join([location, *profile_terms, sanitized, "official government application"]).strip()


async def get_live_guidance(message: str, state: str = "", profile: dict | None = None) -> dict:
    """Search official portals and turn verified results into safe next steps."""
    api_key = os.getenv("SERPER_API_KEY", "").strip()
    if not api_key:
        return {
            "searched": False,
            "configured": False,
            "notice": "Live web guidance is not configured. Add SERPER_API_KEY to the local .env file.",
            "steps": [],
            "sources": [],
        }

    payload = {
        "q": _safe_query(message, state, profile),
        "gl": "in",
        "hl": "en",
        "num": 10,
    }
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(
                SEARCH_ENDPOINT,
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            organic = response.json().get("organic", [])
    except Exception:
        return {
            "searched": True,
            "configured": True,
            "notice": "I could not reach the official web search service. Please try again shortly.",
            "steps": [],
            "sources": [],
        }

    sources = []
    seen_urls = set()
    for item in organic if isinstance(organic, list) else []:
        url = str(item.get("link", "")).strip()
        if not url or url in seen_urls or not _is_official_url(url):
            continue
        seen_urls.add(url)
        sources.append(
            {
                "title": str(item.get("title", "Official government portal")).strip(),
                "url": url,
                "snippet": str(item.get("snippet", "")).strip(),
            }
        )
        if len(sources) >= MAX_SOURCES:
            break

    if not sources:
        return {
            "searched": True,
            "configured": True,
            "notice": "No official portal result was found for this request. Please try naming the scheme or certificate.",
            "steps": [],
            "sources": [],
        }

    primary = sources[0]
    steps = [
        f"Open the official {primary['title']} website below.",
        "Read the latest eligibility and document requirements on the portal.",
        "Create an account or sign in, then choose the relevant scheme or service.",
        "Complete the application and keep the acknowledgement number for tracking.",
    ]
    return {
        "searched": True,
        "configured": True,
        "notice": "Live guidance was found on official government portals. Confirm requirements before submitting.",
        "steps": steps,
        "sources": sources,
    }
