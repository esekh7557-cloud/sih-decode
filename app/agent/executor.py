"""Retired unrestricted browser-execution path.

The former computer-use agent accepted arbitrary multipart data and could
upload documents or submit an application. Saarthi now uses the reviewed CDP
filler instead, which deliberately stops before any portal action.
"""
from __future__ import annotations

from typing import Any


async def execute_form_fill(url: str, data: dict[str, Any]) -> str:
    """Refuse the retired executor without opening a browser.

    Keeping this function prevents stale imports from silently regaining the
    unsafe behaviour while providing a clear migration error to callers.
    """
    del url, data
    raise RuntimeError(
        "The legacy form executor is disabled: it cannot upload files or "
        "click Save, Continue, Proceed, or Submit. Use the reviewed portal "
        "form-filling flow instead."
    )
