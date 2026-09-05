import sys
import os
import json
import time
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import UnexpectedAlertPresentException, NoAlertPresentException
def wait_and_click_yes(driver, action_name, timeout=10):
    print(f"   [WAIT] Waiting for 'Yes' modal for {action_name}...")
    for _ in range(int(timeout * 2)):
        time.sleep(0.5)
        try:
            for tag in ["button", "a"]:
                elements = driver.find_elements(By.XPATH, f"//{tag}[contains(., 'Yes') or contains(., 'YES')]")
                for el in elements:
                    if el.is_displayed():
                        el.click()
                        print(f"   [OK] Clicked 'Yes' to confirm {action_name}")
                        return True
            elements = driver.find_elements(By.XPATH, "//input[@value='Yes' or @value='YES']")
            for el in elements:
                if el.is_displayed():
                    el.click()
                    print(f"   [OK] Clicked 'Yes' to confirm {action_name}")
                    return True
        except:
            pass
    print(f"   [WARN] Could not find 'Yes' modal for {action_name} within {timeout}s")
    return False

def main():
    print("=" * 60)
    print("  JanSeva AI -- Form Filler (Selenium Debugging Mode)")
    print("=" * 60)

    # 1. Load Data - from file argument, or use defaults
    data = None
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"   [OK] Loaded data from: {sys.argv[1]}")
    
    if data is None:
        # Default data for testing
        data = {
            "certificate_type": "CERT_INC",  # CERT_INC, CERT_CST, CERT_DOM
            "applying_for": "",
            "purpose": "economically weaker section",
            "residence_period": "15",
            "title": "Mr.",
            "name": "Rahul Sharma",
            "place_of_birth": "Panaji",
            "dob": "15/08/1990",
            "gender": "male",
            "marital_status": "",
            "guardian_relation": "Father",
            "father_name": "Ramesh Kumar",  
            "mobile": "9876543210",
            "email": "rahul.sharma@example.com",
            "occupation": "", 
            "caste_category": "GENERAL",
            "address": "Flat 4B, Sunshine Apartments",
            "locality": "Market Area",
            "district": "North Goa",
            "taluka": "Tiswadi",
            "village": "Panaji",
            "pincode": "403001",
            "family_size": "4",
            "earning_members": "1",
            "children_count": "2",
            "previous_certificate": "No",
            "immovable_property": "no", 
            "property_value": "0",
            "other_income": "0",
            "part_no": "12",
            "serial_no": "345",
            "electoral_year": "2023",
            "constituency": "Panaji",
            "ration_card": "RC1234567",
            "property_details": "None",
            "id_proof_type": "aadhaar card", 
            "id_proof_no": "673720425369",
            "certify": "yes",
            "family_members": []
        }
    
    cert_type = data.get("certificate_type", "CERT_INC")
    print(f"   [INFO] Certificate type: {cert_type}")

    # 2. Connect to existing Edge browser
    print("\n[CONNECT] Connecting to Edge on port 9222...")
    edge_options = Options()
    edge_options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

    try:
        driver = webdriver.Edge(options=edge_options)
        
        # Switch to the correct tab
        found = False
        for handle in driver.window_handles:
            driver.switch_to.window(handle)
            if "goaonline" in driver.current_url.lower() or "goa" in driver.title.lower():
                found = True
                break
                
        if not found:
            print("   [WARN] Could not find Goa Online tab. Using current tab.")
            
        print(f"   [OK] Connected! Current page: {driver.title}")
    except Exception as e:
        print(f"\n[ERROR] Could not connect to Edge!")
        sys.exit(1)

    # 3. Iterate over data and inject JS to find each input fresh (prevents StaleElementReferenceException)
    print("\n[FILL] Starting Selenium Native Type-in...")
    
    js_script = """
    const labelTexts = arguments[0];
    
    function findInputByLabel(labelTexts) {
        const labels = Array.from(document.querySelectorAll('label'));
        for (const label of labels) {
            if (labelTexts.some(text => label.innerText && label.innerText.toLowerCase().includes(text.toLowerCase()))) {
                if (label.htmlFor) {
                    const input = document.getElementById(label.htmlFor);
                    if (input && input.getBoundingClientRect().width > 0) return input;
                }
                const inputInside = label.querySelector('input:not([type="hidden"]), select, textarea');
                if (inputInside && inputInside.getBoundingClientRect().width > 0) return inputInside;
                
                let next = label.nextElementSibling;
                for(let i=0; i<3 && next; i++) {
                    const input = next.querySelector('input:not([type="hidden"]), select, textarea');
                    if (input && input.getBoundingClientRect().width > 0) return input;
                    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(next.tagName) && next.type !== 'hidden' && next.getBoundingClientRect().width > 0) return next;
                    next = next.nextElementSibling;
                }
            }
        }
        
        // Fallback for checkboxes/radios without proper <label> tags (like certify)
        const allEls = Array.from(document.querySelectorAll('*'));
        for (const el of allEls) {
            if (el.children.length === 0 && el.innerText && labelTexts.some(text => el.innerText.toLowerCase().includes(text.toLowerCase()))) {
                let prev = el.previousElementSibling;
                if (prev && prev.tagName === 'INPUT' && prev.type !== 'hidden') return prev;
                let next = el.nextElementSibling;
                if (next && next.tagName === 'INPUT' && next.type !== 'hidden') return next;
                const inputInParent = el.parentElement.querySelector('input:not([type="hidden"])');
                if (inputInParent) return inputInParent;
            }
        }
        return null;
    }

    return findInputByLabel(labelTexts);
    """
    # Common fields for ALL certificate types
    commonLabels = {
        'applying_for': ['Applying for'],
        'purpose': ['Purpose'],
        'residence_period': ['Residence Period'],
        'title': ['Title', 'Prefix'],
        'name': ['Name of the applicant', 'Applicant Name', 'Name'],
        'place_of_birth': ['Place of Birth'],
        'dob': ['Date of birth', 'DOB', 'Date of Birth'],
        'gender': ['Gender'],
        'marital_status': ['Marital Status'],
        'guardian_relation': ["Father's/Husband's/Guardian's Name", "Father/Husband/Wife/Guardian"],
        'father_name': ["Father's/Husband's", "Father Name", "Father's Name", "Father's/Husband's/Guardian's Name"],
        'mobile': ['Mobile'],
        'email': ['Email'],
        'address': ['House/Flat No.', 'House/Flat No', 'House/Bldg./Apt. No. & Name', 'Address'],
        'locality': ['Locality/Area/Ward', 'Street/Locality/Ward', 'Locality'],
        'district': ['District'],
        'taluka': ['Taluka'],
        'village': ['Village/City', 'Village/Town', 'Village', 'Town'],
        'pincode': ['Pincode'],
        'id_proof_type': ['ID Proof'], 
        'id_proof_no': ['ID Proof No.', 'ID Proof No'],
        'certify': ['I hereby certify that']
    }
    incomeLabels = {
        'occupation': ['Occupational Status', 'Occupation'],
        'family_size': ['Total Family Members', 'Total family size', 'family size'],
        'earning_members': ['Total earning members in family', 'Total earning members', 'earning members'],
        'children_count': ['Total No. of Children in family', 'Total No. of Children', 'children'],
        'previous_certificate': ['Any Income certificate was issued to you recently', 'Any Income certificate was issued', 'previous Certificate'],
        'immovable_property': ['Any immovable property'], 
        'property_value': ['Property Value', 'Value of Property'],
        'other_income': ['Any income from other sources', 'Income from other source'],
        'ration_card': ['Ration Card No.'],
        'property_details': ['Property Details'],
    }
    casteLabels = {
        'caste_category': ['Caste category', 'Caste/Category', 'Category'],
        'part_no': ['Part No.', 'Part No'],
        'serial_no': ['Serial No.', 'Serial No'],
        'electoral_year': ['Electoral Roll Year'],
        'constituency': ['Constituency'],
    }
    residenceLabels = {
        'residence_period': ['Residence Period'],
        'part_no': ['Part No.', 'Part No'],
        'serial_no': ['Serial No.', 'Serial No'],
        'electoral_year': ['Electoral Roll Year'],
        'constituency': ['Constituency'],
    }
    
    labelMapping = dict(commonLabels)
    if cert_type == 'CERT_INC':
        labelMapping.update(incomeLabels)
    elif cert_type == 'CERT_CST':
        labelMapping.update(casteLabels)
    elif cert_type == 'CERT_DOM':
        labelMapping.update(residenceLabels)
    else:
        labelMapping.update(incomeLabels)
        labelMapping.update(casteLabels)
        labelMapping.update(residenceLabels)
    
    print(f"   [INFO] Filling {len(labelMapping)} field mappings for {cert_type}")

    for key, val in data.items():
        if key not in labelMapping:
            continue
            
        success = False
        last_error = ""
        for attempt in range(3):
            # Give Wicket plenty of time (2.0s) to finish any pending Ajax (especially after TABs)
            time.sleep(2.0)
                
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
                        if val.lower() in opt.text.lower():
                            select.select_by_visible_text(opt.text)
                            found_opt = True
                            break
                    
                    if not found_opt:
                        for opt in select.options:
                            if val.lower() in opt.get_attribute("value").lower():
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
                            r_val = r.get_attribute("value")
                            
                            # 1. Match by value attribute
                            if r_val and val.lower() == str(r_val).lower():
                                r.click()
                                clicked_radio = True
                                break
                                
                            # 2. Match by associated <label for="...">
                            if r_id:
                                labels = driver.find_elements(By.XPATH, f"//label[@for='{r_id}']")
                                if labels and val.lower() in labels[0].text.lower():
                                    r.click()
                                    clicked_radio = True
                                    break
                            
                            # 3. Match by parent wrapper text
                            parent_text = r.find_element(By.XPATH, "..").text
                            if parent_text and val.lower() in parent_text.lower():
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
                    element.send_keys(val + Keys.TAB)
                
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
            # Clean up the error message for readability
            err_msg = last_error.split('\n')[0] if last_error else "Element not found or permanently hidden."
            print(f"   [WARN] Could not fill {key} after 3 attempts. Skipping. ({err_msg})")

    # 4. Handle "+ Add New" Family Member Modal
    print("\n[FILL] Handling Family Member Modal...")
    try:
        add_new_btns = driver.find_elements(By.XPATH, "//button[contains(., 'Add New')] | //a[contains(., 'Add New')]")
        if add_new_btns:
            for btn in reversed(add_new_btns):
                if btn.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", btn)
                    time.sleep(0.5)
                    try:
                        btn.click()
                    except:
                        pass # Skip JS click to avoid bot detection
                    print("   [OK] Clicked '+ Add New'")
                    time.sleep(2.5) 
                    break
            
            def get_modal_element(key):
                modal_js = f"""
                function getModalInput(ph, isSelect=false, labelTxt='') {{
                   if (!isSelect) {{
                       const inputs = Array.from(document.querySelectorAll('input:not([type="hidden"])')).filter(el => el.getBoundingClientRect().width > 0);
                       const matched = inputs.filter(el => el.placeholder && el.placeholder.toLowerCase().includes(ph.toLowerCase()));
                       return matched.length > 0 ? matched[matched.length - 1] : null; 
                   }} else {{
                       const selects = Array.from(document.querySelectorAll('select')).filter(el => el.getBoundingClientRect().width > 0);
                       const labels = Array.from(document.querySelectorAll('*')).filter(el => el.innerText && el.innerText.includes(labelTxt) && el.children.length <= 1);
                       if (labels.length > 0) {{
                           const lastLabel = labels[labels.length - 1];
                           let p = lastLabel.parentElement;
                           for (let i=0; i<3 && p; i++) {{
                               const sel = p.querySelector('select');
                               if (sel && sel.getBoundingClientRect().width > 0) return sel;
                               p = p.parentElement;
                           }}
                       }}
                       return selects.length > 0 ? selects[selects.length - 1] : null;
                   }}
                }}
                
                if ('{key}' === 'name') return getModalInput('name', false);
                if ('{key}' === 'age') return getModalInput('age', false);
                if ('{key}' === 'relationship') return getModalInput('', true, 'Relationship');
                if ('{key}' === 'occupation') return getModalInput('occupation', false);
                if ('{key}' === 'is_earning') return getModalInput('', true, 'Is Earning');
                if ('{key}' === 'income') return getModalInput('monthly income', false);
                if ('{key}' === 'add_btn') return Array.from(document.querySelectorAll('button, a, input[type="submit"], input[type="button"]')).filter(el => (el.innerText && el.innerText.trim() === 'Add') || (el.value && el.value.trim() === 'Add')).filter(el => el.getBoundingClientRect().width > 0).pop();
                return null;
                """
                return driver.execute_script(modal_js)
            
            def fill_modal_field(key, tag_type, value):
                time.sleep(0.5) # Wait for previous field's Ajax
                el = get_modal_element(key)
                if not el: return
                try:
                    if tag_type == "text":
                        try:
                            el.clear()
                        except:
                            pass
                        try:
                            el.send_keys(value + Keys.TAB)
                        except:
                            print(f"   [WARN] Could not type into Modal {key} natively. Skipping.")
                    elif tag_type == "select":
                        select = Select(el)
                        found = False
                        for opt in select.options:
                            if value.lower() == opt.text.lower():
                                select.select_by_visible_text(opt.text)
                                found = True
                                break
                        if not found:
                            for opt in select.options:
                                if value.lower() in opt.text.lower():
                                    select.select_by_visible_text(opt.text)
                                    break
                    print(f"   [OK] Filled Modal {key} -> {value}")
                except Exception as e:
                    print(f"   [FAIL] Modal {key}: {e}")

            # Calculate age from DOB
            calculated_age = '30'
            if "dob" in data and "/" in data["dob"]:
                try:
                    parts = data["dob"].split("/")
                    if len(parts) == 3:
                        birth_year = int(parts[2])
                        current_year = 2026 
                        if 1900 < birth_year <= current_year:
                            calculated_age = str(current_year - birth_year)
                except:
                    pass

            fill_modal_field('name', 'text', data.get("name", "Self"))
            fill_modal_field('age', 'text', calculated_age)
            fill_modal_field('relationship', 'select', 'Self')
            fill_modal_field('occupation', 'text', 'Employed') # Changed to text
            fill_modal_field('is_earning', 'select', 'Yes')
            fill_modal_field('income', 'text', '20000')
            
            add_btn = get_modal_element('add_btn')
            if add_btn:
                try:
                    add_btn.click()
                    print("   [OK] Clicked 'Add' inside Modal")
                    
                    wait_and_click_yes(driver, "Income Details")
                    time.sleep(2.0)
                except:
                    print("   [WARN] Could not click 'Add' natively. Skipping.")
                
    except Exception as e:
        print(f"   [FAIL] Error processing modal: {e}")

    # 5. Click "Save & Proceed"
    print("\n[FILL] Submitting Form...")
    try:
        # Scroll to the bottom of the page first, as the button might only load/appear then
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2.0)
        
        # Poll for Save & Proceed button
        print("   [WAIT] Waiting for 'Save & Proceed' button to become visible...")
        clicked_save = False
        for _ in range(10): # Wait up to 5s
            time.sleep(0.5)
            save_btns = driver.find_elements(By.XPATH, "//button[contains(., 'Save & Proceed')] | //a[contains(., 'Save & Proceed')] | //input[contains(@value, 'Save & Proceed')]")
            for btn in reversed(save_btns):
                if btn.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", btn)
                    time.sleep(0.5)
                    try:
                        btn.click()
                        print("   [OK] Clicked 'Save & Proceed' natively")
                        clicked_save = True
                        break
                    except Exception:
                        try:
                            # Fallback: if a sticky footer or CSS intercepts the click, force it via JS
                            driver.execute_script("arguments[0].click();", btn)
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

    print("\n[DONE] Finished auto-filling form via Native Selenium!")
    print("\n[WAIT] Waiting 4 seconds for page to transition to Document Upload...")
    time.sleep(4.0)
    
    print("\n[LAUNCH] Automatically running Document Uploader...")
    import subprocess
    subprocess.run([sys.executable, "-m", "app.docgen.document_uploader"])

if __name__ == "__main__":
    main()
