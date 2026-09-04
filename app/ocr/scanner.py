"""Document scanning + OCR.

TesseractScanner needs a camera + tesseract language packs (hin/mar/guj/eng).
MockScanner lets the whole kiosk run end-to-end in demo mode
(JANSEVA_DEMO_MODE=1, the default).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

CONFIDENCE_THRESHOLD = 0.7
MAX_RETRIES = 3


@dataclass
class ScanResult:
    document_type: str
    raw_text: str
    fields: dict = field(default_factory=dict)
    confidence: float = 0.0
    image_path: str = ""


class BaseScanner:
    async def scan(self, expected_type: str | None = None, images: list[str] = None, chat_history: list[dict] = None) -> ScanResult:
        raise NotImplementedError


class MockScanner(BaseScanner):
    """Deterministic scanner for demo mode and tests."""

    async def scan(self, expected_type: str | None = None, images: list[str] = None, chat_history: list[dict] = None) -> ScanResult:
        return ScanResult(
            document_type=expected_type or "aadhaar",
            raw_text="DEMO DOCUMENT",
            fields={
                "name": "Demo Citizen", 
                "dob": "01/01/1990", 
                "gender": "female",
                "annual_income": 150000,
                "occupation": "farmer"
            },
            confidence=0.95,
        )


def _dummy_scan(expected_type: str | None = None) -> ScanResult:
    """Return safe, clearly synthetic data for explicit local fallback mode."""
    return ScanResult(
        document_type=expected_type or "aadhaar",
        raw_text="DEMO DOCUMENT",
        fields={
            "name": "Demo Citizen",
            "dob": "01/01/1990",
            "gender": "female",
            "annual_income": 150000,
            "occupation": "farmer",
        },
        confidence=0.95,
    )


class TesseractScanner(BaseScanner):
    """Real OCR via pytesseract. Requires camera capture to be wired in."""

    LANGS = "hin+mar+guj+eng"

    async def scan(self, expected_type: str | None = None, images: list[str] = None, chat_history: list[dict] = None) -> ScanResult:
        import pytesseract  # optional dependency, production only
        from PIL import Image
        import base64
        import io

        if not images:
            return ScanResult(document_type="error", raw_text="No image provided")

        b64_data = images[0].split(",")[1] if "," in images[0] else images[0]
        img = Image.open(io.BytesIO(base64.b64decode(b64_data)))
        
        data = pytesseract.image_to_data(
            img, lang=self.LANGS, output_type=pytesseract.Output.DICT
        )
        words = [w for w, c in zip(data["text"], data["conf"]) if w.strip() and float(c) >= 0]
        confs = [float(c) for w, c in zip(data["text"], data["conf"]) if w.strip() and float(c) >= 0]
        confidence = (sum(confs) / len(confs) / 100) if confs else 0.0
        raw = " ".join(words)
        return ScanResult(
            document_type=expected_type or "unknown",
            raw_text=raw,
            fields=self._extract_fields(raw),
            confidence=confidence,
        )

    @staticmethod
    def _extract_fields(text: str) -> dict:
        fields: dict = {}
        m = re.search(r"\b(\d{4}\s?\d{4}\s?\d{4})\b", text)
        if m:
            fields["aadhaar_number"] = m.group(1)
        m = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", text)
        if m:
            fields["dob"] = m.group(1)
        return fields


class AIVisionScanner(BaseScanner):
    """Uses OpenRouter Vision LLM to extract fields from document images."""

    async def scan(self, expected_type: str | None = None, images: list[str] = None, chat_history: list[dict] = None) -> ScanResult:
        from app.ocr.ai_extractor import extract_data_from_images

        if not images and not chat_history:
            return ScanResult(document_type=expected_type or "unknown", raw_text="")

        try:
            result = await extract_data_from_images(images, chat_history=chat_history)
        except Exception:
            if os.getenv("JANSEVA_EXTRACTION_MODE", "ai").strip().lower() == "fallback":
                return _dummy_scan(expected_type)
            raise
        if result.get("success") and result.get("extracted_fields"):
            fields = result["extracted_fields"]
            return ScanResult(
                document_type=fields.get("document_type") or expected_type or "mixed",
                raw_text=result.get("raw_output", ""),
                fields=fields,
                confidence=0.95
            )

        if os.getenv("JANSEVA_EXTRACTION_MODE", "ai").strip().lower() == "fallback":
            return _dummy_scan(expected_type)

        print(f"[OCR Scanner] AI Vision extraction failed: {result.get('error')}")
        return ScanResult(
            document_type=expected_type or "unknown",
            raw_text=result.get("error", "AI extraction failed"),
            fields={},
            confidence=0.0
        )

def get_scanner() -> BaseScanner:
    mode = os.getenv("JANSEVA_EXTRACTION_MODE", "ai").strip().lower()
    if mode in {"mock", "dummy"}:
        return MockScanner()
    return AIVisionScanner()
