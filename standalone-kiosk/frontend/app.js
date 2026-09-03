/**
 * JanSeva AI Kiosk — Frontend Application Logic
 *
 * Drives the 6-state wizard:
 *   GREET → IDENTIFY → CHECKLIST → SCAN → FILL → DELIVER
 */

const API = window.location.origin;

// ── State ──
let sessionId = null;
let currentStep = 0; // 0-based: 0=GREET, 1=IDENTIFY, 2=CHECKLIST, 3=SCAN, 4=FILL, 5=DELIVER
let language = "hi";
let selectedServiceId = null;
let scanData = null;
let schemeResults = [];
let deliverData = null;
let selectedImages = [];

// ── DOM Refs ──
const panels = () => document.querySelectorAll(".panel");
const stepItems = () => document.querySelectorAll(".step-item");
const connectors = () => document.querySelectorAll(".step-connector");

// ── Service icon mapping ──
const SERVICE_ICONS = {
  CERT_INC: "📄",
  CERT_DOM: "🏠",
  CERT_CST: "📜",
  CERT_NCL: "📋",
  CERT_EWS: "🆔",
  LAND_712: "🌾",
  PERM_BDC: "👶",
  SCH_RAT: "🍚",
};

// ── Helpers ──
async function api(path, method = "GET", body = null) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${API}${path}`, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

function toast(msg, type = "info") {
  const container =
    document.querySelector(".toast-container") || createToastContainer();
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function createToastContainer() {
  const c = document.createElement("div");
  c.className = "toast-container";
  document.body.appendChild(c);
  return c;
}

function showPanel(index) {
  // Cancel any ongoing text-to-speech when navigating
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
    const btn = document.getElementById("btn-read-aloud");
    if (btn) btn.innerText = "🔊";
  }

  currentStep = index;
  panels().forEach((p, i) => p.classList.toggle("active", i === index));
  stepItems().forEach((s, i) => {
    s.classList.remove("active", "done");
    // Since our progress bar starts at Checklist (index 1), subtract 1 from i
    if (i < index - 1) s.classList.add("done");
    else if (i === index - 1) s.classList.add("active");
  });
  connectors().forEach((c, i) => {
    c.classList.toggle("done", i < index - 1);
  });
}

// Auto-initialize session
window.addEventListener('DOMContentLoaded', async () => {
  try {
    const session = await api("/sessions", "POST");
    sessionId = session.session_id;
    // Load all services for the state 'Goa' by default
    loadServices('Goa');
  } catch (e) {
    toast("Failed to initialize session.", "error");
  }
});

// ===================================================================
// STEP 0: GREET — Language Selection
// ===================================================================
async function selectLanguage(lang) {
  try {
    // Create session first
    const session = await api("/sessions", "POST");
    sessionId = session.session_id;

    // Set language
    language = lang;
    const result = await api(`/sessions/${sessionId}/language`, "POST", {
      language: lang,
    });

    showPanel(0); // Show HOME (Service Selection)
    const greetings = {
      en: "Welcome! Select an option",
      hi: "स्वागत! अपना विकल्प चुनें",
      mr: "स्वागत आहे! आपला पर्याय निवडा",
      gu: "સ્વાગત છે! તમારો વિકલ્પ પસંદ કરો"
    };
    toast(greetings[lang] || greetings['hi'], "success");
  } catch (e) {
    toast(e.message, "error");
  }
}

// ===================================================================
// STEP 1.5: HOME — Portal & State Selection
// ===================================================================
async function selectState(state) {
  try {
    // Update UI and session context
    document.getElementById('card-official').style.display = 'none';
    document.getElementById('card-admin').style.display = 'none';
    
    await api(`/sessions/${sessionId}/state`, "POST", { state: state });
    
    // Update Header to show selected state
    document.getElementById("status-lang").innerHTML = `<b>${window.selectedLanguage}</b> | State: <b>${state}</b>`;

    // Move to next step
    document.getElementById('panel-home').classList.remove('active');
    document.getElementById('panel-identify').classList.add('active');

    loadServices(state);
  } catch (e) {
    toast("Error: " + e.message + " (Please refresh the page)", "error");
  }
}

async function loadServices(state) {
  const container = document.getElementById("service-grid");
  container.innerHTML = '<div class="spinner"></div>';
  try {
    const url = state ? `/services?state=${encodeURIComponent(state)}&_t=${Date.now()}` : `/services?_t=${Date.now()}`;
    const services = await api(url);
    renderServiceList(services);
  } catch (e) {
    toast("Error fetching services: " + e.message, "error");
  }
}

function openAdminAuth() {
  document.getElementById('admin-auth-modal').style.display = 'flex';
  document.getElementById('admin-auth-error').style.display = 'none';
  document.getElementById('admin-username').value = '';
  document.getElementById('admin-password').value = '';
}

function closeAdminAuth() {
  document.getElementById('admin-auth-modal').style.display = 'none';
}

function submitAdminAuth() {
  const user = document.getElementById('admin-username').value;
  const pass = document.getElementById('admin-password').value;
  
  if (user === 'vedant' && pass === 'vedant') {
    closeAdminAuth();
    showPanel(5);
    adminReset();
  } else {
    document.getElementById('admin-auth-error').style.display = 'block';
  }
}

// ===================================================================
// STEP 1: IDENTIFY — Service Selection
// ===================================================================
function renderServiceList(options) {
  const grid = document.getElementById("service-grid");
  grid.innerHTML = "";
  options.forEach((opt) => {
    const card = document.createElement("button");
    card.className = "service-card";
    card.onclick = () => selectService(opt.id);
    card.innerHTML = `
      <div class="svc-icon">${SERVICE_ICONS[opt.id] || "📄"}</div>
      <div>
        <div class="svc-name">${opt.label}</div>
        <div class="svc-cat">${opt.id.replace(/_/g, " ")}</div>
      </div>
    `;
    grid.appendChild(card);
  });
}

async function triggerAutoFill() {
  if (!sessionId) {
    toast("No active session.", "error");
    return;
  }
  
  // Map selectedServiceId to the correct Python mapping file
  let certType = "income_certificate";
  if (selectedServiceId === "REV07" || selectedServiceId === "RESIDENCE") {
      certType = "residence_certificate";
  } else if (selectedServiceId === "DOMICILE") {
      certType = "domicile_certificate";
  } else if (selectedServiceId === "CASTE") {
      certType = "caste_certificate";
  }
  
  const btn = document.getElementById("btn-trigger-fill");
  const originalText = btn ? btn.innerHTML : "";
  if (btn) {
    btn.innerHTML = '<span class="spinner" style="width:16px;height:16px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:8px;"></span>Filling Form...';
    btn.disabled = true;
  }
  
  try {
    const res = await api(`/sessions/${sessionId}/automate_fill`, "POST", { 
        port: 9222,
        certificate_type: certType
    });
    if (res.action === "filling") {
      toast("Selenium form filling started! Switch to your Goa Online browser window.", "success");
    }
  } catch (err) {
    toast("Error triggering autofill: " + err.message, "error");
  } finally {
    if (btn) {
      setTimeout(() => {
        btn.innerHTML = originalText;
        btn.disabled = false;
      }, 5000);
    }
  }
}

async function selectService(serviceId) {
  try {
    selectedServiceId = serviceId;
    const result = await api(`/sessions/${sessionId}/service`, "POST", {
      service_id: serviceId,
    });
    renderChecklist(result.summary);
    showPanel(1);
  } catch (e) {
    toast(e.message, "error");
  }
}

// ===================================================================
// STEP 3: CHECKLIST
// ===================================================================
function renderChecklist(summary) {
  if (!summary) return;

  document.getElementById("cl-service").textContent = summary.service || "";
  document.getElementById("cl-fee").textContent = summary.fee || "—";
  document.getElementById("cl-processing").textContent = summary.processing || "—";
  document.getElementById("cl-validity").textContent = summary.validity || "—";

  const list = document.getElementById("checklist-items");
  list.innerHTML = "";
  (summary.items || []).forEach((item) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="doc-num">${item.number}</div>
      <div class="doc-info">
        <div class="doc-name">${item.name}</div>
        ${item.detail ? `<div class="doc-detail">${item.detail}</div>` : ""}
        ${item.alternatives ? `<div class="doc-alt">✅ Alternatives: ${item.alternatives.join(", ")}</div>` : ""}
        ${item.note ? `<div class="doc-note">ℹ️ ${item.note}</div>` : ""}
      </div>
    `;
    list.appendChild(li);
  });
}

async function confirmChecklist() {
  try {
    await api(`/sessions/${sessionId}/checklist/confirm`, "POST");
    showPanel(2);
  } catch (e) {
    toast(e.message, "error");
  }
}

// ===================================================================
// STEP 4: SCAN
// ===================================================================
let pendingQuestions = [];
let gatheredAnswers = [];

function compressImage(file, maxDimension = 1024, quality = 0.75) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        let width = img.width;
        let height = img.height;
        if (width > height) {
          if (width > maxDimension) {
            height = Math.round((height * maxDimension) / width);
            width = maxDimension;
          }
        } else {
          if (height > maxDimension) {
            width = Math.round((width * maxDimension) / height);
            height = maxDimension;
          }
        }
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, width, height);
        resolve(canvas.toDataURL("image/jpeg", quality));
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  });
}

async function handleImageSelect(event) {
  const files = event.target ? event.target.files : event;
  if (!files || files.length === 0) return;
  
  const previewArea = document.getElementById("image-preview-area");
  if (previewArea) previewArea.style.display = "block";
  const previewContainer = document.getElementById("image-previews");
  if (!selectedImages) selectedImages = [];

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    const base64Str = await compressImage(file);
    selectedImages.push({ name: file.name, data: base64Str });
    
    if (previewContainer) {
      const card = document.createElement("div");
      card.style.display = "flex";
      card.style.alignItems = "center";
      card.style.gap = "12px";
      card.style.background = "white";
      card.style.padding = "8px 12px";
      card.style.borderRadius = "8px";
      card.style.border = "1px solid #cbd5e1";

      const img = document.createElement("img");
      img.src = base64Str;
      img.style.width = "70px";
      img.style.height = "70px";
      img.style.objectFit = "cover";
      img.style.borderRadius = "6px";
      img.style.border = "1px solid var(--border)";

      const info = document.createElement("div");
      info.style.textAlign = "left";
      const sizeKb = Math.round(file.size / 1024);
      info.innerHTML = `
        <div style="font-weight: 700; font-size: 13px; color: #1e293b; max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${file.name}</div>
        <div style="font-size: 11px; color: #64748b;">${sizeKb} KB • Ready for AI extraction</div>
      `;

      card.appendChild(img);
      card.appendChild(info);
      previewContainer.appendChild(card);
    }
  }
  toast(`Selected ${files.length} document image${files.length > 1 ? 's' : ''}`, "success");
}

function clearSelectedImages() {
  selectedImages = [];
  const fileInput = document.getElementById("scan-file-input");
  if (fileInput) fileInput.value = "";
  const previewArea = document.getElementById("image-preview-area");
  if (previewArea) previewArea.style.display = "none";
  const previewContainer = document.getElementById("image-previews");
  if (previewContainer) previewContainer.innerHTML = "";
  toast("Cleared document image", "info");
}

async function loadSampleDocument(filename = "vilas_rakhe.png") {
  try {
    const res = await fetch(`/scans/${filename}`);
    if (!res.ok) throw new Error("Could not fetch sample document");
    const blob = await res.blob();
    const base64Str = await new Promise((resolve) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result);
      reader.readAsDataURL(blob);
    });
    
    document.getElementById("image-preview-area").style.display = "block";
    const previewContainer = document.getElementById("image-previews");
    previewContainer.innerHTML = "";
    selectedImages = [{ name: filename, data: base64Str }];

    const img = document.createElement("img");
    img.src = base64Str;
    img.style.width = "100px";
    img.style.height = "100px";
    img.style.objectFit = "cover";
    img.style.borderRadius = "8px";
    img.style.border = "2px solid var(--primary)";
    previewContainer.appendChild(img);
    toast(`Loaded sample document (${filename})`, "success");
    return true;
  } catch (err) {
    console.warn("Sample doc load failed:", err);
    return false;
  }
}

async function performScan() {
  if (selectedImages.length === 0) {
    toast("No image uploaded — loading demo sample document...", "info");
    await loadSampleDocument("vilas_rakhe.png");
  }

  if (selectedImages.length === 0) {
    toast("Please select or drop at least one document image first", "error");
    return;
  }

  const btn = document.getElementById("scan-btn");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Extracting Information with AI...';

  const docType = document.getElementById("scan-doc-type").value || "document";

  try {
    const result = await api(`/sessions/${sessionId}/scan`, "POST", {
      expected_type: docType,
      images: selectedImages
    });

    if (result.summary && Object.keys(result.summary).length > 0) {
      scanData = result.summary;
      renderScanResult(result.summary);
      document.getElementById("scan-confirm-area").style.display = "block";
      document.getElementById("scan-btn").style.display = "none";
      document.getElementById("scan-confirm-area").scrollIntoView({ behavior: "smooth" });
      toast(`AI successfully extracted ${Object.keys(result.summary).length} fields!`, "success");
    } else if (result.action === "ask" && result.questions && result.questions.length > 0) {
      pendingQuestions = result.questions;
      gatheredAnswers = [];
      askNextQuestion();
    } else {
      toast("No readable data could be extracted. Please upload a clear photo.", "warning");
    }
  } catch (e) {
    toast("Extraction failed: " + e.message, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = "⚡ Extract Information with AI";
  }
}

function speakText(text) {
  if (!window.speechSynthesis) return;
  const utterance = new SpeechSynthesisUtterance(text);
  if (language === "hi") utterance.lang = "hi-IN";
  else if (language === "mr") utterance.lang = "mr-IN";
  else utterance.lang = "en-IN";
  window.speechSynthesis.speak(utterance);
}

function startDictation() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    toast("Speech recognition is not supported in this browser.", "warning");
    return;
  }
  
  const recognition = new SpeechRecognition();
  if (language === "hi") recognition.lang = "hi-IN";
  else if (language === "mr") recognition.lang = "mr-IN";
  else recognition.lang = "en-IN";
  
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  
  const inputEl = document.getElementById("chat-input");
  inputEl.placeholder = "Listening...";
  
  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    inputEl.value = transcript;
    inputEl.placeholder = "Type your answer here...";
    sendScanAnswer();
  };
  
  recognition.onspeechend = () => {
    recognition.stop();
    inputEl.placeholder = "Type your answer here...";
  };
  
  recognition.onerror = (event) => {
    inputEl.placeholder = "Type your answer here...";
    toast("Microphone error: " + event.error, "error");
  };
  
  recognition.start();
}

function askNextQuestion() {
  if (pendingQuestions.length > 0) {
    const nextQ = pendingQuestions.shift();
    document.getElementById("chat-area").style.display = "block";
    document.getElementById("chat-question").innerText = nextQ;
    document.getElementById("chat-input").value = "";
    document.getElementById("chat-input").focus();
    speakText(nextQ);
  } else {
    submitGatheredAnswers();
  }
}

async function sendScanAnswer() {
  const answer = document.getElementById("chat-input").value.trim();
  if (!answer) return;
  
  const currentQ = document.getElementById("chat-question").innerText;
  gatheredAnswers.push(`Q: ${currentQ}\nA: ${answer}`);
  
  document.getElementById("chat-area").style.display = "none";
  askNextQuestion();
}

async function submitGatheredAnswers() {
  const docType = document.getElementById("scan-doc-type").value || "document";
  const btn = document.getElementById("scan-btn");
  btn.innerHTML = '<span class="spinner"></span> AI is analyzing your responses...';
  
  const combinedAnswers = gatheredAnswers.join("\n\n");
  
  try {
    const result = await api(`/sessions/${sessionId}/scan_chat`, "POST", {
      expected_type: docType,
      user_answer: combinedAnswers
    });

    if (result.summary && Object.keys(result.summary).length > 0) {
      scanData = result.summary;
      renderScanResult(result.summary);
      document.getElementById("scan-confirm-area").style.display = "block";
      document.getElementById("scan-btn").style.display = "none";
      document.getElementById("scan-confirm-area").scrollIntoView({ behavior: "smooth" });
      toast(`AI successfully extracted ${Object.keys(result.summary).length} fields!`, "success");
      btn.innerHTML = '⚡ Extract Information with AI';
    } else if (result.action === "ask" && result.questions && result.questions.length > 0) {
      pendingQuestions = result.questions;
      gatheredAnswers = [];
      askNextQuestion();
      btn.innerHTML = '⚡ Extract Information with AI';
    } else {
      toast("Extraction failed. Please try again.", "warning");
      btn.innerHTML = '⚡ Extract Information with AI';
    }
  } catch (err) {
    toast(err.message, "error");
    btn.innerHTML = '⚡ Extract Information with AI';
  }
}

function renderScanResult(fields) {
  const container = document.getElementById("scan-fields");
  container.innerHTML = "";
  
  const entries = Object.entries(fields);
  const count = entries.length;
  
  const meta = document.getElementById("extraction-meta");
  if (meta) {
    meta.textContent = `${count} Field${count !== 1 ? 's' : ''} Extracted (Model: openrouter/free)`;
  }

  for (const [key, value] of entries) {
    if (!value || typeof value === "object") continue;
    const card = document.createElement("div");
    card.className = "extracted-card";
    const label = key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    card.innerHTML = `
      <span class="extracted-label">${label}</span>
      <span class="extracted-value">${value}</span>
    `;
    container.appendChild(card);
  }
}

// Confirm extracted and move to fill
function confirmScan() {
  if (scanData) {
    // Fill each field and highlight it
    for (const [key, rawValue] of Object.entries(scanData)) {
      const value = String(rawValue).trim();
      let targetId = `f-${key}`;
      
      // Handle special field name variations
      if (key === "aadhaar_number" || key === "aadhaar") targetId = "f-id_proof_no";
      if (key === "pincode" || key === "pin_code") targetId = "f-pincode";
      if (key === "annual_income" || key === "income") targetId = "f-annual_income";
      
      const el = document.getElementById(targetId);
      if (el) {
        if (el.tagName === "SELECT") {
          // Attempt exact match or lowercase match
          const options = Array.from(el.options);
          const match = options.find(o => o.value.toLowerCase() === value.toLowerCase());
          if (match) {
            el.value = match.value;
          } else {
            el.value = value;
          }
        } else {
          el.value = value;
        }
        el.classList.add("ai-field-highlight");
        setTimeout(() => el.classList.remove("ai-field-highlight"), 2500);
      }
      
      // Auto-calculate age from DOB if age field exists and is empty
      if (key === "dob" && value.includes("/")) {
        const ageEl = document.getElementById("f-age");
        if (ageEl && !ageEl.value) {
          const parts = value.split("/");
          if (parts.length === 3) {
            const birthYear = parseInt(parts[2], 10);
            const currentYear = new Date().getFullYear();
            if (birthYear > 1900 && birthYear <= currentYear) {
              ageEl.value = currentYear - birthYear;
              ageEl.classList.add("ai-field-highlight");
            }
          }
        }
      }
    }
  }
  showPanel(3);
}

// ===================================================================
// STEP 5: FILL — Profile Form + Scheme Discovery
// ===================================================================
async function submitProfile() {
  const btn = document.getElementById("submit-profile-btn");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Finding Schemes...';

  const updates = {};
  const fields = [
    "name",
    "father_name",
    "dob",
    "gender",
    "mobile",
    "address",
    "village",
    "taluka",
    "district",
    "state",
    "residence_area",
    "occupation",
    "employment_sector",
    "caste_category",
    "house_type",
    "applying_for",
    "purpose",
    "residence_period",
    "title",
    "place_of_birth",
    "marital_status",
    "guardian_relation",
    "email",
    "locality",
    "pincode",
    "previous_certificate",
    "immovable_property",
    "property_value",
    "other_income",
    "part_no",
    "serial_no",
    "electoral_year",
    "constituency",
    "ration_card",
    "property_details",
    "id_proof_type",
    "id_proof_no",
    "certify"
  ];
  fields.forEach((f) => {
    const el = document.getElementById(`f-${f}`);
    if (el && el.value) updates[f] = el.value;
  });

  const income = document.getElementById("f-annual_income");
  if (income && income.value) updates.annual_income = parseInt(income.value);
  const famSize = document.getElementById("f-family_size");
  if (famSize && famSize.value) updates.family_size = parseInt(famSize.value);
  const land = document.getElementById("f-land_acres");
  if (land && land.value) updates.land_acres = parseFloat(land.value);
  const age = document.getElementById("f-age");
  if (age && age.value) updates.age = parseInt(age.value);
  const earn = document.getElementById("f-earning_members");
  if (earn && earn.value) updates.earning_members = parseInt(earn.value);
  const childCount = document.getElementById("f-children_count");
  if (childCount && childCount.value) updates.children_count = parseInt(childCount.value);

  [
    "is_bpl",
    "is_student",
    "is_entrepreneur",
    "is_pregnant",
    "is_first_child",
    "has_lpg_connection",
  ].forEach((f) => {
    const el = document.getElementById(`f-${f}`);
    if (el) updates[f] = el.checked;
  });

  try {
    const result = await api(`/sessions/${sessionId}/profile`, "POST", updates);
    schemeResults = result.schemes_found || [];
    renderSchemes(schemeResults);
    toast(result.text || `Found ${schemeResults.length} schemes!`, "success");
    document.getElementById("fill-confirm-area").style.display = "block";
  } catch (e) {
    toast(e.message, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = "🔍 Check Eligibility & Find Schemes";
  }
}

function renderSchemes(schemes) {
  const container = document.getElementById("scheme-results");
  container.innerHTML = "";

  if (schemes.length === 0) {
    container.innerHTML =
      '<p style="text-align:center; color:var(--text-muted); padding:20px;">No additional schemes found with the provided details. You can still proceed.</p>';
    document.getElementById("fill-confirm-area").style.display = "block";
    return;
  }

  const header = document.createElement("div");
  header.className = "schemes-header";
  header.innerHTML = `
    <h3 style="font-size:18px; font-weight:800; color:var(--primary)">🎉 Eligible Schemes</h3>
    <span class="count-badge">${schemes.length} found</span>
  `;
  container.appendChild(header);

  schemes.forEach((s) => {
    const card = document.createElement("div");
    card.className = `scheme-card ${s.verify_manually ? "verify" : ""}`;
    card.innerHTML = `
      ${s.verify_manually ? '<div class="verify-badge">Verify at Office</div>' : ""}
      <div class="scheme-name">${s.scheme_name}</div>
      <div class="scheme-reason">${s.eligibility_reason}</div>
      <div class="scheme-details">
        <div class="scheme-detail">
          <div class="sdl">Benefit</div>
          <div class="sdv">${s.estimated_benefit}</div>
        </div>
        <div class="scheme-detail">
          <div class="sdl">How to Apply</div>
          <div class="sdv">${s.how_to_apply}</div>
        </div>
      </div>
    `;
    container.appendChild(card);
  });
}

// ===================================================================
// STEP 5: DELIVER — Confirm & Generate Documents
// ===================================================================
async function confirmAndDeliver() {
  const btn = document.getElementById("deliver-btn");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Generating Documents...';

  try {
    const result = await api(
      `/sessions/${sessionId}/confirm`,
      "POST"
    );
    deliverData = result;
    renderDeliverPanel(result);
    showPanel(4);
    const msgs = {
      en: "Checklist confirmed. Please scan documents.",
      hi: "चेकलिस्ट पक्की हुई। कृपया दस्तावेज़ स्कैन करें।",
      mr: "चेकलिस्ट निश्चित झाली. कृपया कागदपत्रे स्कॅन करा.",
      gu: "ચેકલિસ્ટ પુષ્ટિ થયેલ છે. કૃપા કરીને દસ્તાવેજો સ્કેન કરો."
    };
    toast(msgs[language] || msgs['hi'], "success");
  } catch (e) {
    toast(e.message, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = "✅ Confirm & Generate Documents";
  }
}

async function renderDeliverPanel(data) {
  const grid = document.getElementById("download-grid");
  grid.innerHTML = "";

  if (data.receipt) {
    // Convert file path to a URL served by the backend
    const filename = data.receipt.replace(/\\/g, "/").split("/").pop();
    const url = `${API}/output/${filename}`;
    const card = document.createElement("a");
    card.className = "download-card";
    card.href = url;
    card.target = "_blank";
    card.innerHTML = `
      <div class="dl-icon">📄</div>
      <div class="dl-label">Application Form</div>
    `;
    grid.appendChild(card);
  }

  if (data.schemes_found && data.schemes_found.length > 0) {
    // The schemes sheet would also be in the output
    const card = document.createElement("div");
    card.className = "download-card";
    card.style.cursor = "default";
    card.innerHTML = `
      <div class="dl-icon">📋</div>
      <div class="dl-label">${data.schemes_found.length} Schemes Listed</div>
    `;
    grid.appendChild(card);
  }

  if (data.qr) {
    const filename = data.qr.replace(/\\/g, "/").split("/").pop();
    const url = `${API}/output/${filename}`;
    document.getElementById("qr-section").style.display = "block";
    document.getElementById("qr-image").src = url;
  }

  if (data.note) {
    document.getElementById("printer-note").textContent = data.note;
    document.getElementById("printer-note").style.display = "block";
  }

  if (data.profile) {
    try {
      // Step 1: Check for missing fields
      const gapResult = await api(`/sessions/${sessionId}/gaps`);
      if (gapResult.missing_fields && gapResult.missing_fields.length > 0) {
        console.log("Gap Analysis - Missing fields:", gapResult.missing_fields);
        const gapNotice = document.createElement("div");
        gapNotice.className = "gap-notice";
        gapNotice.innerHTML = `
          <h4 style="color:var(--warning, #f59e0b); margin-bottom:8px;">⚠️ Missing Fields (${gapResult.missing_fields.length})</h4>
          <p style="font-size:13px; color:var(--text-muted); margin-bottom:8px;">These fields are empty and will be skipped during auto-fill:</p>
          <div style="display:flex; flex-wrap:wrap; gap:6px;">
            ${gapResult.missing_fields.map(f => `<span style="background:rgba(245,158,11,0.15); color:#f59e0b; padding:2px 8px; border-radius:4px; font-size:12px;">${f.replace(/_/g, ' ')}</span>`).join('')}
          </div>
        `;
        grid.parentNode.insertBefore(gapNotice, grid.nextSibling);
      }

      const autofillSec = document.getElementById("autofill-section");
      if (autofillSec) autofillSec.style.display = "block";
    } catch(e) {
      console.error("Gap analysis failed:", e);
      const autofillSec = document.getElementById("autofill-section");
      if (autofillSec) autofillSec.style.display = "block";
    }
  }
}



function openGovPortal() {
  window.open("https://goaonline.gov.in/Appln/UIL/deptServices?__DocId=REV&__ServiceId=REV07", "_blank");
}

function getCurrentFormValues() {
  const values = {};
  const formIds = [
    "applying_for", "purpose", "residence_period", "title", "name",
    "place_of_birth", "dob", "gender", "marital_status", "guardian_relation",
    "father_name", "mobile", "email", "occupation", "caste_category",
    "address", "locality", "district", "taluka", "village", "pincode",
    "family_size", "earning_members", "children_count", "previous_certificate",
    "immovable_property", "property_value", "other_income", "part_no",
    "serial_no", "electoral_year", "constituency", "ration_card",
    "property_details", "id_proof_type", "id_proof_no", "certify"
  ];
  for (const id of formIds) {
    const el = document.getElementById(`f-${id}`);
    if (el) {
      values[id] = el.value;
    }
  }
  return values;
}

// ===================================================================
// Session Management
// ===================================================================
async function endSession() {
  if (sessionId) {
    try {
      await api(`/sessions/${sessionId}`, "DELETE");
    } catch {
      // Silently fail — data wipe is best-effort from the frontend's perspective
    }
  }
  resetUI();
  const msgsEnd = {
    en: "Session ended. All data wiped.",
    hi: "सत्र समाप्त। सारा डेटा हटा दिया गया।",
    mr: "सत्र संपले. सर्व डेटा काढला.",
    gu: "સત્ર સમાપ્ત. બધો ડેટા કાઢી નાખવામાં આવ્યો."
  };
  toast(msgsEnd[language] || msgsEnd['hi'], "info");
}

async function startAnother() {
  if (sessionId) {
    try {
      const result = await api(`/sessions/${sessionId}/another`, "POST");
      showPanel(0);
      // Reset form-related state
      scanData = null;
      schemeResults = [];
      deliverData = null;
      document.getElementById("fill-confirm-area").style.display = "none";
      document.getElementById("scheme-results").innerHTML = "";
      document.getElementById("scan-confirm-area").style.display = "none";
      document.getElementById("scan-fields").innerHTML = "";
      const msgsAnother = {
        en: "Starting another application...",
        hi: "नया आवेदन शुरू कर रहे हैं...",
        mr: "नवीन अर्ज सुरू करत आहोत...",
        gu: "નવી અરજી શરૂ કરી રહ્યા છીએ..."
      };
      toast(msgsAnother[language] || msgsAnother['hi'], "info");
      return;
    } catch {
      // Fall through to full reset
    }
  }
  resetUI();
}

function resetUI() {
  sessionId = null;
  currentStep = 0;
  selectedServiceId = null;
  scanData = null;
  schemeResults = [];
  deliverData = null;
  selectedImages = [];
  
  const previewArea = document.getElementById("image-preview-area");
  if (previewArea) previewArea.style.display = "none";
  const previews = document.getElementById("image-previews");
  if (previews) previews.innerHTML = "";
  
  const uploadInput = document.getElementById("scan-upload");
  if (uploadInput) uploadInput.value = "";
  
  showPanel(0);

  // Reset form
  document
    .querySelectorAll("#fill-form input, #fill-form select")
    .forEach((el) => {
      if (el.type === "checkbox") {
        if (el.id === "f-has_lpg_connection") {
          el.checked = true;
        } else {
          el.checked = false;
        }
      } else {
        el.value = el.defaultValue || "";
      }
    });
  document.getElementById("fill-confirm-area").style.display = "none";
  document.getElementById("scheme-results").innerHTML = "";
  document.getElementById("scan-confirm-area").style.display = "none";
  document.getElementById("scan-fields").innerHTML = "";
  document.getElementById("qr-section").style.display = "none";
  document.getElementById("printer-note").style.display = "none";
  
  const autofillSec = document.getElementById("autofill-section");
  if (autofillSec) autofillSec.style.display = "none";
  const dlGrid = document.getElementById("download-grid");
  if (dlGrid) dlGrid.innerHTML = "";
  const scriptArea = document.getElementById("autofill-script");
  if (scriptArea) scriptArea.value = "";
}

// ===================================================================
// Text-To-Speech (Read Aloud)
// ===================================================================

function toggleReadAloud() {
  if (!window.speechSynthesis) {
    alert("Text-to-Speech is not supported in this browser.");
    return;
  }
  
  if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
    window.speechSynthesis.cancel();
    document.getElementById("btn-read-aloud").innerText = "🔊";
    return;
  }

  // Find the currently active panel
  const activePanel = document.querySelector(".panel.active");
  if (!activePanel) return;

  // Clone it to manipulate text without breaking the actual UI
  const clone = activePanel.cloneNode(true);
  
  // CRITICAL FIX: cloneNode(true) loses user-typed values in <input> fields. 
  // We must manually copy them over into the clone as visible text so the TTS reads them.
  const originalInputs = activePanel.querySelectorAll("input, select, textarea");
  const clonedInputs = clone.querySelectorAll("input, select, textarea");
  originalInputs.forEach((orig, index) => {
    if (clonedInputs[index]) {
      const val = orig.type === "checkbox" ? (orig.checked ? "Checked" : "Unchecked") : orig.value;
      if (val) {
        const textNode = document.createTextNode(`: ${val}. `);
        clonedInputs[index].parentNode.insertBefore(textNode, clonedInputs[index].nextSibling);
      }
    }
  });
  
  // Remove non-readable or hidden elements to avoid reading garbage code
  clone.querySelectorAll("[style*='display: none'], script, style").forEach(e => e.remove());
  
  // Also clean up any buttons so it doesn't read button labels awkwardly if not desired, 
  // but button labels can be useful. We'll leave them.
  
  const textToRead = clone.innerText || clone.textContent;
  if (!textToRead.trim()) return;
  
  const utterance = new SpeechSynthesisUtterance(textToRead);
  
  // Map our UI language variable to Web Speech API lang codes
  let langCode = 'hi-IN'; // Default to Hindi
  if (language === 'en') langCode = 'en-IN';
  if (language === 'mr') langCode = 'mr-IN';
  if (language === 'gu') langCode = 'gu-IN';
  
  utterance.lang = langCode;
  
  // CRITICAL FIX: Explicitly find and set the voice. 
  // If we don't do this, some browsers will try to read Hindi/Marathi text using an American English voice, resulting in gibberish or silence!
  const voices = window.speechSynthesis.getVoices();
  const preferredVoice = voices.find(v => v.lang === langCode || v.lang.replace('_', '-') === langCode);
  if (preferredVoice) {
    utterance.voice = preferredVoice;
  }
  
  utterance.onend = (e) => {
    // Only reset if nothing else is speaking
    if (!window.speechSynthesis.speaking && !window.speechSynthesis.pending) {
      document.getElementById("btn-read-aloud").innerText = "🔊";
    }
  };
  
  utterance.onerror = (e) => {
    if (!window.speechSynthesis.speaking && !window.speechSynthesis.pending) {
      document.getElementById("btn-read-aloud").innerText = "🔊";
    }
  };
  
  window.speechSynthesis.speak(utterance);
  document.getElementById("btn-read-aloud").innerText = "⏹️";
}

// ── Init ──
document.addEventListener("DOMContentLoaded", () => {
  showPanel(0);
  
  // Drag & drop for document scan dropzone
  const dropzone = document.getElementById("scan-dropzone");
  if (dropzone) {
    ["dragenter", "dragover"].forEach(evt => {
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.add("dragover");
      });
    });

    ["dragleave", "drop"].forEach(evt => {
      dropzone.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove("dragover");
      });
    });

    dropzone.addEventListener("drop", (e) => {
      const dt = e.dataTransfer;
      if (dt && dt.files && dt.files.length > 0) {
        handleImageSelect({ target: { files: dt.files } });
      }
    });
  }

  // CRITICAL FIX: Pre-load voices. 
  // Chrome loads voices asynchronously. If we don't trigger this early, 
  // getVoices() returns an empty array on the first click!
  if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = () => {
      window.speechSynthesis.getVoices();
    };
  }
});

async function launchBrowser() {
  if (!sessionId) return;
  const btnLaunch = document.getElementById("btn-launch-browser");
  const btnFill = document.getElementById("btn-trigger-fill");
  const originalText = btnLaunch.innerHTML;
  
  btnLaunch.innerHTML = "Launching Edge...";
  btnLaunch.disabled = true;
  
  try {
    await api(`/sessions/${sessionId}/launch_browser`, "POST");
    btnLaunch.innerHTML = "✓ Browser Launched";
    btnLaunch.classList.remove("btn-primary");
    btnLaunch.classList.add("btn-secondary");
    btnFill.style.display = "block";
  } catch (err) {
    btnLaunch.innerHTML = "Failed to launch";
    setTimeout(() => {
      btnLaunch.innerHTML = originalText;
      btnLaunch.disabled = false;
    }, 3000);
  }
}

// (Duplicate triggerAutoFill removed to fix scoping)


async function startUploadAutomation() {
  if (!sessionId) return;
  try {
    const btn = document.getElementById('upload-btn');
    if (btn) {
      btn.innerHTML = '<span class="spinner"></span> Automating...';
      btn.disabled = true;
    }
    await api(`/sessions/${sessionId}/automate_upload`, 'POST');
    toast('Upload automation started! Please do not touch the mouse.', 'success');
    setTimeout(() => {
      if (btn) {
        btn.innerHTML = '?? Automate Document Uploads';
        btn.disabled = false;
      }
    }, 10000);
  } catch (e) {
    toast('Failed to start upload automation: ' + e.message, 'error');
  }
}


function printDocument(elementId) {
  const element = document.getElementById(elementId);
  if (!element) return;
  const win = window.open('', '', 'height=800,width=800');
  win.document.write('<html><head><title>Print Certificate</title>');
  win.document.write('<style>body{font-family:sans-serif;padding:20px;} img{max-width:100%;}</style>');
  win.document.write('</head><body>');
  win.document.write(element.innerHTML);
  win.document.write('</body></html>');
  win.document.close();
  setTimeout(() => { win.print(); }, 500);
}

// Auto-initialize session directly to Income Certificate
window.addEventListener('DOMContentLoaded', async () => {
  try {
    const session = await api("/sessions", "POST");
    sessionId = session.session_id;
    language = "en";
    await api(`/sessions/${sessionId}/language`, "POST", { language: "en" });
    await api(`/sessions/${sessionId}/state`, "POST", { state: "Goa" });
    selectedServiceId = "CERT_INC";
    const result = await api(`/sessions/${sessionId}/service`, "POST", { service_id: "CERT_INC" });
    renderChecklist(result.summary);
    showPanel(0);
  } catch (e) {
    toast("Failed to initialize session: " + e.message, "error");
  }
});

