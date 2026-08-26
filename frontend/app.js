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
  await applyUiDefaults();
  await restoreLastProject();
}


// ── Remembering the Script screen ─────────────────────────────────────────────
// Voice, series pack, tone and style reset to the first option on every launch,
// so the same choices had to be made before every video.

const UI_FIELDS = {
  voice: "pt-voice", series_slug: "pt-series-slug",
  tone: "pt-tone", visual_type: "pt-style",
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
  defaults.formats = getSelectedFormats();
  try { await window.pywebview.api.save_ui_defaults(defaults); } catch (e) {}
}

async function applyUiDefaults() {
  if (isWebMode) return;
  try {
    const res = await window.pywebview.api.get_ui_defaults();
    const d = (res && res.ui_defaults) || {};
    for (const [key, id] of Object.entries(UI_FIELDS)) {
      const el = document.getElementById(id);
      if (!el || !d[key]) continue;
      // Only restore a choice the dropdown still offers.
      if ([...el.options].some(o => o.value === d[key])) el.value = d[key];
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
      { series_slug: "civil_war", display_name: "American Civil War" },
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

  select.addEventListener("change", loadStylePresets);
  await loadStylePresets();
}

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

  voiceCatalogue.forEach(engGroup => {
    const engDiv = document.createElement("div");
    engDiv.className = "eng";

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

    engDiv.innerHTML = `
      <div class="eng-h">
        <b>${engGroup.engine}</b>
        <span class="pill p-mute">${engGroup.voices.length} voices</span>
        <span class="mono" style="margin-left:auto">${enabledInEng} enabled</span>
      </div>
      <div class="tbl">
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
    setKeyStatus("google-key-status", !!localStorage.getItem("google_api_key"));
    setKeyStatus("google-tts-key-status", !!localStorage.getItem("google_tts_api_key"));
    return;
  }

  try {
    const settings = await window.pywebview.api.get_settings();
    const rows = [
      ["google-key", settings.google_api_key_set],
      ["google-tts-key", settings.google_tts_api_key_set],
      ["elevenlabs-key", settings.elevenlabs_api_key_set],
    ];
    rows.forEach(([id, isSet]) => {
      setKeyStatus(`${id}-status`, !!isSet);
      const input = document.getElementById(`${id}-input`);
      if (input && isSet) input.placeholder = "•••••• stored — type a new key to replace";
    });
  } catch (e) {}
}

function setKeyStatus(id, connected) {
  const el = document.getElementById(id);
  if (!el) return;
  if (connected) {
    el.className = "pill p-ok";
    el.textContent = "connected";
  } else {
    el.className = "pill p-mute";
    el.textContent = "not set";
  }
}

async function saveGoogleKey() {
  const key = document.getElementById("google-key-input").value;
  if (!isWebMode) {
    await window.pywebview.api.save_google_key(key);
  } else {
    localStorage.setItem("google_api_key", key);
  }
  setKeyStatus("google-key-status", !!key.trim());
}

async function saveGoogleTtsKey() {
  const key = document.getElementById("google-tts-key-input").value;
  if (!isWebMode) {
    await window.pywebview.api.save_google_tts_key(key);
  } else {
    localStorage.setItem("google_tts_api_key", key);
  }
  setKeyStatus("google-tts-key-status", !!key.trim());
}

// DeepSeek and Freesound rows are gone from Settings — DeepSeek was out of credit
// and its planning job runs locally; Freesound was never wired to anything.

/** ElevenLabs is optional: only whoever chooses to pay for it ever sets this. */
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
  const style = document.getElementById("pt-style").value;
  const tone = document.getElementById("pt-tone").value;

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
        voice: voice || "local:supertonic-m1",
        visual_style: style
      },
      segments: paragraphs.map((p, i) => ({
        segment_id: i + 1,
        narration: p.trim(),
        shots: [{ shot_id: `${i + 1}a`, query: p.slice(0, 40) + " visual" }]
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
      tone
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
    const briefEl = document.getElementById("pt-brief");
    if (briefEl && briefEl.value.trim()) {
      currentScriptData.project.project_brief = briefEl.value.trim();
    }
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

        const briefBox = document.getElementById("pt-brief");
        if (briefBox && !briefBox.value.trim() && currentScriptData && currentScriptData.project
            && currentScriptData.project.project_brief) {
          briefBox.value = currentScriptData.project.project_brief;
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

  let html = "";

  currentScriptData.segments.forEach(seg => {
    const segId = seg.segment_id;
    const narration = seg.narration;
    const shots = seg.shots || [{ shot_id: `${segId}a`, query: seg.b_roll_keyword || "visual" }];

    shots.forEach(shot => {
      const shotId = shot.shot_id;
      const key = `${segId}_${shotId}`;
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
              <span class="sid">SEGMENT ${segId} &middot; SHOT ${shotId}</span>
              <span class="pill ${pillClass}">${pillText}</span>
            </div>
            <p class="narr">&ldquo;${narration}&rdquo;</p>
            <p class="q">query: ${rep.query || shot.query}</p>
            ${pinWarnHtml}
            ${altsHtml}
            ${gapBoxHtml}
            <div class="acts">
              <button type="button" onclick="openReplaceModal('${segId}', '${shotId}')">Replace</button>
            </div>
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

let rhythmTimer = null;

function updateRhythmLabel(val) {
  const lbl = document.getElementById("rhythm-label");
  const secs = RHYTHM_SECONDS[val] || 7;
  if (lbl) lbl.textContent = `~${secs}s per shot`;

  // Re-cutting runs CLIP over every new shot, so wait until the slider settles.
  clearTimeout(rhythmTimer);
  rhythmTimer = setTimeout(() => applyShotRhythm(secs), 450);
}

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
window.applyShotRhythm = applyShotRhythm;

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
    document.getElementById("working-folder-label"),
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
  const btn = document.getElementById("btn-working-folder") || document.getElementById("btn-working-folder-board");
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
async function refreshLibraryAndReplan() {
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

window.refreshLibraryAndReplan = refreshLibraryAndReplan;
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
  const rep = findReport(segId, shotId);
  if (!rep) return;
  try {
    await navigator.clipboard.writeText(rep.composed_prompt || "");
  } catch (e) {
    alert("Could not copy — here is the prompt:\n\n" + (rep.composed_prompt || ""));
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

// ── Library Screen Management ────────────────────────────────────────────────
function switchLibTab(tab) {
  document.getElementById("tab-lib-images").className = `lib-tab ${tab === 'images' ? 'active' : ''}`;
  document.getElementById("tab-lib-sounds").className = `lib-tab ${tab === 'sounds' ? 'active' : ''}`;

  document.getElementById("lib-content-images").style.display = tab === "images" ? "flex" : "none";
  document.getElementById("lib-content-sounds").style.display = tab === "sounds" ? "flex" : "none";
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
