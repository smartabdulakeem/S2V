/**
 * S2V frontend — IPC bridge between the PyWebView API and the UI.
 * All calls to Python go through window.pywebview.api.*
 */

// State
let currentScriptPath = null;
let isRendering = false;
let lastOutputPath = null;
const MAX_LOG_LINES = 60;
let logLines = [];

// ── Boot ─────────────────────────────────────────────────────────────────────

window.addEventListener("pywebviewready", () => {
  initApp();
});

// Fallback for slow init
setTimeout(() => {
  if (typeof window.pywebview !== "undefined" && window.pywebview.api) {
    initApp();
  }
}, 500);

async function initApp() {
  window.scrollTo(0, 0);
  try {
    const version = await window.pywebview.api.get_version();
    document.getElementById("version-badge").textContent = `v${version}`;

    const settings = await window.pywebview.api.get_settings();
    if (settings.pixabay_api_key) {
      document.getElementById("pexels-key-input").value = settings.pixabay_api_key;
      setKeyStatus("saved", "✓ Key saved");
    }
    updateRenderButton();
  } catch (e) {
    console.error("Init error:", e);
  }
}

// ── Voice preview ─────────────────────────────────────────────────────────────

let _previewAudio = null;

async function previewVoice() {
  const voice  = document.getElementById('pt-voice').value;
  const btn    = document.getElementById('btn-preview-voice');
  const status = document.getElementById('voice-preview-status');

  // Stop any playing preview
  if (_previewAudio) { _previewAudio.pause(); _previewAudio = null; }

  btn.disabled = true;
  btn.textContent = '⏳ Loading…';
  status.textContent = 'Generating…';

  const result = await window.pywebview.api.preview_voice(voice);

  btn.disabled = false;
  btn.textContent = '▶ Preview';

  if (!result.success) {
    status.textContent = '✗ Error';
    return;
  }

  status.textContent = '▶ Playing…';
  const audio = new Audio('data:audio/mp3;base64,' + result.audio_b64);
  _previewAudio = audio;
  audio.onended = () => { status.textContent = ''; _previewAudio = null; };
  audio.play();
}

// ── Mode switching ────────────────────────────────────────────────────────────

function switchMode(mode) {
  const isText = mode === 'text';
  document.getElementById('mode-text').classList.toggle('hidden', !isText);
  document.getElementById('mode-json').classList.toggle('hidden', isText);
  document.getElementById('tab-text').classList.toggle('active', isText);
  document.getElementById('tab-json').classList.toggle('active', !isText);

  // Reset any loaded script when switching modes
  currentScriptPath = null;
  document.getElementById('script-summary').classList.add('hidden');
  document.getElementById('validation-errors').classList.add('hidden');
  document.getElementById('keywords-wrap').classList.add('hidden');
  updateRenderButton();
}

// ── Plain text parsing ────────────────────────────────────────────────────────

async function parsePlainText() {
  const text     = document.getElementById('pt-script').value.trim();
  const title    = document.getElementById('pt-title').value.trim();
  const filename = document.getElementById('pt-filename').value.trim();
  const voice    = document.getElementById('pt-voice').value;

  const errBlock = document.getElementById('validation-errors');
  const summary  = document.getElementById('script-summary');

  if (!text) {
    errBlock.textContent = 'Please paste your script first.';
    errBlock.classList.remove('hidden');
    summary.classList.add('hidden');
    return;
  }
  if (!title) {
    errBlock.textContent = 'Please enter a video title.';
    errBlock.classList.remove('hidden');
    summary.classList.add('hidden');
    return;
  }
  if (!filename) {
    errBlock.textContent = 'Please enter an output filename (no spaces, e.g. my_video).';
    errBlock.classList.remove('hidden');
    summary.classList.add('hidden');
    return;
  }

  const btn = document.getElementById('btn-parse');
  btn.textContent = 'Parsing…';
  btn.disabled = true;

  // Fire and forget — result comes back via window.onParseComplete()
  await window.pywebview.api.parse_plain_text(text, title, voice, filename);
}

// Called by Python when parse is complete (runs in background thread)
window.onParseComplete = function(result) {
  const btn      = document.getElementById('btn-parse');
  const errBlock = document.getElementById('validation-errors');
  const summary  = document.getElementById('script-summary');

  btn.textContent = 'Parse Script →';
  btn.disabled = false;
  errBlock.classList.add('hidden');

  if (!result.success) {
    errBlock.textContent = 'Error:\n' + result.errors.join('\n');
    errBlock.classList.remove('hidden');
    summary.classList.add('hidden');
    currentScriptPath = null;
    updateRenderButton();
    return;
  }

  // Show summary
  summary.classList.remove('hidden');
  document.getElementById('s-title').textContent    = result.title;
  document.getElementById('s-segments').textContent = result.segment_count + ' scenes';
  document.getElementById('s-duration').textContent = `~${result.estimated_duration}s`;
  document.getElementById('s-voice').textContent    = result.voice;
  document.getElementById('s-output').textContent   = result.output_filename;

  const valEl = document.getElementById('s-validation');
  valEl.textContent = '✅ Ready';
  valEl.className = 'summary-value badge-ok';

  // Show keyword chips
  if (result.keywords && result.keywords.length) {
    const list = document.getElementById('keywords-list');
    list.innerHTML = result.keywords.map(
      k => `<span class="keyword-chip">${k}</span>`
    ).join('');
    document.getElementById('keywords-wrap').classList.remove('hidden');
  }

  currentScriptPath = result.path;
  updateRenderButton();
};

// ── Script loading ────────────────────────────────────────────────────────────

async function loadScript() {
  const path = await window.pywebview.api.open_file_dialog();
  if (!path) return;

  document.getElementById("loaded-path").textContent = path;

  const result = await window.pywebview.api.load_script(path);

  const summary = document.getElementById("script-summary");
  const errBlock = document.getElementById("validation-errors");

  if (!result.success) {
    summary.classList.add("hidden");
    errBlock.textContent = "Validation errors:\n" + result.errors.join("\n");
    errBlock.classList.remove("hidden");
    currentScriptPath = null;
    document.getElementById("s-validation").textContent = "❌ Failed";
    document.getElementById("s-validation").className = "summary-value badge-err";
    updateRenderButton();
    return;
  }

  // Show summary
  errBlock.classList.add("hidden");
  summary.classList.remove("hidden");

  document.getElementById("s-title").textContent    = result.title;
  document.getElementById("s-segments").textContent = result.segment_count + " segments";
  document.getElementById("s-duration").textContent = `~${result.estimated_duration}s`;
  document.getElementById("s-voice").textContent    = result.voice;
  document.getElementById("s-output").textContent   = result.output_filename;

  const valEl = document.getElementById("s-validation");
  valEl.textContent = "✅ Passed";
  valEl.className = "summary-value badge-ok";

  currentScriptPath = result.path;
  updateRenderButton();
}

// ── Pexels key ────────────────────────────────────────────────────────────────

let keyDirty = false;

function onKeyInput() {
  keyDirty = true;
  setKeyStatus("", "");
  updateRenderButton();
}

async function saveKey() {
  const key = document.getElementById("pexels-key-input").value.trim();
  if (!key) {
    setKeyStatus("err", "✗ Key is empty");
    return;
  }
  await window.pywebview.api.save_pixabay_key(key);
  keyDirty = false;
  setKeyStatus("saved", "✓ Saved");
  updateRenderButton();
}

function setKeyStatus(type, msg) {
  const el = document.getElementById("key-status");
  el.textContent = msg;
  el.className = "key-status" + (type === "saved" ? " ok" : type === "err" ? " err" : "");
}

function hasValidKey() {
  const val = document.getElementById("pexels-key-input").value.trim();
  return val.length > 0;
}

// ── Render button state ───────────────────────────────────────────────────────

function updateRenderButton() {
  const btn = document.getElementById("btn-render");
  const hint = document.getElementById("render-hint");

  const ready = currentScriptPath && hasValidKey() && !isRendering;
  btn.disabled = !ready;

  if (!currentScriptPath) {
    hint.textContent = "Load a valid script (.json) to begin.";
  } else if (!hasValidKey()) {
    hint.textContent = "Enter and save your Pexels API key to begin.";
  } else if (isRendering) {
    hint.textContent = "Render in progress…";
  } else {
    hint.textContent = "Ready to render. Click the button above.";
  }
}

// ── Rendering ─────────────────────────────────────────────────────────────────

async function startRender() {
  if (!currentScriptPath || isRendering) return;

  // Save key if dirty
  if (keyDirty) {
    await saveKey();
  }

  isRendering = true;
  lastOutputPath = null;
  logLines = [];

  document.getElementById("btn-render").classList.add("hidden");
  document.getElementById("btn-cancel").classList.remove("hidden");
  document.getElementById("section-progress").classList.remove("hidden");
  document.getElementById("section-complete").classList.add("hidden");
  document.getElementById("log-panel").innerHTML = "";
  document.getElementById("progress-fill").style.width = "0%";
  document.getElementById("stage-label").textContent = "Starting render…";
  document.getElementById("segment-label").textContent = "";

  // Scroll the progress section into view so user can always see it
  setTimeout(() => {
    document.getElementById("section-progress").scrollIntoView({ behavior: "smooth", block: "start" });
  }, 100);

  updateRenderButton();

  const result = await window.pywebview.api.start_render(currentScriptPath);
  if (!result.success) {
    appendLog("ERROR: " + result.error, "error");
    finishRender(false);
  }
}

async function cancelRender() {
  await window.pywebview.api.cancel_render();
  appendLog("Render cancelled.", "error");
  finishRender(false);
}

function finishRender(success) {
  isRendering = false;
  document.getElementById("btn-render").classList.remove("hidden");
  document.getElementById("btn-cancel").classList.add("hidden");
  updateRenderButton();

  if (success) {
    document.getElementById("section-complete").classList.remove("hidden");
    document.getElementById("complete-path").textContent = lastOutputPath || "";
    document.getElementById("section-progress").classList.add("hidden");
  }
}

// ── Pipeline event handler (called from Python via evaluate_js) ──────────────

window.onPipelineEvent = function(event) {
  switch (event.type) {
    case "stage":
      document.getElementById("stage-label").textContent = event.name;
      const pct = Math.round((event.stage_num / event.total_stages) * 100);
      document.getElementById("progress-fill").style.width = pct + "%";
      break;

    case "progress":
      document.getElementById("segment-label").textContent =
        `Segment ${event.segment} of ${event.total_segments}`;
      appendLog(event.message);
      break;

    case "log":
      appendLog(event.message);
      break;

    case "error":
      appendLog("ERROR: " + event.message, "error");
      finishRender(false);
      break;

    case "complete":
      lastOutputPath = event.output_path;
      appendLog("✅ Render complete: " + event.output_path, "ok");
      document.getElementById("progress-fill").style.width = "100%";
      document.getElementById("stage-label").textContent = "Complete ✅";
      finishRender(true);
      break;
  }
};

function appendLog(msg, cls) {
  logLines.push({ msg, cls });
  if (logLines.length > MAX_LOG_LINES) logLines.shift();

  const panel = document.getElementById("log-panel");
  const line = document.createElement("span");
  line.className = "log-line" + (cls ? " " + cls : "");
  line.textContent = msg;
  panel.appendChild(line);
  panel.appendChild(document.createElement("br"));

  // Auto-scroll to bottom
  panel.scrollTop = panel.scrollHeight;
}

// ── Post-render actions ───────────────────────────────────────────────────────

async function openOutputFolder() {
  await window.pywebview.api.open_output_folder(lastOutputPath);
}

function renderAnother() {
  document.getElementById("section-complete").classList.add("hidden");
  document.getElementById("section-progress").classList.add("hidden");
  currentScriptPath = null;
  lastOutputPath = null;
  document.getElementById("loaded-path").textContent = "No file loaded";
  document.getElementById("script-summary").classList.add("hidden");
  document.getElementById("validation-errors").classList.add("hidden");
  document.getElementById("keywords-wrap").classList.add("hidden");
  // Clear plain text fields
  document.getElementById("pt-script").value = "";
  document.getElementById("pt-title").value = "";
  document.getElementById("pt-filename").value = "";
  updateRenderButton();
}
