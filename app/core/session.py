"""Six-state kiosk session state machine with zero-PII audit logging.

GREET -> IDENTIFY -> CHECKLIST -> SCAN -> FILL -> DELIVER

Sessions live in memory only. wipe() deletes every artifact (scans, PDFs)
and logs nothing but timestamp + service_id + status.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from app.core.profile import CitizenProfile, sample_profile

log = logging.getLogger("saarthi.audit")


class State(str, Enum):
    GREET = "GREET"
    IDENTIFY = "IDENTIFY"
    CHECKLIST = "CHECKLIST"
    SCAN = "SCAN"
    FILL = "FILL"
    DELIVER = "DELIVER"


_ORDER = [State.GREET, State.IDENTIFY, State.CHECKLIST, State.SCAN, State.FILL, State.DELIVER]


class Session:
    def __init__(self) -> None:
        self.id = uuid.uuid4().hex
        self.state: State = State.GREET
        self.language = "en"
        self.service_id: Optional[str] = None
        self.profile = sample_profile()
        self.eligibility: list = []
        self.artifacts: List[str] = []  # file paths of generated PDFs
        self.scans: Dict[str, str] = {} # maps document category to absolute file path
        self.document_extractions: List[Dict[str, Any]] = []  # reviewed extra fields, kept only for this session
        # Service-specific answers that do not belong in the reusable citizen
        # profile. This makes new portal forms configurable without adding a
        # model field for every government scheme.
        self.application_details: Dict[str, Dict[str, Any]] = {}
        self.discovered_forms: Dict[str, Dict[str, Any]] = {}
        # One live-guidance application may be prepared alongside catalogued
        # services. It contains only the official URL/title for this session.
        self.live_application: Dict[str, Any] = {}
        self.chat_history: List[Dict[str, str]] = [] # conversational fallback history for extraction
        # The assistant keeps only the current intent and the profile fields
        # it still needs to answer that intent. Values are merged into the
        # normal profile only after the citizen sends a follow-up answer.
        self.assistant_context: Dict[str, Any] = {}
        self.created_at = time.time()
        self.last_active = time.time()
        self.completed = False

    def advance(self) -> State:
        """Move to the next state; stays at DELIVER once reached."""
        idx = _ORDER.index(self.state)
        if idx < len(_ORDER) - 1:
            self.state = _ORDER[idx + 1]
        return self.state

    def restart_service(self) -> None:
        """Citizen has another task: go back to IDENTIFY, keep language."""
        self.state = State.IDENTIFY
        self.service_id = None
        self.completed = False


class SessionStore:
    """In-memory only. Nothing is ever persisted to disk or a database."""

    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}

    def cleanup(self, max_age: int = 1800) -> None:
        """Retained as an explicit maintenance hook; sessions are not timed out automatically."""
        now = time.time()
        to_wipe = [sid for sid, s in self._sessions.items() if now - getattr(s, "last_active", s.created_at) > max_age]
        for sid in to_wipe:
            self.wipe(sid, status="timeout")

    def create(self, *, sample: bool = True) -> Session:
        s = Session()
        if not sample:
            s.profile = CitizenProfile()
        self._sessions[s.id] = s
        return s

    def get(self, sid: str) -> Optional[Session]:
        s = self._sessions.get(sid)
        if s:
            s.last_active = time.time()
        return s

    def wipe(self, sid: str, status: str = "abandoned") -> None:
        """Delete the session, all citizen data and every generated file.

        Audit log is zero-PII: timestamp + service_id + status only.
        """
        s = self._sessions.pop(sid, None)
        if s is None:
            return
        for path in s.artifacts:
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
                
        # --- NEW: Physically shred the citizen's local scans folder ---
        try:
            import shutil
            from pathlib import Path
            scan_dir = Path.cwd() / "scans" / sid
            if scan_dir.exists() and scan_dir.is_dir():
                shutil.rmtree(scan_dir)
        except OSError:
            pass
        # ---------------------------------------------------------------
        
        log.info(
            "session_end ts=%s service=%s status=%s",
            int(time.time()),
            s.service_id or "-",
            "completed" if s.completed else status,
        )
