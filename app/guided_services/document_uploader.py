"""
JanSeva AI - Document Uploader (Edge / Selenium Mode)
"""

import os
import sys
import time
from pathlib import Path


def document_source_directory(session_id: str | None = None) -> Path:
    """Choose the current session's documents before a shared library.

    ``JANSEVA_DOCUMENT_SOURCE_DIR`` is an explicit portable override. Otherwise
    a current session must use its own scanned files; a shared OneDrive library
    is only a fallback for the legacy standalone uploader.
    """
    configured = os.getenv("JANSEVA_DOCUMENT_SOURCE_DIR")
    if configured:
        return Path(configured).expanduser()

    if session_id:
        session_scans = Path.cwd() / "scans" / session_id
        if session_scans.is_dir():
            return session_scans

    shared_library = Path.home() / "OneDrive" / "Pictures" / "doc"
    if shared_library.is_dir():
        return shared_library

    return Path.cwd() / "scans" / (session_id or "")

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

# Each section below needs one supporting document.  The source document may
# have a more specific name (for example Aadhaar Card), while Goa Online may
# show only the section name (for example Identity Proof).
REQUIRED_DOCUMENT_SECTIONS = {
    "Affidavit on stamp paper": ("Affidavit",),
    "Age Proof": ("Birth Certificate", "Aadhaar Card", "Voter ID", "Passport"),
    "Identity Proof": ("Aadhaar Card", "Voter ID", "PAN Card", "Passport"),
    "Photograph": ("Photograph", "Photo", "Passport Size Photograph"),
    "Residence Proof": ("Ration Card", "Electricity Bill", "Residence Certificate"),
}

# Upload jobs are organised by the portal requirement, rather than by source
# file.  This is important because Goa Online can ask for the same file in
# two distinct sections (for example, Aadhaar for both Age Proof and Identity
# Proof).  A file is therefore allowed to appear in more than one job.
SECTION_UPLOAD_REQUIREMENTS = (
    (
        "Affidavit on a stamp paper",
        ("Affidavit",),
        ("affidavit on a stamp paper", "affidavit"),
    ),
    (
        "Age Proof",
        ("Birth Certificate", "Aadhaar Card", "Voter ID", "Passport"),
        ("age proof", "birth certificate", "passing certificate", "passport copy", "aadhaar card"),
    ),
    (
        "Identity Proof",
        ("Aadhaar Card", "Voter ID", "PAN Card", "Passport"),
        ("identity proof", "aadhaar card", "voter id", "pan card", "passport copy"),
    ),
    (
        "Photograph",
        ("Photograph", "Photo", "Passport Size Photograph"),
        ("photograph", "photo", "passport size photograph"),
    ),
    (
        "Residence Proof",
        ("Residence Certificate", "Ration Card", "Electricity Bill"),
        ("residence proof", "residence certificate", "domicile certificate", "ration card", "electricity bill"),
    ),
)

# Goa Online can list the same named document in more than one requirement
# section.  For example, Aadhaar may be offered as an age proof and as an
# identity proof.  Prefer the section where the document is normally needed,
# while still accepting portals that do not show section headings.
_PREFERRED_PORTAL_SECTIONS = {
    "Birth Certificate": "age proof",
    "Aadhaar Card": "identity proof",
    "Voter ID": "identity proof",
    "PAN Card": "identity proof",
    "Passport": "identity proof",
    "Ration Card": "residence proof",
    "Electricity Bill": "residence proof",
    "Residence Certificate": "residence proof",
    "Affidavit": "affidavit",
    "Photograph": "photograph",
    "Photo": "photograph",
    "Passport Size Photograph": "photograph",
}


def _document_label_for_filename(file_path: Path) -> str | None:
    stem = "".join(character for character in file_path.stem.lower() if character.isalnum())
    exact_match = _FILENAME_LABELS.get(stem)
    if exact_match:
        return exact_match

    # Citizens commonly add descriptive text such as "PAN card - ID proof"
    # or "Affidavit on a stamp paper".  Match these safely to their portal
    # category instead of requiring a filename rename.
    for token, label in (
        ("affidavitonastamppaper", "Affidavit"),
        ("affidavitonstamppaper", "Affidavit"),
        ("ageproof", "Birth Certificate"),
        ("identityproof", "Aadhaar Card"),
        ("residenceproof", "Residence Certificate"),
        ("birthcertificate", "Birth Certificate"),
        ("aadhar", "Aadhaar Card"),
        ("aadhaar", "Aadhaar Card"),
        ("pancard", "PAN Card"),
        ("voter", "Voter ID"),
        ("passport", "Passport"),
        ("ration", "Ration Card"),
        ("electricity", "Electricity Bill"),
        ("residence", "Residence Certificate"),
        ("domicile", "Residence Certificate"),
        ("photograph", "Photograph"),
        ("photo", "Photograph"),
        ("income", "Income Certificate"),
        ("caste", "Caste Certificate"),
        ("affidavit", "Affidavit"),
        ("selfdeclaration", "Self Declaration"),
    ):
        if token in stem:
            return label
    return None


def _portal_row_aliases(label: str) -> tuple[str, ...]:
    """Return the document label plus category labels used by Goa Online."""
    return (label.lower(),) + _PORTAL_ROW_ALIASES.get(label, ())


def _specific_portal_row_aliases(label: str) -> tuple[str, ...]:
    """Return only the portal row names that identify this exact document."""
    return {
        "Aadhaar Card": ("aadhaar card", "aadhar card"),
        "Voter ID": ("voter id", "voter id card"),
        "PAN Card": ("pan card", "pan card - id proof"),
        "Passport": ("passport copy", "passport"),
        "Residence Certificate": ("residence certificate", "domicile certificate"),
        "Photograph": ("photograph",),
        "Photo": ("photo",),
        "Passport Size Photograph": ("passport size photograph",),
        "Affidavit": ("affidavit on a stamp paper", "affidavit"),
    }.get(label, (label.lower(),))


def missing_required_sections(matches: list[tuple[str, str]]) -> list[str]:
    """Return required portal sections that have no eligible local document."""
    labels = {label for label, _ in matches}
    return [
        section
        for section, accepted_labels in REQUIRED_DOCUMENT_SECTIONS.items()
        if not labels.intersection(accepted_labels)
    ]


def _section_upload_plan(matches: list[tuple[str, str]]) -> list[tuple[str, str, str, tuple[str, ...]]]:
    """Choose one local document for every required portal section.

    The same path can deliberately occur more than once.  For example, when
    Birth Certificate is absent, Aadhaar is eligible for Age Proof and will
    still be selected again for Identity Proof.
    """
    path_by_label = {label: path for label, path in matches}
    plan: list[tuple[str, str, str, tuple[str, ...]]] = []
    for section, accepted_labels, row_aliases in SECTION_UPLOAD_REQUIREMENTS:
        selected_label = next(
            (label for label in accepted_labels if label in path_by_label),
            None,
        )
        if selected_label:
            plan.append((section, selected_label, path_by_label[selected_label], row_aliases))
    return plan


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

    missing_sections = missing_required_sections(matches)
    if missing_sections:
        print("\n[ERROR] One document is required for each portal section.")
        for section in missing_sections:
            print(f"   [MISSING] {section}")
        return {
            "found": len(matches),
            "planned": 0,
            "uploaded": 0,
            "failed": len(missing_sections),
            "failed_documents": missing_sections,
        }

    upload_plan = _section_upload_plan(matches)

    print(f"\n[INFO] Found {len(matches)} local document(s):")
    for label, path in matches:
        print(f"   - {label} -> {os.path.basename(path)}")
    print(f"\n[PLAN] One upload for each of {len(upload_plan)} required portal sections:")
    for section, label, path, _ in upload_plan:
        print(f"   - {section} <- {label} ({os.path.basename(path)})")

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
        # Attaching with Selenium still requires a matching EdgeDriver.  When
        # that binary is unavailable, Playwright can attach directly over the
        # already-open Chrome DevTools connection and preserve the same tab.
        print("   [INFO] Selenium EdgeDriver is unavailable; using the open browser connection directly.")
        return _upload_documents_with_playwright(upload_plan, port, len(matches))

    # ---------------------------------------------------------
    # UPLOAD EXECUTION
    # ---------------------------------------------------------
    uploaded = 0
    failed = 0
    skipped = 0
    failures: list[str] = []
    skipped_documents: list[str] = []
    skipped_details: dict[str, str] = {}
    failure_details: dict[str, str] = {}
    used_portal_rows: set[str] = set()
    for section, label, file_path, row_aliases in upload_plan:
        print(f"\n[UPLOAD] {section} <- {label}")
        outcome = "failed"
        reason = "The upload did not start."
        # The portal rebuilds its document panel after an Ajax request.  A
        # short retry prevents a temporarily loading dialog from turning a
        # valid document into a permanent failure.
        for attempt in range(2):
            if attempt:
                print("   [RETRY] Retrying after the portal finishes refreshing...")
                _close_modal(driver)
                _wait_for_portal_idle(driver, timeout=10)
            outcome, reason = _upload_single_document(
                driver, section, label, file_path, row_aliases, used_portal_rows
            )
            if outcome != "failed":
                break

        if outcome == "uploaded":
            uploaded += 1
            print(f"   [OK] Uploaded successfully!")
        elif outcome == "skipped":
            skipped += 1
            skipped_documents.append(section)
            skipped_details[section] = reason
            print(f"   [SKIP] {reason}")
        else:
            failed += 1
            failures.append(section)
            failure_details[section] = reason
            print(f"   [FAIL] {section}: {reason}")

        time.sleep(1.5)  # Pause between uploads

    print("\n" + "="*50)
    print(
        f"[SUMMARY] Upload: {uploaded} succeeded, {failed} failed, "
        f"{skipped} skipped out of {len(upload_plan)} required sections"
    )
    print("="*50)

    # Do NOT close the browser - user still needs it!
    print("\n[DONE] Browser left open for you to verify.")
    return {
        "found": len(matches),
        "planned": len(upload_plan),
        "uploaded": uploaded,
        "failed": failed,
        "failed_documents": failures,
        "failure_details": failure_details,
        "skipped": skipped,
        "skipped_documents": skipped_documents,
        "skipped_details": skipped_details,
    }


def _upload_documents_with_playwright(
    upload_plan: list[tuple[str, str, str, tuple[str, ...]]],
    port: int,
    source_document_count: int,
) -> dict[str, object]:
    """Upload through the existing DevTools session without an EdgeDriver."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    uploaded = 0
    failed = 0
    skipped = 0
    failures: list[str] = []
    failure_details: dict[str, str] = {}
    skipped_documents: list[str] = []
    skipped_details: dict[str, str] = {}
    used_portal_rows: set[str] = set()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            pages = [page for context in browser.contexts for page in context.pages]
            page = next(
                (
                    candidate
                    for candidate in pages
                    if "goaonline" in candidate.url.lower() or "goa" in candidate.title().lower()
                ),
                None,
            )
            if page is None:
                raise RuntimeError("No Goa Online page is open in the browser connection.")

            print(f"   [OK] Connected directly! Current page: {page.title()}")
            for section, label, file_path, row_aliases in upload_plan:
                print(f"\n[UPLOAD] {section} <- {label}")
                outcome, reason = _playwright_upload_single_document(
                    page, section, label, file_path, row_aliases, used_portal_rows
                )
                if outcome == "uploaded":
                    uploaded += 1
                    print("   [OK] Uploaded successfully!")
                elif outcome == "skipped":
                    skipped += 1
                    skipped_documents.append(section)
                    skipped_details[section] = reason
                    print(f"   [SKIP] {reason}")
                else:
                    failed += 1
                    failures.append(section)
                    failure_details[section] = reason
                    print(f"   [FAIL] {section}: {reason}")
                page.wait_for_timeout(1000)
    except PlaywrightTimeoutError as error:
        failed = len(upload_plan)
        failures = [section for section, _, _, _ in upload_plan]
        failure_details = {section: str(error) for section in failures}
        print(f"\n[ERROR] The portal did not finish an upload: {error}")
    except Exception as error:
        failed = len(upload_plan)
        failures = [section for section, _, _, _ in upload_plan]
        failure_details = {section: str(error) for section in failures}
        print(f"\n[ERROR] Could not use the open browser connection: {error}")

    print("\n" + "=" * 50)
    print(
        f"[SUMMARY] Upload: {uploaded} succeeded, {failed} failed, "
        f"{skipped} skipped out of {len(upload_plan)} required sections"
    )
    print("=" * 50)
    print("\n[DONE] Browser left open for you to verify.")
    return {
        "found": source_document_count,
        "planned": len(upload_plan),
        "uploaded": uploaded,
        "failed": failed,
        "failed_documents": failures,
        "failure_details": failure_details,
        "skipped": skipped,
        "skipped_documents": skipped_documents,
        "skipped_details": skipped_details,
    }


def _playwright_upload_single_document(
    page,
    section: str,
    label: str,
    file_path: str,
    row_aliases: tuple[str, ...],
    used_portal_rows: set[str],
) -> tuple[str, str]:
    """Attach a file to one distinct section in the already-open page."""
    candidate_aliases = tuple(dict.fromkeys(_specific_portal_row_aliases(label) + row_aliases))
    section_has_file = page.evaluate("""
        (sectionName) => {
            const normalise = (value) => (value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
            let inSection = false;
            for (const row of document.querySelectorAll('tr')) {
                const text = normalise(row.innerText || row.textContent);
                const controls = row.querySelectorAll('button, a, input[type="button"], input[type="submit"]');
                if (!controls.length && /minimum .*document\\(s\\) required/.test(text)) {
                    inSection = text.includes(sectionName);
                    continue;
                }
                if (inSection && /\\b[1-9][0-9]*\\s*file\\(s\\)/.test(text)) return true;
            }
            return false;
        }
    """, section.lower())
    if section_has_file:
        return "skipped", "This portal section already has an attached document."
    page.evaluate("""
        () => {
            for (const modal of document.querySelectorAll('.modal')) {
                const style = window.getComputedStyle(modal);
                if (style.display !== 'none' && modal.offsetWidth && modal.offsetHeight) {
                    const close = modal.querySelector('.close, [data-dismiss="modal"]');
                    if (close) close.click();
                }
            }
        }
    """)

    click_result = page.evaluate("""
        ({ aliases, preferredSection, usedRows }) => {
            const normalise = (value) => (value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
            const used = new Set(usedRows);
            const rows = [...document.querySelectorAll('tr, .document-row, .upload-row, [data-document-row]')];
            let heading = '';
            let best = null;
            let matchingRowFound = false;
            let unclaimedMatchingRowFound = false;
            let existingDocumentFound = false;
            for (let index = 0; index < rows.length; index += 1) {
                const row = rows[index];
                const rowText = normalise(row.innerText || row.textContent);
                const controls = [...row.querySelectorAll('button, a, input[type="button"], input[type="submit"]')];
                if (!controls.length && /minimum .*document\\(s\\) required/.test(rowText)) {
                    heading = rowText;
                    continue;
                }
                const matchedAlias = aliases.find((alias) => rowText.includes(alias));
                if (!matchedAlias) continue;
                matchingRowFound = true;
                const rowKey = `${heading}::${rowText}`;
                if (/\\b[1-9][0-9]*\\s*file\\(s\\)/.test(rowText)) {
                    existingDocumentFound = true;
                    continue;
                }
                if (used.has(rowKey)) continue;
                unclaimedMatchingRowFound = true;
                const uploadButton = controls.find((control) => {
                    if (!control.offsetWidth || !control.offsetHeight || control.disabled) return false;
                    const controlText = normalise([
                        control.innerText, control.value, control.title,
                        control.getAttribute('aria-label'), control.getAttribute('onclick'),
                    ].filter(Boolean).join(' '));
                    return control.getAttribute('data-toggle') === 'modal'
                        || /upload|attach|re-upload|reupload|replace/.test(controlText);
                });
                if (!uploadButton) continue;
                let score = matchedAlias === aliases[0] ? 10 : 1;
                if (preferredSection && heading.includes(preferredSection)) score += 20;
                if (!best || score > best.score) best = { uploadButton, rowKey, score };
            }
            if (best) {
                best.uploadButton.click();
                return { status: 'clicked', rowKey: best.rowKey };
            }
            if (!matchingRowFound) return { status: 'not_requested' };
            if (existingDocumentFound) return { status: 'already_uploaded' };
            if (!unclaimedMatchingRowFound) return { status: 'slot_already_used' };
            return { status: 'row_without_upload_button' };
        }
    """, {
        "aliases": list(candidate_aliases),
        "preferredSection": section.lower(),
        "usedRows": sorted(used_portal_rows),
    })

    status = click_result.get("status")
    if status == "not_requested":
        return "skipped", "The current portal form does not request this document section."
    if status == "slot_already_used":
        return "skipped", "Its matching portal upload slot was already used."
    if status == "already_uploaded":
        return "skipped", "This portal section already has an attached document."
    if status != "clicked":
        return "failed", "A matching portal row was found, but it has no usable Upload button."

    try:
        page.wait_for_function("""
            () => [...document.querySelectorAll('.modal')].some((modal) => {
                const style = window.getComputedStyle(modal);
                return style.display !== 'none' && modal.offsetWidth && modal.offsetHeight
                    && Boolean(modal.querySelector('input[type="file"]'));
            })
        """, timeout=15_000)
        found_input = page.evaluate("""
            () => {
                const visible = (element) => {
                    const style = window.getComputedStyle(element);
                    return style.display !== 'none' && style.visibility !== 'hidden';
                };
                const modal = [...document.querySelectorAll('.modal')].find((candidate) => visible(candidate)
                    && candidate.offsetWidth && candidate.offsetHeight);
                const input = (modal && modal.querySelector('input[type="file"]'))
                    || [...document.querySelectorAll('input[type="file"]')].find(visible);
                if (!input) return false;
                input.setAttribute('data-saarthi-upload-input', 'true');
                return true;
            }
        """)
        if not found_input:
            return "failed", "The portal upload dialog has no file selector."
        page.locator('[data-saarthi-upload-input="true"]').last.set_input_files(file_path, timeout=15_000)
        page.wait_for_timeout(750)
        saved = page.evaluate("""
            () => {
                const visible = (element) => {
                    const style = window.getComputedStyle(element);
                    return style.display !== 'none' && element.offsetWidth && element.offsetHeight;
                };
                const modal = [...document.querySelectorAll('.modal')].find(visible);
                if (!modal) return false;
                const button = [...modal.querySelectorAll(
                    'button, input[type="button"], input[type="submit"], a, [role="button"]'
                )].find((candidate) => {
                    if (!visible(candidate) || candidate.disabled || candidate.classList.contains('close')) return false;
                    const text = (candidate.innerText || candidate.value || '').toLowerCase().trim();
                    return text.includes('save') || text.includes('submit') || text === 'upload' || text.includes('ok');
                });
                if (!button) return false;
                button.click();
                return true;
            }
        """)
        if not saved:
            return "failed", "The portal upload dialog has no Save or Submit button."
        page.wait_for_function("""
            () => ![...document.querySelectorAll('.modal')].some((modal) => {
                const style = window.getComputedStyle(modal);
                return style.display !== 'none' && modal.offsetWidth && modal.offsetHeight;
            })
        """, timeout=20_000)
    except Exception as error:
        return "failed", f"Could not save the selected file: {error}"

    used_portal_rows.add(click_result["rowKey"])
    return "uploaded", ""


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Upload documents to Goa Online portal from a local folder"
    )
    parser.add_argument("--folder", "-f", required=True, help="Path to folder containing document images")
    parser.add_argument("--port", "-p", type=int, default=9222, help="Edge remote debugging port")
    args = parser.parse_args()
    upload_documents(args.folder, args.port)


def _upload_single_document(
    driver,
    section: str,
    label: str,
    file_path: str,
    row_aliases: tuple[str, ...],
    used_portal_rows: set[str],
) -> tuple[str, str]:
    """Upload one section's file and return ``uploaded``, ``skipped``, or ``failed``.

    A service only exposes rows for the documents it asks for.  A local
    document library can contain additional proofs, so an absent portal row is
    informational rather than an upload failure.  Generic rows such as
    ``Identity proof`` are also claimed once, preventing a later document from
    overwriting the first one selected for that row.
    """
    from selenium.webdriver.common.by import By
    candidate_aliases = tuple(dict.fromkeys(_specific_portal_row_aliases(label) + row_aliases))

    section_has_file = driver.execute_script("""
        var sectionName = arguments[0].toLowerCase();
        var rows = document.querySelectorAll('tr');
        var inSection = false;
        for (var index = 0; index < rows.length; index += 1) {
            var row = rows[index];
            var text = (row.innerText || row.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
            var controls = row.querySelectorAll('button, a, input[type="button"], input[type="submit"]');
            if (!controls.length && /minimum .*document\\(s\\) required/.test(text)) {
                inSection = text.indexOf(sectionName) !== -1;
                continue;
            }
            if (inSection && /\\b[1-9][0-9]*\\s*file\\(s\\)/.test(text)) return true;
        }
        return false;
    """, section)
    if section_has_file:
        return "skipped", "This portal section already has an attached document."

    # A completed upload can leave its modal in the DOM during the Wicket
    # Ajax transition. Do not click the next row while that overlay is still
    # active.
    _wait_for_modal(driver, visible=False, timeout=8)
    _wait_for_portal_idle(driver, timeout=10)

    # -- 1. Find the Upload button for this document --
    click_result = driver.execute_script("""
        var labels = arguments[0];
        var usedRows = new Set(arguments[1]);
        var preferredSection = arguments[2];
        var rows = document.querySelectorAll('tr, .document-row, .upload-row, [data-document-row]');
        var bestButton = null;
        var bestScore = 0;
        var bestRowKey = null;
        var matchingRowFound = false;
        var unclaimedMatchingRowFound = false;
        var existingDocumentFound = false;
        var currentSection = '';
        for (var rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
            var row = rows[rowIndex];
            var rowKey = String(rowIndex);
            var rowText = row.textContent.trim().toLowerCase();
            var controls = row.querySelectorAll('button, a, input[type="button"], input[type="submit"]');
            if (!controls.length && /(?:affidavit|(?:age|identity|residence) proof|photograph|photo)/.test(rowText)) {
                currentSection = rowText;
                continue;
            }
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
            var score = rowText.indexOf(labels[0]) !== -1 ? 2 : 0;
            if (!score) {
                for (var labelIndex = 1; labelIndex < labels.length; labelIndex += 1) {
                    if (rowText.indexOf(labels[labelIndex]) !== -1) {
                        score = 1;
                        break;
                    }
                }
            }
            if (!score) continue;
            if (preferredSection && currentSection.indexOf(preferredSection) !== -1) {
                score += 5;
            }
            matchingRowFound = true;
            if (/\\b[1-9][0-9]*\\s*file\\(s\\)\\b/.test(rowText)) {
                existingDocumentFound = true;
                continue;
            }
            if (usedRows.has(rowKey)) continue;
            unclaimedMatchingRowFound = true;
            if (!uploadBtn) continue;
            if (score > bestScore) {
                bestButton = uploadBtn;
                bestScore = score;
                bestRowKey = rowKey;
            }
        }
        if (bestButton) {
            bestButton.click();
            return { status: 'clicked', rowKey: bestRowKey };
        }
        if (!matchingRowFound) return { status: 'not_requested' };
        if (existingDocumentFound) return { status: 'already_uploaded' };
        if (!unclaimedMatchingRowFound) return { status: 'slot_already_used' };
        return { status: 'row_without_upload_button' };
    """, list(candidate_aliases), sorted(used_portal_rows), section.lower())

    click_status = click_result.get("status") if isinstance(click_result, dict) else click_result
    if click_status == "not_requested":
        return "skipped", "The current portal form does not request this document."
    if click_status == "slot_already_used":
        return "skipped", "Its matching portal upload slot was already used by another document."
    if click_status == "already_uploaded":
        return "skipped", "This document is already attached in the portal."
    if click_status != "clicked":
        message = "A matching portal row was found, but it has no usable Upload button."
        print(f"   [FAIL] {message}")
        return "failed", message

    row_key = click_result.get("rowKey") if isinstance(click_result, dict) else None

    print(f"   -> Clicked Upload button, waiting for modal...")
    active_modal = _wait_for_upload_modal(driver, timeout=15)
    if not active_modal:
        print("   [FAIL] No active upload dialog found")
        return "failed", "The portal did not open its file-upload dialog."

    # -- 2. Find the file input inside the ACTIVE modal --
    try:
        file_inputs = active_modal.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
        if not file_inputs:
            # Some Goa Online variants mount the file control outside the modal
            # while keeping the modal as the visible upload dialog.
            file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
        if not file_inputs:
            print(f"   [FAIL] No file input found inside the active modal")
            _close_modal(driver)
            return "failed", "The portal upload dialog has no file selector."

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

        # Selenium reports an empty value if the portal replaced the input
        # before it received the selected file.  Retry the document rather
        # than clicking Upload with no file selected.
        if not file_input.get_attribute("value"):
            _close_modal(driver)
            return "failed", "The portal did not retain the selected file."

        # Keep the input usable until the onchange/Ajax handler has had time to
        # receive the selected file, then restore the portal's original style.
        time.sleep(1)
        driver.execute_script("arguments[0].setAttribute('style', arguments[1]);", file_input, original_style)
        time.sleep(2)

    except Exception as e:
        print(f"   [FAIL] Error finding/using file input: {e}")
        _close_modal(driver)
        return "failed", f"Could not select the file: {e}"

    # -- 3. Click Save/Submit in the modal --
    try:
        save_btn = driver.execute_script("""
            const modal = arguments[0];
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
        """, active_modal)

        if not save_btn:
            print(f"   [FAIL] Could not find Save/Submit button")
            _close_modal(driver)
            return "failed", "The portal upload dialog has no Save or Submit button."

        print(f"   -> Clicked Save/Submit button")
        driver.execute_script("arguments[0].click();", save_btn)
        time.sleep(3)

    except Exception as e:
        print(f"   [FAIL] Error clicking Save: {e}")
        _close_modal(driver)
        return "failed", f"Could not save the selected file: {e}"

    # Wait for the portal's Ajax response and modal transition before the next
    # document row is touched. If it remains open, close it and verify closure.
    if not _wait_for_modal(driver, visible=False, timeout=15):
        portal_error = _upload_dialog_error(active_modal)
        _close_modal(driver)
        _wait_for_modal(driver, visible=False, timeout=5)
        if portal_error:
            return "failed", f"The portal rejected the upload: {portal_error}"
        return "failed", "The portal did not finish saving the selected file."
    _wait_for_portal_idle(driver, timeout=10)
    if row_key is not None:
        used_portal_rows.add(str(row_key))
    return "uploaded", ""


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


def _wait_for_upload_modal(driver, *, timeout: float):
    """Wait until the visible modal contains the portal's file picker."""
    from selenium.webdriver.common.by import By

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            modal = _active_modal(driver)
            if modal and modal.find_elements(By.CSS_SELECTOR, 'input[type="file"]'):
                return modal
        except Exception:
            pass
        time.sleep(0.25)
    return None


def _wait_for_portal_idle(driver, *, timeout: float) -> bool:
    """Wait for Goa Online's loading overlays before touching another row."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            is_loading = driver.execute_script("""
                return [...document.querySelectorAll(
                    '#DocTypeUploadPanelLoading, #myModalLoading, .blockUI, .loading, .loader'
                )].some((element) => {
                    const style = window.getComputedStyle(element);
                    return style.display !== 'none' && style.visibility !== 'hidden'
                        && element.offsetWidth > 0 && element.offsetHeight > 0;
                });
            """)
            if not is_loading:
                return True
        except Exception:
            return False
        time.sleep(0.25)
    return False


def _upload_dialog_error(modal) -> str:
    """Return the portal validation text, if a still-open dialog shows one."""
    try:
        messages = []
        for element in modal.find_elements(
            "css selector", ".text-danger, .error, .errors, [style*='color: red']"
        ):
            text = " ".join(element.text.split())
            # Required-field asterisks are styled red but are not errors.
            if text and text != "*":
                messages.append(text)
        return " ".join(messages)
    except Exception:
        return ""


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
