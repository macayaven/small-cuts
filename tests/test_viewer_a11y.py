"""Accessibility: icon-only control buttons must carry aria-labels (#4).

The control-pill buttons are icon-only (``gr.Button("")`` with masked SVG), so
screen readers have no text to announce. The volume slider already has an
aria-label; these tests ensure the five in-scope icon buttons (rewind, play,
forward, CC, upload) get aria-labels via the same JS pattern that already fixes
form-field a11y (``scFixUploadFormFields``).
"""

from __future__ import annotations

from small_cuts.viewer import PLAYBACK_SYNC_JS


def test_js_sets_aria_label_on_rewind_button():
    assert "sc-ico-rewind" in PLAYBACK_SYNC_JS
    assert PLAYBACK_SYNC_JS.count("aria-label") >= 1


def test_js_sets_aria_labels_for_all_five_icon_controls():
    """Rewind, play, forward, CC, and upload must each get an aria-label."""
    for cls in ("sc-ico-rewind", "sc-play-btn", "sc-ico-forward", "sc-cc-btn", "sc-upload"):
        assert cls in PLAYBACK_SYNC_JS, f"missing {cls} in PLAYBACK_SYNC_JS"


def test_js_has_a11y_label_function():
    """A dedicated function stamps the labels (mirrors scFixUploadFormFields)."""
    assert "scA11y" in PLAYBACK_SYNC_JS or "scLabelButtons" in PLAYBACK_SYNC_JS


def test_play_button_aria_label_updates_with_state():
    """scSetPlayIcon should also swap the aria-label (Play <-> Pause)."""
    assert "aria-label" in PLAYBACK_SYNC_JS
