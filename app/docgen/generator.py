"""Print-ready document generation.

Renders HTML via Jinja2, converts to PDF with WeasyPrint when installed,
otherwise writes the HTML file (still printable via browser).
Aadhaar is always shown masked (last 4 digits only).
"""
from __future__ import annotations

import datetime
import os
from pathlib import Path

from jinja2 import Template

from app.core.profile import CitizenProfile

OUTPUT_DIR = Path(os.getenv("JANSEVA_OUTPUT_DIR", "output"))

APPLICATION_TEMPLATE = Template(
    """
<html><head><meta charset=\"utf-8\"><style>
body { font-family: 'Noto Sans Devanagari', sans-serif; font-size: 14px; margin: 2cm; }
h2 { text-align: center; }
table { width: 100%; border-collapse: collapse; }
td { border: 1px solid #333; padding: 6px 10px; }
.sig { margin-top: 60px; text-align: right; }
</style></head><body>
<h2>{{ service_name }} - Application / \u0906\u0935\u0947\u0926\u0928</h2>
<p>To, The Tehsildar / Mamlatdar, {{ p.taluka }} Taluka, {{ p.district }} District</p>
<table>
<tr><td>Applicant Name / \u0928\u093e\u092e</td><td>{{ p.name }}</td></tr>
<tr><td>Father's Name / \u092a\u093f\u0924\u093e \u0915\u093e \u0928\u093e\u092e</td><td>{{ p.father_name }}</td></tr>
<tr><td>Date of Birth / \u091c\u0928\u094d\u092e \u0924\u093f\u0925\u093f</td><td>{{ p.dob }}</td></tr>
<tr><td>Aadhaar</td><td>XXXX XXXX {{ p.aadhaar_last4 }}</td></tr>
<tr><td>Address / \u092a\u0924\u093e</td><td>{{ p.address }}, {{ p.village }}, {{ p.taluka }}, {{ p.district }}</td></tr>
<tr><td>Mobile</td><td>{{ p.mobile }}</td></tr>
<tr><td>Occupation / \u0935\u094d\u092f\u0935\u0938\u093e\u092f</td><td>{{ p.occupation }}</td></tr>
<tr><td>Annual Income / \u0935\u093e\u0930\u094d\u0937\u093f\u0915 \u0906\u092f</td><td>{{ p.annual_income or '' }}</td></tr>
<tr><td>Purpose / \u0909\u0926\u094d\u0926\u0947\u0936\u094d\u092f</td><td>{{ purpose }}</td></tr>
</table>
<p>I declare that the above information is true. /
\u092e\u0948\u0902 \u0918\u094b\u0937\u0923\u093e \u0915\u0930\u0924\u093e/\u0915\u0930\u0924\u0940 \u0939\u0942\u0901 \u0915\u093f \u0909\u092a\u0930\u094b\u0915\u094d\u0924 \u091c\u093e\u0928\u0915\u093e\u0930\u0940 \u0938\u0924\u094d\u092f \u0939\u0948\u0964</p>
<div class=\"sig\">Signature / \u0939\u0938\u094d\u0924\u093e\u0915\u094d\u0937\u0930: ______________<br>Date: {{ today }}</div>
</body></html>
"""
)

SCHEMES_TEMPLATE = Template(
    """
<html><head><meta charset=\"utf-8\"><style>
body { font-family: sans-serif; margin: 2cm; } h2 { text-align: center; }
li { margin-bottom: 14px; }
</style></head><body>
<h2>\u0906\u092a \u0907\u0928 \u092f\u094b\u091c\u0928\u093e\u0913\u0902 \u0915\u0947 \u0932\u093f\u090f \u092a\u093e\u0924\u094d\u0930 \u0939\u0948\u0902 / You may be eligible for these schemes</h2>
<ol>
{% for r in results %}
<li><b>{{ r.scheme_name }}</b>{% if r.verify_manually %} (\u0915\u0943\u092a\u092f\u093e \u0915\u093e\u0930\u094d\u092f\u093e\u0932\u092f \u092e\u0947\u0902 \u092a\u0941\u0937\u094d\u091f\u093f \u0915\u0930\u0947\u0902 / verify at office){% endif %}<br>
Reason: {{ r.eligibility_reason }}<br>
Benefit: {{ r.estimated_benefit }}<br>
Apply: {{ r.how_to_apply }}</li>
{% endfor %}
</ol></body></html>
"""
)


def _write(html: str, stem: str) -> str:
    """Write PDF if WeasyPrint is available, else printable HTML."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = OUTPUT_DIR / f"{stem}.pdf"
    try:
        from weasyprint import HTML  # optional dependency

        HTML(string=html).write_pdf(str(pdf_path))
        return str(pdf_path)
    except Exception:
        html_path = OUTPUT_DIR / f"{stem}.html"
        html_path.write_text(html, encoding="utf-8")
        return str(html_path)


def generate_application(
    service_name: str, profile: CitizenProfile, purpose: str = "", language: str = "hi"
) -> str:
    html = APPLICATION_TEMPLATE.render(
        service_name=service_name,
        p=profile,
        purpose=purpose,
        today=datetime.date.today().isoformat(),
    )
    stamp = int(datetime.datetime.now().timestamp())
    import uuid
    uid = uuid.uuid4().hex[:6]
    return _write(html, f"application_{stamp}_{uid}")


def generate_schemes_sheet(results: list, language: str = "hi") -> str:
    html = SCHEMES_TEMPLATE.render(results=results)
    stamp = int(datetime.datetime.now().timestamp())
    import uuid
    uid = uuid.uuid4().hex[:6]
    return _write(html, f"schemes_{stamp}_{uid}")
