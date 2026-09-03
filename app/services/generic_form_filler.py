"""Safely fill reviewed fields on the citizen's already-opened portal form.

The filler uses the same local Chrome DevTools Protocol connection as the
portal scanner. It never starts a second browser, reads no existing applicant
values, and deliberately has no upload, button, save, or submit behaviour.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.services.chrome_cdp import ChromeDebugError, evaluate_open_form


_SENSITIVE_FIELD = re.compile(
    r"password|\botp\b|captcha|verification\s*code|security\s*code",
    re.IGNORECASE,
)
_UNFILLABLE_TYPES = {
    "button",
    "file",
    "hidden",
    "image",
    "password",
    "reset",
    "submit",
}


def _reviewed_fill_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a minimal, safe copy of values already reviewed by the citizen.

    The HTTP endpoint builds ``fields`` from the reviewed application plan.
    This second check keeps the service safe when it is called directly too:
    credentials, OTP/CAPTCHA controls, files, and button-like controls are
    never sent to the browser-side evaluator.
    """
    reviewed: list[dict[str, Any]] = []
    for field in fields:
        if not isinstance(field, dict):
            continue

        key = str(field.get("key") or "").strip()
        label = str(field.get("label") or "").strip()
        field_type = str(field.get("type") or "text").strip().lower()
        value = field.get("value")
        identity = f"{key} {label}"

        if (
            not (key or label)
            or value is None
            or field_type in _UNFILLABLE_TYPES
            or _SENSITIVE_FIELD.search(identity)
        ):
            continue
        reviewed.append({
            "key": key,
            "label": label,
            "type": field_type,
            "value": value,
        })
    return reviewed


# ``__SAARTHI_REVIEWED_FIELDS__`` is replaced with JSON generated locally by
# ``fill_open_form``. Keeping the script static makes it easy to audit that it
# never clicks a button or handles a file/password/OTP/CAPTCHA control.
_FILL_REVIEWED_FIELDS = r"""(() => {
  const fields = __SAARTHI_REVIEWED_FIELDS__;
  const normalise = (value) => String(value ?? '')
    .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  const clean = (value) => String(value ?? '')
    .replace(/\*/g, '').replace(/\s+/g, ' ').trim();
  const blocked = /password|\botp\b|captcha|verification\s*code|security\s*code/i;
  const blockedInputTypes = new Set([
    'button', 'file', 'hidden', 'image', 'password', 'reset', 'submit'
  ]);

  const isVisible = (el) => {
    const box = el.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
  };
  const labelFor = (el) => {
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
  };
  const groupLabelFor = (el) => {
    const fieldset = el.closest('fieldset');
    if (fieldset) {
      const legend = fieldset.querySelector('legend');
      if (legend && clean(legend.innerText)) return clean(legend.innerText);
    }
    const labelledBy = (el.getAttribute('aria-labelledby') || '')
      .split(/\s+/).map((id) => document.getElementById(id)).filter(Boolean)
      .map((node) => clean(node.innerText)).filter(Boolean).join(' ');
    if (labelledBy) return labelledBy;
    const container = el.closest(
      '[role="radiogroup"], [role="group"], .radio-group, .checkbox-group, .form-group, .field, .row, li, td'
    );
    if (container) {
      const heading = container.querySelector(
        'legend, .control-label, .form-label, .field-label, [data-field-label]'
      );
      if (heading && clean(heading.innerText)) return clean(heading.innerText);
      const cells = container.querySelectorAll('td');
      if (cells.length > 1 && clean(cells[0].innerText)) return clean(cells[0].innerText);
      const plainLabel = Array.from(container.querySelectorAll('label')).find((node) =>
        node !== el.closest('label') && !node.htmlFor &&
        !node.querySelector('input[type="radio"], input[type="checkbox"]') &&
        clean(node.innerText)
      );
      if (plainLabel) return clean(plainLabel.innerText);
    }
    return '';
  };
  const dispatchChange = (target) => {
    target.dispatchEvent(new Event('input', { bubbles: true }));
    target.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const setValue = (target, value) => {
    const prototype = target instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : target instanceof HTMLSelectElement
        ? HTMLSelectElement.prototype
        : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
    if (setter) setter.call(target, value);
    else target.value = value;
  };
  const setChecked = (target) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'checked')?.set;
    if (setter) setter.call(target, true);
    else target.checked = true;
  };
  const controls = Array.from(document.querySelectorAll('input, select, textarea')).filter((el) => {
    const inputType = String(el.type || '').toLowerCase();
    return !el.disabled && isVisible(el) && !blockedInputTypes.has(inputType);
  });
  const changed = [];

  for (const field of fields) {
    const fieldIdentity = [field.key, field.label].join(' ');
    if (blocked.test(fieldIdentity) || blockedInputTypes.has(String(field.type || '').toLowerCase())) continue;
    const needles = [normalise(field.key), normalise(field.label)].filter(Boolean);
    if (!needles.length) continue;
    const values = Array.isArray(field.value) ? field.value : [field.value];
    const desiredValues = values.map(normalise).filter(Boolean);
    const targets = controls.filter((el) => {
      const haystacks = [
        normalise(el.name), normalise(el.id), normalise(labelFor(el)), normalise(groupLabelFor(el))
      ].filter(Boolean);
      if (haystacks.some((value) => blocked.test(value))) return false;
      return needles.some((needle) => haystacks.some((haystack) =>
        haystack === needle || (needle.length > 3 && haystack.includes(needle))
      ));
    });
    if (!targets.length) continue;

    const choiceTargets = targets.filter((el) => /^(checkbox|radio)$/i.test(el.type || ''));
    if (choiceTargets.length) {
      const isRadio = choiceTargets.some((el) => el.type === 'radio');
      let selected = false;
      for (const target of choiceTargets) {
        const optionValues = [
          normalise(target.value), normalise(labelFor(target)),
          normalise((target.closest('label') || {}).innerText)
        ].filter(Boolean);
        const matches = desiredValues.some((value) => optionValues.includes(value));
        // A reviewed declaration checkbox may be represented by ``true``.
        const shouldCheck = matches || (!isRadio && desiredValues.includes('true') && !selected);
        if (!shouldCheck) continue;
        setChecked(target);
        dispatchChange(target);
        changed.push(groupLabelFor(target) || labelFor(target) || target.name || target.id);
        selected = true;
        if (isRadio) break;
      }
      continue;
    }

    const target = targets[0];
    if (target.tagName.toLowerCase() === 'select') {
      const options = Array.from(target.options);
      const matchingOptions = options.filter((option) => {
        const optionText = normalise(option.text);
        const optionValue = normalise(option.value);
        return desiredValues.some((desired) =>
          optionText === desired || optionValue === desired ||
          (desired.length > 2 && (optionText.includes(desired) || desired.includes(optionText)))
        );
      });
      if (!matchingOptions.length) continue;
      if (target.multiple) {
        // Only add reviewed choices. Do not inspect or clear an existing value.
        matchingOptions.forEach((option) => { option.selected = true; });
        dispatchChange(target);
      } else {
        setValue(target, matchingOptions[0].value);
        dispatchChange(target);
      }
      changed.push(labelFor(target) || target.name || target.id);
      continue;
    }

    setValue(target, String(values[0] ?? ''));
    dispatchChange(target);
    changed.push(labelFor(target) || target.name || target.id);
  }
  return changed;
})()"""


def fill_open_form(fields: list[dict[str, Any]], port: int = 9222) -> list[str]:
    """Fill only reviewed values in the same open tab chosen by the scanner.

    ``evaluate_open_form`` selects the HTTP(S) tab with the most form controls,
    matching the scanner's selection logic and avoiding ChromeDriver entirely.
    """
    reviewed_fields = _reviewed_fill_fields(fields)
    if not reviewed_fields:
        return []

    expression = _FILL_REVIEWED_FIELDS.replace(
        "__SAARTHI_REVIEWED_FIELDS__",
        json.dumps(reviewed_fields, ensure_ascii=False, default=str),
        1,
    )
    try:
        changed = evaluate_open_form(expression, port)
    except ChromeDebugError as exc:
        raise RuntimeError(str(exc)) from exc
    return [str(label) for label in changed] if isinstance(changed, list) else []
