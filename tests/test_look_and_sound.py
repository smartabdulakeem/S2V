"""
The look and the sound: treatments, motion travel, and the project style.

magick_processor has implemented vignette, vox_collage, documentary, illustration
and silhouette since the beginning. The compositor used `treatment` only to build
a cache key and rendered the raw image, so no film ever carried a look. The chosen
visual_style was stored and never read at all.
"""

import os

import pytest
from PIL import Image

from pipeline.composer import (
    _apply_treatment,
    treatment_for_style,
    SINGLE_IMAGE_TREATMENTS,
)


@pytest.fixture
def source(tmp_path):
    p = tmp_path / "src.jpg"
    img = Image.new("RGB", (400, 300))
    px = img.load()
    for x in range(400):
        for y in range(300):
            px[x, y] = ((x * 7) % 256, (y * 5) % 256, ((x + y) * 3) % 256)
    img.save(p)
    return str(p)


@pytest.mark.parametrize("name", sorted(SINGLE_IMAGE_TREATMENTS))
def test_every_treatment_produces_a_different_image(name, source, tmp_path):
    out_mp4 = str(tmp_path / f"shot_{name}.mp4")
    result = _apply_treatment({"treatment": {"filter": name}}, source, out_mp4, 400, 300)

    assert result != source, f"{name} was not applied at all"
    assert os.path.exists(result)
    assert Image.open(result).size == (400, 300)


def test_unknown_or_absent_treatment_leaves_the_image_alone(source, tmp_path):
    out_mp4 = str(tmp_path / "shot.mp4")
    assert _apply_treatment({}, source, out_mp4, 400, 300) == source
    assert _apply_treatment({"treatment": {"filter": "none"}}, source, out_mp4, 400, 300) == source
    assert _apply_treatment({"treatment": {"filter": "nonsense"}}, source, out_mp4, 400, 300) == source


def test_a_missing_source_never_breaks_the_shot(tmp_path):
    out_mp4 = str(tmp_path / "shot.mp4")
    missing = str(tmp_path / "gone.jpg")
    assert _apply_treatment({"treatment": {"filter": "vignette"}}, missing, out_mp4, 400, 300) == missing


def test_project_style_supplies_the_treatment_when_none_was_chosen(source, tmp_path):
    """Choosing 'Vox paper-collage' has to change the picture."""
    out_mp4 = str(tmp_path / "shot_style.mp4")
    treated = _apply_treatment(
        {"treatment": {"filter": "vignette"}}, source, out_mp4, 400, 300,
        default_filter=treatment_for_style("Vox paper-collage"),
    )
    assert treated != source
    assert "vox_collage" in treated


def test_a_deliberate_treatment_beats_the_project_style(source, tmp_path):
    out_mp4 = str(tmp_path / "shot_explicit.mp4")
    treated = _apply_treatment(
        {"treatment": {"filter": "silhouette"}}, source, out_mp4, 400, 300,
        default_filter="vox_collage",
    )
    assert "silhouette" in treated


@pytest.mark.parametrize("style,expected", [
    ("Vox paper-collage", "vox_collage"),
    ("vintage_documentary", "documentary"),
    ("Silhouette drama", "silhouette"),
    ("hand illustrated", "illustration"),
    ("", None),
    ("something nobody mapped", None),
])
def test_style_mapping(style, expected):
    assert treatment_for_style(style) == expected
