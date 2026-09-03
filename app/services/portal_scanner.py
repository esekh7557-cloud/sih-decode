"""Read visible application requirements from the citizen's opened portal page.

The scanner attaches to the locally opened Chrome session. It reads labels,
control types, required markers and document-upload row labels only; it never
reads passwords, OTPs, CAPTCHA answers or existing form values.
"""
from __future__ import annotations

import re
from typing import Any

from app.services.chrome_cdp import ChromeDebugError, evaluate_open_form


def _key(value: str, fallback: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return key[:80] or fallback


def scan_open_form(port: int = 9222) -> dict[str, Any]:
    try:
        data = evaluate_open_form(
        r"""(() => {
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
        function groupLabelFor(el, fallback) {
          // A radio button's nearest <label> is normally its option (for
          // example, "Self"), not the question. Prefer the group heading so
          // the preparation screen can ask "Applying for" with each option.
          const fieldset = el.closest('fieldset');
          if (fieldset) {
            const legend = fieldset.querySelector('legend');
            if (legend && clean(legend.innerText)) return clean(legend.innerText);
          }
          const labelledBy = (el.getAttribute('aria-labelledby') || '')
            .split(/\s+/).map((id) => document.getElementById(id)).filter(Boolean)
            .map((node) => clean(node.innerText)).filter(Boolean).join(' ');
          if (labelledBy) return labelledBy;
          const container = el.closest('[role="radiogroup"], [role="group"], .radio-group, .checkbox-group, .form-group, .field, .row, li, td');
          if (container) {
            const heading = container.querySelector('legend, .control-label, .form-label, .field-label, [data-field-label]');
            if (heading && clean(heading.innerText)) return clean(heading.innerText);
            const plainLabel = Array.from(container.querySelectorAll('label')).find((node) =>
              node !== el.closest('label') &&
              !node.htmlFor &&
              !node.querySelector('input[type="radio"], input[type="checkbox"]') &&
              clean(node.innerText)
            );
            if (plainLabel) return clean(plainLabel.innerText);
            const explicit = Array.from(container.querySelectorAll('label[for], th')).find((node) => {
              if (node === el.closest('label') || !clean(node.innerText)) return false;
              if (node.tagName.toLowerCase() !== 'label') return true;
              const target = document.getElementById(node.htmlFor);
              return !target || !['radio', 'checkbox'].includes(target.type);
            });
            if (explicit) return clean(explicit.innerText);
          }
          return fallback;
        }
        function choicesFor(el) {
          const found = [];
          const add = (value, label) => {
            const cleanValue = String(value || '').trim();
            const cleanLabel = clean(label);
            if (!cleanLabel) return;
            const key = cleanValue || cleanLabel;
            if (!found.some((item) => item.value === key)) {
              found.push({ value: key, label: cleanLabel });
            }
          };
          if (el.tagName.toLowerCase() === 'select') {
            Array.from(el.options).filter((option) => option.value).forEach((option) => add(option.value, option.text));
          }
          // Native datalist inputs and accessible comboboxes often keep their
          // choices outside the input itself. Read only labels/options, never
          // the applicant's entered value.
          const references = [
            el.getAttribute('list'),
            el.getAttribute('aria-controls'),
            el.getAttribute('aria-owns'),
          ].filter(Boolean).flatMap((value) => String(value).split(/\s+/));
          references.forEach((id) => {
            const list = document.getElementById(id);
            if (!list) return;
            list.querySelectorAll('option, [role="option"], .dropdown-item, .select2-results__option, .chosen-results li').forEach((option) => {
              if (option.getAttribute('aria-disabled') === 'true') return;
              add(option.value || option.getAttribute('data-value') || option.getAttribute('data-id') || option.id, option.getAttribute('aria-label') || option.innerText || option.textContent);
            });
          });
          const container = el.closest('.form-group, .field, .row, li, td, [role="group"]');
          if (!found.length && container) {
            container.querySelectorAll('[role="option"], .dropdown-menu .dropdown-item, .select2-results__option, .chosen-results li').forEach((option) => {
              if (option.getAttribute('aria-disabled') === 'true') return;
              add(option.getAttribute('data-value') || option.getAttribute('data-id') || option.id, option.getAttribute('aria-label') || option.innerText || option.textContent);
            });
          }
          return found.slice(0, 30);
        }
        const fields = [];
        const seen = new Set();
        const controls = Array.from(document.querySelectorAll(
          'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="file"]), select, textarea, [role="combobox"], [aria-haspopup="listbox"]'
        ));
        controls.forEach((el, index) => {
          const box = el.getBoundingClientRect();
          // Select libraries commonly hide the native <select> and render a
          // visible custom control. Its option list remains the reliable
          // source of choices, so retain hidden selects with a real label.
          const hiddenNativeSelect = el.tagName.toLowerCase() === 'select';
          if ((box.width === 0 || box.height === 0) && !hiddenNativeSelect) return;
          if (el.disabled) return;
          const tag = el.tagName.toLowerCase();
          const optionOrFieldLabel = labelFor(el);
          const inputType = el.type || tag;
          const label = inputType === 'radio' || inputType === 'checkbox'
            ? groupLabelFor(el, optionOrFieldLabel)
            : optionOrFieldLabel;
          if (!label || label.length < 2 || /search|captcha|otp|password/i.test(label)) return;
          const choices = choicesFor(el);
          const isChoiceWidget = el.getAttribute('role') === 'combobox' || el.getAttribute('aria-haspopup') === 'listbox';
          const type = tag === 'select'
            ? (el.multiple ? 'multi_select' : 'select')
            : (isChoiceWidget && choices.length ? 'select' : (tag === 'textarea' ? 'textarea' : (el.type || tag)));
          const baseKey = el.name || el.id || label;
          const unique = baseKey + '|' + type;
          if (seen.has(unique) && type !== 'radio' && type !== 'checkbox') return;
          seen.add(unique);
          const optionLabel = type === 'radio' || type === 'checkbox'
            ? clean((el.closest('label') || {}).innerText || el.value || optionOrFieldLabel)
            : '';
          fields.push({
            key: baseKey,
            label,
            type,
            required: !!(el.required || el.getAttribute('aria-required') === 'true' || /required|mandatory/i.test((el.closest('tr, .form-group, .field, .row') || {}).innerText || '')),
            options: type === 'select' || type === 'multi_select'
              ? choices
              : (optionLabel ? [{ value: el.value || optionLabel, label: optionLabel }] : []),
            placeholder: clean(el.getAttribute('placeholder')),
            min: el.getAttribute('min') || '',
            max: el.getAttribute('max') || '',
            step: el.getAttribute('step') || '',
            pattern: el.getAttribute('pattern') || '',
            max_length: Number(el.getAttribute('maxlength')) > 0 ? Number(el.getAttribute('maxlength')) : null
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
        })()""",
        port,
        )
    except ChromeDebugError as exc:
        raise RuntimeError(str(exc)) from exc

    fields, used_keys = [], set()
    grouped_controls = {}
    for item in data.get("fields", []):
        item_type = str(item.get("type", "text"))
        raw_key = str(item.get("key") or item.get("label") or "")
        if item_type in {"radio", "checkbox"}:
            group_key = (raw_key, item_type)
            if group_key in grouped_controls:
                existing = grouped_controls[group_key]
                options = existing.get("options", []) + item.get("options", [])
                existing["options"] = list({
                    str(option.get("value", option) if isinstance(option, dict) else option): option
                    for option in options
                }.values())
                existing["required"] = existing.get("required", False) or bool(item.get("required"))
                continue
            # Keep the object returned in ``fields`` identical to the grouped
            # object so later radio/checkbox options are not merged into a
            # discarded copy.
            grouped_controls[group_key] = item
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
            "placeholder": item.get("placeholder", ""),
            "min": item.get("min", ""),
            "max": item.get("max", ""),
            "step": item.get("step", ""),
            "pattern": item.get("pattern", ""),
            "max_length": item.get("max_length"),
        })
    return {
        "url": str(data.get("url") or ""),
        "title": str(data.get("title") or ""),
        "fields": normalised_fields,
        "documents": [str(item) for item in data.get("documents", []) if str(item).strip()],
    }
