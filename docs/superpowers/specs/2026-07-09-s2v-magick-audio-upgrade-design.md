# S2V ImageMagick & Audio Glitch-Fix Upgrade Spec

## Overview
This specification details the enhancements to the S2V (Script-to-Video) rendering pipeline to achieve:
1. **Rendering Speedup:** Grouping script narration into fewer, longer segments (Option A) to reduce video composition overhead.
2. **Documentary Visual Aesthetics:** Using the local ImageMagick tool to automate radial vignettes, film grain textures, split-screen collages, and panoramic diptych stitching.
3. **Glitch-Free Voiceover:** Stitching individual segment narration audios into a single master audio track before final video assembly, preventing clicks, pops, and silent gaps at segment boundaries.

---

## Technical Design & Architecture

### 1. Storyboard Segment Grouping (Option A)
The script is grouped into 9 segments (reduced from 18). Each segment has a target duration of 20–30 seconds.
- **Diptych Segments:** Segments 2, 6, and 9 use horizontal stitching (`+append`) of two source images.
- **Collage Segments:** Segment 5 combines a map and a character image side-by-side with a central separator border.
- **Single Image Segments:** Segments 1, 3, 4, 7, and 8 use a single source image with a centered vignette filter.

### 2. ImageMagick Processing Pipeline
A new module `pipeline/magick_processor.py` will be created. It executes shell commands targeting the local `magick` executable:
- **Panoramic Diptych Command:**
  ```cmd
  magick convert <img1> <img2> -resize 1280x720^ -gravity center -crop 1280x720+0+0 +append -background black -vignette 0x20 -attenuate 0.5 +noise Gaussian <output>
  ```
- **Collage Command:**
  ```cmd
  magick convert ( <img1> -resize 640x720^ -gravity center -crop 640x720+0+0 ) ( <img2> -resize 640x720^ -gravity center -crop 640x720+0+0 ) +append -background black -vignette 0x20 <output>
  ```
- **Vignette Command:**
  ```cmd
  magick convert <img1> -resize 1280x720^ -gravity center -crop 1280x720+0+0 -background black -vignette 0x20 -attenuate 0.5 +noise Gaussian <output>
  ```

### 3. Continuous Audio Generation & Stitching
- **Audio Stitching:** In `pipeline/voiceover.py`, a new function `stitch_master_audio(segment_audio_paths, output_path)` will combine all segment audio clips seamlessly using FFmpeg's concat filter.
- **Stitcher Modification:** `pipeline/stitcher.py` will be updated to:
  1. Concatenate all segment video clips, stripping their individual audio tracks (`-an`).
  2. Overlay the pre-stitched `master_narration.mp3` file across the complete video timeline.

---

## File Modifications

### `[NEW]` [magick_processor.py](file:///C:/Users/HomePC/Documents/GitHub/S2V/pipeline/magick_processor.py)
Implements diptych stitching, collaging, and vignette/grain filters.

### `[MODIFY]` [visuals.py](file:///C:/Users/HomePC/Documents/GitHub/S2V/pipeline/visuals.py)
Hooks into `magick_processor.py` before copying visuals to cache, preparing stitched panoramic canvases and single vignetted frames.

### `[MODIFY]` [stitcher.py](file:///C:/Users/HomePC/Documents/GitHub/S2V/pipeline/stitcher.py)
Replaces segment-level audio tracks with the seamless master audio track.

---

## Verification Plan

### Automated Verification
1. Run S2V CLI to compile `planned_script.json`.
2. Inspect the output logs to confirm ImageMagick and FFmpeg concat commands succeed.

### Manual Verification
1. Play the rendered video `S2E5_Caliph_Goes_To_War.mp4` to check:
   - Voiceover is seamless and free of pop glitches between scenes.
   - Panoramic scenes (e.g. Segments 2, 6, 9) show smooth camera movement traveling across two stitched images.
