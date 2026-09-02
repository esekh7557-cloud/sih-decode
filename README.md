PS3: Digital Citizen Assistant for multilingual access to government services and schemes.


# JanSeva AI

JanSeva AI is a digital citizen assistant for government services and welfare
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
  when a citizen asks for a scholarship, JanSeva asks for missing age, student
  status, income, category, or state details, saves clear answers to the
  session profile, and refreshes the scholarship matches.
- Explainable scheme cards with eligibility reason, benefit, and application
  route.
- Certificate service checklists with documents, fee, processing time, and
  validity.
- A configuration-driven **Apply with Saarthi** journey: collect missing
  application fields, open the official portal for citizen login, review the
  exact values to fill, then upload scanned documents after the citizen
  reviews the portal form.
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

### Applying with Saarthi

For a supported service:

1. Ask for a named service (for example, “I need a residence certificate”) or
   select it in Services.
2. Review the listed documents, upload and label available scans, then select
   **Apply with Saarthi**.
3. Enter any missing portal fields. Saarthi does not invent answers.
4. Open the official portal, log in, complete any OTP/CAPTCHA, and open the
   correct application page yourself.
5. Select **Scan opened form**. Saarthi reads the visible field labels,
   required markers, dropdown choices, and upload-row labels from the local
   browser, then adds newly discovered questions and documents to the plan.
   It does not read passwords, OTPs, CAPTCHAs, or entered form values.
6. Review the masked application summary and explicitly ask Saarthi to fill
   the opened form when that service has a verified mapping. It stops before
   **Save & Proceed**.
7. After reviewing the official form, start document upload. Verify the files
   and submit the final application yourself on the government portal.

The current catalog connects Income, Residence, and Caste Certificates for
Goa Online. To add another service, add it to `app/data/services.yaml` with:

- its `documents`, fee, processing time, and `portal` or `portal_url`;
- optional `application_fields` for the answers Saarthi should collect; and
- an `automation_mapping` whose verified mapping file is in
  `app/docgen/mappings/` if portal form filling is safe to enable.

Without a verified mapping, Saarthi still prepares the checklist, saves
service-specific answers for the session, and opens the official site, but
leaves form entry manual.

## Quick start

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

Open http://127.0.0.1:8000 for the dashboard and
http://127.0.0.1:8000/docs for interactive API documentation.

## Configuration

- OPENROUTER_API_KEY enables AI Vision document extraction, optional scheme
  enrichment, and browser-agent features. Never commit a real key.
- OPENROUTER_MODEL selects the OpenRouter model.
- SERPER_API_KEY optionally enables live official-web guidance. It is never
  required for the Income Certificate flow's built-in Goa Online link.
- JANSEVA_OUTPUT_DIR sets the generated document directory.
- JANSEVA_BASE_URL sets the URL included in QR-code download fallbacks.

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
| GET | /sessions/{id}/applications/{service_id}/readiness | Get a reviewed service application plan |
| POST | /sessions/{id}/applications/{service_id}/details | Save service-specific application answers |
| POST | /sessions/{id}/applications/{service_id}/scan-open-form | Scan the logged-in form's visible requirements |
| POST | /sessions/{id}/launch_browser | Open the official portal for citizen login |
| POST | /sessions/{id}/automate_fill | Fill reviewed fields; stops before Save & Proceed |
| POST | /sessions/{id}/automate_upload | Upload scanned documents after portal-form review |
| DELETE | /sessions/{id} | End the session and wipe tracked artifacts |

## Current scope and safety

- The current service catalog contains Income, Residence, and Caste
  certificates.
- The eligibility engine includes central schemes and Maharashtra-specific
  rules. State-specific catalogs and rule sets can be added incrementally.
- Final government applications, OTPs, CAPTCHAs, and eligibility decisions
  must be verified by a human authority.
- Saarthi does not submit an application automatically. Auto-fill is enabled
  only for services with a verified portal mapping; all others remain guided,
  human-entered applications.
- The development server has permissive CORS and should not be exposed to the
  public internet without deployment hardening.
- Scans are stored only in the current session's local `scans/` folder for the
  document-upload step; review retention and access controls before production.

## Tests

    python -m pip install -r requirements-dev.txt
    pytest
