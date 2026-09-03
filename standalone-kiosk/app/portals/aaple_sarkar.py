"""Aaple Sarkar (Maharashtra) certificate application playbook.

NOTE: The CSS selectors below are placeholders and MUST be verified against
the live portal before enabling online mode. Until then any failure raises
PortalDown and the kiosk falls back to offline PDF generation automatically.

Rules honoured here:
- wait after every navigation/click
- screenshot before and after submission
- never navigate away before capturing the acknowledgment number
- OTP is human-in-the-loop and never stored
"""
from __future__ import annotations

from app.core.profile import CitizenProfile

from .base import BasePortal, PortalDown


class AapleSarkar(BasePortal):
    url = "https://aaplesarkar.mahaonline.gov.in/en"

    SELECTORS = {
        "mobile_input": "#txtMobileNo",
        "send_otp": "#btnSendOTP",
        "otp_input": "#txtOTP",
        "verify_otp": "#btnVerify",
        "department_revenue": "text=Revenue Department",
        "submit": "#btnSubmit",
        "acknowledgment": "#lblAckNo",
    }

    def apply(self, service_name: str, profile: CitizenProfile, uploads: list) -> str:
        """Run the full playbook; return the acknowledgment number."""
        self._start()
        page = self._page
        try:
            # 1. Login with mobile OTP (human in the loop)
            page.fill(self.SELECTORS["mobile_input"], profile.mobile)
            page.click(self.SELECTORS["send_otp"])
            otp = self.ask_human("OTP from citizen's phone")
            page.fill(self.SELECTORS["otp_input"], otp)
            page.click(self.SELECTORS["verify_otp"])
            page.wait_for_load_state("networkidle")

            # 2. Select department and service
            page.click(self.SELECTORS["department_revenue"])
            page.click(f"text={service_name}")
            page.wait_for_load_state("networkidle")

            # 3. Fill citizen data (label mapping to be verified per service form)
            for label, value in {
                "Applicant Name": profile.name,
                "Father Name": profile.father_name,
                "Date of Birth": profile.dob,
                "District": profile.district,
                "Taluka": profile.taluka,
            }.items():
                try:
                    page.get_by_label(label).fill(str(value))
                except Exception:
                    self.notify(f"Field not found on portal: {label}")

            # 4. Upload scanned documents
            for path in uploads:
                try:
                    page.set_input_files("input[type=file]", path)
                except Exception:
                    self.notify(f"Upload control not found for {path}")

            # 5. Preview screenshot -> explicit citizen confirmation
            self.screenshot("aaple_sarkar_preview")
            answer = self.ask_human("Confirm submission? (haan/nahi)").strip().lower()
            if answer not in ("haan", "yes", "y"):
                raise PortalDown("Citizen did not confirm - aborting online submission")

            # 6. Submit and capture acknowledgment BEFORE any navigation
            page.click(self.SELECTORS["submit"])
            page.wait_for_load_state("networkidle")
            self.screenshot("aaple_sarkar_submitted")
            ack = page.text_content(self.SELECTORS["acknowledgment"]) or ""
            if not ack.strip():
                raise PortalDown("Acknowledgment number not found")
            return ack.strip()
        except PortalDown:
            raise
        except Exception as exc:
            raise PortalDown(f"Aaple Sarkar playbook failed: {exc}") from exc
        finally:
            self.close()
