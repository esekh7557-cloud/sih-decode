# JanSeva AI

JanSeva AI is a multilingual public-service kiosk for Mamlatdar and Tehsildar
offices in India. It helps citizens understand certificate requirements,
extract information from documents, discover potentially eligible government
schemes, generate an application, and print or download the result.

The project is designed to reduce dependence on paid middlemen while keeping
the rule-based eligibility result explainable and usable offline.

## Current capabilities

- Six-state citizen workflow: `GREET -> IDENTIFY -> CHECKLIST -> SCAN -> FILL -> DELIVER`
- Hindi, Marathi, Gujarati, and English UI support
- YAML-backed document checklists with fees, processing times, validity, and alternatives
- Current catalog services: Income Certificate, Residence Certificate, and Caste Certificate
- Aadhaar validation using the Verhoeff checksum and masking to the last four digits
- AI Vision document extraction through OpenRouter
- Deterministic scheme eligibility rules, with optional LLM enrichment clearly marked for manual verification
- Citizen dashboard for profile entry, document upload, certificate checklists, and plain-language scheme questions
- Profile-aware assistant endpoint that returns explainable scheme matches, missing details, and service guidance
- Application and scheme-sheet generation as PDF when WeasyPrint is available, or printable HTML otherwise
- CUPS printing with QR-code download fallback when no printer is available
- Optional Selenium/Playwright/browser-use helpers for government portal workflows
- In-memory sessions with automatic expiry and an explicit data-wipe endpoint

## Requirements

- Python 3.10 or newer
- A modern browser for the kiosk UI
- An OpenRouter API key for AI Vision extraction, LLM scheme enrichment, and the AI form assistant
- Optional production integrations:
  - WeasyPrint for PDF output
  - Tesseract and language packs for the standalone OCR implementation
  - Chrome/Chromium or Microsoft Edge for browser automation
  - A CUPS-compatible printer for direct printing

## Quick start

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open the kiosk at [http://127.0.0.1:8000](http://127.0.0.1:8000). Interactive
API documentation is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs),
and the health check is at `/health`.

The server serves the frontend directly from `frontend/`; no separate frontend
build step is required.

## Configuration

Copy `.env.example` to `.env` and set values for the deployment:

| Variable | Purpose |
| --- | --- |
| `OPENROUTER_API_KEY` | Enables OpenRouter-backed document extraction, enrichment, and form-agent features. Keep it out of source control. |
| `OPENROUTER_MODEL` | OpenRouter model used by the AI integrations. |
| `JANSEVA_DEMO_MODE` | Demo-mode flag retained in the configuration template. See the scanner note below. |
| `JANSEVA_OUTPUT_DIR` | Directory for generated PDFs/HTML and QR images; defaults to `output`. |
| `JANSEVA_BASE_URL` | Base URL embedded in printer-fallback QR codes. Set this to the kiosk's reachable address and port. |
| `KIOSK_LOCATION` | Display/deployment location metadata. |
| `KIOSK_TALUKA`, `KIOSK_DISTRICT`, `KIOSK_STATE` | Kiosk location defaults; the profile state defaults to Maharashtra. |

### Scanner and demo-mode note

The codebase includes `MockScanner` and `TesseractScanner`, but the current
`get_scanner()` implementation returns `AIVisionScanner`. Therefore, uploaded
document extraction currently requires `OPENROUTER_API_KEY`; setting
`JANSEVA_DEMO_MODE=1` alone does not switch the active scanner to the mock
scanner.

## Optional production extras

PDF generation:

```bash
python -m pip install weasyprint
```

OCR support on Debian/Ubuntu:

```bash
sudo apt install tesseract-ocr tesseract-ocr-hin tesseract-ocr-mar tesseract-ocr-guj
python -m pip install pytesseract Pillow
```

Playwright browser binaries:

```bash
python -m playwright install chromium
```

Set `JANSEVA_DEMO_MODE=0` only after the required hardware and integrations
have been configured and tested locally.

## Typical kiosk flow

1. Choose a language and state.
2. Choose a service.
3. Review the document checklist, fee, processing time, and validity.
4. Upload or scan documents and review extracted fields.
5. Enter or correct profile details and run scheme eligibility checks.
6. Confirm the information to generate the application and schemes sheet.
7. Collect printed documents or scan the QR code to download them.

The frontend also includes an AI Form Assistant that can analyze an online
form, collect the required fields and documents, and invoke a browser agent to
fill it. Government portal automation may still require a citizen or operator
to complete login, OTP, CAPTCHA, and other human-verification steps.

## API overview

The complete schema is available in `/docs`. The main endpoints are:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service health check |
| `GET` | `/services` | List catalog services; optionally filter with `?state=` |
| `POST` | `/sessions` | Create an in-memory kiosk session |
| `POST` | `/sessions/{id}/language` | Set the session language |
| `POST` | `/sessions/{id}/state` | Set the citizen's state |
| `POST` | `/sessions/{id}/service` | Select a certificate service and receive its checklist |
| `POST` | `/sessions/{id}/scan` | Process uploaded document images |
| `POST` | `/sessions/{id}/scan_chat` | Continue an extraction conversation |
| `POST` | `/sessions/{id}/profile` | Save profile data and run eligibility checks |
| `POST` | `/sessions/{id}/assistant` | Ask for scheme or certificate help using the saved citizen profile |
| `POST` | `/sessions/{id}/confirm` | Generate and print/download documents |
| `DELETE` | `/sessions/{id}` | Wipe the session and its tracked artifacts |
| `POST` | `/api/extract` | Standalone AI document extraction |
| `POST` | `/api/analyze-form` | Analyze an online form into a field schema |
| `POST` | `/api/execute-form` | Fill an online form using multipart form data |

## Testing

```bash
python -m pip install -r requirements-dev.txt
pytest
```

The test suite covers the eligibility rules, session state machine, Aadhaar
and PAN validation, mobile validation, and artifact cleanup.

## Project layout

```text
app/
  agent/        AI/browser form analysis and execution
  core/         citizen profile and session lifecycle
  data/         service catalog (`services.yaml`)
  docgen/       application generation and portal upload helpers
  eligibility/  deterministic rules and optional LLM enrichment
  i18n/         localized kiosk phrases
  ocr/          AI Vision and Tesseract scanner implementations
  portals/      portal integration abstractions
  printing/     CUPS printing and QR fallback
frontend/       static kiosk UI
tests/          automated tests
scans/          local uploaded sample/session scans
```

## Privacy and deployment safety

- Session state is held in memory and inactive sessions are cleaned up after 30 minutes.
- Aadhaar values are validated and stored/displayed only as `XXXX XXXX ####`.
- The eligibility enrichment request is intended to exclude direct personal identifiers.
- `DELETE /sessions/{id}` removes the tracked session artifacts and the session scan directory.
- Do not expose this development server directly to the public internet: CORS is permissive, generated files are served locally, and portal automation is environment-specific.
- The current `/scan` implementation also copies uploaded images to a machine-specific `C:\Users\Vedant\Desktop\data` path. Review or remove that behavior before production deployment; the session wipe does not remove that external copy.
- Never commit `.env`, API keys, citizen documents, generated output, or real kiosk data.

## Portal automation limitations

The Goa Online/Selenium helper currently assumes a Windows Edge setup with
remote debugging on port `9222` and contains machine-specific paths. Update
those paths and verify the target portal's selectors before enabling it on a
different kiosk. OTPs, CAPTCHAs, and final submissions should remain under
human control.
#   s i h - d e c o d e  
 #   s i h - d e c o d e  
 
