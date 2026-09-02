const API = window.location.origin;

let sessionId = null;
let language = "en";
let selectedFiles = [];
let services = [];
let activeServiceId = null;

const $ = (selector) => document.querySelector(selector);

async function api(path, method = "GET", body = null) {
  const options = { method, headers: { "Content-Type": "application/json" } };
  if (body !== null) options.body = JSON.stringify(body);
  const response = await fetch(API + path, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || "Something went wrong. Please try again.");
  }
  return response.json();
}

function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = "toast " + type;
  toast.textContent = message;
  $("#toast-region").appendChild(toast);
  window.setTimeout(() => toast.remove(), 4200);
}

function addMessage(role, text) {
  const article = document.createElement("article");
  article.className = "chat-message " + (role === "user" ? "user-message" : "assistant-message");
  if (role !== "user") {
    const avatar = document.createElement("span");
    avatar.className = "avatar";
    avatar.textContent = "AI";
    article.appendChild(avatar);
  }
  const content = document.createElement("div");
  if (role !== "user") {
    const label = document.createElement("strong");
    label.textContent = "JanSeva Assistant";
    content.appendChild(label);
  }
  const message = document.createElement("p");
  message.textContent = text;
  content.appendChild(message);
  article.appendChild(content);
  const chat = $("#chat-log");
  chat.appendChild(article);
  chat.scrollTop = chat.scrollHeight;
}

function numberValue(name) {
  const raw = $('[name="' + name + '"]').value.trim();
  return raw === "" ? null : Number(raw);
}

function profilePayload() {
  const checked = (name) => $('[name="' + name + '"]').checked;
  const girlChildAge = numberValue("girl_child_age");
  return {
    name: $("#profile-name").value.trim(),
    age: numberValue("age"),
    gender: $("#profile-gender").value,
    state: $("#profile-state").value,
    occupation: $("#profile-occupation").value,
    annual_income: numberValue("annual_income"),
    caste_category: $("#profile-category").value,
    land_acres: numberValue("land_acres") || 0,
    employment_sector: $("#profile-sector").value,
    house_type: $("#profile-house").value,
    is_bpl: checked("is_bpl"),
    has_lpg_connection: checked("has_lpg_connection"),
    is_student: checked("is_student"),
    is_entrepreneur: checked("is_entrepreneur"),
    is_pregnant: checked("is_pregnant"),
    is_first_child: checked("is_first_child"),
    children: girlChildAge === null ? [] : [{ gender: "female", age: girlChildAge }],
  };
}

function updateReadiness() {
  const data = profilePayload();
  const fields = [data.name, data.age, data.gender, data.state, data.occupation, data.annual_income];
  const complete = fields.filter((value) => value !== null && value !== "").length;
  const percentage = Math.round((complete / fields.length) * 100);
  const remaining = 6 - complete;
  $("#readiness-score").textContent = percentage + "%";
  $("#readiness-bar").style.width = percentage + "%";
  $("#readiness-text").textContent = percentage === 100
    ? "Your profile is ready for personalised guidance"
    : remaining + " key detail" + (remaining === 1 ? "" : "s") + " remaining";
}

function renderSchemes(schemes) {
  const grid = $("#scheme-grid");
  $("#scheme-count").textContent = schemes.length + " match" + (schemes.length === 1 ? "" : "es");
  grid.innerHTML = "";
  if (!schemes.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.innerHTML = "<strong>No verified matches yet.</strong><p>Add more profile details, then ask the assistant to check schemes again.</p>";
    grid.appendChild(empty);
    return;
  }
  schemes.forEach((scheme) => {
    const card = document.createElement("article");
    card.className = "scheme-card" + (scheme.verify_manually ? " manual" : "");
    if (scheme.verify_manually) {
      const note = document.createElement("span");
      note.className = "manual-note";
      note.textContent = "VERIFY WITH OFFICE";
      card.appendChild(note);
    }
    const title = document.createElement("h3");
    title.textContent = scheme.scheme_name;
    const reason = document.createElement("p");
    reason.className = "reason";
    reason.textContent = scheme.eligibility_reason || "Potential match based on the information provided.";
    card.append(title, reason);
    [["BENEFIT", scheme.estimated_benefit || "Confirm benefit with the authority"], ["HOW TO APPLY", scheme.how_to_apply || "Visit the nearest government office or CSC"]].forEach(([label, value]) => {
      const detail = document.createElement("div");
      detail.className = "scheme-detail";
      const caption = document.createElement("span");
      caption.textContent = label;
      const text = document.createElement("strong");
      text.textContent = value;
      detail.append(caption, text);
      card.appendChild(detail);
    });
    grid.appendChild(card);
  });
}

async function saveProfile({ quiet = false } = {}) {
  if (!sessionId) throw new Error("Your session is still starting. Please wait a moment.");
  const result = await api("/sessions/" + sessionId + "/profile", "POST", profilePayload());
  renderSchemes(result.schemes_found || []);
  updateReadiness();
  await loadServices();
  if (!quiet) showToast("Your details were saved and eligibility was checked.", "success");
  return result;
}

function renderServices() {
  const container = $("#service-list");
  container.innerHTML = "";
  if (!services.length) {
    container.innerHTML = '<p class="muted">No services are currently available for this state.</p>';
    return;
  }
  services.forEach((service) => {
    const button = document.createElement("button");
    button.className = "service-button" + (service.id === activeServiceId ? " selected" : "");
    button.type = "button";
    button.textContent = service.label;
    button.addEventListener("click", () => selectService(service.id));
    container.appendChild(button);
  });
}

async function loadServices() {
  if (!sessionId) return;
  const state = $("#profile-state").value;
  const query = state ? "?state=" + encodeURIComponent(state) : "";
  services = await api("/services" + query);
  renderServices();
}

async function selectService(serviceId) {
  try {
    const result = await api("/sessions/" + sessionId + "/service", "POST", { service_id: serviceId });
    activeServiceId = serviceId;
    renderServices();
    const summary = result.summary;
    const checklist = $("#service-checklist");
    checklist.hidden = false;
    checklist.innerHTML = "";
    const title = document.createElement("h3");
    title.textContent = summary.service;
    const meta = document.createElement("div");
    meta.className = "service-meta";
    ["Fee: " + (summary.fee || "Check office"), "Processing: " + (summary.processing || "Check office"), "Validity: " + (summary.validity || "Check office")].forEach((item) => {
      const chip = document.createElement("span");
      chip.textContent = item;
      meta.appendChild(chip);
    });
    const list = document.createElement("ul");
    (summary.items || []).forEach((item) => {
      const entry = document.createElement("li");
      entry.textContent = item.name;
      list.appendChild(entry);
    });
    checklist.append(title, meta, list);
    addMessage("assistant", "I have prepared the checklist for " + summary.service + ". You can review it in the Services panel.");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function renderDocuments() {
  const list = $("#document-list");
  $("#document-count").textContent = selectedFiles.length + " file" + (selectedFiles.length === 1 ? "" : "s");
  $("#scan-documents-button").disabled = selectedFiles.length === 0;
  if (!selectedFiles.length) {
    list.innerHTML = '<p class="empty-documents">No documents added yet.</p>';
    return;
  }
  list.innerHTML = "";
  selectedFiles.forEach((file, index) => {
    const item = document.createElement("div");
    item.className = "document-item";
    const info = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = file.name;
    const size = document.createElement("small");
    size.textContent = Math.max(1, Math.round(file.size / 1024)) + " KB";
    info.append(name, size);
    const remove = document.createElement("button");
    remove.className = "remove-document";
    remove.type = "button";
    remove.setAttribute("aria-label", "Remove " + file.name);
    remove.textContent = "x";
    remove.addEventListener("click", () => {
      selectedFiles.splice(index, 1);
      renderDocuments();
    });
    item.append(info, remove);
    list.appendChild(item);
  });
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Could not read " + file.name));
    reader.readAsDataURL(file);
  });
}

async function extractDocuments() {
  if (!selectedFiles.length) return;
  const button = $("#scan-documents-button");
  button.disabled = true;
  button.textContent = "Extracting details...";
  $("#scan-status").textContent = "Reading the uploaded images securely...";
  try {
    const images = await Promise.all(selectedFiles.map(async (file) => ({ name: file.name, data: await readFileAsDataUrl(file) })));
    const result = await api("/sessions/" + sessionId + "/scan", "POST", { expected_type: "document", images });
    applyExtractedFields(result.summary || {});
    updateReadiness();
    $("#scan-status").textContent = "Details extracted. Please review your profile before checking schemes.";
    showToast("Document details have been added to the profile.", "success");
    addMessage("assistant", "I extracted the available document details. Please check the profile fields and correct anything that looks wrong.");
  } catch (error) {
    $("#scan-status").textContent = "Could not extract details. You can still enter them manually.";
    showToast(error.message, "error");
  } finally {
    button.disabled = selectedFiles.length === 0;
    button.textContent = "Extract document details";
  }
}

function applyExtractedFields(fields) {
  const bindings = {
    name: "#profile-name", age: "#profile-age", gender: "#profile-gender",
    state: "#profile-state", occupation: "#profile-occupation",
    annual_income: "#profile-income", caste_category: "#profile-category",
    land_acres: "#profile-land",
  };
  Object.entries(bindings).forEach(([field, selector]) => {
    if (fields[field] !== undefined && fields[field] !== null && fields[field] !== "") {
      $(selector).value = fields[field];
    }
  });
}

async function askAssistant(message) {
  const question = message.trim();
  if (!question) return;
  addMessage("user", question);
  $("#assistant-input").value = "";
  try {
    await saveProfile({ quiet: true });
    const result = await api("/sessions/" + sessionId + "/assistant", "POST", { message: question });
    addMessage("assistant", result.reply);
    renderSchemes(result.recommendations || []);
    if (result.profile_gaps && result.profile_gaps.length) {
      showToast("For better matches, add: " + result.profile_gaps.join(", ") + ".", "info");
    }
  } catch (error) {
    addMessage("assistant", "I could not process that request right now. Please check your details and try again.");
    showToast(error.message, "error");
  }
}

async function changeLanguage() {
  language = $("#language-select").value;
  try {
    await api("/sessions/" + sessionId + "/language", "POST", { language });
    showToast("Language preference saved.", "success");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function endSession() {
  if (!sessionId || !window.confirm("End this session and erase its saved session data?")) return;
  try {
    await api("/sessions/" + sessionId, "DELETE");
    sessionId = null;
    selectedFiles = [];
    renderDocuments();
    renderSchemes([]);
    $("#session-status").textContent = "Session erased. Starting a new one...";
    await startSession();
    addMessage("assistant", "Your previous session was erased. A new private session is ready.");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function startSession() {
  const session = await api("/sessions", "POST");
  sessionId = session.session_id;
  await api("/sessions/" + sessionId + "/language", "POST", { language });
  $("#session-status").textContent = "Secure session active";
  await loadServices();
  updateReadiness();
}

function bindEvents() {
  $("#assistant-form").addEventListener("submit", (event) => {
    event.preventDefault();
    askAssistant($("#assistant-input").value);
  });
  document.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => askAssistant(button.dataset.prompt));
  });
  $("#save-profile-button").addEventListener("click", () => saveProfile().catch((error) => showToast(error.message, "error")));
  $("#check-eligibility-button").addEventListener("click", () => saveProfile().catch((error) => showToast(error.message, "error")));
  $("#language-select").addEventListener("change", changeLanguage);
  $("#profile-state").addEventListener("change", () => loadServices().catch((error) => showToast(error.message, "error")));
  $("#profile-form").addEventListener("input", updateReadiness);
  $("#document-input").addEventListener("change", (event) => {
    selectedFiles = selectedFiles.concat(Array.from(event.target.files || []));
    event.target.value = "";
    renderDocuments();
  });
  $("#scan-documents-button").addEventListener("click", extractDocuments);
  $("#end-session-button").addEventListener("click", endSession);
}

window.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  renderDocuments();
  updateReadiness();
  try {
    await startSession();
  } catch (error) {
    $("#session-status").textContent = "Could not start a session";
    showToast("Unable to connect to the server: " + error.message, "error");
  }
});
