/**
 * S2V frontend — IPC bridge between the PyWebView API and the UI.
 * Supports running inside local desktop PyWebView and standard web browsers (cloud-mode Vercel).
 */

// Detect running mode
const isWebMode = typeof window.pywebview === "undefined" || !window.pywebview.api;

// State
let currentScriptPath = null;
let currentScriptData = null;
let isRendering = false;
let lastOutputPath = null;
const MAX_LOG_LINES = 100;
let logLines = [];

// ── Boot ─────────────────────────────────────────────────────────────────────

window.addEventListener("pywebviewready", () => {
  initApp();
});

// Boot fallback/webmode init
window.addEventListener("DOMContentLoaded", () => {
  if (isWebMode) {
    initApp();
  }
});

// Fallback for slower init
setTimeout(() => {
  if (!isWebMode && window.pywebview && window.pywebview.api) {
    initApp();
  }
}, 500);

async function initApp() {
  window.scrollTo(0, 0);
  
  if (isWebMode) {
    console.log("S2V running in Cloud Web Mode");
    document.getElementById("version-badge").textContent = `v2.0.0 (Cloud)`;
    
    // Load credentials from browser localStorage
    const pexelsKey = localStorage.getItem("pixabay_api_key") || "";
    const hfKey = localStorage.getItem("huggingface_api_key") || "";
    
    if (pexelsKey) {
      document.getElementById("pexels-key-input").value = pexelsKey;
      setKeyStatus("saved", "✓ Pixabay saved");
    }
    if (hfKey) {
      document.getElementById("huggingface-key-input").value = hfKey;
      setHFKeyStatus("saved", "✓ Token saved");
    }
    updateRenderButton();
    return;
  }

  // Native PyWebView desktop mode
  try {
    const version = await window.pywebview.api.get_version();
    document.getElementById("version-badge").textContent = `v${version}`;

    const settings = await window.pywebview.api.get_settings();
    if (settings.pixabay_api_key) {
      document.getElementById("pexels-key-input").value = settings.pixabay_api_key;
      setKeyStatus("saved", "✓ Pixabay saved");
    }
    if (settings.huggingface_api_key) {
      document.getElementById("huggingface-key-input").value = settings.huggingface_api_key;
      setHFKeyStatus("saved", "✓ Token saved");
    }
    updateRenderButton();
  } catch (e) {
    console.error("Init desktop app failed:", e);
  }
}

// ── Voice preview ─────────────────────────────────────────────────────────────

let _previewAudio = null;

async function previewVoice() {
  const voice = document.getElementById('pt-voice').value;
  const btn = document.getElementById('btn-preview-voice');
  const status = document.getElementById('voice-preview-status');

  if (_previewAudio) {
    _previewAudio.pause();
    _previewAudio = null;
  }

  btn.disabled = true;
  btn.textContent = '⏳ Loading…';
  status.textContent = 'Generating preview…';

  let result;
  
  if (isWebMode) {
    try {
      const hfKey = localStorage.getItem("huggingface_api_key") || "";
      const resp = await fetch("/api/preview_voice", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice_id: voice, hf_token: hfKey })
      });
      result = await resp.json();
    } catch (err) {
      result = { success: false, error: err.message };
    }
  } else {
    result = await window.pywebview.api.preview_voice(voice);
  }

  btn.disabled = false;
  btn.textContent = '▶ Preview';

  if (!result.success) {
    status.textContent = '✗ Error: ' + (result.error || 'Failed');
    return;
  }

  status.textContent = '▶ Playing…';
  const audio = new Audio('data:audio/mp3;base64,' + result.audio_b64);
  _previewAudio = audio;
  audio.onended = () => {
    status.textContent = '';
    _previewAudio = null;
  };
  audio.play().catch(err => {
    status.textContent = '✗ Play blocked';
    console.error("Audio play failed:", err);
  });
}

// ── Mode switching ────────────────────────────────────────────────────────────

function switchMode(mode) {
  const isText = mode === 'text';
  document.getElementById('mode-text').classList.toggle('hidden', !isText);
  document.getElementById('mode-json').classList.toggle('hidden', isText);
  document.getElementById('tab-text').classList.toggle('active', isText);
  document.getElementById('tab-json').classList.toggle('active', !isText);

  currentScriptPath = null;
  currentScriptData = null;
  document.getElementById('script-summary').classList.add('hidden');
  document.getElementById('section-storyboard').classList.add('hidden');
  document.getElementById('validation-errors').classList.add('hidden');
  updateRenderButton();
}

// ── Plain text parsing ────────────────────────────────────────────────────────

async function parsePlainText() {
  const text = document.getElementById('pt-script').value.trim();
  const title = document.getElementById('pt-title').value.trim();
  const filename = document.getElementById('pt-filename').value.trim();
  const voice = document.getElementById('pt-voice').value;
  const visualStyle = document.getElementById('pt-visual-style').value.trim();
  const aspectRatio = document.getElementById('pt-aspect-ratio').value;

  const errBlock = document.getElementById('validation-errors');
  const summary = document.getElementById('script-summary');
  const storyboard = document.getElementById('section-storyboard');

  if (!text) {
    showError('Please paste your script narration first.');
    return;
  }
  if (!title) {
    showError('Please enter a video title.');
    return;
  }
  if (!filename) {
    showError('Please enter an output filename (no spaces, e.g. Baghdad_Golden_Age).');
    return;
  }

  const btn = document.getElementById('btn-parse');
  btn.textContent = '🧠 AI Agent Planning storyboard…';
  btn.disabled = true;
  errBlock.classList.add('hidden');
  storyboard.classList.add('hidden');

  if (isWebMode) {
    try {
      const hfKey = localStorage.getItem("huggingface_api_key") || "";
      const resp = await fetch("/api/parse_plain_text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: text,
          title: title,
          voice: voice,
          filename: filename,
          visual_style: visualStyle,
          aspect_ratio: aspectRatio,
          hf_token: hfKey
        })
      });
      const result = await resp.json();
      window.onParseComplete(result);
    } catch (err) {
      window.onParseComplete({ success: false, errors: [err.message] });
    }
  } else {
    await window.pywebview.api.parse_plain_text(text, title, voice, filename, visualStyle, aspectRatio);
  }
}

function showError(msg) {
  const errBlock = document.getElementById('validation-errors');
  errBlock.textContent = msg;
  errBlock.classList.remove('hidden');
  document.getElementById('script-summary').classList.add('hidden');
  document.getElementById('section-storyboard').classList.add('hidden');
  errBlock.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Called when parsing is completed
window.onParseComplete = function(result) {
  const btn = document.getElementById('btn-parse');
  const errBlock = document.getElementById('validation-errors');
  const summary = document.getElementById('script-summary');
  const storyboard = document.getElementById('section-storyboard');

  btn.textContent = 'Generate Storyboard Plan →';
  btn.disabled = false;
  errBlock.classList.add('hidden');

  if (!result.success) {
    showError('AI Storyboard Planner Error:\n' + result.errors.join('\n'));
    currentScriptPath = null;
    currentScriptData = null;
    updateRenderButton();
    return;
  }

  currentScriptPath = result.path;
  currentScriptData = result.script_data;

  // Show summary card
  summary.classList.remove('hidden');
  document.getElementById('s-title').textContent = result.title;
  document.getElementById('s-segments').textContent = result.segment_count + ' scenes';
  document.getElementById('s-duration').textContent = `~${result.estimated_duration}s`;
  document.getElementById('s-voice').textContent = result.voice;
  document.getElementById('s-aspect-ratio').textContent = result.aspect_ratio;
  
  const valEl = document.getElementById('s-validation');
  valEl.textContent = isWebMode ? '✅ Planned (Cloud)' : '✅ Planned';
  valEl.className = 'summary-value badge-ok';

  // Display and populate Storyboard review panel
  storyboard.classList.remove('hidden');
  document.getElementById('sb-est-duration').textContent = `~${result.estimated_duration} seconds`;
  
  const renderSecs = result.estimated_render_time;
  if (renderSecs > 60) {
    const mins = Math.floor(renderSecs / 60);
    const secs = renderSecs % 60;
    document.getElementById('sb-est-render').textContent = `~${mins}m ${secs}s (approx)`;
  } else {
    document.getElementById('sb-est-render').textContent = `~${renderSecs}s (approx)`;
  }

  document.getElementById('sb-style-guide').textContent = currentScriptData.project.visual_style || "cinematic";
  document.getElementById('sb-status').textContent = result.fallback ? "⚠️ Planned (Rule Fallback)" : "🤖 AI Structured";
  document.getElementById('sb-status').className = result.fallback ? "badge-err" : "badge-ok";

  // Build the list of scene editors
  drawStoryboard(currentScriptData);

  updateRenderButton();

  setTimeout(() => {
    storyboard.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 100);
};

// ── Render Storyboard Review Cards ────────────────────────────────────────────

function drawStoryboard(scriptData) {
  const container = document.getElementById("storyboard-scenes-container");
  container.innerHTML = "";

  scriptData.segments.forEach((seg, idx) => {
    const card = document.createElement("div");
    card.className = "scene-card card-fade-in";
    card.style.animationDelay = `${idx * 0.05}s`;

    const badgeClass = seg.type === "hook" ? "hook" : seg.type === "conclusion" ? "conclusion" : "body";
    const kbOptions = ["zoom_in", "zoom_out", "pan_left", "pan_right", "none"]
      .map(opt => `<option value="${opt}" ${seg.ken_burns === opt ? 'selected' : ''}>${opt.replace('_', ' ')}</option>`)
      .join('');

    const overlayText = seg.text_overlay ? seg.text_overlay.text : "";

    card.innerHTML = `
      <div class="scene-header">
        <span class="scene-num">Scene ${seg.segment_id}</span>
        <span class="scene-badge ${badgeClass}">${seg.type}</span>
      </div>
      <div class="scene-grid-cols">
        <div class="scene-field">
          <label>Scene Voice Narration (verbatim)</label>
          <textarea class="scene-textarea scene-input-narration" data-index="${idx}" placeholder="Enter scene text...">${seg.narration}</textarea>
        </div>
        <div class="scene-field">
          <label>AI Visual Generation Prompt</label>
          <textarea class="scene-textarea scene-input-keyword" data-index="${idx}" placeholder="Describe the scene imagery...">${seg.b_roll_keyword}</textarea>
          
          <div class="scene-row-3" style="margin-top: 8px;">
            <div class="scene-field">
              <label>Ken Burns Motion</label>
              <select class="scene-input scene-input-kb" data-index="${idx}">
                ${kbOptions}
              </select>
            </div>
            <div class="scene-field">
              <label>Text Overlay</label>
              <input type="text" class="scene-input scene-input-overlay" data-index="${idx}" value="${overlayText}" placeholder="Optional subtitle / keyword" />
            </div>
          </div>
        </div>
      </div>
    `;
    container.appendChild(card);
  });
}

// ── Save Storyboard edits ─────────────────────────────────────────────────────

async function saveStoryboardEdits(showNotification = false) {
  if (!currentScriptData || !currentScriptPath) return false;

  const narrations = document.querySelectorAll(".scene-input-narration");
  const keywords = document.querySelectorAll(".scene-input-keyword");
  const motions = document.querySelectorAll(".scene-input-kb");
  const overlays = document.querySelectorAll(".scene-input-overlay");

  narrations.forEach((el) => {
    const idx = parseInt(el.getAttribute("data-index"));
    currentScriptData.segments[idx].narration = el.value.trim();
  });

  keywords.forEach((el) => {
    const idx = parseInt(el.getAttribute("data-index"));
    currentScriptData.segments[idx].b_roll_keyword = el.value.trim();
  });

  motions.forEach((el) => {
    const idx = parseInt(el.getAttribute("data-index"));
    currentScriptData.segments[idx].ken_burns = el.value;
  });

  overlays.forEach((el) => {
    const idx = parseInt(el.getAttribute("data-index"));
    const val = el.value.trim();
    if (val) {
      const segDuration = Math.max(3, Math.round(currentScriptData.segments[idx].narration.length / 15));
      currentScriptData.segments[idx].text_overlay = {
        "text": val,
        "position": "bottom_center",
        "duration_seconds": segDuration
      };
    } else {
      currentScriptData.segments[idx].text_overlay = null;
    }
  });

  let res;
  if (isWebMode) {
    try {
      const resp = await fetch("/api/save_edited_script", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: currentScriptPath, script_data: currentScriptData })
      });
      res = await resp.json();
    } catch (err) {
      res = { success: false, error: err.message };
    }
  } else {
    res = await window.pywebview.api.save_edited_script(currentScriptPath, currentScriptData);
  }

  if (res.success) {
    if (showNotification) {
      alert("✓ Storyboard changes saved successfully.");
    }
    return true;
  } else {
    alert("✗ Failed to save storyboard changes: " + res.error);
    return false;
  }
}

// ── JSON file loading ─────────────────────────────────────────────────────────

async function loadScript() {
  if (isWebMode) {
    // browser file input handler
    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = ".json";
    fileInput.onchange = e => {
      const file = e.target.files[0];
      if (!file) return;
      document.getElementById("loaded-path").textContent = file.name;
      
      const reader = new FileReader();
      reader.onload = async event => {
        try {
          const data = JSON.parse(event.target.result);
          
          if (!data.project || !data.segments) {
            showError("Invalid JSON structure: Missing project or segments block.");
            return;
          }
          
          currentScriptPath = "cloud_loaded_script";
          currentScriptData = data;
          
          const summary = document.getElementById("script-summary");
          const errBlock = document.getElementById("validation-errors");
          const storyboard = document.getElementById("section-storyboard");

          errBlock.classList.add("hidden");
          summary.classList.remove("hidden");

          document.getElementById("s-title").textContent = data.project.title || "Untitled";
          document.getElementById("s-segments").textContent = data.segments.length + " segments";
          document.getElementById("s-duration").textContent = `~${Math.round(data.segments.length * 4)}s`;
          document.getElementById("s-voice").textContent = data.project.voice || "";
          document.getElementById("s-aspect-ratio").textContent = data.project.aspect_ratio || "16:9";

          const valEl = document.getElementById("s-validation");
          valEl.textContent = "✅ Loaded (Cloud)";
          valEl.className = "summary-value badge-ok";

          storyboard.classList.remove('hidden');
          document.getElementById('sb-est-duration').textContent = `~${Math.round(data.segments.length * 4)} seconds`;
          document.getElementById('sb-est-render').textContent = `Local Only`;
          document.getElementById('sb-style-guide').textContent = data.project.visual_style || "cinematic";
          document.getElementById('sb-status').textContent = "Loaded JSON";
          document.getElementById('sb-status').className = "badge-ok";

          drawStoryboard(data);
          updateRenderButton();
        } catch (err) {
          showError("Failed to parse JSON file: " + err.message);
        }
      };
      reader.readAsText(file);
    };
    fileInput.click();
    return;
  }

  // Desktop Native filePicker
  const path = await window.pywebview.api.open_file_dialog();
  if (!path) return;

  document.getElementById("loaded-path").textContent = path;

  const result = await window.pywebview.api.load_script(path);
  const summary = document.getElementById("script-summary");
  const errBlock = document.getElementById("validation-errors");
  const storyboard = document.getElementById("section-storyboard");

  if (!result.success) {
    summary.classList.add("hidden");
    storyboard.classList.add("hidden");
    errBlock.textContent = "Validation errors:\n" + result.errors.join("\n");
    errBlock.classList.remove("hidden");
    currentScriptPath = null;
    currentScriptData = null;
    document.getElementById("s-validation").textContent = "❌ Failed";
    document.getElementById("s-validation").className = "summary-value badge-err";
    updateRenderButton();
    return;
  }

  errBlock.classList.add("hidden");
  summary.classList.remove("hidden");

  currentScriptPath = result.path;
  currentScriptData = result.script_data;

  document.getElementById("s-title").textContent = result.title;
  document.getElementById("s-segments").textContent = result.segment_count + " segments";
  document.getElementById("s-duration").textContent = `~${result.estimated_duration}s`;
  document.getElementById("s-voice").textContent = result.voice;
  document.getElementById("s-aspect-ratio").textContent = result.aspect_ratio || "16:9";

  const valEl = document.getElementById("s-validation");
  valEl.textContent = "✅ Loaded";
  valEl.className = "summary-value badge-ok";

  storyboard.classList.remove('hidden');
  document.getElementById('sb-est-duration').textContent = `~${result.estimated_duration} seconds`;
  document.getElementById('sb-est-render').textContent = `Calculating...`;
  document.getElementById('sb-style-guide').textContent = currentScriptData.project.visual_style || "cinematic";
  document.getElementById('sb-status').textContent = "Loaded from file";
  document.getElementById('sb-status').className = "badge-ok";

  drawStoryboard(currentScriptData);
  updateRenderButton();
}

// ── Hugging Face Credentials ──────────────────────────────────────────────────

let hfKeyDirty = false;

function onHuggingFaceKeyInput() {
  hfKeyDirty = true;
  setHFKeyStatus("", "");
}

async function saveHuggingFaceKey() {
  const key = document.getElementById("huggingface-key-input").value.trim();
  if (!key) {
    setHFKeyStatus("err", "✗ Token is empty");
    return;
  }
  
  if (isWebMode) {
    localStorage.setItem("huggingface_api_key", key);
    hfKeyDirty = false;
    setHFKeyStatus("saved", "✓ Saved (Local)");
  } else {
    await window.pywebview.api.save_huggingface_key(key);
    hfKeyDirty = false;
    setHFKeyStatus("saved", "✓ Saved");
  }
}

function setHFKeyStatus(type, msg) {
  const el = document.getElementById("hf-key-status");
  el.textContent = msg;
  el.className = "key-status" + (type === "saved" ? " ok" : type === "err" ? " err" : "");
}

// ── Pixabay key ───────────────────────────────────────────────────────────────

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
  
  if (isWebMode) {
    localStorage.setItem("pixabay_api_key", key);
    keyDirty = false;
    setKeyStatus("saved", "✓ Saved (Local)");
    updateRenderButton();
  } else {
    await window.pywebview.api.save_pixabay_key(key);
    keyDirty = false;
    setKeyStatus("saved", "✓ Saved");
    updateRenderButton();
  }
}

function setKeyStatus(type, msg) {
  const el = document.getElementById("key-status");
  el.textContent = msg;
  el.className = "key-status" + (type === "saved" ? " ok" : type === "err" ? " err" : "");
}

// ── Render button state ───────────────────────────────────────────────────────

function updateRenderButton() {
  const btn = document.getElementById("btn-render");
  const hint = document.getElementById("render-hint");

  const ready = currentScriptPath && !isRendering;
  btn.disabled = !ready;

  if (!currentScriptPath) {
    hint.textContent = "Plan a script or load a JSON file to render.";
  } else if (isRendering) {
    hint.textContent = "Rendering in progress…";
  } else {
    hint.textContent = isWebMode 
      ? "Planned script ready. (Review storyboard above. Rendering requires running app locally)."
      : "Ready to start video creation. Review storyboard above first.";
  }
}

// ── Approve and Render ────────────────────────────────────────────────────────

async function approveAndRender() {
  const saved = await saveStoryboardEdits(false);
  if (saved) {
    startRender();
  }
}

// ── Rendering ─────────────────────────────────────────────────────────────────

async function startRender() {
  if (!currentScriptPath || isRendering) return;

  if (keyDirty) await saveKey();
  if (hfKeyDirty) await saveHuggingFaceKey();

  isRendering = true;
  lastOutputPath = null;
  logLines = [];

  document.getElementById("btn-render").classList.add("hidden");
  document.getElementById("btn-cancel").classList.remove("hidden");
  document.getElementById("btn-approve-render").disabled = true;
  document.getElementById("btn-approve-render").textContent = "⚡ Rendering…";
  
  document.getElementById("section-progress").classList.remove("hidden");
  document.getElementById("section-complete").classList.add("hidden");
  
  document.getElementById("log-panel").innerHTML = "";
  document.getElementById("progress-fill").style.width = "0%";
  document.getElementById("stage-label").textContent = "Starting render…";
  document.getElementById("segment-label").textContent = "";

  setTimeout(() => {
    document.getElementById("section-progress").scrollIntoView({ behavior: "smooth", block: "start" });
  }, 100);

  updateRenderButton();

  let result;
  
  if (isWebMode) {
    try {
      const resp = await fetch("/api/start_render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ script_path: currentScriptPath })
      });
      result = await resp.json();
    } catch (err) {
      result = { success: false, error: err.message };
    }
  } else {
    result = await window.pywebview.api.start_render(currentScriptPath);
  }
  
  if (!result.success) {
    appendLog("ERROR: " + result.error, "error");
    finishRender(false);
  }
}

async function cancelRender() {
  if (!isWebMode) {
    await window.pywebview.api.cancel_render();
  }
  appendLog("Render cancelled.", "error");
  finishRender(false);
}

function finishRender(success) {
  isRendering = false;
  document.getElementById("btn-render").classList.remove("hidden");
  document.getElementById("btn-cancel").classList.add("hidden");
  
  const btnApprove = document.getElementById("btn-approve-render");
  btnApprove.disabled = false;
  btnApprove.textContent = "▶ Approve & Start Render";
  
  updateRenderButton();

  if (success) {
    document.getElementById("section-complete").classList.remove("hidden");
    document.getElementById("complete-path").textContent = lastOutputPath || "";
    document.getElementById("section-progress").classList.add("hidden");
    document.getElementById("section-storyboard").classList.add("hidden");
    
    setTimeout(() => {
      document.getElementById("section-complete").scrollIntoView({ behavior: "smooth", block: "start" });
    }, 100);
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

  panel.scrollTop = panel.scrollHeight;
}

// ── Post-render actions ───────────────────────────────────────────────────────

async function openOutputFolder() {
  if (isWebMode) {
    alert("Output folders are on your local computer. Run S2V locally to view outputs.");
    return;
  }
  await window.pywebview.api.open_output_folder(lastOutputPath);
}

function renderAnother() {
  document.getElementById("section-complete").classList.add("hidden");
  document.getElementById("section-progress").classList.add("hidden");
  document.getElementById("section-storyboard").classList.add("hidden");
  currentScriptPath = null;
  currentScriptData = null;
  lastOutputPath = null;
  document.getElementById("loaded-path").textContent = "No file loaded";
  document.getElementById("script-summary").classList.add("hidden");
  document.getElementById("validation-errors").classList.add("hidden");
  document.getElementById("pt-script").value = "";
  document.getElementById("pt-title").value = "";
  document.getElementById("pt-filename").value = "";
  document.getElementById("pt-visual-style").value = "";
  updateRenderButton();
}
