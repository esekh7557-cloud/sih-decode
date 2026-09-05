const API = window.location.origin;
const SESSION_STORAGE_KEY = "janseva.session.id";
const APPLICATION_DRAFT_STORAGE_KEY = "janseva.application.draft";
const PORTAL_OPEN_STORAGE_KEY = "janseva.application.portal-open";
const APPLICATION_STAGE_STORAGE_KEY = "janseva.application.stage";
const APPLICATION_FLASH_STORAGE_KEY = "janseva.application.flash";
const params = new URLSearchParams(window.location.search);
const APPLICATION_STEPS = ["portal", "documents", "details", "review", "submit"];
const pathStep = window.location.pathname.split("/").filter(Boolean)[1];
const currentStep = APPLICATION_STEPS.includes(pathStep) ? pathStep : "portal";

let sessionId = localStorage.getItem(SESSION_STORAGE_KEY);
let applicationPlan = null;
let portalOpened = false;
let applicationStage = sessionStorage.getItem(APPLICATION_STAGE_STORAGE_KEY) || "upload";
let selectedFiles = [];
let requiredApplicationDocuments = [];
let savedExtractedData = {};
let additionalDocumentData = [];

function documentTypesFor(item) {
  const types = Array.isArray(item.documentTypes)
    ? item.documentTypes
    : (item.documentType ? [item.documentType] : []);
  return Array.from(new Set(types.filter(Boolean)));
}

function setDocumentTypes(item, types) {
  item.documentTypes = Array.from(new Set(types.filter(Boolean)));
  item.documentType = item.documentTypes[0] || "";
}

const $ = (selector) => document.querySelector(selector);

function applicationStepUrl(step, plan = applicationPlan) {
  const query = new URLSearchParams();
  if ((plan && plan.application_type === "live_guidance") || params.get("live") === "1") {
    query.set("live", "1");
  } else {
    const serviceId = (plan && plan.service_id) || params.get("service");
    if (serviceId) query.set("service", serviceId);
  }
  return "/application/" + step + (query.toString() ? "?" + query.toString() : "");
}

async function persistApplicationDraft() {
  if (!selectedFiles.length) {
    sessionStorage.removeItem(APPLICATION_DRAFT_STORAGE_KEY);
    return;
  }
  try {
    const draft = await Promise.all(selectedFiles.map(async (item) => ({
      name: item.file.name,
      type: item.file.type,
      documentType: item.documentType || "",
      documentTypes: documentTypesFor(item),
      data: await readFileAsDataUrl(item.file),
    })));
    sessionStorage.setItem(APPLICATION_DRAFT_STORAGE_KEY, JSON.stringify(draft));
  } catch (_) {
    // Extracted files remain in the private backend session if this draft is too large.
  }
}

async function goToApplicationStep(step, message = "") {
  if (message) sessionStorage.setItem(APPLICATION_FLASH_STORAGE_KEY, message);
  await persistApplicationDraft();
  window.location.assign(applicationStepUrl(step));
}

async function api(path, method = "GET", body = null) {
  const options = { method, headers: { "Content-Type": "application/json" } };
  if (body !== null) options.body = JSON.stringify(body);
  const response = await fetch(API + path, options);
  let payload = null;
  try {
    payload = await response.json();
  } catch (_) {
    payload = null;
  }
  if (!response.ok) throw new Error((payload && (payload.detail || payload.message)) || "The server could not complete this step.");
  return payload;
}

function showAlert(message, type = "info") {
  const alert = $("#application-alert");
  if (!alert) return;
  alert.hidden = !message;
  alert.className = "application-alert" + (type === "error" ? " error" : type === "success" ? " success" : "");
  alert.textContent = message || "";
}

function setProgress(step) {
  const order = ["portal", "documents", "details", "review", "submit"];
  const activeIndex = order.indexOf(step);
  order.forEach((name, index) => {
    const item = $("#progress-" + name);
    if (!item) return;
    item.classList.toggle("complete", index < activeIndex);
    item.classList.toggle("active", index === activeIndex);
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

function dataUrlToFile(item) {
  const parts = String(item.data || "").split(",");
  if (parts.length !== 2) return null;
  const mime = (parts[0].match(/data:(.*?);base64/) || [])[1] || "image/png";
  const binary = atob(parts[1]);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return new File([bytes], item.name || "document.png", { type: mime });
}

async function restoreDraftDocuments() {
  const raw = sessionStorage.getItem(APPLICATION_DRAFT_STORAGE_KEY);
  if (!raw) return;
  try {
    const draft = JSON.parse(raw);
    selectedFiles = (Array.isArray(draft) ? draft : [])
      .map((item) => ({ file: dataUrlToFile(item), documentType: item.documentType || "", documentTypes: item.documentTypes || [] }))
      .filter((item) => item.file);
  } catch (_) {
    sessionStorage.removeItem(APPLICATION_DRAFT_STORAGE_KEY);
  }
}

function documentMatchesRequirement(type, requirement) {
  const typeText = String(type || "").toLowerCase();
  const requirementText = String(requirement || "").toLowerCase();
  if (requirementText.includes("aadhaar") || requirementText.includes("aadhar")) return typeText.includes("aadhaar") || typeText.includes("aadhar");
  if (requirementText.includes("pan")) return typeText.includes("pan");
  if (requirementText.includes("voter") || requirementText.includes("identity") || requirementText.includes("id proof")) return /voter|aadhaar|aadhar|pan|identity|id/.test(typeText);
  if (requirementText.includes("birth") || requirementText.includes("school leaving")) return /birth|school|bonafide/.test(typeText);
  if (requirementText.includes("residence") || requirementText.includes("address")) return /residence|address|bonafide/.test(typeText);
  if (requirementText.includes("photograph") || requirementText.includes("photo")) return /photograph|photo/.test(typeText);
  if (requirementText.includes("income")) return typeText.includes("income");
  if (requirementText.includes("caste") || requirementText.includes("category")) return /caste|category/.test(typeText);
  return typeText === requirementText;
}

function renderRequirements(plan) {
  requiredApplicationDocuments = Array.from(new Set((plan.documents || []).filter(Boolean)));
  const request = $("#application-document-request");
  const list = $("#application-document-requirements");
  const instructions = $("#document-instructions");
  if (!request || !list || !instructions) return;
  request.hidden = requiredApplicationDocuments.length === 0;
  list.innerHTML = "";
  if (!requiredApplicationDocuments.length) {
    instructions.textContent = plan.form_scanned
      ? "The portal did not expose document rows. Confirm the latest requirements on the official page before applying."
      : "Saarthi will read the required document rows after you open the logged-in application form.";
    renderDocuments();
    renderDocumentUploadDecision(plan);
    return;
  }
  instructions.textContent = plan.form_scanned
    ? "These requirements were read from the official application form. Add and label every document you have."
    : "These are the currently configured requirements. Saarthi will check the official form for any additional documents after login.";
  $("#application-document-title").textContent = "Documents required for " + (plan.service || "your application");
  requiredApplicationDocuments.forEach((name) => {
    const item = document.createElement("li");
    item.textContent = name;
    list.appendChild(item);
  });
  renderDocuments();
  renderDocumentUploadDecision(plan);
}

function renderDocumentUploadDecision(plan) {
  const panel = $("#application-documents-panel");
  const instructions = $("#document-instructions");
  const zone = panel && panel.querySelector(".upload-zone");
  const list = $("#document-list");
  const scan = $("#scan-documents-button");
  if (!panel || !instructions || !zone || !list || !scan) return;
  const unavailable = Boolean(plan.form_scanned && plan.document_uploads_detected === false);
  const decisionKey = "janseva.application.documents-needed." + (plan.service_id || "application");
  const old = panel.querySelector(".document-upload-decision");
  if (old) old.remove();
  if (!unavailable) {
    [zone, list, scan].forEach((node) => { node.hidden = false; });
    return;
  }

  const decision = document.createElement("section");
  decision.className = "document-upload-decision application-step";
  const title = document.createElement("h4");
  title.textContent = "This form has no document-upload field";
  const copy = document.createElement("p");
  copy.textContent = "Do you still need to prepare supporting documents for this application?";
  const actions = document.createElement("div");
  actions.className = "button-row";
  const yes = document.createElement("button");
  yes.type = "button";
  yes.className = "secondary-button";
  yes.textContent = "Yes, prepare documents";
  const no = document.createElement("button");
  no.type = "button";
  no.className = "secondary-button";
  no.textContent = "No documents needed";
  const setDecision = (needed) => {
    sessionStorage.setItem(decisionKey, needed ? "yes" : "no");
    [zone, list, scan].forEach((node) => { node.hidden = !needed; });
    instructions.textContent = needed
      ? "Prepare these supporting documents for your records or any manual upload the authority requests."
      : "No document preparation was selected. Continue to the remaining application details.";
    yes.disabled = needed;
    no.disabled = !needed;
  };
  yes.addEventListener("click", () => setDecision(true));
  no.addEventListener("click", () => setDecision(false));
  actions.append(yes, no);
  decision.append(title, copy, actions);
  panel.insertBefore(decision, zone);
  const saved = sessionStorage.getItem(decisionKey);
  if (saved === "yes") setDecision(true);
  else if (saved === "no") setDecision(false);
  else {
    [zone, list, scan].forEach((node) => { node.hidden = true; });
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
  const choices = Array.from(new Set(requiredApplicationDocuments.concat([
    "Aadhaar Card", "PAN Card", "Voter ID Card", "Photograph", "Income Certificate",
    "Residence Certificate", "Caste Certificate", "Birth Certificate", "Ration Card", "Other Document",
  ])));
  selectedFiles.forEach((item, index) => {
    const row = document.createElement("div");
    row.className = "document-item";
    const info = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = item.file.name;
    const size = document.createElement("small");
    size.textContent = Math.max(1, Math.round(item.file.size / 1024)) + " KB";
    info.append(name, size);
    const assignments = document.createElement("fieldset");
    assignments.className = "document-type-options";
    const legend = document.createElement("legend");
    legend.textContent = SaarthiI18n.t("documentUses");
    assignments.appendChild(legend);
    choices.forEach((choice) => {
      const label = document.createElement("label");
      label.className = "document-type-choice";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = choice;
      checkbox.checked = documentTypesFor(item).includes(choice);
      checkbox.addEventListener("change", () => {
        setDocumentTypes(selectedFiles[index], Array.from(assignments.querySelectorAll("input:checked")).map((input) => input.value));
      });
      const text = document.createElement("span");
      text.textContent = choice;
      label.append(checkbox, text);
      assignments.appendChild(label);
    });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove-document";
    remove.textContent = "x";
    remove.setAttribute("aria-label", "Remove " + item.file.name);
    remove.addEventListener("click", () => { selectedFiles.splice(index, 1); renderDocuments(); });
    row.append(info, assignments, remove);
    list.appendChild(row);
  });
}

function renderExtractedData() {
  const saved = $("#saved-data");
  const savedList = $("#saved-data-list");
  const entries = Object.entries(savedExtractedData).filter(([key, value]) => key !== "action" && value !== "");
  saved.hidden = entries.length === 0;
  savedList.innerHTML = "";
  entries.forEach(([key, value]) => {
    const item = document.createElement("div");
    item.className = "saved-data-row";
    item.textContent = key.replace(/_/g, " ") + ": " + value;
    savedList.appendChild(item);
  });
  const additional = $("#additional-data");
  const additionalList = $("#additional-data-list");
  additional.hidden = additionalDocumentData.length === 0;
  additionalList.innerHTML = "";
  additionalDocumentData.forEach((entry) => {
    const item = document.createElement("div");
    item.className = "saved-data-row";
    item.textContent = entry.documentType + ": " + Object.entries(entry.fields).map(([key, value]) => key.replace(/_/g, " ") + " = " + value).join(", ");
    additionalList.appendChild(item);
  });
}

function setPlanHeader(plan) {
  $("#application-page-title").textContent = plan.service + " with Saarthi";
  const metadata = {
    portal: ["STEP 1", plan.service + " official portal", portalOpened ? "Portal opened" : "Login required"],
    documents: ["STEP 2", "Upload required documents", (plan.documents || []).length + " required"],
    details: ["STEP 3", "Complete missing application details", (plan.missing_fields || []).length + " missing"],
    review: ["STEP 4", "Review and fill the official form", "Review required"],
    submit: ["STEP 5", "Upload, pay, and submit", "Your approval"],
  }[currentStep];
  $("#application-step-eyebrow").textContent = metadata[0];
  $("#application-portal-title").textContent = metadata[1];
  const status = $("#portal-status");
  status.textContent = metadata[2];
  status.className = "application-badge " + (currentStep !== "portal" || portalOpened ? "ready" : "waiting");
  const portalLink = $("#application-portal-link");
  if (portalLink) portalLink.href = plan.portal_url || "#";
}

function makeOfficialLink(plan) {
  const link = document.createElement("a");
  link.className = "official-portal-link";
  link.href = plan.portal_url || "#";
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = plan.portal_url ? "View official portal in a new tab" : "Official portal link unavailable";
  return link;
}

function launchPath() {
  return applicationPlan.application_type === "live_guidance"
    ? "/sessions/" + sessionId + "/live-application/launch"
    : "/sessions/" + sessionId + "/launch_browser";
}

async function launchOfficialPortal(button = null) {
  if (!applicationPlan || !applicationPlan.portal_url) {
    showAlert("This application does not have a verified official portal URL yet.", "error");
    return;
  }
  if (button) {
    button.disabled = true;
    button.textContent = "Opening Google Chrome...";
  }
  try {
    const result = await api(launchPath(), "POST", applicationPlan.application_type === "live_guidance" ? null : { service_id: applicationPlan.service_id });
    portalOpened = true;
    localStorage.setItem(PORTAL_OPEN_STORAGE_KEY, applicationPlan.portal_url);
    showAlert(result.message || "The official portal was opened in Google Chrome.", "success");
    renderPlan(applicationPlan);
  } catch (error) {
    if (button) {
      button.disabled = false;
      button.textContent = "Open official portal and log in";
    }
    showAlert(error.message, "error");
  }
}

async function scanOpenForm(button) {
  if (!portalOpened) {
    showAlert("Open the official portal, log in yourself, and then try the form scan.", "info");
    return;
  }
  button.disabled = true;
  button.textContent = "Checking the logged-in form...";
  try {
    const path = applicationPlan.application_type === "live_guidance"
      ? "/sessions/" + sessionId + "/live-application/scan-open-form"
      : "/sessions/" + sessionId + "/applications/" + encodeURIComponent(applicationPlan.service_id) + "/scan-open-form";
    applicationPlan = await api(path, "POST");
    await goToApplicationStep("documents", applicationPlan.scan_message || "Login confirmed. Upload the required documents now.");
  } catch (error) {
    button.disabled = false;
    button.textContent = "I am logged in — continue to documents";
    showAlert(error.message, "error");
  }
}

function renderPortalStep(plan) {
  const flow = $("#application-flow");
  flow.innerHTML = "";
  const overview = document.createElement("section");
  overview.className = "application-step";
  const title = document.createElement("h3");
  title.textContent = "Open the official portal";
  const copy = document.createElement("p");
  copy.textContent = "Saarthi opens the official website in Google Chrome. Log in, complete OTP or CAPTCHA yourself, and open the actual application form.";
  overview.append(title, copy, makeOfficialLink(plan));
  const open = document.createElement("button");
  open.type = "button";
  open.className = "primary-button full-width";
  open.textContent = portalOpened ? "Official portal opened" : "Open official portal and log in";
  open.disabled = portalOpened;
  open.addEventListener("click", () => launchOfficialPortal(open));
  overview.appendChild(open);
  flow.appendChild(overview);

  if (!plan.form_scanned) {
    const scan = document.createElement("section");
    scan.className = "application-step";
    const scanTitle = document.createElement("h4");
    scanTitle.textContent = "Check the application form requirements";
    const scanCopy = document.createElement("p");
    scanCopy.textContent = "After login, navigate to the correct application form. Saarthi will read visible field labels, required markers, dropdown choices, and document upload rows from that page.";
    const scanButton = document.createElement("button");
    scanButton.type = "button";
    scanButton.className = "secondary-button full-width";
    scanButton.textContent = "I am logged in — continue to documents";
    scanButton.disabled = !portalOpened;
    scanButton.addEventListener("click", () => scanOpenForm(scanButton));
    scan.append(scanTitle, scanCopy, scanButton);
    flow.appendChild(scan);
    setProgress("portal");
    return;
  }

  const scanned = document.createElement("p");
  scanned.className = "ready-message";
  scanned.textContent = "Saarthi found the requirements on " + ((plan.scanned_form && plan.scanned_form.title) || "the opened application form") + ".";
  flow.appendChild(scanned);
  const recheck = document.createElement("button");
  recheck.type = "button";
  recheck.className = "secondary-button full-width";
  recheck.textContent = "Recheck form requirements";
  recheck.disabled = !portalOpened;
  recheck.addEventListener("click", () => scanOpenForm(recheck));
  flow.appendChild(recheck);
  const next = document.createElement("button");
  next.type = "button";
  next.className = "primary-button full-width";
  next.textContent = "Continue to required documents";
  next.addEventListener("click", () => goToApplicationStep("documents"));
  flow.appendChild(next);
  setProgress("portal");
}

function fieldOptions(field) {
  return (Array.isArray(field.options) ? field.options : [])
    .map((option) => {
      if (option && typeof option === "object") {
        const value = String(option.value ?? option.label ?? "");
        return { value, label: String(option.label ?? value) };
      }
      return { value: String(option), label: String(option) };
    })
    .filter((option) => option.value && option.label);
}

function applyFieldConstraints(input, field) {
  if (field.placeholder) input.placeholder = field.placeholder;
  if (field.min !== undefined && field.min !== "") input.min = field.min;
  if (field.max !== undefined && field.max !== "") input.max = field.max;
  if (field.step) input.step = field.step;
  if (field.pattern) input.pattern = field.pattern;
  if (field.max_length) input.maxLength = Number(field.max_length);
}

function choiceControl(field, options, multiple = false) {
  const choices = document.createElement("fieldset");
  choices.className = "question-choices";
  choices.dataset.choiceRequired = field.required ? "true" : "false";
  choices.dataset.fieldKey = field.key;
  const legend = document.createElement("legend");
  legend.textContent = field.label;
  choices.appendChild(legend);
  options.forEach((option) => {
    const choice = document.createElement("label");
    choice.className = "question-choice";
    const control = document.createElement("input");
    control.type = multiple ? "checkbox" : "radio";
    control.name = field.key;
    control.value = option.value;
    control.required = field.required && !multiple;
    const text = document.createElement("span");
    text.textContent = option.label;
    choice.append(control, text);
    choices.appendChild(choice);
  });
  return choices;
}

function answersFromDetailForm(form) {
  const answers = {};
  for (const [key, value] of new FormData(form).entries()) {
    if (Object.prototype.hasOwnProperty.call(answers, key)) {
      answers[key] = Array.isArray(answers[key]) ? answers[key].concat(value) : [answers[key], value];
    } else {
      answers[key] = value;
    }
  }
  form.querySelectorAll("[data-choice-required='true']").forEach((group) => {
    const selected = group.querySelector("input:checked");
    if (!selected) group.classList.add("question-choices-error");
    else group.classList.remove("question-choices-error");
  });
  return answers;
}

function hasUnansweredRequiredChoices(form) {
  return Array.from(form.querySelectorAll("[data-choice-required='true']"))
    .some((group) => !group.querySelector("input:checked"));
}

function renderMissingDetails(flow, plan) {
  const details = document.createElement("section");
  details.className = "application-step application-details";
  const title = document.createElement("h4");
  title.textContent = "Details not found in your documents";
  const copy = document.createElement("p");
  copy.textContent = "Please provide these required answers. Saarthi will not invent information that is missing from your profile or documents.";
  const recheck = document.createElement("button");
  recheck.type = "button";
  recheck.className = "secondary-button full-width";
  recheck.textContent = plan.form_scanned
    ? "Recheck choices from the official form"
    : "Scan choices from the official form";
  recheck.disabled = !portalOpened;
  recheck.addEventListener("click", () => scanOpenForm(recheck));
  const missingFields = (plan.fields || []).filter((field) => field.missing);
  if (!missingFields.length) {
    copy.textContent = "Saarthi found all required details in your saved profile and uploaded documents.";
    const next = document.createElement("button");
    next.type = "button";
    next.className = "primary-button full-width";
    next.textContent = "Continue to review";
    next.addEventListener("click", () => goToApplicationStep("review"));
    details.append(title, copy, recheck, next);
    flow.appendChild(details);
    return;
  }
  const currentField = missingFields[0];
  title.textContent = currentField.label;
  copy.textContent = missingFields.length + " required answer" + (missingFields.length === 1 ? " remains." : "s remain. Answer this one and Saarthi will ask the next.");
  const form = document.createElement("form");
  form.className = "application-detail-form";
  [currentField].forEach((field) => {
    const options = fieldOptions(field);
    const kind = String(field.type || "text").toLowerCase();
    if (kind === "radio") {
      form.appendChild(choiceControl(field, options, false));
      return;
    }
    if (kind === "checkbox" || kind === "multi_select") {
      form.appendChild(choiceControl(field, options.length ? options : [{ value: "true", label: field.label }], true));
      return;
    }

    const group = document.createElement("label");
    group.className = "field-group";
    const label = document.createElement("span");
    label.textContent = field.label;
    group.appendChild(label);
    let input;
    // Some portals expose a list of choices alongside a control they label
    // as text (for example a custom Purpose picker). Detected choices are
    // authoritative, so present them instead of an unrestricted text box.
    if ((kind === "select" || options.length) && options.length) {
      input = document.createElement("select");
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "Select an option";
      input.appendChild(placeholder);
      options.forEach((option) => {
        const choice = document.createElement("option");
        choice.value = option.value;
        choice.textContent = option.label;
        input.appendChild(choice);
      });
    } else if (kind === "textarea") {
      input = document.createElement("textarea");
    } else {
      input = document.createElement("input");
      const supported = new Set(["date", "datetime-local", "email", "month", "number", "range", "tel", "time", "url", "week"]);
      input.type = supported.has(kind) ? kind : "text";
      if (kind === "number") input.inputMode = "decimal";
    }
    input.name = field.key;
    input.required = field.required;
    input.autocomplete = "off";
    applyFieldConstraints(input, field);
    group.appendChild(input);
    form.appendChild(group);
  });
  const save = document.createElement("button");
  save.type = "submit";
  save.className = "secondary-button full-width";
  save.textContent = missingFields.length === 1 ? "Save and continue to review" : "Save and ask the next question";
  form.appendChild(save);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    if (hasUnansweredRequiredChoices(form)) {
      answersFromDetailForm(form);
      showAlert("Choose at least one option before continuing.", "info");
      return;
    }
    save.disabled = true;
    try {
      const path = plan.application_type === "live_guidance"
        ? "/sessions/" + sessionId + "/live-application/details"
        : "/sessions/" + sessionId + "/applications/" + encodeURIComponent(plan.service_id) + "/details";
      applicationPlan = await api(path, "POST", { details: answersFromDetailForm(form) });
      if (applicationPlan.missing_fields && applicationPlan.missing_fields.length) {
        showAlert("Answer saved. Here is the next missing detail.", "success");
        renderPlan(applicationPlan);
      } else {
        await goToApplicationStep("review", "All missing details are saved. Review every value before Saarthi fills the official form.");
      }
    } catch (error) {
      save.disabled = false;
      showAlert(error.message, "error");
    }
  });
  details.append(title, copy, recheck, form);
  flow.appendChild(details);
}

function renderReviewStep(flow, plan) {
  const review = document.createElement("section");
  review.className = "application-step application-review";
  const title = document.createElement("h4");
  title.textContent = "Review the details Saarthi will fill";
  const copy = document.createElement("p");
  copy.textContent = "Check every value carefully. Saarthi fills only these reviewed visible fields and never reads passwords, OTPs, CAPTCHAs, or existing portal values.";
  const list = document.createElement("dl");
  list.className = "review-list";
  (plan.fields || []).forEach((field) => {
    const row = document.createElement("div");
    const label = document.createElement("dt");
    label.textContent = field.label;
    const value = document.createElement("dd");
    value.textContent = Array.isArray(field.value) ? field.value.join(", ") : (field.value || "Not provided");
    row.append(label, value);
    list.appendChild(row);
  });
  const confirm = document.createElement("label");
  confirm.className = "check-control review-confirm";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  const confirmText = document.createElement("span");
  confirmText.textContent = "I reviewed these details and want Saarthi to fill the opened official form.";
  confirm.append(checkbox, confirmText);
  const fill = document.createElement("button");
  fill.type = "button";
  fill.className = "primary-button full-width";
  fill.textContent = "Fill the reviewed form";
  fill.disabled = !portalOpened;
  fill.addEventListener("click", async () => {
    if (!checkbox.checked) {
      showAlert("Please confirm that you reviewed the details first.", "info");
      return;
    }
    fill.disabled = true;
    fill.textContent = "Filling the official form...";
    try {
      const path = plan.application_type === "live_guidance"
        ? "/sessions/" + sessionId + "/live-application/automate-fill"
        : "/sessions/" + sessionId + "/automate_fill";
      const result = await api(path, "POST", plan.application_type === "live_guidance" ? null : { service_id: plan.service_id });
      fill.textContent = "Fields filled — review in Chrome";
      const stopped = document.createElement("p");
      stopped.className = "ready-message";
      stopped.textContent = result.message || "The reviewed fields were filled. Saarthi did not click Save, Continue, Proceed, Upload, or Submit.";
      review.appendChild(stopped);
      if (!(plan.form_scanned && plan.document_uploads_detected === false)) {
        const documents = document.createElement("button");
        documents.type = "button";
        documents.className = "secondary-button full-width";
        documents.textContent = "I reviewed the filled portal form — manage documents";
        documents.addEventListener("click", async () => {
          applicationStage = "upload";
          sessionStorage.setItem(APPLICATION_STAGE_STORAGE_KEY, applicationStage);
          await goToApplicationStep("submit", "Form review confirmed. Document tools are ready when you need them.");
        });
        review.appendChild(documents);
      }
      showAlert("Fields filled. Saarthi stopped without saving or continuing the official form.", "success");
    } catch (error) {
      fill.disabled = false;
      fill.textContent = "Fill the reviewed form";
      showAlert(error.message, "error");
    }
  });
  review.append(title, copy, list, confirm, fill);
  flow.appendChild(review);
}

function renderUploadStep(flow, plan) {
  const step = document.createElement("section");
  step.className = "application-step upload-after-review";
  const title = document.createElement("h4");
  title.textContent = applicationStage === "submit" ? "Documents upload started" : "Review the form, then upload documents";
  const copy = document.createElement("p");
  if (plan.form_scanned && plan.document_uploads_detected === false) {
    copy.textContent = "The scanned official form has no document-upload field. Review the filled form and continue on the portal when ready.";
    step.append(title, copy);
    flow.appendChild(step);
    return;
  }
  copy.textContent = applicationStage === "submit"
    ? "Review the official portal while the scanned files are uploaded. Saarthi will not submit the application or handle payment."
    : "Review every value in the official portal first. When you are on its document-upload page, start the upload of the scanned documents.";
  step.append(title, copy);
  if (applicationStage === "upload") {
    const upload = document.createElement("button");
    upload.type = "button";
    upload.className = "secondary-button full-width";
    upload.textContent = "I reviewed the form — upload documents";
    upload.addEventListener("click", async () => {
      upload.disabled = true;
      upload.textContent = "Uploading scanned documents...";
      try {
        const result = await api("/sessions/" + sessionId + "/automate_upload", "POST");
        applicationStage = "submit";
        sessionStorage.setItem(APPLICATION_STAGE_STORAGE_KEY, applicationStage);
        showAlert(result.message || "Document upload started.", "success");
        renderPlan(plan);
      } catch (error) {
        upload.disabled = false;
        upload.textContent = "I reviewed the form — upload documents";
        showAlert(error.message, "error");
      }
    });
    step.appendChild(upload);
  }
  if (applicationStage === "submit") {
    const note = document.createElement("p");
    note.className = "final-submission-note";
    note.textContent = "Final step: verify the uploaded files, submit the application yourself on the official portal, and complete any payment yourself if the portal requests a fee. Saarthi never handles payment credentials or final submission.";
    const final = document.createElement("button");
    final.type = "button";
    final.className = "primary-button full-width";
    final.textContent = "Open official portal to review and submit";
    final.addEventListener("click", async () => {
      await launchOfficialPortal(final);
      showAlert("Review the filled form and complete any payment yourself on the official portal.", "info");
    });
    step.append(note, final);
  }
  flow.appendChild(step);
}

function renderPlan(plan) {
  applicationPlan = plan;
  portalOpened = portalOpened || localStorage.getItem(PORTAL_OPEN_STORAGE_KEY) === plan.portal_url;
  setPlanHeader(plan);
  renderRequirements(plan);
  const portalPanel = $("#application-portal-panel");
  const documentsPanel = $("#application-documents-panel");
  portalPanel.hidden = currentStep === "documents";
  documentsPanel.hidden = currentStep !== "documents";
  const flow = $("#application-flow");
  flow.innerHTML = "";

  if (currentStep === "portal") {
    renderPortalStep(plan);
  } else if (currentStep === "documents") {
    setProgress("documents");
  } else if (currentStep === "details") {
    renderMissingDetails(flow, plan);
    setProgress("details");
  } else if (currentStep === "review") {
    if (plan.missing_fields && plan.missing_fields.length) {
      const gate = document.createElement("section");
      gate.className = "application-step";
      gate.innerHTML = "<h3>Some required details are still missing</h3><p>Complete those answers before reviewing or filling the official form.</p>";
      const back = document.createElement("button");
      back.type = "button";
      back.className = "primary-button full-width";
      back.textContent = "Complete missing details";
      back.addEventListener("click", () => goToApplicationStep("details"));
      gate.appendChild(back);
      flow.appendChild(gate);
    } else {
      renderReviewStep(flow, plan);
    }
    setProgress("review");
  } else {
    renderUploadStep(flow, plan);
    setProgress("submit");
  }
  renderExtractedData();
}

async function refreshPlanAfterExtraction() {
  const path = applicationPlan.application_type === "live_guidance"
    ? "/sessions/" + sessionId + "/live-application/readiness"
    : "/sessions/" + sessionId + "/applications/" + encodeURIComponent(applicationPlan.service_id) + "/readiness";
  applicationPlan = await api(path);
  renderPlan(applicationPlan);
}

async function extractDocuments() {
  if (!selectedFiles.length) return;
  const button = $("#scan-documents-button");
  const unlabelled = selectedFiles.filter((item) => documentTypesFor(item).length === 0);
  if (unlabelled.length) {
    showAlert("Choose at least one use for every uploaded file before extracting.", "info");
    return;
  }
  button.disabled = true;
  let extractedCount = 0;
  const errors = [];
  try {
    for (let index = 0; index < selectedFiles.length; index += 1) {
      const item = selectedFiles[index];
      const documentTypes = documentTypesFor(item);
      $("#scan-status").textContent = "Extracting " + (index + 1) + " of " + selectedFiles.length + ": " + documentTypes.join(", ");
      try {
        const result = await api("/sessions/" + sessionId + "/scan", "POST", {
          expected_type: documentTypes[0],
          document_types: documentTypes,
          images: [{ name: item.file.name, data: await readFileAsDataUrl(item.file) }],
        });
        if (result.action === "ask") {
          const questions = Array.isArray(result.questions) ? result.questions.join(" ") : "The document could not be read confidently.";
          throw new Error(questions);
        }
        Object.assign(savedExtractedData, result.summary || {});
        if (result.extra_fields && Object.keys(result.extra_fields).length) {
          additionalDocumentData.push({ documentType: documentTypes.join(", "), fields: result.extra_fields });
        }
        extractedCount += 1;
      } catch (_) {
        errors.push(item.file.name);
      }
    }
    renderExtractedData();
    if (extractedCount) {
      await refreshPlanAfterExtraction();
      $("#scan-status").textContent = extractedCount + " document" + (extractedCount === 1 ? "" : "s") + " processed and saved to this session.";
      await goToApplicationStep(
        "details",
        errors.length
          ? "Some documents could not be processed: " + errors.join(", ") + ". Add the remaining details manually."
          : "Documents were scanned and saved. Add only the details that were not found in them."
      );
      return;
    } else {
      throw new Error("No documents could be processed. Check the file type and try again.");
    }
  } catch (error) {
    $("#scan-status").textContent = "Document extraction needs attention.";
    showAlert(error.message, "error");
  } finally {
    button.disabled = selectedFiles.length === 0;
    button.textContent = "Extract labelled documents";
  }
}

async function initialise() {
  if (!sessionId) {
    $("#session-status").textContent = "No active session";
    showAlert("Open this page from the Saarthi dashboard so your secure session can be used.", "error");
    return;
  }
  if (!params.get("service") && params.get("live") !== "1") {
    showAlert("Choose an application from Live Official Guidance or Government Services first.", "error");
    return;
  }
  await restoreDraftDocuments();
  renderDocuments();
  try {
    if (params.get("live") === "1" && params.get("source_url")) {
      applicationPlan = await api("/sessions/" + sessionId + "/live-application", "POST", {
        title: params.get("source_title") || "Official government application",
        url: params.get("source_url"),
      });
      window.history.replaceState({}, "", "/application/portal?live=1");
    } else {
      const path = params.get("live") === "1"
        ? "/sessions/" + sessionId + "/live-application/readiness"
        : "/sessions/" + sessionId + "/applications/" + encodeURIComponent(params.get("service")) + "/readiness";
      applicationPlan = await api(path);
    }
    renderPlan(applicationPlan);
    const flash = sessionStorage.getItem(APPLICATION_FLASH_STORAGE_KEY);
    if (flash) {
      sessionStorage.removeItem(APPLICATION_FLASH_STORAGE_KEY);
      showAlert(flash, "success");
    }
  } catch (error) {
    showAlert(error.message, "error");
    $("#portal-status").textContent = "Needs attention";
    $("#portal-status").className = "application-badge waiting";
  }
}

$("#document-input").addEventListener("change", (event) => {
  selectedFiles = selectedFiles.concat(Array.from(event.target.files || []).map((file) => ({ file, documentType: "", documentTypes: [] })));
  event.target.value = "";
  renderDocuments();
});
$("#scan-documents-button").addEventListener("click", extractDocuments);
$("#continue-details-button").addEventListener("click", () => goToApplicationStep("details"));
initialise();
