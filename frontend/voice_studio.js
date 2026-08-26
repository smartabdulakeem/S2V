/* ══════════════════════════════════════════════════════════════════════════
   VOICEOVER STUDIO
   Standalone speech generation: Supertonic, Edge-TTS, Google Cloud TTS,
   Kokoro, Piper, and OpenVoice V2 cloning.

   Engines are probed at runtime, so anything unavailable is disabled with the
   reason shown up front rather than failing halfway through a generation.
   ══════════════════════════════════════════════════════════════════════════ */

const EDGE_VOICES = [
  ["en-US-AriaNeural", "Aria — US female, warm"],
  ["en-US-GuyNeural", "Guy — US male, steady"],
  ["en-US-JennyNeural", "Jenny — US female, friendly"],
  ["en-US-ChristopherNeural", "Christopher — US male, deep"],
  ["en-GB-SoniaNeural", "Sonia — UK female"],
  ["en-GB-RyanNeural", "Ryan — UK male"],
  ["en-NG-EzinneNeural", "Ezinne — Nigerian female"],
  ["en-NG-AbeoNeural", "Abeo — Nigerian male"],
  ["en-AU-NatashaNeural", "Natasha — Australian female"],
  ["en-ZA-LeahNeural", "Leah — South African female"],
];

const SUPERTONIC_VOICES = [
  ["M1", "M1 — male, neutral"], ["M2", "M2 — male, warm"], ["M3", "M3 — male, bright"],
  ["M4", "M4 — male, deep"], ["M5", "M5 — male, soft"],
  ["F1", "F1 — female, neutral"], ["F2", "F2 — female, warm"], ["F3", "F3 — female, bright"],
  ["F4", "F4 — female, deep"], ["F5", "F5 — female, soft"],
];

/* Every entry below was called against this account key and returned 200.
   Google has no en-NG voices — the closest natural fits are the Indian and
   Australian Neural2 sets. */
const GOOGLE_VOICES = [
  ["en-US-Journey-F", "US female — Journey (most natural)"],
  ["en-US-Journey-D", "US male — Journey (most natural)"],
  ["en-US-Studio-O", "US female — Studio (premium)"],
  ["en-US-Studio-Q", "US male — Studio (premium)"],
  ["en-US-Neural2-F", "US female — Neural2"],
  ["en-US-Neural2-D", "US male — Neural2"],
  ["en-GB-Studio-C", "UK female — Studio"],
  ["en-GB-Studio-B", "UK male — Studio"],
  ["en-GB-Neural2-A", "UK female — Neural2"],
  ["en-GB-Neural2-B", "UK male — Neural2"],
  ["en-IN-Neural2-A", "Indian female — Neural2"],
  ["en-IN-Neural2-B", "Indian male — Neural2"],
  ["en-AU-Neural2-A", "Australian female — Neural2"],
  ["en-AU-Neural2-B", "Australian male — Neural2"],
];

const KOKORO_VOICES = [
  ["af_heart", "Heart — US female"], ["af_bella", "Bella — US female"],
  ["af_nicole", "Nicole — US female"], ["am_michael", "Michael — US male"],
  ["am_adam", "Adam — US male"], ["bf_emma", "Emma — UK female"],
  ["bm_george", "George — UK male"],
];

const OPENVOICE_LANGUAGES = [
  ["EN", "English (US)"], ["EN-BR", "English (British)"], ["EN-AU", "English (Australian)"],
  ["EN-INDIA", "English (India)"], ["ES", "Spanish"], ["FR", "French"],
  ["JP", "Japanese"], ["KR", "Korean"], ["ZH", "Chinese"],
];

let voiceEngines = {};
let voiceProfiles = [];
let voiceReferencePath = "";
let voiceCurrentClip = null;
let voiceBusy = false;
let voiceRecorder = null;
let voiceRecordChunks = [];

function voiceApiReady() {
  return window.pywebview && window.pywebview.api && window.pywebview.api.voice_probe_engines;
}

function escapeVoiceHtml(v) {
  return String(v == null ? "" : v).replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[ch]));
}

function toastVoice(msg) {
  if (typeof toast === "function") { toast(msg); return; }
  const el = document.getElementById("voice-status");
  if (el) el.textContent = msg; else console.warn(msg);
}

function setVoiceStatus(msg, busy) {
  const el = document.getElementById("voice-status");
  if (el) el.textContent = msg;
  const bar = document.getElementById("voice-progress-bar");
  if (bar) {
    bar.style.width = busy ? "100%" : "0%";
    bar.style.opacity = busy ? "1" : "0.35";
  }
}

/* ── init ────────────────────────────────────────────────────────────────── */

async function initVoiceStudio() {
  const textEl = document.getElementById("voice-text");
  if (textEl && !textEl.dataset.bound) {
    textEl.dataset.bound = "1";
    textEl.addEventListener("input", () => {
      document.getElementById("voice-char-count").textContent = textEl.value.length + " characters";
    });
  }

  if (!voiceApiReady()) {
    const note = document.getElementById("voice-engine-note");
    if (note) note.textContent = "Voiceover Studio needs the desktop app — it is not available in browser preview mode.";
    return;
  }

  await refreshVoiceEngines();
  await refreshVoiceProfiles();
  await refreshVoiceHistory();
}

async function refreshVoiceEngines() {
  const note = document.getElementById("voice-engine-note");
  const sel = document.getElementById("voice-engine");
  try {
    setVoiceStatus("Checking engines…", true);
    const res = await window.pywebview.api.voice_probe_engines();
    setVoiceStatus("Ready", false);
    if (!res.success) { note.textContent = res.error || "Could not probe engines."; return; }

    voiceEngines = res.engines || {};
    sel.innerHTML = "";
    ["supertonic", "edge", "google", "kokoro", "piper", "openvoice"].forEach(key => {
      const eng = voiceEngines[key];
      if (!eng) return;
      const opt = document.createElement("option");
      opt.value = key;
      opt.textContent = eng.ready ? eng.name : eng.name + " — unavailable";
      opt.disabled = !eng.ready;
      sel.appendChild(opt);
    });
    const firstReady = ["supertonic", "edge", "google", "kokoro", "piper", "openvoice"].find(k => voiceEngines[k] && voiceEngines[k].ready);
    if (firstReady) sel.value = firstReady;
    onVoiceEngineChange();
  } catch (e) {
    setVoiceStatus("Ready", false);
    note.textContent = "Engine probe failed: " + e;
  }
}

function onVoiceEngineChange() {
  const engineId = document.getElementById("voice-engine").value;
  const eng = voiceEngines[engineId] || {};
  const note = document.getElementById("voice-engine-note");
  const voiceSel = document.getElementById("voice-voice");
  const voiceNote = document.getElementById("voice-voice-note");
  const cloneCard = document.getElementById("voice-clone-card");
  const pitchNote = document.getElementById("voice-pitch-note");
  const pitchInput = document.getElementById("voice-pitch");

  if (!eng.ready && eng.blocker) {
    note.innerHTML = "<b>Unavailable.</b> " + escapeVoiceHtml(eng.blocker) +
      (eng.fix ? '<br><span class="mono">' + escapeVoiceHtml(eng.fix) + "</span>" : "");
  } else if (eng.offline) {
    note.textContent = "Runs fully offline on this machine.";
  } else {
    note.textContent = "Cloud voices, free, no API key needed.";
  }

  voiceSel.innerHTML = "";
  cloneCard.style.display = engineId === "openvoice" ? "" : "none";

  const pitchSupported = !!eng.supports_pitch;
  pitchInput.disabled = !pitchSupported;
  pitchNote.textContent = pitchSupported ? "" : "This engine does not support pitch shifting.";

  if (engineId === "edge") {
    EDGE_VOICES.forEach(pair => voiceSel.add(new Option(pair[1], pair[0])));
    voiceNote.textContent = "";
  } else if (engineId === "supertonic") {
    SUPERTONIC_VOICES.forEach(pair => voiceSel.add(new Option(pair[1], pair[0])));
    voiceNote.textContent = "Offline. First clip of a session takes ~14s while the model loads, then ~3s each.";
  } else if (engineId === "google") {
    GOOGLE_VOICES.forEach(pair => voiceSel.add(new Option(pair[1], pair[0])));
    voiceNote.textContent = "Uses the Google API key from Settings.";
  } else if (engineId === "kokoro") {
    KOKORO_VOICES.forEach(pair => voiceSel.add(new Option(pair[1], pair[0])));
    voiceNote.textContent = "";
  } else if (engineId === "piper") {
    (eng.models || []).forEach(m => voiceSel.add(new Option(m, m)));
    voiceNote.textContent = (eng.models && eng.models.length) ? "" : "No Piper models installed.";
  } else if (engineId === "openvoice") {
    const avail = (eng.languages && eng.languages.length)
      ? OPENVOICE_LANGUAGES.filter(p => eng.languages.indexOf(p[0]) !== -1)
      : OPENVOICE_LANGUAGES;
    (avail.length ? avail : OPENVOICE_LANGUAGES).forEach(p => voiceSel.add(new Option(p[1], p[0])));
    voiceNote.textContent = "Cloning runs on " + (eng.device || "cpu") + ". CPU is slow for long scripts.";
  }
}

/* ── reference audio ─────────────────────────────────────────────────────── */

async function pickVoiceReference() {
  try {
    const path = await window.pywebview.api.voice_pick_reference();
    if (!path) return;
    voiceReferencePath = path;
    document.getElementById("voice-ref-status").textContent = path.split(/[\\/]/).pop();
  } catch (e) {
    toastVoice("Could not open the file picker: " + e);
  }
}

async function toggleVoiceRecording() {
  const btn = document.getElementById("voice-record-btn");
  const status = document.getElementById("voice-ref-status");

  if (voiceRecorder && voiceRecorder.state === "recording") {
    voiceRecorder.stop();
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    toastVoice("Microphone capture is not available in this window.");
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    voiceRecordChunks = [];
    voiceRecorder = new MediaRecorder(stream);

    voiceRecorder.ondataavailable = e => { if (e.data.size) voiceRecordChunks.push(e.data); };
    voiceRecorder.onstop = () => {
      stream.getTracks().forEach(t => t.stop());
      btn.textContent = "Record from microphone";
      status.textContent = "Saving recording…";

      const blob = new Blob(voiceRecordChunks, { type: "audio/webm" });
      const reader = new FileReader();
      reader.onloadend = async () => {
        try {
          const res = await window.pywebview.api.voice_save_recording(reader.result, ".webm");
          if (res.success) {
            voiceReferencePath = res.path;
            status.textContent = "Recorded sample ready";
          } else {
            status.textContent = "Recording failed";
            toastVoice(res.error || "Could not save the recording.");
          }
        } catch (e) {
          status.textContent = "Recording failed";
          toastVoice("Could not save the recording: " + e);
        }
      };
      reader.readAsDataURL(blob);
    };

    voiceRecorder.start();
    btn.textContent = "Stop recording";
    status.textContent = "Recording… speak for 5–10 seconds";
  } catch (e) {
    toastVoice("Microphone access was refused: " + e);
  }
}

/* ── profiles ────────────────────────────────────────────────────────────── */

async function refreshVoiceProfiles() {
  try {
    const res = await window.pywebview.api.voice_list_profiles();
    voiceProfiles = res.success ? (res.profiles || []) : [];
  } catch (e) { voiceProfiles = []; }

  const sel = document.getElementById("voice-profile-select");
  sel.innerHTML = "";
  sel.add(new Option(voiceProfiles.length ? "— pick a saved voice —" : "No saved profiles yet", ""));
  voiceProfiles.forEach(p => sel.add(new Option(p.name, p.id)));
}

async function saveVoiceProfile() {
  const name = document.getElementById("voice-profile-name").value.trim();
  if (!name) { toastVoice("Give the voice profile a name first."); return; }
  if (!voiceReferencePath) { toastVoice("Choose or record a reference clip first."); return; }

  const lang = document.getElementById("voice-voice").value || "EN";
  try {
    const res = await window.pywebview.api.voice_save_profile(name, voiceReferencePath, lang);
    if (!res.success) { toastVoice(res.error || "Could not save the profile."); return; }
    document.getElementById("voice-profile-name").value = "";
    await refreshVoiceProfiles();
    toastVoice('Saved voice profile "' + name + '".');
  } catch (e) { toastVoice("Could not save the profile: " + e); }
}

function useVoiceProfile() {
  const id = document.getElementById("voice-profile-select").value;
  const profile = voiceProfiles.find(p => p.id === id);
  if (!profile) return;
  voiceReferencePath = profile.reference;
  document.getElementById("voice-ref-status").textContent = "Profile: " + profile.name;
  if (profile.language) {
    const sel = document.getElementById("voice-voice");
    if (Array.prototype.some.call(sel.options, o => o.value === profile.language)) {
      sel.value = profile.language;
    }
  }
}

async function deleteVoiceProfile() {
  const id = document.getElementById("voice-profile-select").value;
  if (!id) { toastVoice("Pick a profile to delete."); return; }
  const profile = voiceProfiles.find(p => p.id === id);
  if (!confirm('Delete voice profile "' + (profile ? profile.name : id) + '"?')) return;
  try {
    const res = await window.pywebview.api.voice_delete_profile(id);
    if (!res.success) { toastVoice(res.error || "Could not delete the profile."); return; }
    voiceReferencePath = "";
    document.getElementById("voice-ref-status").textContent = "No reference selected";
    await refreshVoiceProfiles();
  } catch (e) { toastVoice("Could not delete the profile: " + e); }
}

/* ── generation ──────────────────────────────────────────────────────────── */

async function generateVoiceover() {
  if (voiceBusy) return;

  const text = document.getElementById("voice-text").value.trim();
  if (!text) { toastVoice("Enter some text to speak."); return; }

  const engine = document.getElementById("voice-engine").value;
  const eng = voiceEngines[engine] || {};
  if (!eng.ready) { toastVoice(eng.blocker || "That engine is not available."); return; }
  if (engine === "openvoice" && !voiceReferencePath) {
    toastVoice("Choose, record, or load a reference voice clip first.");
    return;
  }

  const btn = document.getElementById("voice-generate-btn");
  voiceBusy = true;
  btn.disabled = true;
  btn.textContent = "Generating…";
  setVoiceStatus(engine === "openvoice"
    ? "Cloning voice — this can take a few minutes on CPU…"
    : "Generating…", true);

  const payload = {
    engine: engine,
    text: text,
    speed: parseFloat(document.getElementById("voice-speed").value) || 1.0,
    pitch: parseFloat(document.getElementById("voice-pitch").value) || 0.0,
    label: text.slice(0, 24),
  };
  if (engine === "openvoice") {
    payload.reference_audio = voiceReferencePath;
    payload.language = document.getElementById("voice-voice").value || "EN";
  } else {
    payload.voice = document.getElementById("voice-voice").value;
  }

  try {
    const res = await window.pywebview.api.voice_generate(payload);
    if (!res.success) {
      setVoiceStatus("Failed", false);
      toastVoice(res.error || "Generation failed.");
      return;
    }
    voiceCurrentClip = res.entry;
    await loadVoiceClipIntoPlayer(res.entry);
    setVoiceStatus("Done in " + res.entry.elapsed + "s", false);
    await refreshVoiceHistory();
  } catch (e) {
    setVoiceStatus("Failed", false);
    toastVoice("Generation failed: " + e);
  } finally {
    voiceBusy = false;
    btn.disabled = false;
    btn.textContent = "Generate Voiceover";
  }
}

async function loadVoiceClipIntoPlayer(entry) {
  try {
    const res = await window.pywebview.api.voice_read_audio(entry.path);
    if (!res.success) { toastVoice(res.error || "Could not load the audio."); return; }
    const player = document.getElementById("voice-player");
    player.src = res.data_url;
    document.getElementById("voice-player-wrap").style.display = "";
    document.getElementById("voice-dl-mp3").style.display = entry.mp3 ? "" : "none";
    document.getElementById("voice-clip-meta").textContent =
      entry.engine + " · " + entry.chars + " chars · " + entry.elapsed + "s";
    voiceCurrentClip = entry;
  } catch (e) { toastVoice("Could not load the audio: " + e); }
}

async function downloadVoiceClip(kind) {
  if (!voiceCurrentClip) { toastVoice("Generate a clip first."); return; }
  const src = (kind === "mp3" && voiceCurrentClip.mp3) ? voiceCurrentClip.mp3 : voiceCurrentClip.path;
  try {
    const res = await window.pywebview.api.voice_download(src, voiceCurrentClip.label || "voiceover");
    if (res.cancelled) return;
    if (!res.success) { toastVoice(res.error || "Could not save the file."); return; }
    toastVoice("Saved to " + res.path);
  } catch (e) { toastVoice("Could not save the file: " + e); }
}

async function openVoiceOutputFolder() {
  try { await window.pywebview.api.voice_open_output_folder(); }
  catch (e) { toastVoice("Could not open the folder: " + e); }
}

/* ── history ─────────────────────────────────────────────────────────────── */

async function refreshVoiceHistory() {
  const body = document.getElementById("voice-history-body");
  let history = [];
  try {
    const res = await window.pywebview.api.voice_list_history();
    history = res.success ? (res.history || []) : [];
  } catch (e) { history = []; }

  body.innerHTML = "";
  if (!history.length) {
    body.innerHTML = '<tr><td colspan="5" class="mono">No clips yet.</td></tr>';
    return;
  }
  history.forEach(h => {
    const tr = document.createElement("tr");
    tr.innerHTML =
      '<td class="mono">' + escapeVoiceHtml(h.created_at || "") + "</td>" +
      "<td>" + escapeVoiceHtml(h.engine || "") + "</td>" +
      "<td>" + escapeVoiceHtml((h.text_preview || "").slice(0, 60)) + "</td>" +
      '<td class="mono">' + escapeVoiceHtml(String(h.elapsed || "-")) + "s</td>" +
      "<td></td>";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ghost";
    btn.textContent = "Load";
    btn.onclick = () => loadVoiceClipIntoPlayer(h);
    tr.lastElementChild.appendChild(btn);
    body.appendChild(tr);
  });
}

async function clearVoiceHistory() {
  if (!confirm("Clear the recent clips list? The audio files stay on disk.")) return;
  try {
    await window.pywebview.api.voice_clear_history();
    await refreshVoiceHistory();
  } catch (e) { toastVoice("Could not clear history: " + e); }
}
