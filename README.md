PS3: Digital Citizen Assistant for multilingual access to government services and schemes.

# Saarthi

Saarthi is a digital citizen assistant for government services and welfare
schemes. It helps a citizen enter or upload their details, ask for assistance
in plain language, understand certificate requirements, and discover scheme
matches with clear reasons and application steps.

## Dashboard

The citizen dashboard is served at http://127.0.0.1:8000 after the server
starts. It provides:

- A profile form for eligibility details such as state, income, occupation,
  category, land, household, and education details.
- A document queue that accepts image uploads and can extract profile fields
  through the configured AI Vision provider.
- A plain-language assistant for questions such as:
  - Which schemes can I apply for?
  - I need an income certificate.
  - Can I apply for PM-KISAN?
- Conversational follow-up questions for intent-specific requests. For example,
  when a citizen asks for a scholarship, Saarthi asks for missing age, student
  status, income, category, or state details, saves clear answers to the
  session profile, and refreshes the scholarship matches.
- Explainable scheme cards with eligibility reason, benefit, and application
  route.
- Certificate service checklists with documents, fee, processing time, and
  validity.
- Voice input and spoken assistant replies in supported browsers. The citizen
  presses **Finish speaking** before a voice request is sent.
- An end-session control that removes tracked session data.

## How it works

1. A citizen enters their data or uploads document images.
2. The dashboard saves the profile in a temporary in-memory session.
3. The rule engine calculates every verified scheme match.
4. OpenRouter enrichment may add extra candidates, but each is labelled for
   manual verification and never overrides rule-based results.
5. The assistant returns guidance based on the citizen request, profile
   completeness, service catalog, and scheme matches. If a request needs more
   information, it asks for missing profile fields in chat and saves
   unambiguous follow-up answers to the same in-memory session.
6. Once a request has the details needed for a useful match, live guidance can
   search recognised official government domains using broad eligibility facts
   (never name, phone, Aadhaar, or address), then show the official source.

Browser portal form scanning, autofill, and document-upload automation have
been moved into the integrated Guided Services page. Open
http://127.0.0.1:8000/guided-services to use the standalone guided flow and
its browser/document automation with the dashboard's current session.

The dashboard's former application automation endpoints remain retired. The
standalone automation is available only from the Guided Services page under
the `/guided-services` API namespace.

1. Ask for a named service (for example, “I need a residence certificate”) or
The current catalog connects Income, Residence, and Caste Certificates for
Goa Online. To add another service, add it to `app/data/services.yaml` with:


## Quick start

After setup, run the project with:

Windows PowerShell:

    .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Windows PowerShell:

    python3 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt
    Copy-Item .env.example .env
    python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Linux or macOS:

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements.txt
    cp .env.example .env
    python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Open http://127.0.0.1:8000 for the dashboard,
http://127.0.0.1:8000/guided-services for the integrated standalone guided
flow, and http://127.0.0.1:8000/docs for interactive API documentation. Both
pages can use the same in-memory session when opened in the same browser.

## Configuration

- OPENROUTER_API_KEY enables AI Vision document extraction, optional scheme
  enrichment, and browser-agent features. Never commit a real key.
- OPENROUTER_MODEL selects the OpenRouter model.
- JANSEVA_EXTRACTION_MODE controls document extraction: `ai` for normal
  OpenRouter extraction, `mock` for synthetic local-test data, or `fallback` to
  try AI and use synthetic data when OpenRouter is unavailable.
- JANSEVA_FORM_FILLER_MODE controls Selenium form data: `session` for normal
  operation or `dummy` to use the local test profile in `form_filler.py`.
- JANSEVA_BROWSER_PROFILE_DIR optionally selects the Edge profile directory used
  by the Guided Services Selenium form-filler and uploader.
- SERPER_API_KEY optionally enables live official-web guidance. It is never
  required for the Income Certificate flow's built-in Goa Online link.
- JANSEVA_OUTPUT_DIR sets the generated document directory.
- `app/data/sample_profile.yaml` contains the starter profile loaded into every
  new local demo session, so development restarts do not require repeated
  onboarding entry. Replace its clearly marked demo values before real use.

The rule-based eligibility flow works without an OpenRouter key. Document
image extraction currently requires it because the active scanner uses the AI
Vision implementation.

## Main API endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | /health | Health check |
| GET | /services | List certificate services |
| POST | /sessions | Create a private in-memory session |
| POST | /sessions/{id}/profile | Save citizen details and calculate matches |
| POST | /sessions/{id}/assistant | Ask for scheme or certificate guidance |
| POST | /sessions/{id}/scan | Extract data from uploaded document images |
| POST | /sessions/{id}/service | Retrieve a service checklist |
| DELETE | /sessions/{id} | End the session and wipe tracked artifacts |

The integrated Guided Services API uses the same operations under the
`/guided-services` prefix, including `/guided-services/sessions/{id}/launch_browser`,
`/guided-services/sessions/{id}/automate_fill`, and
`/guided-services/sessions/{id}/automate_upload`.

## Current scope and safety

- The current service catalog contains Income, Residence, and Caste
  certificates.
- The eligibility engine includes central schemes and Maharashtra-specific
  rules. State-specific catalogs and rule sets can be added incrementally.
- Final government applications, OTPs, CAPTCHAs, and eligibility decisions
  must be completed and verified by a human authority on the official portal.
- The development server has permissive CORS and should not be exposed to the
  public internet without deployment hardening.
- Scans are stored only in the current session's local `scans/` folder; review
  retention and access controls before production.

## Tests

    python -m pip install -r requirements-dev.txt
    pytest
