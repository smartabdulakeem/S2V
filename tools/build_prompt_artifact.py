#!/usr/bin/env python
"""
Render `library/prompt_pack.jsonl` into a single self-contained HTML page.

The markdown pack is 991 KB and unusable for the job it exists to do: copying
50 or 100 prompts at a time into an image generator, and remembering which ones
are already done. This page does that. It is generated, never hand-edited, so
`build_prompt_pack.py` remains the one source of truth.

    python tools/build_prompt_pack.py --total 2000
    python tools/build_prompt_artifact.py
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "library", "prompt_pack.jsonl")
OUT = os.path.join(ROOT, "library", "prompt-pack.html")

# Raw string: the JavaScript below contains \n escapes that belong to the browser,
# not to Python. Without the r prefix Python turns them into real newlines and
# breaks the string literals they sit in.
PAGE = r"""<title>Smart Studio Prompt Pack</title>
<style>
  /* Light palette on the bare :root so the un-stamped "system" state resolves.
     Neutrals carry a slight blue bias toward the indigo accent, so the greys
     read as chosen rather than inherited. */
  :root {
    --ground:   #eef0f4;
    --surface:  #ffffff;
    --raised:   #f7f8fa;
    --ink:      #15181f;
    --muted:    #616a7d;
    --faint:    #8b93a4;
    --rule:     #d9dde5;
    --accent:   #3a4788;
    --accent-soft: #e6e9f6;
    --done:     #3f6d52;
    --done-soft:#e3efe7;
    --shadow:   0 1px 2px rgba(21, 24, 31, .06), 0 4px 12px rgba(21, 24, 31, .04);
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --ground:   #0f1116;
      --surface:  #171a21;
      --raised:   #1d212a;
      --ink:      #e7eaf1;
      --muted:    #99a2b4;
      --faint:    #6a7286;
      --rule:     #2a2f3a;
      --accent:   #97a4e8;
      --accent-soft: #232841;
      --done:     #7fb694;
      --done-soft:#1c2b23;
      --shadow:   0 1px 2px rgba(0, 0, 0, .4), 0 4px 14px rgba(0, 0, 0, .3);
    }
  }
  :root[data-theme="dark"] {
    --ground:   #0f1116;
    --surface:  #171a21;
    --raised:   #1d212a;
    --ink:      #e7eaf1;
    --muted:    #99a2b4;
    --faint:    #6a7286;
    --rule:     #2a2f3a;
    --accent:   #97a4e8;
    --accent-soft: #232841;
    --done:     #7fb694;
    --done-soft:#1c2b23;
    --shadow:   0 1px 2px rgba(0, 0, 0, .4), 0 4px 14px rgba(0, 0, 0, .3);
  }

  * { box-sizing: border-box; }

  body {
    background: var(--ground);
    color: var(--ink);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    font-size: 15px;
    line-height: 1.5;
    margin: 0;
    padding: 0 20px 80px;
  }

  /* Prompts are machine text on their way to a generator, so they are set in a
     mono face: it makes a truncated or malformed prompt obvious at a glance. */
  .mono { font-family: ui-monospace, "Cascadia Code", "SF Mono", Consolas, monospace; }

  .wrap { max-width: 1100px; margin: 0 auto; }

  header { padding: 40px 0 22px; }
  h1 {
    font-size: clamp(26px, 3.4vw, 38px);
    line-height: 1.1;
    letter-spacing: -.02em;
    margin: 0 0 10px;
    text-wrap: balance;
  }
  .lede { color: var(--muted); margin: 0; max-width: 62ch; }
  .lede b { color: var(--ink); font-weight: 600; }

  /* -- progress ----------------------------------------------------------- */
  .progress { margin-top: 22px; display: flex; flex-direction: column; gap: 7px; }
  .bar { height: 6px; border-radius: 3px; background: var(--rule); overflow: hidden; }
  .bar > span {
    display: block; height: 100%; width: 0;
    background: var(--done); border-radius: 3px;
    transition: width .35s ease;
  }
  @media (prefers-reduced-motion: reduce) { .bar > span { transition: none; } }
  .progress-line {
    display: flex; justify-content: space-between; gap: 16px;
    font-size: 13px; color: var(--muted);
    font-variant-numeric: tabular-nums;
  }

  /* -- controls ----------------------------------------------------------- */
  .controls {
    position: sticky; top: 0; z-index: 10;
    background: var(--surface);
    border: 1px solid var(--rule); border-radius: 10px;
    padding: 14px; margin: 22px 0 20px;
    display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end;
    box-shadow: var(--shadow);
  }
  .field { display: flex; flex-direction: column; gap: 5px; }
  .field > label {
    font-size: 11px; letter-spacing: .07em; text-transform: uppercase;
    color: var(--faint); font-weight: 600;
  }
  select, button {
    font: inherit; color: var(--ink);
    background: var(--raised);
    border: 1px solid var(--rule); border-radius: 7px;
    padding: 8px 11px; cursor: pointer;
  }
  select { min-width: 150px; }
  button:hover, select:hover { border-color: var(--accent); }
  button:focus-visible, select:focus-visible, .row-check:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px;
  }
  button.primary {
    background: var(--accent); border-color: var(--accent);
    color: #fff; font-weight: 600;
  }
  :root[data-theme="dark"] button.primary,
  :root:not([data-theme="light"]) button.primary { color: #10131b; }
  @media (prefers-color-scheme: light) {
    :root:not([data-theme="dark"]) button.primary { color: #fff; }
  }
  button:disabled { opacity: .4; cursor: not-allowed; }
  .spacer { flex: 1 1 auto; }
  .pager { display: flex; align-items: center; gap: 8px; }
  .pager .count {
    font-size: 13px; color: var(--muted); min-width: 128px; text-align: center;
    font-variant-numeric: tabular-nums;
  }

  /* -- rows --------------------------------------------------------------- */
  .rows { display: flex; flex-direction: column; gap: 8px; }
  .row {
    background: var(--surface);
    border: 1px solid var(--rule); border-left: 3px solid var(--rule);
    border-radius: 8px; padding: 12px 14px;
    display: grid; grid-template-columns: auto 1fr; gap: 12px; align-items: start;
  }
  .row.is-done { border-left-color: var(--done); background: var(--done-soft); }
  .row-check {
    appearance: none; width: 19px; height: 19px; margin: 2px 0 0;
    border: 1.5px solid var(--faint); border-radius: 5px;
    background: var(--surface); cursor: pointer; flex: none;
  }
  .row-check:checked {
    background: var(--done); border-color: var(--done);
  }
  .row-check:checked::after {
    content: "\2713"; display: block; color: var(--surface);
    font-size: 13px; line-height: 16px; text-align: center; font-weight: 700;
  }
  .row-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; margin-bottom: 6px; }
  .id {
    font-size: 11px; font-weight: 700; letter-spacing: .04em;
    color: var(--accent); background: var(--accent-soft);
    padding: 2px 7px; border-radius: 4px;
  }
  .fname { font-size: 12.5px; color: var(--muted); word-break: break-all; }
  .cat { font-size: 11px; color: var(--faint); letter-spacing: .04em; }
  .prompt { font-size: 13px; line-height: 1.55; color: var(--ink); }
  .row.is-done .prompt { color: var(--muted); }

  /* -- copy sheet --------------------------------------------------------- */
  dialog {
    border: 1px solid var(--rule); border-radius: 12px;
    background: var(--surface); color: var(--ink);
    padding: 0; width: min(820px, 92vw); box-shadow: var(--shadow);
  }
  dialog::backdrop { background: rgba(8, 10, 15, .55); }
  .sheet-head {
    display: flex; justify-content: space-between; align-items: center; gap: 14px;
    padding: 15px 18px; border-bottom: 1px solid var(--rule);
  }
  .sheet-head h2 { margin: 0; font-size: 16px; }
  dialog textarea {
    width: 100%; height: 46vh; border: 0; resize: vertical;
    padding: 16px 18px; background: var(--surface); color: var(--ink);
    font-family: ui-monospace, "Cascadia Code", "SF Mono", Consolas, monospace;
    font-size: 12.5px; line-height: 1.6;
  }
  dialog textarea:focus { outline: none; }
  .sheet-foot {
    display: flex; gap: 10px; align-items: center;
    padding: 13px 18px; border-top: 1px solid var(--rule);
  }
  .hint { font-size: 12.5px; color: var(--muted); }

  .tag-copied {
    font-size: 10.5px; font-weight: 700; letter-spacing: .06em;
    text-transform: uppercase; color: var(--done);
    border: 1px solid var(--done); border-radius: 4px; padding: 1px 5px;
  }
  .warn {
    background: var(--done-soft); border: 1px solid var(--done);
    border-radius: 8px; padding: 10px 13px; font-size: 13px; color: var(--ink);
  }

  .empty { padding: 44px; text-align: center; color: var(--muted); }
  footer {
    margin-top: 34px; padding-top: 18px;
    border-top: 1px solid var(--rule);
    font-size: 12.5px; color: var(--faint);
  }
  footer code {
    font-family: ui-monospace, Consolas, monospace;
    background: var(--raised); padding: 1px 5px; border-radius: 4px; color: var(--muted);
  }
</style>

<div class="wrap">
  <header>
    <h1>Smart Studio Prompt Pack</h1>
    <p class="lede">
      <b>__TOTAL__ image prompts</b> for the Smart Studio library. Filter to a group,
      copy a batch, generate the images, then save each one under the filename shown
      beside its prompt &mdash; the number and the subject words are both how the app
      finds the picture again.
      <br><br>
      Copies <b>one prompt per line</b>, ready to paste straight into a batch
      generator. Anything you copy is <b>marked automatically</b> and stays in
      place wearing a <b>copied</b> tag, so you can always see what has already
      gone out &mdash; and copy it again if you want to. Switch <b>Show</b> to
      <i>Not copied yet</i> to hide them. Use <b>Copy as</b> to fold the filename
      into the line itself if your generator names its output from the prompt text.
    </p>
    <div class="progress">
      <div class="bar"><span id="bar-fill"></span></div>
      <div class="progress-line">
        <span id="progress-text">0 of __TOTAL__ done</span>
        <span id="filter-text"></span>
      </div>
    </div>
  </header>

  <div class="controls">
    <div class="field">
      <label for="f-group">Group</label>
      <select id="f-group"></select>
    </div>
    <div class="field">
      <label for="f-show">Show</label>
      <select id="f-show">
        <option value="all" selected>All prompts</option>
        <option value="todo">Not copied yet</option>
        <option value="done">Already copied</option>
      </select>
    </div>
    <div class="field">
      <label for="f-size">Batch size</label>
      <select id="f-size">
        <option value="25">25</option>
        <option value="50" selected>50</option>
        <option value="100">100</option>
      </select>
    </div>
    <div class="field">
      <label for="f-format">Copy as</label>
      <select id="f-format">
        <option value="plain" selected>Prompt only</option>
        <option value="lead">Name first, then prompt</option>
        <option value="trail">Prompt, then name</option>
      </select>
    </div>
    <div class="spacer"></div>
    <div class="pager">
      <button id="prev" type="button" aria-label="Previous batch">&larr;</button>
      <span class="count" id="batch-count"></span>
      <button id="next" type="button" aria-label="Next batch">&rarr;</button>
    </div>
    <button class="primary" id="copy-batch" type="button">Copy this batch</button>
    <button id="mark-batch" type="button">Mark batch copied</button>
    <button id="undo-batch" type="button">Undo last copy</button>
  </div>

  <div class="rows" id="rows"></div>

  <footer>
    Generated from <code>library/prompt_pack.jsonl</code> by
    <code>tools/build_prompt_artifact.py</code>. Regenerate rather than editing by hand.
    Progress is remembered in this browser only.
  </footer>
</div>

<dialog id="sheet">
  <div class="sheet-head">
    <h2 id="sheet-title">Copy prompts</h2>
    <button id="sheet-close" type="button">Close</button>
  </div>
  <textarea id="sheet-text" readonly spellcheck="false"></textarea>
  <div class="sheet-foot">
    <button class="primary" id="sheet-copy" type="button">Copy to clipboard</button>
    <span class="hint" id="sheet-hint">Or select the text above and copy it yourself.</span>
  </div>
</dialog>

<script>
const DATA = __DATA__;
/* v2: "done" used to mean a box the user ticked by hand. It now means "copied",
   set automatically, so the old set would mislead if it were carried over. */
const STORE = "smartstudio.promptpack.copied.v2";
let lastCopied = [];

let done = new Set();
try { done = new Set(JSON.parse(localStorage.getItem(STORE) || "[]")); } catch (e) {}

const el = (id) => document.getElementById(id);
let batch = 0;

/** Human label for a group key, e.g. "hands_and_gesture" -> "Hands and gesture". */
function label(key) {
  const s = key.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function buildGroups() {
  const sel = el("f-group");
  const universal = [...new Set(DATA.filter(r => r.tier === "universal").map(r => r.category))].sort();
  const niche = [...new Set(DATA.filter(r => r.tier === "niche").map(r => r.category))].sort();

  const opt = (v, t) => { const o = document.createElement("option"); o.value = v; o.textContent = t; return o; };
  sel.appendChild(opt("all", `Everything (${DATA.length})`));

  const uniCount = DATA.filter(r => r.tier === "universal").length;
  sel.appendChild(opt("tier:universal", `- Universal, fits any niche (${uniCount})`));
  const gu = document.createElement("optgroup"); gu.label = "Universal";
  universal.forEach(c => gu.appendChild(opt("cat:" + c, `${label(c)} (${DATA.filter(r => r.category === c).length})`)));
  sel.appendChild(gu);

  const nicheCount = DATA.filter(r => r.tier === "niche").length;
  sel.appendChild(opt("tier:niche", `- All series packs (${nicheCount})`));
  const gn = document.createElement("optgroup"); gn.label = "Series packs";
  niche.forEach(c => gn.appendChild(opt("cat:" + c, `${label(c)} (${DATA.filter(r => r.category === c).length})`)));
  sel.appendChild(gn);
}

function filtered() {
  const g = el("f-group").value;
  const show = el("f-show").value;
  return DATA.filter(r => {
    if (g.startsWith("tier:") && r.tier !== g.slice(5)) return false;
    if (g.startsWith("cat:") && r.category !== g.slice(4)) return false;
    if (show === "todo" && done.has(r.id)) return false;
    if (show === "done" && !done.has(r.id)) return false;
    return true;
  });
}

function currentBatch() {
  const size = Number(el("f-size").value);
  const rows = filtered();
  const pages = Math.max(1, Math.ceil(rows.length / size));
  if (batch >= pages) batch = pages - 1;
  if (batch < 0) batch = 0;
  return { rows: rows.slice(batch * size, batch * size + size), total: rows.length, pages, size };
}

function save() {
  try { localStorage.setItem(STORE, JSON.stringify([...done])); } catch (e) {}
}

function render() {
  const { rows, total, pages, size } = currentBatch();
  const host = el("rows");
  host.innerHTML = "";

  if (!rows.length) {
    const d = document.createElement("div");
    d.className = "empty";
    d.textContent = el("f-show").value === "todo"
      ? "Every prompt in this group has been copied. Switch Show to see them again."
      : "Nothing here. Try a different group.";
    host.appendChild(d);
  }

  // Warn before the mistake, not after: this only appears when the visible batch
  // holds prompts that went out already.
  const repeats = rows.filter(r => done.has(r.id)).length;
  if (repeats) {
    const w = document.createElement("div");
    w.className = "warn";
    w.textContent = repeats === rows.length
      ? `All ${repeats} of these were copied before.`
      : `${repeats} of these ${rows.length} were copied before.`;
    host.appendChild(w);
  }

  for (const r of rows) {
    const row = document.createElement("div");
    row.className = "row" + (done.has(r.id) ? " is-done" : "");

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "row-check";
    cb.checked = done.has(r.id);
    cb.setAttribute("aria-label", "Mark " + r.id + " copied");
    cb.addEventListener("change", () => {
      cb.checked ? done.add(r.id) : done.delete(r.id);
      save(); render();
    });

    const body = document.createElement("div");
    const head = document.createElement("div");
    head.className = "row-head";

    const id = document.createElement("span");
    id.className = "id"; id.textContent = r.id;
    const fn = document.createElement("span");
    fn.className = "fname mono"; fn.textContent = r.filename;
    const cat = document.createElement("span");
    cat.className = "cat"; cat.textContent = label(r.category);
    head.append(id, fn, cat);
    if (done.has(r.id)) {
      const tag = document.createElement("span");
      tag.className = "tag-copied"; tag.textContent = "copied";
      head.appendChild(tag);
    }

    const p = document.createElement("p");
    p.className = "prompt mono"; p.textContent = r.prompt;

    body.append(head, p);
    row.append(cb, body);
    host.appendChild(row);
  }

  const start = total ? batch * size + 1 : 0;
  const end = Math.min(batch * size + size, total);
  el("batch-count").textContent = total
    ? `${start}\u2013${end} of ${total}` : "none";
  el("prev").disabled = batch <= 0;
  el("next").disabled = batch >= pages - 1;

  const pct = DATA.length ? (done.size / DATA.length) * 100 : 0;
  el("bar-fill").style.width = pct + "%";
  el("progress-text").textContent =
    `${done.size} of ${DATA.length} copied - ${DATA.length - done.size} still to go`;
  el("filter-text").textContent = `batch ${batch + 1} of ${pages}`;
}

/* -- copying ---------------------------------------------------------------
   ONE PROMPT PER LINE, always. A batch generator reads a pasted block a line at
   a time, so anything sitting on its own line becomes its own image request.
   An earlier version put the filename on a line above each prompt, which would
   have generated a picture of the filename.                                  */
function batchText() {
  const { rows } = currentBatch();
  const fmt = el("f-format").value;
  return rows.map((r) => {
    // Drop the extension: the id and subject words are the useful part, and
    // ".jpg" inside a prompt is just noise for the model to ignore.
    const name = r.filename.replace(/\.jpg$/, "");
    if (fmt === "lead") return `${name}, ${r.prompt}`;
    if (fmt === "trail") return `${r.prompt} ${name}`;
    return r.prompt;
  }).join("\n");
}

async function openSheet() {
  const { rows } = currentBatch();
  if (!rows.length) return;
  el("sheet-title").textContent =
    `Copy ${rows.length} prompt${rows.length > 1 ? "s" : ""} - one per line`;
  el("sheet-text").value = batchText();
  el("sheet-hint").textContent = "Or select the text above and copy it yourself.";
  el("sheet").showModal();
  el("sheet-text").focus();
  el("sheet-text").setSelectionRange(0, 0);
}

/* Copying is what marks a prompt used. Requiring a second click on a separate
   "mark done" button meant the only thing standing between the user and copying
   the same 50 prompts twice was remembering to press it. */
function markCopied(rows) {
  lastCopied = rows.map(r => r.id).filter(id => !done.has(id));
  lastCopied.forEach(id => done.add(id));
  save();
  el("undo-batch").disabled = lastCopied.length === 0;
  render();
}

/* Marking must NOT depend on the clipboard call succeeding. Sandboxed viewers
   block `navigator.clipboard`, and when that happens the user still copies the
   text by hand with Ctrl+C - so keying the mark off the API would silently stop
   tracking in exactly the place this page is meant to run. The batch is marked
   either way; the hint says which happened, and Undo is one click. */
async function copyText() {
  const text = el("sheet-text").value;
  const rows = currentBatch().rows;
  let ok = true;
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    el("sheet-text").select();
    try {
      ok = document.execCommand("copy");
    } catch (e2) {
      ok = false;
    }
  }
  markCopied(rows);
  el("sheet-hint").textContent = ok
    ? `Copied ${rows.length}, and marked so they will not come round again.`
    : `The text is selected - press Ctrl+C to copy it. All ${rows.length} are `
      + `marked; press Undo last copy if that was wrong.`;
}

el("copy-batch").addEventListener("click", openSheet);
el("sheet-copy").addEventListener("click", copyText);
el("sheet-close").addEventListener("click", () => el("sheet").close());
el("mark-batch").addEventListener("click", () => markCopied(currentBatch().rows));
el("undo-batch").addEventListener("click", () => {
  lastCopied.forEach(id => done.delete(id));
  lastCopied = [];
  save();
  el("undo-batch").disabled = true;
  render();
});
el("prev").addEventListener("click", () => { batch--; render(); });
el("next").addEventListener("click", () => { batch++; render(); });
["f-group", "f-show", "f-size"].forEach(id =>
  el(id).addEventListener("change", () => { batch = 0; render(); }));
// Format changes the copied text, not the batch, so it must not reset the page.
el("f-format").addEventListener("change", render);

buildGroups();
el("undo-batch").disabled = true;
render();
</script>
"""


def main() -> None:
    with open(SRC, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]

    slim = [
        {"id": r["id"], "tier": r["tier"], "category": r["category"],
         "filename": r["filename"], "prompt": r["prompt"]}
        for r in rows
    ]
    payload = json.dumps(slim, ensure_ascii=False, separators=(",", ":"))
    # A literal </script> inside the JSON would close the tag early.
    payload = payload.replace("</", "<\\/")

    html = PAGE.replace("__DATA__", payload).replace("__TOTAL__", f"{len(slim):,}")
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"{len(slim)} prompts -> {OUT}  ({os.path.getsize(OUT) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
