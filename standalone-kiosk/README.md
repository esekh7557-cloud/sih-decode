# JanSeva AI - Digital Citizen Assistant Kiosk

Free public-kiosk assistant for Mamlatdar/Tehsildar offices in India. Helps
citizens obtain certificates and discover government schemes they are entitled
to - replacing paid middlemen who charge Rs 200-2000 for Rs 15 government work.

## Features

- **Six-state guided session**: GREET -> IDENTIFY -> CHECKLIST -> SCAN -> FILL -> DELIVER
- **Multilingual**: Hindi (default), Marathi, Gujarati, English
- **Document Requirements Database**: income, domicile, caste, non-creamy layer,
  EWS, 7/12 extract, birth/death, ration card - with alternatives, fees,
  processing times and validity
- **Hybrid Scheme Eligibility Engine** (core feature):
  - Deterministic **rule engine** is the source of truth - fully unit-tested,
    works offline, never hallucinates eligibility
  - Optional **LLM enrichment** via OpenRouter adds extra candidates, always
    flagged "verify manually"; it can never override the rules
- **OCR scanning** (Tesseract hin/mar/guj/eng) with Verhoeff Aadhaar validation
  and a demo-mode mock scanner
- **Print-ready PDFs** (WeasyPrint, HTML fallback), schemes sheet included
- **Printing** via CUPS (2 copies) with QR-code download fallback
- **Portal automation** (Playwright) with human-in-the-loop OTP/CAPTCHA and
  automatic offline fallback when a portal is down
- **Privacy by design**: in-memory sessions, Aadhaar masked to last 4 digits,
  full data wipe on session end, zero-PII audit log

## Quickstart (demo mode)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # optionally set OPENROUTER_API_KEY
uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for the interactive API. Demo mode
(`JANSEVA_DEMO_MODE=1`, default) mocks the camera and lets the whole flow run
end-to-end without kiosk hardware.

For local extraction UI testing without OpenRouter, set
`JANSEVA_EXTRACTION_MODE=mock` before starting the server. This returns clearly
synthetic demo fields for every uploaded image. Use `fallback` instead of
`mock` to try AI first and use the synthetic fields only when AI is unavailable.

To make the Selenium form filler use the dummy profile from
`app/docgen/form_filler.py`, also set `JANSEVA_FORM_FILLER_MODE=dummy`. This
overrides the current session profile only for the form-filler test.

Windows PowerShell:

```powershell
$env:JANSEVA_EXTRACTION_MODE = "mock"
$env:JANSEVA_FORM_FILLER_MODE = "dummy"
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8011
```

## Production extras

- OCR: `apt install tesseract-ocr tesseract-ocr-hin tesseract-ocr-mar tesseract-ocr-guj`
  and `pip install pytesseract Pillow`
- PDF: `pip install weasyprint`
- Portals: `pip install playwright && playwright install chromium`
  (verify Aaple Sarkar selectors against the live portal first)
- Set `JANSEVA_DEMO_MODE=0`

## Security

- `OPENROUTER_API_KEY` is read from the environment only. **Never commit keys.**
  If a key is ever exposed, revoke it immediately.
- Aadhaar numbers are validated (Verhoeff checksum) and only the last 4 digits
  are ever stored or displayed (`XXXX XXXX 1234`).
- No PII is sent to the LLM: name, mobile, Aadhaar, DOB and address are
  stripped before the eligibility enrichment call.
- `DELETE /sessions/{id}` wipes all scans, generated PDFs and profile data.
- The audit log contains only timestamp + service_id + completed/abandoned.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
