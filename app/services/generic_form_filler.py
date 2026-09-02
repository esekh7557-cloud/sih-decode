"""Safe, generic filling for a form the citizen has already opened.

This helper attaches to Saarthi's local Chrome session. It fills only reviewed
text/select fields, never reads existing values, never handles passwords/OTPs/
CAPTCHAs, never uploads a file, and never clicks save or submit.
"""
from __future__ import annotations

from typing import Any


def fill_open_form(fields: list[dict[str, Any]], port: int = 9222) -> None:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    driver = webdriver.Chrome(options=options)

    # The same visible application tab selected by the scanner is preferred.
    best_handle, best_count = driver.current_window_handle, -1
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        count = driver.execute_script(
            "return document.querySelectorAll('input, select, textarea').length;"
        )
        if count > best_count:
            best_handle, best_count = handle, count
    driver.switch_to.window(best_handle)

    # Values are supplied only from the reviewed plan returned to the citizen.
    # The browser-side code intentionally has no save/submit/button behaviour.
    driver.execute_script(
        r"""
        const fields = arguments[0];
        const normalise = (value) => String(value || '')
          .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
        const clean = (value) => String(value || '').replace(/\*/g, '').replace(/\s+/g, ' ').trim();
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
          }
          return clean(el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.name || el.id);
        };
        const controls = Array.from(document.querySelectorAll(
          'input:not([type="hidden"]), select, textarea'
        )).filter((el) => {
          const box = el.getBoundingClientRect();
          return box.width > 0 && box.height > 0 && !el.disabled;
        });
        const blocked = /password|otp|captcha|verification code|security code/i;
        const changed = [];

        for (const field of fields) {
          const needles = [normalise(field.key), normalise(field.label)].filter(Boolean);
          if (!needles.length || blocked.test(field.label || '') || field.type === 'file') continue;
          const target = controls.find((el) => {
            const haystacks = [normalise(el.name), normalise(el.id), normalise(labelFor(el))];
            if (haystacks.some((value) => blocked.test(value))) return false;
            return needles.some((needle) => haystacks.some((haystack) =>
              haystack === needle || (needle.length > 3 && haystack.includes(needle))
            ));
          });
          if (!target || target.type === 'file' || /checkbox|radio/i.test(target.type || '')) continue;

          const value = String(field.value ?? '');
          if (target.tagName.toLowerCase() === 'select') {
            const desired = normalise(value);
            const option = Array.from(target.options).find((item) => {
              const optionText = normalise(item.text);
              const optionValue = normalise(item.value);
              return optionText === desired || optionValue === desired ||
                (desired.length > 2 && (optionText.includes(desired) || desired.includes(optionText)));
            });
            if (!option) continue;
            target.value = option.value;
          } else {
            target.value = value;
          }
          target.dispatchEvent(new Event('input', { bubbles: true }));
          target.dispatchEvent(new Event('change', { bubbles: true }));
          changed.push(labelFor(target) || target.name || target.id);
        }
        return changed;
        """,
        fields,
    )
