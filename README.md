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
- Explainable scheme cards with eligibility reason, benefit, and application
  route.
- Certificate service checklists with documents, fee, processing time, and
  validity.
- An end-session control that removes tracked session data.

## How it works

1. A citizen enters their data or uploads document images.
2. The dashboard saves the profile in a temporary in-memory session.
3. The rule engine calculates every verified scheme match.
4. OpenRouter enrichment may add extra candidates, but each is labelled for
   manual verification and never overrides rule-based results.
5. The assistant returns guidance based on the citizen request, profile
   completeness, service catalog, and scheme matches.

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
| DELETE | /sessions/{id} | End the session and wipe tracked artifacts |

## Current scope and safety

- The current service catalog contains Income, Residence, and Caste
  certificates.
- The eligibility engine includes central schemes and Maharashtra-specific
  rules. State-specific catalogs and rule sets can be added incrementally.
- Final government applications, OTPs, CAPTCHAs, and eligibility decisions
  must be verified by a human authority.
- The development server has permissive CORS and should not be exposed to the
  public internet without deployment hardening.
- Review the scan storage paths before production. The current scan endpoint
  includes a machine-specific local-copy behavior.

## Tests

    python -m pip install -r requirements-dev.txt
    pytest
