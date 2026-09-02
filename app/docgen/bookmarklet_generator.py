import json
import re

def generate_autofill_bookmarklet(user_data: dict) -> str:
    """Generate the exact JavaScript bookmarklet for government portal auto-fill."""
    # Ensure all extracted fields have values or sensible defaults
    gender = (user_data.get("gender") or "male").lower()
    title = user_data.get("title") or ("Mr." if gender == "male" else "Mrs.")
    name = user_data.get("name") or ""
    dob = user_data.get("dob") or ""
    aadhaar_num = user_data.get("aadhaar_number") or user_data.get("aadhaar") or user_data.get("id_proof_no") or ""
    clean_aadhaar = str(aadhaar_num).replace(" ", "").strip()
    
    village = user_data.get("village") or ""
    taluka = user_data.get("taluka") or ""
    district = user_data.get("district") or ""
    state = user_data.get("state") or ""
    pincode = user_data.get("pincode") or ""
    address = user_data.get("address") or ""
    locality = user_data.get("locality") or village or taluka or district or ""

    clean_data = {
        "applying_for": user_data.get("applying_for") or "Self",
        "purpose": user_data.get("purpose") or "economically weaker section",
        "residence_period": int(user_data["residence_period"]) if str(user_data.get("residence_period", "")).isdigit() else (user_data.get("residence_period") or 15),
        "title": title,
        "name": name,
        "place_of_birth": user_data.get("place_of_birth") or village or taluka or district or "",
        "dob": dob,
        "gender": gender,
        "marital_status": user_data.get("marital_status") or "Married",
        "guardian_relation": user_data.get("guardian_relation") or "Father",
        "father_name": user_data.get("father_name") or "",
        "mobile": user_data.get("mobile") or "9876543210",
        "email": user_data.get("email") or (f"{re.sub(r'[^a-zA-Z0-9]', '', name).lower()}@example.com" if name else "applicant@example.com"),
        "occupation": user_data.get("occupation") or "employed",
        "caste_category": user_data.get("caste_category") or "GENERAL",
        "address": address,
        "locality": locality,
        "district": district,
        "taluka": taluka,
        "village": village,
        "pincode": pincode,
        "family_size": int(user_data["family_size"]) if str(user_data.get("family_size", "")).isdigit() else (user_data.get("family_size") or 4),
        "earning_members": int(user_data["earning_members"]) if str(user_data.get("earning_members", "")).isdigit() else (user_data.get("earning_members") or 1),
        "children_count": int(user_data["children_count"]) if str(user_data.get("children_count", "")).isdigit() else (user_data.get("children_count") or 2),
        "previous_certificate": user_data.get("previous_certificate") or "No",
        "immovable_property": user_data.get("immovable_property") or "no",
        "property_value": str(user_data.get("property_value") or "0"),
        "other_income": str(user_data.get("other_income") or "0"),
        "part_no": str(user_data.get("part_no") or "12"),
        "serial_no": str(user_data.get("serial_no") or "345"),
        "electoral_year": str(user_data.get("electoral_year") or "2023"),
        "constituency": user_data.get("constituency") or taluka or district or "",
        "ration_card": user_data.get("ration_card") or "RC1234567",
        "property_details": user_data.get("property_details") or "None",
        "id_proof_type": user_data.get("id_proof_type") or "aadhaar card",
        "id_proof_no": clean_aadhaar or user_data.get("id_proof_no") or "",
        "certify": user_data.get("certify") or "click it"
    }

    data_json = json.dumps(clean_data, indent=4)
    
    bookmarklet = f'''javascript:(async function(){{
  // 1. Updated Sample Data matching your exact overrides
  const data = {{
    "applying_for": "Self",
    "purpose": "economically weaker section",
    "residence_period": 15,
    "title": "Mr.",
    "name": "Rahul Sharma",
    "place_of_birth": "Panaji",
    "dob": "15/08/1990",
    "gender": "male",
    "marital_status": "Married",
    "guardian_relation": "Father",
    "father_name": "Ramesh Kumar",  
    "mobile": "9876543210",
    "email": "rahul.sharma@example.com",
    "occupation": "employed", 
    "caste_category": "GENERAL",
    "address": "Flat 4B, Sunshine Apartments",
    "locality": "Market Area",
    "district": "North Goa",
    "taluka": "Tiswadi",
    "village": "Panaji",
    "pincode": "403001",
    "family_size": 4,
    "earning_members": 1, // Updated to 1
    "children_count": 2,
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
    "certify": "click it" 
  }};
  
  // 2. Updated Field Label Mapping
  const labelMapping = {{
    'applying_for': ['Applying for'],
    'purpose': ['Purpose'],
    'residence_period': ['Residence Period', 'Residence Period*'],
    'title': ['Title'],
    'name': ['Name of the applicant', 'Applicant Name'],
    'place_of_birth': ['Place of Birth'],
    'dob': ['Date of birth', 'DOB'],
    'gender': ['Gender'],
    'marital_status': ['Marital Status'],
    'guardian_relation': ['Father/Husband/Wife/Guardian'],
    'father_name': ["Father's/Husband's", "Father Name", "Father's Name"],
    'mobile': ['Mobile No'],
    'email': ['Email ID'],
    'occupation': ['Occupational Status', 'Occupation'], 
    'caste_category': ['Caste category'],
    'address': ['House/Flat No'],
    'locality': ['Locality/Area/Ward'],
    'district': ['District'],
    'taluka': ['Taluka'],
    'village': ['Village/City'],
    'pincode': ['Pincode'],
    'family_size': ['Total Family Members'],
    'earning_members': ['Total earning members', 'Total earning members in family*'],
    'children_count': ['Total No. of Children'],
    'previous_certificate': ['Any Income certificate was issued'],
    'immovable_property': ['Any immovable property', 'Any immovable property?'], 
    'property_value': ['Property Value'],
    'other_income': ['Any income from other sources'],
    'part_no': ['Part No.'],
    'serial_no': ['Serial No.'],
    'electoral_year': ['Electoral Roll Year'],
    'constituency': ['Constituency'],
    'ration_card': ['Ration Card No.'],
    'property_details': ['Property Details'],
    'id_proof_type': ['ID Proof', 'Select ID Proof', 'ID Proof*'], 
    'id_proof_no': ['ID Proof No.', 'ID Proof No', 'ID Proof Number', 'ID Proof No.*'], 
    'certify': ['I hereby certify that', 'certify that, the above mentioned information'] 
  }};

  // 3. Query Function: Find Inputs by Labels
  function findInputByLabel(labelTexts) {{
    const labels = Array.from(document.querySelectorAll('label'));
    for (const label of labels) {{
      if (labelTexts.some(text => label.innerText && label.innerText.toLowerCase().includes(text.toLowerCase()))) {{
        if (label.htmlFor) {{
          const input = document.getElementById(label.htmlFor);
          if (input) return input;
        }}
        const inputInside = label.querySelector('input:not([type="hidden"]), select, textarea');
        if (inputInside) return inputInside;
        
        let next = label.nextElementSibling;
        for(let i=0; i<3 && next; i++) {{
          const input = next.querySelector('input:not([type="hidden"]), select, textarea');
          if (input) return input;
          if (['INPUT', 'SELECT', 'TEXTAREA'].includes(next.tagName) && next.type !== 'hidden') return next;
          next = next.nextElementSibling;
        }}
      }}
    }}

    const textNodes = Array.from(document.querySelectorAll('span, div, td, th, p, h1, h2, h3, h4, h5, h6'));
    for (const node of textNodes) {{
      if (node.children.length > 2) continue;
      if (labelTexts.some(text => node.innerText && node.innerText.toLowerCase().trim() === text.toLowerCase().trim() || node.innerText.toLowerCase().includes(text.toLowerCase()))) {{
        const inputInside = node.querySelector('input:not([type="hidden"]), select, textarea');
        if (inputInside) return inputInside;
        
        let next = node.nextElementSibling;
        for(let i=0; i<3 && next; i++) {{
          const input = next.querySelector('input:not([type="hidden"]), select, textarea');
          if (input) return input;
          if (['INPUT', 'SELECT', 'TEXTAREA'].includes(next.tagName) && next.type !== 'hidden') return next;
          next = next.nextElementSibling;
        }}
      }}
    }}
    
    const inputs = Array.from(document.querySelectorAll('input:not([type="hidden"]), select, textarea'));
    for (const input of inputs) {{
      const placeholder = input.placeholder || '';
      const name = input.name || '';
      const id = input.id || '';
      if (labelTexts.some(text => 
        placeholder.toLowerCase().includes(text.toLowerCase()) ||
        name.toLowerCase().replace(/_/g, ' ').includes(text.toLowerCase()) ||
        id.toLowerCase().replace(/_/g, ' ').includes(text.toLowerCase())
      )) {{
        return input;
      }}
    }}
    return null;
  }}

  // 4. Value Setter Function (Framework Bypass & Checkbox overrides)
  function setNativeValue(element, value) {{
    if (!element) return;
    
    element.style.border = "3px solid red";
    element.style.backgroundColor = "#ffcccc";

    if (element.tagName.toLowerCase() === 'select') {{
      let optionFound = false;
      for (let i = 0; i < element.options.length; i++) {{
        const optText = element.options[i].text.toLowerCase().trim();
        const optVal = element.options[i].value.toLowerCase().trim();
        const searchVal = value.toString().toLowerCase().trim();
        
        if (optText === searchVal || optVal === searchVal) {{
          element.selectedIndex = i;
          element.value = element.options[i].value; 
          optionFound = true;
          break;
        }}
      }}
      if (!optionFound) {{
        for (let i = 0; i < element.options.length; i++) {{
          if (element.options[i].text.toLowerCase().includes(value.toString().toLowerCase().trim())) {{
            element.selectedIndex = i;
            element.value = element.options[i].value;
            optionFound = true;
            break;
          }}
        }}
      }}
      if (!optionFound) {{
        element.value = value;
      }}
    }} else if (element.type === 'radio' || element.type === 'checkbox') {{
      const valStr = value.toString().toLowerCase().trim();
      const clickTriggers = ['true', 'yes', 'self', 'click it', 'checked', 'on', '1'];
      
      if (value === true || clickTriggers.includes(valStr)) {{
        if (!element.checked) {{
          element.click();
          if (!element.checked) {{
            element.checked = true;
          }}
        }}
      }}
    }} else {{
      try {{
        const valueSetter = Object.getOwnPropertyDescriptor(element, 'value').set;
        const prototype = Object.getPrototypeOf(element);
        const prototypeValueSetter = Object.getOwnPropertyDescriptor(prototype, 'value').set;
        
        if (valueSetter && valueSetter !== prototypeValueSetter) {{
          prototypeValueSetter.call(element, value);
        }} else {{
          valueSetter.call(element, value);
        }}
      }} catch (e) {{
        element.value = value;
      }}
      element.setAttribute("value", value);
    }}

    try {{ element.dispatchEvent(new Event('focus', {{ bubbles: true }})); }} catch(e){{}}
    try {{ element.dispatchEvent(new Event('input', {{ bubbles: true }})); }} catch(e){{}}
    try {{ element.dispatchEvent(new Event('change', {{ bubbles: true }})); }} catch(e){{}}
    try {{ element.dispatchEvent(new Event('blur', {{ bubbles: true }})); }} catch(e){{}}
    
    // Wicket heavily uses jQuery. Native dispatchEvent often fails to trigger jQuery listeners.
    try {{
        if (typeof jQuery !== 'undefined') {{
            jQuery(element).trigger('change');
            jQuery(element).trigger('input');
            jQuery(element).trigger('blur');
        }}
    }} catch(e) {{}}
  }}

  // 5. Execution Loop
  const delay = ms => new Promise(res => setTimeout(res, ms));

  let filledCount = 0;
  console.log("--- JanSeva AI Auto-fill Starting ---");
  for (const [key, labelTexts] of Object.entries(labelMapping)) {{
    if (data[key] === undefined || data[key] === null || data[key] === '') continue;
    
    const el = findInputByLabel(labelTexts);
    if (el) {{
      console.log("Found match for:", key, "-> filling with:", data[key]);
      setNativeValue(el, data[key]);
      filledCount++;
      await delay(2000); // 2.0s DELAY ADDED HERE 
    }} else {{
      console.log("Could NOT find input for:", key);
    }}
  }}

  // 6. Custom Workflows (Income Certificate Modal & Submit)
  console.log("--- Executing Custom Workflows ---");
  
  // A. Add New Family Member (Income Details)
  const addNewBtn = Array.from(document.querySelectorAll('button, a')).find(el => el.innerText && el.innerText.includes('Add New'));
  if (addNewBtn) {{
    console.log("Found '+ Add New' button. Clicking...");
    addNewBtn.click();
    await delay(1500); // Wait for modal animation
    
    // Calculate age
    let age = '30';
    if (data.dob && data.dob.includes('/')) {{
       const parts = data.dob.split('/');
       if (parts.length === 3) {{
          const birthYear = parseInt(parts[2], 10);
          const currentYear = new Date().getFullYear();
          if (birthYear > 1900 && birthYear <= currentYear) age = (currentYear - birthYear).toString();
       }}
    }}

    function getModalInput(ph, isSelect=false, labelTxt='') {{
       if (!isSelect) {{
           const inputs = Array.from(document.querySelectorAll('input:not([type="hidden"])')).filter(el => el.getBoundingClientRect().width > 0);
           const matched = inputs.filter(el => el.placeholder && el.placeholder.toLowerCase().includes(ph.toLowerCase()));
           return matched[matched.length - 1]; // Return the last matching visible input
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
           return selects[selects.length - 1]; // fallback to last visible select
       }}
    }}

    const mName = getModalInput('name', false);
    if (mName) {{ setNativeValue(mName, data.name || 'Self'); await delay(2000); }}
    
    const mAge = getModalInput('age', false);
    if (mAge) {{ setNativeValue(mAge, age); await delay(2000); }}
    
    const mRel = getModalInput('', true, 'Relationship');
    if (mRel) {{ setNativeValue(mRel, 'Self'); await delay(2000); }}
    
    const mOcc = getModalInput('occupation', false);
    if (mOcc) {{ setNativeValue(mOcc, data.occupation || 'Employed'); await delay(2000); }}
    
    const mEarn = getModalInput('', true, 'Is Earning');
    if (mEarn) {{ setNativeValue(mEarn, 'Yes'); await delay(2000); }}
    
    const mInc = getModalInput('monthly income', false);
    if (mInc) {{ setNativeValue(mInc, '20000'); await delay(2000); }}
    
    // Click 'Add' inside modal
    const addBtn = Array.from(document.querySelectorAll('button, a')).filter(el => el.innerText && el.innerText.trim() === 'Add' && el.getBoundingClientRect().width > 0);
    if (addBtn.length > 0) {{
       console.log("Clicking 'Add' in modal...");
       addBtn[addBtn.length - 1].click();
       await delay(1500); // Wait for modal to close
    }}
  }}

  // B. Ensure Certify Checkbox is checked (fallback if standard loop missed it)
  const textNodesForCertify = Array.from(document.querySelectorAll('*')).filter(el => el.innerText && el.innerText.includes('I hereby certify that'));
  if (textNodesForCertify.length > 0) {{
      const node = textNodesForCertify[textNodesForCertify.length - 1];
      const cb = node.querySelector('input[type="checkbox"]');
      if (cb && !cb.checked) {{
          setNativeValue(cb, true);
      }} else {{
          // Check previous siblings
          let prev = node.previousElementSibling;
          if (prev && prev.tagName.toLowerCase() === 'input' && prev.type === 'checkbox' && !prev.checked) {{
              setNativeValue(prev, true);
          }}
      }}
  }}

  // C. (REMOVED) We no longer automatically click "Save & Proceed". 
  // Clicking it too fast via JavaScript interrupts Wicket's background Ajax calls, 
  // which corrupts the application state and causes the Document Upload to fail!
  
  alert("JanSeva AI Auto-fill Complete!\\nFilled " + filledCount + " fields.\\n\\nPLEASE WAIT 3 SECONDS before manually clicking 'Save & Proceed' to allow the server to register the data.");
}})();
'''
    return bookmarklet
