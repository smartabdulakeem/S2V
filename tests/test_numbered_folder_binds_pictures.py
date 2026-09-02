"""
A numbered image belongs to a picture, not to a script line.

The owner planned a 347-line film down to 15 pictures, copied the 15 prompts,
generated 15 images, numbered them 1..15 and pointed the app at the folder. Two
came back. The numbers were being counted against every shot in the film — one
per script line — so 1.jpg..15.jpg were paired with lines 1..15, and only line 1
happened to own a picture. The other fourteen landed on shots carrying
`share_with`, which are drawn from another shot's image and can never hold one
of their own, so the pictures they were made for stayed empty.

`picture_owning_shots` already stated the rule: slot n is the nth picture the
film actually makes, and every caller has to agree or the mismatch simply moves.
These tests hold `plan_shots`'s caller to it.
"""

import pytest

from pipeline import library


def film(owner_lines, total):
    """
    A film of `total` script lines whose pictures begin at `owner_lines`.

    Shaped like `plan_shots`'s `all_shots`: one entry per script line, each
    either owning a picture or sharing the one before it.
    """
    shots = []
    for line in range(1, total + 1):
        owner = max(o for o in owner_lines if o <= line)
        shots.append({
            "shot_id": f"{line}a",
            "share_with": None if line == owner else f"{owner}a",
        })
    return shots


def numbered(count):
    return [f"C:/pics/{n}_pic.jpg" for n in range(1, count + 1)]


def test_the_owners_real_film_binds_every_picture():
    """15 numbered images, 15 pictures, 347 lines: all fifteen land."""
    owners = [1, 20, 38, 57, 78, 100, 124, 146, 171, 196, 219, 251, 277, 304, 329]
    shots = film(owners, 347)

    out = library.number_pictures_from_folder(shots, numbered(15))

    assert len(out) == 15, "every generated image should reach the picture it was made for"
    # Slot n -> the nth picture, which sits on the nth owner line (1-based).
    for slot, line in enumerate(owners, start=1):
        assert out[line - 1] == f"C:/pics/{slot}_pic.jpg"


def test_no_image_lands_on_a_sharing_shot():
    """The defect itself: a shot that shares can never hold an image."""
    shots = film([1, 20, 38, 57, 78, 100, 124, 146, 171, 196, 219, 251, 277, 304, 329], 347)

    out = library.number_pictures_from_folder(shots, numbered(15))

    stranded = [i for i in out if shots[i].get("share_with")]
    assert stranded == [], f"images bound to shots that never own a picture: {stranded}"


def test_counting_script_lines_is_what_lost_fourteen_of_them():
    """
    The old behaviour, kept as the thing this must never do again.

    Counting `all_shots` pairs image n with script line n. On this film exactly
    one of those lines owns a picture, which is what the owner saw.
    """
    owners = [1, 20, 38, 57, 78, 100, 124, 146, 171, 196, 219, 251, 277, 304, 329]
    shots = film(owners, 347)

    by_line = library.match_shots_by_number(numbered(15), len(shots))
    usable = [i for i in by_line if not shots[i].get("share_with")]

    assert len(usable) == 1, "the old pairing is expected to strand fourteen images"
    assert len(library.number_pictures_from_folder(shots, numbered(15))) == 15


def test_the_slot_ceiling_is_the_picture_count():
    """An image numbered past the last picture is not a picture of this film."""
    shots = film([1, 10, 20], 30)

    out = library.number_pictures_from_folder(shots, numbered(6))

    assert sorted(out) == [0, 9, 19]
    assert len(out) == 3, "images 4, 5 and 6 name pictures this film does not make"


def test_a_film_where_every_line_owns_a_picture_is_unchanged():
    """With no sharing, picture order and line order are the same list."""
    shots = film(list(range(1, 13)), 12)

    out = library.number_pictures_from_folder(shots, numbered(12))

    assert out == {n - 1: f"C:/pics/{n}_pic.jpg" for n in range(1, 13)}


def test_a_film_with_no_pictures_binds_nothing():
    assert library.number_pictures_from_folder([], numbered(5)) == {}
