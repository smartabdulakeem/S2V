"""
Delivery profiles: the tone has to change how the words are read.

Before this existed the Tone dropdown reached only the LLM planner, so a
motivational speech and a war documentary came out of the offline engines
sounding identical.
"""

import numpy as np
import pytest

from pipeline.delivery import (
    DELIVERY_PROFILES, NICHE_TONES, DEFAULT_TONE,
    resolve_tone, delivery_for, tones_for_niche, steering_for,
    apply_rate, split_blocks, join_with_silence,
)


# ── the profile table itself ────────────────────────────────────────────────

def test_every_profile_is_complete():
    for key, prof in DELIVERY_PROFILES.items():
        assert prof["label"].strip(), key
        assert prof["steering"].strip(), key
        assert 0.7 <= prof["speed"] <= 2.0, key
        assert 0.0 <= prof["silence"] <= 3.0, key
        assert prof["silence"] <= prof["block_silence"], \
            f"{key}: a paragraph gap must not be shorter than a sentence gap"


def test_every_niche_recommends_real_tones():
    for slug, keys in NICHE_TONES.items():
        assert keys, slug
        for key in keys:
            assert key in DELIVERY_PROFILES, f"{slug} recommends unknown tone {key}"


def test_the_tones_are_actually_different():
    # If two profiles were identical the dropdown would be lying to the user.
    shapes = {(p["speed"], p["silence"], p["block_silence"])
              for p in DELIVERY_PROFILES.values()}
    assert len(shapes) == len(DELIVERY_PROFILES)


def test_motivational_holds_longer_than_news():
    mot = delivery_for("motivational_punch")
    news = delivery_for("urgent_news")
    assert mot["block_silence"] > news["block_silence"] * 3
    assert mot["speed"] < news["speed"]


# ── resolving what the project stored ───────────────────────────────────────

def test_a_key_resolves_to_itself():
    assert resolve_tone("urgent_news") == "urgent_news"


def test_a_label_resolves():
    assert resolve_tone("Urgent news") == "urgent_news"


@pytest.mark.parametrize("legacy,expected", [
    ("Grave documentary", "grave_documentary"),
    ("Warm storytelling", "warm_storytelling"),
    ("Urgent", "urgent_news"),
])
def test_the_three_old_dropdown_strings_still_resolve(legacy, expected):
    # Projects saved before this existed hold these exact strings.
    assert resolve_tone(legacy) == expected


def test_nothing_resolves_to_the_default():
    assert resolve_tone("") == DEFAULT_TONE
    assert resolve_tone(None) == DEFAULT_TONE
    assert resolve_tone("something nobody ever wrote") == DEFAULT_TONE


def test_steering_is_prose_for_the_planner():
    assert "motivational" in steering_for("motivational_punch").lower()


# ── the dropdown ordering ───────────────────────────────────────────────────

def test_recommended_tones_come_first():
    tones = tones_for_niche("motivational")
    assert tones[0]["key"] == "motivational_punch"
    assert tones[0]["recommended"] is True


def test_no_tone_is_hidden():
    # A motivational read on a wildlife film is allowed, just not offered first.
    assert len(tones_for_niche("nature_wildlife")) == len(DELIVERY_PROFILES)


def test_an_unknown_niche_still_gets_a_full_list():
    tones = tones_for_niche("no_such_niche")
    assert len(tones) == len(DELIVERY_PROFILES)
    assert any(t["recommended"] for t in tones)


# ── the user's own rate still applies on top ────────────────────────────────

def test_rate_nudges_the_tone_speed():
    assert apply_rate(1.0, "+10%") == 1.1
    assert apply_rate(1.0, "-10%") == 0.9


def test_rate_is_optional_and_junk_is_ignored():
    assert apply_rate(0.94, "") == 0.94
    assert apply_rate(0.94, "fast") == 0.94


def test_speed_stays_inside_what_the_engines_accept():
    assert apply_rate(1.12, "+500%") <= 2.0
    assert apply_rate(0.9, "-500%") >= 0.7


# ── splitting narration into pausable units ────────────────────────────────

def test_sentences_within_a_paragraph_get_sentence_gaps():
    blocks = split_blocks("One thing. Another thing.")
    assert [g for _, g in blocks] == ["sentence", None]


def test_a_blank_line_is_a_block_gap():
    blocks = split_blocks("One thing.\n\nAnother thing.")
    assert [g for _, g in blocks] == ["block", None]


def test_the_last_chunk_never_trails_silence():
    blocks = split_blocks("A. B.\n\nC. D.")
    assert blocks[-1][1] is None


def test_empty_narration_splits_to_nothing():
    assert split_blocks("") == []
    assert split_blocks("   ") == []


def test_punctuation_stays_with_its_sentence():
    blocks = split_blocks("Who goes there? Nobody answered.")
    assert blocks[0][0].endswith("?")


# ── the silence is real samples, of the right length ───────────────────────

def test_silence_is_inserted_at_the_profile_length():
    sr = 24000
    profile = {"silence": 0.5, "block_silence": 1.5}
    a = np.ones(sr, dtype=np.float32)   # 1 second
    b = np.ones(sr, dtype=np.float32)   # 1 second
    joined = join_with_silence([(a, "sentence"), (b, None)], sr, profile)
    assert len(joined) == sr + int(0.5 * sr) + sr


def test_a_block_gap_is_longer_than_a_sentence_gap():
    sr = 24000
    profile = {"silence": 0.5, "block_silence": 1.5}
    one = np.ones(sr, dtype=np.float32)
    sentence = join_with_silence([(one, "sentence"), (one, None)], sr, profile)
    block = join_with_silence([(one, "block"), (one, None)], sr, profile)
    assert len(block) - len(sentence) == int(1.0 * sr)


def test_the_inserted_samples_are_actually_silent():
    sr = 100
    profile = {"silence": 1.0, "block_silence": 2.0}
    one = np.ones(10, dtype=np.float32)
    joined = join_with_silence([(one, "sentence"), (one, None)], sr, profile)
    assert np.count_nonzero(joined[10:110]) == 0


def test_empty_pieces_are_skipped_not_padded():
    sr = 100
    profile = {"silence": 1.0, "block_silence": 2.0}
    one = np.ones(10, dtype=np.float32)
    joined = join_with_silence(
        [(np.array([], dtype=np.float32), "sentence"), (one, None)], sr, profile)
    assert len(joined) == 10


def test_nothing_at_all_joins_to_nothing():
    assert join_with_silence([], 24000, {"silence": 1.0, "block_silence": 2.0}) is None


def test_a_real_profile_produces_the_arithmetic_it_promises():
    # Two paragraphs of two sentences: 2 sentence gaps + 1 block gap.
    sr = 24000
    profile = delivery_for("motivational_punch")
    blocks = split_blocks("A one. A two.\n\nB one. B two.")
    gaps = [g for _, g in blocks]
    assert gaps == ["sentence", "block", "sentence", None]

    one = np.ones(sr, dtype=np.float32)
    joined = join_with_silence([(one, g) for _, g in blocks], sr, profile)

    expected_silence = 2 * profile["silence"] + profile["block_silence"]
    expected_len = 4 * sr + int(expected_silence * sr)
    # Integer sample counts, so allow a sample or two of rounding either way.
    assert abs(len(joined) - expected_len) <= 4, (len(joined), expected_len)
