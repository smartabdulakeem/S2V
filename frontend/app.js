/**
 * S2V frontend — IPC bridge between the PyWebView API and the UI.
 * Supports running inside local desktop PyWebView and standard web browsers (cloud-mode Vercel).
 */

// Detect running mode (re-evaluated dynamically in initApp)
let isWebMode = typeof window.pywebview === "undefined" || !window.pywebview.api;

// State
let currentScriptPath = null;
let currentScriptData = null;
let isRendering = false;
let lastOutputPath = null;
const MAX_LOG_LINES = 100;
let logLines = [];

window.decodeBase64UTF8 = function(payload) {
    const binary = atob(payload);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    return new TextDecoder("utf-8").decode(bytes);
};

const ALL_DIALECTS = [
    { code: 'Standard English', label: 'Standard English', flag: '🇺🇸' },
    { code: 'Nigerian English', label: 'Nigerian English', flag: '🇳🇬' },
    { code: 'British English', label: 'British English (UK)', flag: '🇬🇧' },
    { code: 'Arabic Storytelling', label: 'Arabic Storytelling', flag: '🇸🇦' },
    { code: 'Spanish Dialect', label: 'Spanish Dialect', flag: '🇪🇸' },
    { code: 'French Dialect', label: 'French Dialect', flag: '🇫🇷' }
];
let enabledLanguages = ['Standard English', 'Nigerian English', 'British English', 'Arabic Storytelling', 'Spanish Dialect', 'French Dialect'];

window.renderLanguageCheckboxes = function() {
    const container = document.getElementById("language-selection-list");
    if (!container) return;
    container.innerHTML = "";
    
    ALL_DIALECTS.forEach((dialect) => {
        const isChecked = enabledLanguages.includes(dialect.code);
        const wrapper = document.createElement("label");
        wrapper.className = "flex items-center gap-2 cursor-pointer p-1.5 rounded hover:bg-white/5 text-[#dfe2f1]";
        wrapper.innerHTML = `
            <input type="checkbox" value="${dialect.code}" ${isChecked ? 'checked' : ''} onchange="toggleLanguagePreference(this)" class="rounded border-white/10 bg-[#171b26] text-[#8083ff] focus:ring-0 focus:ring-offset-0" />
            <span>${dialect.flag} ${dialect.label}</span>
        `;
        container.appendChild(wrapper);
    });
};

window.toggleLanguagePreference = function(checkbox) {
    const lang = checkbox.value;
    if (checkbox.checked) {
        if (!enabledLanguages.includes(lang)) {
            enabledLanguages.push(lang);
        }
    } else {
        enabledLanguages = enabledLanguages.filter(l => l !== lang);
    }
    localStorage.setItem("enabled_languages", JSON.stringify(enabledLanguages));
    rebuildDialectSelect();
};

window.rebuildDialectSelect = function() {
    const dialectSelect = document.getElementById("pt-voice-dialect");
    if (!dialectSelect) return;
    
    const currentVal = dialectSelect.value;
    dialectSelect.innerHTML = "";
    
    const filtered = ALL_DIALECTS.filter(d => enabledLanguages.includes(d.code));
    filtered.forEach((dialect) => {
        const opt = document.createElement("option");
        opt.value = dialect.code;
        opt.textContent = dialect.label;
        dialectSelect.appendChild(opt);
    });
    
    if (filtered.some(d => d.code === currentVal)) {
        dialectSelect.value = currentVal;
    } else if (filtered.length > 0) {
        dialectSelect.value = filtered[0].code;
    }

    rebuildVoiceSelect();
};

window.rebuildVoiceSelect = function() {
    const voiceSelect = document.getElementById("pt-voice");
    if (!voiceSelect) return;

    const currentVoice = voiceSelect.value;
    let selectedStillValid = false;

    const options = voiceSelect.querySelectorAll("option");
    options.forEach(opt => {
        const val = opt.value;
        let dialect = "";
        if (val.startsWith("edge:en-US-") || val.startsWith("google:gemini-3.1-flash-tts-preview:") || val.startsWith("google:en-US-")) {
            dialect = "Standard English";
        } else if (val.startsWith("edge:en-GB-") || val.startsWith("edge:en-AU-") || val.startsWith("google:en-GB-")) {
            dialect = "British English";
        } else if (val === "local:supertonic-f3") {
            dialect = "Arabic Storytelling";
        } else if (val.startsWith("local:supertonic-")) {
            dialect = "Nigerian English";
        } else if (val.startsWith("edge:es-") || val.startsWith("google:es-")) {
            dialect = "Spanish Dialect";
        } else if (val.startsWith("edge:fr-") || val.startsWith("google:fr-")) {
            dialect = "French Dialect";
        }

        if (dialect) {
            const isEnabled = enabledLanguages.includes(dialect);
            if (isEnabled) {
                opt.style.display = "";
                opt.disabled = false;
                if (val === currentVoice) selectedStillValid = true;
            } else {
                opt.style.display = "none";
                opt.disabled = true;
            }
        } else {
            opt.style.display = "";
            opt.disabled = false;
            if (val === currentVoice) selectedStillValid = true;
        }
    });

    const optgroups = voiceSelect.querySelectorAll("optgroup");
    optgroups.forEach(group => {
        const totalOpts = group.querySelectorAll("option").length;
        const hiddenOpts = group.querySelectorAll("option[disabled]").length;
        if (totalOpts === hiddenOpts) {
            group.style.display = "none";
        } else {
            group.style.display = "";
        }
    });

    if (!selectedStillValid) {
        const firstEnabled = voiceSelect.querySelector("option:not([disabled])");
        if (firstEnabled) {
            voiceSelect.value = firstEnabled.value;
        }
    }
};

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

// Fallback for slower init or early-injection race conditions
setTimeout(() => {
  const actuallyDesktop = typeof window.pywebview !== "undefined" && window.pywebview.api;
  if (actuallyDesktop) {
    initApp();
  }
}, 500);

async function initApp() {
  window.scrollTo(0, 0);
  
  const savedLangs = localStorage.getItem("enabled_languages");
  if (savedLangs) {
      enabledLanguages = JSON.parse(savedLangs);
  }
  renderLanguageCheckboxes();
  rebuildDialectSelect();
  
  // Update mode based on presence of injected pywebview API
  isWebMode = typeof window.pywebview === "undefined" || !window.pywebview.api;
  
  if (isWebMode) {
    console.log("S2V running in Cloud Web Mode");
    document.getElementById("version-badge").textContent = `v2.0.0 (Cloud)`;
    
    // Load credentials from browser localStorage
    const googleKey = localStorage.getItem("google_api_key") || "";
    if (googleKey) {
      document.getElementById("google-key-input").value = googleKey;
      setGoogleKeyStatus("saved", "✓ Key saved");
    }
    const googleTtsKey = localStorage.getItem("google_tts_api_key") || "";
    if (googleTtsKey) {
      document.getElementById("google-tts-key-input").value = googleTtsKey;
      setGoogleTtsKeyStatus("saved", "✓ Key saved");
    }
    const deepseekKey = localStorage.getItem("deepseek_api_key") || "";
    if (deepseekKey) {
      document.getElementById("deepseek-key-input").value = deepseekKey;
      setDeepseekKeyStatus("saved", "✓ Key saved");
    }
    updateRenderButton();
    return;
  }

  // Native PyWebView desktop mode
  try {
    const version = await window.pywebview.api.get_version();
    document.getElementById("version-badge").textContent = `v${version}`;

    const settings = await window.pywebview.api.get_settings();
    if (settings.google_api_key) {
      document.getElementById("google-key-input").value = settings.google_api_key;
      setGoogleKeyStatus("saved", "✓ Key saved");
    }
    if (settings.google_tts_api_key) {
      document.getElementById("google-tts-key-input").value = settings.google_tts_api_key;
      setGoogleTtsKeyStatus("saved", "✓ Key saved");
    }
    if (settings.deepseek_api_key) {
      document.getElementById("deepseek-key-input").value = settings.deepseek_api_key;
      setDeepseekKeyStatus("saved", "✓ Key saved");
    }
    updateRenderButton();
  } catch (e) {
    console.error("Init desktop app failed:", e);
  }
}

window.toggleSettingsModal = function() {
    const modal = document.getElementById('settings-modal');
    if (modal) {
        modal.classList.toggle('hidden');
    }
};

// ── Voice preview ─────────────────────────────────────────────────────────────

let _previewAudio = null;

async function previewVoice() {
  const voice = document.getElementById('pt-voice').value;
  const btn = document.getElementById('btn-preview-voice');
  const status = document.getElementById('voice-preview-status');

  if (_previewAudio) {
    try {
      _previewAudio.pause();
    } catch(e) {}
    _previewAudio = null;
  }

  // 1. Unlocked Audio Element Trick: Create the element synchronously inside the click handler
  // and load a tiny silent WAV placeholder. Play it to establish user-interaction context.
  const audio = new Audio("data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAAA");
  _previewAudio = audio;
  try {
    await audio.play();
  } catch (playErr) {
    console.warn("Muted autoplay unlock failed, continuing...", playErr);
  }

  btn.disabled = true;
  btn.textContent = '⏳ Loading…';
  status.textContent = 'Generating preview…';

  let result;
  
  if (isWebMode) {
    try {
      const resp = await fetch("/api/preview_voice", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice_id: voice })
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
    _previewAudio = null;
    return;
  }

  // 2. Swapping source to base64 audio and trigger playback. 
  // The browser allows this because the audio element was unlocked during the initial click event.
  status.textContent = '▶ Playing…';
  audio.src = 'data:audio/mp3;base64,' + result.audio_b64;
  audio.onended = () => {
    status.textContent = '';
    _previewAudio = null;
  };
  
  audio.play().catch(err => {
    status.textContent = '✗ Play blocked';
    console.error("Audio playback failed:", err);
  });
}

// ── Mode switching ────────────────────────────────────────────────────────────

window.switchTab = function(tabIdx) {
  const coreTab = document.getElementById("coreTab");
  const aiTab = document.getElementById("aiTab");
  const tab0 = document.getElementById("tab0");
  const tab1 = document.getElementById("tab1");
  const pill = document.getElementById("tabPill");
  const tabBar = document.getElementById("tabBar");

  if (tabIdx === 0) {
    if (coreTab) coreTab.style.display = "block";
    if (aiTab) aiTab.style.display = "none";
    if (tab0) tab0.classList.add("active");
    if (tab1) tab1.classList.remove("active");
    if (pill && tabBar && tab0) {
      pill.style.left = (tab0.offsetLeft - tabBar.offsetLeft - 3) + "px";
      pill.style.width = tab0.offsetWidth + "px";
    }
  } else {
    if (coreTab) coreTab.style.display = "none";
    if (aiTab) aiTab.style.display = "block";
    if (tab0) tab0.classList.remove("active");
    if (tab1) tab1.classList.add("active");
    if (pill && tabBar && tab1) {
      pill.style.left = (tab1.offsetLeft - tabBar.offsetLeft - 3) + "px";
      pill.style.width = tab1.offsetWidth + "px";
    }
  }
};

window.selectRatio = function(element) {
  document.querySelectorAll(".ratio-grid .ratio-btn").forEach(btn => btn.classList.remove("active"));
  element.classList.add("active");
  const ratio = element.querySelector(".ratio-label").textContent.trim();
  const ptAspectRatio = document.getElementById("pt-aspect-ratio");
  if (ptAspectRatio) {
    ptAspectRatio.value = ratio;
    // Trigger aspect ratio text summary update if active
    const sAspectRatio = document.getElementById("s-aspect-ratio");
    if (sAspectRatio) sAspectRatio.textContent = ratio;
    if (currentScriptData) {
      currentScriptData.project.aspect_ratio = ratio;
    }
  }
};

window.toggleSettingsModal = function() {
  const modal = document.getElementById("settings-modal");
  if (modal) modal.classList.toggle("hidden");
};

window.closeSettings = function() {
  const modal = document.getElementById("settings-modal");
  if (modal) modal.classList.add("hidden");
};

window.saveSettingsModal = async function() {
  if (googleKeyDirty) await window.saveGoogleKey();
  if (deepseekKeyDirty) await window.saveDeepseekKey();
  if (googleTtsKeyDirty) await window.saveGoogleTtsKey();
  window.closeSettings();
};

window.toggleKey = function(id, btn) {
  const inp = document.getElementById(id);
  if (!inp) return;
  const show = inp.type === "password";
  inp.type = show ? "text" : "password";
  btn.textContent = show ? "Hide" : "Show";
};

function toggleCustomStyleInput() {
  const select = document.getElementById("pt-style-select");
  const customRow = document.getElementById("custom-style-row");
  if (select.value === "custom") {
    customRow.classList.remove("hidden");
  } else {
    customRow.classList.add("hidden");
  }
}

// ── Plain text parsing ────────────────────────────────────────────────────────

async function parsePlainText() {
  const text = document.getElementById('pt-script').value.trim();
  const title = document.getElementById('pt-title').value.trim();
  const voice = document.getElementById('pt-voice').value;
  const aspectRatio = document.getElementById('pt-aspect-ratio').value;
  const aiGuideline = document.getElementById('pt-ai-guideline').value.trim();
  const voiceDialect = document.getElementById('pt-voice-dialect').value;
  const narrativeTone = document.getElementById('pt-narrative-tone').value;
  const speakerMode = document.getElementById('pt-speaker-mode').value;

  // Automatically generate filename from title (lowercase, no spaces/special characters)
  const filename = title ? title.toLowerCase().replace(/[^a-z0-9]+/g, '_') : 'my_video';

  // Get visual style based on selection
  const styleSelect = document.getElementById('pt-style-select').value;
  let visualStyle = styleSelect;
  if (styleSelect === 'custom') {
    visualStyle = document.getElementById('pt-visual-style-custom').value.trim();
  }

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

  const btn = document.getElementById('btn-parse');
  btn.textContent = '🧠 AI Agent Planning storyboard…';
  btn.disabled = true;
  errBlock.classList.add('hidden');
  storyboard.classList.add('hidden');

  if (isWebMode) {
    try {
      const googleKey = localStorage.getItem("google_api_key") || "";
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
          google_api_key: googleKey,
          ai_guideline: aiGuideline,
          voice_dialect: voiceDialect,
          narrative_tone: narrativeTone,
          speaker_mode: speakerMode
        })
      });
      const result = await resp.json();
      window.onParseComplete(result);
    } catch (err) {
      window.onParseComplete({ success: false, errors: [err.message] });
    }
  } else {
    await window.pywebview.api.parse_plain_text(
      text, title, voice, filename, visualStyle, aspectRatio, aiGuideline, voiceDialect, narrativeTone, speakerMode
    );
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
  if (result.fallback) {
    let cleanErr = result.error_msg || "Token missing or API call failed";
    if (cleanErr.length > 50) {
      cleanErr = cleanErr.substring(0, 50) + "...";
    }
    document.getElementById('sb-status').textContent = `⚠️ Planned (Rule Fallback) — ${cleanErr}`;
    console.warn("AI Storyboard Planner fell back to rules. Error details:", result.error_msg);
  } else {
    document.getElementById('sb-status').textContent = "🤖 AI Structured";
  }
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
    card.id = `scene${idx}`;
    card.style.animationDelay = `${idx * 0.05}s`;

    const badgeClass = seg.type === "hook" ? "tag-hook" : seg.type === "conclusion" ? "tag-conclusion" : seg.type === "cta" ? "tag-cta" : "tag-body";
    const tagLabel = seg.type ? seg.type.toUpperCase() : "BODY";

    const kbOptions = ["zoom_in", "zoom_out", "pan_left", "pan_right", "none"]
      .map(opt => `<option value="${opt}" ${seg.ken_burns === opt ? 'selected' : ''}>${opt.replace('_', ' ')}</option>`)
      .join('');

    const overlayText = seg.text_overlay ? seg.text_overlay.text : "";
    const voiceSteering = seg.voice_steering || "";

    card.innerHTML = `
      <div class="scene-card-top">
        <span class="scene-num">#${seg.segment_id}</span>
        <span class="scene-tag ${badgeClass}">${tagLabel}</span>
        <div class="scene-actions">
          <button class="scene-action-btn" title="Preview speech" onclick="previewSceneSpeech(${idx})"><i class="ti ti-player-play" aria-hidden="true"></i></button>
          <button class="scene-action-btn" title="Delete scene" onclick="deleteStoryboardScene(${idx})" style="color:var(--text3)"><i class="ti ti-trash" aria-hidden="true"></i></button>
        </div>
      </div>
      <div class="scene-card-body space-y-2">
        <div>
          <div class="scene-field-label"><i class="ti ti-microphone" aria-hidden="true"></i>Voice Narration (verbatim)</div>
          <textarea class="scene-narration scene-input-narration" data-index="${idx}" oninput="syncScene(${idx},'narration',this.value)">${seg.narration}</textarea>
        </div>
        
        <div>
          <div class="scene-field-label"><i class="ti ti-microphone-alt" aria-hidden="true"></i>Voice Steering & Tone (Optional)</div>
          <input type="text" class="form-input scene-input-steering" data-index="${idx}" value="${voiceSteering}" oninput="syncScene(${idx},'voice_steering',this.value)" placeholder="e.g. Speak with a warm conversational cadence" />
        </div>

        <div>
          <div class="scene-field-label"><i class="ti ti-photo" aria-hidden="true"></i>B-Roll Visual Prompt</div>
          <textarea class="scene-broll scene-input-keyword" data-index="${idx}" oninput="syncScene(${idx},'b_roll_keyword',this.value)">${seg.b_roll_keyword}</textarea>
        </div>

        <div class="grid grid-cols-2 gap-2">
          <div>
            <div class="scene-field-label"><i class="ti ti-arrows-maximize" aria-hidden="true"></i>Ken Burns Motion</div>
            <select class="form-select scene-input-kb" data-index="${idx}" onchange="syncScene(${idx},'ken_burns',this.value)">
              ${kbOptions}
            </select>
          </div>
          <div>
            <div class="scene-field-label"><i class="ti ti-typography" aria-hidden="true"></i>Text Overlay</div>
            <input type="text" class="form-input scene-input-overlay" data-index="${idx}" value="${overlayText}" oninput="syncSceneOverlay(${idx},this.value)" placeholder="Optional subtitle text" />
          </div>
        </div>
      </div>
    `;
    container.appendChild(card);
  });

  buildSceneStrip();
}

// ── Save Storyboard edits ─────────────────────────────────────────────────────

async function saveStoryboardEdits(showNotification = false) {
  if (!currentScriptData || !currentScriptPath) return false;

  const narrations = document.querySelectorAll(".scene-input-narration");
  const keywords = document.querySelectorAll(".scene-input-keyword");
  const motions = document.querySelectorAll(".scene-input-kb");
  const overlays = document.querySelectorAll(".scene-input-overlay");
  const steerings = document.querySelectorAll(".scene-input-steering");

  // Client-side validation: ensure no narration or keyword fields are empty
  for (let el of narrations) {
    const idx = parseInt(el.getAttribute("data-index"));
    const val = el.value.trim();
    currentScriptData.segments[idx].narration = val;
    if (!val) {
      alert(`Scene ${idx + 1} Voice Narration cannot be empty. Please enter some text before saving or starting render.`);
      el.focus();
      return false;
    }
  }

  for (let el of keywords) {
    const idx = parseInt(el.getAttribute("data-index"));
    const val = el.value.trim();
    currentScriptData.segments[idx].b_roll_keyword = val;
    if (!val) {
      alert(`Scene ${idx + 1} Visual Generation Prompt cannot be empty. Please enter a visual description before saving or starting render.`);
      el.focus();
      return false;
    }
  }

  motions.forEach((el) => {
    const idx = parseInt(el.getAttribute("data-index"));
    currentScriptData.segments[idx].ken_burns = el.value;
  });

  steerings.forEach((el) => {
    const idx = parseInt(el.getAttribute("data-index"));
    currentScriptData.segments[idx].voice_steering = el.value.trim();
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

window.openProjectFolder = async function() {
    if (!currentScriptData) return;
    const title = currentScriptData.project.title;
    if (isWebMode) {
        alert("Project folder is only accessible in Desktop mode.");
    } else {
        await window.pywebview.api.open_project_folder(title);
    }
};

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

// ── Google Credentials ─────────────────────────────────────────

let googleKeyDirty = false;
let googleTtsKeyDirty = false;
let deepseekKeyDirty = false;

window.saveGoogleKey = async function() {
    const key = document.getElementById("google-key-input").value.trim();
    if (isWebMode) {
        localStorage.setItem("google_api_key", key);
        setGoogleKeyStatus("saved", "✓ Saved (Local)");
    } else {
        await window.pywebview.api.save_google_key(key);
        googleKeyDirty = false;
        setGoogleKeyStatus("saved", "✓ Saved");
    }
};

window.saveDeepseekKey = async function() {
    const key = document.getElementById("deepseek-key-input").value.trim();
    if (isWebMode) {
        localStorage.setItem("deepseek_api_key", key);
        setDeepseekKeyStatus("saved", "✓ Saved (Local)");
    } else {
        await window.pywebview.api.save_deepseek_key(key);
        deepseekKeyDirty = false;
        setDeepseekKeyStatus("saved", "✓ Saved");
    }
};

window.saveGoogleTtsKey = async function() {
    const key = document.getElementById("google-tts-key-input").value.trim();
    if (isWebMode) {
        localStorage.setItem("google_tts_api_key", key);
        setGoogleTtsKeyStatus("saved", key ? "✓ Saved (Local)" : "✓ Cleared (Local)");
    } else {
        await window.pywebview.api.save_google_tts_key(key);
        googleTtsKeyDirty = false;
        setGoogleTtsKeyStatus("saved", key ? "✓ Saved" : "✓ Cleared");
    }
};

window.onGoogleKeyInput = function() {
    googleKeyDirty = true;
    setGoogleKeyStatus("", "");
};

window.onDeepseekKeyInput = function() {
    deepseekKeyDirty = true;
    setDeepseekKeyStatus("", "");
};

window.onGoogleTtsKeyInput = function() {
    googleTtsKeyDirty = true;
    setGoogleTtsKeyStatus("", "");
};

function setGoogleKeyStatus(type, msg) {
    const el = document.getElementById("google-key-status");
    if (el) { el.textContent = msg; el.className = "key-status " + type; }
}

function setDeepseekKeyStatus(type, msg) {
    const el = document.getElementById("deepseek-key-status");
    if (el) { el.textContent = msg; el.className = "key-status " + type; }
}

function setGoogleTtsKeyStatus(type, msg) {
    const el = document.getElementById("google-tts-key-status");
    if (el) { el.textContent = msg; el.className = "key-status " + type; }
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
  const validationPassed = await saveStoryboardEdits(false);
  if (!validationPassed) return;

  if (!currentScriptPath || isRendering) return;

  if (googleKeyDirty) await saveGoogleKey();
  if (googleTtsKeyDirty) await saveGoogleTtsKey();
  if (deepseekKeyDirty) await saveDeepseekKey();

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
  const progText = document.getElementById("progress-text");
  if (progText) progText.textContent = "0%";
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
      const progText = document.getElementById("progress-text");
      if (progText) progText.textContent = pct + "%";
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
      const progTextComplete = document.getElementById("progress-text");
      if (progTextComplete) progTextComplete.textContent = "100%";
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
  document.getElementById("pt-style-select").value = document.getElementById("pt-style-select").options[0].value;
  document.getElementById("pt-visual-style-custom").value = "";
  toggleCustomStyleInput();
  updateRenderButton();
}

window.clearCache = async function() {
    if (isWebMode) {
        alert("Clear Cache is not available in Web mode.");
        return;
    }
    const hint = document.getElementById("render-hint");
    if (hint) hint.textContent = "Clearing cache...";
    try {
        const res = await window.pywebview.api.clear_cache();
        if (res.success) {
            if (hint) hint.textContent = "Cache cleared successfully!";
        } else {
            if (hint) hint.textContent = "Failed to clear cache: " + res.error;
        }
    } catch (e) {
        if (hint) hint.textContent = "Error clearing cache: " + e;
    }
};

// ── Storyboard card sync and utility actions ─────────────────────────────────

window.syncScene = function(idx, field, val) {
  if (currentScriptData && currentScriptData.segments[idx]) {
    currentScriptData.segments[idx][field] = val;
  }
};

window.syncSceneOverlay = function(idx, val) {
  if (currentScriptData && currentScriptData.segments[idx]) {
    if (val.trim()) {
      const segDuration = Math.max(3, Math.round(currentScriptData.segments[idx].narration.length / 15));
      currentScriptData.segments[idx].text_overlay = {
        "text": val.trim(),
        "position": "bottom_center",
        "duration_seconds": segDuration
      };
    } else {
      currentScriptData.segments[idx].text_overlay = null;
    }
  }
};

window.deleteStoryboardScene = function(idx) {
  if (!currentScriptData || currentScriptData.segments.length <= 1) return;
  currentScriptData.segments.splice(idx, 1);
  currentScriptData.segments.forEach((seg, i) => {
    seg.segment_id = i + 1;
  });
  drawStoryboard(currentScriptData);
  
  // Update summaries
  const sSegments = document.getElementById("s-segments");
  if (sSegments) sSegments.textContent = currentScriptData.segments.length + " segments";
  const sbEstDuration = document.getElementById("sb-est-duration");
  if (sbEstDuration) sbEstDuration.textContent = `~${Math.round(currentScriptData.segments.length * 4)} seconds`;
};

// ── Horizontal timeline navigation strip ─────────────────────────────────────

function buildSceneStrip() {
  const strip = document.getElementById("sceneStrip");
  if (!strip || !currentScriptData) return;
  
  const colors = {
    hook: "rgba(6,182,212,0.25)",
    body: "rgba(99,102,241,0.25)",
    cta: "rgba(139,92,246,0.25)",
    conclusion: "rgba(16,185,129,0.25)"
  };
  
  strip.innerHTML = currentScriptData.segments.map((s, i) => `
    <div onclick="previewScene(${i})" style="flex-shrink:0;width:32px;height:24px;border-radius:6px;border:1px solid rgba(255,255,255,0.1);background:${colors[s.type] || "rgba(255,255,255,0.05)"};cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:600;color:#94a3b8;transition:all 0.15s" onmouseover="this.style.transform='scale(1.1)'" onmouseout="this.style.transform='scale(1)'" title="Scene ${s.segment_id}: ${s.type || 'Body'}">${s.segment_id}</div>
  `).join("");
}

window.previewScene = function(idx) {
  if (!currentScriptData || !currentScriptData.segments[idx]) return;
  
  const seg = currentScriptData.segments[idx];
  const preview = document.getElementById("previewStage");
  const captionBar = document.getElementById("captionBar");
  
  const colors = {
    hook: "rgba(6,182,212,0.1)",
    body: "rgba(99,102,241,0.1)",
    cta: "rgba(139,92,246,0.1)",
    conclusion: "rgba(16,185,129,0.1)"
  };
  
  if (preview) {
    preview.style.backgroundColor = colors[seg.type] || "rgba(0,0,0,0.35)";
    preview.querySelector(".preview-inner").innerHTML = `
      <div style="font-size:11px;font-weight:600;color:#94a3b8;letter-spacing:0.5px;text-transform:uppercase">${seg.type || 'Body'} — Scene ${seg.segment_id}</div>
      <div style="font-size:10px;color:#64748b;max-width:180px;text-align:center;line-height:1.5;margin-top:4px">${seg.b_roll_keyword.substring(0,80)}…</div>
    `;
  }
  
  if (captionBar) {
    captionBar.style.display = "block";
    captionBar.textContent = seg.narration;
  }
  
  // Highlight active card border in middle panel
  document.querySelectorAll(".scene-card").forEach(c => c.style.borderColor = "");
  const activeCard = document.getElementById(`scene${idx}`);
  if (activeCard) {
    activeCard.style.borderColor = "rgba(99,102,241,0.6)";
    activeCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
};

// ── TTS waveform visualizer ───────────────────────────────────────────────

function buildWave() {
  const wrap = document.getElementById("waveBars");
  if (!wrap) return;
  wrap.innerHTML = "";
  for (let i = 0; i < 35; i++) {
    const b = document.createElement("div");
    b.className = "wbar";
    const h = 4 + Math.random() * 16;
    b.style.height = h + "px";
    wrap.appendChild(b);
  }
}

let waveAnim = null;
window.animateWave = function(on) {
  const bars = document.querySelectorAll(".wbar");
  if (on) {
    if (waveAnim) clearInterval(waveAnim);
    waveAnim = setInterval(() => {
      bars.forEach((b, i) => {
        const phase = Date.now() / 120 + i * 0.4;
        const h = 4 + Math.abs(Math.sin(phase)) * 26;
        b.style.height = h + "px";
        b.classList.toggle("active", h > 16);
      });
    }, 60);
  } else {
    if (waveAnim) clearInterval(waveAnim);
    bars.forEach(b => {
      b.classList.remove("active");
      b.style.height = (4 + Math.random() * 8) + "px";
    });
  }
};

window.previewSceneSpeech = function(idx) {
  if (!currentScriptData || !currentScriptData.segments[idx]) return;
  
  window.animateWave(true);
  const ttsStatus = document.getElementById("ttsStatus");
  if (ttsStatus) ttsStatus.textContent = `Scene ${idx + 1} TTS synthesis…`;
  
  setTimeout(() => {
    window.animateWave(false);
    if (ttsStatus) ttsStatus.textContent = "Done · 1.8s";
    window.previewScene(idx);
  }, 1800);
};

// ── Log and Terminal controls ───────────────────────────────────────────────

window.toggleLog = function() {
  const body = document.getElementById("logBody");
  const header = document.getElementById("logHeader");
  const chev = document.getElementById("logChevron");
  if (!body) return;
  const open = body.classList.toggle("visible");
  if (header) header.classList.toggle("open", open);
  if (chev) chev.style.transform = open ? "rotate(180deg)" : "";
};

window.openLog = function() {
  const body = document.getElementById("logBody");
  const header = document.getElementById("logHeader");
  const chev = document.getElementById("logChevron");
  if (body) body.classList.add("visible");
  if (header) header.classList.add("open");
  if (chev) chev.style.transform = "rotate(180deg)";
};

// Init waveform on script boot
buildWave();
