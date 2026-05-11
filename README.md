# S2V — Script-to-Video Pipeline

**Turn a JSON script into a finished 1080p YouTube video — no coding required.**

---

## What this app does

S2V reads a script you write in a simple text format (JSON), and automatically:

1. Generates a professional AI voiceover (using Microsoft's free neural voices)
2. Finds matching stock photos from Pexels for each scene
3. Applies cinematic Ken Burns motion (slow zoom, pan) to each image
4. Transcribes the voiceover and burns captions into the video
5. Assembles everything into a finished 1080p MP4, ready to upload to YouTube

You write the script → click Render → get a video. That's it.

---

## First-time setup (5–15 minutes)

You only need to do this once.

**Step 1.** Make sure you have Python 3.10 or newer installed.
- Download from: https://www.python.org/downloads/
- On the installer screen, **tick "Add Python to PATH"** before clicking Install.

**Step 2.** Open the `S2V` folder. Double-click **`setup.bat`**.

A black window will open and run automatically. It will:
- Download FFmpeg (the video processing engine) — ~80 MB
- Install all required software — ~800 MB (includes AI models)
- Test that everything works correctly

When it finishes, you'll see: `✅ Setup complete! Double-click run.bat to start the app.`

---

## How to get a free Pixabay API key

Pixabay provides free stock photos. You need a free key to use them.

1. Go to: https://pixabay.com/api/docs/
2. Click **"Join"** at the top of the page and create a free account (no credit card needed)
3. Once logged in, go back to https://pixabay.com/api/docs/ — your API key will be shown near the top of the page
4. Copy it — you'll paste it into the app

---

## How to write your script (JSON format)

Your script is a `.json` file. JSON is just structured text — think of it as a very precise way of writing a list.

Here is the minimum you need for each scene (called a "segment"):

```json
{
  "segment_id": 1,
  "type": "hook",
  "narration": "The words you want spoken out loud.",
  "b_roll_keyword": "what to search on Pexels (e.g. ancient ruins)",
  "visual_type": "stock_photo",
  "ken_burns": "zoom_in",
  "text_overlay": null,
  "transition_in": "fade",
  "transition_out": "fade"
}
```

**Ken Burns options:** `zoom_in`, `zoom_out`, `pan_left`, `pan_right`, `none`

**Transition options:** `fade`, `cut`, `crossfade`

**Text overlay** (optional — leave as `null` if you don't want one):
```json
"text_overlay": {
  "text": "BAGHDAD — 762 CE",
  "position": "bottom_center",
  "duration_seconds": 4
}
```

**Position options:** `top_left`, `top_center`, `top_right`, `bottom_left`, `bottom_center`, `bottom_right`, `center`

**Voice options** (examples):
| Voice ID | Description |
|---|---|
| `en-US-GuyNeural` | American male, neutral |
| `en-US-AriaNeural` | American female, warm |
| `en-GB-RyanNeural` | British male, authoritative |
| `en-GB-SoniaNeural` | British female, clear |

See the full list at: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support

Open `samples/sample_script.json` in any text editor to see a complete working example.

---

## How to render

1. Double-click **`run.bat`** to open the app.
2. Click **"Load Script (.json)"** and choose your script file.
3. If you haven't entered your Pexels API key yet, paste it in the key field and click **Save**.
4. Click **"▶ Render Video"**.
5. Watch the progress panel. Each segment is processed one at a time.
6. When finished, click **"Open Output Folder"** to find your MP4.

Your finished video will be in the `output/` folder inside S2V.

---

## Troubleshooting

**"Python was not found" when running setup.bat**
→ Install Python from python.org. Make sure you ticked "Add Python to PATH" during installation. Then run setup.bat again.

**"FFmpeg download failed" during setup**
→ Check your internet connection. If it keeps failing, download FFmpeg manually from https://www.gyan.dev/ffmpeg/builds/ — get the "essentials" build, extract it, and place `ffmpeg.exe` inside `S2V\vendor\ffmpeg\bin\`.

**"Pixabay API key is invalid" error during render**
→ Go to pixabay.com/api/docs, log in, and copy your key again from the top of the page. Make sure there are no spaces before or after the key when you paste it.

**The app opens but the render crashes at a specific segment**
→ Check the `logs/` folder — there will be a file named `render_YYYYMMDD_HHMMSS.log` with detailed error information. The render is resume-capable: if you fix the issue and click Render again, it will skip the segments that already completed.

**The render is very slow**
→ The first render is always slower because the Whisper AI model needs to load. Subsequent renders are faster. Composition speed depends on your CPU — a 3-minute video typically takes 5–15 minutes to render.

---

## File structure explained

| File / Folder | What it is |
|---|---|
| `run.bat` | Double-click to open the app |
| `setup.bat` | Run once to install everything |
| `samples/` | Example scripts to test with |
| `output/` | Your finished MP4 files land here |
| `cache/` | Temporary files created during render (safe to delete after render) |
| `logs/` | Error logs if something goes wrong |
| `config/settings.json` | Where your Pexels key is saved |
