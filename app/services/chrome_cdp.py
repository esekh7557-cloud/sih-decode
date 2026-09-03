"""Small, local-only Chrome DevTools Protocol helpers.

Saarthi opens Chrome with a localhost debugging port.  Using CDP directly
avoids a separate ChromeDriver download and lets the scanner inspect the form
that the citizen has already opened and logged into.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


class ChromeDebugError(RuntimeError):
    """The local Saarthi Chrome debugging session cannot be used."""


def _targets(port: int) -> list[dict[str, Any]]:
    try:
        with urlopen(f"http://127.0.0.1:{port}/json", timeout=3) as response:
            data = json.load(response)
    except (OSError, URLError, ValueError) as exc:
        raise ChromeDebugError("Could not connect to the Saarthi browser.") from exc
    if not isinstance(data, list):
        raise ChromeDebugError("The Saarthi browser did not return a tab list.")
    return [
        item for item in data
        if isinstance(item, dict)
        and item.get("type") == "page"
        and str(item.get("url") or "").startswith(("http://", "https://"))
        and item.get("webSocketDebuggerUrl")
    ]


def _evaluate(target: dict[str, Any], expression: str) -> Any:
    try:
        import websocket
    except ImportError as exc:
        raise ChromeDebugError("Chrome DevTools support is not installed.") from exc

    try:
        socket = websocket.create_connection(
            str(target["webSocketDebuggerUrl"]),
            timeout=5,
            # Chrome may reject arbitrary web origins for a local debugging
            # port. CDP clients are not web pages, so omit Origin entirely.
            suppress_origin=True,
        )
        try:
            socket.send(json.dumps({
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": expression,
                    "returnByValue": True,
                    "awaitPromise": True,
                },
            }))
            while True:
                reply = json.loads(socket.recv())
                if reply.get("id") != 1:
                    continue
                if reply.get("error"):
                    raise ChromeDebugError(str(reply["error"].get("message") or "Chrome could not evaluate the form."))
                result = reply.get("result", {}).get("result", {})
                if result.get("subtype") == "error":
                    raise ChromeDebugError(str(result.get("description") or "Chrome could not evaluate the form."))
                return result.get("value")
        finally:
            socket.close()
    except ChromeDebugError:
        raise
    except Exception as exc:
        if "403" in str(exc) or "origin" in str(exc).lower():
            raise ChromeDebugError(
                "The Saarthi browser needs to be reopened before its form can be scanned."
            ) from exc
        raise ChromeDebugError("Could not communicate with the Saarthi browser.") from exc


def evaluate_open_form(expression: str, port: int = 9222) -> Any:
    """Evaluate JavaScript on the open tab containing the most form controls."""
    candidates = _targets(port)
    if not candidates:
        raise ChromeDebugError("No official application page is open in the Saarthi browser.")

    best_target = candidates[0]
    best_count = -1
    for target in candidates:
        count = _evaluate(target, "document.querySelectorAll('input, select, textarea').length")
        try:
            numeric_count = int(count)
        except (TypeError, ValueError):
            numeric_count = 0
        if numeric_count > best_count:
            best_target, best_count = target, numeric_count
    return _evaluate(best_target, expression)
