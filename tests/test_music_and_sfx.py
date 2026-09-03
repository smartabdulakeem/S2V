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
