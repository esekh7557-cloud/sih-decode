"""Residence Certificate-specific Goa Online modal automation.

This is intentionally separate from ``form_filler.py`` so residence address
history cannot be confused with the Income Certificate family-member modal.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select


# Values collected for the Residence Certificate only.  Shared applicant data
# (name, contact details, address, identity proof, and so on) remains in the
# Income demo data used by the main filler.
RESIDENCE_DEMO_OVERRIDES = {
    "purpose": "Other",
    "where_to_submit": "Education institute",
    "residence_certificate_period": "For",
    "residence_period": "15",
    "residence_months": "5",
    "previous_certificate": "No",
    "voter_id_no": "",
    "rented_owned": "Owned",
    "currently_staying": "Yes",
    "period_of_stay": "Since",
    "residence_from_date": "25-MAR-2011",
    "residence_to_date": "25-AUG-2026",
    "apply_to_concerned_office": "Yes",
    "certify": "Yes",
}


def residence_demo_overrides() -> dict[str, str]:
    """Return a per-run copy of the Residence-only answers."""
    return dict(RESIDENCE_DEMO_OVERRIDES)


_RESIDENCE_MODAL_ALIASES = {
    "house_no": ["House/Flat No."],
    "rented_owned": ["Rented/Owned", "drpPremisesType_"],
    "currently_staying": ["Are you currently staying at below address?", "drpCurrentStay_"],
    "locality": ["Locality/Area/Ward"],
    "district": ["District"],
    "taluka": ["Taluka"],
    "village": ["Village"],
    "pincode": ["Pincode"],
    "period_of_stay": ["Period of Stay"],
    "from_date": ["From Date", "Date From", "Residence From Date", "txtFromDate", "dtFrom"],
    "to_date": ["To Date", "Date To", "Residence To Date", "txtToDate", "dtTo"],
    "apply_to_concerned_office": [
        "Do you want to apply for the Certificate to the concerned office",
        "drpApplyTo_",
    ],
}


def residence_modal_values(data: dict[str, Any]) -> dict[str, str]:
    """Build the Residence Details modal data from shared applicant values."""
    return {
        "house_no": str(data.get("house_no") or data.get("address") or ""),
        "rented_owned": str(data.get("rented_owned") or "Owned"),
        "currently_staying": str(data.get("currently_staying") or "Yes"),
        "locality": str(data.get("locality") or ""),
        "district": str(data.get("district") or ""),
        "taluka": str(data.get("taluka") or ""),
        "village": str(data.get("village") or ""),
        "pincode": str(data.get("pincode") or ""),
        "period_of_stay": str(data.get("period_of_stay") or "Since"),
        "from_date": str(data.get("residence_from_date") or ""),
        "to_date": str(data.get("residence_to_date") or ""),
        "apply_to_concerned_office": str(data.get("apply_to_concerned_office") or "Yes"),
    }


def native_date_value(value: str) -> str:
    """Convert portal-style dates to the ISO value required by <input type=date>."""
    text = str(value).strip()
    for pattern in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text


def portal_date_value(value: str) -> str:
    """Return the DD-MMM-YYYY format shown by Goa Online's date picker."""
    text = str(value).strip()
    for pattern in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).strftime("%d-%b-%Y").upper()
        except ValueError:
            continue
    return text.upper()


def fill_residence_details_modal(driver, data: dict[str, Any]) -> bool:
    """Open, fill, save, and verify the Residence Details dialog.

    The main form must not be submitted until this returns ``True``.  Goa
    Online has generic hidden modal shells in its page markup, so only a
    visible dialog containing Residence Details fields counts as open.
    """
    print("\n[FILL] Handling Residence Details modal...")
    modal_js = r"""
    const aliases = arguments[0];
    const action = arguments[1];
    const visible = (el) => !!el && el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0;
    const norm = (value) => (value || '').replace(/\s+/g, ' ').trim().toLowerCase();
    const controls = 'input:not([type="hidden"]), select, textarea';
    const dialogs = Array.from(document.querySelectorAll('[role="dialog"], .modal, .modal-dialog, .ui-dialog, .wicket-modal'))
      .filter(visible);
    if (action === 'confirm_yes') {
      const confirmation = dialogs
        .filter((el) => {
          const text = norm(el.innerText);
          return text.includes('are you sure') && text.includes('residence details');
        })
        .sort((left, right) => right.querySelectorAll('button, a, input').length
          - left.querySelectorAll('button, a, input').length)[0];
      if (!confirmation) return null;
      return Array.from(confirmation.querySelectorAll('button, a, input[type="button"], input[type="submit"]'))
        .filter(visible)
        .find((el) => /^(yes|confirm)$/i.test((el.innerText || el.value || '').trim())) || null;
    }
    const residenceMarkers = [
      'residence details', 'house/flat no', 'rented/owned', 'currently staying',
      'period of stay', 'apply for the certificate to the concerned office'
    ];
    const candidates = dialogs.filter((el) => {
      const text = norm(el.innerText);
      return residenceMarkers.some((marker) => text.includes(marker));
    });
    // Bootstrap/Wicket nests .modal-dialog inside .modal. Choose the
    // container that actually owns the most controls, not the last nested
    // wrapper, so fields and the Add button remain discoverable.
    candidates.sort((left, right) =>
      right.querySelectorAll(controls).length - left.querySelectorAll(controls).length
    );
    const modal = candidates[0] || null;

    if (action === 'is_open') return !!modal;
    if (action === 'open') {
      const triggers = Array.from(document.querySelectorAll('button, a, input[type="button"], input[type="submit"]'))
        .filter(visible)
        .map((el) => {
          const text = (el.innerText || el.value || '').trim();
          const parent = el.closest('tr, fieldset, .form-group, .panel, .card') || el.parentElement;
          const context = norm(parent && parent.innerText);
          let score = 0;
          if (/add\s+(residence|address|details)/i.test(text)) score = 3;
          else if (/^(?:\+\s*)?add\s*new$/i.test(text) && context.includes('residence')) score = 2;
          else if (/^(?:\+\s*)?add\s*new$/i.test(text)) score = 1;
          return { el, score };
        })
        .filter((item) => item.score > 0)
        .sort((left, right) => right.score - left.score);
      return triggers.length ? triggers[0].el : null;
    }
    if (!modal) return null;
    if (action === 'add') {
      return Array.from(modal.querySelectorAll('button, a, input[type="button"], input[type="submit"]'))
        .filter(visible)
        .filter((el) => /^(?:add|add\s+new)$/i.test((el.innerText || el.value || '').trim()))
        .pop() || null;
    }

    const wanted = aliases.map(norm);
    const matches = (value) => wanted.some((item) => norm(value).includes(item));
    for (const label of Array.from(modal.querySelectorAll('label'))) {
      if (!matches(label.innerText)) continue;
      if (label.htmlFor) {
        const linked = document.getElementById(label.htmlFor);
        if (visible(linked)) return linked;
      }
      const nested = label.querySelector(controls);
      if (visible(nested)) return nested;
      for (const parent of [label.parentElement, label.parentElement && label.parentElement.parentElement]) {
        if (!parent) continue;
        const found = Array.from(parent.querySelectorAll(controls)).find(visible);
        if (found) return found;
      }
    }
    return Array.from(modal.querySelectorAll(controls)).find((el) => {
      const idAndName = `${el.id || ''} ${el.name || ''} ${el.placeholder || ''}`;
      return visible(el) && matches(idAndName);
    }) || null;
    """

    try:
        is_open = driver.execute_script(modal_js, [], "is_open")
        if not is_open:
            opener = driver.execute_script(modal_js, [], "open")
            if not opener:
                print("   [WARN] Could not find the Add New button for Residence Details.")
                return False
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", opener)
            print("   [OPEN] Clicking Add New for Residence Details...")
            opener.click()
            for _ in range(20):
                time.sleep(0.5)
                if driver.execute_script(modal_js, [], "is_open"):
                    print("   [OK] Residence Details dialog is ready")
                    break

        if not driver.execute_script(modal_js, [], "is_open"):
            print("   [WARN] Residence Details modal was not found or could not be opened.")
            return False

        values = residence_modal_values(data)
        # District refreshes Taluka; Taluka refreshes Village.  Keep this order.
        ordered_fields = [
            "house_no", "rented_owned", "currently_staying", "locality",
            "district", "taluka", "village", "pincode", "period_of_stay",
        ]
        # Goa Online shows only From Date for "Since". It shows both From
        # Date and To Date only when the citizen selects "For".
        ordered_fields.append("from_date")
        if values["period_of_stay"].strip().lower() == "for":
            ordered_fields.append("to_date")
        ordered_fields.append("apply_to_concerned_office")
        missing_fields = []
        for key in ordered_fields:
            value = values[key]
            if not value:
                print(f"   [WARN] Residence modal {key} has no value.")
                missing_fields.append(key)
                continue
            element = driver.execute_script(modal_js, _RESIDENCE_MODAL_ALIASES[key], "field")
            if not element:
                print(f"   [WARN] Could not find Residence modal field: {key}")
                missing_fields.append(key)
                continue
            try:
                if element.tag_name.lower() == "select":
                    select = Select(element)
                    option = next(
                        (item for item in select.options if item.text.strip().lower() == value.strip().lower()),
                        None,
                    )
                    option = option or next(
                        (item for item in select.options if value.strip().lower() in item.text.strip().lower()),
                        None,
                    )
                    if not option:
                        print(f"   [WARN] No '{value}' option for Residence modal {key}")
                        missing_fields.append(key)
                        continue
                    select.select_by_visible_text(option.text)
                    time.sleep(1.0)
                else:
                    if key in {"from_date", "to_date"}:
                        # Goa Online renders these as readonly-looking text
                        # fields with a calendar icon and the DD-MMM-YYYY
                        # placeholder. Typing is ignored by the date picker,
                        # so update the DOM value and emit its normal events.
                        driver.execute_script(
                            """
                            const input = arguments[0];
                            const value = arguments[1];
                            const setter = Object.getOwnPropertyDescriptor(
                                HTMLInputElement.prototype, 'value'
                            ).set;
                            setter.call(input, value);
                            input.setAttribute('value', value);
                            ['input', 'keyup', 'change', 'blur'].forEach((name) =>
                                input.dispatchEvent(new Event(name, {bubbles: true}))
                            );
                            if (window.jQuery) {
                                window.jQuery(input).trigger('change').trigger('blur');
                            }
                            """,
                            element,
                            portal_date_value(value),
                        )
                    elif element.get_attribute("type").lower() == "date":
                        # Chromium rejects typed DD-MMM-YYYY text for native
                        # date controls. Set its ISO value and emit the same
                        # events the portal listens for.
                        driver.execute_script(
                            """
                            const input = arguments[0];
                            const value = arguments[1];
                            const setter = Object.getOwnPropertyDescriptor(
                                HTMLInputElement.prototype, 'value'
                            ).set;
                            setter.call(input, value);
                            input.dispatchEvent(new Event('input', {bubbles: true}));
                            input.dispatchEvent(new Event('change', {bubbles: true}));
                            input.dispatchEvent(new Event('blur', {bubbles: true}));
                            """,
                            element,
                            native_date_value(value),
                        )
                    else:
                        element.send_keys(Keys.CONTROL + "a")
                        element.send_keys(Keys.BACKSPACE)
                        element.send_keys(value + Keys.TAB)
                    time.sleep(0.5)
                print(f"   [OK] Filled Residence modal {key} -> {value}")
            except Exception as exc:
                print(f"   [WARN] Could not fill Residence modal {key}: {exc}")
                missing_fields.append(key)

        if missing_fields:
            print("   [HALT] Residence Details was not added; leaving the dialog open for review.")
            return False

        add_button = driver.execute_script(modal_js, [], "add")
        if not add_button:
            print("   [WARN] Could not find the Add button in Residence Details.")
            return False
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", add_button)
        add_button.click()
        print("   [OK] Clicked Add in Residence Details")

        # Goa Online asks for a separate confirmation before it saves the
        # residence row. Confirm this dialog before allowing the main form to
        # reach Save & Proceed.
        confirmation_button = None
        for _ in range(20):
            time.sleep(0.5)
            confirmation_button = driver.execute_script(modal_js, [], "confirm_yes")
            if confirmation_button:
                break
        if not confirmation_button:
            print("   [HALT] Residence Details confirmation was not shown; Save & Proceed was not started.")
            return False
        confirmation_button.click()
        print("   [OK] Clicked Yes to confirm Residence Details")

        for _ in range(20):
            time.sleep(0.5)
            if not driver.execute_script(modal_js, [], "is_open"):
                print("   [OK] Residence Details was added")
                return True
        print("   [HALT] Residence Details did not close after Add; it may need correction.")
        return False
    except Exception as exc:
        print(f"   [FAIL] Error processing Residence Details modal: {exc}")
        return False
