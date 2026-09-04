"""
tests/test_music_and_sfx.py

Verification for Slice F: Music and Sound Effects on the Timeline.
Covers:
1. build_music_filter construction (volume on [2:a], normalize=0, no volume on [aout]).
2. Narration level survival in mix (within ~1 dB of narration without music).
3. Audio fades (music_fade_in produces quieter level in first second vs second 3).
4. filmTimeToSfx maps playhead time to segment and offset_ms.
5. sfxToFilmTime maps segment + offset_ms to film time; round-trip equality.
6. moveSfxEffect moves effect across segment boundary and preserves dropped film time.
7. The Sounds tab reads a manifest, says empty when there is none, and the mockup stays gone.
8. Every music/SFX helper the Timeline calls is actually defined in app.js.
"""

import json
import os
import re
import subprocess
import pytest

from pipeline.ffmpeg_locate import find_ffmpeg
from pipeline.stitcher import build_music_filter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(REPO_ROOT, "frontend", "index.html")
APP_JS = os.path.join(REPO_ROOT, "frontend", "app.js")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_audio_tone(path: str, duration: float, freq: int = 440, volume_factor: float = 1.0) -> str:
    """Generate a test audio tone with ffmpeg."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ffmpeg = find_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency={freq}:duration={duration}",
        "-af", f"volume={volume_factor:.4f}",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        path
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return path


def _get_volume_stats(path: str, start: float = None, duration: float = None) -> dict:
    """Run volumedetect filter and return mean_volume and max_volume in dB."""
    ffmpeg = find_ffmpeg()
    cmd = [ffmpeg]
    if start is not None:
        cmd.extend(["-ss", str(start)])
    if duration is not None:
        cmd.extend(["-t", str(duration)])
    cmd.extend(["-i", path, "-af", "volumedetect", "-f", "null", "-"])
    res = subprocess.run(cmd, capture_output=True, text=True)
    mean_vol = None
    max_vol = None
    for line in res.stderr.splitlines():
        if "mean_volume:" in line:
            mean_vol = float(line.split("mean_volume:")[1].split("dB")[0].strip())
        elif "max_volume:" in line:
            max_vol = float(line.split("max_volume:")[1].split("dB")[0].strip())
    return {"mean_volume": mean_vol, "max_volume": max_vol}


def _run_node_expr(expr: str, script_context: dict = None) -> str:
    """Evaluate a JavaScript expression in Node with app.js loaded."""
    with open(APP_JS, "r", encoding="utf-8") as f:
        js_code = f.read()

    setup_before = """
let document = { querySelectorAll: () => [], getElementById: () => null, addEventListener: () => {} };
let window = { addEventListener: () => {} };
"""
    setup_after = f"""
currentScriptData = {json.dumps(script_context or {})};
currentScriptPath = 'mock/script.json';
"""
    wrapped = f"""
{setup_before}
{js_code}
{setup_after}
console.log(JSON.stringify({expr}));
"""
    res = subprocess.run(["node", "-"], input=wrapped, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(res.stdout.strip())


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_music_filter_syntax():
    """
    Test 1: Job 1 filter is built correctly:
    - volume= is on the music input [2:a]
    - normalize=0 is set on amix
    - NO volume= on the mix output [aout]
    """
    filt = build_music_filter(
        music_volume_db=-20.0,
        music_fade_in=2.0,
        music_fade_out=3.0,
        film_duration=15.0
    )

    # 1. Gain is on [2:a] input
    assert "[2:a]volume=" in filt, f"Expected [2:a]volume= in filter: {filt}"
    # 2. normalize=0 on amix
    assert "normalize=0" in filt, f"Expected normalize=0 in amix filter: {filt}"
    # 3. Fade in and fade out on music track
    assert "afade=t=in:st=0:d=2" in filt, f"Expected fade in in filter: {filt}"
    assert "afade=t=out:st=12" in filt and ":d=3" in filt, f"Expected fade out in filter: {filt}"
    # 4. No volume= on the mix output
    assert not re.search(r'amix=[^;]+,\s*volume=', filt), f"Found chained volume on amix output: {filt}"
    assert filt.endswith("[aout]"), f"Filter should output [aout]: {filt}"


def test_narration_level_survives_mix(tmp_path):
    """
    Test 2: Narration level survives the mix:
    Synthesize 5 seconds of narration audio and 10 seconds of music.
    Mix them with music at -20 dB using build_music_filter.
    Assert narration peak and mean in mixed file is within 1.5 dB of narration without music.
    (On previous code with chained volume and normalize=1, narration dropped by ~26 dB).
    """
    ffmpeg = find_ffmpeg()
    narr_path = str(tmp_path / "narration.mp3")
    music_path = str(tmp_path / "music.mp3")
    mixed_path = str(tmp_path / "mixed.mp3")

    _create_audio_tone(narr_path, duration=5.0, freq=500, volume_factor=0.9)
    _create_audio_tone(music_path, duration=10.0, freq=220, volume_factor=0.9)

    filt = build_music_filter(music_volume_db=-20.0, film_duration=5.0)
    test_filt = filt.replace("[1:a]", "[0:a]").replace("[2:a]", "[1:a]")

    cmd = [
        ffmpeg, "-y",
        "-i", narr_path,
        "-i", music_path,
        "-filter_complex", test_filt,
        "-map", "[aout]",
        mixed_path
    ]
    subprocess.run(cmd, capture_output=True, check=True)

    narr_stats = _get_volume_stats(narr_path)
    mixed_stats = _get_volume_stats(mixed_path)

    assert narr_stats["max_volume"] is not None
    assert mixed_stats["max_volume"] is not None

    diff_max = abs(mixed_stats["max_volume"] - narr_stats["max_volume"])
    diff_mean = abs(mixed_stats["mean_volume"] - narr_stats["mean_volume"])

    assert diff_max < 1.5, f"Narration max volume shifted by {diff_max:.2f} dB (narr={narr_stats['max_volume']}, mix={mixed_stats['max_volume']})"
    assert diff_mean < 1.5, f"Narration mean volume shifted by {diff_mean:.2f} dB (narr={narr_stats['mean_volume']}, mix={mixed_stats['mean_volume']})"


def test_music_fade_in(tmp_path):
    """
    Test 3: the fade works, and it is our filter doing it.

    This ran ffmpeg against a hand-written "afade=t=in:st=0:d=3.0" string, which
    proves ffmpeg has an afade filter but says nothing about build_music_filter -
    it passed whatever the stitcher emitted, including nothing. It now renders
    through the real built filter, so deleting the fade branch fails the test.
    Narration is silent here so that what volumedetect measures is the music.
    """
    ffmpeg = find_ffmpeg()
    narr_path = str(tmp_path / "narration.mp3")
    music_path = str(tmp_path / "music.mp3")
    faded_path = str(tmp_path / "faded.mp3")

    _create_audio_tone(narr_path, duration=6.0, freq=500, volume_factor=0.0)
    _create_audio_tone(music_path, duration=6.0, freq=440, volume_factor=0.8)

    filt = build_music_filter(music_volume_db=0.0, music_fade_in=3.0, film_duration=6.0)
    test_filt = filt.replace("[1:a]", "[0:a]").replace("[2:a]", "[1:a]")

    cmd = [
        ffmpeg, "-y",
        "-i", narr_path,
        "-i", music_path,
        "-filter_complex", test_filt,
        "-map", "[aout]",
        faded_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)

    stats_sec1 = _get_volume_stats(faded_path, start=0.0, duration=1.0)
    stats_sec4 = _get_volume_stats(faded_path, start=3.5, duration=1.0)

    assert stats_sec1["mean_volume"] < stats_sec4["mean_volume"] - 3.0, (
        f"Expected the fade-in to leave the first second quieter: "
        f"sec1={stats_sec1['mean_volume']}dB, sec4={stats_sec4['mean_volume']}dB"
    )


def test_film_time_to_sfx_conversion():
    """
    Test 4: filmTimeToSfx maps playhead time to segment and offset.
    Script has 3 segments: 4.0s, 6.0s, 5.0s.
    Playhead at 7.5s should land on segment 2 (starts at 4.0s) with offset 3500ms.
    """
    mock_script = {
        "segments": [
            {"segment_id": 101, "narration": "First line", "narration_seconds": 4.0},
            {"segment_id": 102, "narration": "Second line", "narration_seconds": 6.0},
            {"segment_id": 103, "narration": "Third line", "narration_seconds": 5.0},
        ]
    }
    res = _run_node_expr("filmTimeToSfx(7.5, currentScriptData)", mock_script)
    assert res["segmentIndex"] == 1
    assert res["segmentId"] == 102
    assert res["offset_ms"] == 3500


def test_sfx_to_film_time_roundtrip():
    """
    Test 5: sfxToFilmTime maps segment + offset to film time; round-trip test.
    """
    mock_script = {
        "segments": [
            {"segment_id": 1, "narration": "Line 1", "narration_seconds": 5.0},
            {"segment_id": 2, "narration": "Line 2", "narration_seconds": 7.0},
            {"segment_id": 3, "narration": "Line 3", "narration_seconds": 4.0},
        ]
    }
    for test_time in [0.5, 3.2, 5.0, 8.45, 11.9, 12.0, 14.75]:
        expr = f"""
        (() => {{
            const sfx = filmTimeToSfx({test_time}, currentScriptData);
            const backTime = sfxToFilmTime(sfx.segmentIndex, sfx.offset_ms, currentScriptData);
            return {{ original: {test_time}, sfx: sfx, back: backTime }};
        }})()
        """
        res = _run_node_expr(expr, mock_script)
        assert abs(res["original"] - res["back"]) < 0.005, f"Round-trip failed for {test_time}: got {res}"


def test_move_sfx_effect_across_boundary():
    """
    Test 6: Dragging an effect past a segment boundary moves it to the new segment
    and preserves the film time it was dropped at.
    """
    mock_script = {
        "segments": [
            {
                "segment_id": 1,
                "narration": "Line 1",
                "narration_seconds": 4.0,
                "sfx": [{"name": "clash.wav", "offset_ms": 1000}]
            },
            {
                "segment_id": 2,
                "narration": "Line 2",
                "narration_seconds": 5.0,
                "sfx": []
            }
        ]
    }
    expr = """
    (() => {
        const moveRes = moveSfxEffect(0, 0, 6.2, currentScriptData);
        const newSeg = currentScriptData.segments[1];
        const effect = newSeg.sfx[moveRes.newSfxIndex];
        const newFilmTime = sfxToFilmTime(1, effect.offset_ms, currentScriptData);
        return {
            moveRes: moveRes,
            oldSegCount: currentScriptData.segments[0].sfx.length,
            newSegCount: newSeg.sfx.length,
            newOffsetMs: effect.offset_ms,
            newFilmTime: newFilmTime
        };
    })()
    """
    res = _run_node_expr(expr, mock_script)
    assert res["oldSegCount"] == 0
    assert res["newSegCount"] == 1
    assert res["newOffsetMs"] == 2200
    assert abs(res["newFilmTime"] - 6.2) < 0.005


def test_the_sounds_tab_reads_a_manifest(tmp_path, monkeypatch):
    """
    Test 7: the Sounds tab's figures come from the manifest.

    This asserted len(load_beds()) >= 14 against the developer's own library, so
    it reported on whatever happened to sit on that machine and would fail on a
    fresh clone. It now points the loader at a two-entry manifest and goes
    through Api.get_sound_library, which is what the screen actually calls.
    """
    import app as smart_studio_app
    from pipeline import sound

    sounds_dir = tmp_path / "library" / "sounds"
    sounds_dir.mkdir(parents=True)
    for name in ("wind.mp3", "crowd.mp3"):
        (sounds_dir / name).write_bytes(b"on disk, which is all load_beds checks")

    manifest = sounds_dir / "manifest.jsonl"
    manifest.write_text(
        json.dumps({"path": "library/sounds/wind.mp3", "query": "desert wind",
                    "duration": 37.0, "category": "beds",
                    "licence_type": "CC0", "attribution": "freesound/one"}) + "\n"
        + json.dumps({"path": "library/sounds/crowd.mp3", "query": "crowd murmur",
                      "duration": 12.5, "category": "beds",
                      "licence_type": "CC0", "attribution": "freesound/two"}) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sound, "ROOT", str(tmp_path))
    monkeypatch.setattr(sound, "SOUNDS_DIR", str(sounds_dir))
    monkeypatch.setattr(sound, "MANIFEST_PATH", str(manifest))

    res = smart_studio_app.Api().get_sound_library()

    assert res["total_sounds"] == 2, f"expected the manifest's two entries, got {res['total_sounds']}"
    assert sorted(s["name"] for s in res["sounds"]) == ["crowd.mp3", "wind.mp3"]

    wind = next(s for s in res["sounds"] if s["name"] == "wind.mp3")
    assert wind["query"] == "desert wind"
    assert wind["duration"] == 37.0
    assert wind["licence_type"] == "CC0"
    assert wind["attribution"] == "freesound/one", "attribution must reach the screen"


def test_the_sounds_tab_says_empty_rather_than_guessing(tmp_path, monkeypatch):
    """A missing manifest means an empty library, never a fallback number."""
    import app as smart_studio_app
    from pipeline import sound

    monkeypatch.setattr(sound, "ROOT", str(tmp_path))
    monkeypatch.setattr(sound, "MANIFEST_PATH", str(tmp_path / "nothing-here.jsonl"))

    res = smart_studio_app.Api().get_sound_library()
    assert res["total_sounds"] == 0
    assert res["sounds"] == []


def test_the_sounds_mockup_is_gone():
    """
    The invented rows and counts must not come back. The bare "87" this asserted
    on matches any colour, width or id containing 87, so it was a trap for the
    next person to touch the file; these are the strings that were actually fake.
    """
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    for phrase in ("87 sounds", "12 music beds", "Desert Wind Ambience",
                   "Horses Galloping", "Sword Clash Heavy"):
        assert phrase not in html, f"the Sounds mockup is back in index.html: {phrase!r}"


def test_timeline_tracks_and_lanes_in_index():
    """
    Assert that Music and Sound effects tracks, lanes, and audio element exist in index.html.
    """
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    assert 'id="tl-music-audio"' in html
    assert '<span class="tl-track-name">Music</span>' in html
    assert '<span class="tl-track-name">Sound effects</span>' in html
    assert 'id="tl-lane-music"' in html
    assert 'id="tl-lane-sfx"' in html
    assert 'id="sfx-picker-modal"' in html


def test_the_timeline_music_and_sfx_helpers_are_all_defined():
    """
    Adding a sound effect died on "ReferenceError: persistCurrentScript is not
    defined". Slice F called that helper from seven places and never wrote it,
    so every music and SFX edit - volume, fades, add, remove, delete, drag -
    threw before anything reached disk, and adding music threw before it could
    prepare the preview, which is why it never played either.

    test_frontend_controls only checks that onclick targets exist, so a helper
    called from inside another function slips straight past it. This walks the
    whole Slice F surface in a real JS runtime instead.
    """
    names = [
        "persistCurrentScript",
        "timelineMusicAudioEl", "prepareTimelineMusic", "timelineAddMusic",
        "removeTimelineMusic", "selectTimelineMusic", "drawTimelineMusicInspector",
        "onTimelineMusicVolumeChange", "onTimelineMusicFadeChange",
        "filmTimeToSfx", "sfxToFilmTime", "moveSfxEffect",
        "selectTimelineSfx", "drawTimelineSfxInspector", "deleteSelectedSfx",
        "openAddSfxMenu", "closeSfxPickerModal", "renderSfxPickerList",
        "filterSfxPicker", "addSfxFromComputer", "addSfxFromLibraryItem",
        "_insertSfxAtPlayhead", "timelineSfxPointerDown",
        # Slice B additions
        "onMotionAmountInput", "resetWindowSize",
        "playSfxPath", "previewSfxItemAudio", "previewCurrentSelectedSfx",
    ]
    expr = "[" + ", ".join(f'typeof {n}' for n in names) + "]"
    kinds = _run_node_expr(expr)

    undefined = [n for n, k in zip(names, kinds) if k != "function"]
    assert not undefined, (
        "Slice F helpers referenced but not defined in app.js: " + ", ".join(undefined)
    )


def test_persist_current_script_writes_through_the_normal_save_path():
    """
    It must save the way every other timeline edit does - save_edited_script with
    the current path and data - and must not throw when there is no path or when
    the page is running outside the desktop shell.
    """
    with open(APP_JS, "r", encoding="utf-8") as f:
        js = f.read()

    assert "async function persistCurrentScript()" in js,         "persistCurrentScript is not defined in app.js"

    body_start = js.index("async function persistCurrentScript()")
    body = js[body_start:body_start + 400]

    assert "save_edited_script(currentScriptPath, currentScriptData)" in body, (
        "persistCurrentScript does not go through save_edited_script"
    )
    assert "isWebMode" in body, "persistCurrentScript must be a no-op in web mode"
    assert "currentScriptPath" in body, "persistCurrentScript must guard on a missing path"


def test_auditioning_a_placed_effect_finds_the_file_the_render_will_use(tmp_path, monkeypatch):
    """
    A placed effect is {name, offset_ms} — the shape _overlay_sound_effects reads.
    It has never carried a `path`. The audition button read sfx.path, got
    undefined, and did nothing at all: no sound, no error, nothing in the console.

    The preview must resolve a bare name exactly where the compositor resolves
    it, under <project>/assets/sfx/, so what you audition is what renders.
    """
    import app as smart_studio_app

    monkeypatch.setenv("SMART_STUDIO_DEVSERVER", "1")

    project_dir = tmp_path / "projects" / "A Film"
    sfx_dir = project_dir / "assets" / "sfx"
    sfx_dir.mkdir(parents=True)
    (sfx_dir / "clash.wav").write_bytes(b"RIFF0000WAVE")

    monkeypatch.setattr(smart_studio_app, "BASE_DIR", str(tmp_path))

    res = smart_studio_app.Api().prepare_sfx_preview("clash.wav", str(project_dir))

    assert res["ok"] is True, f"a placed effect could not be auditioned: {res.get('error')}"
    assert res.get("src"), "no playable source came back for a placed effect"


def test_a_missing_effect_says_so_rather_than_failing_silently():
    """Silence was the original bug. An unresolvable effect must report why."""
    import app as smart_studio_app

    res = smart_studio_app.Api().prepare_sfx_preview("no-such-sound.wav", "")
    assert res["ok"] is False
    assert "not found" in res["error"].lower()


def test_the_audition_reads_the_field_the_insert_writes():
    """
    _insertSfxAtPlayhead pushes {name, offset_ms}. Whatever the audition reads
    has to be a key that object actually has, or the button goes quiet again.
    """
    with open(APP_JS, "r", encoding="utf-8") as f:
        js = f.read()

    insert = js[js.index("async function _insertSfxAtPlayhead"):]
    insert = insert[:insert.index("\n}")]
    assert "name:" in insert, "_insertSfxAtPlayhead no longer writes a name"

    audition = js[js.index("function previewCurrentSelectedSfx"):]
    audition = audition[:audition.index("\n}")]
    assert "sfx.name" in audition, (
        "previewCurrentSelectedSfx does not read sfx.name — the key a placed "
        "effect actually carries. Reading only sfx.path audits nothing, silently."
    )


# ── Slice G Tests: Timeline Live Playback & Audio Sync ────────────────────────

def test_sfx_schedule_construction_roundtrips():
    """
    Test 1: Schedule construction. A script with effects in three different
    segments produces a sorted film-time list whose values round-trip through
    filmTimeToSfx unchanged.
    """
    script = {
        "segments": [
            {"narration_seconds": 4.0, "sfx": [{"name": "whoosh.wav", "offset_ms": 1500}]},
            {"narration_seconds": 6.0, "sfx": [{"name": "bell.wav", "offset_ms": 2000}]},
            {"narration_seconds": 5.0, "sfx": [{"name": "hit.wav", "offset_ms": 500}]}
        ]
    }
    res = _run_node_expr("""
    (() => {
        buildTimelineSfxSchedule();
        return tlSfxSchedule.map(item => {
            const mapBack = filmTimeToSfx(item.filmTime);
            return {
                name: item.name,
                filmTime: item.filmTime,
                origSeg: item.segIndex,
                origOffset: item.sfxIndex,
                mappedSeg: mapBack.segmentIndex,
                mappedOffset: mapBack.offset_ms
            };
        });
    })()
    """, script)

    assert len(res) == 3
    # Sorted order by filmTime: 1.5s, 6.0s (4.0 + 2.0), 10.5s (4.0 + 6.0 + 0.5)
    assert res[0]["filmTime"] == 1.5
    assert res[1]["filmTime"] == 6.0
    assert res[2]["filmTime"] == 10.5
    assert res[0]["mappedSeg"] == 0 and res[0]["mappedOffset"] == 1500
    assert res[1]["mappedSeg"] == 1 and res[1]["mappedOffset"] == 2000
    assert res[2]["mappedSeg"] == 2 and res[2]["mappedOffset"] == 500


def test_sfx_crossing_fires_once():
    """
    Test 2: Crossing fires once. Advancing the playhead across an effect fires it
    exactly once, not on every subsequent frame.
    """
    script = {
        "segments": [
            {"narration_seconds": 10.0, "sfx": [{"name": "impact.wav", "offset_ms": 3000}]}
        ]
    }
    res = _run_node_expr("""
    (() => {
        buildTimelineSfxSchedule();
        resetTimelineSfxCursor(0);
        let fired = [];
        playTimelineSfx = (name) => { fired.push(name); };

        // Frame 1: t=1.0s (before effect)
        processTimelineSfxCrossing(1.0);
        const count1 = fired.length;

        // Frame 2: t=3.05s (crosses effect at 3.0s)
        processTimelineSfxCrossing(3.05);
        const count2 = fired.length;

        // Frame 3: t=3.10s (subsequent frame past effect)
        processTimelineSfxCrossing(3.10);
        const count3 = fired.length;

        // Frame 4: t=5.0s (farther along)
        processTimelineSfxCrossing(5.0);
        const count4 = fired.length;

        return { count1, count2, count3, count4, fired };
    })()
    """, script)

    assert res["count1"] == 0
    assert res["count2"] == 1
    assert res["count3"] == 1, "Effect fired again on subsequent frame"
    assert res["count4"] == 1, "Effect fired again long after crossing"
    assert res["fired"] == ["impact.wav"]


def test_seeking_across_two_hundred_effects_fires_none():
    """
    Test 3: Seeking fires nothing. Jumping the playhead from before two hundred
    effects to after them fires zero. This is the machine-gun guard.
    """
    segments = []
    for s in range(10):
        sfx_list = [{"name": f"sfx_{s}_{i}.wav", "offset_ms": i * 50} for i in range(20)]
        segments.append({"narration_seconds": 10.0, "sfx": sfx_list})
    script = {"segments": segments}

    res = _run_node_expr("""
    (() => {
        buildTimelineSfxSchedule();
        resetTimelineSfxCursor(0);
        let fired = [];
        playTimelineSfx = (name) => { fired.push(name); };

        // Scrub/seek from 0 to 95.0s across all 200 effects
        resetTimelineSfxCursor(95.0);

        // Next frame at 95.016s
        processTimelineSfxCrossing(95.016);

        return {
            totalScheduled: tlSfxSchedule.length,
            firedCount: fired.length,
            cursor: tlSfxCursor
        };
    })()
    """, script)

    assert res["totalScheduled"] == 200
    assert res["firedCount"] == 0, f"Seeking fired {res['firedCount']} effects instead of 0"


def test_seek_then_play_forward_still_fires_later_effects():
    """
    The companion to test_seeking_across_two_hundred_effects_fires_none, and the
    reason that test is not sufficient on its own.

    That test seeks to 95.0s in a 100s fixture where every effect sits before the
    seek point, so it cannot tell a correctly positioned cursor apart from a
    cursor parked at the end of the schedule. Both produce zero fires. An
    implementation that killed every effect after any seek passed all 23 tests in
    this file, which is the "test that cannot fail" shape ANTIGRAVITY-RULES.md
    warns about.

    So this seeks into the MIDDLE, where effects exist on both sides, and asserts
    both halves: nothing fires from the seek itself, and the effects after the
    seek point still fire when the playhead reaches them.
    """
    segments = []
    for s in range(10):
        sfx_list = [{"name": f"sfx_{s}_{i}.wav", "offset_ms": i * 500} for i in range(2)]
        segments.append({"narration_seconds": 10.0, "sfx": sfx_list})
    script = {"segments": segments}

    res = _run_node_expr("""
    (() => {
        buildTimelineSfxSchedule();
        let fired = [];
        playTimelineSfx = (name) => { fired.push(name); };

        // Seek into the middle: effects exist before AND after 45.0s.
        resetTimelineSfxCursor(45.0);
        const firedBySeek = fired.length;
        const cursorAfterSeek = tlSfxCursor;

        // Now play forward across the effects at 50.0s and 50.5s.
        processTimelineSfxCrossing(50.016);
        processTimelineSfxCrossing(50.6);

        return {
            totalScheduled: tlSfxSchedule.length,
            firedBySeek: firedBySeek,
            cursorAfterSeek: cursorAfterSeek,
            firedAfterSeek: fired.length,
            names: fired
        };
    })()
    """, script)

    assert res["totalScheduled"] == 20

    # The seek itself is silent.
    assert res["firedBySeek"] == 0, f"The seek fired {res['firedBySeek']} effects"

    # The cursor lands on the first effect at or after 45.0s, which is index 10
    # (segment 5, offset 0). Parking it at 20 is the bug this test exists to catch.
    assert res["cursorAfterSeek"] == 10, (
        f"Cursor landed at {res['cursorAfterSeek']}, expected 10. "
        "A cursor at 20 means seeking silently disabled every later effect."
    )

    # Playing forward past the seek still fires.
    assert res["firedAfterSeek"] == 2, (
        f"Expected the two effects at 50.0s and 50.5s to fire after seeking, "
        f"got {res['firedAfterSeek']}. Seeking has disabled later playback."
    )
    assert res["names"] == ["sfx_5_0.wav", "sfx_5_1.wav"]


def test_pause_stops_sfx_in_flight():
    """
    Test 4: Pause stops effects in flight. A sound effect still playing when
    pause is hit is immediately stopped and reset.
    """
    res = _run_node_expr("""
    (() => {
        let pausedCount = 0;
        class MockAudio {
            constructor() {
                this.paused = false;
                this.currentTime = 1.2;
                this.src = "mock.wav";
            }
            pause() { this.paused = true; pausedCount++; }
        }
        tlActiveSfxElements = [new MockAudio(), new MockAudio()];
        tlSfxAudioPool = { "bg": new MockAudio() };

        stopAllTimelineSfx();
        return {
            activeRemaining: tlActiveSfxElements.length,
            pausedCount: pausedCount,
            poolPaused: tlSfxAudioPool["bg"].paused,
            poolTime: tlSfxAudioPool["bg"].currentTime
        };
    })()
    """)

    assert res["activeRemaining"] == 0
    assert res["pausedCount"] == 3
    assert res["poolPaused"] is True
    assert res["poolTime"] == 0


def test_music_gain_fade_in():
    """
    Test 5: musicGainAt at t=0 with 2s fade-in returns 0; at t=1 returns about
    half the base gain; past the fade returns base gain exactly.
    """
    res = _run_node_expr("""
    (() => {
        const proj = { music_volume_db: -20, music_fade_in: 2, music_fade_out: 0 };
        const g0 = musicGainAt(0, 100, proj);
        const g1 = musicGainAt(1, 100, proj);
        const g3 = musicGainAt(3, 100, proj);
        const base = Math.pow(10, -20 / 20); // 0.1
        return { g0, g1, g3, base };
    })()
    """)

    base = res["base"]
    assert res["g0"] == pytest.approx(0.0, abs=1e-4)
    assert res["g1"] == pytest.approx(base * 0.5, rel=1e-3)
    assert res["g3"] == pytest.approx(base, rel=1e-3)


def test_music_gain_fade_out():
    """
    Test 6: With music_fade_out=4 on a 100s film, t=98 is about half base and
    t=100 is 0.
    """
    res = _run_node_expr("""
    (() => {
        const proj = { music_volume_db: -20, music_fade_in: 0, music_fade_out: 4 };
        const g98 = musicGainAt(98, 100, proj);
        const g100 = musicGainAt(100, 100, proj);
        const base = Math.pow(10, -20 / 20); // 0.1
        return { g98, g100, base };
    })()
    """)

    base = res["base"]
    assert res["g98"] == pytest.approx(base * 0.5, rel=1e-3)
    assert res["g100"] == pytest.approx(0.0, abs=1e-4)


def test_music_gain_flat_when_fades_zero():
    """
    Test 7: With both fades 0, the function returns the flat dB conversion
    at every time — current behaviour unchanged.
    """
    res = _run_node_expr("""
    (() => {
        const proj = { music_volume_db: -12, music_fade_in: 0, music_fade_out: 0 };
        const base = Math.pow(10, -12 / 20);
        const times = [0, 10, 50, 99, 100];
        const gains = times.map(t => musicGainAt(t, 100, proj));
        return { base, gains };
    })()
    """)

    base = res["base"]
    for g in res["gains"]:
        assert g == pytest.approx(base, rel=1e-4)


def test_music_drift_modulo_and_deadband():
    """
    Test 8: Given narration time and shorter looped music duration, the target
    music position is the modulo, and a delta under the deadband produces no
    correction.
    """
    res = _run_node_expr("""
    (() => {
        const musicDur = 30.0;
        const narrTime = 75.0; // 75 % 30 = 15.0s

        // Within 0.25s deadband (delta = 0.15s)
        const check1 = checkMusicDrift(narrTime, musicDur, 15.15, 0.25);

        // Outside 0.25s deadband (delta = 0.40s)
        const check2 = checkMusicDrift(narrTime, musicDur, 15.40, 0.25);

        return { check1, check2 };
    })()
    """)

    assert res["check1"]["targetTime"] == pytest.approx(15.0)
    assert res["check1"]["needsCorrection"] is False

    assert res["check2"]["targetTime"] == pytest.approx(15.0)
    assert res["check2"]["needsCorrection"] is True
    assert res["check2"]["drift"] == pytest.approx(0.40)

