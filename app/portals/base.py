"""Playwright portal playbooks with human-in-the-loop OTP/CAPTCHA.

If a portal is unreachable (or Playwright is not installed), PortalDown is
raised and the kiosk automatically falls back to offline PDF generation.
"""
from __future__ import annotations

from typing import Callable


class PortalDown(Exception):
    """Raised when a portal is unusable - caller must switch to offline path."""


class BasePortal:
    url: str = ""

    def __init__(self, ask_human: Callable[[str], str], notify: Callable[[str], None] = print):
        # ask_human(prompt) returns a citizen-provided value (OTP / CAPTCHA / yes-no).
        # OTPs are used once and never stored.
        self.ask_human = ask_human
        self.notify = notify
        self._page = None
        self._pw = None

    def _start(self) -> None:
        try:
            from playwright.sync_api import sync_playwright  # optional dependency
        except ImportError as exc:
            raise PortalDown("Playwright not installed - using offline path") from exc
        self._pw = sync_playwright().start()
        browser = self._pw.chromium.launch(headless=False)
        self._page = browser.new_page()
        try:
            self._page.goto(self.url, timeout=30_000)
        except Exception as exc:
            raise PortalDown(f"{self.url} unreachable") from exc

    def screenshot(self, name: str) -> str:
        path = f"output/{name}.png"
        self._page.screenshot(path=path)
        return path

    def close(self) -> None:
        if self._pw:
            self._pw.stop()
