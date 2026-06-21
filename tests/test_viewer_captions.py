"""Library hero-thumbnail captions: one structured, 3-line block per clip (#1).

Every shelf thumbnail must show the same three pieces of information at the same
level — title, language, narrator style — each on its own line. This replaces the
old conditional ``"title · LANG · Style"`` join that only rendered the meta block
when *both* language and persona were present, leaving seed scenes (which carry a
``style_key`` but no persona/language) showing just a bare title.
"""

from __future__ import annotations

from small_cuts.viewer import _shelf_caption, format_stage


def _seed_like_scene(scene_id: str = "seed-0", title: str = "Debugging His Ambition") -> dict:
    """A scene shaped like the curated seed library: a style_key, no persona."""
    return {
        "scene_id": scene_id,
        "title": title,
        "style_key": "deadpan",
        "language": "English",
    }


def _v2_like_scene() -> dict:
    """A scene shaped like a v2 Modal upload: a persona + language."""
    return {
        "scene_id": "upload-1",
        "title": "Just Five Minutes",
        "style_key": "deadpan",
        "persona": "deadpan",
        "language": "Spanish",
        "source_icon": "upload",
    }


def test_caption_has_exactly_three_lines_for_seed_scene():
    caption = _shelf_caption(_seed_like_scene())
    assert caption.count("\n") == 2
    lines = caption.splitlines()
    assert lines[0] == "Debugging His Ambition"
    assert lines[1] == "EN"  # English -> EN
    assert lines[2] == "Deadpan Omniscient (the classic)"  # style_key deadpan label


def test_caption_has_exactly_three_lines_for_v2_scene():
    caption = _shelf_caption(_v2_like_scene())
    lines = caption.splitlines()
    assert len(lines) == 3
    # the invisible source prefix must stay glued to the title line (#2-style badge)
    assert lines[0].endswith("Just Five Minutes")
    assert lines[1] == "ES"  # Spanish -> ES
    assert lines[2] == "Deadpan Omniscient · The Invention of Lying"  # persona label


def test_caption_language_line_is_placeholder_when_unknown():
    scene = _seed_like_scene()
    scene["language"] = None
    caption = _shelf_caption(scene)
    lines = caption.splitlines()
    assert len(lines) == 3
    assert lines[1] == "\u2014"  # em dash placeholder for a genuinely missing language


def test_caption_style_matches_the_stage_header_resolution():
    """The shelf and the stage header must agree on the narrator-style label."""
    for scene in (_seed_like_scene(), _v2_like_scene()):
        caption_lines = _shelf_caption(scene).splitlines()
        stage = format_stage(scene)
        # format_stage's style_label is the single source of truth; the shelf's
        # third line must be identical so the two surfaces never disagree.
        expected = stage["style_label"]
        assert caption_lines[2] == expected, (
            f"shelf style '{caption_lines[2]}' != header style '{expected}'"
        )


def test_caption_preserves_source_icon_prefix_on_title_line():
    scene = _v2_like_scene()
    prefix = "\u2063"  # UPLOAD_SHELF_PREFIX (invisible; drives the CSS source badge)
    assert _shelf_caption(scene).startswith(prefix + "Just Five Minutes")
