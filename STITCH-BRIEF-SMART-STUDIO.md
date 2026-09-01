# Design brief for Google Stitch — Smart Studio

Paste everything below the line into Google Stitch as one prompt.

---

## What I am building

**Smart Studio** is a Windows desktop application for one person who makes narrated
documentary-style videos on their own. You write or paste a script, the app plans which
pictures go where, finds or generates the images, records the narration, lays it all on a
timeline, and renders a finished film.

It is not a consumer app and not a web SaaS. It is a **workbench for a single professional
operator** who uses it for hours at a time and knows exactly what every control does. Density
and information beat friendliness. Nothing should be hidden behind a wizard.

Design **six screens plus a settings screen**, in both a dark and a light theme.

## Who uses it

One person, wearing four hats: marketer, educator, software developer, entrepreneur. They are
not a beginner. They want to see the numbers, override any automatic decision, and be told
plainly when something failed. They work on a large desktop monitor, keyboard-heavy, and they
are often reviewing sixty items in a row.

## Platform and hard constraints

- **Desktop application** in an embedded browser window, roughly 1440×900 up to 2560×1440.
  Not responsive to phone sizes. No mobile layout.
- **Dark theme is the default.** A light theme must exist and be equally finished.
- **No login, no account, no onboarding, no marketing page, no pricing page, no dashboard
  greeting.** The app opens straight into work.
- Left vertical navigation rail, always visible, with number-key shortcuts.
- Everything must work offline. Never design anything that implies a cloud service.

## Visual direction

Not a bright startup SaaS look. Think **a well-made instrument**: quiet, dense, precise,
slightly editorial. Closer to a professional audio or film tool than to a productivity web app.

Use this exact palette.

**Dark theme (default)**
- Page background `#0E1319`
- Panel surface `#161D25`
- Hairline borders `#2B3641`
- Primary text `#E6ECF2`
- Accent — brass `#D6A455`
- Good / matched `#43B491`
- Warning / weak `#E0964C`
- Problem / gap `#DF7168`

**Light theme**
- Page background `#EFF1F4`
- Panel surface `#FFFFFF`
- Hairline borders `#CDD4DC`
- Primary text `#111820`
- Accent — brass `#9A6E2A`
- Good `#1C7A5E`
- Warning `#B4600F`
- Problem `#A83A32`

**Type.** A clean system sans for prose and UI. A **monospace face for every number** —
timecodes, durations, counts, line numbers, file paths. This is important: numbers must line up
in columns and be instantly scannable.

**Surfaces.** Flat panels with 1px hairline borders and small radii. Minimal shadow. No
gradients, no glassmorphism, no large rounded cards, no illustrations, no stock photography, no
emoji in the interface.

## Navigation

A narrow left rail, full height, with the product name at the top and these items in order,
each showing its number-key shortcut:

1. **Script**
2. **Storyboard**
3. **Timeline**
4. **Render**
5. **Library**
6. **Voiceover**

**Settings** sits at the bottom of the rail, separated.

A slim application header above the workspace holds the project name, a theme toggle, and a
version badge.

---

# The six screens

## 1. Script

Where a film begins.

- A large plain-text editor filling most of the screen, holding the narration script. Line
  numbers down the left edge. No rich-text formatting toolbar — this is plain narration text.
- A right-hand settings column, roughly 320px, containing:
  - **Series / niche** dropdown (this controls the visual style rules for the whole film)
  - **Narrator voice** dropdown with a "Preview voice" button beside it
  - **Voice speed** and **pitch** as small numeric steppers
  - **Narrative tone** dropdown
- A footer strip showing live counts in monospace: word count, estimated runtime, number of
  script lines.
- One primary action, bottom right: **Plan storyboard →**
- A quiet status line at the top right: `draft · not yet planned`.

**Empty state:** the editor shows a paste prompt and two buttons — *Paste a script* and
*Open a file*.

## 2. Storyboard — the most important screen

This is where the operator spends most of their time. It answers one question: *which picture
covers which part of the narration, and is that picture any good?*

### Top bar — the planning controls

A single row of controls, left to right:

- A segmented toggle with two options: **Auto** and **Exact number**.
  - **Auto** selected: show two small numeric fields, "hold each picture between `8` and `75`
    seconds". The app decides how many pictures the film needs.
  - **Exact number** selected: show one numeric field, "use exactly `60` pictures". The range
    fields grey out. The field accepts anything from 1 upward — one single picture for an
    entire twenty-minute film is a legitimate, supported answer, and the interface must not
    fight it or warn against it.
- A **Re-plan pictures** button.
- A **Measure narration** button with a small state indicator beside it reading either
  `timings measured` in the good colour or `estimated from word count` in the warning colour.
  This matters: the plan is better when real audio has been measured.

### The counter strip

A horizontal row of large monospace figures with small labels underneath:

`48` matched · `7` weak · `5` gaps · `60` pictures · `18:22` runtime

Colour each figure with its meaning colour (good / warning / problem / neutral / neutral).

### The picture list

A vertical scrolling list. **Each picture is one wide row**, not a grid of tiles. Sixty of these
will be scrolled through in one sitting, so the row must be scannable and compact — target
around 120px tall.

Each row contains, left to right:

1. **Picture number**, large, monospace, e.g. `07`
2. **Thumbnail** of the chosen image, about 160×90, with a coloured left edge showing its state:
   green matched, amber weak, red gap.
3. **The timing block**, monospace, stacked:
   - `02:14 → 02:34` (when this picture is on screen)
   - `holds 20.2s` (how long it stays)
   - `script lines 31–36` (which narration it covers)
4. **The narration excerpt** it covers — two or three lines of the actual script text, dimmed
   slightly, so the operator can see what the picture is meant to illustrate.
5. **The image description** — the sentence the app or a model wrote describing what the picture
   should show. This should be editable in place by clicking it.
6. **A row of small actions** on the right: *Replace image*, *Pin*, *Regenerate description*,
   *Split this picture*, *Merge with next*.

**Split** and **Merge** are important and must be obvious: they let the operator override the
model's boundary choices by hand.

### Bottom action bar

- *Work from this folder…* with a label showing the current scope, e.g. `whole library`
- *Paste external prompts…*
- *Export prompt request* — writes a text file to hand to an outside AI
- Primary, right: **Open timeline →**

**Busy state:** when re-planning, overlay the list with a quiet progress strip reading
`Planning pictures… 34 of 60` — never a spinner with no number.

## 3. Timeline — a new screen

A multi-track timeline editor, built into this app. Think of a video editor's timeline, but
**stripped to only what a narrated documentary needs.** No transitions gallery, no effects
browser, no colour grading, no title designer.

### Layout

- **Top:** a video preview pane, roughly 16:9, centred, with transport controls beneath it —
  play/pause, step back, step forward, and a monospace current-time readout `02:14.3 / 18:22.0`.
- **Middle:** a zoom control and a ruler marked in minutes and seconds.
- **Bottom, filling the rest:** four stacked tracks, each with a fixed label column on the left
  about 140px wide:

| Track | Contents | Colour |
|---|---|---|
| **Pictures** | one block per picture, its width proportional to how long it holds, showing a small thumbnail and the picture number | brass |
| **Narration** | one waveform block per script line, laid end to end | good/green |
| **Captions** | small text blocks aligned to the spoken words | neutral grey |
| **Music & SFX** | initially empty, with a visible *+ Add audio* affordance | warning/amber |

### Behaviour to show in the design

- A **playhead** — a thin vertical brass line across all tracks with a draggable handle in the
  ruler.
- **Selecting a picture block** highlights it and shows a small inspector panel on the right
  with: the picture number, its in and out times, its duration, its image thumbnail, and a
  **Replace image** button.
- **Dragging the edge of a picture block** trims it, and the neighbouring block grows to match —
  the pictures always cover the whole narration with no gaps. Show this constraint visually.
- Each track label has a **mute** and a **lock** toggle.

### Empty state

If no timeline exists yet: a centred panel reading *"No timeline yet — plan your storyboard
first"* with a button back to Storyboard.

## 4. Render

- A prominent progress area: a wide progress bar, a percentage in large monospace, a current
  step description in words (e.g. *"Rendering picture 34 of 60"*), and an elapsed / remaining
  time pair.
- **Cancel render** button, clearly available while running.
- A collapsible **log panel** below — monospace, dark, scrolling, with each line timestamped.
  Collapsed by default.
- On completion: a success panel with the output file path in monospace, a thumbnail of the
  first frame, and buttons *Open folder*, *Play*, *Render again*.
- Render settings in a compact row above: resolution, frame rate, motion style, caption style.

## 5. Library

- Two tabs at the top: **Images** and **Sounds**.
- A dense grid of image thumbnails, roughly 180px wide, six or more per row.
- Above the grid: a search field, a **Work from this folder…** scope control showing the current
  folder or `whole library`, and a count in monospace, e.g. `2,418 images`.
- Hovering a thumbnail reveals small actions: *Use*, *Retire*, *Delete*.
- A right-hand detail panel appears when an image is selected: larger preview, file path in
  monospace, dimensions, and which pictures in the current film use it.

## 6. Voiceover

- A left column listing saved **voice profiles** as compact rows, each with a name, a small
  waveform, and a play button.
- A main area with: a text field for the line to speak, an engine dropdown, speed and pitch
  steppers, a large **Generate** button, and an audio player with a waveform.
- Below that, a **history** list of previously generated clips — each row showing the text, the
  duration in monospace, and play / save / delete actions.
- A *Record reference audio* affordance for cloning a voice profile.

## Settings

A single scrolling page of grouped sections, each a bordered panel:

- **API keys** — one row per provider (Anthropic, OpenAI, Google, DeepSeek, ElevenLabs), each
  with a masked input, a *Test* button, and a status pill reading `connected`, `no key`, or
  `failed` in the appropriate colour.
- **Niche / series style** — a list of series packs, and an editor for the visual style rules
  with a **live prompt preview** panel showing an example generated prompt.
- **Defaults** — starting image count, motion style, caption style, output folder.
- **Maintenance** — *Clear cache*, *Rebuild library index*, with sizes shown in monospace.

---

## States you must design for every screen

1. **Empty** — nothing loaded yet, with the one action that fixes it.
2. **Busy** — always with a real count or percentage, never an unlabelled spinner.
3. **Error** — a bordered panel in the problem colour, stating plainly what failed and what to
   do next. Never a modal alert box, never a toast that disappears.
4. **Success** — quiet confirmation, no celebration.

## What to avoid

- No onboarding flow, no tour, no tooltips-as-tutorial.
- No marketing language anywhere. Labels are nouns and verbs: *Re-plan pictures*, not
  *Let's make some magic!*
- No emoji, no illustrations, no stock imagery, no mascot.
- No large hero areas or wasted vertical space — this is a dense tool.
- No modal dialogs except for genuine destructive confirmations.
- No hiding numbers. If the app knows a count, a duration, or a file path, show it.

## What I want back from you

1. All six screens plus Settings, in **dark theme**, at desktop width.
2. The **Storyboard** and **Timeline** screens are the priority — spend the most care there.
3. A light-theme version of Storyboard and Timeline.
4. The empty state and the busy state for Storyboard.
5. A small component sheet: buttons (primary, secondary, ghost), the segmented toggle, numeric
   stepper, status pill, counter strip, and a picture row.
