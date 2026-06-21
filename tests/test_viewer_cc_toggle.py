"""CC caption toggle: the gate must use a selector Gradio's CSS prefixer can't break (#2).

Gradio 6 prepends ``.gradio-container.gradio-container-6-18-0 .contain`` to every
custom CSS rule. A selector rooted on ``body`` (e.g. ``body:not(.sc-cc-on)
.sc-subtitle``) becomes ``.contain body:not(...) .sc-subtitle`` — impossible to
match, because ``<body>`` is an *ancestor* of ``.contain``, never a descendant.
The subtitle therefore showed at all times and the CC button appeared to do nothing.

The fix moves the toggle class from ``<body>`` to ``.sc-theater`` (inside
``.contain``, persists across stage re-renders, ancestor of both the subtitle and
the CC button), so the prefixed selector resolves correctly.
"""

from __future__ import annotations

from small_cuts.viewer import PLAYBACK_SYNC_JS, VIEWER_CSS


def test_cc_gate_does_not_root_on_body():
    """The broken selector ``body:not(.sc-cc-on) .sc-subtitle`` must be gone."""
    assert "body:not(.sc-cc-on) .sc-subtitle" not in VIEWER_CSS


def test_cc_gate_roots_on_sc_theater():
    """The gate must use ``.sc-theater`` (inside .contain, so Gradio's prefix works)."""
    assert ".sc-theater:not(.sc-cc-on) .sc-subtitle" in VIEWER_CSS


def test_cc_button_on_state_does_not_root_on_body():
    assert "body.sc-cc-on .sc-cc-btn" not in VIEWER_CSS


def test_cc_button_on_state_roots_on_sc_theater():
    assert ".sc-theater.sc-cc-on .sc-cc-btn" in VIEWER_CSS


def test_cc_js_toggles_class_on_sc_theater_not_body():
    """The click handler must toggle the class on .sc-theater, not on <body>."""
    assert "classList.toggle('sc-cc-on')" in PLAYBACK_SYNC_JS
    assert ".sc-theater" in PLAYBACK_SYNC_JS
    # the old body-rooted toggle must be gone
    assert "document.body.classList.toggle('sc-cc-on')" not in PLAYBACK_SYNC_JS
    assert "document.body.classList.add('sc-cc-on')" not in PLAYBACK_SYNC_JS
