"""
Saarthi - Document Uploader (Edge / Selenium Mode)
"""

import os
import sys
import time
import argparse
from pathlib import Path

# -- Document category mapping ------------------------------------------------
DOCUMENT_MAP = {
    # Age Proof
    'birth certificate': ['Birth Certificate'],
    
    # Identify Proof
    'aadhaar card': ['Aadhaar Card', 'Aadhar Card'],
    'voter id': ['Voter ID', 'Election Card', 'EPIC'],
    'pan card': ['PAN Card'],
    'passport': ['Passport'],
    
    # Address Proof
    'ration card': ['Ration Card'],
    'electricity bill': ['Electricity Bill'],
    
    # Other
    'photograph': ['Photograph', 'Photo', 'Passport Size Photograph'],
    'income certificate': ['Income Certificate'],
    'caste certificate': ['Caste Certificate'],
    'affidavit': ['Affidavit'],
    'self declaration': ['Self Declaration'],
}


def upload_documents(folder: str, port: int = 9222):
    data_folder = Path(folder)
    if not data_folder.exists():
        print(f"[ERROR] Folder not found: {data_folder}")
        sys.exit(1)

    print("=" * 60)
    print("  Saarthi -- Document Uploader (Edge Debugging Mode)")
    print("=" * 60)
    print(f"\n[SCAN] Scanning folder: {data_folder}")

    # Find matches
    matches = []
    for ext in ['*.jpg', '*.jpeg', '*.png', '*.pdf']:
        for file_path in data_folder.glob(ext):
            stem = file_path.stem.lower().strip().replace(" ", "").replace("_", "")
            
            matched_labels = []
            for key, labels in DOCUMENT_MAP.items():
                clean_key = key.replace(" ", "").replace("_", "")
                clean_aliases = [l.lower().replace(" ", "").replace("_", "") for l in labels]
                
                if clean_key == stem or stem in clean_aliases or clean_key in stem:
                    for lbl in labels:
                        if lbl not in matched_labels:
                            matched_labels.append(lbl)
            
            if matched_labels:
                print(f"  [OK] Matched: '{file_path.name}' -> {matched_labels}")
                matches.append((matched_labels, str(file_path.absolute())))
            else:
                print(f"  [SKIP] No match for: '{file_path.name}'")

    if not matches:
        print("\n[INFO] No matching documents found. Exiting.")
        sys.exit(0)

    print(f"\n[INFO] Found {len(matches)} document(s) to upload:")
    for label, path in matches:
        print(f"   - {label} -> {os.path.basename(path)}")

    # ---------------------------------------------------------
    # SELENIUM SETUP
    # ---------------------------------------------------------
    print(f"\n[CONNECT] Connecting to Edge on port {port}...")
    
    from selenium import webdriver
    from selenium.webdriver.edge.options import Options

    edge_options = Options()
    # This tells Selenium to attach to the ALREADY RUNNING Edge browser
    edge_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")

    try:
        driver = webdriver.Edge(options=edge_options)
        
        from selenium.webdriver.common.by import By
        # Ensure we are on the correct tab (Goa Online)
        for handle in driver.window_handles:
            driver.switch_to.window(handle)
            if "goaonline" in driver.current_url.lower() or "goa" in driver.title.lower():
                break
                
        print(f"   [OK] Connected! Current page: {driver.title}")
    except Exception as e:
        print(f"\n[ERROR] Could not connect to Edge!")
        print(f"   Make sure you started Edge with:")
        print(f"   msedge.exe --remote-debugging-port={port} --user-data-dir=\"C:\\Users\\Vedant\\Desktop\\edge-debug-profile\"")
        sys.exit(1)

    # ---------------------------------------------------------
    # UPLOAD EXECUTION
    # ---------------------------------------------------------
    uploaded = 0
    failed = 0

    for labels, file_path in matches:
        for label in labels:
            print(f"\n[UPLOAD] Checking slots for: {label} using {os.path.basename(file_path)}")
            attempts = 0
            while attempts < 3: # Max 3 uploads per label to avoid infinite loops
                success = _upload_single_document(driver, label, file_path)
                
                if success:
                    uploaded += 1
                    print(f"   [OK] Uploaded successfully to a slot for '{label}'!")
                    time.sleep(1.5)
                else:
                    break # No more slots found or failed
                attempts += 1

    print("\n" + "="*50)
    print(f"[SUMMARY] Upload: {uploaded} succeeded, {failed} failed out of {len(matches)} total")
    print("="*50)

    # Do NOT close the browser - user still needs it!
    print("\n[DONE] Browser left open for you to verify.")


def _upload_single_document(driver, label: str, file_path: str) -> bool:
    from selenium.webdriver.common.by import By

    # -- 1. Find the Upload button for this document --
    click_result = driver.execute_script("""
        const label = arguments[0];
        const rows = document.querySelectorAll('tr');
        for (const row of rows) {
            const textContent = row.textContent.toLowerCase();
            if (textContent.includes(label.toLowerCase())) {
                // Check if it already has an uploaded document
                const hasUploaded = row.querySelector('a[title*="View"], a[title*="Delete"], i.fa-trash, i.fa-eye, a[title*="Download"]');
                if (hasUploaded) {
                    continue; // Skip this row, already uploaded
                }
                
                const uploadBtn = row.querySelector('button[data-toggle="modal"], a[data-toggle="modal"]');
                if (uploadBtn) {
                    uploadBtn.click();
                    return 'clicked';
                }
            }
        }
        return 'not_found';
    """, label)

    if click_result != 'clicked':
        print(f"   [FAIL] Could not find Upload button for '{label}'")
        return False

    print(f"   -> Clicked Upload button, waiting for modal...")
    time.sleep(2)  # Wait for modal animation

    # -- 2. Find the file input inside the ACTIVE modal --
    try:
        active_modal = driver.execute_script("""
            return document.querySelector('.modal.fade.in, .modal.show, .modal[style*="display: block"]');
        """)

        if not active_modal:
            print("   [FAIL] No active modal found")
            return False

        file_inputs = active_modal.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
        if not file_inputs:
            time.sleep(2)
            file_inputs = active_modal.find_elements(By.CSS_SELECTOR, 'input[type="file"]')

        if not file_inputs:
            print(f"   [FAIL] No file input found inside the active modal")
            _close_modal(driver)
            return False

        file_input = file_inputs[0]

        # Save original style and make it interactable
        original_style = driver.execute_script("return arguments[0].getAttribute('style');", file_input) or ""
        driver.execute_script("""
            arguments[0].style.display = 'block';
            arguments[0].style.visibility = 'visible';
            arguments[0].style.opacity = '1';
        """, file_input)

        time.sleep(0.5)

        # -- 3. Send the file path --
        file_input.send_keys(file_path)
        print(f"   -> File path sent: {os.path.basename(file_path)}")
        
        # Revert style back to exactly what it was before so Wicket doesn't crash
        driver.execute_script("arguments[0].setAttribute('style', arguments[1]);", file_input, original_style)
        
        # IMPORTANT: Wait longer after file selection so Wicket's background Ajax finishes!
        time.sleep(3)

    except Exception as e:
        print(f"   [FAIL] Error finding/using file input: {e}")
        _close_modal(driver)
        return False

    # -- 4. Click Save/Submit in the modal --
    try:
        save_btn = driver.execute_script("""
            const modal = document.querySelector('.modal.fade.in, .modal.show, .modal[style*="display: block"]');
            if (!modal) return null;

            const buttons = modal.querySelectorAll('button, input[type="button"], input[type="submit"], a.btn');
            for (const btn of buttons) {
                // Skip hidden buttons! This is critical for Wicket Modals
                if (btn.offsetWidth === 0 && btn.offsetHeight === 0) continue;

                const text = (btn.innerText || btn.value || '').toLowerCase().trim();
                if (text.includes('save') || text.includes('submit') || text === 'upload' || text.includes('ok')) {
                    if (text === 'x' || btn.classList.contains('close')) continue;
                    return btn;
                }
            }
            return null;
        """)

        if save_btn:
            print(f"   -> Clicked Save/Submit button")
            save_btn.click()
        else:
            print(f"   [WARN] Could not find Save button")

        time.sleep(4)  # Wait for upload to complete

    except Exception as e:
        print(f"   [WARN] Error clicking Save: {e}")

    _close_modal(driver)
    return True


def _close_modal(driver):
    """Try to close any open modals if something failed."""
    try:
        driver.execute_script("""
            const closeBtn = document.querySelector('.modal.show .close, .modal.fade.in .close');
            if (closeBtn) closeBtn.click();
        """)
        time.sleep(1)
    except:
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Upload documents to Goa Online portal from a local folder"
    )
    parser.add_argument(
        "--folder", "-f",
        default=r"C:\Users\Vedant\Desktop\data",
        help="Path to folder containing document images"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=9222,
        help="Chrome remote debugging port"
    )
    args = parser.parse_args()
    upload_documents(args.folder, args.port)

if __name__ == "__main__":
    main()

