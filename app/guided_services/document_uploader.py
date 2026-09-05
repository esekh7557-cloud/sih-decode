"""
JanSeva AI - Document Uploader (Edge / Selenium Mode)
"""

import os
import sys
import time
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
    'residence certificate': ['Residence Certificate', 'Domicile Certificate'],
    
    # Other
    'photograph': ['Photograph', 'Photo', 'Passport Size Photograph'],
    'income certificate': ['Income Certificate'],
    'caste certificate': ['Caste Certificate'],
    'affidavit': ['Affidavit'],
    'self declaration': ['Self Declaration'],
}

# `scan()` normalizes common filenames (for example, `aadharcard.png`), while
# citizens may upload files with spaces, dashes, or underscores. Match all of
# those forms to the label displayed by Goa Online.
_FILENAME_LABELS = {
    "birthcertificate": "Birth Certificate",
    "aadhaarcard": "Aadhaar Card",
    "aadharcard": "Aadhaar Card",
    "voterid": "Voter ID",
    "voteridcard": "Voter ID",
    "electioncard": "Election Card",
    "epic": "EPIC",
    "pancard": "PAN Card",
    "passport": "Passport",
    "rationcard": "Ration Card",
    "electricitybill": "Electricity Bill",
    "photograph": "Photograph",
    "photo": "Photo",
    "passportsizephotograph": "Passport Size Photograph",
    "incomecertificate": "Income Certificate",
    "residencecertificate": "Residence Certificate",
    "domicilecertificate": "Residence Certificate",
    "castecertificate": "Caste Certificate",
    "affidavit": "Affidavit",
    "selfdeclaration": "Self Declaration",
}

_PORTAL_ROW_ALIASES = {
    "Birth Certificate": ("birth certificate", "age proof"),
    "Aadhaar Card": ("aadhaar card", "aadhar card", "identity proof", "id proof"),
    "Voter ID": ("voter id", "voter id card", "identity proof", "id proof"),
    "PAN Card": ("pan card", "identity proof", "id proof"),
    "Passport": ("passport", "identity proof", "id proof"),
    "Photograph": ("photograph", "photo", "passport size photograph"),
    "Ration Card": ("ration card", "address proof"),
    "Electricity Bill": ("electricity bill", "address proof"),
    "Income Certificate": ("income certificate",),
    "Residence Certificate": ("residence certificate", "domicile certificate", "address proof"),
    "Caste Certificate": ("caste certificate",),
    "Affidavit": ("affidavit",),
    "Self Declaration": ("self declaration", "self-declaration"),
}


def _document_label_for_filename(file_path: Path) -> str | None:
    stem = "".join(character for character in file_path.stem.lower() if character.isalnum())
    return _FILENAME_LABELS.get(stem)


def _portal_row_aliases(label: str) -> tuple[str, ...]:
    """Return the document label plus category labels used by Goa Online."""
    return (label.lower(),) + _PORTAL_ROW_ALIASES.get(label, ())


def _matching_documents(data_folder: Path) -> list[tuple[str, str]]:
    """Return one current file for each portal document category.

    A citizen can scan the same Aadhaar card twice, often once as JPG and once
    as JPEG. Goa Online has one row for that category, so submitting both is
    not a valid "multiple document" upload. Keep the newest version and still
    upload every distinct document category.
    """
    newest_by_label: dict[str, Path] = {}
    for pattern in ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.pdf"):
        for file_path in data_folder.glob(pattern):
            matched_label = _document_label_for_filename(file_path)
            if not matched_label:
                print(f"  [SKIP] No match for: '{file_path.name}'")
                continue
            existing = newest_by_label.get(matched_label)
            if existing is None or file_path.stat().st_mtime >= existing.stat().st_mtime:
                newest_by_label[matched_label] = file_path

    matches = sorted(newest_by_label.items(), key=lambda entry: entry[0])
    for label, file_path in matches:
        print(f"  [OK] Matched: '{file_path.name}' -> '{label}'")
    return [(label, str(file_path.absolute())) for label, file_path in matches]


def upload_documents(folder: str | os.PathLike[str], port: int = 9222) -> dict[str, object]:
    """Upload the documents saved for one Saarthi session to the open portal."""
    data_folder = Path(folder)
    if not data_folder.exists():
        raise FileNotFoundError(f"Document folder not found: {data_folder}")

    print("=" * 60)
    print("  Saarthi -- Document Uploader (Edge Debugging Mode)")
    print("=" * 60)
    print(f"\n[SCAN] Scanning folder: {data_folder}")

    matches = _matching_documents(data_folder)

    if not matches:
        print("\n[INFO] No matching documents found. Exiting.")
        return {"found": 0, "uploaded": 0, "failed": 0}

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
        raise RuntimeError("Could not connect to Edge for document upload") from e

    # ---------------------------------------------------------
    # UPLOAD EXECUTION
    # ---------------------------------------------------------
    uploaded = 0
    failed = 0

    failures: list[str] = []
    for label, file_path in matches:
        print(f"\n[UPLOAD] Uploading: {label}")
        success = _upload_single_document(driver, label, file_path)
        
        if success:
            uploaded += 1
            print(f"   [OK] Uploaded successfully!")
        else:
            failed += 1
            failures.append(label)
            
        time.sleep(1.5)  # Pause between uploads

    print("\n" + "="*50)
    print(f"[SUMMARY] Upload: {uploaded} succeeded, {failed} failed out of {len(matches)} total")
    print("="*50)

    # Do NOT close the browser - user still needs it!
    print("\n[DONE] Browser left open for you to verify.")
    return {
        "found": len(matches),
        "uploaded": uploaded,
        "failed": failed,
        "failed_documents": failures,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Upload documents to Goa Online portal from a local folder"
    )
    parser.add_argument("--folder", "-f", required=True, help="Path to folder containing document images")
    parser.add_argument("--port", "-p", type=int, default=9222, help="Edge remote debugging port")
    args = parser.parse_args()
    upload_documents(args.folder, args.port)


def _upload_single_document(driver, label: str, file_path: str) -> bool:
    from selenium.webdriver.common.by import By

    # A completed upload can leave its modal in the DOM during the Wicket
    # Ajax transition. Do not click the next row while that overlay is still
    # active.
    _wait_for_modal(driver, visible=False, timeout=8)

    # -- 1. Find the Upload button for this document --
    click_result = driver.execute_script("""
        var labels = arguments[0];
        var rows = document.querySelectorAll('tr, .document-row, .upload-row, [data-document-row]');
        var bestButton = null;
        var bestScore = 0;
        for (var rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
            var row = rows[rowIndex];
            var rowText = row.textContent.trim().toLowerCase();
            var controls = row.querySelectorAll('button, a, input[type="button"], input[type="submit"]');
            var uploadBtn = null;
            for (var controlIndex = 0; controlIndex < controls.length; controlIndex += 1) {
                var control = controls[controlIndex];
                if (control.offsetWidth === 0 || control.offsetHeight === 0 || control.disabled) continue;
                var controlText = [
                    control.innerText, control.value, control.title, control.getAttribute('aria-label'),
                    control.getAttribute('data-original-title'), control.getAttribute('onclick'), control.getAttribute('href')
                ].filter(Boolean).join(' ').toLowerCase();
                if (control.getAttribute('data-toggle') === 'modal'
                    || /upload|attach|re-upload|reupload|replace/.test(controlText)) {
                    uploadBtn = control;
                    break;
                }
            }
            if (!uploadBtn) continue;
            var score = rowText.indexOf(labels[0]) !== -1 ? 2 : 0;
            if (!score) {
                for (var labelIndex = 1; labelIndex < labels.length; labelIndex += 1) {
                    if (rowText.indexOf(labels[labelIndex]) !== -1) {
                        score = 1;
                        break;
                    }
                }
            }
            if (score > bestScore) {
                bestButton = uploadBtn;
                bestScore = score;
            }
        }
        if (bestButton) {
            bestButton.click();
            return 'clicked';
        }
        return 'not_found';
    """, list(_portal_row_aliases(label)))

    if click_result != 'clicked':
        print(f"   [FAIL] Could not find Upload button for '{label}'")
        return False

    print(f"   -> Clicked Upload button, waiting for modal...")
    if not _wait_for_modal(driver, visible=True, timeout=8):
        print("   [FAIL] No active modal found")
        return False

    # -- 2. Find the file input inside the ACTIVE modal --
    try:
        active_modal = _active_modal(driver)
        if not active_modal:
            print("   [FAIL] No active modal found")
            return False

        file_inputs = active_modal.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
        if not file_inputs:
            # Some Goa Online variants mount the file control outside the modal
            # while keeping the modal as the visible upload dialog.
            file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
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

        file_input.send_keys(file_path)
        print(f"   -> File path sent: {os.path.basename(file_path)}")

        # Keep the input usable until the onchange/Ajax handler has had time to
        # receive the selected file, then restore the portal's original style.
        time.sleep(1)
        driver.execute_script("arguments[0].setAttribute('style', arguments[1]);", file_input, original_style)
        time.sleep(2)

    except Exception as e:
        print(f"   [FAIL] Error finding/using file input: {e}")
        _close_modal(driver)
        return False

    # -- 3. Click Save/Submit in the modal --
    try:
        save_btn = driver.execute_script("""
            const modal = [...document.querySelectorAll('.modal')]
                .find((candidate) => {
                    const style = window.getComputedStyle(candidate);
                    return style.display !== 'none' && candidate.offsetWidth > 0 && candidate.offsetHeight > 0;
                });
            if (!modal) return null;

            const buttons = modal.querySelectorAll('button, input[type="button"], input[type="submit"], a, [role="button"]');
            for (const btn of buttons) {
                if (btn.offsetWidth === 0 || btn.offsetHeight === 0) continue;
                const text = (btn.innerText || btn.value || '').toLowerCase().trim();
                if ((text.includes('save') || text.includes('submit') || text === 'upload' || text.includes('ok'))
                    && text !== 'x' && !btn.classList.contains('close')) {
                    return btn;
                }
            }
            return null;
        """)

        if not save_btn:
            print(f"   [FAIL] Could not find Save/Submit button")
            _close_modal(driver)
            return False

        print(f"   -> Clicked Save/Submit button")
        driver.execute_script("arguments[0].click();", save_btn)
        time.sleep(3)

    except Exception as e:
        print(f"   [FAIL] Error clicking Save: {e}")
        _close_modal(driver)
        return False

    # Wait for the portal's Ajax response and modal transition before the next
    # document row is touched. If it remains open, close it and verify closure.
    if not _wait_for_modal(driver, visible=False, timeout=8):
        _close_modal(driver)
        _wait_for_modal(driver, visible=False, timeout=3)
    return True


def _active_modal(driver):
    return driver.execute_script("""
        return [...document.querySelectorAll('.modal')]
            .find((candidate) => {
                const style = window.getComputedStyle(candidate);
                return style.display !== 'none' && candidate.offsetWidth > 0 && candidate.offsetHeight > 0;
            }) || null;
    """)


def _wait_for_modal(driver, *, visible: bool, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            is_visible = _active_modal(driver) is not None
            if is_visible == visible:
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def _close_modal(driver):
    """Try to close any open modals if something failed."""
    try:
        driver.execute_script("""
            const modal = [...document.querySelectorAll('.modal')]
                .find((candidate) => {
                    const style = window.getComputedStyle(candidate);
                    return style.display !== 'none' && candidate.offsetWidth > 0 && candidate.offsetHeight > 0;
                });
            const closeBtn = modal && modal.querySelector('.close, [data-dismiss="modal"]');
            if (closeBtn) closeBtn.click();
        """)
        time.sleep(1)
    except:
        pass


if __name__ == "__main__":
    main()
