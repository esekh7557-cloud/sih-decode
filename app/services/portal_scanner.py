"""Read visible application requirements from the citizen's opened portal page.

The scanner attaches to the locally opened Chrome session. It reads labels,
control types, required markers and document-upload row labels only; it never
reads passwords, OTPs, CAPTCHA answers or existing form values.
"""
from __future__ import annotations

import re
from typing import Any


def _key(value: str, fallback: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return key[:80] or fallback


def scan_open_form(port: int = 9222) -> dict[str, Any]:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    try:
        driver = webdriver.Chrome(options=options)
    except Exception as exc:
        raise RuntimeError(
            "Could not connect to the Saarthi browser. Open the official portal with Saarthi first."
        ) from exc

    # Prefer the visible tab containing the most controls. This works for new
    # government portals without relying on a domain-specific URL.
    best_handle, best_count = driver.current_window_handle, -1
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        count = driver.execute_script(
            "return document.querySelectorAll('input, select, textarea').length;"
        )
        if count > best_count:
            best_handle, best_count = handle, count
    driver.switch_to.window(best_handle)

    data = driver.execute_script(
        r"""
        function clean(text) {
          return (text || '').replace(/\*/g, '').replace(/\s+/g, ' ').trim();
        }
        function labelFor(el) {
          if (el.id) {
            const explicit = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
            if (explicit) return clean(explicit.innerText);
          }
          const wrapped = el.closest('label');
          if (wrapped) return clean(wrapped.innerText);
          const container = el.closest('tr, .form-group, .field, .row, li, td');
          if (container) {
            const label = container.querySelector('label, legend, th, .control-label, .form-label');
            if (label) return clean(label.innerText);
            const cells = container.querySelectorAll('td');
            if (cells.length > 1) return clean(cells[0].innerText);
          }
          return clean(el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.name || el.id);
        }
        const fields = [];
        const seen = new Set();
        const controls = document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]), select, textarea');
        controls.forEach((el, index) => {
          const box = el.getBoundingClientRect();
          if (box.width === 0 || box.height === 0 || el.disabled) return;
          const label = labelFor(el);
          if (!label || label.length < 2 || /search|captcha|otp|password/i.test(label)) return;
          const type = el.tagName.toLowerCase() === 'select' ? 'select' : (el.type || el.tagName.toLowerCase());
          const baseKey = el.name || el.id || label;
          const unique = baseKey + '|' + type;
          if (seen.has(unique) && type !== 'radio' && type !== 'checkbox') return;
          seen.add(unique);
          const optionLabel = type === 'radio' || type === 'checkbox'
            ? clean((el.closest('label') || {}).innerText || el.value || label)
            : '';
          fields.push({
            key: baseKey,
            label,
            type,
            required: !!(el.required || el.getAttribute('aria-required') === 'true' || /required|mandatory/i.test((el.closest('tr, .form-group, .field, .row') || {}).innerText || '')),
            options: type === 'select'
              ? Array.from(el.options).filter(o => o.value).map(o => clean(o.text)).slice(0, 30)
              : (optionLabel ? [optionLabel] : [])
          });
        });
        const documents = new Set();
        document.querySelectorAll('input[type="file"]').forEach((el) => {
          const label = labelFor(el);
          if (label) documents.add(label);
        });
        document.querySelectorAll('tr, .document-row, .upload-row, li').forEach((row) => {
          if (!row.querySelector('input[type="file"], button[data-toggle="modal"], a[data-toggle="modal"], .upload, [data-upload]')) return;
          const text = clean(row.innerText);
          if (text && /upload|attach|document|certificate|proof/i.test(text) && text.length < 220) {
            const first = text.split(/upload|attach|choose file/i)[0].trim();
            if (first.length > 2) documents.add(first);
          }
        });
        return { fields, documents: Array.from(documents).slice(0, 40), url: location.href, title: document.title };
        """
    )

    fields, used_keys = [], set()
    grouped_controls = {}
    for item in data.get("fields", []):
        item_type = str(item.get("type", "text"))
        raw_key = str(item.get("key") or item.get("label") or "")
        if item_type in {"radio", "checkbox"}:
            group_key = (raw_key, item_type)
            if group_key in grouped_controls:
                existing = grouped_controls[group_key]
                existing["options"] = list(dict.fromkeys(existing.get("options", []) + item.get("options", [])))
                existing["required"] = existing.get("required", False) or bool(item.get("required"))
                continue
            grouped_controls[group_key] = dict(item)
        fields.append(item)

    normalised_fields, used_keys = [], set()
    for index, item in enumerate(fields, start=1):
        label = str(item.get("label") or "").strip()
        key = _key(str(item.get("key") or label), f"field_{index}")
        original = key
        suffix = 2
        while key in used_keys:
            key = f"{original}_{suffix}"
            suffix += 1
        used_keys.add(key)
        normalised_fields.append({
            "key": key,
            "label": label,
            "type": item.get("type", "text"),
            "required": bool(item.get("required")),
            "options": item.get("options", []),
        })
    return {
        "url": str(data.get("url") or driver.current_url),
        "title": str(data.get("title") or driver.title),
        "fields": normalised_fields,
        "documents": [str(item) for item in data.get("documents", []) if str(item).strip()],
    }
