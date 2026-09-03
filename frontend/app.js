/**
 * Smart Studio frontend — IPC bridge between PyWebView API and UI.
 * Plain HTML/CSS/JS architecture supporting native desktop and cloud fallback.
 */

let isWebMode = typeof window.pywebview === "undefined" || !window.pywebview.api;

let currentScriptPath = null;
let currentScriptData = null;
let coverageReport = null;
let isRendering = false;
let logLines = [];
const MAX_LOG_LINES = 150;

let seriesPacks = [];
let voiceCatalogue = [];
const openVoiceEngines = new Set();
let activeReplaceShot = null;

// ── Busy indicators ───────────────────────────────────────────────────────────
// Any action that leaves the UI unchanged for more than an instant has to show
// that it is working. Planning, coverage recalculation and image import all run
// CLIP or touch the disk, and each one used to freeze the interface in silence.

function setButtonBusy(btn, busyLabel) {
  if (!btn) return;
  if (!btn.dataset.idleLabel) btn.dataset.idleLabel = btn.innerHTML;
  btn.dataset.busy = "1";
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span>${busyLabel}`;
}

function clearButtonBusy(btn) {
  if (!btn) return;
  btn.disabled = false;
  delete btn.dataset.busy;
  if (btn.dataset.idleLabel) {
    btn.innerHTML = btn.dataset.idleLabel;
    delete btn.dataset.idleLabel;
  }
}

/** A thin working strip above the storyboard while coverage is recalculated. */
function setBoardBusy(busy, label) {
  const el = document.getElementById("board-busy");
  if (!el) return;
  el.textContent = label || "Working…";
  el.classList.toggle("hidden", !busy);
}

// Base64 decoder helper
window.decodeBase64UTF8 = function(payload) {
  const binary = atob(payload);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new TextDecoder("utf-8").decode(bytes);
};

// Boot lifecycle
window.addEventListener("pywebviewready", () => {
  initApp();
});

window.addEventListener("DOMContentLoaded", () => {
  if (isWebMode) {
    initApp();
  }
});

setTimeout(() => {
  if (typeof window.pywebview !== "undefined" && window.pywebview.api) {
    initApp();
  }
}, 400);

async function initApp() {
  isWebMode = typeof window.pywebview === "undefined" || !window.pywebview.api;

  if (isWebMode) {
    document.getElementById("version-badge").textContent = "v2.0.0 (Cloud)";
  } else {
    try {
      const ver = await window.pywebview.api.get_version();
      document.getElementById("version-badge").textContent = `v${ver}`;
    } catch (e) {}
  }

  await loadSeriesPacks();
  await loadVoiceCatalogue();
  await loadSettingsData();
  await loadLibraryData();
  await loadImageFolders();
  // Before applyUiDefaults, which can only restore a choice the list already
  // holds. The motion styles do not depend on the niche, so they load once.
  await loadMotionStyles();
  await applyUiDefaults();
  await restoreLastProject();
  await checkFfmpegStatus();
}

async function checkFfmpegStatus() {
  if (isWebMode || typeof window.pywebview === "undefined" || !window.pywebview.api) {
    return;
  }
  try {
    if (window.pywebview.api.check_ffmpeg) {
      const res = await window.pywebview.api.check_ffmpeg();
      const banner = document.getElementById("ffmpeg-missing-banner");
      if (!banner) return;
      if (res && !res.available) {
        const msg = res.message || "FFmpeg is not installed on this computer. Smart Studio needs it to build video and to measure narration. Install it from https://ffmpeg.org/download.html, make sure it is on your PATH, then restart Smart Studio.";
        banner.textContent = msg;
        banner.classList.remove("hidden");
      } else {
        banner.classList.add("hidden");
      }
    }
  } catch (e) {
    console.error("Failed to check ffmpeg status:", e);
  }
}


// ── Remembering the Script screen ─────────────────────────────────────────────
// Voice, series pack, tone and style reset to the first option on every launch,
// so the same choices had to be made before every video.

const UI_FIELDS = {
  voice: "pt-voice", series_slug: "pt-series-slug",
  tone: "pt-tone", visual_type: "pt-style",
  motion_style: "pt-motion",
};

async function rememberUiChoices() {
  if (isWebMode) return;
  const defaults = {};
  for (const [key, id] of Object.entries(UI_FIELDS)) {
    const el = document.getElementById(id);
    if (el && el.value) defaults[key] = el.value;
  }
  defaults.captions_enabled = captionsEnabled();
  const rhythm = document.getElementById("shot-rhythm-slider");
  // Store the seconds, not the slider position. A stored position silently
  // changes meaning the moment the slider's range or mapping is edited.
  if (rhythm) defaults.shot_rhythm_seconds = RHYTHM_SECONDS[rhythm.value] || 7;
  const imgCountEl = document.getElementById("image-count");
  if (imgCountEl && imgCountEl.value) {
    defaults.image_count = parseInt(imgCountEl.value, 10);
  }
  defaults.formats = getSelectedFormats();
  try { await window.pywebview.api.save_ui_defaults(defaults); } catch (e) {}
}

async function applyUiDefaults() {
  if (isWebMode) return;
  try {
    const res = await window.pywebview.api.get_ui_defaults();
    const d = (res && res.ui_defaults) || {};

    // Order matters. Setting .value in code fires no "change" event, so the
    // visual-type list would still hold the first pack's presets while the
    // niche dropdown showed the remembered one. The saved visual_type then
    // failed to restore and the whole feature fell back to style_block with
    // nothing on screen to say so. Restore the niche, repopulate, then the type.
    for (const [key, id] of Object.entries(UI_FIELDS)) {
      if (key === "visual_type") continue;
      const el = document.getElementById(id);
      if (!el || !d[key]) continue;
      if ([...el.options].some(o => o.value === d[key])) el.value = d[key];
    }

    await loadStylePresets();

    const styleEl = document.getElementById("pt-style");
    if (styleEl && d.visual_type
        && [...styleEl.options].some(o => o.value === d.visual_type)) {
      styleEl.value = d.visual_type;
    }
    if (typeof d.captions_enabled === "boolean" && d.captions_enabled !== captionsEnabled()) {
      toggleCaptionsMaster();
    }
    const rhythm = document.getElementById("shot-rhythm-slider");
    // `shot_rhythm` was the old slider position under the inverted mapping; it is
    // ignored on purpose, because restoring it would restore the wrong speed.
    if (rhythm && d.shot_rhythm_seconds) {
      rhythm.value = rhythmPositionFor(d.shot_rhythm_seconds);
      const lbl = document.getElementById("rhythm-label");
      if (lbl) lbl.textContent = `~${RHYTHM_SECONDS[rhythm.value] || 7}s per shot`;
    }
    const imgCountEl = document.getElementById("image-count");
    if (imgCountEl && d.image_count) {
      imgCountEl.value = d.image_count;
      updateImageCountHint(d.image_count);
    }
    if (Array.isArray(d.formats) && d.formats.length) {
      document.querySelectorAll(".fmt").forEach(btn => {
        const on = d.formats.includes(btn.dataset.fmt);
        btn.classList.toggle("on", on);
        const tick = btn.querySelector(".tick");
        if (tick) tick.textContent = on ? "✓" : " ";
      });
    }
  } catch (e) {}
}

window.rememberUiChoices = rememberUiChoices;
window.applyUiDefaults = applyUiDefaults;

// ── Screen Navigation ────────────────────────────────────────────────────────
function switchPane(paneId) {
  document.querySelectorAll(".nav").forEach(b => {
    b.setAttribute("aria-selected", b.dataset.p === paneId ? "true" : "false");
  });

  document.querySelectorAll(".pane").forEach(p => {
    p.removeAttribute("data-on");
    if (p.dataset.pane === paneId) {
      p.setAttribute("data-on", "1");
    }
  });

  if (paneId === "library") {
    loadLibraryData();
  }

  if (paneId === "timeline" && typeof renderTimelineScreen === "function") {
    renderTimelineScreen();
  } else if (typeof timelinePauseAudio === "function") {
    timelinePauseAudio();
  }

  if (paneId === "voice" && typeof initVoiceStudio === "function") {
    initVoiceStudio();
  }
}

// ── Format Checklist ─────────────────────────────────────────────────────────
function toggleFormat(btn) {
  btn.classList.toggle("on");
  const tickSpan = btn.querySelector(".tick");
  if (tickSpan) {
    tickSpan.textContent = btn.classList.contains("on") ? "✓" : " ";
  }
}

function getSelectedFormats() {
  const selected = [];
  document.querySelectorAll(".fmt.on").forEach(b => {
    if (b.dataset.fmt) selected.push(b.dataset.fmt);
  });
  return selected.length > 0 ? selected : ["16:9"];
}

// ── Captions Master Toggle ────────────────────────────────────────────────────
function toggleCaptionsMaster() {
  const master = document.getElementById("capMaster");
  const opts = document.getElementById("capOpts");
  if (!master || !opts) return;

  master.classList.toggle("on");
  const isOn = master.classList.contains("on");
  opts.classList.toggle("off", !isOn);
  master.lastChild.textContent = isOn ? "On" : "Off";
  applyCaptionSetting();
}

/** True when the Script screen's captions master toggle is on. */
function captionsEnabled() {
  const master = document.getElementById("capMaster");
  return master ? master.classList.contains("on") : true;
}

/**
 * Push the captions toggle into the script itself.
 *
 * The toggle used to live only in the DOM, so the planner never recorded it and
 * the renderer saw disable_captions unset — captions were burned into every shot
 * whatever the switch said.
 */
function applyCaptionSetting() {
  if (!currentScriptData || !currentScriptData.project) return;
  const on = captionsEnabled();
  currentScriptData.project.disable_captions = !on;
  currentScriptData.project.captions = {
    ...(currentScriptData.project.captions || {}),
    enabled: on,
    source: (currentScriptData.project.captions || {}).source || "tts_timings",
  };
}

// ── Theme Switcher ───────────────────────────────────────────────────────────
function toggleTheme() {
  const html = document.documentElement;
  const current = html.getAttribute("data-theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  html.setAttribute("data-theme", next);
  document.getElementById("btn-theme-toggle").textContent = `Theme: ${next === "dark" ? "Dark" : "Light"}`;
}

// ── Series Packs Loader ──────────────────────────────────────────────────────
async function loadSeriesPacks() {
  const select = document.getElementById("pt-series-slug");
  if (!select) return;

  select.innerHTML = "";

  if (!isWebMode && window.pywebview.api.get_series_packs) {
    try {
      seriesPacks = await window.pywebview.api.get_series_packs();
    } catch (e) {
      console.error("Failed to load series packs:", e);
    }
  }

  if (!seriesPacks || seriesPacks.length === 0) {
    seriesPacks = [
      { series_slug: "islamic_history", display_name: "Islamic History" },
      { series_slug: "space_science", display_name: "Space Science" },
      { series_slug: "world_military_history", display_name: "World Military History" },
      { series_slug: "true_crime", display_name: "True Crime" },
      { series_slug: "mythology_folklore", display_name: "Mythology & Folklore" },
      { series_slug: "nature_wildlife", display_name: "Nature & Wildlife" },
      { series_slug: "biography", display_name: "Biography" },
      { series_slug: "business_money", display_name: "Business & Money" },
      { series_slug: "default", display_name: "Default (General)" }
    ];
  }

  seriesPacks.forEach(p => {
    const opt = document.createElement("option");
    opt.value = p.series_slug;
    opt.textContent = p.display_name;
    select.appendChild(opt);
  });

  select.addEventListener("change", async () => {
    await loadStylePresets();
    await loadNarrationTones();
  });
  await loadStylePresets();
  await loadNarrationTones();
}

// ── Camera motion ────────────────────────────────────────────────────────────
// Static / Gentle drift / Ken Burns / Dynamic. The style sets how far the frame
// travels per second of shot and how much padding the crop moves across, and it
// deals the four moves out in a cycle so a film stops repeating one move.
async function loadMotionStyles() {
  const sel = document.getElementById("pt-motion");
  if (!sel || isWebMode) return;

  let styles = [];
  try {
    styles = await window.pywebview.api.get_motion_styles();
  } catch (e) {
    console.error("Could not load motion styles:", e);
  }
  if (!styles.length) return;

  const previous = sel.value;
  sel.innerHTML = "";
  styles.forEach(st => {
    const opt = new Option(st.label, st.key);
    opt.title = st.description;
    sel.appendChild(opt);
  });

  if (previous && [...sel.options].some(o => o.value === previous)) {
    sel.value = previous;
  } else {
    const fallback = styles.find(st => st.default) || styles[0];
    sel.value = fallback.key;
  }
}

// ── Narration tone ───────────────────────────────────────────────────────────
// The tone is not a label. It sets the reading speed and the length of the
// silence left at each sentence and paragraph, which is what actually makes a
// motivational read sound different from a news read.
async function loadNarrationTones() {
  const sel = document.getElementById("pt-tone");
  if (!sel || isWebMode) return;
  const slug = (document.getElementById("pt-series-slug") || {}).value || "";

  let tones = [];
  try {
    tones = await window.pywebview.api.get_narration_tones(slug);
  } catch (e) {
    console.error("Could not load narration tones:", e);
  }
  if (!tones.length) return;

  const previous = sel.value;
  sel.innerHTML = "";

  const best = tones.filter(t => t.recommended);
  const rest = tones.filter(t => !t.recommended);

  const addGroup = (labelText, items) => {
    if (!items.length) return;
    const group = document.createElement("optgroup");
    group.label = labelText;
    items.forEach(t => {
      const opt = new Option(t.label, t.key);
      opt.title = t.steering;
      group.appendChild(opt);
    });
    sel.appendChild(group);
  };

  addGroup("Best for this niche", best);
  addGroup("Other tones", rest);

  // Keep the user's pick if this niche still offers it, else take the first
  // recommendation, which is the one written for this niche.
  if (previous && [...sel.options].some(o => o.value === previous)) {
    sel.value = previous;
  } else if (best.length) {
    sel.value = best[0].key;
  }
}
window.loadNarrationTones = loadNarrationTones;

// ── Prompt opening ───────────────────────────────────────────────────────────

// ── Visual Types ─────────────────────────────────────────────────────────────
async function loadStylePresets() {
  const sel = document.getElementById("pt-style");
  const slugEl = document.getElementById("pt-series-slug");
  if (!sel || !slugEl) return;

  let presets = [];
  if (!isWebMode && window.pywebview.api.get_style_presets) {
    try {
      presets = await window.pywebview.api.get_style_presets(slugEl.value);
    } catch (e) {
      console.error("Failed to load style presets:", e);
    }
  }

  sel.innerHTML = "";
  if (!presets.length) {
    sel.appendChild(new Option("Pack default", ""));
    return;
  }
  presets.forEach(p => {
    const opt = new Option(p.label, p.key);
    opt.title = p.prompt;
    sel.appendChild(opt);
  });
}

// ── Voice Catalogue Loader & Settings ─────────────────────────────────────────
async function loadVoiceCatalogue() {
  if (!isWebMode && window.pywebview.api.get_voice_catalogue) {
    try {
      voiceCatalogue = await window.pywebview.api.get_voice_catalogue();
    } catch (e) {
      console.error("Failed to load voice catalogue:", e);
    }
  }

  if (!voiceCatalogue || voiceCatalogue.length === 0) {
    voiceCatalogue = [
      {
        engine: "Google Cloud",
        voices: [
          { id: "google:en-GB-Neural2-D", label: "Neural2-D (male)", gender: "male", lang: "en-GB", captions: "fast", timings: true, enabled: true },
          { id: "google:en-US-Neural2-F", label: "Neural2-F (female)", gender: "female", lang: "en-US", captions: "fast", timings: true, enabled: true }
        ]
      },
      {
        engine: "Gemini Flash TTS",
        voices: [
          { id: "google:gemini-3.1-flash-tts-preview:Charon", label: "Charon (male)", gender: "male", lang: "multi", captions: "fast", timings: true, enabled: true },
          { id: "google:gemini-3.1-flash-tts-preview:Puck", label: "Puck (male)", gender: "male", lang: "multi", captions: "fast", timings: true, enabled: true }
        ]
      },
      {
        engine: "Kokoro",
        voices: [
          { id: "local:kokoro-af_heart", label: "af_heart (female)", gender: "female", lang: "en-US", captions: "slow", timings: false, enabled: true },
          { id: "local:kokoro-am_michael", label: "am_michael (male)", gender: "male", lang: "en-US", captions: "slow", timings: false, enabled: true }
        ]
      },
      {
        engine: "Supertonic",
        voices: [
          { id: "local:supertonic-m1", label: "M1 (male)", gender: "male", lang: "en + ar", captions: "slow", timings: false, enabled: true }
        ]
      }
    ];
  }

  renderVoiceCatalogueSettings();
  renderScriptNarratorSelect();
}

function renderVoiceCatalogueSettings() {
  const container = document.getElementById("voice-engines-container");
  if (!container) return;

  container.innerHTML = "";
  let totalAvailable = 0;
  let totalEnabled = 0;

  voiceCatalogue.forEach((engGroup, idx) => {
    const isOpen = openVoiceEngines.has(engGroup.engine);
    const engDiv = document.createElement("div");
    engDiv.className = isOpen ? "eng" : "eng collapsed";

    let enabledInEng = 0;
    let rowsHtml = "";

    engGroup.voices.forEach(v => {
      totalAvailable++;
      if (v.enabled) {
        totalEnabled++;
        enabledInEng++;
      }

      const cbClass = v.enabled ? "cb on" : "cb";
      const cbCheck = v.enabled ? "✓" : "";
      const capPillClass = v.captions === "fast" ? "p-ok" : "p-warn";

      rowsHtml += `
        <tr>
          <td><span class="${cbClass}" onclick="toggleVoiceEnable('${v.id}')">${cbCheck}</span></td>
          <td><b>${v.label}</b> <span class="mono">${v.gender || ''}</span></td>
          <td class="mono">${v.lang}</td>
          <td><span class="pill ${capPillClass}">${v.captions}</span></td>
          <td><button type="button" class="ghost" onclick="previewSpecificVoice('${v.id}')">Preview</button></td>
        </tr>
      `;
    });

    const tblId = `eng-tbl-${idx}`;
    engDiv.innerHTML = `
      <div class="eng-h" role="button" tabindex="0" aria-expanded="${isOpen ? 'true' : 'false'}" aria-controls="${tblId}" data-engine="${engGroup.engine}">
        <span class="chevron" aria-hidden="true">▶</span>
        <b>${engGroup.engine}</b>
        <span class="pill p-mute">${engGroup.voices.length} voices</span>
        <span class="mono" style="margin-left:auto">${enabledInEng} enabled</span>
      </div>
      <div class="tbl" id="${tblId}">
        <table>
          <thead><tr><th style="width:34px"></th><th>Voice</th><th>Lang</th><th>Captions</th><th></th></tr></thead>
          <tbody>${rowsHtml}</tbody>
        </table>
      </div>
    `;

    container.appendChild(engDiv);
  });

  const countSpan = document.getElementById("voice-catalogue-count");
  if (countSpan) {
    countSpan.textContent = `${totalAvailable} available · ${totalEnabled} enabled`;
  }
}

// ── Settings Collapsible Sections & Voice Engine Accordion ─────────────────
document.addEventListener("click", (e) => {
  const toggleBtn = e.target.closest(".card-toggle");
  if (toggleBtn) {
    const card = toggleBtn.closest(".card");
    const controlsId = toggleBtn.getAttribute("aria-controls");
    const body = controlsId ? document.getElementById(controlsId) : (card ? card.querySelector(".card-body") : null);
    const isExpanded = toggleBtn.getAttribute("aria-expanded") === "true";
    const nextState = !isExpanded;

    toggleBtn.setAttribute("aria-expanded", String(nextState));
    if (card) {
      card.classList.toggle("collapsed", !nextState);
    }
    if (body) {
      if (nextState) {
        body.removeAttribute("hidden");
      } else {
        body.setAttribute("hidden", "");
      }
    }
    return;
  }

  // Voice engine header toggle (ignoring clicks on checkboxes, preview buttons, inputs)
  const engHeader = e.target.closest(".eng-h");
  if (engHeader && !e.target.closest(".cb") && !e.target.closest("button") && !e.target.closest("input")) {
    const engName = engHeader.getAttribute("data-engine");
    if (engName) {
      if (openVoiceEngines.has(engName)) {
        openVoiceEngines.delete(engName);
      } else {
        openVoiceEngines.add(engName);
      }
      renderVoiceCatalogueSettings();
    }
  }
});

// Keyboard support (Enter & Space) for .eng-h
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    const engHeader = document.activeElement && document.activeElement.closest(".eng-h");
    if (engHeader && document.activeElement === engHeader) {
      e.preventDefault();
      const engName = engHeader.getAttribute("data-engine");
      if (engName) {
        if (openVoiceEngines.has(engName)) {
          openVoiceEngines.delete(engName);
        } else {
          openVoiceEngines.add(engName);
        }
        renderVoiceCatalogueSettings();
        const updatedHeader = Array.from(document.querySelectorAll(".eng-h")).find(el => el.getAttribute("data-engine") === engName);
        if (updatedHeader) updatedHeader.focus();
      }
    }
  }
});

function toggleVoiceEnable(voiceId) {
  voiceCatalogue.forEach(group => {
    group.voices.forEach(v => {
      if (v.id === voiceId) {
        v.enabled = !v.enabled;
      }
    });
  });

  renderVoiceCatalogueSettings();
  renderScriptNarratorSelect();

  if (!isWebMode && window.pywebview.api.save_voice_catalogue) {
    window.pywebview.api.save_voice_catalogue(voiceCatalogue);
  }
}

function renderScriptNarratorSelect() {
  const select = document.getElementById("pt-voice");
  if (!select) return;

  select.innerHTML = "";

  voiceCatalogue.forEach(group => {
    const enabledVoices = group.voices.filter(v => v.enabled);
    if (enabledVoices.length > 0) {
      const optgroup = document.createElement("optgroup");
      optgroup.label = group.engine;

      enabledVoices.forEach(v => {
        const opt = document.createElement("option");
        opt.value = v.id;
        opt.textContent = `${v.label} · ${v.lang} · ${v.captions} captions`;
        optgroup.appendChild(opt);
      });

      select.appendChild(optgroup);
    }
  });

  const mgmtOpt = document.createElement("option");
  mgmtOpt.value = "manage";
  mgmtOpt.textContent = "— manage voices in Settings —";
  select.appendChild(mgmtOpt);

  select.onchange = () => {
    if (select.value === "manage") {
      switchPane("settings");
    }
  };
}

// ── Voice Preview ──────────────────────────────────────────────────────────
async function previewVoice() {
  const voice = document.getElementById("pt-voice").value;
  if (!voice || voice === "manage") return;
  await previewSpecificVoice(voice);
}

async function previewSpecificVoice(voiceId) {
  const status = document.getElementById("voice-preview-status");
  if (status) status.textContent = "Generating preview...";

  if (isWebMode) {
    if (status) status.textContent = "Preview available in desktop mode.";
    return;
  }

  try {
    const res = await window.pywebview.api.preview_voice(voiceId);
    if (res.success && res.audio_b64) {
      const audio = new Audio("data:audio/mp3;base64," + res.audio_b64);
      audio.play();
      if (status) status.textContent = "Playing...";
      audio.onended = () => {
        if (status) status.textContent = "";
      };
    } else {
      if (status) status.textContent = "Preview error: " + (res.error || "failed");
    }
  } catch (e) {
    if (status) status.textContent = "Preview error";
  }
}

// ── Settings Keys Load & Save ────────────────────────────────────────────────
/**
 * Show whether each key is set — never the key itself.
 *
 * The backend used to hand the raw keys to this page and they were written
 * straight back into the inputs, which put live credentials in the DOM. The UI
 * only needs to know a key exists; to change one you type a new one.
 */
async function loadSettingsData() {
  if (isWebMode) {
    setKeyStatus("anthropic-key-status", !!localStorage.getItem("anthropic_api_key"));
    setKeyStatus("openai-key-status", !!localStorage.getItem("openai_api_key"));
    setKeyStatus("google-key-status", !!localStorage.getItem("google_api_key"));
    setKeyStatus("deepseek-key-status", !!localStorage.getItem("deepseek_api_key"));
    setKeyStatus("google-tts-key-status", !!localStorage.getItem("google_tts_api_key"));
    setKeyStatus("elevenlabs-key-status", !!localStorage.getItem("elevenlabs_api_key"));
    return;
  }

  try {
    const settings = await window.pywebview.api.get_settings();
    const rows = [
      ["anthropic-key", settings.anthropic_api_key_set, settings.anthropic_api_key_len],
      ["openai-key", settings.openai_api_key_set, settings.openai_api_key_len],
      ["google-key", settings.google_api_key_set, settings.google_api_key_len],
      ["deepseek-key", settings.deepseek_api_key_set, settings.deepseek_api_key_len],
      ["google-tts-key", settings.google_tts_api_key_set, settings.google_tts_api_key_len],
      ["elevenlabs-key", settings.elevenlabs_api_key_set, settings.elevenlabs_api_key_len],
    ];
    rows.forEach(([id, isSet, len]) => {
      setKeyStatus(`${id}-status`, !!isSet, len);
      const input = document.getElementById(`${id}-input`);
      if (input && isSet) input.placeholder = "•••••• stored — type a new key to replace";
    });

    const aiDescCb = document.getElementById("setting-ai-shot-descriptions");
    if (aiDescCb) {
      aiDescCb.checked = !!settings.ai_shot_descriptions;
    }

    const llmPlanCb = document.getElementById("setting-llm-planning");
    if (llmPlanCb) {
      llmPlanCb.checked = !!settings.llm_planning_enabled;
    }

    const modeAuto = document.getElementById("pw-mode-auto");
    if (modeAuto) {
      modeAuto.checked = (settings.prompt_writer_mode === "auto" || !settings.prompt_writer_mode);
    }

    const pwConfig = settings.prompt_writer_providers || {};
    ["anthropic", "openai", "gemini", "deepseek"].forEach(p => {
      const pInfo = pwConfig[p] || {};
      const cb = document.getElementById(`pw-enable-${p}`);
      if (cb) {
        cb.checked = (pInfo.enabled !== undefined) ? !!pInfo.enabled : (p === "gemini" || p === "anthropic");
      }
      const modelInput = document.getElementById(`pw-model-${p}`);
      if (modelInput && pInfo.model) {
        modelInput.value = pInfo.model;
      }
    });

    // Check last provider status / error banner
    try {
      if (window.pywebview.api.get_provider_status) {
        const statusObj = await window.pywebview.api.get_provider_status();
        const banner = document.getElementById("provider-status-banner");
        if (banner && statusObj && statusObj.message) {
          banner.textContent = statusObj.message;
          banner.className = `provider-banner ${statusObj.status || ""}`.trim();
        }
      }
    } catch (e) {}
  } catch (e) {}
  await loadNicheStyleSettings();
}

async function toggleAiShotDescriptions(enabled) {
  if (!isWebMode) {
    await window.pywebview.api.save_ai_shot_descriptions(enabled);
  } else {
    localStorage.setItem("ai_shot_descriptions", enabled ? "1" : "0");
  }
}
window.toggleAiShotDescriptions = toggleAiShotDescriptions;

async function toggleLlmPlanning(enabled) {
  if (!isWebMode) {
    await window.pywebview.api.save_llm_planning_enabled(enabled);
  } else {
    localStorage.setItem("llm_planning_enabled", enabled ? "1" : "0");
  }
}
window.toggleLlmPlanning = toggleLlmPlanning;

function onPromptWriterModeChange() {
  savePromptWriterSettings();
}
window.onPromptWriterModeChange = onPromptWriterModeChange;

async function savePromptWriterSettings() {
  const modeAuto = document.getElementById("pw-mode-auto");
  const mode = modeAuto && modeAuto.checked ? "auto" : "auto";
  const providersConfig = {};
  ["anthropic", "openai", "gemini", "deepseek"].forEach(p => {
    const cb = document.getElementById(`pw-enable-${p}`);
    const modelInput = document.getElementById(`pw-model-${p}`);
    providersConfig[p] = {
      enabled: cb ? cb.checked : false,
      model: modelInput ? modelInput.value.trim() : ""
    };
  });

  const payload = {
    prompt_writer_mode: mode,
    prompt_writer_providers: providersConfig
  };

  if (!isWebMode) {
    await window.pywebview.api.save_prompt_writer_settings(payload);
  } else {
    localStorage.setItem("prompt_writer_settings", JSON.stringify(payload));
  }
}
window.savePromptWriterSettings = savePromptWriterSettings;

function setKeyStatus(id, connected, len = 0) {
  const el = document.getElementById(id);
  if (!el) return;
  if (connected) {
    el.className = "pill p-ok";
    el.textContent = len > 0 ? `●●●● set` : "●●●● set";
  } else {
    el.className = "pill p-mute";
    el.textContent = "not set";
  }
}

async function saveAndTestProvider(provider) {
  const keyInput = document.getElementById(`${provider === "gemini" ? "google" : provider}-key-input`);
  const modelInput = document.getElementById(`pw-model-${provider}`);
  const resultSpan = document.getElementById(`${provider}-test-result`);
  const statusPill = document.getElementById(`${provider === "gemini" ? "google" : provider}-key-status`);

  if (resultSpan) {
    resultSpan.textContent = "testing…";
    resultSpan.className = "test-result";
  }

  const keyVal = keyInput ? keyInput.value.trim() : "";
  const modelVal = modelInput ? modelInput.value.trim() : "";

  // Save key if user entered one
  if (keyVal) {
    if (!isWebMode) {
      if (provider === "gemini") await window.pywebview.api.save_google_key(keyVal);
      else if (provider === "anthropic") await window.pywebview.api.save_anthropic_key(keyVal);
      else if (provider === "openai") await window.pywebview.api.save_openai_key(keyVal);
      else if (provider === "deepseek") await window.pywebview.api.save_deepseek_key(keyVal);
    }
  }

  await savePromptWriterSettings();

  let testRes = { status: "error", message: "Failed" };
  if (!isWebMode) {
    testRes = await window.pywebview.api.test_llm_provider(provider, modelVal, keyVal);
  } else {
    testRes = { status: "ok", message: "working" };
  }

  if (resultSpan) {
    if (testRes.status === "ok") {
      resultSpan.textContent = "working";
      resultSpan.className = "test-result ok";
      if (statusPill) {
        statusPill.className = "pill p-ok";
        statusPill.textContent = "●●●● set";
      }
    } else {
      const codeStr = testRes.code ? ` (${testRes.code})` : "";
      resultSpan.textContent = (testRes.reason || testRes.message || "error") + codeStr;
      resultSpan.className = "test-result err";
      resultSpan.title = testRes.message || "";
    }
  }

  const banner = document.getElementById("provider-status-banner");
  if (banner && testRes.status !== "ok" && testRes.message) {
    banner.textContent = testRes.message;
    banner.className = "provider-banner";
  }
}
window.saveAndTestProvider = saveAndTestProvider;

/**
 * Delete a stored key, said out loud.
 *
 * Emptying the field and pressing Test did nothing, because saving is guarded
 * by `if (keyVal)`. That guard has to stay: the backend never sends real keys
 * to the browser, so every field is blank on load and an always-save would wipe
 * a working key the first time any other provider was tested.
 */
async function removeProviderKey(provider) {
  const uiName = provider === "gemini" ? "google" : provider;
  const label = { gemini: "Google", google_tts: "Google TTS" }[provider]
    || provider.charAt(0).toUpperCase() + provider.slice(1);
  if (!confirm(`Remove the ${label} key from this machine?\n\n` +
               `The app stops using ${label} until you enter a new one.`)) return;

  const statusPill = document.getElementById(`${uiName}-key-status`);
  const resultSpan = document.getElementById(`${provider}-test-result`);
  try {
    const res = isWebMode
      ? { success: true, removed: true }
      : await window.pywebview.api.remove_api_key(provider);
    if (!res || !res.success) {
      alert("Could not remove that key: " + ((res && res.error) || "unknown error"));
      return;
    }
    const input = document.getElementById(`${uiName}-key-input`);
    if (input) input.value = "";
    if (statusPill) {
      statusPill.className = "pill p-mute";
      statusPill.textContent = "not set";
    }
    if (resultSpan) {
      resultSpan.textContent = res.removed ? "removed" : "there was no key";
      resultSpan.className = "test-result";
    }
  } catch (e) {
    alert("Could not remove that key: " + e.message);
  }
}
window.removeProviderKey = removeProviderKey;

async function saveGoogleKey() {
  const key = document.getElementById("google-key-input").value;
  if (!isWebMode) {
    await window.pywebview.api.save_google_key(key);
  } else {
    localStorage.setItem("google_api_key", key);
  }
  setKeyStatus("google-key-status", !!key.trim());
}
window.saveGoogleKey = saveGoogleKey;

async function saveGoogleTtsKey() {
  const key = document.getElementById("google-tts-key-input").value;
  if (!isWebMode) {
    await window.pywebview.api.save_google_tts_key(key);
  } else {
    localStorage.setItem("google_tts_api_key", key);
  }
  setKeyStatus("google-tts-key-status", !!key.trim());
}
window.saveGoogleTtsKey = saveGoogleTtsKey;

async function saveElevenLabsKey() {
  const key = document.getElementById("elevenlabs-key-input").value;
  if (!isWebMode) {
    await window.pywebview.api.save_elevenlabs_key(key);
  } else {
    localStorage.setItem("elevenlabs_api_key", key);
  }
  setKeyStatus("elevenlabs-key-status", !!key.trim());
}
window.saveElevenLabsKey = saveElevenLabsKey;



// ── Visual Style Per Niche (Settings Editor) ─────────────────────────────────

async function loadNicheStyleSettings() {
  const sel = document.getElementById("niche-select");
  if (!sel) return;
  
  if (!isWebMode && window.pywebview.api.get_series_packs) {
    try {
      const packs = await window.pywebview.api.get_series_packs();
      sel.innerHTML = "";
      packs.forEach(p => {
        const opt = new Option(p.display_name, p.series_slug);
        sel.appendChild(opt);
      });
      const scriptSlug = (document.getElementById("pt-series-slug") || {}).value;
      if (scriptSlug && Array.from(sel.options).some(o => o.value === scriptSlug)) {
        sel.value = scriptSlug;
      }
    } catch (e) {
      console.error("Failed to load series packs for niche editor:", e);
    }
  }
  await onNicheSelectChange();
}
window.loadNicheStyleSettings = loadNicheStyleSettings;

let currentNicheVisualTypes = [];

function renderNicheVisualTypesList() {
  const container = document.getElementById("niche-visual-types-list");
  if (!container) return;
  
  if (!currentNicheVisualTypes || currentNicheVisualTypes.length === 0) {
    container.innerHTML = `<p class="hint vt-empty">No visual types defined yet. Click "+ Add visual type" below to create one.</p>`;
    return;
  }

  const escapeHtml = (str) => String(str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  let html = "";
  currentNicheVisualTypes.forEach((vt, idx) => {
    const isFirst = idx === 0;
    const isLast = idx === currentNicheVisualTypes.length - 1;
    const isDefaultBadge = isFirst ? `<span class="pill p-ok vt-badge">DEFAULT</span>` : "";
    const treatmentBadge = vt.treatment && vt.treatment !== "none" ? `<span class="mono vt-treatment">[${escapeHtml(vt.treatment)}]</span>` : "";

    html += `
      <div class="visual-type-row">
        <div class="vt-move">
          <button type="button" class="ghost tiny icon-btn" title="Move Up" ${isFirst ? "disabled" : ""} onclick="moveVisualType(${idx}, -1)">▲</button>
          <button type="button" class="ghost tiny icon-btn" title="Move Down" ${isLast ? "disabled" : ""} onclick="moveVisualType(${idx}, 1)">▼</button>
        </div>
        <div class="vt-fields">
          <div class="vt-name-row">
            <input type="text" value="${escapeHtml(vt.label)}" placeholder="Visual type name (e.g. 3D Realistic Photo)" oninput="onVisualTypeChange(${idx}, 'label', this.value)">
            ${isDefaultBadge}
            ${treatmentBadge}
          </div>
          <textarea rows="2" class="compact" placeholder="Prompt instruction (e.g. 3D render, soft global illumination, physically based materials, shallow depth of field...)" oninput="onVisualTypeChange(${idx}, 'prompt', this.value)">${escapeHtml(vt.prompt)}</textarea>
        </div>
        <button type="button" class="ghost tiny icon-btn danger vt-remove" title="Remove" onclick="removeVisualType(${idx})">✕</button>
      </div>
    `;
  });

  container.innerHTML = html;
}
window.renderNicheVisualTypesList = renderNicheVisualTypesList;

function addNewVisualTypeRow() {
  currentNicheVisualTypes.push({
    key: "",
    label: "",
    prompt: "",
    treatment: "none",
  });
  renderNicheVisualTypesList();
  updateNichePreview();

  const container = document.getElementById("niche-visual-types-list");
  if (container) {
    const inputs = container.querySelectorAll("input[type='text']");
    if (inputs.length) {
      inputs[inputs.length - 1].focus();
    }
  }
}
window.addNewVisualTypeRow = addNewVisualTypeRow;

function moveVisualType(idx, dir) {
  const targetIdx = idx + dir;
  if (targetIdx < 0 || targetIdx >= currentNicheVisualTypes.length) return;
  const temp = currentNicheVisualTypes[idx];
  currentNicheVisualTypes[idx] = currentNicheVisualTypes[targetIdx];
  currentNicheVisualTypes[targetIdx] = temp;
  renderNicheVisualTypesList();
  updateNichePreview();
}
window.moveVisualType = moveVisualType;

function removeVisualType(idx) {
  if (idx < 0 || idx >= currentNicheVisualTypes.length) return;
  currentNicheVisualTypes.splice(idx, 1);
  renderNicheVisualTypesList();
  updateNichePreview();
}
window.removeVisualType = removeVisualType;

function onVisualTypeChange(idx, field, value) {
  if (idx < 0 || idx >= currentNicheVisualTypes.length) return;
  currentNicheVisualTypes[idx][field] = value;
  updateNichePreview();
}
window.onVisualTypeChange = onVisualTypeChange;

async function onNicheSelectChange() {
  const sel = document.getElementById("niche-select");
  if (!sel) return;
  const slug = sel.value;
  if (!slug) return;

  if (!isWebMode && window.pywebview.api.get_niche_style) {
    try {
      const data = await window.pywebview.api.get_niche_style(slug);
      if (data.success) {
        const nameEl = document.getElementById("niche-display-name-input");
        const eraEl = document.getElementById("niche-era-input");
        const negEl = document.getElementById("niche-negative-input");
        const recipeEl = document.getElementById("niche-prompt-recipe-input");

        if (nameEl) nameEl.value = data.display_name || "";
        if (eraEl) eraEl.value = data.era_block || "";
        if (negEl) negEl.value = data.negative_block || "";
        if (recipeEl) recipeEl.value = data.prompt_recipe || "";

        currentNicheVisualTypes = (data.style_presets || []).map(p => ({ ...p }));
        renderNicheVisualTypesList();

        const statusEl = document.getElementById("niche-override-status");
        if (statusEl) {
          if (data.is_user_created) {
            statusEl.textContent = "custom niche";
            statusEl.className = "mono pill p-ok";
          } else {
            statusEl.textContent = data.is_overridden ? "customised" : "default";
            statusEl.className = data.is_overridden ? "mono pill p-warn" : "mono";
          }
        }

        const resetBtn = document.getElementById("btn-niche-reset");
        const deleteBtn = document.getElementById("btn-niche-delete");
        if (resetBtn) resetBtn.style.display = data.is_user_created ? "none" : "inline-block";
        if (deleteBtn) deleteBtn.style.display = data.is_user_created ? "inline-block" : "none";
      }
    } catch (e) {
      console.error("Failed to get niche style:", e);
    }
  }
  updateNichePreview();
}
window.onNicheSelectChange = onNicheSelectChange;

function updateNichePreview() {
  const previewEl = document.getElementById("niche-prompt-preview");
  if (!previewEl) return;

  let medium = "";
  if (currentNicheVisualTypes && currentNicheVisualTypes.length > 0) {
    const firstType = currentNicheVisualTypes[0];
    if (firstType && firstType.prompt) {
      medium = firstType.prompt.trim();
    }
  }

  const era = (document.getElementById("niche-era-input") || {}).value ? document.getElementById("niche-era-input").value.trim() : "";

  const parts = ["A citadel at dawn", "wide establishing shot"];
  if (medium) parts.push(medium.replace(/\.+$/, ""));
  if (era && !parts.join(", ").toLowerCase().includes(era.toLowerCase())) {
    parts.push(era.replace(/\.+$/, ""));
  }

  previewEl.textContent = parts.filter(Boolean).join(", ").replace(/,\s*$/, "") + ".";
}
window.updateNichePreview = updateNichePreview;

async function saveNicheStyle() {
  const sel = document.getElementById("niche-select");
  if (!sel) return;
  const slug = sel.value;
  if (!slug) return;

  const style_presets = {};
  currentNicheVisualTypes.forEach((vt, i) => {
    const label = (vt.label || "").trim();
    const prompt = (vt.prompt || "").trim();
    if (!label && !prompt) return;
    let key = (vt.key || "").trim();
    if (!key) {
      key = label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
      if (!key) key = "visual_type_" + (i + 1);
    }
    let finalKey = key;
    let counter = 2;
    while (style_presets[finalKey]) {
      finalKey = `${key}_${counter}`;
      counter++;
    }
    style_presets[finalKey] = {
      label: label || finalKey.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase()),
      prompt: prompt,
      treatment: vt.treatment || "none"
    };
  });

  const overrides = {
    display_name: (document.getElementById("niche-display-name-input") || {}).value || "",
    era_block: (document.getElementById("niche-era-input") || {}).value ? document.getElementById("niche-era-input").value.trim() : "",
    negative_block: (document.getElementById("niche-negative-input") || {}).value ? document.getElementById("niche-negative-input").value.trim() : "",
    prompt_recipe: (document.getElementById("niche-prompt-recipe-input") || {}).value || "",
    style_presets: style_presets,
  };

  if (!isWebMode && window.pywebview.api.save_niche_style) {
    try {
      const res = await window.pywebview.api.save_niche_style(slug, overrides);
      if (res.success) {
        alert("Visual style saved for " + sel.options[sel.selectedIndex].text + ".\nStored in config/series_overrides/" + slug + ".json");
        await loadSeriesPacks();
        await loadStylePresets();
        await loadNicheStyleSettings();
        if (currentScriptData) {
          await refreshStoryboardCoverage();
        }
      } else {
        alert("Failed to save style: " + (res.error || "unknown error"));
      }
    } catch (e) {
      alert("Error saving style: " + e.message);
    }
  }
}
window.saveNicheStyle = saveNicheStyle;

async function resetNicheStyle() {
  const sel = document.getElementById("niche-select");
  if (!sel) return;
  const slug = sel.value;
  if (!slug) return;

  if (!confirm(`Reset ${sel.options[sel.selectedIndex].text} visual style to shipped default?`)) {
    return;
  }

  if (!isWebMode && window.pywebview.api.reset_niche_style) {
    try {
      const res = await window.pywebview.api.reset_niche_style(slug);
      if (res.success) {
        alert("Reset to default.");
        await loadStylePresets();
        await onNicheSelectChange();
        if (currentScriptData) {
          await refreshStoryboardCoverage();
        }
      } else {
        alert("Failed to reset style: " + (res.error || "unknown error"));
      }
    } catch (e) {
      alert("Error resetting style: " + e.message);
    }
  }
}
window.resetNicheStyle = resetNicheStyle;

function openNewNicheModal() {
  const modal = document.getElementById("modal-new-niche");
  if (modal) {
    const slugEl = document.getElementById("new-niche-slug");
    const nameEl = document.getElementById("new-niche-name");
    if (slugEl) slugEl.value = "";
    if (nameEl) nameEl.value = "";
    modal.style.display = "flex";
    if (slugEl) slugEl.focus();
  }
}
window.openNewNicheModal = openNewNicheModal;

function closeNewNicheModal() {
  const modal = document.getElementById("modal-new-niche");
  if (modal) modal.style.display = "none";
}
window.closeNewNicheModal = closeNewNicheModal;

async function submitCreateNewNiche() {
  const slugInput = document.getElementById("new-niche-slug");
  const nameInput = document.getElementById("new-niche-name");
  const rawSlug = (slugInput ? slugInput.value : "").trim();
  const rawName = (nameInput ? nameInput.value : "").trim();

  if (!rawSlug) {
    alert("Please provide a niche slug (e.g. cyberpunk_noir).");
    return;
  }

  const slug = rawSlug.toLowerCase().replace(/[^a-z0-9_]/g, "_");

  if (!isWebMode && window.pywebview.api.create_user_niche) {
    try {
      const res = await window.pywebview.api.create_user_niche(slug, rawName || slug.replace(/_/g, " ").toUpperCase());
      if (res.success) {
        closeNewNicheModal();
        await loadSeriesPacks();
        await loadNicheStyleSettings();
        const sel = document.getElementById("niche-select");
        if (sel) {
          sel.value = slug;
          await onNicheSelectChange();
        }
        alert(`Created new niche "${rawName || slug}" in config/series_overrides/${slug}.json`);
      } else {
        alert("Failed to create niche: " + (res.error || "unknown error"));
      }
    } catch (e) {
      alert("Error creating niche: " + e.message);
    }
  }
}
window.submitCreateNewNiche = submitCreateNewNiche;

async function deleteNicheStyle() {
  const sel = document.getElementById("niche-select");
  if (!sel) return;
  const slug = sel.value;
  if (!slug) return;

  if (!confirm(`Delete custom niche "${sel.options[sel.selectedIndex].text}" (${slug})?\n\nThis will remove config/series_overrides/${slug}.json.`)) {
    return;
  }

  if (!isWebMode && window.pywebview.api.delete_user_niche) {
    try {
      const res = await window.pywebview.api.delete_user_niche(slug);
      if (res.success) {
        alert("Niche deleted.");
        await loadSeriesPacks();
        await loadNicheStyleSettings();
      } else {
        alert("Failed to delete niche: " + (res.error || "unknown error"));
      }
    } catch (e) {
      alert("Error deleting niche: " + e.message);
    }
  }
}
window.deleteNicheStyle = deleteNicheStyle;


// ── Paste External Prompts & Numbered Folder Matching ────────────────────────

function togglePastePromptsPanel() {
  const panel = document.getElementById("paste-prompts-panel");
  if (!panel) return;
  if (panel.style.display === "none" || panel.classList.contains("hidden")) {
    panel.style.display = "block";
    panel.classList.remove("hidden");
    const ta = document.getElementById("paste-prompts-textarea");
    if (ta) ta.focus();
  } else {
    panel.style.display = "none";
    panel.classList.add("hidden");
  }
}
window.togglePastePromptsPanel = togglePastePromptsPanel;

async function submitPastedPrompts() {
  if (!currentScriptData) {
    alert("Please plan or load a storyboard first.");
    return;
  }
  const ta = document.getElementById("paste-prompts-textarea");
  const text = (ta ? ta.value : "").trim();
  if (!text) {
    alert("Please paste one or more prompt blocks (separated by blank lines).");
    return;
  }

  const workingFolder = (currentScriptData.project || {}).image_folder || "";
  const btn = document.getElementById("btn-apply-pasted-prompts");
  setButtonBusy(btn, "Matching…");

  try {
    if (!isWebMode && window.pywebview.api.apply_external_prompts) {
      const res = await window.pywebview.api.apply_external_prompts(currentScriptData, text, workingFolder);
      if (!res.success) {
        alert(res.error || "Failed to apply prompts.");
        return;
      }

      currentScriptData = res.script_data;
      if (currentScriptPath) {
        await window.pywebview.api.save_edited_script(currentScriptPath, currentScriptData);
      }

      // Display summary line
      const summaryEl = document.getElementById("paste-prompts-summary");
      if (summaryEl) {
        summaryEl.textContent = res.summary || "";
      }

      // Both counts, named out loud. Over-supply and under-supply each get a
      // sentence; silence here is what let a mismatch pass unnoticed.
      const countsEl = document.getElementById("paste-prompts-counts");
      if (countsEl) {
        const mismatch = (res.unprompted_pictures || 0) > 0 || (res.unused_prompts || 0) > 0;
        countsEl.textContent = res.counts || "";
        countsEl.className = "prompt-counts" + (res.counts ? " shown" : "") + (mismatch ? " mismatch" : "");
      }

      // Render mapping preview table
      const tableWrap = document.getElementById("paste-prompts-table-wrap");
      const tbody = document.getElementById("paste-prompts-table-body");
      if (tableWrap && tbody && res.mapping_table) {
        tbody.innerHTML = "";
        res.mapping_table.forEach(row => {
          const tr = document.createElement("tr");
          tr.style.borderBottom = "1px solid var(--line)";
          const isMatched = row.status === "matched";
          tr.innerHTML = `
            <td style="padding:6px 8px; font-family:var(--mono); font-weight:700">${row.slot}</td>
            <td style="padding:6px 8px; color:var(--text, #e1e7ec)" title="${(row.prompt_full || '').replace(/"/g, '&quot;')}">${row.prompt_preview || ''}</td>
            <td style="padding:6px 8px; font-family:var(--mono); font-size:11px; color:${isMatched ? 'var(--text)' : 'var(--ink-3)'}">${row.image_found || '—'}</td>
            <td style="padding:6px 8px; font-family:var(--mono); font-weight:700; color:${isMatched ? 'var(--ok, #73c991)' : 'var(--gap, #e06c75)'}">
              ${isMatched ? '✓' : 'missing'}
            </td>
          `;
          tbody.appendChild(tr);
        });
        tableWrap.style.display = "block";
      }

      // Re-render storyboard coverage and cards
      await refreshStoryboardCoverage();
    }
  } catch (e) {
    alert("Error applying prompts: " + e.message);
  } finally {
    clearButtonBusy(btn);
  }
}
window.submitPastedPrompts = submitPastedPrompts;

// The manual route, with no API key. The app writes the request an outside AI
// needs — the niche recipe, the whole script, and the numbered list of moments
// this film wants a picture for — so the AI never has to guess how the script
// was cut up. Its reply goes straight back into the box above.
async function writePromptRequest() {
  const status = document.getElementById("prompt-request-status");
  const btn = document.getElementById("btn-write-prompt-request");
  if (!currentScriptData) {
    if (status) status.textContent = "Plan the storyboard first.";
    return;
  }
  setButtonBusy(btn, "Writing…");
  try {
    if (isWebMode) {
      if (status) status.textContent = "Only available in the desktop app.";
      return;
    }
    const res = await window.pywebview.api.write_prompt_request(currentScriptData);
    if (status) {
      status.textContent = res && res.success
        ? `Saved — ${res.pictures} moments. Paste this file into any AI chat.`
        : `Could not write it: ${(res && res.error) || "unknown error"}`;
    }
  } catch (e) {
    if (status) status.textContent = "Could not write it: " + e.message;
  } finally {
    clearButtonBusy(btn);
  }
}
window.writePromptRequest = writePromptRequest;



// ── Script Loading & Planning ────────────────────────────────────────────────
/**
 * Reopen the project this app last had open.
 *
 * Planned scripts were written to a temp file and the only way back was a JSON
 * file picker, so closing the app lost every image you had placed by hand — and
 * Windows could clear the file on its own. Projects now live under projects/ and
 * come back on their own.
 */
async function restoreLastProject() {
  if (isWebMode) return;
  try {
    const res = await window.pywebview.api.get_last_project();
    if (!res.success || !res.found) return;

    currentScriptPath = res.path;
    currentScriptData = res.script_data;
    applyCaptionSetting();

    const title = document.getElementById("pt-title");
    if (title && res.title) title.value = res.title;
    const label = document.getElementById("script-status-label");
    if (label) label.textContent = `reopened: ${res.title} · ${res.segments} segments`;

    if (currentScriptData && currentScriptData.project) {
      const applyEraEl = document.getElementById("pt-apply-era");
      if (applyEraEl) {
        applyEraEl.checked = currentScriptData.project.apply_era !== false;
      }
    }

    await loadImageFolders();
    await refreshStoryboardCoverage();
  } catch (e) {
    console.error("Could not reopen the last project:", e);
  }
}
window.restoreLastProject = restoreLastProject;

async function planStoryboard() {
  await rememberUiChoices();
  const title = document.getElementById("pt-title").value;
  const text = document.getElementById("pt-text").value;
  const seriesSlug = document.getElementById("pt-series-slug").value;
  const voice = document.getElementById("pt-voice").value;
  const styleSel = document.getElementById("pt-style");
  // The backend still treats visual_style as prose - it feeds the LLM planner and
  // the world-anchor fallback. Send the label, never the snake_case key.
  const style = styleSel.selectedIndex >= 0
    ? styleSel.options[styleSel.selectedIndex].textContent.trim()
    : "";
  const tone = document.getElementById("pt-tone").value;
  const motionEl = document.getElementById("pt-motion");
  const motionStyle = motionEl ? motionEl.value : "";

  if (!text.trim()) {
    alert("Please paste or type script text before planning.");
    return;
  }

  const btn = document.getElementById("btn-plan-storyboard");
  setButtonBusy(btn, "Planning storyboard…");

  if (isWebMode) {
    // Basic local parse fallback in web mode
    const paragraphs = text.split(/\n\s*\n/).filter(p => p.trim());
    currentScriptData = {
      project: {
        title: title || "Untitled Project",
        series_slug: seriesSlug,
        voice: { id: voice },
        visual_style: style,
        visual_type: (document.getElementById("pt-style") || {}).value || "",
        narration_tone: tone,
        motion_style: motionStyle,
        apply_era: (document.getElementById("pt-apply-era") || {}).checked !== false,
      },
      segments: paragraphs.map((p, i) => ({
        segment_id: i + 1,
        narration: p.trim(),
        b_roll_keyword: "cinematic scene",
        shots: [{ shot_id: `${i+1}a`, query: "cinematic scene" }]
      }))
    };

    currentScriptPath = null;
    clearButtonBusy(btn);

    await refreshStoryboardCoverage();
    switchPane("board");
    return;
  }

  try {
    const res = await window.pywebview.api.parse_plain_text(
      text,
      title,
      voice,
      title.toLowerCase().replace(/[^a-z0-9]+/g, "_") + ".mp4",
      style,
      getSelectedFormats()[0],
      "",
      "",
      tone,
      "single",
      motionStyle,
      seriesSlug
    );

    if (res.started) {
      // Result comes via window.onParseComplete(result)
    }
  } catch (e) {
    clearButtonBusy(btn);
    alert("Planning failed: " + e.message);
  }
}

window.onParseComplete = async function(result) {
  const btn = document.getElementById("btn-plan-storyboard");
  clearButtonBusy(btn);

  if (result.success) {
    currentScriptPath = result.path;
    currentScriptData = result.script_data;
    // The planner does not know about these two, so attach them here, before the
    // draft is saved and before coverage is planned — plan_shots reads them off
    // project and every prompt in this script then opens the same way.
    currentScriptData.project = currentScriptData.project || {};
    currentScriptData.project.visual_type = document.getElementById("pt-style").value || "";
    const applyEraEl = document.getElementById("pt-apply-era");
    currentScriptData.project.apply_era = applyEraEl ? applyEraEl.checked : true;
    applyCaptionSetting();
    await saveDraftScript(true);

    document.getElementById("script-status-label").textContent = `planned: ${result.title}`;

    await refreshStoryboardCoverage();
    switchPane("board");
  } else {
    alert("Storyboard planning failed: " + (result.errors ? result.errors.join("\n") : "unknown error"));
  }
};

/** Save the project under projects/, and remember it as the one to reopen. */
async function saveDraftScript(quiet) {
  if (!currentScriptData) {
    if (!quiet) alert("Nothing to save yet — plan a storyboard first.");
    return false;
  }
  if (isWebMode) {
    if (!quiet) alert("Draft saved in memory.");
    return false;
  }

  const res = await window.pywebview.api.save_project(currentScriptData);
  if (!res.success) {
    if (!quiet) alert("Could not save the project: " + (res.error || "unknown error"));
    return false;
  }
  currentScriptPath = res.path;
  if (!quiet) alert(`Saved to ${res.path}\n\nIt reopens by itself next time you start the app.`);
  return true;
}
window.saveDraftScript = saveDraftScript;

// ── Storyboard Screen Coverage & Rendering ────────────────────────────────────
async function refreshStoryboardCoverage() {
  if (!currentScriptData) return;

  if (!isWebMode && window.pywebview.api.get_storyboard_coverage) {
    // This searches the CLIP index once per shot, so it is seconds of silence
    // on a full episode. Say so rather than appearing frozen.
    setBoardBusy(true, "Matching shots against your library…");
    try {
      const res = await window.pywebview.api.get_storyboard_coverage(currentScriptData);
      if (res.success) {
        coverageReport = res.report;
        rememberResolvedImages();

        // The brief is drafted by the backend on every plan — recurring figures
        // only, no medium — and is no longer editable, so it is simply stored.
        const drafted = (res.report && res.report.project_brief) || "";
        if (drafted && currentScriptData) {
          currentScriptData.project = currentScriptData.project || {};
          currentScriptData.project.project_brief = drafted;
        }
      } else if (res.error) {
        console.error("Coverage calculation failed:", res.error);
        setBoardBusy(true, `Coverage failed: ${res.error}`);
        renderStoryboardScreen();
        return;
      }
    } catch (e) {
      console.error("Coverage calculation error:", e);
    } finally {
      setBoardBusy(false);
    }
  }

  renderStoryboardScreen();
}

/**
 * Record what each shot settled on, so the next plan keeps it.
 *
 * Retrieval is greedy and never reuses an image, so without a memory every
 * refresh re-assigned the whole board: choosing an image for one shot freed its
 * old one and cascaded through all the others. Fix one, break another.
 */
function rememberResolvedImages() {
  if (!currentScriptData || !coverageReport) return;

  const byKey = {};
  (coverageReport.shot_reports || []).forEach(r => {
    byKey[`${r.segment_id}_${r.shot_id}`] = r;
  });

  currentScriptData.segments.forEach(seg => {
    (seg.shots || []).forEach(shot => {
      const r = byKey[`${seg.segment_id}_${shot.shot_id}`];
      if (!r) return;
      if (r.best_path && r.state !== "gap") {
        shot.resolved = r.best_path;
        shot.resolved_score = r.best_score;
      } else {
        delete shot.resolved;
        delete shot.resolved_score;
      }
    });
  });
}

/* ── Pictures, not shots ─────────────────────────────────────────────────────
   The board drew one row per shot. A 347-segment film with 60 pictures drew 347
   rows, most of them repeats of a picture already shown further up, and there
   was no way to see how long a picture actually held or which stretch of
   narration it had been given. These helpers group the segments back into the
   pictures they belong to, so a row is a picture and carries its real timing. */

/** Spoken seconds per segment: measured where a timing pass has run, estimated elsewhere. */
function segmentSecondsList(script) {
  return (script.segments || []).map(seg => {
    const measured = parseFloat(seg.narration_seconds);
    if (isFinite(measured) && measured > 0) return measured;
    const words = String(seg.narration || "").trim().split(/\s+/).filter(Boolean).length;
    return words ? words / 2.6 : 0;   // WORDS_PER_SECOND, same as the backend
  });
}

/** Walk the script once, following share_with, and return one entry per picture. */
function picturesFromScript(script) {
  const secs = segmentSecondsList(script);
  const pictures = [];
  let elapsed = 0;

  (script.segments || []).forEach((seg, i) => {
    const shot = (seg.shots || [])[0] || {};
    if (!shot.share_with || !pictures.length) {
      pictures.push({
        number: pictures.length + 1,
        key: `${seg.segment_id}_${shot.shot_id}`,
        firstLine: i + 1,
        lastLine: i + 1,
        startsAt: elapsed,
        seconds: secs[i] || 0,
        narration: [seg.narration || ""]
      });
    } else {
      const p = pictures[pictures.length - 1];
      p.lastLine = i + 1;
      p.seconds += secs[i] || 0;
      p.narration.push(seg.narration || "");
    }
    elapsed += secs[i] || 0;
  });
  return pictures;
}

function mmss(t) {
  const whole = Math.max(0, Math.round(t));
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

/** Narration is the user's own text and goes into markup; it does not get a vote. */
function escapeHtml(text) {
  return String(text == null ? "" : text)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function toggleSplitPanel(panelId) {
  const el = document.getElementById(panelId);
  if (!el) return;
  const opening = el.classList.contains("hidden");
  // One open at a time, or a long board becomes a wall of choices.
  document.querySelectorAll(".splitpanel").forEach(p => p.classList.add("hidden"));
  if (opening) el.classList.remove("hidden");
}

/**
 * Move one boundary, keeping every other picture exactly as it is.
 *
 * The board is re-planned against the library afterwards because the picture
 * that changed needs an image and a description; the ones that did not change
 * keep the description they already had.
 */
async function applyBoundaryChange(call, line, busyLabel) {
  if (isWebMode || !currentScriptData) return;
  setBoardBusy(true, busyLabel);
  try {
    const res = await window.pywebview.api[call](currentScriptData, line);
    if (!res || !res.success) {
      alert((res && res.error) || "Could not change that boundary.");
      return;
    }
    currentScriptData = res.script_data;
    if (currentScriptPath) {
      await window.pywebview.api.save_edited_script(currentScriptPath, currentScriptData);
    }
    await refreshStoryboardCoverage();
  } catch (e) {
    alert("Could not change that boundary: " + e.message);
  } finally {
    setBoardBusy(false);
  }
}

function splitPictureAt(line) {
  return applyBoundaryChange("split_picture_at", line,
    `Starting a new picture at line ${line}…`);
}

function mergePictureAt(line) {
  return applyBoundaryChange("merge_picture_at", line,
    "Joining this picture to the one before it…");
}

function renderStoryboardScreen() {
  const listContainer = document.getElementById("storyboard-list");
  if (!listContainer) return;

  if (!currentScriptData || !currentScriptData.segments) {
    listContainer.innerHTML = `
      <div class="card" style="text-align:center; padding:30px">
        <p class="sub">No storyboard loaded yet. Paste a script on the <b>Script</b> screen and click <b>Plan storyboard</b>.</p>
      </div>
    `;
    return;
  }

  let matchedCnt = 0;
  let weakCnt = 0;
  let gapCnt = 0;
  let totalShots = 0;

  const shotReports = coverageReport ? coverageReport.shot_reports : [];
  const reportMap = {};
  shotReports.forEach(r => {
    reportMap[`${r.segment_id}_${r.shot_id}`] = r;
    // Count pictures, not shots. Ask for 25 images across 44 segments and 19 of
    // those shots reuse another shot's image - tallying them said "44" beside a
    // box reading "How many images? 25", and every number on the board
    // disagreed with the one the user had just typed.
    if (r.share_with) return;
    // A pinned shot is one the user has already settled. It counts as covered;
    // counting it as a gap would nag about the very thing they just fixed.
    if (r.state === "matched" || r.state === "pinned") matchedCnt++;
    else if (r.state === "weak") weakCnt++;
    else gapCnt++;
    totalShots++;
  });

  document.getElementById("board-cnt-matched").textContent = matchedCnt;
  document.getElementById("board-cnt-weak").textContent = weakCnt;
  document.getElementById("board-cnt-gaps").textContent = gapCnt;
  document.getElementById("board-cnt-shots").textContent = totalShots || currentScriptData.segments.length;

  const estSecs = getScriptEstSeconds();
  const rMins = Math.floor(estSecs / 60);
  const rSecs = Math.floor(estSecs % 60);
  const rtEl = document.getElementById("board-cnt-runtime");
  if (rtEl) rtEl.textContent = `${rMins}:${String(rSecs).padStart(2, "0")}`;

  syncPlanModeFromScript();
  syncImageCountControl();

  updateTimingPill();

  const pictures = picturesFromScript(currentScriptData);
  const pictureByKey = {};
  pictures.forEach(pic => { pictureByKey[pic.key] = pic; });

  let html = "";

  currentScriptData.segments.forEach(seg => {
    const segId = seg.segment_id;
    const narration = seg.narration;
    const shots = seg.shots || [{ shot_id: `${segId}a`, query: seg.b_roll_keyword || "visual" }];

    shots.forEach(shot => {
      // A shot pointing at another shot's image is not a picture of its own. It
      // used to draw its own row, repeating a picture already shown above.
      if (shot.share_with) return;

      const shotId = shot.shot_id;
      const key = `${segId}_${shotId}`;
      const pic = pictureByKey[key];
      const rep = reportMap[key] || {
        state: "matched",
        best_score: 0.32,
        best_path: "library/images/sample.jpg",
        query: shot.query || "visual landscape",
        composed_prompt: "cinematic documentary shot"
      };

      const stateClass = rep.state === "weak" ? "weak" : rep.state === "gap" ? "gap" : "";
      const pillClass = rep.state === "weak" ? "p-warn" : rep.state === "gap" ? "p-gap" : "p-ok";
      const pillText = rep.state === "weak" ? "weak match"
        : rep.state === "gap" ? "gap"
        : rep.state === "pinned" ? "your choice"
        : "matched";

      // Thumb section
      let thumbHtml = "";
      if (rep.state === "gap" || !rep.best_path) {
        thumbHtml = `
          <div class="thumb empty">
            <span style="font-size:22px">□</span>
            <span>no match<br>best ${(rep.best_score || 0.19).toFixed(2)}</span>
          </div>
        `;
      } else {
        const imgUrl = rep.best_url || rep.best_path;
        thumbHtml = `
          <div class="thumb">
            <img src="${imgUrl}" alt="${shot.query}" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'200\\' height=\\'112\\' fill=\\'%2326313C\\'><text x=\\'50%\\' y=\\'50%\\' fill=\\'%2378848F\\' text-anchor=\\'middle\\'>image</text></svg>'"/>
            <span class="score">${(rep.best_score || 0.30).toFixed(2)}</span>
          </div>
        `;
      }

      // Alternatives strip for weak matches
      let altsHtml = "";
      if (rep.alternatives && rep.alternatives.length > 0 && rep.state !== "gap") {
        const altSource = (rep.alternative_urls && rep.alternative_urls.length)
          ? rep.alternative_urls
          : rep.alternatives.map(a => ({ url: a[0], path: a[0], score: a[1] }));
        const altImgs = altSource.slice(0, 3).map(alt => `
          <span class="altwrap" onclick="selectAlternative('${segId}', '${shotId}', '${alt.path}', '${alt.url}')">
            <img class="alt" src="${alt.url}" alt="alternative"/>
            <i>${(alt.score || 0.25).toFixed(2)}</i>
          </span>
        `).join("");

        altsHtml = `
          <div class="alts">
            <span class="lbl">Other options in your library &mdash; click one to use it</span>
            ${altImgs}
          </div>
        `;
      }

      // Moving one boundary by hand. Re-planning to fix a single picture costs
      // two model calls, rewrites every other picture, and throws away
      // descriptions that were already good.
      let boundaryActsHtml = "";
      let splitPanelHtml = "";
      if (pic) {
        const panelId = `split-${segId}-${shotId}`;
        // Line one already starts this picture; a new one can begin anywhere after it.
        const splitLines = pic.narration
          .map((text, i) => ({ line: pic.firstLine + i, text: text }))
          .slice(1);

        boundaryActsHtml = `
          ${pic.number > 1
            ? `<button type="button" onclick="mergePictureAt(${pic.firstLine})"
                 title="Fold this picture into picture ${pic.number - 1}">&uarr; Join to picture ${String(pic.number - 1).padStart(2, "0")}</button>`
            : ""}
          ${splitLines.length
            ? `<button type="button" onclick="toggleSplitPanel('${panelId}')">Split into two&hellip;</button>`
            : ""}
        `;

        if (splitLines.length) {
          splitPanelHtml = `
            <div class="splitpanel hidden" id="${panelId}">
              <span class="lbl">Start a new picture at&hellip;</span>
              ${splitLines.map(l => `
                <button type="button" class="splitline" onclick="splitPictureAt(${l.line})">
                  <b>line ${l.line}</b> ${escapeHtml(l.text).slice(0, 110)}
                </button>`).join("")}
            </div>
          `;
        }
      }

      // A pin that no longer resolves must say so, not quietly revert to a search result.
      const pinWarnHtml = rep.pin_missing
        ? `<p class="q" style="color:var(--warn)">the image you chose is missing from the library — showing a search result instead</p>`
        : "";

      // Prompt box for gaps
      let gapBoxHtml = "";
      if (rep.state === "gap") {
        gapBoxHtml = `
          <div class="promptbox">
            <span class="lbl">Generate this &mdash; prompt ready</span>
            <code>${rep.composed_prompt || 'cinematic shot'}</code>
            <div style="display:flex; gap:7px; flex-wrap:wrap">
              <button type="button" onclick="copyPromptFor('${segId}', '${shotId}')">Copy prompt</button>
            </div>
            <div class="drop">Generate it anywhere, then bring it back with <b>Replace &rarr; Use your own image</b>.</div>
          </div>
        `;
      }

      html += `
        <div class="seg ${stateClass}">
          ${thumbHtml}
          <div class="body">
            <div class="head">
              <span class="sid">${pic ? `PICTURE ${String(pic.number).padStart(2, "0")}` : `SEGMENT ${segId} &middot; SHOT ${shotId}`}</span>
              ${pic ? `<span class="mono pic-timing">${mmss(pic.startsAt)} &rarr; ${mmss(pic.startsAt + pic.seconds)}
                 &middot; holds ${pic.seconds.toFixed(1)}s
                 &middot; ${pic.firstLine === pic.lastLine
                     ? `script line ${pic.firstLine}`
                     : `script lines ${pic.firstLine}-${pic.lastLine}`}</span>` : ""}
              <span class="pill ${pillClass}">${pillText}</span>
            </div>
            <p class="narr">&ldquo;${pic ? pic.narration.join(" ") : narration}&rdquo;</p>
            <p class="q">query: ${rep.query || shot.query}</p>
            ${pinWarnHtml}
            ${altsHtml}
            ${gapBoxHtml}
            <div class="acts">
              <button type="button" onclick="openReplaceModal('${segId}', '${shotId}')">Replace</button>
              ${boundaryActsHtml}
            </div>
            ${splitPanelHtml}
          </div>
        </div>
      `;
    });
  });

  listContainer.innerHTML = html;
}

// Slider position -> seconds a single picture stays on screen. This MUST ascend
// with the slider position: the label next to it reads "~Ns per shot", and a
// slider that moves right while its own number falls reads as broken. It used to
// descend, so dragging right to hold each picture longer cut the film faster
// instead — the opposite of what the label promised.
const RHYTHM_SECONDS = { "1": 3, "2": 5, "3": 7, "4": 9, "5": 12 };

/** Nearest slider position for a seconds value, so a saved preference restores. */
function rhythmPositionFor(secs) {
  const want = Number(secs);
  if (!Number.isFinite(want)) return "3";
  return Object.keys(RHYTHM_SECONDS).reduce((best, pos) =>
    Math.abs(RHYTHM_SECONDS[pos] - want) < Math.abs(RHYTHM_SECONDS[best] - want) ? pos : best, "3");
}

// ── Image Budget & Shot Rhythm Control ───────────────────────────────────────

function getScriptWordCount() {
  if (!currentScriptData || !currentScriptData.segments) return 0;
  return currentScriptData.segments.reduce((acc, s) => {
    const text = (s.narration || "").trim();
    return acc + (text ? text.split(/\s+/).filter(Boolean).length : 0);
  }, 0);
}

function getScriptEstSeconds() {
  const words = getScriptWordCount();
  return words > 0 ? (words / 2.6) : 0.0;
}

function countScriptImages(scriptData) {
  if (!scriptData || !scriptData.segments) return 0;
  let cnt = 0;
  scriptData.segments.forEach(seg => {
    const shots = seg.shots || [];
    if (shots.length) {
      cnt += shots.filter(s => !s.share_with).length;
    } else {
      cnt += 1;
    }
  });
  return cnt;
}

function updateImageCountHint(val) {
  const hintEl = document.getElementById("image-count-hint");
  if (!hintEl) return;
  const words = getScriptWordCount();
  const estSecs = getScriptEstSeconds();
  const mins = (estSecs / 60).toFixed(1);
  const count = Math.max(1, Math.min(500, parseInt(val, 10) || 1));
  const secsPerImg = estSecs > 0 ? Math.round(estSecs / count) : 25;
  hintEl.textContent = `~${words.toLocaleString()} words · ${mins} min · about ${secsPerImg}s per image`;
}

/**
 * Show the mode the saved plan was actually made in.
 *
 * `planMode` is a page variable that starts at "auto" on every load, while the
 * plan on disk does not. A film pinned to exactly 30 pictures came back reading
 * "Auto", and pressing Re-plan then quietly changed what had been asked for.
 */
function syncPlanModeFromScript() {
  const project = (currentScriptData && currentScriptData.project) || {};
  if (project.plan_mode !== "auto" && project.plan_mode !== "exact") return;

  setPlanMode(project.plan_mode);

  // The count box is left to `syncImageCountControl`, which fills it from the
  // pictures the film has right now. Restoring the number that was asked for
  // would show 15 on a film that has 16 after a split by hand.
  const lo = document.getElementById("plan-hold-min");
  const hi = document.getElementById("plan-hold-max");
  if (lo && project.plan_min_hold) lo.value = project.plan_min_hold;
  if (hi && project.plan_max_hold) hi.value = project.plan_max_hold;
}

function syncImageCountControl() {
  const input = document.getElementById("image-count");
  if (!input) return;
  const estSecs = getScriptEstSeconds();
  const currentImages = countScriptImages(currentScriptData);
  const suggested = Math.max(1, Math.round(estSecs / 25)) || 1;
  const val = currentImages || suggested;
  input.value = val;
  updateImageCountHint(val);

  const slider = document.getElementById("shot-rhythm-slider");
  const lbl = document.getElementById("rhythm-label");
  if (slider && estSecs > 0) {
    const secsPerImg = estSecs / val;
    const pos = rhythmPositionFor(secsPerImg);
    slider.value = pos;
    if (lbl) lbl.textContent = `~${RHYTHM_SECONDS[pos] || 7}s per shot`;
  }
}

function onImageCountInput(val) {
  updateImageCountHint(val);
  const estSecs = getScriptEstSeconds();
  const count = Math.max(1, Math.min(500, parseInt(val, 10) || 1));
  const slider = document.getElementById("shot-rhythm-slider");
  const lbl = document.getElementById("rhythm-label");
  if (slider && estSecs > 0) {
    const secsPerImg = estSecs / count;
    const pos = rhythmPositionFor(secsPerImg);
    slider.value = pos;
    if (lbl) lbl.textContent = `~${RHYTHM_SECONDS[pos] || 7}s per shot`;
  }
}

// The count box and the rhythm slider used to re-cut the film themselves, by
// clock, through `set_image_count` -> `plan_image_budget`. Both are gone.
//
// The box is read by `replanPictures`, and clicking "Re-plan pictures" blurs it,
// so one gesture started two planners on the same script: the clock cut (fast,
// local) and the model plan (slow, two model calls). Both wrote `currentScriptData`
// and both saved, so whichever finished last won. On the owner's film the clock
// cut won: all 347 shots carried `run_index`, which only `plan_image_budget`
// writes, the 15 runs came out near-uniform (19,18,19,21,22,24,22,25,25,23,32,
// 26,27,25,19), and 26 of the model's 30 descriptions were left stranded on
// shots now carrying `share_with`, where no prompt can ever reach them.
//
// A picture boundary is now only ever moved by the model, through
// `plan_pictures_for_script`. Auto and Exact already cover what these offered.

/** Re-cut every segment into shots of roughly `secs`, then re-plan the board. */
async function applyShotRhythm(secs) {
  if (isWebMode || !currentScriptData) return;
  setBoardBusy(true, `Re-cutting into ~${secs}s shots…`);
  try {
    const res = await window.pywebview.api.set_shot_rhythm(currentScriptData, secs);
    if (!res.success) {
      alert("Could not change the shot rhythm: " + (res.error || "unknown error"));
      return;
    }
    currentScriptData = res.script_data;
    if (currentScriptPath) {
      await window.pywebview.api.save_edited_script(currentScriptPath, currentScriptData);
    }
    await refreshStoryboardCoverage();
  } catch (e) {
    alert("Could not change the shot rhythm: " + e.message);
  } finally {
    setBoardBusy(false);
  }
}
/* ── Picture planning ────────────────────────────────────────────────────────
   The old budget divided the runtime by a count and cut there, which put
   boundaries inside narration with nothing to photograph. These controls hand
   the whole script to a model and let it choose the boundaries instead. */
let planMode = "auto";

function setPlanMode(mode) {
  planMode = (mode === "exact") ? "exact" : "auto";
  const on = (id, yes) => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle("hidden", !yes);
  };
  const seg = (id, yes) => {
    const el = document.getElementById(id);
    if (el) el.classList.toggle("active", yes);
  };
  seg("plan-mode-auto", planMode === "auto");
  seg("plan-mode-exact", planMode === "exact");
  on("plan-hold-group", planMode === "auto");
  on("image-count-label", planMode === "exact");
  on("image-count", planMode === "exact");
  on("image-count-hint", planMode === "exact");
}

/** Ask the model where the pictures belong, then redraw the board. */
async function replanPictures() {
  if (isWebMode || !currentScriptData) return;

  const num = (id, fallback) => {
    const el = document.getElementById(id);
    const v = parseFloat(el && el.value);
    return isFinite(v) && v > 0 ? v : fallback;
  };

  const exact = planMode === "exact"
    ? Math.max(1, Math.min(500, Math.round(num("image-count", 1))))
    : null;
  const minHold = num("plan-hold-min", 8);
  const maxHold = num("plan-hold-max", 75);

  setBoardBusy(true, exact
    ? `Planning exactly ${exact} picture${exact === 1 ? "" : "s"}…`
    : "Letting the story decide how many pictures…");
  try {
    const res = await window.pywebview.api.plan_pictures_for_script(
      currentScriptData, exact, minHold, maxHold);
    if (!res.success) {
      alert("Could not plan the pictures: " + (res.error || "unknown error"));
      return;
    }
    currentScriptData = res.script_data;
    if (currentScriptPath) {
      await window.pywebview.api.save_edited_script(currentScriptPath, currentScriptData);
    }
    await refreshStoryboardCoverage();
  } catch (e) {
    alert("Could not plan the pictures: " + e.message);
  } finally {
    setBoardBusy(false);
  }
}
/** Does this script sit on measured audio, or on the word-count guess? */
function updateTimingPill() {
  const pill = document.getElementById("timing-pill");
  if (!pill) return;
  const segs = (currentScriptData && currentScriptData.segments) || [];
  const measured = segs.filter(sg => parseFloat(sg.narration_seconds) > 0).length;
  const all = segs.length > 0 && measured === segs.length;
  pill.classList.toggle("ok", all);
  pill.classList.toggle("warn", !all);
  pill.textContent = all
    ? "timings measured"
    : measured
      ? `${measured} of ${segs.length} measured`
      : "estimated from word count";
}

/* The app pushes one of these per segment while the narration is being timed. */
window.onTimingProgress = function(event) {
  if (event && event.finished) return;
  const total = (event && event.total) || 0;
  const done = (event && event.done) || 0;
  setBoardBusy(true, total
    ? `Timing narration… ${done} of ${total}`
    : "Timing narration…");
};

/** Render every line and measure it, so boundaries sit on real seconds. */
async function measureNarration() {
  if (isWebMode || !currentScriptData) return;
  const segs = currentScriptData.segments || [];
  if (!segs.length) return;

  setBoardBusy(true, `Timing narration… 0 of ${segs.length}`);
  try {
    const res = await window.pywebview.api.measure_narration_for_script(currentScriptData);
    if (!res.success) {
      alert("Could not measure the narration: " + (res.error || "unknown error"));
      return;
    }
    currentScriptData = res.script_data;
    if (currentScriptPath) {
      await window.pywebview.api.save_edited_script(currentScriptPath, currentScriptData);
    }
    updateTimingPill();
    await refreshStoryboardCoverage();
    if (res.failed) {
      alert(`Measured ${res.measured} of ${segs.length} lines. `
        + `${res.failed} could not be recorded or read, and keep their word-count estimate.`);
    }
  } catch (e) {
    alert("Could not measure the narration: " + e.message);
  } finally {
    setBoardBusy(false);
  }
}
window.measureNarration = measureNarration;
window.updateTimingPill = updateTimingPill;

window.setPlanMode = setPlanMode;
window.replanPictures = replanPictures;
window.splitPictureAt = splitPictureAt;
window.mergePictureAt = mergePictureAt;
window.toggleSplitPanel = toggleSplitPanel;

window.applyShotRhythm = applyShotRhythm;
window.onImageCountInput = onImageCountInput;

// ── Timeline ─────────────────────────────────────────────────────────────────
//
// The film laid out against the clock, which is the one view the Storyboard
// cannot give: a list of rows says a picture holds 75.8s, but only a timeline
// shows that it is a fifth of the film and the four beside it are twenty
// seconds each. Built from the plan already in memory - no render, no second
// pass over the library - so it costs nothing to look at.

let tlZoom = 8;          // pixels per second
let tlPlayhead = 0;      // seconds
let tlSelected = 1;      // picture number

/** Tick spacing that keeps roughly 90px between labels at the current zoom. */
function tlTickInterval() {
  const wanted = 90 / tlZoom;
  return [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900]
    .find(step => step >= wanted) || 1800;
}

function tlClock(t) {
  const whole = Math.max(0, t);
  const m = Math.floor(whole / 60);
  const s = whole % 60;
  return `${String(m).padStart(2, "0")}:${s.toFixed(1).padStart(4, "0")}`;
}

function tlPictures() {
  if (!currentScriptData || !currentScriptData.segments) return [];
  return picturesFromScript(currentScriptData);
}

/** The image the board settled on for a picture, if it has one yet. */
function tlImageFor(pic) {
  const reports = (coverageReport && coverageReport.shot_reports) || [];
  const rep = reports.find(r => `${r.segment_id}_${r.shot_id}` === pic.key);
  return rep ? (rep.best_url || "") : "";
}

function tlStateFor(pic) {
  const reports = (coverageReport && coverageReport.shot_reports) || [];
  const rep = reports.find(r => `${r.segment_id}_${r.shot_id}` === pic.key);
  return rep ? rep.state : "";
}

let tlAnimFrameId = null;
let tlCurrentFramePic = null;
let tlAudioPreparing = false;

function timelineAudioEl() {
  return document.getElementById("tl-audio");
}

function timelineMusicAudioEl() {
  return document.getElementById("tl-music-audio");
}

let tlMusicPreparing = false;
async function prepareTimelineMusic() {
  const musicAudio = timelineMusicAudioEl();
  if (!musicAudio || !currentScriptData || !currentScriptData.project) return;
  const bgMusic = currentScriptData.project.background_music;
  if (!bgMusic) {
    if (musicAudio.src) {
      musicAudio.pause();
      musicAudio.removeAttribute("src");
      musicAudio.removeAttribute("data-music");
      musicAudio.removeAttribute("data-project");
    }
    return;
  }
  const projectTitle = currentScriptData.project.title || "Untitled Project";
  if (musicAudio.dataset.project === projectTitle && musicAudio.dataset.music === bgMusic && musicAudio.src) {
    const db = currentScriptData.project.music_volume_db !== undefined ? currentScriptData.project.music_volume_db : -20;
    musicAudio.volume = Math.min(1.0, Math.max(0.0, Math.pow(10, db / 20)));
    return;
  }
  if (tlMusicPreparing) return;
  tlMusicPreparing = true;
  try {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.prepare_timeline_music) {
      const projectDir = currentScriptPath ? currentScriptPath.replace(/[\\/][^\\/]*$/, "") : "";
      const res = await window.pywebview.api.prepare_timeline_music(currentScriptData, projectDir);
      if (res && res.ok && res.src) {
        musicAudio.src = res.src;
        musicAudio.dataset.project = projectTitle;
        musicAudio.dataset.music = bgMusic;
        const db = currentScriptData.project.music_volume_db !== undefined ? currentScriptData.project.music_volume_db : -20;
        musicAudio.volume = Math.min(1.0, Math.max(0.0, Math.pow(10, db / 20)));
        musicAudio.load();
      }
    }
  } catch (err) {
    console.error("Error preparing timeline music:", err);
  } finally {
    tlMusicPreparing = false;
  }
}

function initTimelineAudio() {
  const audio = timelineAudioEl();
  const musicAudio = timelineMusicAudioEl();
  if (musicAudio) {
    musicAudio.loop = true;
  }
  if (!audio || audio.dataset.initialized) return;
  audio.dataset.initialized = "true";

  audio.addEventListener("play", () => {
    const btn = document.getElementById("btn-tl-play");
    if (btn) {
      btn.innerHTML = "&#10074;&#10074;";
      btn.setAttribute("aria-label", "Pause");
      btn.title = "Pause";
    }
    const mAudio = timelineMusicAudioEl();
    if (mAudio && mAudio.src) {
      if (mAudio.duration) {
        mAudio.currentTime = audio.currentTime % mAudio.duration;
      }
      mAudio.play().catch(() => {});
    }
    if (tlAnimFrameId) cancelAnimationFrame(tlAnimFrameId);
    tlAnimFrameId = requestAnimationFrame(tlAnimLoop);
  });

  audio.addEventListener("pause", () => {
    const btn = document.getElementById("btn-tl-play");
    if (btn) {
      btn.innerHTML = "&#9654;";
      btn.setAttribute("aria-label", "Play");
      btn.title = "Play";
    }
    const mAudio = timelineMusicAudioEl();
    if (mAudio && !mAudio.paused) {
      mAudio.pause();
    }
    if (tlAnimFrameId) {
      cancelAnimationFrame(tlAnimFrameId);
      tlAnimFrameId = null;
    }
  });

  audio.addEventListener("ended", () => {
    const btn = document.getElementById("btn-tl-play");
    if (btn) {
      btn.innerHTML = "&#9654;";
      btn.setAttribute("aria-label", "Play");
      btn.title = "Play";
    }
    const mAudio = timelineMusicAudioEl();
    if (mAudio && !mAudio.paused) {
      mAudio.pause();
    }
    if (tlAnimFrameId) {
      cancelAnimationFrame(tlAnimFrameId);
      tlAnimFrameId = null;
    }
    const secs = segmentSecondsList(currentScriptData);
    const total = secs.reduce((a, b) => a + b, 0);
    timelineSeek(total, { fromAudio: true });
  });
}

function tlAnimLoop() {
  const audio = timelineAudioEl();
  if (!audio || audio.paused) {
    tlAnimFrameId = null;
    return;
  }
  timelineSeek(audio.currentTime, { fromAudio: true });
  tlAnimFrameId = requestAnimationFrame(tlAnimLoop);
}

function timelinePauseAudio() {
  const audio = timelineAudioEl();
  if (audio && !audio.paused) {
    audio.pause();
  }
  const mAudio = timelineMusicAudioEl();
  if (mAudio && !mAudio.paused) {
    mAudio.pause();
  }
  if (tlAnimFrameId) {
    cancelAnimationFrame(tlAnimFrameId);
    tlAnimFrameId = null;
  }
}

async function timelineTogglePlay() {
  const audio = timelineAudioEl();
  if (!audio) return;

  if (!audio.paused) {
    audio.pause();
    return;
  }

  const secs = segmentSecondsList(currentScriptData);
  const total = secs.reduce((a, b) => a + b, 0);
  if (tlPlayhead >= total - 0.05) {
    timelineSeek(0);
  }

  // Ensure music track is loaded if configured
  if (currentScriptData && currentScriptData.project && currentScriptData.project.background_music) {
    await prepareTimelineMusic();
  }

  const projectTitle = (currentScriptData && currentScriptData.project && currentScriptData.project.title) || "Untitled Project";
  if (!audio.src || audio.dataset.project !== projectTitle) {
    if (tlAudioPreparing) return;
    tlAudioPreparing = true;
    const playBtn = document.getElementById("btn-tl-play");
    const statusEl = document.getElementById("tl-status");
    const origStatus = statusEl ? statusEl.textContent : "";
    if (playBtn) playBtn.disabled = true;
    if (statusEl) statusEl.textContent = "Building timeline narration audio...";

    try {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.prepare_timeline_audio) {
        // The narration track belongs beside the film it was made from, not in a
        // hashed cache folder. currentScriptPath is the project's script.json.
        const projectDir = currentScriptPath
          ? currentScriptPath.replace(/[\\/][^\\/]*$/, "")
          : "";
        const res = await window.pywebview.api.prepare_timeline_audio(currentScriptData, projectDir);
        if (!res || !res.ok || !res.src) {
          alert("Could not prepare timeline audio: " + ((res && res.error) || "unknown error"));
          if (statusEl) statusEl.textContent = origStatus;
          return;
        }
        audio.src = res.src;
        audio.dataset.project = projectTitle;
        audio.load();
      } else {
        alert("Audio playback requires backend connection.");
        if (statusEl) statusEl.textContent = origStatus;
        return;
      }
    } catch (err) {
      alert("Error preparing timeline audio: " + err);
      if (statusEl) statusEl.textContent = origStatus;
      return;
    } finally {
      tlAudioPreparing = false;
      if (playBtn) playBtn.disabled = false;
      if (statusEl) statusEl.textContent = origStatus;
    }
  }

  audio.currentTime = tlPlayhead;
  try {
    await audio.play();
  } catch (err) {
    console.error("Audio playback error:", err);
  }
}

function renderTimelineScreen() {
  const lanes = document.getElementById("tl-lanes");
  if (!lanes) return;

  const pics = tlPictures();
  const statusEl = document.getElementById("tl-status");
  const ruler = document.getElementById("tl-ruler");
  const laneP = document.getElementById("tl-lane-pictures");
  const laneN = document.getElementById("tl-lane-narration");
  const laneM = document.getElementById("tl-lane-music");
  const laneS = document.getElementById("tl-lane-sfx");
  const laneC = document.getElementById("tl-lane-captions");

  initTimelineAudio();
  tlCurrentFramePic = null;

  if (!pics.length) {
    if (statusEl) statusEl.textContent = "no film loaded";
    ruler.innerHTML = "";
    laneP.innerHTML = `<p class="sub tl-empty">Plan a storyboard first. The Timeline shows the plan you already have.</p>`;
    laneN.innerHTML = "";
    if (laneM) laneM.innerHTML = "";
    if (laneS) laneS.innerHTML = "";
    laneC.innerHTML = "";
    const playBtn = document.getElementById("btn-tl-play");
    if (playBtn) playBtn.disabled = true;
    return;
  }

  const segs = currentScriptData.segments || [];
  const secs = segmentSecondsList(currentScriptData);
  const total = secs.reduce((a, b) => a + b, 0);
  const measured = segs.filter(s => Boolean(s.narration_audio && parseFloat(s.narration_seconds) > 0)).length;
  const width = Math.max(320, total * tlZoom);

  const playBtn = document.getElementById("btn-tl-play");
  if (measured === 0) {
    if (playBtn) {
      playBtn.disabled = true;
      playBtn.title = "Narration has not been recorded yet. Measure narration on the Storyboard first.";
    }
    if (statusEl) {
      statusEl.textContent = "Narration not recorded yet — Measure narration on the Storyboard first";
      statusEl.classList.add("warn-text");
    }
  } else {
    if (playBtn) {
      playBtn.disabled = false;
      playBtn.title = "Play / pause";
    }
    if (statusEl) {
      statusEl.textContent =
        `${pics.length} picture${pics.length === 1 ? "" : "s"} · ${tlClock(total)} · ` +
        (measured === segs.length ? "all timings measured" : `${measured} of ${segs.length} measured (${segs.length - measured} missing)`);
      statusEl.classList.toggle("warn-text", measured !== segs.length);
    }
  }

  lanes.style.width = `${width}px`;

  // Ruler
  const step = tlTickInterval();
  let ticks = "";
  for (let t = 0; t <= total; t += step) {
    ticks += `<span class="tl-tick" style="left:${(t * tlZoom).toFixed(1)}px">
                <i></i><b class="mono">${mmss(t)}</b></span>`;
  }
  ruler.innerHTML = ticks;

  // Pictures — one clip per picture, width is the time it holds
  laneP.innerHTML = pics.map((pic, idx) => {
    const w = Math.max(2, pic.seconds * tlZoom);
    const img = tlImageFor(pic);
    const state = tlStateFor(pic);
    const narrow = w < 78;
    // role="slider" promises a range, so state the range it can actually reach:
    // one line past the picture before, one line short of the picture after.
    const hMin = idx > 0 ? pics[idx - 1].firstLine + 1 : 1;
    const hMax = idx + 1 < pics.length ? pics[idx + 1].firstLine - 1 : segs.length;
    const handleHtml = idx > 0
      ? `<div class="tl-clip-handle"
              tabindex="0"
              role="slider"
              aria-label="Start of picture ${String(pic.number).padStart(2, "0")}, line ${pic.firstLine}"
              aria-valuenow="${pic.firstLine}"
              aria-valuemin="${hMin}"
              aria-valuemax="${hMax}"
              data-pic="${pic.number}"
              data-from-line="${pic.firstLine}"
              onpointerdown="timelineHandlePointerDown(event, ${pic.number})"
              onpointermove="timelineHandlePointerMove(event)"
              onpointerup="timelineHandlePointerUp(event)"
              onpointercancel="timelineHandleCancel(event)"
              onkeydown="timelineHandleKeyDown(event, ${pic.number})">
           <span class="tl-handle-bar"></span>
         </div>`
      : "";
    return `
      <div class="tl-clip ${state === "gap" ? "gap" : state === "weak" ? "weak" : ""} ${tlSelected === pic.number ? "sel" : ""}"
           id="tl-clip-${pic.number}"
           data-pic="${pic.number}"
           style="left:${(pic.startsAt * tlZoom).toFixed(1)}px; width:${w.toFixed(1)}px"
           onclick="selectTimelinePicture(${pic.number})"
           title="Picture ${pic.number} — ${pic.seconds.toFixed(1)}s — script lines ${pic.firstLine}-${pic.lastLine}">
        ${handleHtml}
        <span class="tl-clip-head mono">
          <b>${narrow ? pic.number : `Pic ${String(pic.number).padStart(2, "0")}`}</b>
          ${narrow ? "" : `<i>${pic.seconds.toFixed(1)}s</i>`}
        </span>
        ${img ? `<img src="${img}" alt=""/>` : `<span class="tl-clip-empty">no image</span>`}
      </div>`;
  }).join("");

  // Narration and captions — one block per script line, so a picture's stretch
  // is visible against the lines it actually has to carry.
  let at = 0;
  let nHtml = "";
  let cHtml = "";
  segs.forEach((seg, i) => {
    const w = Math.max(1, (secs[i] || 0) * tlZoom);
    const isMeasured = parseFloat(seg.narration_seconds) > 0;
    const text = (seg.narration || "").trim();
    nHtml += `<div class="tl-narr ${isMeasured ? "measured" : ""}"
                   style="left:${(at * tlZoom).toFixed(1)}px; width:${(w - 1).toFixed(1)}px"
                   title="line ${i + 1} · ${(secs[i] || 0).toFixed(1)}s${isMeasured ? " (measured)" : " (estimated)"}"></div>`;
    if (w > 46) {
      cHtml += `<div class="tl-cap" style="left:${(at * tlZoom).toFixed(1)}px; width:${(w - 3).toFixed(1)}px"
                     title="${escapeHtml(text)}">${escapeHtml(text)}</div>`;
    }
    at += secs[i] || 0;
  });
  laneN.innerHTML = nHtml;

  // Music — one block across the whole film
  if (laneM) {
    const bgMusic = currentScriptData?.project?.background_music;
    if (bgMusic) {
      const fname = bgMusic.split(/[\\/]/).pop();
      const volDb = currentScriptData.project.music_volume_db !== undefined ? currentScriptData.project.music_volume_db : -20;
      const fadeIn = currentScriptData.project.music_fade_in || 0;
      const fadeOut = currentScriptData.project.music_fade_out || 0;
      const fades = (fadeIn || fadeOut) ? ` · in ${fadeIn}s, out ${fadeOut}s` : "";
      const isSel = tlSelectedType === "music";
      laneM.innerHTML = `
        <div class="tl-music-block ${isSel ? "sel" : ""}"
             onclick="selectTimelineMusic()"
             style="left: 0px; width: ${(total * tlZoom).toFixed(1)}px;"
             title="${escapeHtml(fname)} (${volDb} dB${fades})">
          <span>&#9835; <b>${escapeHtml(fname)}</b> <i style="color:var(--ink-3); margin-left:6px">${volDb} dB${fades}</i></span>
        </div>
      `;
    } else {
      laneM.innerHTML = `
        <div class="tl-music-empty" onclick="timelineAddMusic()" title="Click to add background music">
          <span>+ Add background music</span>
        </div>
      `;
    }
  }

  // Sound effects — placed at specific offsets within segments
  if (laneS) {
    let sfxHtml = "";
    let sfxCount = 0;
    segs.forEach((seg, segIdx) => {
      const list = seg.sfx || [];
      list.forEach((sfx, sfxIdx) => {
        sfxCount++;
        const t = sfxToFilmTime(segIdx, sfx.offset_ms);
        const isSel = tlSelectedType === "sfx" && tlSelectedSfx && tlSelectedSfx.segIndex === segIdx && tlSelectedSfx.sfxIndex === sfxIdx;
        const x = (t * tlZoom).toFixed(1);
        sfxHtml += `
          <div class="tl-sfx-chip ${isSel ? "sel" : ""}"
               id="tl-sfx-${segIdx}-${sfxIdx}"
               data-seg="${segIdx}"
               data-sfx="${sfxIdx}"
               style="left: ${x}px;"
               onclick="selectTimelineSfx(${segIdx}, ${sfxIdx}, event)"
               onpointerdown="timelineSfxPointerDown(event, ${segIdx}, ${sfxIdx})"
               title="${escapeHtml(sfx.name)} · ${tlClock(t)} (line ${segIdx + 1} + ${sfx.offset_ms}ms)">
            <span>&#9889; ${escapeHtml(sfx.name)}</span>
          </div>
        `;
      });
    });
    if (sfxCount === 0) {
      laneS.innerHTML = `
        <div class="tl-sfx-empty" onclick="openAddSfxMenu()" title="Click to add sound effect at playhead">
          <span>+ Add sound effect at playhead (${tlClock(tlPlayhead)})</span>
        </div>
      `;
    } else {
      laneS.innerHTML = sfxHtml;
    }
  }

  // An empty lane reads as broken rather than as "too small to letter".
  laneC.innerHTML = cHtml ||
    `<span class="tl-cap-hint mono">zoom in to read the narration line by line</span>`;

  timelineSeek(Math.min(tlPlayhead, total), { keepSelection: true });
}

function setTimelineZoom(value) {
  tlZoom = Math.max(1, Math.min(60, parseFloat(value) || 8));
  renderTimelineScreen();
}

/** Move the playhead, and show whichever picture is on screen at that moment. */
function timelineSeek(seconds, opts) {
  const pics = tlPictures();
  if (!pics.length) return;
  const secs = segmentSecondsList(currentScriptData);
  const total = secs.reduce((a, b) => a + b, 0);
  tlPlayhead = Math.max(0, Math.min(total, seconds));

  const audio = timelineAudioEl();
  if (audio && (!opts || !opts.fromAudio)) {
    if (Math.abs(audio.currentTime - tlPlayhead) > 0.05) {
      audio.currentTime = tlPlayhead;
    }
  }

  const mAudio = timelineMusicAudioEl();
  if (mAudio && mAudio.src && mAudio.duration && (!opts || !opts.fromAudio)) {
    mAudio.currentTime = tlPlayhead % mAudio.duration;
  }

  const x = tlPlayhead * tlZoom;
  const head = document.getElementById("tl-playhead");
  if (head) head.style.left = `${x.toFixed(1)}px`;

  // Follow the playhead. Stepping to picture 12 of an eighteen-minute film put
  // it 9,000px along a lane 790px wide, so the timeline appeared not to respond.
  const scroll = document.getElementById("tl-scroll");
  if (scroll) {
    const view = scroll.clientWidth;
    if (x < scroll.scrollLeft + 40 || x > scroll.scrollLeft + view - 40) {
      scroll.scrollLeft = Math.max(0, x - view * 0.35);
    }
  }

  const clock = document.getElementById("tl-clock");
  if (clock) clock.textContent = `${tlClock(tlPlayhead)} / ${tlClock(total)}`;

  const at = pics.find(p => tlPlayhead >= p.startsAt && tlPlayhead < p.startsAt + p.seconds)
             || pics[pics.length - 1];
  if (at) {
    if (at.number !== tlCurrentFramePic) {
      tlCurrentFramePic = at.number;
      const frame = document.getElementById("tl-frame");
      if (frame) {
        const img = tlImageFor(at);
        frame.innerHTML = img
          ? `<img src="${img}" alt="Picture ${at.number}"/>`
          : `<p class="sub">Picture ${at.number} has no image yet. The Storyboard has its prompt.</p>`;
      }
      if (!(opts && opts.keepSelection && tlSelected !== at.number)) {
        selectTimelinePicture(at.number, { silent: true });
      }
    }
  }
  if (opts && opts.keepSelection) drawTimelineInspector(tlSelected);
}

function timelineNudge(delta) {
  timelineSeek(tlPlayhead + delta);
}

function timelineSeekPicture(direction) {
  const pics = tlPictures();
  if (!pics.length) return;
  const here = pics.findIndex(p => p.number === tlSelected);
  const next = pics[Math.max(0, Math.min(pics.length - 1, here + direction))];
  if (next) timelineSeek(next.startsAt + 0.01);
}

let tlSelectedType = "picture";
let tlSelectedSfx = null;

function selectTimelinePicture(number, opts) {
  tlSelectedType = "picture";
  tlSelectedSfx = null;
  tlSelected = number;
  document.querySelectorAll("#tl-lane-pictures .tl-clip").forEach((el, i) => {
    el.classList.toggle("sel", i + 1 === number);
  });
  document.querySelectorAll("#tl-lane-music .tl-music-block").forEach(el => el.classList.remove("sel"));
  document.querySelectorAll("#tl-lane-sfx .tl-sfx-chip").forEach(el => el.classList.remove("sel"));
  drawTimelineInspector(number);
  if (!(opts && opts.silent)) {
    const pic = tlPictures().find(p => p.number === number);
    if (pic) timelineSeek(pic.startsAt + 0.01, { keepSelection: true });
  }
}

/** Which script line is on screen at a moment, 1-based. */
function tlLineAt(seconds) {
  const secs = segmentSecondsList(currentScriptData);
  let at = 0;
  for (let i = 0; i < secs.length; i++) {
    at += secs[i] || 0;
    if (seconds < at) return i + 1;
  }
  return secs.length;
}

/** Spoken seconds elapsed before a script line starts, 1-based. */
function tlLineStartTime(lineNumber) {
  const secs = segmentSecondsList(currentScriptData);
  let at = 0;
  for (let i = 0; i < lineNumber - 1 && i < secs.length; i++) {
    at += secs[i] || 0;
  }
  return at;
}

/** Convert film playhead time in seconds to the owning segment index, segmentId, and offset_ms */
function filmTimeToSfx(seconds, script) {
  script = script || currentScriptData;
  const rawLine = tlLineAt(seconds);
  const segs = (script && script.segments) || [];
  const clampedLine = Math.max(1, Math.min(rawLine, segs.length || 1));
  const segIndex = clampedLine - 1;
  const seg = segs[segIndex] || {};
  const lineStart = tlLineStartTime(clampedLine);
  const offsetSeconds = Math.max(0, seconds - lineStart);
  const offsetMs = Math.round(offsetSeconds * 1000);
  return {
    segmentIndex: segIndex,
    segmentId: seg.segment_id !== undefined ? seg.segment_id : (segIndex + 1),
    offset_ms: offsetMs
  };
}

/** Convert segment index or id and offset_ms to absolute film time in seconds */
function sfxToFilmTime(segIndexOrId, offsetMs, script) {
  script = script || currentScriptData;
  const segs = (script && script.segments) || [];
  let idx = -1;
  if (typeof segIndexOrId === "number" && segIndexOrId >= 0 && segIndexOrId < segs.length) {
    idx = segIndexOrId;
  } else {
    idx = segs.findIndex(s => s.segment_id === segIndexOrId);
  }
  if (idx < 0) idx = 0;
  const lineStart = tlLineStartTime(idx + 1);
  return lineStart + ((offsetMs || 0) / 1000.0);
}

/** Move an effect from one segment to another based on dropped film time, preserving dropped film time */
function moveSfxEffect(fromSegIndex, sfxIndex, targetFilmSeconds, script) {
  script = script || currentScriptData;
  const segs = (script && script.segments) || [];
  const fromSeg = segs[fromSegIndex];
  if (!fromSeg || !fromSeg.sfx || !fromSeg.sfx[sfxIndex]) return null;

  const effect = fromSeg.sfx.splice(sfxIndex, 1)[0];
  const target = filmTimeToSfx(targetFilmSeconds, script);
  const toSeg = segs[target.segmentIndex];
  if (!toSeg.sfx) toSeg.sfx = [];
  effect.offset_ms = target.offset_ms;
  toSeg.sfx.push(effect);
  return {
    newSegIndex: target.segmentIndex,
    newSfxIndex: toSeg.sfx.length - 1,
    newOffsetMs: target.offset_ms
  };
}

let tlDragState = null;

function timelineHandlePointerDown(e, picNumber) {
  if (e.button !== 0 && e.pointerType === "mouse") return;
  e.stopPropagation();
  e.preventDefault();

  const handle = e.currentTarget;
  const pics = tlPictures();
  const pic = pics.find(p => p.number === picNumber);
  const prevPic = pics.find(p => p.number === picNumber - 1);
  const nextPic = pics.find(p => p.number === picNumber + 1);
  if (!pic || !prevPic) return;

  const totalLines = (currentScriptData.segments || []).length;
  const minLine = prevPic.firstLine + 1;
  const maxLine = nextPic ? nextPic.firstLine - 1 : totalLines;

  selectTimelinePicture(picNumber, { silent: true });

  try {
    handle.setPointerCapture(e.pointerId);
  } catch (_) {}

  tlDragState = {
    pointerId: e.pointerId,
    handle: handle,
    picNumber: picNumber,
    fromLine: pic.firstLine,
    currentLine: pic.firstLine,
    minLine: minLine,
    maxLine: maxLine,
    prevPicNumber: prevPic.number,
    prevStartsAt: prevPic.startsAt,
    picEndAt: pic.startsAt + pic.seconds,
    prevClip: document.getElementById("tl-clip-" + prevPic.number),
    currClip: document.getElementById("tl-clip-" + pic.number),
    cancelled: false
  };

  handle.classList.add("dragging");
}

function timelineHandlePointerMove(e) {
  if (!tlDragState || tlDragState.pointerId !== e.pointerId) return;
  e.preventDefault();
  e.stopPropagation();

  if (tlDragState.cancelled) return;

  const lanes = document.getElementById("tl-lanes");
  if (!lanes) return;
  const rect = lanes.getBoundingClientRect();
  const seconds = (e.clientX - rect.left) / tlZoom;

  const rawLine = tlLineAt(seconds);
  const clampedLine = Math.max(tlDragState.minLine, Math.min(rawLine, tlDragState.maxLine));

  if (clampedLine !== tlDragState.currentLine) {
    tlDragState.currentLine = clampedLine;

    // Fast CSS preview:
    const newStartsAt = tlLineStartTime(clampedLine);
    const prevSeconds = newStartsAt - tlDragState.prevStartsAt;
    const currSeconds = tlDragState.picEndAt - newStartsAt;

    if (tlDragState.prevClip) {
      tlDragState.prevClip.style.width = `${Math.max(2, prevSeconds * tlZoom).toFixed(1)}px`;
      const prevSub = tlDragState.prevClip.querySelector(".tl-clip-head i");
      if (prevSub) prevSub.textContent = `${prevSeconds.toFixed(1)}s`;
    }
    if (tlDragState.currClip) {
      tlDragState.currClip.style.left = `${(newStartsAt * tlZoom).toFixed(1)}px`;
      tlDragState.currClip.style.width = `${Math.max(2, currSeconds * tlZoom).toFixed(1)}px`;
      const currSub = tlDragState.currClip.querySelector(".tl-clip-head i");
      if (currSub) currSub.textContent = `${currSeconds.toFixed(1)}s`;
    }

    tlDragState.handle.setAttribute("aria-valuenow", clampedLine);
    tlDragState.handle.title = `Line ${clampedLine} · holds ${currSeconds.toFixed(1)}s`;
  }
}

async function timelineHandlePointerUp(e) {
  if (!tlDragState || tlDragState.pointerId !== e.pointerId) return;
  e.preventDefault();
  e.stopPropagation();

  const state = tlDragState;
  tlDragState = null;

  try {
    state.handle.releasePointerCapture(e.pointerId);
  } catch (_) {}
  state.handle.classList.remove("dragging");

  if (state.cancelled || state.currentLine === state.fromLine) {
    renderTimelineScreen();
    if (tlSelected) drawTimelineInspector(tlSelected);
    return;
  }

  await moveTimelinePictureBoundary(state.fromLine, state.currentLine, state.picNumber);
}

function timelineHandleCancel(e) {
  if (!tlDragState) return;
  tlDragState.cancelled = true;
  tlDragState.handle.classList.remove("dragging");
  try {
    tlDragState.handle.releasePointerCapture(tlDragState.pointerId);
  } catch (_) {}
  tlDragState = null;
  renderTimelineScreen();
  if (tlSelected) drawTimelineInspector(tlSelected);
}

async function timelineHandleKeyDown(e, picNumber) {
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  e.preventDefault();
  e.stopPropagation();

  const pics = tlPictures();
  const pic = pics.find(p => p.number === picNumber);
  const prevPic = pics.find(p => p.number === picNumber - 1);
  const nextPic = pics.find(p => p.number === picNumber + 1);
  if (!pic || !prevPic) return;

  const totalLines = (currentScriptData.segments || []).length;
  const minLine = prevPic.firstLine + 1;
  const maxLine = nextPic ? nextPic.firstLine - 1 : totalLines;

  const step = e.shiftKey ? 5 : 1;
  const dir = e.key === "ArrowLeft" ? -1 : 1;
  const targetLine = Math.max(minLine, Math.min(pic.firstLine + (dir * step), maxLine));

  if (targetLine === pic.firstLine) return;

  await moveTimelinePictureBoundary(pic.firstLine, targetLine, picNumber);
}

async function moveTimelinePictureBoundary(fromLine, toLine, focusPicNumber) {
  if (isWebMode || !currentScriptData) return;
  try {
    const res = await window.pywebview.api.move_picture_boundary_to(currentScriptData, fromLine, toLine);
    if (!res || !res.success) {
      alert((res && res.error) || "Could not move boundary.");
      renderTimelineScreen();
      return;
    }
    currentScriptData = res.script_data;
    if (currentScriptPath) {
      await window.pywebview.api.save_edited_script(currentScriptPath, currentScriptData);
    }
    // Update local coverage mapping for instant continuity
    if (coverageReport && coverageReport.shot_reports) {
      const oldRep = coverageReport.shot_reports.find(r => r.segment_id === fromLine);
      if (oldRep) {
        let newRep = coverageReport.shot_reports.find(r => r.segment_id === toLine);
        if (!newRep) {
          newRep = { ...oldRep, segment_id: toLine, shot_id: `${toLine}a` };
          coverageReport.shot_reports.push(newRep);
        } else {
          newRep.best_url = oldRep.best_url;
          newRep.best_path = oldRep.best_path;
          newRep.best_score = oldRep.best_score;
          newRep.state = oldRep.state;
        }
      }
    }
    renderTimelineScreen();
    if (tlSelected) {
      drawTimelineInspector(tlSelected);
    }
    if (focusPicNumber) {
      setTimeout(() => {
        const handle = document.querySelector(`.tl-clip-handle[data-pic="${focusPicNumber}"]`);
        if (handle) handle.focus();
      }, 50);
    }
  } catch (e) {
    alert("Could not move boundary: " + e.message);
    renderTimelineScreen();
  }
}

function drawTimelineInspector(number) {
  const box = document.getElementById("tl-inspector");
  const frame = document.getElementById("tl-frame");
  if (!box) return;

  if (tlSelectedType === "music") {
    drawTimelineMusicInspector();
    return;
  }
  if (tlSelectedType === "sfx" && tlSelectedSfx) {
    drawTimelineSfxInspector(tlSelectedSfx.segIndex, tlSelectedSfx.sfxIndex);
    return;
  }

  const pic = tlPictures().find(p => p.number === number);
  if (!pic) {
    box.innerHTML = `<span class="lbl">Inspector</span><p class="sub">Click a picture, music track, or sound effect on the timeline.</p>`;
    return;
  }

  const img = tlImageFor(pic);
  const state = tlStateFor(pic);
  // Cutting at the playhead is the timeline's own gesture for what Split does
  // on the board. It can only start a picture on a line this one already covers,
  // and never on the line it already starts at.
  const headLine = tlLineAt(tlPlayhead);
  const canCutHere = headLine > pic.firstLine && headLine <= pic.lastLine;
  if (frame) {
    frame.innerHTML = img
      ? `<img src="${img}" alt="Picture ${pic.number}"/>`
      : `<p class="sub">Picture ${pic.number} has no image yet. The Storyboard has its prompt.</p>`;
  }

  box.innerHTML = `
    <span class="lbl">Inspector</span>
    <h3>Picture ${String(pic.number).padStart(2, "0")}</h3>
    ${img ? `<img class="tl-insp-thumb" src="${img}" alt=""/>`
          : `<div class="tl-insp-thumb empty">no image yet</div>`}
    <div class="tl-insp-grid mono">
      <span class="k">in</span><span class="v">${tlClock(pic.startsAt)}</span>
      <span class="k">out</span><span class="v">${tlClock(pic.startsAt + pic.seconds)}</span>
      <span class="k">holds</span><span class="v brass">${pic.seconds.toFixed(1)}s</span>
      <span class="k">lines</span><span class="v">${pic.firstLine}&ndash;${pic.lastLine}</span>
      <span class="k">state</span><span class="v">${state || "not planned"}</span>
    </div>
    <p class="tl-insp-narr">&ldquo;${escapeHtml(pic.narration.join(" ")).slice(0, 420)}&rdquo;</p>
    <div class="tl-insp-acts">
      ${canCutHere
        ? `<button type="button" onclick="splitPictureAt(${headLine})"
             title="A new picture starts at the playhead">&#9986; Cut here &mdash; line ${headLine}</button>`
        : `<button type="button" class="tl-cut-disabled" disabled
             title="Move the playhead inside this picture, past its first line">
             <span class="tl-btn-title">&#9986; Cut at the playhead</span>
             <span class="tl-btn-reason">Playhead must be inside this picture, past line ${pic.firstLine}</span>
           </button>`}
      ${pic.number > 1
        ? `<button type="button" onclick="mergePictureAt(${pic.firstLine})">&uarr; Join to picture ${String(pic.number - 1).padStart(2, "0")}</button>`
        : ""}
      <button type="button" onclick="switchPane('board')">Open on the Storyboard</button>
    </div>`;
}

function selectTimelineMusic() {
  tlSelectedType = "music";
  tlSelected = null;
  tlSelectedSfx = null;
  document.querySelectorAll("#tl-lane-pictures .tl-clip").forEach(el => el.classList.remove("sel"));
  document.querySelectorAll("#tl-lane-sfx .tl-sfx-chip").forEach(el => el.classList.remove("sel"));
  const m = document.querySelector("#tl-lane-music .tl-music-block");
  if (m) m.classList.add("sel");
  drawTimelineMusicInspector();
}

function drawTimelineMusicInspector() {
  const box = document.getElementById("tl-inspector");
  if (!box) return;
  const proj = (currentScriptData && currentScriptData.project) || {};
  const bgMusic = proj.background_music || "";
  const fname = bgMusic ? bgMusic.split(/[\\/]/).pop() : "No music";
  const volDb = proj.music_volume_db !== undefined ? proj.music_volume_db : -20;
  const fadeIn = proj.music_fade_in || 0;
  const fadeOut = proj.music_fade_out || 0;

  box.innerHTML = `
    <span class="lbl">Inspector</span>
    <h3>Background Music</h3>
    <p class="sub mono" style="word-break:break-all">${escapeHtml(fname)}</p>
    <div class="form-stacked mt-xs">
      <div>
        <label for="tl-music-vol">Level: <b id="tl-music-vol-val" class="mono">${volDb} dB</b></label>
        <input type="range" id="tl-music-vol" min="-40" max="0" step="1" value="${volDb}"
               class="w-full" oninput="onTimelineMusicVolumeChange(this.value)">
      </div>
      <div class="grid2 mt-xs">
        <div>
          <label for="tl-music-fadein">Fade in (s)</label>
          <input type="number" id="tl-music-fadein" min="0" max="30" step="0.5" value="${fadeIn}"
                 class="w-full mono" onchange="onTimelineMusicFadeChange('in', this.value)">
        </div>
        <div>
          <label for="tl-music-fadeout">Fade out (s)</label>
          <input type="number" id="tl-music-fadeout" min="0" max="30" step="0.5" value="${fadeOut}"
                 class="w-full mono" onchange="onTimelineMusicFadeChange('out', this.value)">
        </div>
      </div>
      <p class="hint">Preview level is honest: matches the final mix without ducking.</p>
      <div class="tl-insp-acts mt-sm">
        <button type="button" onclick="timelineAddMusic()">Change music file&hellip;</button>
        <button type="button" class="ghost" onclick="removeTimelineMusic()">Remove music</button>
      </div>
    </div>
  `;
}

/**
 * Write currentScriptData back to its file, the way every other timeline edit
 * does (see moveTimelinePictureBoundary). Slice F called this from seven places
 * without ever defining it, so adding music or a sound effect died on a
 * ReferenceError before anything reached disk.
 */
async function persistCurrentScript() {
  if (isWebMode || !currentScriptData || !currentScriptPath) return false;
  await window.pywebview.api.save_edited_script(currentScriptPath, currentScriptData);
  return true;
}

async function onTimelineMusicVolumeChange(val) {
  const db = parseInt(val, 10);
  if (!currentScriptData.project) currentScriptData.project = {};
  currentScriptData.project.music_volume_db = db;
  const valEl = document.getElementById("tl-music-vol-val");
  if (valEl) valEl.textContent = `${db} dB`;
  const mAudio = timelineMusicAudioEl();
  if (mAudio) {
    mAudio.volume = Math.min(1.0, Math.max(0.0, Math.pow(10, db / 20)));
  }
  await persistCurrentScript();
  renderTimelineScreen();
}

async function onTimelineMusicFadeChange(type, val) {
  const sec = Math.max(0, parseFloat(val) || 0);
  if (!currentScriptData.project) currentScriptData.project = {};
  if (type === "in") {
    currentScriptData.project.music_fade_in = sec;
  } else {
    currentScriptData.project.music_fade_out = sec;
  }
  await persistCurrentScript();
  renderTimelineScreen();
}

async function timelineAddMusic() {
  if (isWebMode) {
    alert("File dialog requires native desktop mode.");
    return;
  }
  try {
    const projectDir = currentScriptPath ? currentScriptPath.replace(/[\\/][^\\/]*$/, "") : "";
    const res = await window.pywebview.api.add_music_file(projectDir);
    if (!res || !res.success) {
      if (res && res.cancelled) return;
      alert("Could not add music: " + ((res && res.error) || "unknown error"));
      return;
    }
    if (!currentScriptData.project) currentScriptData.project = {};
    currentScriptData.project.background_music = res.relative_path;
    if (currentScriptData.project.music_volume_db === undefined) {
      currentScriptData.project.music_volume_db = -20;
    }
    if (currentScriptData.project.music_fade_in === undefined) {
      currentScriptData.project.music_fade_in = 0.0;
    }
    if (currentScriptData.project.music_fade_out === undefined) {
      currentScriptData.project.music_fade_out = 0.0;
    }
    await persistCurrentScript();
    await prepareTimelineMusic();
    selectTimelineMusic();
    renderTimelineScreen();
  } catch (err) {
    alert("Failed to add music: " + err);
  }
}

async function removeTimelineMusic() {
  if (!currentScriptData || !currentScriptData.project) return;
  delete currentScriptData.project.background_music;
  delete currentScriptData.project.music_volume_db;
  delete currentScriptData.project.music_fade_in;
  delete currentScriptData.project.music_fade_out;

  const mAudio = timelineMusicAudioEl();
  if (mAudio) {
    mAudio.pause();
    mAudio.removeAttribute("src");
    mAudio.removeAttribute("data-music");
    mAudio.removeAttribute("data-project");
  }

  await persistCurrentScript();
  tlSelectedType = null;
  renderTimelineScreen();
  const box = document.getElementById("tl-inspector");
  if (box) {
    box.innerHTML = `<span class="lbl">Inspector</span><p class="sub">Click a picture, music track, or sound effect on the timeline.</p>`;
  }
}

function selectTimelineSfx(segIndex, sfxIndex, e) {
  if (e) e.stopPropagation();
  tlSelectedType = "sfx";
  tlSelected = null;
  tlSelectedSfx = { segIndex, sfxIndex };
  document.querySelectorAll("#tl-lane-pictures .tl-clip").forEach(el => el.classList.remove("sel"));
  document.querySelectorAll("#tl-lane-music .tl-music-block").forEach(el => el.classList.remove("sel"));
  document.querySelectorAll("#tl-lane-sfx .tl-sfx-chip").forEach(el => {
    const s = parseInt(el.dataset.seg, 10);
    const x = parseInt(el.dataset.sfx, 10);
    el.classList.toggle("sel", s === segIndex && x === sfxIndex);
  });
  drawTimelineSfxInspector(segIndex, sfxIndex);
}

function drawTimelineSfxInspector(segIndex, sfxIndex) {
  const box = document.getElementById("tl-inspector");
  if (!box) return;
  const segs = (currentScriptData && currentScriptData.segments) || [];
  const seg = segs[segIndex] || {};
  const sfxList = seg.sfx || [];
  const sfx = sfxList[sfxIndex];
  if (!sfx) {
    box.innerHTML = `<span class="lbl">Inspector</span><p class="sub">Sound effect not found.</p>`;
    return;
  }
  const filmTime = sfxToFilmTime(segIndex, sfx.offset_ms);

  box.innerHTML = `
    <span class="lbl">Inspector</span>
    <h3>Sound Effect</h3>
    <p class="sub mono" style="word-break:break-all"><b>${escapeHtml(sfx.name)}</b></p>
    <div class="tl-insp-grid mono mt-xs">
      <span class="k">film time</span><span class="v brass">${tlClock(filmTime)} (${filmTime.toFixed(2)}s)</span>
      <span class="k">segment</span><span class="v">Line ${segIndex + 1} (id: ${seg.segment_id})</span>
      <span class="k">offset</span><span class="v">+${sfx.offset_ms} ms</span>
    </div>
    <p class="hint mt-sm">Drag along the lane to re-time across segments. Effects are heard in the render, not in the timeline preview.</p>
    <div class="tl-insp-acts mt-sm">
      <button type="button" class="ghost" onclick="deleteSelectedSfx()" style="color:var(--gap); border-color:var(--gap)">Delete sound effect</button>
    </div>
  `;
}

async function deleteSelectedSfx() {
  if (tlSelectedType !== "sfx" || !tlSelectedSfx) return;
  const seg = (currentScriptData.segments || [])[tlSelectedSfx.segIndex];
  if (!seg || !seg.sfx) return;
  seg.sfx.splice(tlSelectedSfx.sfxIndex, 1);
  tlSelectedType = null;
  tlSelectedSfx = null;
  await persistCurrentScript();
  renderTimelineScreen();
  const box = document.getElementById("tl-inspector");
  if (box) {
    box.innerHTML = `<span class="lbl">Inspector</span><p class="sub">Click a picture, music track, or sound effect on the timeline.</p>`;
  }
}

async function openAddSfxMenu() {
  const modal = document.getElementById("sfx-picker-modal");
  if (!modal) return;
  modal.classList.remove("hidden");
  if (!soundLibraryData.length) {
    await loadSoundLibrary();
  }
  renderSfxPickerList(soundLibraryData);
}

function closeSfxPickerModal() {
  const modal = document.getElementById("sfx-picker-modal");
  if (modal) modal.classList.add("hidden");
}

function renderSfxPickerList(sounds) {
  const list = document.getElementById("sfx-modal-list");
  if (!list) return;
  if (!sounds || sounds.length === 0) {
    list.innerHTML = `<p class="sub p-sm">No sounds in library.</p>`;
    return;
  }
  list.innerHTML = `
    <table>
      <thead><tr><th>Name</th><th>Query</th><th>Duration</th><th>Action</th></tr></thead>
      <tbody>
        ${sounds.map(s => {
          const name = s.name || (s.path ? s.path.split("/").pop() : "Sound");
          const query = s.query || "—";
          const dur = s.duration ? `${s.duration.toFixed(1)}s` : "—";
          return `<tr>
            <td><b>${escapeHtml(name)}</b></td>
            <td>${escapeHtml(query)}</td>
            <td class="mono">${dur}</td>
            <td>
              <button type="button" class="primary" style="padding: 2px 8px; font-size:11px"
                      onclick="addSfxFromLibraryItem('${escapeHtml(s.path || "")}')">Use</button>
            </td>
          </tr>`;
        }).join("")}
      </tbody>
    </table>
  `;
}

function filterSfxPicker(query) {
  const q = (query || "").toLowerCase();
  const filtered = soundLibraryData.filter(s => {
    return (s.name || "").toLowerCase().includes(q) ||
           (s.query || "").toLowerCase().includes(q) ||
           (s.category || "").toLowerCase().includes(q);
  });
  renderSfxPickerList(filtered);
}

async function addSfxFromComputer() {
  if (isWebMode) {
    alert("File dialog requires native desktop mode.");
    return;
  }
  try {
    const projectDir = currentScriptPath ? currentScriptPath.replace(/[\\/][^\\/]*$/, "") : "";
    const res = await window.pywebview.api.add_sfx_file(projectDir);
    if (!res || !res.success) {
      if (res && res.cancelled) return;
      alert("Could not import effect: " + ((res && res.error) || "unknown error"));
      return;
    }
    await _insertSfxAtPlayhead(res.name);
    closeSfxPickerModal();
  } catch (err) {
    alert("Failed to add sound effect: " + err);
  }
}

async function addSfxFromLibraryItem(soundRelPath) {
  try {
    const projectDir = currentScriptPath ? currentScriptPath.replace(/[\\/][^\\/]*$/, "") : "";
    const res = await window.pywebview.api.add_sfx_from_library(soundRelPath, projectDir);
    if (!res || !res.success) {
      alert("Could not import effect: " + ((res && res.error) || "unknown error"));
      return;
    }
    await _insertSfxAtPlayhead(res.name);
    closeSfxPickerModal();
  } catch (err) {
    alert("Failed to add sound effect: " + err);
  }
}

async function _insertSfxAtPlayhead(name) {
  const target = filmTimeToSfx(tlPlayhead);
  const segs = currentScriptData.segments || [];
  const seg = segs[target.segmentIndex];
  if (!seg) return;
  if (!Array.isArray(seg.sfx)) seg.sfx = [];
  seg.sfx.push({
    name: name,
    offset_ms: target.offset_ms
  });
  await persistCurrentScript();
  tlSelectedType = "sfx";
  tlSelectedSfx = { segIndex: target.segmentIndex, sfxIndex: seg.sfx.length - 1 };
  renderTimelineScreen();
  drawTimelineSfxInspector(target.segmentIndex, seg.sfx.length - 1);
}

let tlSfxDragState = null;

function timelineSfxPointerDown(e, segIndex, sfxIndex) {
  if (e.button !== 0 && e.pointerType === "mouse") return;
  e.stopPropagation();
  e.preventDefault();

  const handle = e.currentTarget;
  selectTimelineSfx(segIndex, sfxIndex, e);

  try {
    handle.setPointerCapture(e.pointerId);
  } catch (_) {}

  const secs = segmentSecondsList(currentScriptData);
  const total = secs.reduce((a, b) => a + b, 0);
  const seg = currentScriptData.segments[segIndex];
  const sfx = seg.sfx[sfxIndex];
  const initialTime = sfxToFilmTime(segIndex, sfx.offset_ms);

  tlSfxDragState = {
    pointerId: e.pointerId,
    handle: handle,
    segIndex: segIndex,
    sfxIndex: sfxIndex,
    sfxName: sfx.name,
    initialTime: initialTime,
    currentTime: initialTime,
    totalFilmTime: total,
    cancelled: false
  };

  handle.classList.add("dragging");

  const onPointerMove = (ev) => {
    if (!tlSfxDragState || tlSfxDragState.pointerId !== ev.pointerId) return;
    ev.preventDefault();
    ev.stopPropagation();
    if (tlSfxDragState.cancelled) return;

    const lanes = document.getElementById("tl-lanes");
    if (!lanes) return;
    const rect = lanes.getBoundingClientRect();
    const filmTime = Math.max(0, Math.min(tlSfxDragState.totalFilmTime, (ev.clientX - rect.left) / tlZoom));
    tlSfxDragState.currentTime = filmTime;
    tlSfxDragState.handle.style.left = `${(filmTime * tlZoom).toFixed(1)}px`;
    tlSfxDragState.handle.title = `${tlSfxDragState.sfxName} · ${tlClock(filmTime)}`;
  };

  const onPointerUp = async (ev) => {
    if (!tlSfxDragState || tlSfxDragState.pointerId !== ev.pointerId) return;
    ev.preventDefault();
    ev.stopPropagation();

    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("pointercancel", onPointerCancel);

    const state = tlSfxDragState;
    tlSfxDragState = null;

    try {
      state.handle.releasePointerCapture(ev.pointerId);
    } catch (_) {}
    state.handle.classList.remove("dragging");

    if (state.cancelled) {
      renderTimelineScreen();
      return;
    }

    const res = moveSfxEffect(state.segIndex, state.sfxIndex, state.currentTime);
    await persistCurrentScript();
    if (res) {
      tlSelectedType = "sfx";
      tlSelectedSfx = { segIndex: res.newSegIndex, sfxIndex: res.newSfxIndex };
    }
    renderTimelineScreen();
    if (tlSelectedSfx) {
      drawTimelineSfxInspector(tlSelectedSfx.segIndex, tlSelectedSfx.sfxIndex);
    }
  };

  const onPointerCancel = (ev) => {
    if (!tlSfxDragState) return;
    tlSfxDragState.cancelled = true;
    tlSfxDragState.handle.classList.remove("dragging");
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("pointercancel", onPointerCancel);
    renderTimelineScreen();
  };

  window.addEventListener("pointermove", onPointerMove);
  window.addEventListener("pointerup", onPointerUp);
  window.addEventListener("pointercancel", onPointerCancel);
}

/** Clicking anywhere in the lanes moves the playhead there. */
function timelineScrubFrom(event) {
  const lanes = document.getElementById("tl-lanes");
  if (!lanes) return;
  const rect = lanes.getBoundingClientRect();
  timelineSeek((event.clientX - rect.left) / tlZoom);
}

window.renderTimelineScreen = renderTimelineScreen;
window.setTimelineZoom = setTimelineZoom;
window.timelineNudge = timelineNudge;
window.timelineSeekPicture = timelineSeekPicture;
window.selectTimelinePicture = selectTimelinePicture;
window.selectTimelineMusic = selectTimelineMusic;
window.selectTimelineSfx = selectTimelineSfx;
window.drawTimelineMusicInspector = drawTimelineMusicInspector;
window.drawTimelineSfxInspector = drawTimelineSfxInspector;
window.onTimelineMusicVolumeChange = onTimelineMusicVolumeChange;
window.onTimelineMusicFadeChange = onTimelineMusicFadeChange;
window.timelineAddMusic = timelineAddMusic;
window.removeTimelineMusic = removeTimelineMusic;
window.openAddSfxMenu = openAddSfxMenu;
window.closeSfxPickerModal = closeSfxPickerModal;
window.renderSfxPickerList = renderSfxPickerList;
window.filterSfxPicker = filterSfxPicker;
window.addSfxFromComputer = addSfxFromComputer;
window.addSfxFromLibraryItem = addSfxFromLibraryItem;
window.deleteSelectedSfx = deleteSelectedSfx;
window.filmTimeToSfx = filmTimeToSfx;
window.sfxToFilmTime = sfxToFilmTime;
window.moveSfxEffect = moveSfxEffect;
window.timelineSfxPointerDown = timelineSfxPointerDown;
window.timelineScrubFrom = timelineScrubFrom;
window.timelineSeek = timelineSeek;
window.timelineTogglePlay = timelineTogglePlay;
window.timelinePauseAudio = timelinePauseAudio;
window.timelineHandlePointerDown = timelineHandlePointerDown;
window.timelineHandlePointerMove = timelineHandlePointerMove;
window.timelineHandlePointerUp = timelineHandlePointerUp;
window.timelineHandleKeyDown = timelineHandleKeyDown;
window.timelineHandleCancel = timelineHandleCancel;
window.moveTimelinePictureBoundary = moveTimelinePictureBoundary;

// Spacebar toggles playback; Escape cancels drag; Delete/Backspace deletes selected SFX
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && tlDragState) {
    e.preventDefault();
    timelineHandleCancel(e);
    return;
  }
  const el = document.activeElement;
  const tag = el && el.tagName ? el.tagName.toUpperCase() : "";
  const isInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (el && el.isContentEditable);
  if (isInput) return;

  if (e.key === "Delete" || e.key === "Backspace") {
    if (tlSelectedType === "sfx" && tlSelectedSfx) {
      e.preventDefault();
      deleteSelectedSfx();
      return;
    }
  }

  if (e.key === " " || e.code === "Space") {
    const timelinePane = document.querySelector('.pane[data-pane="timeline"]');
    if (timelinePane && timelinePane.getAttribute("data-on") === "1") {
      e.preventDefault();
      timelineTogglePlay();
    }
  }
});

// ── Replace: the one place a shot's image changes ─────────────────────────────

function findShot(segId, shotId) {
  if (!currentScriptData) return null;
  const seg = currentScriptData.segments.find(s => s.segment_id == segId);
  if (!seg) return null;
  if (!seg.shots || !seg.shots.length) {
    // Schema v1 segment — give it a shot list so a pin has somewhere to live.
    // These defaults mirror validator.py's v1 upconversion; a shot written back
    // without motion/treatment would fail validation at render time.
    seg.shots = [{
      shot_id: `${segId}a`,
      duration: null,
      source: "library",
      query: seg.b_roll_keyword || "visual",
      pin: null,
      min_score: 0.26,
      motion: { kind: "ken_burns", effect: seg.ken_burns || "zoom_in" },
      treatment: { filter: seg.magick_filter || "vignette", grade: null }
    }];
  }
  return seg.shots.find(s => s.shot_id == shotId) || null;
}

function findReport(segId, shotId) {
  const reports = coverageReport ? coverageReport.shot_reports || [] : [];
  return reports.find(r => r.segment_id == segId && r.shot_id == shotId) || null;
}

/**
 * Pin an image to a shot and persist it.
 *
 * Persisting is not optional: the render reads the script from disk via
 * start_render(currentScriptPath), so a pin held only in memory is silently
 * dropped the moment rendering starts.
 */
async function pinImageToShot(segId, shotId, imagePath) {
  const shot = findShot(segId, shotId);
  if (!shot) return false;

  shot.source = "pin";
  shot.pin = imagePath;
  delete shot.image_path;  // legacy field the planner never read

  if (!isWebMode && currentScriptPath) {
    const res = await window.pywebview.api.save_edited_script(currentScriptPath, currentScriptData);
    if (!res.success) {
      alert("Chose the image but could not save the script: " + (res.error || "unknown error"));
      return false;
    }
  }
  return true;
}

/**
 * Show which images this project is drawing on.
 *
 * A working folder is any folder on this machine — the pictures chosen for one
 * video, wherever they are kept. Moving them into the library afterwards is the
 * user's decision, so the app never does it for them.
 */
async function loadImageFolders() {
  if (isWebMode) return;
  const labels = [
    document.getElementById("working-folder-label-board"),
  ].filter(Boolean);
  if (!labels.length) return;
  try {
    const res = await window.pywebview.api.get_working_folder_status(currentScriptData || {});
    if (!res.success) return;
    labels.forEach(label => {
      if (res.folder) {
        label.textContent = `${res.name} (${res.images})`;
        label.title = res.folder;
      } else {
        label.textContent = `whole library (${res.images})`;
        label.title = "";
      }
    });
  } catch (e) {}
}

/** Choose any folder on this machine to work from. */
async function chooseWorkingFolder() {
  if (isWebMode || !currentScriptData) {
    alert("Plan a storyboard first.");
    return;
  }
  const btn = document.getElementById("btn-working-folder-board");
  setButtonBusy(btn, "Indexing folder…");
  setBoardBusy(true, "Indexing the images in that folder…");
  try {
    const res = await window.pywebview.api.choose_working_folder(currentScriptData);
    if (res.cancelled) return;
    if (!res.success) {
      alert(res.error || "Could not use that folder.");
      return;
    }
    currentScriptData = res.script_data;
    if (currentScriptPath) {
      await window.pywebview.api.save_edited_script(currentScriptPath, currentScriptData);
    }
    await loadImageFolders();
    await refreshStoryboardCoverage();

    const dropped = (res.cleared_pins || 0) + (res.cleared_resolved || 0);
    if (dropped) {
      alert(`Now working from ${res.images} image${res.images === 1 ? "" : "s"} in that folder.\n\n` +
            `${dropped} shot${dropped === 1 ? "" : "s"} were still holding images from the ` +
            `previous source and have been re-planned` +
            `${res.cleared_pins ? ` (${res.cleared_pins} of them pinned by hand)` : ""}.`);
    }
  } catch (e) {
    alert("Could not use that folder: " + e.message);
  } finally {
    clearButtonBusy(btn);
    setBoardBusy(false);
  }
}

/** Go back to searching the whole library. */
async function useWholeLibrary() {
  if (isWebMode || !currentScriptData) return;
  setBoardBusy(true, "Using the whole library…");
  try {
    const res = await window.pywebview.api.use_whole_library(currentScriptData);
    if (!res.success) return;
    currentScriptData = res.script_data;
    if (currentScriptPath) {
      await window.pywebview.api.save_edited_script(currentScriptPath, currentScriptData);
    }
    await loadImageFolders();
    await refreshStoryboardCoverage();
  } finally {
    setBoardBusy(false);
  }
}

window.loadImageFolders = loadImageFolders;
window.chooseWorkingFolder = chooseWorkingFolder;
window.useWholeLibrary = useWholeLibrary;

/**
 * Pick up images added to the library folder by hand, then re-plan.
 *
 * Generating an image elsewhere and dropping it into library/images used to have
 * no effect until something else invalidated the index — and then cost a full
 * re-embed of every image. Indexing is incremental now, so this is quick.
 */
async function refreshLibrary() {
  if (isWebMode) return;
  const btn = document.getElementById("btn-refresh-library");
  setButtonBusy(btn, "Refreshing…");
  setBoardBusy(true, "Looking for new images in your library…");
  try {
    const res = await window.pywebview.api.refresh_library();
    if (!res.success) {
      alert("Could not refresh the library: " + (res.error || "unknown error"));
      return;
    }
    await loadLibraryData();
    await loadImageFolders();
    if (currentScriptData) await refreshStoryboardCoverage();
    alert(`Library refreshed — ${res.images} images indexed in ${res.seconds}s.\n${res.detail}`);
  } catch (e) {
    alert("Could not refresh the library: " + e.message);
  } finally {
    clearButtonBusy(btn);
    setBoardBusy(false);
  }
}

/** Copy every shot's image prompt for this script, matched shots included. */
async function copyAllPrompts() {
  if (isWebMode || !currentScriptData) {
    alert("Plan a storyboard first.");
    return;
  }
  const btn = document.getElementById("btn-copy-prompts");
  setButtonBusy(btn, "Collecting…");
  try {
    const res = await window.pywebview.api.get_all_prompts(currentScriptData);
    if (!res.success) {
      alert("Could not collect the prompts: " + (res.error || "unknown error"));
      return;
    }
    try {
      await navigator.clipboard.writeText(res.text);
      alert(`Copied ${res.shots} prompts to the clipboard.`);
    } catch (clipErr) {
      // WebView2 can refuse clipboard access; never lose the work.
      const save = await window.pywebview.api.save_prompts_to_file(res.text);
      alert(save.success
        ? `Clipboard was blocked, so the prompts were saved to:\n${save.path}`
        : "Could not copy or save the prompts: " + (save.error || "unknown error"));
    }
  } catch (e) {
    alert("Could not collect the prompts: " + e.message);
  } finally {
    clearButtonBusy(btn);
  }
}

async function openTimelineFromBoard() {
  if (!currentScriptData) {
    alert("Plan a storyboard first.");
    return;
  }
  switchPane("timeline");
  renderTimelineScreen();
}

window.openTimelineFromBoard = openTimelineFromBoard;
window.refreshLibrary = refreshLibrary;
window.copyAllPrompts = copyAllPrompts;

/** Accept the closest library image for every gap, in one action. */
async function fillAllGaps() {
  if (isWebMode || !currentScriptData) return;
  const btn = document.getElementById("btn-fill-gaps");
  setButtonBusy(btn, "Filling gaps…");
  setBoardBusy(true, "Finding the closest image for every gap…");
  try {
    const res = await window.pywebview.api.fill_gaps_with_nearest(currentScriptData, true);
    if (!res.success) {
      alert("Could not fill the gaps: " + (res.error || "unknown error"));
      return;
    }
    currentScriptData = res.script_data;
    if (currentScriptPath) {
      await window.pywebview.api.save_edited_script(currentScriptPath, currentScriptData);
    }
    await refreshStoryboardCoverage();
    const left = res.still_empty
      ? ` ${res.still_empty} still have nothing close enough.`
      : "";
    alert(`Filled ${res.filled} gap${res.filled === 1 ? "" : "s"} with the closest image.${left}\n\nEach one is a normal pin — use Replace on any you dislike.`);
  } catch (e) {
    alert("Could not fill the gaps: " + e.message);
  } finally {
    clearButtonBusy(btn);
    setBoardBusy(false);
  }
}

/**
 * Update one shot's card without re-planning the board.
 *
 * A full re-plan searches every shot — measured at ~18 seconds on a 95-shot
 * board — and it ran on every Replace click, which is what made changing images
 * by hand unbearable. Pinning one shot cannot change any other shot's match, so
 * there is nothing to recompute.
 */
function applyPinLocally(segId, shotId, newPath, thumbUrl) {
  if (!coverageReport) return false;
  const rep = (coverageReport.shot_reports || []).find(
    r => r.segment_id == segId && r.shot_id == shotId);
  if (!rep) return false;

  rep.best_path = newPath;
  rep.best_score = 1.0;
  rep.state = "pinned";
  rep.pin_missing = false;
  if (thumbUrl) rep.best_url = thumbUrl;
  // The image now belongs to this shot, so stop offering it elsewhere.
  (coverageReport.shot_reports || []).forEach(other => {
    if (other === rep) return;
    other.alternative_urls = (other.alternative_urls || []).filter(a => a.path !== newPath);
  });
  renderStoryboardScreen();
  return true;
}

async function selectAlternative(segId, shotId, newPath, thumbUrl) {
  if (!(await pinImageToShot(segId, shotId, newPath))) return;
  if (!applyPinLocally(segId, shotId, newPath, thumbUrl)) {
    await refreshStoryboardCoverage();
  }
}

function openReplaceModal(segId, shotId) {
  activeReplaceShot = { segId, shotId };
  const rep = findReport(segId, shotId);

  const label = document.getElementById("modal-shot-label");
  if (label) label.textContent = `Segment ${segId} · shot ${shotId} — query: ${rep ? rep.query : ""}`;

  const current = document.getElementById("modal-current");
  if (current) {
    current.innerHTML = (rep && rep.best_url)
      ? `<div class="modal-current"><img src="${rep.best_url}" alt="current image"/>
           <span>${rep.state === "pinned" ? "your chosen image" : "currently suggested"}</span></div>`
      : `<div class="modal-current empty"><span>no image on this shot yet</span></div>`;
  }

  const alts = document.getElementById("modal-alts");
  if (alts) {
    const list = (rep && rep.alternative_urls) ? rep.alternative_urls : [];
    alts.innerHTML = list.length
      ? list.map(a => `
          <span class="altwrap" onclick="chooseAlternativeFromModal('${a.path}', '${a.url}')">
            <img class="alt" src="${a.url}" alt="alternative"/>
            <i>${(a.score || 0).toFixed(2)}</i>
          </span>`).join("")
      : `<span class="sub">Nothing else in the library is close to this query.</span>`;
  }

  const promptEl = document.getElementById("modal-prompt");
  if (promptEl) promptEl.textContent = rep ? (rep.composed_prompt || "") : "";

  const modal = document.getElementById("replace-modal");
  if (modal) modal.classList.remove("hidden");
}

function closeReplaceModal() {
  activeReplaceShot = null;
  const modal = document.getElementById("replace-modal");
  if (modal) modal.classList.add("hidden");
}

// Escape always closes the dialog, and so does clicking the backdrop. A modal
// with no visible way out is a trap.
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const modal = document.getElementById("replace-modal");
  if (modal && !modal.classList.contains("hidden")) closeReplaceModal();
});

document.addEventListener("click", (e) => {
  const modal = document.getElementById("replace-modal");
  if (modal && e.target === modal) closeReplaceModal();
});

async function chooseAlternativeFromModal(path, thumbUrl) {
  if (!activeReplaceShot) return;
  const { segId, shotId } = activeReplaceShot;
  closeReplaceModal();
  await selectAlternative(segId, shotId, path, thumbUrl);
}

/** Bring in an image made outside the app and pin it to this shot. */
async function replaceWithOwnImage() {
  if (!activeReplaceShot) return;
  if (!window.pywebview) { alert("Image import is only available in the desktop app."); return; }

  const { segId, shotId } = activeReplaceShot;
  const rep = findReport(segId, shotId);
  closeReplaceModal();

  // Importing a new file rebuilds the CLIP index over the whole library, which
  // takes a while on 1,200+ images. Without this the app looks hung.
  setBoardBusy(true, "Adding your image and reindexing the library…");
  try {
    const res = await window.pywebview.api.import_shot_image(rep ? rep.query : "", segId, shotId);
    if (res.cancelled) { setBoardBusy(false); return; }
    if (!res.success) {
      setBoardBusy(false);
      alert("Could not add the image: " + (res.error || "unknown error"));
      return;
    }

    if (await pinImageToShot(segId, shotId, res.path)) {
      if (!applyPinLocally(segId, shotId, res.path, res.url)) {
        await refreshStoryboardCoverage();
      }
    }
    setBoardBusy(false);
  } catch (e) {
    setBoardBusy(false);
    alert("Could not add the image: " + e.message);
  }
}

async function copyPromptFor(segId, shotId) {
  const shot = findShot(segId, shotId);
  const rep = findReport(segId, shotId);
  const text = (shot && shot.prompt_override && shot.prompt_override.trim()) || (rep && rep.composed_prompt) || "";
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    alert("Could not copy — here is the prompt:\n\n" + text);
  }
}

async function copyShotPrompt() {
  if (!activeReplaceShot) return;
  await copyPromptFor(activeReplaceShot.segId, activeReplaceShot.shotId);
}

async function confirmReplace(actionType) {
  if (!activeReplaceShot) { closeReplaceModal(); return; }
  const { segId, shotId } = activeReplaceShot;
  const rep = findReport(segId, shotId);
  closeReplaceModal();

  if (!rep || !rep.best_path) { await refreshStoryboardCoverage(); return; }

  const shot = findShot(segId, shotId);

  try {
    if (actionType === "never_this_query") {
      const res = await window.pywebview.api.reject_shot_image(rep.query, rep.best_path);
      if (!res.success) { alert("Could not record that: " + (res.error || "unknown error")); return; }
    } else if (actionType === "retire") {
      const res = await window.pywebview.api.retire_library_image(rep.best_path);
      if (!res.success) { alert("Could not retire that image: " + (res.error || "unknown error")); return; }
    }

    // The user has rejected this image, so an existing pin on it must go.
    let cleared = false;
    if (shot && shot.pin === rep.best_path) {
      delete shot.pin;
      shot.source = "library";
      cleared = true;
    }

    // "Just not here" records nothing, so retrieval would hand back the same
    // image on the next plan. Move the shot onto the next best candidate instead,
    // which leaves the rejected image in the library and free for other shots.
    const nextBest = (rep.alternative_urls && rep.alternative_urls.length)
      ? rep.alternative_urls[0].path
      : null;

    if (actionType === "just_not_here") {
      if (!nextBest) {
        alert("Nothing else in your library is close to this query. Use your own image instead.");
        return;
      }
      await pinImageToShot(segId, shotId, nextBest);
    } else if (cleared && !isWebMode && currentScriptPath) {
      await window.pywebview.api.save_edited_script(currentScriptPath, currentScriptData);
    }

    await refreshStoryboardCoverage();
  } catch (e) {
    alert("Could not apply that: " + e.message);
  }
}

window.fillAllGaps = fillAllGaps;
window.selectAlternative = selectAlternative;
window.chooseAlternativeFromModal = chooseAlternativeFromModal;
window.replaceWithOwnImage = replaceWithOwnImage;
window.copyPromptFor = copyPromptFor;
window.copyShotPrompt = copyShotPrompt;
window.confirmReplace = confirmReplace;
window.openReplaceModal = openReplaceModal;
window.closeReplaceModal = closeReplaceModal;

// ── Render Screen Execution & Log Updates ────────────────────────────────────
async function startRenderFromBoard() {
  if (!currentScriptPath && !isWebMode) {
    alert("Please save draft script before rendering.");
    return;
  }

  // The render reads the script from disk, so the board's decisions — pins and
  // the images it settled on — have to be written down first. Otherwise the
  // render re-runs retrieval and can use different images than you approved.
  if (!isWebMode && currentScriptPath && currentScriptData) {
    const res = await window.pywebview.api.save_edited_script(currentScriptPath, currentScriptData);
    if (!res.success) {
      alert("Could not save the storyboard before rendering: " + (res.error || "unknown error"));
      return;
    }
  }

  switchPane("render");
  toggleRenderExecution();
}

async function toggleRenderExecution() {
  const btn = document.getElementById("btn-render-action");

  if (isRendering) {
    if (!isWebMode) {
      await window.pywebview.api.cancel_render();
    }
    finishRender("p-warn", "cancelled", "Render cancelled.");
    return;
  }

  if (!currentScriptPath && !isWebMode) {
    alert("No active script file to render.");
    return;
  }

  isRendering = true;
  btn.textContent = "Cancel Render";
  btn.className = "ghost";
  document.getElementById("render-status-pill").className = "pill p-ok";
  document.getElementById("render-status-pill").textContent = "rendering";
  document.getElementById("render-human-step").textContent = "Starting…";

  renderStage = { num: 0, total: 7 };
  setRenderProgress(0);
  setBarBusy(true);
  startRenderClock();

  document.getElementById("render-project-title").textContent = currentScriptData ? currentScriptData.project.title : "Smart Studio Project";

  if (!isWebMode) {
    const res = await window.pywebview.api.start_render(currentScriptPath);
    if (!res.success) {
      alert("Could not start render: " + res.error);
      finishRender("p-gap", "failed", res.error || "Could not start the render.");
    }
  }
}

// ── Render progress ───────────────────────────────────────────────────────────
//
// The handlers here previously listened for "stage_start" and "segment_progress".
// The pipeline has only ever emitted "stage" and "progress", so the bar and the
// counters never moved on any render, successful or not — which is why a working
// render was indistinguishable from a dead one.

let renderStartedAt = null;
let renderTimer = null;
let renderStage = { num: 0, total: 7 };

const STAGE_COUNTERS = {
  "Voiceovers": "kv-narr-status",
  "Captions": "kv-cap-status",
  "Composing": "kv-shots-status",
};

function setBarBusy(busy) {
  const bar = document.getElementById("render-progress-bar");
  if (bar) bar.classList.toggle("busy", !!busy);
}

function setRenderProgress(fraction) {
  const bar = document.getElementById("render-progress-bar");
  if (bar) bar.style.width = `${Math.max(0, Math.min(100, Math.round(fraction * 100)))}%`;
}

function formatClock(totalSeconds) {
  const m = Math.floor(totalSeconds / 60);
  const s = Math.floor(totalSeconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function startRenderClock() {
  renderStartedAt = Date.now();
  stopRenderClock();
  renderTimer = setInterval(() => {
    const elapsed = (Date.now() - renderStartedAt) / 1000;
    const info = document.getElementById("render-time-info");
    if (!info) return;
    // Estimate from stage completion — honest about being an estimate, and
    // absent until there is something real to base it on.
    let eta = "--:--";
    const done = renderStage.total ? (renderStage.num - 1) / renderStage.total : 0;
    if (done > 0.05 && elapsed > 3) eta = formatClock((elapsed / done) - elapsed);
    info.textContent = `elapsed ${formatClock(elapsed)} · eta ${eta}`;
  }, 500);
}

function stopRenderClock() {
  if (renderTimer) { clearInterval(renderTimer); renderTimer = null; }
}

function finishRender(pillClass, pillText, humanStep) {
  isRendering = false;
  stopRenderClock();
  setBarBusy(false);
  const btn = document.getElementById("btn-render-action");
  if (btn) { btn.textContent = "Start Render"; btn.className = "primary"; }
  const pill = document.getElementById("render-status-pill");
  if (pill) { pill.className = `pill ${pillClass}`; pill.textContent = pillText; }
  const step = document.getElementById("render-human-step");
  if (step) step.textContent = humanStep;
}

window.onPipelineEvent = function(event) {
  if (!event) return;

  if (event.type === "log" && event.message) {
    logLines.push(event.message);
    if (logLines.length > MAX_LOG_LINES) logLines.shift();
    const logPanel = document.getElementById("log-panel");
    if (logPanel) {
      logPanel.textContent = logLines.join("\n");
      logPanel.scrollTop = logPanel.scrollHeight;
    }
    const step = document.getElementById("render-human-step");
    if (step && renderStage.num === 0) step.textContent = event.message;
  }

  if (event.type === "stage") {
    renderStage = { num: event.stage_num || 0, total: event.total_stages || 7 };
    const step = document.getElementById("render-human-step");
    if (step) step.textContent = `Step ${renderStage.num} of ${renderStage.total} — ${event.name}`;
    setRenderProgress((renderStage.num - 1) / renderStage.total);
    setBarBusy(true);
  }

  if (event.type === "progress") {
    const done = event.completed || 0;
    const total = event.total || 1;

    const counterId = STAGE_COUNTERS[event.stage];
    if (counterId) {
      const el = document.getElementById(counterId);
      if (el) el.textContent = `${done} / ${total}`;
    }

    // Overall = whole stages finished, plus how far through the current one.
    const base = (renderStage.num - 1) / renderStage.total;
    setRenderProgress(base + (done / total) / renderStage.total);

    const step = document.getElementById("render-human-step");
    if (step) step.textContent = event.message || `${event.stage} ${done}/${total}`;
  }

  if (event.type === "error") {
    finishRender("p-gap", "failed", event.message || "The render failed.");
    if (event.detail) {
      logLines.push(event.detail);
      const logPanel = document.getElementById("log-panel");
      if (logPanel) logPanel.textContent = logLines.join("\n");
    }
    alert(event.message || "The render failed. Open Show raw logs for detail.");
  }

  if (event.type === "complete") {
    setRenderProgress(1);
    finishRender("p-ok", "completed", "Render completed successfully.");
  }
};

function toggleRawLogs() {
  const panel = document.getElementById("log-panel");
  if (panel) panel.classList.toggle("hidden");
}

function openOutputFolder() {
  if (!isWebMode) {
    window.pywebview.api.open_output_folder();
  }
}

async function openInWolfCut(projectPath) {
  if (isWebMode || !window.pywebview || !window.pywebview.api || !window.pywebview.api.open_in_wolfcut) {
    alert("WolfCut export is available in desktop app mode.");
    return;
  }

  try {
    const res = await window.pywebview.api.open_in_wolfcut(projectPath);
    if (res.success) {
      return;
    }

    if (!res.installed) {
      const msg = `${res.error || "WolfCut is not installed on this machine."}\n\nYou can download WolfCut free from:\n${res.releases_url || "https://github.com/jub0t/WolfCut/releases"}\n\nWould you like to show the exported .wolfcut file in your folder?`;
      if (confirm(msg)) {
        if (window.pywebview.api.show_wolfcut_file) {
          window.pywebview.api.show_wolfcut_file(res.path);
        }
      }
    } else if (res.error) {
      alert(`Could not open WolfCut: ${res.error}`);
    }
  } catch (e) {
    console.error("openInWolfCut error:", e);
    alert(`Failed to open WolfCut: ${e}`);
  }
}
window.openInWolfCut = openInWolfCut;

async function exportTimelineToWolfCut() {
  if (!currentScriptData) {
    alert("No film loaded to export.");
    return;
  }
  const statusEl = document.getElementById("tl-status");
  const origStatus = statusEl ? statusEl.textContent : "";
  if (statusEl) {
    statusEl.textContent = "Exporting timeline to WolfCut...";
    statusEl.className = "mono";
  }

  try {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.export_wolfcut_timeline) {
      const projectDir = currentScriptPath
        ? currentScriptPath.replace(/[\\/][^\\/]*$/, "")
        : "";
      const res = await window.pywebview.api.export_wolfcut_timeline(currentScriptData, projectDir);
      if (!res || !res.success) {
        const err = (res && res.error) || "Export failed.";
        alert(err);
        if (statusEl) {
          statusEl.textContent = err;
          statusEl.className = "mono warn-text";
        }
        return;
      }

      if (statusEl) {
        statusEl.textContent = `Exported ${res.pictures} pictures to WolfCut · captions come with render`;
        statusEl.className = "mono ink-1";
      }

      if (res.path) {
        await openInWolfCut(res.path);
      }
    } else {
      alert("WolfCut export requires desktop app connection.");
      if (statusEl) statusEl.textContent = origStatus;
    }
  } catch (err) {
    console.error("exportTimelineToWolfCut error:", err);
    alert("Export to WolfCut failed: " + err);
    if (statusEl) statusEl.textContent = origStatus;
  }
}
window.exportTimelineToWolfCut = exportTimelineToWolfCut;

function switchLibTab(tab) {
  document.getElementById("tab-lib-images").className = `lib-tab ${tab === 'images' ? 'active' : ''}`;
  document.getElementById("tab-lib-sounds").className = `lib-tab ${tab === 'sounds' ? 'active' : ''}`;

  document.getElementById("lib-content-images").style.display = tab === "images" ? "flex" : "none";
  document.getElementById("lib-content-sounds").style.display = tab === "sounds" ? "flex" : "none";
  if (tab === "sounds") {
    loadSoundLibrary();
  }
}

let soundLibraryData = [];

async function loadSoundLibrary() {
  if (isWebMode) return;
  try {
    if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.get_sound_library) return;
    const res = await window.pywebview.api.get_sound_library();
    soundLibraryData = res.sounds || [];
    renderSoundLibrary(soundLibraryData);
  } catch (e) {
    console.error("Failed to load sound library:", e);
  }
}

function renderSoundLibrary(sounds) {
  const tbody = document.getElementById("lib-sounds-tbody");
  const empty = document.getElementById("lib-sounds-empty");
  const countPill = document.getElementById("lib-sounds-count-pill");
  if (!tbody) return;

  if (countPill) {
    countPill.textContent = `${sounds.length} sound${sounds.length === 1 ? "" : "s"}`;
  }

  if (!sounds || sounds.length === 0) {
    tbody.innerHTML = "";
    if (empty) empty.classList.remove("hidden");
    return;
  }
  if (empty) empty.classList.add("hidden");

  tbody.innerHTML = sounds.map(s => {
    const name = s.name || (s.path ? s.path.split("/").pop() : "Unknown");
    const query = s.query || "—";
    const cat = s.category || "beds";
    const durSec = parseFloat(s.duration) || 0;
    const dur = `${Math.floor(durSec / 60)}:${String(Math.floor(durSec % 60)).padStart(2, "0")}`;
    const lic = s.licence_type || "CC0";
    const attr = s.attribution || "—";
    return `<tr>
      <td><b>${escapeHtml(name)}</b></td>
      <td>${escapeHtml(query)}</td>
      <td><span class="pill p-ok">${escapeHtml(cat)}</span></td>
      <td class="mono">${dur}</td>
      <td><span class="pill p-mute">${escapeHtml(lic)}</span></td>
      <td class="mono text-muted" style="font-size:11px">${escapeHtml(attr)}</td>
    </tr>`;
  }).join("");
}

async function loadLibraryData(query = "") {
  if (isWebMode) return;

  try {
    const res = await window.pywebview.api.get_library_data(query);
    renderLibraryGrid(res.images || []);
    const pending = res.sounds_pending ? ` · ${res.sounds_pending} awaiting review` : "";
    document.getElementById("lib-counts-label").textContent =
      `${res.total_images} images · ${res.sounds_count} sounds${pending}`;
    document.getElementById("house-active-count").textContent = res.total_images;
    document.getElementById("house-retired-count").textContent = res.retired_count;
    await loadSoundLibrary();
  } catch (e) {
    console.error("Failed to load library data:", e);
  }
}

function renderLibraryGrid(images) {
  const grid = document.getElementById("library-img-grid");
  if (!grid) return;

  if (!images || images.length === 0) {
    grid.innerHTML = `
      <div class="card" style="grid-column: 1 / -1; padding: 24px; text-align: center;">
        <h3>No images found</h3>
        <p class="sub" style="margin-top: 6px;">Add images to <code>library/images/</code> or render a script to populate your media library.</p>
      </div>
    `;
    return;
  }

  grid.innerHTML = images.map(img => `
    <div class="img-card">
      <img src="${img.url || img.path}" alt="${img.filename}" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'180\\' height=\\'110\\' fill=\\'%2326313C\\'></svg>'"/>
      <div class="info">
        <span class="fname">${img.filename}</span>
        <button type="button" class="ghost" style="padding: 2px 6px; font-size: 10.5px; border-color: var(--gap); color: var(--gap)" onclick="deleteImage('${img.filename}')">Delete</button>
      </div>
    </div>
  `).join("");
}

function filterLibraryImages(query) {
  loadLibraryData(query);
}

async function deleteImage(filename) {
  if (confirm(`Permanently delete ${filename} from library?`)) {
    if (!isWebMode) {
      await window.pywebview.api.delete_library_image(filename);
      await loadLibraryData();
    }
  }
}

async function clearLibraryCache() {
  if (!isWebMode) {
    await window.pywebview.api.clear_cache();
    alert("Cache cleared.");
  }
}


// Importing an image now lives in the Replace modal (replaceWithOwnImage), so it
// works on every shot and pins what it adds.
