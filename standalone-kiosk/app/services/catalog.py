"""Service catalog backed by data/services.yaml."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

_DATA = Path(__file__).resolve().parent.parent / "data" / "services.yaml"


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(_DATA, encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_services(state: Optional[str] = None) -> dict:
    services = _load()
    if state:
        # If the service explicitly defines states, it must match.
        # If it doesn't define states, it's a generic service available everywhere.
        return {
            sid: {"name": s["name"], "category": s.get("category", "other")}
            for sid, s in services.items()
            if not s.get("states") or state in s.get("states", [])
        }
    return {
        sid: {"name": s["name"], "category": s.get("category", "other")}
        for sid, s in services.items()
    }


def get_service(service_id: str) -> Optional[dict]:
    return _load().get(service_id)


def build_checklist(service_id: str, occupation: Optional[str] = None) -> Optional[dict]:
    """Numbered checklist with fee/processing/validity.

    Resolves occupation-dependent requirements (e.g. income proof) when the
    citizen's occupation is known.
    """
    service = get_service(service_id)
    if not service:
        return None
    items = []
    for i, doc in enumerate(service.get("documents", []), start=1):
        entry: dict = {"number": i, "name": doc["name"]}
        variants = doc.get("variants_by_occupation")
        if variants and occupation:
            entry["detail"] = variants.get(occupation, "Self-declaration")
        elif variants:
            entry["detail"] = "; ".join(f"{k}: {v}" for k, v in variants.items())
        if doc.get("alternatives"):
            entry["alternatives"] = doc["alternatives"]
        if doc.get("note"):
            entry["note"] = doc["note"]
        items.append(entry)
    return {
        "service": service["name"],
        "fee": service.get("fee"),
        "processing": service.get("processing"),
        "validity": service.get("validity"),
        "items": items,
    }
