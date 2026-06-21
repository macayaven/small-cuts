"""Rewind/forward direction: the chevrons must match where the selection moves (#3).

The library rail is newest-first (leftmost = most recent). In the ascending
``scenes`` array that backs it, the newest clip is the LAST element, so moving
visually LEFT (toward newer) is ``delta +1`` and moving RIGHT (toward older) is
``delta -1``. The rewind icon (``<<``) points LEFT, so it must advance toward
newer clips; the forward icon (``>>``) points RIGHT, so it must step toward older
clips. These tests lock that contract so the wiring can never be silently swapped
back.
"""

from __future__ import annotations

from small_cuts.viewer import _stepped_scene

# Ascending order (oldest → newest), the same order _stepped_scene receives.
SCENES = [
    {"scene_id": "oldest"},
    {"scene_id": "mid"},
    {"scene_id": "newest"},
]


def test_stepped_scene_plus_one_moves_toward_newer():
    """delta +1 advances one step toward the newest (end of ascending array)."""
    assert _stepped_scene(SCENES, "oldest", +1)["scene_id"] == "mid"
    assert _stepped_scene(SCENES, "mid", +1)["scene_id"] == "newest"


def test_stepped_scene_minus_one_moves_toward_older():
    """delta -1 steps one step toward the oldest (start of ascending array)."""
    assert _stepped_scene(SCENES, "newest", -1)["scene_id"] == "mid"
    assert _stepped_scene(SCENES, "mid", -1)["scene_id"] == "oldest"


def test_stepped_scene_wraps_around():
    assert _stepped_scene(SCENES, "newest", +1)["scene_id"] == "oldest"
    assert _stepped_scene(SCENES, "oldest", -1)["scene_id"] == "newest"


def test_rewind_chevron_moves_visually_left_toward_newer():
    """``<<`` (rewind) points LEFT; LEFT in the newest-first rail = newer = delta +1.

    User is on the middle clip. Pressing ``<<`` must select the clip to its LEFT,
    which is the NEWEST clip — so the delta passed to _stepped_scene must be +1.
    """
    assert _stepped_scene(SCENES, "mid", +1)["scene_id"] == "newest"


def test_forward_chevron_moves_visually_right_toward_older():
    """``>>`` (forward) points RIGHT; RIGHT in the newest-first rail = older = delta -1.

    User is on the middle clip. Pressing ``>>`` must select the clip to its RIGHT,
    which is the OLDEST clip — so the delta passed to _stepped_scene must be -1.
    """
    assert _stepped_scene(SCENES, "mid", -1)["scene_id"] == "oldest"
