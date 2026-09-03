import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import UnexpectedAlertPresentException


# This module is retained only for older, mapping-based deployments.  It may
# fill reviewed ordinary fields, but must never deal with sign-in challenges,
# files, or actions which advance an application.
_BLOCKED_CONTROL_TYPES = {
    "button", "file", "hidden", "image", "password", "reset", "submit",
}
_SENSITIVE_LABEL_RE = re.compile(
    r"password|\botp\b|captcha|verification\s*code|security\s*code",
    re.IGNORECASE,
)
_MASKED_VALUE_RE = re.compile(r"(?:x|\*|•){3,}", re.IGNORECASE)


def _labels_text(labels) -> str:
    """Normalize a mapping's possible labels for safety checks."""
    if isinstance(labels, (list, tuple, set)):
        return " ".join(str(label) for label in labels)
    return str(labels or "")


def _is_sensitive_control(key: str, labels) -> bool:
    return bool(_SENSITIVE_LABEL_RE.search(f"{key} {_labels_text(labels)}"))


def _is_masked_value(value) -> bool:
    """Do not write placeholders such as ``XXXX XXXX 1234`` to a portal."""
    return isinstance(value, str) and bool(_MASKED_VALUE_RE.search(value))

def wait_and_click_yes(driver, action_name, timeout=2):
    """Legacy compatibility shim that intentionally never confirms a portal action."""
    del driver, timeout
    print(f"   [REVIEW] {action_name} needs the citizen's confirmation. No action was clicked.")
    return False

def fill_form(
    session_id: str,
    port: int = 9222,
    certificate_type: str = "income_certificate",
    proceed_to_upload: bool = False,
):
    import importlib
    print("=" * 60)
    print("  JanSeva AI -- Form Filler (Selenium Debugging Mode)")
    print("=" * 60)

    # 1. Load Data
    try:
        mapping_module = importlib.import_module(f"app.docgen.mappings.{certificate_type}")
        labelMapping = mapping_module.MAPPING
    except ImportError:
        print(f"\n[ERROR] No mapping found for certificate type: {certificate_type}")
        print(f"Make sure app/docgen/mappings/{certificate_type}.py exists!")
        return

    if session_id:
        from app.main import store
        session = store.get(session_id)
        if not session:
            print(f"\n[ERROR] Session {session_id} not found!")
            return
        # Only use answers actually supplied by the citizen. Missing details
        # must be collected in Saarthi's review screen, never guessed.
        combined_data = session.profile.model_dump()
        combined_data.update(getattr(session, "application_details", {}).get(session.service_id or "", {}))
        data = {}
        for key, value in combined_data.items():
            if key not in labelMapping or value in (None, ""):
                continue
            if _is_sensitive_control(key, labelMapping[key]):
                print(f"   [SKIP] {key}: sign-in or verification fields are citizen-only.")
                continue
            if _is_masked_value(value):
                print(f"   [SKIP] {key}: masked values are never written to a portal.")
                continue
            data[key] = value
        print("\n[DATA] Loaded reviewed session data.")
    else:
        # Fallback dummy data for local testing
        print("\n[DATA] Using dummy fallback data...")
        data = {
            'applying_for': 'Self',
            'purpose': 'Marriage Registration',
            'residence_period': 'For',
            'title': 'Mr.',
            'name': 'Vedant Gurav',
            'place_of_birth': 'Goa',
            'dob': '12/05/1990',
            'gender': 'Male',
            'marital_status': 'Unmarried',
            'guardian_relation': 'Father',
            'father_name': 'Ram Gurav',
            'mobile': '9876543210',
            'email': 'vedant@example.com',
            'occupation': 'Student',
            'caste_category': 'General',
            'address': 'House 123',
            'locality': 'Mapusa',
            'district': 'North Goa',
            'taluka': 'Bardez',
            'village': 'Mapusa',
            'pincode': '403507',
            'family_size': '4',
            'earning_members': '1',
            'children_count': '0',
            'previous_certificate': 'No',
            'immovable_property': 'No',
            'property_value': '0',
            'other_income': 'No',
            'part_no': '12',
            'serial_no': '34',
            'electoral_year': '2023',
            'constituency': 'Mapusa',
            'ration_card': 'RC123456',
            'id_proof_type': 'Aadhaar Card',
            'certify': 'Yes',
            
            # Modal specific fallback data
            'house_no': 'House 123',
            'rented_owned': 'Owned',
            'currently_staying': 'Yes',
            'period_of_stay': 'For',
            'from_date': '01-Jan-2000',
            'to_date': '01-Jan-2024',
            'apply_to_concerned_office': 'Yes'
        }

    # Mapping files can be customized outside this module, so apply the same
    # protections to both session data and the local demo data.
    safe_data = {}
    for key, value in data.items():
        if _is_sensitive_control(key, labelMapping[key]):
            print(f"   [SKIP] {key}: sign-in or verification fields are citizen-only.")
            continue
        if _is_masked_value(value):
            print(f"   [SKIP] {key}: masked values are never written to a portal.")
            continue
        safe_data[key] = value
    data = safe_data

    # 2. Connect to the existing Chrome browser
    print(f"\n[CONNECT] Connecting to Chrome on port {port}...")
    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
    except Exception as e:
        print(f"\n[ERROR] Could not connect to Chrome on port {port}!")
        print(f"Make sure you launched it with --remote-debugging-port={port}")
        return

    # Wait for page to fully load
    WebDriverWait(driver, 10).until(
        lambda d: d.execute_script('return document.readyState') == 'complete'
    )
    
    # Switch to the correct tab if there are multiple
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        if "goaonline" in driver.current_url.lower() or "goa" in driver.title.lower():
            break

    print(f"   [OK] Connected! Current page: {driver.title}")

    # 3. Fill the Form
    print("\n[FILL] Starting native element matching...")
    
    js_script = """
    const labelTexts = arguments[0];
    
    function isSafeControl(control) {
        if (!control) return false;
        const type = (control.getAttribute('type') || '').toLowerCase();
        return !['button', 'file', 'hidden', 'image', 'password', 'reset', 'submit'].includes(type);
    }

    // First, strictly try to match exact text or 'for' attributes to prevent cross-contamination
    function findInputByLabel(labels) {
        for (const text of labels) {
            // 1. Check strict <label> tags
            const labelElements = Array.from(document.querySelectorAll('label'));
            for (const el of labelElements) {
                if (el.innerText.toLowerCase().trim() === text.toLowerCase().trim() || 
                    el.innerText.toLowerCase().includes(text.toLowerCase())) {
                    
                    if (el.htmlFor) {
                        const input = document.getElementById(el.htmlFor);
                        if (isSafeControl(input)) return input;
                    }
                    
                    const next = el.nextElementSibling;
                    if (next && (next.tagName === 'INPUT' || next.tagName === 'SELECT' || next.tagName === 'TEXTAREA') && isSafeControl(next)) return next;
                    const inputInParent = el.parentElement.querySelector('input:not([type="hidden"]), select, textarea');
                    if (isSafeControl(inputInParent)) return inputInParent;
                }
            }
            
            // 2. Check table cells
            const tdElements = Array.from(document.querySelectorAll('td'));
            for (const el of tdElements) {
                if (el.innerText.toLowerCase().trim() === text.toLowerCase().trim() || 
                    el.innerText.toLowerCase().includes(text.toLowerCase())) {
                    
                    const next = el.nextElementSibling;
                    if (next) {
                        const input = next.querySelector('input:not([type="hidden"]), select, textarea');
                        if (isSafeControl(input)) return input;
                    }
                }
            }
        }
        return null;
    }

    return findInputByLabel(labelTexts);
    """
    
    failed_keys = []

    for key, val in data.items():
        if key not in labelMapping:
            continue
            
        success = False
        last_error = ""
        for attempt in range(3):
            # Give Wicket plenty of time (2.0s) to finish any pending Ajax (especially after TABs)
            time.sleep(1.0)
                
            element = driver.execute_script(js_script, labelMapping[key])
            if not element:
                continue
                
            tag_name = element.tag_name.lower()
            
            try:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                time.sleep(0.5)
                
                # Re-fetch it just in case scrolling triggered a layout redraw
                element = driver.execute_script(js_script, labelMapping[key])
                if not element: continue
                tag_name = element.tag_name.lower()
                control_type = (element.get_attribute("type") or "").lower()
                if control_type in _BLOCKED_CONTROL_TYPES:
                    print(f"   [SKIP] {key}: this control is not safe for automatic filling.")
                    success = True
                    break
                
                if tag_name == "select":
                    select = Select(element)
                    found_opt = False
                    for opt in select.options:
                        if str(val).lower() in opt.text.lower():
                            select.select_by_visible_text(opt.text)
                            found_opt = True
                            break
                    
                    if not found_opt:
                        for opt in select.options:
                            if str(val).lower() in opt.get_attribute("value").lower():
                                select.select_by_value(opt.get_attribute("value"))
                                break
                                
                elif element.get_attribute("type") == "checkbox":
                    is_selected = element.is_selected()
                    wants_selected = str(val).lower() in ["true", "yes", "1", "on"]
                    if is_selected != wants_selected:
                        element.click()
                        
                elif element.get_attribute("type") == "radio":
                    radio_name = element.get_attribute("name")
                    clicked_radio = False
                    if radio_name:
                        radios = driver.find_elements(By.NAME, radio_name)
                        for r in radios:
                            r_id = r.get_attribute("id")
                            
                            # 1. Match by value
                            if r.get_attribute("value") and str(val).lower() in r.get_attribute("value").lower():
                                r.click()
                                clicked_radio = True
                                break
                                
                            # 2. Match by associated <label for="...">
                            if r_id:
                                labels = driver.find_elements(By.XPATH, f"//label[@for='{r_id}']")
                                if labels and str(val).lower() in labels[0].text.lower():
                                    r.click()
                                    clicked_radio = True
                                    break
                            
                            # 3. Match by parent wrapper text
                            parent_text = r.find_element(By.XPATH, "..").text
                            if parent_text and str(val).lower() in parent_text.lower():
                                r.click()
                                clicked_radio = True
                                break
                    
                    if not clicked_radio:
                        # Fallback just click the one we found if we couldn't match text
                        element.click()
                        
                else:
                    # Normal input/textarea
                    # Do not inspect existing portal values.  Native clearing
                    # avoids Wicket state corruption while entering reviewed data.
                    # element.clear() does not trigger Wicket's keystroke listeners and causes internal state corruption.
                    # We must simulate a human pressing Ctrl+A then Backspace.
                    element.send_keys(Keys.CONTROL + "a")
                    element.send_keys(Keys.BACKSPACE)
                    time.sleep(0.2)
                    
                    # Add Keys.TAB to trigger Wicket's 'blur' Ajax call!
                    element.send_keys(str(val) + Keys.TAB)
                
                print(f"   [OK] Filled reviewed field: {key}")
                success = True
                break # Break out of the retry loop if successful!
                
            except Exception as e:
                if isinstance(e, UnexpectedAlertPresentException):
                    last_error = "A portal alert needs the citizen's review."
                else:
                    last_error = type(e).__name__
                # It will loop back around and try again!
                
        if not success:
            err_msg = last_error.split('\\n')[0] if last_error else "Element not found or permanently hidden."
            print(f"   [WARN] Could not fill {key} on main page. Saving for Modal attempt. ({err_msg})")
            failed_keys.append(key)

    if failed_keys:
        print(f"\n[REVIEW] {len(failed_keys)} field(s) need the citizen's attention. Modal controls were not opened.")
    if proceed_to_upload:
        print("[REVIEW] The legacy advance flag is ignored. The citizen must choose every next action manually.")
    print("\n[REVIEW] Reviewed fields were filled. Saarthi will not save, continue, upload, or submit.")

if __name__ == "__main__":
    fill_form(None)
