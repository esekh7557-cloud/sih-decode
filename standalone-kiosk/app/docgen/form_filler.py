import sys
import time
import os
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import UnexpectedAlertPresentException, NoAlertPresentException

def wait_and_click_yes(driver, action_name, timeout=2):
    """
    Utility function to wait for Wicket's dynamically injected 'Yes' confirmation modal
    and click it to avoid getting stuck.
    """
    print(f"   [WAIT] Looking for '{action_name}' confirmation 'Yes'/'Add' button...")
    try:
        yes_btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Yes') or contains(., 'Add') or contains(., 'Save')] | //a[contains(., 'Yes') or contains(., 'Add') or contains(., 'Save')]"))
        )
        # Scroll to it just in case
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", yes_btn)
        time.sleep(0.5)
        yes_btn.click()
        print(f"   [OK] Clicked confirmation for {action_name}")
        return True
    except:
        print(f"   [WARN] Could not find confirmation modal for {action_name} within {timeout}s")
        return False

def fill_form(session_id: str, port: int = 9222, certificate_type: str = "income_certificate"):
    import importlib
    print("=" * 60)
    print("  Saarthi -- Form Filler (Selenium Debugging Mode)")
    print("=" * 60)

    # 1. Load Data
    try:
        mapping_module = importlib.import_module(f"app.docgen.mappings.{certificate_type}")
        labelMapping = mapping_module.MAPPING
    except ImportError:
        print(f"\n[ERROR] No mapping found for certificate type: {certificate_type}")
        print(f"Make sure app/docgen/mappings/{certificate_type}.py exists!")
        return

    # The browser workflow normally receives the active session id. For local
    # form-filler testing, allow the explicit dummy mode to use the fallback
    # profile below even when the request came from a real session.
    filler_mode = os.getenv("JANSEVA_FORM_FILLER_MODE", "session").strip().lower()
    use_dummy_data = filler_mode in {"mock", "dummy", "fallback"}

    if session_id and not use_dummy_data:
        from app.main import store
        session = store.get(session_id)
        if not session:
            print(f"\n[ERROR] Session {session_id} not found!")
            return
        data = session.profile.model_dump()
        print(f"\n[DATA] Loaded session data for {data.get('name', 'Unknown')}")
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
            'other_income': '0',
            'part_no': '12',
            'serial_no': '34',
            'electoral_year': '2023',
            'constituency': 'Mapusa',
            'ration_card': 'RC123456',
            'id_proof_type': 'Aadhaar Card',
            'id_proof_no': '123456789012',
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

    # 2. Connect to the existing Edge Browser
    print(f"\n[CONNECT] Connecting to Edge on port {port}...")
    edge_options = Options()
    edge_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    
    try:
        driver = webdriver.Edge(options=edge_options)
    except Exception as e:
        print(f"\n[ERROR] Could not connect to Edge on port {port}!")
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
                        if (input) return input;
                    }
                    
                    const next = el.nextElementSibling;
                    if (next && (next.tagName === 'INPUT' || next.tagName === 'SELECT' || next.tagName === 'TEXTAREA') && next.type !== 'hidden') return next;
                    const inputInParent = el.parentElement.querySelector('input:not([type="hidden"]), select, textarea');
                    if (inputInParent) return inputInParent;
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
                        if (input) return input;
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
                    current_val = element.get_attribute("value")
                    
                    # Only skip if Wicket auto-filled the EXACT value we want (e.g. Pincode)
                    if current_val and str(current_val).strip().lower() == str(val).strip().lower():
                        print(f"   [OK] {key} is already auto-filled correctly with '{current_val}'. Skipping.")
                        success = True
                        break

                    # If we need to overwrite (e.g. Name is wrong), we must NOT use element.clear()!
                    # element.clear() does not trigger Wicket's keystroke listeners and causes internal state corruption.
                    # We must simulate a human pressing Ctrl+A then Backspace.
                    element.send_keys(Keys.CONTROL + "a")
                    element.send_keys(Keys.BACKSPACE)
                    time.sleep(0.2)
                    
                    # Add Keys.TAB to trigger Wicket's 'blur' Ajax call!
                    element.send_keys(str(val) + Keys.TAB)
                
                print(f"   [OK] Filled {key} -> {val}")
                success = True
                break # Break out of the retry loop if successful!
                
            except Exception as e:
                if isinstance(e, UnexpectedAlertPresentException):
                    try:
                        alert = driver.switch_to.alert
                        print(f"   [WARN] Dismissed Alert: {alert.text}")
                        alert.accept()
                    except NoAlertPresentException:
                        pass
                    last_error = "Unexpected validation alert triggered and dismissed."
                else:
                    last_error = str(e)
                # It will loop back around and try again!
                
        if not success:
            err_msg = last_error.split('\\n')[0] if last_error else "Element not found or permanently hidden."
            print(f"   [WARN] Could not fill {key} on main page. Saving for Modal attempt. ({err_msg})")
            failed_keys.append(key)

    # 4. Handle "+ Add New" Universal Modals
    if failed_keys:
        print(f"\\n[FILL] {len(failed_keys)} fields failed. Checking for '+ Add New' Modals...")
        try:
            add_new_btns = driver.find_elements(By.XPATH, "//button[contains(., 'Add New')] | //a[contains(., 'Add New')] | //span[contains(., 'Add New')] | //div[contains(@class, 'add')]")
            if add_new_btns:
                for btn in reversed(add_new_btns):
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", btn)
                        time.sleep(0.5)
                        try:
                            btn.click()
                        except:
                            driver.execute_script("arguments[0].click();", btn)
                        print("   [OK] Clicked '+ Add New'. Waiting for modal...")
                        time.sleep(2.5)
                        break
                
                # Retry failed fields inside the modal!
                for key in failed_keys:
                    val = data[key]
                    success = False
                    for attempt in range(2):
                        element = driver.execute_script(js_script, labelMapping[key])
                        if not element:
                            time.sleep(1.0)
                            continue
                            
                        tag_name = element.tag_name.lower()
                        try:
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
                            else:
                                current_val = element.get_attribute("value")
                                if current_val and str(current_val).strip().lower() == str(val).strip().lower():
                                    success = True
                                    break
                                element.send_keys(Keys.CONTROL + "a")
                                element.send_keys(Keys.BACKSPACE)
                                time.sleep(0.2)
                                element.send_keys(str(val) + Keys.TAB)
                            print(f"   [OK] Filled Modal {key} -> {val}")
                            success = True
                            break
                        except Exception as e:
                            pass
                            
                # Try to click the "Add" or "Save" button inside the modal
                try:
                    modal_save_btns = driver.find_elements(By.XPATH, "//div[contains(@class, 'modal')]//button[contains(., 'Add') or contains(., 'Save')] | //div[contains(@class, 'modal')]//input[@value='Add' or @value='Save']")
                    if modal_save_btns:
                        for mbtn in modal_save_btns:
                            if mbtn.is_displayed():
                                mbtn.click()
                                print("   [OK] Saved Modal Data.")
                                time.sleep(2.0)
                                wait_and_click_yes(driver, "Modal Details")
                                break
                except:
                    print("   [WARN] Could not click Modal Save button natively.")
                    
        except Exception as e:
            print(f"   [FAIL] Error processing modal: {e}")

    # 5. Click "Save & Proceed"
    print("\\n[FILL] Submitting Form...")
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2.0)
        
        print("   [WAIT] Waiting for 'Save & Proceed' button to become visible...")
        clicked_save = False
        for _ in range(10):
            time.sleep(0.5)
            save_btns = driver.find_elements(By.XPATH, "//button[contains(., 'Save & Proceed') or contains(., 'Save and Proceed') or contains(., 'Save')] | //a[contains(., 'Save & Proceed') or contains(., 'Save and Proceed') or contains(., 'Save')] | //input[contains(@value, 'Save')]")
            # We want the main submit button, which usually has 'Proceed' or 'Upload'
            best_btn = None
            for btn in reversed(save_btns):
                text = btn.text.lower() if btn.text else btn.get_attribute("value").lower()
                if "proceed" in text or "upload" in text:
                    best_btn = btn
                    break
            
            if not best_btn and save_btns:
                best_btn = save_btns[-1]
                
            if best_btn and best_btn.is_displayed():
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", best_btn)
                time.sleep(0.5)
                try:
                    best_btn.click()
                    print("   [OK] Clicked 'Save & Proceed' natively")
                    clicked_save = True
                    break
                except Exception:
                    try:
                        driver.execute_script("arguments[0].click();", best_btn)
                        print("   [OK] Clicked 'Save & Proceed' via Javascript")
                        clicked_save = True
                        break
                    except:
                        pass
            if clicked_save:
                break
        
        if clicked_save:
            wait_and_click_yes(driver, "Final Submission")
        else:
            print("   [WARN] Could not find or click 'Save & Proceed'.")
            
    except Exception as e:
        print(f"   [FAIL] Could not click Save & Proceed: {e}")

    print("\\n[DONE] Finished auto-filling form via Native Selenium!")
    print("\\n[WAIT] Waiting 4 seconds for page to transition to Document Upload...")
    time.sleep(4.0)
    
    print("\\n[LAUNCH] Automatically running Document Uploader...")
    import subprocess
    cmd = [sys.executable, "-m", "app.docgen.document_uploader"]
    if session_id:
        cmd.extend(["--folder", os.path.join(os.getcwd(), "scans", session_id)])
    subprocess.run(cmd)

if __name__ == "__main__":
    fill_form(None)
