const API = window.location.origin;
const SESSION_STORAGE_KEY = "janseva.session.id";
const ONBOARDING_STORAGE_KEY = "janseva.onboarding";
const VOICE_STORAGE_KEY = "janseva.voice.enabled";
const APPLICATION_DRAFT_STORAGE_KEY = "janseva.application.draft";
const PORTAL_OPEN_STORAGE_KEY = "janseva.application.portal-open";

let sessionId = null;
let language = "en";
let selectedFiles = [];
let services = [];
let activeServiceId = null;
let activeApplicationServiceId = null;
let activeApplicationType = null;
let requiredApplicationDocuments = [];
let applicationPageOpen = false;
let documentsOriginalParent = null;
let documentsOriginalNextSibling = null;
let checklistOriginalParent = null;
let checklistOriginalNextSibling = null;
let speechEnabled = localStorage.getItem(VOICE_STORAGE_KEY) === "true";
let recognition = null;
let isListening = false;
let voiceTranscript = "";
let sendVoiceMessage = false;
let additionalDocumentData = [];
let savedProfileData = {};
const openedPortalServices = new Set();
let onboardingStep = 0;
let onboardingAnswers = {};
let onboardingRecognition = null;
let onboardingListening = false;
const ONBOARDING_STEPS = [
  { key: "language", title: "Choose your language", copy: "Start with your preferred language. You can change it later from the dashboard." },
  { key: "age", title: "What is your age?", copy: "This helps Saarthi find schemes that match your age group.", type: "number", placeholder: "Enter your age", min: "0", max: "120" },
  { key: "gender", title: "What is your gender?", copy: "Choose the option you are most comfortable sharing.", type: "select", options: [["female", "Female"], ["male", "Male"], ["other", "Other"]] },
  { key: "state", title: "Which state do you live in?", copy: "State information helps us show the right government services.", type: "select", options: [["Goa", "Goa"], ["Maharashtra", "Maharashtra"], ["Gujarat", "Gujarat"], ["Other", "Other"]] },
  { key: "district", title: "Which district do you live in?", copy: "Enter your district as it appears on your official documents.", type: "text", placeholder: "Enter your district" },
  { key: "occupation", title: "What is your occupation?", copy: "This helps us identify work-related benefits and schemes.", type: "select", options: [["farmer", "Farmer"], ["salaried", "Salaried employee"], ["artisan", "Artisan / craftsperson"], ["small_business", "Small-business owner"], ["unemployed", "Unemployed"], ["pensioner", "Pensioner"], ["student", "Student"]] },
  { key: "annual_income", title: "What is your annual family income?", copy: "Enter the approximate total income of your family in Indian rupees.", type: "number", placeholder: "e.g. 250000", min: "0" },
  { key: "caste_category", title: "What is your social category?", copy: "This helps improve scheme matches. Choose the option shown on your official documents.", type: "select", options: [["GENERAL", "General"], ["SC", "SC"], ["ST", "ST"], ["OBC", "OBC"], ["NT", "NT"], ["VJNT", "VJNT"], ["SBC", "SBC"], ["MINORITY", "Minority"]] },
];
const DOCUMENT_TYPES = [
  "Aadhaar Card",
  "PAN Card",
  "Voter ID Card",
  "Photograph",
  "Income Certificate",
  "Residence Certificate",
  "Caste Certificate",
  "Birth Certificate",
  "Ration Card",
  "Other Document",
];

// A single file can be valid evidence for more than one requirement (for
// example, an Aadhaar card may be used as both identity and address proof).
// Keep those assignments on the file instead of asking the citizen to upload
// the same image again.
function documentTypesFor(item) {
  const types = Array.isArray(item.documentTypes)
    ? item.documentTypes
    : (item.documentType ? [item.documentType] : []);
  return Array.from(new Set(types.filter(Boolean)));
}

function setDocumentTypes(item, types) {
  item.documentTypes = Array.from(new Set(types.filter(Boolean)));
  // Retain the primary type for older draft data and existing integrations.
  item.documentType = item.documentTypes[0] || "";
}

function allSelectedDocumentTypes() {
  return selectedFiles.flatMap(documentTypesFor);
}

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

function saveOnboardingState(complete = false) {
  if (!sessionId) return;
  try {
    localStorage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify({
      sessionId,
      step: onboardingStep,
      answers: onboardingAnswers,
      complete,
    }));
  } catch (error) {
    // The server session remains the source of truth if browser storage is unavailable.
  }
}

function readOnboardingState() {
  try {
    const saved = JSON.parse(localStorage.getItem(ONBOARDING_STORAGE_KEY) || "null");
    return saved && saved.sessionId === sessionId ? saved : null;
  } catch (error) {
    return null;
  }
}

function syncVoiceButton() {
  const button = $("#voice-toggle");
  if (!button) return;
  button.setAttribute("aria-pressed", String(speechEnabled));
  button.textContent = speechEnabled ? SaarthiI18n.t("voiceOn") : SaarthiI18n.t("voiceOff");
}

function profileInputSelector(key) {
  return {
    age: "#profile-age",
    gender: "#profile-gender",
    state: "#profile-state",
    district: "#profile-district",
    occupation: "#profile-occupation",
    annual_income: "#profile-income",
    caste_category: "#profile-category",
  }[key];
}

function setProfileInputValue(key, value) {
  const selector = profileInputSelector(key);
  if (!selector || $(selector) === null || value === null || value === undefined) return;
  $(selector).value = String(value);
  updateReadiness();
}

function applicationFieldOptions(field) {
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

function appendApplicationQuestion(form, field) {
  const kind = String(field.type || "text").toLowerCase();
  const options = applicationFieldOptions(field);
  if (kind === "radio" || kind === "checkbox" || kind === "multi_select") {
    const group = document.createElement("fieldset");
    group.className = "question-choices";
    group.dataset.choiceRequired = field.required ? "true" : "false";
    const legend = document.createElement("legend");
    legend.textContent = field.label;
    group.appendChild(legend);
    const choices = options.length ? options : [{ value: "true", label: field.label }];
    choices.forEach((option) => {
      const choice = document.createElement("label");
      choice.className = "question-choice";
      const control = document.createElement("input");
      control.type = kind === "radio" ? "radio" : "checkbox";
      control.name = field.key;
      control.value = option.value;
      control.required = kind === "radio" && field.required;
      const text = document.createElement("span");
      text.textContent = option.label;
      choice.append(control, text);
      group.appendChild(choice);
    });
    form.appendChild(group);
    return;
  }

  const group = document.createElement("label");
  group.className = "field-group";
  const label = document.createElement("span");
  label.textContent = field.label;
  group.appendChild(label);
  let input;
  // A field may be technically text but still have a finite set of choices
  // (custom portal widgets commonly do this), so choices take precedence.
  if (options.length) {
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
  input.required = field.required !== false;
  input.autocomplete = "off";
  ["placeholder", "min", "max", "step", "pattern"].forEach((key) => {
    if (field[key] !== undefined && field[key] !== "") input[key] = field[key];
  });
  if (field.max_length) input.maxLength = Number(field.max_length);
  group.appendChild(input);
  form.appendChild(group);
}

function applicationFormAnswers(form) {
  const answers = {};
  for (const [key, value] of new FormData(form).entries()) {
    answers[key] = Object.prototype.hasOwnProperty.call(answers, key)
      ? (Array.isArray(answers[key]) ? answers[key].concat(value) : [answers[key], value])
      : value;
  }
  return answers;
}

function requiredChoiceIsMissing(form) {
  return Array.from(form.querySelectorAll("[data-choice-required='true']"))
    .some((group) => !group.querySelector("input:checked"));
}

function onboardingValue(key) {
  const selector = profileInputSelector(key);
  if (!selector || !$(selector)) return "";
  return $(selector).value.trim();
}

function startOnboardingListening(input) {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    showToast("Voice input is not supported in this browser. Please use Chrome or Edge.", "error");
    return;
  }
  if (onboardingListening && onboardingRecognition) {
    onboardingRecognition.stop();
    return;
  }
  onboardingListening = true;
  const button = $("#onboarding-mic");
  if (button) {
    button.textContent = "Listening...";
    button.classList.add("listening");
  }
  onboardingRecognition = new Recognition();
  onboardingRecognition.lang = recognitionLanguage();
  onboardingRecognition.interimResults = true;
  onboardingRecognition.maxAlternatives = 1;
  onboardingRecognition.onresult = (event) => {
    let transcript = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      transcript += event.results[index][0].transcript;
    }
    input.value = transcript.trim();
  };
  onboardingRecognition.onerror = () => showToast("Voice input could not start. Please try again.", "error");
  onboardingRecognition.onend = () => {
    onboardingListening = false;
    if (button) {
      button.textContent = "Answer with voice";
      button.classList.remove("listening");
    }
  };
  try {
    onboardingRecognition.start();
  } catch (error) {
    onboardingListening = false;
    if (button) {
      button.textContent = "Answer with voice";
      button.classList.remove("listening");
    }
  }
}

function renderOnboardingStep() {
  const backdrop = $("#onboarding");
  const content = $("#onboarding-content");
  const title = $("#onboarding-title");
  const copy = $("#onboarding-copy");
  const kicker = $("#onboarding-kicker");
  const progress = $("#onboarding-progress-bar");
  const next = $("#onboarding-next");
  const back = $("#onboarding-back");
  if (!backdrop || !content) return;
  backdrop.hidden = false;
  content.innerHTML = "";

  if (onboardingStep >= ONBOARDING_STEPS.length) {
    kicker.textContent = "SETUP COMPLETE";
    title.textContent = "Your basic details are ready";
    copy.textContent = "Saarthi can now personalise scheme matches and government-service guidance for you.";
    progress.style.width = "100%";
    const summary = document.createElement("div");
    summary.className = "onboarding-summary";
    const labels = { age: "Age", gender: "Gender", state: "State", district: "District", occupation: "Occupation", annual_income: "Annual family income", caste_category: "Social category" };
    Object.entries(labels).forEach(([key, label]) => {
      const row = document.createElement("div");
      const name = document.createElement("span");
      name.textContent = label;
      const value = document.createElement("strong");
      const raw = onboardingAnswers[key] ?? onboardingValue(key);
      value.textContent = key === "annual_income" && raw !== "" ? "₹" + Number(raw).toLocaleString("en-IN") : (raw || "Not provided");
      row.append(name, value);
      summary.appendChild(row);
    });
    content.appendChild(summary);
    next.textContent = "Continue to dashboard";
    back.classList.remove("visible");
    window.setTimeout(() => speakAssistant(title.textContent + ". " + copy.textContent), 0);
    return;
  }

  const step = ONBOARDING_STEPS[onboardingStep];
  kicker.textContent = onboardingStep === 0 ? "WELCOME" : `STEP ${onboardingStep} OF ${ONBOARDING_STEPS.length - 1}`;
  title.textContent = step.title;
  copy.textContent = step.copy;
  progress.style.width = `${Math.round((onboardingStep / ONBOARDING_STEPS.length) * 100)}%`;
  back.classList.toggle("visible", onboardingStep > 0);
  next.textContent = onboardingStep === ONBOARDING_STEPS.length - 1 ? "Save my details" : "Continue";

  if (step.key === "language") {
    const field = document.createElement("div");
    field.className = "onboarding-field";
    const label = document.createElement("label");
    label.textContent = "Preferred language";
    const select = document.createElement("select");
    select.id = "onboarding-language";
    [["en", "English"], ["hi", "Hindi"], ["mr", "Marathi"], ["gu", "Gujarati"]].forEach(([value, text]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = text;
      option.selected = value === (onboardingAnswers.language || language);
      select.appendChild(option);
    });
    field.append(label, select);
    content.appendChild(field);
    const voice = document.createElement("label");
    voice.className = "onboarding-voice";
    voice.innerHTML = '<input id="onboarding-voice-enabled" type="checkbox" /> <span><strong>Use voice assistance</strong>Saarthi can read guidance aloud and let you answer with your microphone. You can turn this off anytime.</span>';
    voice.querySelector("input").checked = speechEnabled;
    content.appendChild(voice);
    select.addEventListener("change", () => { language = select.value; });
  } else {
    const field = document.createElement("div");
    field.className = "onboarding-field";
    const label = document.createElement("label");
    label.htmlFor = "onboarding-input";
    label.textContent = step.title;
    let input;
    if (step.type === "select") {
      input = document.createElement("select");
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "Select an option";
      input.appendChild(placeholder);
      step.options.forEach(([value, text]) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = text;
        input.appendChild(option);
      });
    } else {
      input = document.createElement("input");
      input.type = step.type || "text";
      input.placeholder = step.placeholder || "Enter your answer";
      if (step.min !== undefined) input.min = step.min;
      if (step.max !== undefined) input.max = step.max;
    }
    input.id = "onboarding-input";
    input.value = onboardingAnswers[step.key] ?? onboardingValue(step.key);
    field.append(label, input);
    content.appendChild(field);
    const mic = document.createElement("button");
    mic.type = "button";
    mic.id = "onboarding-mic";
    mic.className = "mic-button onboarding-mic";
    mic.textContent = "Answer with voice";
    mic.addEventListener("click", () => startOnboardingListening(input));
    content.appendChild(mic);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        next.click();
      }
    });
    window.setTimeout(() => input.focus(), 0);
  }
  window.setTimeout(() => speakAssistant(title.textContent + ". " + copy.textContent), 0);
}

function hideOnboarding() {
  $("#onboarding").hidden = true;
  saveOnboardingState(true);
}

async function advanceOnboarding() {
  if (onboardingStep >= ONBOARDING_STEPS.length) {
    hideOnboarding();
    addMessage("assistant", "Your basic details are saved for this session. I am ready to help you find schemes and services.");
    return;
  }
  const step = ONBOARDING_STEPS[onboardingStep];
  let value;
  if (step.key === "language") {
    value = $("#onboarding-language").value;
    if (!value) {
      showToast("Please choose a language to continue.", "info");
      return;
    }
    language = value;
    $("#language-select").value = language;
    const voiceChoice = $("#onboarding-voice-enabled");
    speechEnabled = Boolean(voiceChoice && voiceChoice.checked);
    localStorage.setItem(VOICE_STORAGE_KEY, String(speechEnabled));
    syncVoiceButton();
    try {
      await api("/sessions/" + sessionId + "/language", "POST", { language });
    } catch (error) {
      showToast(error.message, "error");
      return;
    }
  } else {
    const input = $("#onboarding-input");
    value = input.value.trim();
    if (!value) {
      input.focus();
      showToast("Please answer this question to continue.", "info");
      return;
    }
    if (step.key === "age" && (Number(value) < 0 || Number(value) > 120)) {
      showToast("Please enter an age between 0 and 120.", "info");
      return;
    }
    if (step.key === "annual_income" && Number(value) < 0) {
      showToast("Annual family income cannot be negative.", "info");
      return;
    }
    value = ["age", "annual_income"].includes(step.key) ? Number(value) : value;
    setProfileInputValue(step.key, value);
  }
  onboardingAnswers[step.key] = value;
  onboardingStep += 1;
  saveOnboardingState(false);
  if (onboardingStep === ONBOARDING_STEPS.length) {
    try {
      await saveProfile({ quiet: true });
      saveOnboardingState(true);
    } catch (error) {
      onboardingStep -= 1;
      saveOnboardingState(false);
      showToast("Your details could not be saved yet: " + error.message, "error");
      renderOnboardingStep();
      return;
    }
  }
  renderOnboardingStep();
}

function goBackOnboarding() {
  if (onboardingStep <= 0) return;
  onboardingStep -= 1;
  saveOnboardingState(false);
  renderOnboardingStep();
}

function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = "toast " + type;
  toast.textContent = message;
  $("#toast-region").appendChild(toast);
  window.setTimeout(() => toast.remove(), 4200);
}

function speechLanguageFor(text) {
  if (language !== "en") return SaarthiI18n.languageCode(language);
  return "en-IN";
}

function recognitionLanguage() {
  return SaarthiI18n.languageCode(language);
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
  localStorage.setItem(VOICE_STORAGE_KEY, String(speechEnabled));
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
    label.textContent = "Saarthi Assistant";
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

function addChoiceMessage(options = []) {
  if (!options.length) return;
  const article = document.createElement("article");
  article.className = "chat-message assistant-message choice-message";
  const avatar = document.createElement("span");
  avatar.className = "avatar";
  avatar.textContent = "AI";
  const content = document.createElement("div");
  const label = document.createElement("strong");
  label.textContent = "Choose an option";
  const choices = document.createElement("div");
  choices.className = "chat-choice-grid";
  options.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chat-choice-button";
    button.textContent = option.label || option.value;
    button.addEventListener("click", () => {
      choices.querySelectorAll("button").forEach((choice) => { choice.disabled = true; });
      askAssistant(option.value || option.label);
    });
    choices.appendChild(button);
  });
  content.append(label, choices);
  article.append(avatar, content);
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
    dob: $("#profile-dob").value.trim(),
    gender: $("#profile-gender").value,
    state: $("#profile-state").value,
    district: $("#profile-district").value.trim(),
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
  const fields = [data.age, data.gender, data.state, data.district, data.occupation, data.annual_income, data.caste_category];
  const complete = fields.filter((value) => value !== null && value !== "").length;
  const percentage = Math.round((complete / fields.length) * 100);
  const remaining = fields.length - complete;
  $("#readiness-score").textContent = percentage + "%";
  $("#readiness-bar").style.width = percentage + "%";
  $("#readiness-text").textContent = percentage === 100
    ? SaarthiI18n.t("profileReady")
    : remaining + " " + SaarthiI18n.t(remaining === 1 ? "detailRemaining" : "detailsRemaining");
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

function renderLiveGuidance(guidance, applicationServiceId = null, availableServices = []) {
  const panel = $("#live-guidance");
  const actions = $("#live-guidance-actions");
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
  actions.innerHTML = "";

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

  const primarySource = (guidance.sources || [])[0];
  if (primarySource && primarySource.url) {
    const open = document.createElement("button");
    open.type = "button";
    open.className = "secondary-button";
    open.textContent = "Open official site";
    open.addEventListener("click", () => window.open(primarySource.url, "_blank", "noopener,noreferrer"));
    actions.appendChild(open);
  }

  // The assistant only supplies this id when it matches a service from the
  // current state catalog. Keep the client-side check as a second guard so
  // generic live guidance never gets an application button by accident.
  const knownService = (availableServices || []).some((service) => service.id === applicationServiceId);
  if (knownService) {
    const apply = document.createElement("button");
    apply.type = "button";
    apply.className = "primary-button";
    apply.textContent = "Apply with Saarthi";
    apply.addEventListener("click", () => {
      window.location.assign("/guided-services?service=" + encodeURIComponent(applicationServiceId));
    });
    actions.appendChild(apply);
  }

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

function documentMatchesRequirement(type, requirement) {
  const typeText = String(type || "").toLowerCase();
  const requirementText = String(requirement || "").toLowerCase();
  if (requirementText.includes("aadhaar")) return typeText.includes("aadhaar");
  if (requirementText.includes("pan")) return typeText.includes("pan");
  if (requirementText.includes("voter")) return typeText.includes("voter");
  if (requirementText.includes("birth")) return typeText.includes("birth");
  if (requirementText.includes("residence")) return typeText.includes("residence");
  if (requirementText.includes("photograph")) return typeText.includes("photograph") || selectedFiles.some((item) => /photo|passport/.test(item.file.name.toLowerCase()));
  return false;
}

function renderApplicationReview(container, plan, portalOpened) {
  const review = document.createElement("section");
  review.className = "application-review";
  const heading = document.createElement("h4");
  heading.textContent = "Review the details Saarthi will fill";
  const note = document.createElement("p");
  note.textContent = "Sensitive ID numbers are masked here. Correct any value in Your details or the missing-details form before continuing.";
  const list = document.createElement("dl");
  list.className = "review-list";
  plan.fields.forEach((field) => {
    const row = document.createElement("div");
    const label = document.createElement("dt");
    label.textContent = field.label;
    const value = document.createElement("dd");
    value.textContent = field.value || "Not provided";
    row.append(label, value);
    list.appendChild(row);
  });
  const confirm = document.createElement("label");
  confirm.className = "check-control review-confirm";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  const text = document.createElement("span");
  text.textContent = "I checked these details and want Saarthi to fill the opened official form.";
  confirm.append(checkbox, text);
  const fill = document.createElement("button");
  fill.type = "button";
  fill.className = "primary-button full-width";
  fill.textContent = "Fill the reviewed form";
  fill.disabled = !portalOpened;
  fill.addEventListener("click", async () => {
    if (!checkbox.checked) {
      showToast("Please confirm that you reviewed the details first.", "info");
      return;
    }
    fill.disabled = true;
    fill.textContent = "Filling the official form...";
    try {
      const result = await api("/sessions/" + sessionId + "/automate_fill", "POST", { service_id: plan.service_id });
      fill.textContent = "Fields filled — review in Chrome";
      showToast(result.message || "Fields filled. Saarthi did not save or continue the official form.", "success");
      renderPostFillReview(container, plan, result.message);
    } catch (error) {
      fill.disabled = false;
      fill.textContent = "Fill the reviewed form";
      showToast(error.message, "error");
    }
  });
  review.append(heading, note, list, confirm, fill);
  container.appendChild(review);
}

function renderDocumentUploadStep(container, plan = null) {
  const existing = container.querySelector(".upload-after-review");
  if (existing) return;
  const step = document.createElement("section");
  step.className = "upload-after-review";
  const heading = document.createElement("h4");
  heading.textContent = "After you review the form";
  const copy = document.createElement("p");
  copy.textContent = "Check every value in the official portal. When you are on its document-upload page, use this button to match and upload the documents you scanned. Saarthi will not submit the final application.";
  const upload = document.createElement("button");
  upload.type = "button";
  upload.className = "secondary-button full-width";
  upload.textContent = "I reviewed the form — upload documents";
  upload.addEventListener("click", async () => {
    upload.disabled = true;
    upload.textContent = "Uploading scanned documents...";
    try {
      const result = await api("/sessions/" + sessionId + "/automate_upload", "POST");
      showToast("Document upload started. Review the portal, then submit the application yourself.", "success");
      const finalNote = document.createElement("p");
      finalNote.className = "final-submission-note";
      finalNote.textContent = "Final step: verify the uploaded files, submit the application yourself on the official portal, and complete any payment yourself if the portal requests a fee. Saarthi never handles payment credentials or final submission.";
      const finalAction = document.createElement("button");
      finalAction.type = "button";
      finalAction.className = "primary-button full-width";
      finalAction.textContent = "Open official portal to review and submit";
      finalAction.disabled = !plan || !plan.portal_url;
      finalAction.addEventListener("click", () => {
        if (plan && plan.portal_url) {
          window.open(plan.portal_url, "_blank", "noopener,noreferrer");
        }
        showToast("Review the filled form and complete any payment yourself on the official portal.", "info");
      });
      step.append(finalNote, finalAction);
      upload.textContent = result.action === "uploading" ? "Uploading started" : "Upload documents";
    } catch (error) {
      upload.disabled = false;
      upload.textContent = "I reviewed the form — upload documents";
      showToast(error.message, "error");
    }
  });
  step.append(heading, copy, upload);
  container.appendChild(step);
}

function setApplicationDocumentRequirements(plan) {
  activeApplicationServiceId = plan.service_id || null;
  activeApplicationType = plan.application_type || "service";
  requiredApplicationDocuments = Array.from(new Set((plan.documents || []).filter(Boolean)));
  const request = $("#application-document-request");
  const title = $("#application-document-title");
  const list = $("#application-document-requirements");
  if (!request || !title || !list) return;

  request.hidden = requiredApplicationDocuments.length === 0;
  list.innerHTML = "";
  if (!requiredApplicationDocuments.length) {
    renderDocuments();
    setDocumentPreparationVisibility(!(plan.form_scanned && plan.document_uploads_detected === false));
    return;
  }

  title.textContent = "Documents requested for " + (plan.service || "your application");
  requiredApplicationDocuments.forEach((documentName) => {
    const item = document.createElement("li");
    item.textContent = documentName;
    list.appendChild(item);
  });
  renderDocuments();
  setDocumentPreparationVisibility(!(plan.form_scanned && plan.document_uploads_detected === false));
}

function renderPostFillReview(container, plan, message = "") {
  if (container.querySelector(".post-fill-review")) return;
  const step = document.createElement("section");
  step.className = "post-fill-review application-review";
  const heading = document.createElement("h4");
  heading.textContent = "Review the filled official form";
  const copy = document.createElement("p");
  copy.textContent = message || "Saarthi filled only the reviewed fields. It did not click Save, Continue, Proceed, Upload, or Submit.";
  step.append(heading, copy);
  if (!(plan.form_scanned && plan.document_uploads_detected === false)) {
    const documents = document.createElement("button");
    documents.type = "button";
    documents.className = "secondary-button full-width";
    documents.textContent = "I reviewed the portal form — manage documents";
    documents.addEventListener("click", () => renderDocumentUploadStep(container, plan));
    step.appendChild(documents);
  }
  container.appendChild(step);
}

function setDocumentPreparationVisibility(visible) {
  const root = $("#documents");
  if (!root) return;
  [
    root.querySelector(".upload-zone"),
    root.querySelector("#document-input"),
    root.querySelector("#document-list"),
    root.querySelector("#scan-documents-button"),
  ].forEach((node) => {
    if (node) node.hidden = !visible;
  });
}

function documentDecisionKey(plan) {
  return "janseva.application.documents-needed." + (plan.service_id || "application");
}

function restoreApplicationNode(node, parent, nextSibling) {
  if (!node || !parent) return;
  const next = nextSibling && nextSibling.parentNode === parent ? nextSibling : null;
  parent.insertBefore(node, next);
}

function isApplicationPageRoute() {
  return window.location.pathname === "/application" || window.location.pathname === "/application.html" || window.location.pathname.startsWith("/application/") || new URLSearchParams(window.location.search).get("view") === "application";
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
    sessionStorage.removeItem(APPLICATION_DRAFT_STORAGE_KEY);
  }
}

function navigateToApplicationPage(parameters = {}) {
  // Navigation must happen immediately from the user's click. The draft is
  // best-effort and is restored by application.js on the new document.
  void persistApplicationDraft();
  const query = new URLSearchParams(parameters);
  window.location.assign("/application/portal?" + query.toString());
}

function openApplicationPage() {
  if (applicationPageOpen) return;
  const page = $("#application-page");
  const flow = $("#application-page-flow");
  const documents = $("#documents");
  const checklist = $("#service-checklist");
  if (!page || !flow || !documents || !checklist) return;

  documentsOriginalParent = documents.parentNode;
  documentsOriginalNextSibling = documents.nextSibling;
  checklistOriginalParent = checklist.parentNode;
  checklistOriginalNextSibling = checklist.nextSibling;
  flow.append(documents, checklist);
  page.hidden = false;
  $(".welcome-card").hidden = true;
  $(".dashboard-grid").hidden = true;
  $(".schemes-panel").hidden = true;
  applicationPageOpen = true;
}

function closeApplicationPage() {
  if (!applicationPageOpen) return;
  const page = $("#application-page");
  const flow = $("#application-page-flow");
  const documents = $("#documents");
  const checklist = $("#service-checklist");
  restoreApplicationNode(checklist, checklistOriginalParent, checklistOriginalNextSibling);
  restoreApplicationNode(documents, documentsOriginalParent, documentsOriginalNextSibling);
  if (flow) flow.innerHTML = "";
  if (page) page.hidden = true;
  $(".welcome-card").hidden = false;
  $(".dashboard-grid").hidden = false;
  $(".schemes-panel").hidden = false;
  applicationPageOpen = false;
  documentsOriginalParent = null;
  documentsOriginalNextSibling = null;
  checklistOriginalParent = null;
  checklistOriginalNextSibling = null;
}

function returnToDashboard() {
  if (isApplicationPageRoute()) window.history.replaceState({}, "", "/");
  closeApplicationPage();
}

function renderSaarthiApplication(plan) {
  setApplicationDocumentRequirements(plan);
  const pageTitle = $("#application-page-title");
  if (pageTitle) pageTitle.textContent = plan.service + " with Saarthi";
  const checklist = $("#service-checklist");
  let flow = checklist.querySelector(".saarthi-application-flow");
  if (flow) flow.remove();
  flow = document.createElement("section");
  flow.className = "saarthi-application-flow";
  const title = document.createElement("h3");
  title.textContent = plan.service + " with Saarthi";
  const intro = document.createElement("p");
  intro.textContent = "Complete the preparation below. You log in to the official portal, Saarthi fills only your reviewed answers, and you submit the final application yourself.";
  const official = document.createElement("a");
  official.className = "official-portal-link";
  official.href = plan.portal_url || "#";
  official.target = "_blank";
  official.rel = "noopener noreferrer";
  official.textContent = plan.portal_url ? "Official application portal ↗" : "Official portal link needs configuration";
  flow.append(title, intro, official);
  if (plan.form_scanned) {
    const scanStatus = document.createElement("p");
    scanStatus.className = "ready-message";
    scanStatus.textContent = "Opened form scanned: " + ((plan.scanned_form && plan.scanned_form.title) || "application page") + ". Its required fields and document rows are included below.";
    flow.appendChild(scanStatus);
  }

  const documents = document.createElement("section");
  documents.className = "application-documents";
  const docTitle = document.createElement("h4");
  const noPortalUpload = Boolean(plan.form_scanned && plan.document_uploads_detected === false);
  docTitle.textContent = noPortalUpload ? "1. Supporting documents" : "1. Required documents";
  const docList = document.createElement("ul");
  const knownTypes = Array.from(new Set(
    (plan.uploaded_document_types || []).concat(allSelectedDocumentTypes()).filter(Boolean)
  ));
  (plan.documents || []).forEach((documentName) => {
    const item = document.createElement("li");
    const hasDocument = knownTypes.some((type) => documentMatchesRequirement(type, documentName));
    item.className = hasDocument ? "document-ready" : "document-missing";
    item.textContent = (hasDocument ? "Ready: " : "Needed: ") + documentName;
    docList.appendChild(item);
  });
  const docNote = document.createElement("p");
  docNote.textContent = "Upload and extract each available document above before the portal upload step. The authority may request additional evidence.";
  const collect = document.createElement("button");
  collect.type = "button";
  collect.className = "secondary-button full-width";
  collect.textContent = "Add and extract required documents";
  collect.addEventListener("click", () => {
    $("#documents").scrollIntoView({ behavior: "smooth", block: "start" });
    showToast("Add the listed documents, select their type, then choose Extract labelled documents.", "info");
  });
  if (noPortalUpload) {
    const decision = document.createElement("section");
    decision.className = "document-upload-decision";
    const question = document.createElement("p");
    question.textContent = "The scanned form has no document-upload field. Do you still need to prepare supporting documents?";
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
      sessionStorage.setItem(documentDecisionKey(plan), needed ? "yes" : "no");
      collect.hidden = !needed;
      setDocumentPreparationVisibility(needed);
      docNote.textContent = needed
        ? "Prepare these supporting documents for your records or any manual upload the authority requests."
        : "No document preparation selected. Continue with the remaining application details.";
      yes.disabled = needed;
      no.disabled = !needed;
    };
    yes.addEventListener("click", () => setDecision(true));
    no.addEventListener("click", () => setDecision(false));
    actions.append(yes, no);
    decision.append(question, actions);
    documents.append(docTitle, docList, decision, docNote, collect);
    const saved = sessionStorage.getItem(documentDecisionKey(plan));
    if (saved === "yes") setDecision(true);
    else if (saved === "no") setDecision(false);
    else {
      collect.hidden = true;
      setDocumentPreparationVisibility(false);
    }
  } else {
    documents.append(docTitle, docList, docNote, collect);
  }
  flow.appendChild(documents);

  const details = document.createElement("section");
  details.className = "application-details";
  const detailsTitle = document.createElement("h4");
  detailsTitle.textContent = "2. Remaining application details";
  details.appendChild(detailsTitle);
  if (plan.missing_fields.length) {
    const copy = document.createElement("p");
    copy.textContent = "Saarthi needs these answers before it can fill the official form. It will not invent any missing information.";
    const form = document.createElement("form");
    form.className = "application-detail-form";
    plan.fields.filter((field) => field.missing).forEach((field) => appendApplicationQuestion(form, field));
    const save = document.createElement("button");
    save.type = "submit";
    save.className = "secondary-button full-width";
    save.textContent = "Save remaining details";
    form.appendChild(save);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      if (requiredChoiceIsMissing(form)) {
        showToast("Choose at least one option before continuing.", "info");
        return;
      }
      const updates = applicationFormAnswers(form);
      try {
        await api("/sessions/" + sessionId + "/applications/" + plan.service_id + "/details", "POST", { details: updates });
        showToast("Application details saved. Please review them now.", "success");
        await openSaarthiApplication(plan.service_id);
      } catch (error) {
        showToast(error.message, "error");
      }
    });
    details.append(copy, form);
    flow.appendChild(details);
    checklist.appendChild(flow);
    return;
  }
  const ready = document.createElement("p");
  ready.className = "ready-message";
  ready.textContent = "All required form details are saved for this session.";
  details.appendChild(ready);
  flow.appendChild(details);

  const login = document.createElement("section");
  login.className = "portal-login-step";
  const loginTitle = document.createElement("h4");
  loginTitle.textContent = "3. Log in on the official portal";
  const loginCopy = document.createElement("p");
  loginCopy.textContent = "Open the official portal in a separate Saarthi browser window. Complete login, OTP, CAPTCHA, and open the correct application page yourself.";
  const open = document.createElement("button");
  open.type = "button";
  open.className = "primary-button full-width";
  open.textContent = "Open official portal and log in";
  const loggedIn = document.createElement("button");
  loggedIn.type = "button";
  loggedIn.className = "secondary-button full-width";
  loggedIn.textContent = plan.form_scanned ? "Show reviewed form details" : "I am logged in — check requirements";
  loggedIn.disabled = !openedPortalServices.has(plan.service_id);
  open.disabled = !plan.portal_url;
  open.addEventListener("click", async () => {
    open.disabled = true;
    open.textContent = "Opening official portal...";
    try {
      const result = await api("/sessions/" + sessionId + "/launch_browser", "POST", { service_id: plan.service_id });
      showToast(result.message, "success");
      open.textContent = "Official portal opened";
      openedPortalServices.add(plan.service_id);
      loggedIn.disabled = false;
    } catch (error) {
      open.disabled = false;
      open.textContent = "Open official portal and log in";
      showToast(error.message, "error");
    }
  });
  loggedIn.addEventListener("click", async () => {
    if (!plan.form_scanned) {
      loggedIn.disabled = true;
      loggedIn.textContent = "Scanning opened form...";
      try {
        const scannedPlan = await api("/sessions/" + sessionId + "/applications/" + plan.service_id + "/scan-open-form", "POST");
        showToast(scannedPlan.scan_message || "The opened form was scanned.", "success");
        renderSaarthiApplication(scannedPlan);
        return;
      } catch (error) {
        loggedIn.disabled = false;
        loggedIn.textContent = "I am logged in — check requirements";
        showToast(error.message, "error");
        return;
      }
    }
    if (plan.automation_available) {
      if (!flow.querySelector(".application-review")) renderApplicationReview(flow, plan, true);
      loggedIn.textContent = "Review shown below";
      loggedIn.disabled = true;
      flow.querySelector(".application-review").scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    const manual = document.createElement("p");
    manual.className = "automation-safety";
    manual.textContent = "This service has no verified portal mapping yet. Use the official portal to enter the reviewed details and upload documents yourself.";
    flow.appendChild(manual);
    loggedIn.textContent = "Use portal manually";
    loggedIn.disabled = true;
  });
  login.append(loginTitle, loginCopy, open, loggedIn);
  flow.appendChild(login);
  const automation = document.createElement("p");
  automation.className = plan.automation_available ? "ready-message" : "automation-safety";
  automation.textContent = plan.automation_message;
  flow.appendChild(automation);
  const safety = document.createElement("p");
  safety.className = "automation-safety";
  safety.textContent = plan.safety_note;
  flow.appendChild(safety);
  checklist.appendChild(flow);
}

async function openSaarthiApplication(serviceId = activeServiceId) {
  if (!sessionId) return;
  if (!serviceId) {
    showToast("Choose a government service first.", "info");
    return;
  }
  if (!isApplicationPageRoute()) {
    navigateToApplicationPage({ service: serviceId });
    return;
  }
  try {
    const plan = await api("/sessions/" + sessionId + "/applications/" + encodeURIComponent(serviceId) + "/readiness");
    openApplicationPage();
    renderSaarthiApplication(plan);
    $("#application-page").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showToast(error.message, "error");
  }
}

function appendLiveApplicationDocuments(flow, plan) {
  const documents = document.createElement("section");
  documents.className = "application-documents";
  const title = document.createElement("h4");
  title.textContent = "1. Required documents";
  const list = document.createElement("ul");
  const knownTypes = Array.from(new Set(
    (plan.uploaded_document_types || []).concat(allSelectedDocumentTypes()).filter(Boolean)
  ));
  (plan.documents || []).forEach((documentName) => {
    const item = document.createElement("li");
    const ready = knownTypes.some((type) => documentMatchesRequirement(type, documentName));
    item.className = ready ? "document-ready" : "document-missing";
    item.textContent = (ready ? "Ready: " : "Needed: ") + documentName;
    list.appendChild(item);
  });
  const copy = document.createElement("p");
  copy.textContent = plan.documents && plan.documents.length
    ? "Add and extract each available document before filling the official form."
    : "The official form did not expose document rows. Confirm the latest document list on the portal before applying.";
  const collect = document.createElement("button");
  collect.type = "button";
  collect.className = "secondary-button full-width";
  collect.textContent = "Add and extract required documents";
  collect.addEventListener("click", () => {
    $("#documents").scrollIntoView({ behavior: "smooth", block: "start" });
    showToast("Add the listed documents, select their type, then choose Extract labelled documents.", "info");
  });
  documents.append(title, list, copy, collect);
  flow.appendChild(documents);
}

function renderLiveApplicationReview(flow, plan) {
  const review = document.createElement("section");
  review.className = "application-review";
  const title = document.createElement("h4");
  title.textContent = "Review the details Saarthi will fill";
  const note = document.createElement("p");
  note.textContent = "Saarthi fills only these reviewed visible fields. It will not read passwords, OTPs, CAPTCHAs, existing values, or submit the application.";
  const list = document.createElement("dl");
  list.className = "review-list";
  plan.fields.forEach((field) => {
    const row = document.createElement("div");
    const label = document.createElement("dt");
    label.textContent = field.label;
    const value = document.createElement("dd");
    value.textContent = field.value || "Not provided";
    row.append(label, value);
    list.appendChild(row);
  });
  const confirm = document.createElement("label");
  confirm.className = "check-control review-confirm";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  const text = document.createElement("span");
  text.textContent = "I reviewed these details and want Saarthi to fill the opened official form.";
  confirm.append(checkbox, text);
  const fill = document.createElement("button");
  fill.type = "button";
  fill.className = "primary-button full-width";
  fill.textContent = "Fill the reviewed form";
  fill.addEventListener("click", async () => {
    if (!checkbox.checked) {
      showToast("Please confirm that you reviewed the details first.", "info");
      return;
    }
    fill.disabled = true;
    fill.textContent = "Filling the official form...";
    try {
      const result = await api("/sessions/" + sessionId + "/live-application/automate-fill", "POST");
      fill.textContent = "Fields filled — review in Chrome";
      showToast(result.message || "Fields filled. Saarthi did not save or continue the official form.", "success");
      renderPostFillReview(flow, plan, result.message);
    } catch (error) {
      fill.disabled = false;
      fill.textContent = "Fill the reviewed form";
      showToast(error.message, "error");
    }
  });
  review.append(title, note, list, confirm, fill);
  flow.appendChild(review);
}

function renderLiveApplication(plan) {
  setApplicationDocumentRequirements(plan);
  const pageTitle = $("#application-page-title");
  if (pageTitle) pageTitle.textContent = plan.service + " with Saarthi";
  const checklist = $("#service-checklist");
  checklist.hidden = false;
  checklist.innerHTML = "";
  const flow = document.createElement("section");
  flow.className = "saarthi-application-flow";
  const title = document.createElement("h3");
  title.textContent = plan.service + " with Saarthi";
  const intro = document.createElement("p");
  intro.textContent = "Saarthi will inspect the application form you open, collect the required documents and missing answers, then fill only the values you review. You submit the final application yourself.";
  flow.append(title, intro);

  if (!plan.form_scanned) {
    const login = document.createElement("section");
    login.className = "portal-login-step";
    const loginTitle = document.createElement("h4");
    loginTitle.textContent = "1. Open and inspect the official application form";
    const loginCopy = document.createElement("p");
    loginCopy.textContent = "Log in, complete any OTP or CAPTCHA yourself, and navigate to the actual application form. Then let Saarthi check the required fields and documents.";
    const open = document.createElement("button");
    open.type = "button";
    open.className = "primary-button full-width";
    open.textContent = "Open official portal and log in";
    const scan = document.createElement("button");
    scan.type = "button";
    scan.className = "secondary-button full-width";
    scan.textContent = "I am logged in — check requirements";
    scan.disabled = !openedPortalServices.has(plan.service_id);
    open.addEventListener("click", async () => {
      open.disabled = true;
      try {
        const result = await api("/sessions/" + sessionId + "/live-application/launch", "POST");
        openedPortalServices.add(plan.service_id);
        showToast(result.message, "success");
        renderLiveApplication(plan);
      } catch (error) {
        open.disabled = false;
        showToast(error.message, "error");
      }
    });
    scan.addEventListener("click", async () => {
      scan.disabled = true;
      scan.textContent = "Checking requirements...";
      try {
        const scannedPlan = await api("/sessions/" + sessionId + "/live-application/scan-open-form", "POST");
        showToast(scannedPlan.scan_message || "The opened form was checked.", "success");
        renderLiveApplication(scannedPlan);
      } catch (error) {
        scan.disabled = false;
        scan.textContent = "I am logged in — check requirements";
        showToast(error.message, "error");
      }
    });
    login.append(loginTitle, loginCopy, open, scan);
    flow.appendChild(login);
    checklist.appendChild(flow);
    return;
  }

  const scanned = document.createElement("p");
  scanned.className = "ready-message";
  scanned.textContent = "Requirements were read from " + ((plan.scanned_form && plan.scanned_form.title) || "the opened application form") + ".";
  flow.appendChild(scanned);
  appendLiveApplicationDocuments(flow, plan);

  const details = document.createElement("section");
  details.className = "application-details";
  const detailsTitle = document.createElement("h4");
  detailsTitle.textContent = "2. Details not found in your documents";
  details.appendChild(detailsTitle);
  if (plan.missing_fields.length) {
    const copy = document.createElement("p");
    copy.textContent = "Saarthi could not find these required answers in your saved details or documents. Please provide them before filling the form.";
    const form = document.createElement("form");
    form.className = "application-detail-form";
    plan.fields.filter((field) => field.missing).forEach((field) => appendApplicationQuestion(form, field));
    const save = document.createElement("button");
    save.type = "submit";
    save.className = "secondary-button full-width";
    save.textContent = "Save missing details";
    form.appendChild(save);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      if (requiredChoiceIsMissing(form)) {
        showToast("Choose at least one option before continuing.", "info");
        return;
      }
      try {
        const updatedPlan = await api("/sessions/" + sessionId + "/live-application/details", "POST", {
          details: applicationFormAnswers(form),
        });
        showToast("Application details saved. Please review them now.", "success");
        renderLiveApplication(updatedPlan);
      } catch (error) {
        showToast(error.message, "error");
      }
    });
    details.append(copy, form);
    flow.appendChild(details);
    checklist.appendChild(flow);
    return;
  }
  const ready = document.createElement("p");
  ready.className = "ready-message";
  ready.textContent = "All required answers are ready for review.";
  details.appendChild(ready);
  flow.appendChild(details);
  renderLiveApplicationReview(flow, plan);
  const safety = document.createElement("p");
  safety.className = "automation-safety";
  safety.textContent = plan.safety_note;
  flow.appendChild(safety);
  checklist.appendChild(flow);
}

async function startGenericLiveApplication(source) {
  if (!source || !source.url) {
    showToast("Choose an official website from the live guidance list first.", "info");
    return;
  }
  try {
    if (!isApplicationPageRoute()) {
      navigateToApplicationPage({
        live: "1",
        source_url: source.url,
        source_title: source.title || "Official government application",
      });
      return;
    }
    const plan = await api("/sessions/" + sessionId + "/live-application", "POST", {
      title: source.title || "Official government application",
      url: source.url,
    });
    openApplicationPage();
    renderLiveApplication(plan);
    const result = await api("/sessions/" + sessionId + "/live-application/launch", "POST");
    openedPortalServices.add(plan.service_id);
    renderLiveApplication(plan);
    $("#application-page").scrollIntoView({ behavior: "smooth", block: "start" });
    showToast(result.message, "success");
    addMessage("assistant", "The official portal is open. Log in yourself, open the application form, then choose ‘I am logged in — check requirements’. ");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function startLiveGuidedApplication(serviceId, source = null) {
  if (!sessionId) return;
  if (!serviceId) {
    await startGenericLiveApplication(source);
    return;
  }
  if (!isApplicationPageRoute()) {
    navigateToApplicationPage({ service: serviceId });
    return;
  }
  try {
    await selectService(serviceId);
    const plan = await api("/sessions/" + sessionId + "/applications/" + encodeURIComponent(serviceId) + "/readiness");
    openApplicationPage();
    renderSaarthiApplication(plan);

    const result = await api("/sessions/" + sessionId + "/launch_browser", "POST", { service_id: serviceId });
    openedPortalServices.add(serviceId);
    renderSaarthiApplication(plan);
    $("#application-page").scrollIntoView({ behavior: "smooth", block: "start" });
    showToast(result.message, "success");
    addMessage(
      "assistant",
      "The official portal is open. Log in, complete any OTP or CAPTCHA yourself, then open the application form and choose ‘I am logged in — check requirements’."
    );
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function resumeApplicationRoute() {
  if (!isApplicationPageRoute() || !sessionId) return;
  const query = new URLSearchParams(window.location.search);
  const serviceId = query.get("service");
  if (serviceId) {
    await startLiveGuidedApplication(serviceId);
    return;
  }
  if (query.get("live") !== "1") {
    returnToDashboard();
    return;
  }
  try {
    const plan = await api("/sessions/" + sessionId + "/live-application/readiness");
    openApplicationPage();
    renderLiveApplication(plan);
    const result = await api("/sessions/" + sessionId + "/live-application/launch", "POST");
    openedPortalServices.add(plan.service_id);
    renderLiveApplication(plan);
    $("#application-page").scrollIntoView({ behavior: "smooth", block: "start" });
    showToast(result.message, "success");
  } catch (error) {
    returnToDashboard();
    showToast("This application page could not be restored: " + error.message, "error");
  }
}

async function refreshApplicationAfterDocumentExtraction() {
  if (!activeApplicationServiceId || !sessionId) return false;
  try {
    const isLiveApplication = activeApplicationType === "live_guidance";
    const plan = await api(isLiveApplication
      ? "/sessions/" + sessionId + "/live-application/readiness"
      : "/sessions/" + sessionId + "/applications/" + encodeURIComponent(activeApplicationServiceId) + "/readiness"
    );
    if (isLiveApplication) renderLiveApplication(plan);
    else renderSaarthiApplication(plan);
    if (plan.missing_fields && plan.missing_fields.length) {
      const labels = plan.fields
        .filter((field) => field.missing)
        .map((field) => field.label)
        .join(", ");
      addMessage(
        "assistant",
        "I extracted the available documents. I still need " + labels + ". Please complete these fields in the Saarthi application preparation panel."
      );
      showToast("More application details are needed before Saarthi can fill the form.", "info");
    } else {
      addMessage("assistant", "I extracted the available documents. Your required application details are now ready for review.");
    }
    return true;
  } catch (error) {
    showToast("Documents were extracted, but the application plan could not be refreshed: " + error.message, "info");
    return false;
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
    const assignments = document.createElement("fieldset");
    assignments.className = "document-type-options";
    const legend = document.createElement("legend");
    legend.textContent = SaarthiI18n.t("documentUses");
    assignments.appendChild(legend);
    const documentChoices = Array.from(new Set(requiredApplicationDocuments.concat(DOCUMENT_TYPES)));
    documentChoices.forEach((documentType) => {
      const choice = document.createElement("label");
      choice.className = "document-type-choice";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = documentType;
      checkbox.checked = documentTypesFor(file).includes(documentType);
      checkbox.addEventListener("change", () => {
        const selected = Array.from(assignments.querySelectorAll("input:checked"))
          .map((input) => input.value);
        setDocumentTypes(selectedFiles[index], selected);
      });
      const text = document.createElement("span");
      text.textContent = documentType;
      choice.append(checkbox, text);
      assignments.appendChild(choice);
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
    item.append(info, assignments, remove);
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
    const unlabelled = selectedFiles.filter((item) => documentTypesFor(item).length === 0);
    if (unlabelled.length) {
      throw new Error("Choose at least one use for every uploaded file before extracting.");
    }

    let extractedCount = 0;
    const errors = [];
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
        applyExtractedFields(result.summary || {});
        Object.assign(savedProfileData, result.summary || {});
        renderSavedProfileData();
        if (result.extra_fields && Object.keys(result.extra_fields).length) {
          additionalDocumentData.push({ documentType: documentTypes.join(", "), fields: result.extra_fields });
          renderAdditionalDocumentData();
        }
        extractedCount += 1;
      } catch (error) {
        errors.push(item.file.name);
      }
    }
    let profileSaved = false;
    let applicationPlanRefreshed = false;
    if (extractedCount) {
      try {
        await saveProfile({ quiet: true });
        profileSaved = true;
      } catch (error) {
        showToast("Documents were processed, but please review the extracted profile details before saving.", "info");
      }
      applicationPlanRefreshed = await refreshApplicationAfterDocumentExtraction();
    }
    updateReadiness();
    $("#scan-status").textContent = extractedCount + " document" + (extractedCount === 1 ? "" : "s") + (profileSaved ? " processed and saved to your profile." : " processed. Please review your profile before saving.");
    if (errors.length) {
      showToast("Could not process: " + errors.join(", ") + ".", "error");
    } else {
      showToast("Labelled document details have been added to the profile.", "success");
      addMessage("assistant", "I processed your labelled documents. Please check the profile fields and correct anything that looks wrong.");
    }
    if (extractedCount && !applicationPlanRefreshed) askForMissingDetails();
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
    state: "#profile-state", district: "#profile-district", occupation: "#profile-occupation",
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

async function askAssistant(message, { autoApply = false } = {}) {
  const question = message.trim();
  if (!question) return;
  addMessage("user", question);
  $("#assistant-input").value = "";
  try {
    await saveProfile({ quiet: true });
    const result = await api("/sessions/" + sessionId + "/assistant", "POST", { message: question });
    // Answers collected in chat are saved to the same profile shown in
    // "Your details", so the citizen can review or correct them immediately.
    if (result.profile) {
      restoreProfile(result.profile);
      await loadServices();
    }
    addMessage("assistant", result.reply);
    if (result.pending_request && result.pending_request.question_options) {
      addChoiceMessage(result.pending_request.question_options);
    }
    renderSchemes(result.recommendations || []);
    renderLiveGuidance(result.live_guidance, result.application_service_id, result.services);
    if (result.application_service_id && !result.live_guidance) await selectService(result.application_service_id);
    if (result.saved_profile_fields && result.saved_profile_fields.length) {
      showToast("Saved from chat: " + result.saved_profile_fields.join(", ") + ".", "success");
    }
    if (result.profile_gaps && result.profile_gaps.length) {
      showToast("For better matches, add: " + result.profile_gaps.join(", ") + ".", "info");
    }
    return result;
  } catch (error) {
    addMessage("assistant", "I could not process that request right now. Please check your details and try again.");
    showToast(error.message, "error");
    return null;
  }
}

async function changeLanguage() {
  language = $("#language-select").value;
  SaarthiI18n.setLanguage(language);
  language = SaarthiI18n.getLanguage();
  $("#language-select").value = language;
  syncVoiceButton();
  try {
    await api("/sessions/" + sessionId + "/language", "POST", { language });
    showToast(language === "en" ? "Language preference saved." : SaarthiI18n.t("language") + " ✓", "success");
    speakAssistant(SaarthiI18n.t("language") + ".");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function restoreProfile(profile = {}) {
  const bindings = {
    name: "#profile-name", age: "#profile-age", dob: "#profile-dob",
    gender: "#profile-gender", state: "#profile-state", district: "#profile-district",
    occupation: "#profile-occupation", annual_income: "#profile-income",
    mobile: "#profile-mobile", address: "#profile-address", caste_category: "#profile-category",
    land_acres: "#profile-land", employment_sector: "#profile-sector", house_type: "#profile-house",
  };
  Object.entries(bindings).forEach(([field, selector]) => {
    if (profile[field] !== undefined && profile[field] !== null) $(selector).value = String(profile[field]);
  });
  ["is_bpl", "has_lpg_connection", "is_student", "is_entrepreneur", "is_pregnant", "is_first_child"].forEach((field) => {
    const input = $(`[name="${field}"]`);
    if (input && profile[field] !== undefined) input.checked = Boolean(profile[field]);
  });
  updateReadiness();
}

function onboardingProfileComplete(profile = null) {
  const data = profile || profilePayload();
  return data.age !== null && data.age !== "" && data.gender && data.state && data.district
    && data.occupation && data.annual_income !== null && data.annual_income !== ""
    && data.caste_category;
}

function resumeOnboarding(profile = {}) {
  const saved = readOnboardingState();
  if (saved && saved.answers) {
    onboardingAnswers = saved.answers;
    ONBOARDING_STEPS.slice(1).forEach(({ key }) => {
      setProfileInputValue(key, Object.prototype.hasOwnProperty.call(onboardingAnswers, key) ? onboardingAnswers[key] : "");
    });
    onboardingStep = Math.max(0, Math.min(Number(saved.step) || 0, ONBOARDING_STEPS.length));
    if (saved.complete && onboardingProfileComplete(profile)) onboardingStep = ONBOARDING_STEPS.length;
  } else if (onboardingProfileComplete(profile)) {
    onboardingAnswers = {
      age: profile.age,
      gender: profile.gender,
      state: profile.state,
      district: profile.district,
      occupation: profile.occupation,
      annual_income: profile.annual_income,
      caste_category: profile.caste_category,
    };
    onboardingStep = ONBOARDING_STEPS.length;
    saveOnboardingState(true);
  } else {
    const firstMissing = ONBOARDING_STEPS.slice(1).findIndex((step) => !onboardingValue(step.key));
    onboardingStep = firstMissing < 0 ? 1 : firstMissing + 1;
  }
  if (onboardingStep >= ONBOARDING_STEPS.length) hideOnboarding();
  else renderOnboardingStep();
}

async function endSession() {
  if (!sessionId || !window.confirm("End this session and erase its saved session data?")) return;
  try {
    await api("/sessions/" + sessionId, "DELETE");
    if (isApplicationPageRoute()) window.history.replaceState({}, "", "/");
    closeApplicationPage();
    sessionId = null;
    selectedFiles = [];
    additionalDocumentData = [];
    savedProfileData = {};
    activeApplicationServiceId = null;
    activeApplicationType = null;
    requiredApplicationDocuments = [];
    onboardingAnswers = {};
    onboardingStep = 0;
    language = "en";
    speechEnabled = false;
    localStorage.removeItem(SESSION_STORAGE_KEY);
    localStorage.removeItem(ONBOARDING_STORAGE_KEY);
    localStorage.removeItem(PORTAL_OPEN_STORAGE_KEY);
    localStorage.setItem(VOICE_STORAGE_KEY, "false");
    $("#profile-form").reset();
    $("#chat-log").innerHTML = "";
    const applicationDocumentRequest = $("#application-document-request");
    if (applicationDocumentRequest) applicationDocumentRequest.hidden = true;
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
  let session = null;
  const savedSessionId = localStorage.getItem(SESSION_STORAGE_KEY);
  if (savedSessionId) {
    try {
      session = await api("/sessions/" + savedSessionId);
      sessionId = session.session_id;
      language = session.language || SaarthiI18n.getLanguage() || language;
      SaarthiI18n.setLanguage(language);
      language = SaarthiI18n.getLanguage();
      restoreProfile(session.profile || {});
      renderSchemes(session.eligibility || []);
    } catch (error) {
      localStorage.removeItem(SESSION_STORAGE_KEY);
      localStorage.removeItem(ONBOARDING_STORAGE_KEY);
      sessionId = null;
    }
  }
  if (!session) {
    session = await api("/sessions", "POST");
    sessionId = session.session_id;
    localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    language = SaarthiI18n.getLanguage() || "en";
    SaarthiI18n.setLanguage(language);
    language = SaarthiI18n.getLanguage();
    await api("/sessions/" + sessionId + "/language", "POST", { language });
    if (session.profile) {
      restoreProfile(session.profile);
    } else {
      onboardingStep = 0;
      onboardingAnswers = {};
      saveOnboardingState(false);
    }
  }
  $("#language-select").value = language;
  SaarthiI18n.apply();
  syncVoiceButton();
  $("#session-status").textContent = "Secure session active";
  await loadServices();
  updateReadiness();
  if (session.profile) resumeOnboarding(session.profile);
  else renderOnboardingStep();
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
      Array.from(event.target.files || []).map((file) => ({ file, documentType: "", documentTypes: [] }))
    );
    event.target.value = "";
    renderDocuments();
  });
  $("#scan-documents-button").addEventListener("click", extractDocuments);
  $("#end-session-button").addEventListener("click", endSession);
  $("#voice-toggle").addEventListener("click", toggleSpeech);
  $("#microphone-button").addEventListener("click", startListening);
  $("#onboarding-next").addEventListener("click", () => advanceOnboarding().catch((error) => showToast(error.message, "error")));
  $("#onboarding-back").addEventListener("click", goBackOnboarding);
  $("#onboarding-end-session").addEventListener("click", endSession);
}

window.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  syncVoiceButton();
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
