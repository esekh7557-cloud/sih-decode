const API = window.location.origin;

let sessionId = null;
let language = "en";
let selectedFiles = [];
let services = [];
let activeServiceId = null;
let speechEnabled = true;
let recognition = null;
let isListening = false;
let voiceTranscript = "";
let sendVoiceMessage = false;
let additionalDocumentData = [];
let savedProfileData = {};
const DOCUMENT_TYPES = [
  "Aadhaar Card",
  "PAN Card",
  "Income Certificate",
  "Residence Certificate",
  "Caste Certificate",
  "Birth Certificate",
  "Ration Card",
  "Other Document",
];

const $ = (selector) => document.querySelector(selector);

async function api(path, method = "GET", body = null) {
  const options = { method, headers: { "Content-Type": "application/json" } };
  if (body !== null) options.body = JSON.stringify(body);
  const response = await fetch(API + path, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || "The server could not complete this request. Please try again.");
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

function speechLanguageFor(text) {
  if (language === "hi" && /[\u0900-\u097F]/.test(text)) return "hi-IN";
  if (language === "mr" && /[\u0900-\u097F]/.test(text)) return "mr-IN";
  if (language === "gu" && /[\u0A80-\u0AFF]/.test(text)) return "gu-IN";
  return "en-IN";
}

function recognitionLanguage() {
  return { en: "en-IN", hi: "hi-IN", mr: "mr-IN", gu: "gu-IN" }[language] || "en-IN";
}

function speakAssistant(text) {
  if (!speechEnabled || !text || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = speechLanguageFor(text);
  utterance.rate = 0.95;
  const voices = window.speechSynthesis.getVoices();
  const matchingVoice = voices.find((voice) => voice.lang.replace("_", "-") === utterance.lang);
  if (matchingVoice) utterance.voice = matchingVoice;
  window.speechSynthesis.speak(utterance);
}

function toggleSpeech() {
  speechEnabled = !speechEnabled;
  const button = $("#voice-toggle");
  button.setAttribute("aria-pressed", String(speechEnabled));
  button.textContent = speechEnabled ? "Voice: On" : "Voice: Off";
  if (!speechEnabled && "speechSynthesis" in window) window.speechSynthesis.cancel();
  showToast(speechEnabled ? "Assistant voice is on." : "Assistant voice is off.", "info");
}

function setListeningState(listening) {
  isListening = listening;
  const button = $("#microphone-button");
  button.classList.toggle("listening", listening);
  button.textContent = listening ? "Finish speaking" : "Speak";
  button.setAttribute("aria-label", listening ? "Finish speaking and send the voice message" : "Start speaking to the assistant");
}

function startListening() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    showToast("Voice input is not supported in this browser. Please use Chrome or Edge.", "error");
    return;
  }
  if (isListening && recognition) {
    sendVoiceMessage = true;
    recognition.stop();
    return;
  }

  voiceTranscript = "";
  sendVoiceMessage = false;
  recognition = new Recognition();
  recognition.lang = recognitionLanguage();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;
  recognition.onstart = () => {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    setListeningState(true);
  };
  recognition.onresult = (event) => {
    let interimTranscript = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const transcript = event.results[index][0].transcript;
      if (event.results[index].isFinal) voiceTranscript += transcript + " ";
      else interimTranscript += transcript;
    }
    $("#assistant-input").value = (voiceTranscript + interimTranscript).trim();
  };
  recognition.onerror = (event) => {
    const messages = {
      "not-allowed": "Microphone permission was denied. Please allow it in your browser settings.",
      "no-speech": "I could not hear anything. Please try again.",
      "network": "Voice input needs a network connection in this browser.",
    };
    showToast(messages[event.error] || "Voice input could not start. Please try again.", "error");
  };
  recognition.onend = () => {
    setListeningState(false);
    const transcript = voiceTranscript.trim() || $("#assistant-input").value.trim();
    if (sendVoiceMessage && transcript) {
      sendVoiceMessage = false;
      askAssistant(transcript);
    } else if (transcript) {
      showToast("Voice message captured. Click Send when you are ready.", "info");
    }
  };
  try {
    recognition.start();
  } catch (error) {
    setListeningState(false);
    showToast("Voice input could not start. Please try again.", "error");
  }
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
  if (role !== "user") speakAssistant(text);
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
    dob: $("#profile-dob").value.trim(),
    gender: $("#profile-gender").value,
    state: $("#profile-state").value,
    occupation: $("#profile-occupation").value,
    annual_income: numberValue("annual_income"),
    mobile: $("#profile-mobile").value.trim(),
    address: $("#profile-address").value.trim(),
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

function missingEligibilityFields() {
  const data = profilePayload();
  const missing = [];
  if (data.age === null) missing.push("your age");
  if (!data.gender) missing.push("your gender");
  if (!data.occupation) missing.push("your occupation");
  if (data.annual_income === null) missing.push("your annual family income");
  if (data.occupation === "farmer" && !data.land_acres) missing.push("your cultivable land in acres");
  return missing;
}

function askForMissingDetails() {
  const missing = missingEligibilityFields();
  if (!missing.length) return;
  const question = "I could not find " + missing.join(", ") + " in the uploaded documents. Please enter " + (missing.length === 1 ? "it" : "these details") + " in Your details so I can check schemes accurately.";
  addMessage("assistant", question);
  showToast("More information is needed for accurate scheme guidance.", "info");
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

function renderLiveGuidance(guidance) {
  const panel = $("#live-guidance");
  if (!guidance) {
    panel.hidden = true;
    return;
  }

  panel.hidden = false;
  $("#live-guidance-notice").textContent = guidance.notice || "";
  const steps = $("#live-guidance-steps");
  const sources = $("#official-sources");
  steps.innerHTML = "";
  sources.innerHTML = "";

  (guidance.steps || []).forEach((step) => {
    const item = document.createElement("li");
    item.textContent = step;
    steps.appendChild(item);
  });

  (guidance.sources || []).forEach((source) => {
    const link = document.createElement("a");
    link.className = "official-source";
    link.href = source.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    const title = document.createElement("strong");
    title.textContent = source.title;
    const snippet = document.createElement("span");
    snippet.textContent = source.snippet || source.url;
    link.append(title, snippet);
    sources.appendChild(link);
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
    name.textContent = file.file.name;
    const size = document.createElement("small");
    size.textContent = Math.max(1, Math.round(file.file.size / 1024)) + " KB";
    info.append(name, size);
    const type = document.createElement("select");
    type.className = "document-type-select";
    type.setAttribute("aria-label", "Document type for " + file.file.name);
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select document type";
    type.appendChild(placeholder);
    DOCUMENT_TYPES.forEach((documentType) => {
      const option = document.createElement("option");
      option.value = documentType;
      option.textContent = documentType;
      option.selected = file.documentType === documentType;
      type.appendChild(option);
    });
    type.addEventListener("change", (event) => {
      selectedFiles[index].documentType = event.target.value;
    });
    const remove = document.createElement("button");
    remove.className = "remove-document";
    remove.type = "button";
    remove.setAttribute("aria-label", "Remove " + file.file.name);
    remove.textContent = "x";
    remove.addEventListener("click", () => {
      selectedFiles.splice(index, 1);
      renderDocuments();
    });
    item.append(info, type, remove);
    list.appendChild(item);
  });
}

function formatFieldName(field) {
  return field.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderAdditionalDocumentData() {
  const section = $("#additional-data");
  const list = $("#additional-data-list");
  list.innerHTML = "";
  section.hidden = additionalDocumentData.length === 0;
  additionalDocumentData.forEach((entry) => {
    Object.entries(entry.fields).forEach(([field, value]) => {
      const item = document.createElement("div");
      item.className = "additional-data-item";
      const label = document.createElement("span");
      label.textContent = entry.documentType + " - " + formatFieldName(field);
      const content = document.createElement("strong");
      content.textContent = typeof value === "object" ? JSON.stringify(value) : String(value);
      item.append(label, content);
      list.appendChild(item);
    });
  });
}

function safeSavedValue(field, value) {
  const text = typeof value === "object" ? JSON.stringify(value) : String(value);
  const digits = text.replace(/\D/g, "");
  if ((field.toLowerCase().includes("aadhaar") || field === "id_proof_no") && digits.length >= 12) {
    return "XXXX XXXX " + digits.slice(-4);
  }
  return text;
}

function renderSavedProfileData() {
  const section = $("#saved-data");
  const list = $("#saved-data-list");
  const entries = Object.entries(savedProfileData);
  list.innerHTML = "";
  section.hidden = entries.length === 0;
  entries.forEach(([field, value]) => {
    const item = document.createElement("div");
    item.className = "saved-data-item";
    const label = document.createElement("span");
    label.textContent = formatFieldName(field);
    const content = document.createElement("strong");
    content.textContent = safeSavedValue(field, value);
    item.append(label, content);
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
  button.textContent = "Extracting documents...";
  $("#scan-status").textContent = "Preparing labelled document extraction...";
  try {
    const unlabelled = selectedFiles.filter((item) => !item.documentType);
    if (unlabelled.length) {
      throw new Error("Select the document type for every uploaded file before extracting.");
    }

    let extractedCount = 0;
    const errors = [];
    for (let index = 0; index < selectedFiles.length; index += 1) {
      const item = selectedFiles[index];
      $("#scan-status").textContent = "Extracting " + (index + 1) + " of " + selectedFiles.length + ": " + item.documentType;
      try {
        const result = await api("/sessions/" + sessionId + "/scan", "POST", {
          expected_type: item.documentType,
          images: [{ name: item.file.name, data: await readFileAsDataUrl(item.file) }],
        });
        applyExtractedFields(result.summary || {});
        Object.assign(savedProfileData, result.summary || {});
        renderSavedProfileData();
        if (result.extra_fields && Object.keys(result.extra_fields).length) {
          additionalDocumentData.push({ documentType: item.documentType, fields: result.extra_fields });
          renderAdditionalDocumentData();
        }
        extractedCount += 1;
      } catch (error) {
        errors.push(item.file.name);
      }
    }
    let profileSaved = false;
    if (extractedCount) {
      try {
        await saveProfile({ quiet: true });
        profileSaved = true;
      } catch (error) {
        showToast("Documents were processed, but please review the extracted profile details before saving.", "info");
      }
    }
    updateReadiness();
    $("#scan-status").textContent = extractedCount + " document" + (extractedCount === 1 ? "" : "s") + (profileSaved ? " processed and saved to your profile." : " processed. Please review your profile before saving.");
    if (errors.length) {
      showToast("Could not process: " + errors.join(", ") + ".", "error");
    } else {
      showToast("Labelled document details have been added to the profile.", "success");
      addMessage("assistant", "I processed your labelled documents. Please check the profile fields and correct anything that looks wrong.");
    }
    if (extractedCount) askForMissingDetails();
  } catch (error) {
    $("#scan-status").textContent = "Could not extract details. You can still enter them manually.";
    showToast(error.message, "error");
  } finally {
    button.disabled = selectedFiles.length === 0;
    button.textContent = "Extract labelled documents";
  }
}

function applyExtractedFields(fields) {
  const bindings = {
    name: "#profile-name", age: "#profile-age", dob: "#profile-dob",
    mobile: "#profile-mobile", address: "#profile-address", gender: "#profile-gender",
    state: "#profile-state", occupation: "#profile-occupation",
    annual_income: "#profile-income", caste_category: "#profile-category",
    land_acres: "#profile-land",
  };
  Object.entries(bindings).forEach(([field, selector]) => {
    if (fields[field] !== undefined && fields[field] !== null && fields[field] !== "") {
      $(selector).value = normaliseExtractedValue(field, fields[field]);
    }
  });
}

function normaliseExtractedValue(field, value) {
  const text = String(value).trim();
  if (["age", "annual_income", "land_acres"].includes(field)) {
    return text.replace(/[^\d.]/g, "");
  }
  if (field === "gender") {
    const gender = text.toLowerCase();
    if (gender.startsWith("m")) return "male";
    if (gender.startsWith("f")) return "female";
    if (gender.startsWith("o")) return "other";
  }
  if (field === "caste_category") return text.toUpperCase();
  if (field === "occupation") {
    const occupation = text.toLowerCase().replace(/\s+/g, "_");
    const aliases = {
      "farmer": "farmer",
      "agriculturist": "farmer",
      "student": "student",
      "artisan": "artisan",
      "craftsperson": "artisan",
      "small_business": "small_business",
      "business_owner": "small_business",
      "salaried": "salaried",
      "employee": "salaried",
      "unemployed": "unemployed",
      "pensioner": "pensioner",
    };
    return aliases[occupation] || "";
  }
  return text;
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
    renderLiveGuidance(result.live_guidance);
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
    speakAssistant("Language preference saved. I will read future answers aloud.");
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
    additionalDocumentData = [];
    savedProfileData = {};
    renderDocuments();
    renderAdditionalDocumentData();
    renderSavedProfileData();
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
    selectedFiles = selectedFiles.concat(
      Array.from(event.target.files || []).map((file) => ({ file, documentType: "" }))
    );
    event.target.value = "";
    renderDocuments();
  });
  $("#scan-documents-button").addEventListener("click", extractDocuments);
  $("#end-session-button").addEventListener("click", endSession);
  $("#voice-toggle").addEventListener("click", toggleSpeech);
  $("#microphone-button").addEventListener("click", startListening);
}

window.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  renderDocuments();
  updateReadiness();
  if ("speechSynthesis" in window) window.speechSynthesis.getVoices();
  try {
    await startSession();
  } catch (error) {
    $("#session-status").textContent = "Could not start a session";
    showToast("Unable to connect to the server: " + error.message, "error");
  }
});
