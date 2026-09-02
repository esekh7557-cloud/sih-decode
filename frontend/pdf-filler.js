const API = window.location.origin;
const SESSION_STORAGE_KEY = "janseva.session.id";
let sessionId = localStorage.getItem(SESSION_STORAGE_KEY);
let selectedPdf = null;
let pdfFields = [];

const $ = (selector) => document.querySelector(selector);

async function api(path, method = "GET", body = null, headers = {}) {
  const options = { method, headers: { ...headers } };
  if (body !== null) options.body = body;
  const response = await fetch(API + path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "The PDF operation could not be completed.");
  return payload;
}

function showAlert(message, type = "info") {
  const alert = $("#pdf-filler-alert");
  alert.hidden = !message;
  alert.className = "pdf-filler-alert" + (type === "error" ? " error" : type === "success" ? " success" : "");
  alert.textContent = message || "";
}

async function ensureSession() {
  if (sessionId) {
    try { await api("/sessions/" + sessionId); return; } catch (_) { localStorage.removeItem(SESSION_STORAGE_KEY); }
  }
  const session = await api("/sessions", "POST", JSON.stringify({}), { "Content-Type": "application/json" });
  sessionId = session.session_id;
  localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
}

function renderFields() {
  const list = $("#pdf-field-list");
  list.innerHTML = "";
  pdfFields.forEach((field) => {
    const row = document.createElement("div");
    row.className = "pdf-field-row";
    const label = document.createElement("div");
    label.className = "pdf-field-label";
    const title = document.createElement("strong");
    title.textContent = field.label;
    const name = document.createElement("small");
    name.textContent = field.name;
    label.append(title, name);
    const inputWrap = document.createElement("div");
    inputWrap.className = "pdf-field-input";
    const options = Array.isArray(field.options) ? field.options.filter(Boolean) : [];
    let input;
    if (options.length) {
      input = document.createElement("select");
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "Select an option";
      input.appendChild(empty);
      options.forEach((option) => {
        const choice = document.createElement("option");
        choice.value = option;
        choice.textContent = option;
        input.appendChild(choice);
      });
    } else if (field.type === "checkbox") {
      input = document.createElement("input");
      input.type = "checkbox";
      input.value = "Yes";
      input.checked = ["yes", "true", "1", "/yes"].includes(String(field.suggested_value || field.value).toLowerCase());
    } else {
      input = document.createElement("input");
      input.type = "text";
      input.value = field.suggested_value || field.value || "";
    }
    input.dataset.pdfField = field.name;
    inputWrap.appendChild(input);
    if (field.suggested_value && field.type !== "checkbox") {
      const note = document.createElement("div");
      note.className = "pdf-suggestion";
      note.textContent = "Suggested from your saved details";
      inputWrap.appendChild(note);
    }
    row.append(label, inputWrap);
    list.appendChild(row);
  });
  $("#pdf-fields-panel").hidden = false;
  $("#pdf-field-count").textContent = pdfFields.length + " fields found";
}

async function inspectPdf() {
  if (!selectedPdf) return;
  const button = $("#inspect-pdf-button");
  button.disabled = true;
  button.textContent = "Reading PDF fields...";
  try {
    await ensureSession();
    const form = new FormData();
    form.append("file", selectedPdf);
    const result = await api("/sessions/" + sessionId + "/pdf-filler/inspect", "POST", form);
    pdfFields = result.fields || [];
    renderFields();
    showAlert("Found " + pdfFields.length + " fillable fields. Review the suggested values below.", "success");
  } catch (error) {
    showAlert(error.message, "error");
  } finally {
    button.disabled = !selectedPdf;
    button.textContent = "Read PDF fields";
  }
}

async function fillPdf() {
  const button = $("#fill-pdf-button");
  const values = {};
  document.querySelectorAll("[data-pdf-field]").forEach((input) => {
    values[input.dataset.pdfField] = input.type === "checkbox" ? (input.checked ? "Yes" : "Off") : input.value;
  });
  button.disabled = true;
  button.textContent = "Creating completed PDF...";
  try {
    const result = await api("/sessions/" + sessionId + "/pdf-filler/fill", "POST", JSON.stringify({ values }), { "Content-Type": "application/json" });
    const link = $("#download-pdf-link");
    link.href = result.download_url;
    $("#pdf-download-panel").hidden = false;
    showAlert(result.message, "success");
    $("#pdf-download-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showAlert(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "Fill PDF with reviewed values";
  }
}

$("#pdf-input").addEventListener("change", (event) => {
  selectedPdf = event.target.files && event.target.files[0];
  $("#pdf-file-name").textContent = selectedPdf ? selectedPdf.name : "Choose a PDF form";
  $("#inspect-pdf-button").disabled = !selectedPdf;
  $("#pdf-fields-panel").hidden = true;
  $("#pdf-download-panel").hidden = true;
  showAlert("");
});
$("#inspect-pdf-button").addEventListener("click", inspectPdf);
$("#fill-pdf-button").addEventListener("click", fillPdf);
