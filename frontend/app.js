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
}

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
async function loadSettingsData() {
  if (isWebMode) {
    const gKey = localStorage.getItem("google_api_key") || "";
    if (gKey) {
      document.getElementById("google-key-input").value = gKey;
      setKeyStatus("google-key-status", true);
    }
    const gTtsKey = localStorage.getItem("google_tts_api_key") || "";
    if (gTtsKey) {
      document.getElementById("google-tts-key-input").value = gTtsKey;
      setKeyStatus("google-tts-key-status", true);
    }
    const dKey = localStorage.getItem("deepseek_api_key") || "";
    if (dKey) {
      document.getElementById("deepseek-key-input").value = dKey;
      setKeyStatus("deepseek-key-status", true);
    }
    return;
  }

  try {
    const settings = await window.pywebview.api.get_settings();
    if (settings.google_api_key) {
      document.getElementById("google-key-input").value = settings.google_api_key;
      setKeyStatus("google-key-status", true);
    }
    if (settings.google_tts_api_key) {
      document.getElementById("google-tts-key-input").value = settings.google_tts_api_key;
      setKeyStatus("google-tts-key-status", true);
    }
    if (settings.deepseek_api_key) {
      document.getElementById("deepseek-key-input").value = settings.deepseek_api_key;
      setKeyStatus("deepseek-key-status", true);
    }
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
  setKeyStatus("google-key-status", !!key.strip());
}

async function saveGoogleTtsKey() {
  const key = document.getElementById("google-tts-key-input").value;
  if (!isWebMode) {
    await window.pywebview.api.save_google_tts_key(key);
  } else {
    localStorage.setItem("google_tts_api_key", key);
  }
  setKeyStatus("google-tts-key-status", !!key.strip());
}

async function saveDeepseekKey() {
  const key = document.getElementById("deepseek-key-input").value;
  if (!isWebMode) {
    await window.pywebview.api.save_deepseek_key(key);
  } else {
    localStorage.setItem("deepseek_api_key", key);
  }
  setKeyStatus("deepseek-key-status", !!key.strip());
}

// ── Script Loading & Planning ────────────────────────────────────────────────
async function triggerLoadScript() {
  if (isWebMode) {
    alert("Use plain text input or paste your script text on the Script screen.");
    return;
  }

  const path = await window.pywebview.api.open_file_dialog();
  if (path) {
    const res = await window.pywebview.api.load_script(path);
    if (res.success) {
      currentScriptPath = res.path;
      currentScriptData = res.script_data;

      document.getElementById("pt-title").value = res.title;
      document.getElementById("script-status-label").textContent = `loaded: ${res.title}`;

      // Calculate coverage and jump to Storyboard
      await refreshStoryboardCoverage();
      switchPane("board");
    } else {
      alert("Failed to load script: " + (res.errors ? res.errors.join("\n") : "invalid format"));
    }
  }
}

async function planStoryboard() {
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
  btn.disabled = true;
  btn.textContent = "Planning storyboard...";

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
    btn.disabled = false;
    btn.textContent = "Plan storyboard →";

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
    btn.disabled = false;
    btn.textContent = "Plan storyboard →";
    alert("Planning failed: " + e.message);
  }
}

window.onParseComplete = async function(result) {
  const btn = document.getElementById("btn-plan-storyboard");
  btn.disabled = false;
  btn.textContent = "Plan storyboard →";

  if (result.success) {
    currentScriptPath = result.path;
    currentScriptData = result.script_data;

    document.getElementById("script-status-label").textContent = `planned: ${result.title}`;

    await refreshStoryboardCoverage();
    switchPane("board");
  } else {
    alert("Storyboard planning failed: " + (result.errors ? result.errors.join("\n") : "unknown error"));
  }
};

function saveDraftScript() {
  if (!currentScriptData) {
    alert("No active planned script to save.");
    return;
  }

  if (currentScriptPath && !isWebMode) {
    window.pywebview.api.save_edited_script(currentScriptPath, currentScriptData);
    alert("Draft saved to " + currentScriptPath);
  } else {
    alert("Draft saved in memory.");
  }
}

// ── Storyboard Screen Coverage & Rendering ────────────────────────────────────
async function refreshStoryboardCoverage() {
  if (!currentScriptData) return;

  if (!isWebMode && window.pywebview.api.get_storyboard_coverage) {
    try {
      const res = await window.pywebview.api.get_storyboard_coverage(currentScriptData);
      if (res.success) {
        coverageReport = res.report;
      }
    } catch (e) {
      console.error("Coverage calculation error:", e);
    }
  }

  renderStoryboardScreen();
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
    if (r.state === "matched") matchedCnt++;
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
      const pillText = rep.state === "weak" ? "weak match" : rep.state === "gap" ? "gap" : "matched";

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
          <span class="altwrap" onclick="selectAlternative('${segId}', '${shotId}', '${alt.path}')">
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

      // Prompt box for gaps
      let gapBoxHtml = "";
      if (rep.state === "gap") {
        gapBoxHtml = `
          <div class="promptbox">
            <span class="lbl">Generate this &mdash; prompt ready</span>
            <code>${rep.composed_prompt || 'cinematic shot'}</code>
            <div style="display:flex; gap:7px; flex-wrap:wrap">
              <button type="button" onclick="navigator.clipboard.writeText('${(rep.composed_prompt || '').replace(/'/g, "\\'")}')">Copy prompt</button>
              <button type="button" class="primary" onclick="importShotImage('${(rep.query || '').replace(/'/g, "\'")}')">I made this image &mdash; add it</button>
            </div>
            <div class="drop">Generate it anywhere, then add it here. It joins the library and this shot fills in.</div>
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
            ${altsHtml}
            ${gapBoxHtml}
            <div class="acts">
              <button type="button" onclick="openReplaceModal('${segId}', '${shotId}')">Replace</button>
              <button type="button" class="ghost" onclick="alert('Prompt: ' + '${(rep.composed_prompt || '').replace(/'/g, "\\'")}')">Get prompt</button>
            </div>
          </div>
        </div>
      `;
    });
  });

  listContainer.innerHTML = html;
}

function updateRhythmLabel(val) {
  const lbl = document.getElementById("rhythm-label");
  if (!lbl) return;
  const map = { "1": "~12s per shot", "2": "~9s per shot", "3": "~7s per shot", "4": "~5s per shot", "5": "~3s per shot" };
  lbl.textContent = map[val] || "~7s per shot";
}

function selectAlternative(segId, shotId, newPath) {
  if (!currentScriptData) return;
  currentScriptData.segments.forEach(seg => {
    if (seg.segment_id == segId) {
      (seg.shots || []).forEach(shot => {
        if (shot.shot_id == shotId) {
          shot.source = "library";
          shot.image_path = newPath;
        }
      });
    }
  });

  refreshStoryboardCoverage();
}

function openReplaceModal(segId, shotId) {
  activeReplaceShot = { segId, shotId };
  const modal = document.getElementById("replace-modal");
  if (modal) modal.classList.remove("hidden");
}

function closeReplaceModal() {
  activeReplaceShot = null;
  const modal = document.getElementById("replace-modal");
  if (modal) modal.classList.add("hidden");
}

function confirmReplace(actionType) {
  closeReplaceModal();
  refreshStoryboardCoverage();
}

// ── Render Screen Execution & Log Updates ────────────────────────────────────
async function startRenderFromBoard() {
  if (!currentScriptPath && !isWebMode) {
    alert("Please save draft script before rendering.");
    return;
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
    isRendering = false;
    btn.textContent = "Start Render";
    btn.className = "primary";
    document.getElementById("render-status-pill").className = "pill p-warn";
    document.getElementById("render-status-pill").textContent = "cancelled";
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

  document.getElementById("render-project-title").textContent = currentScriptData ? currentScriptData.project.title : "Smart Studio Project";

  if (!isWebMode) {
    const res = await window.pywebview.api.start_render(currentScriptPath);
    if (!res.success) {
      alert("Could not start render: " + res.error);
      isRendering = false;
      btn.textContent = "Start Render";
      btn.className = "primary";
    }
  }
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
  }

  if (event.type === "stage_start") {
    document.getElementById("render-human-step").textContent = `Stage: ${event.stage}`;
  }

  if (event.type === "segment_progress") {
    const curr = event.current || 0;
    const total = event.total || 1;
    const pct = Math.round((curr / total) * 100);

    document.getElementById("render-progress-bar").style.width = `${pct}%`;
    document.getElementById("render-human-step").textContent = `Composing segment ${curr} of ${total}`;
    document.getElementById("kv-narr-status").textContent = `${curr} / ${total}`;
    document.getElementById("kv-cap-status").textContent = `${curr} / ${total}`;
    document.getElementById("kv-shots-status").textContent = `${curr} / ${total}`;
  }

  if (event.type === "complete") {
    isRendering = false;
    const btn = document.getElementById("btn-render-action");
    if (btn) {
      btn.textContent = "Start Render";
      btn.className = "primary";
    }
    document.getElementById("render-progress-bar").style.width = "100%";
    document.getElementById("render-status-pill").className = "pill p-ok";
    document.getElementById("render-status-pill").textContent = "completed";
    document.getElementById("render-human-step").textContent = "Render completed successfully!";
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


// Bring an image made outside the app into the library, then re-plan so the shot fills.
async function importShotImage(query) {
  if (!window.pywebview) { alert("Image import is only available in the desktop app."); return; }
  try {
    const res = await window.pywebview.api.import_shot_image(query || "");
    if (res.cancelled) return;
    if (!res.success) { alert("Could not add the image: " + (res.error || "unknown error")); return; }
    await refreshStoryboardCoverage();
  } catch (e) {
    alert("Could not add the image: " + e.message);
  }
}
window.importShotImage = importShotImage;
