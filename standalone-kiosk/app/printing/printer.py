"""Printing via CUPS (lp) with QR-code fallback for phone download."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def print_document(file_path: str, copies: int = 2) -> bool:
    """Print via CUPS. Returns False if no printer - caller shows a QR instead."""
    if shutil.which("lp") is None:
        return False
    try:
        subprocess.run(["lp", "-n", str(copies), file_path], check=True, timeout=30)
        return True
    except Exception:
        return False


def make_qr(data: str, out_path: str | None = None) -> str:
    """Generate a QR code (e.g. a download link) as printer fallback."""
    import qrcode
    import uuid
    import time
    from app.docgen.generator import OUTPUT_DIR

    if out_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = str(OUTPUT_DIR / f"qr_{int(time.time())}_{uuid.uuid4().hex[:6]}.png")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    qrcode.make(data).save(out_path)
    return out_path
