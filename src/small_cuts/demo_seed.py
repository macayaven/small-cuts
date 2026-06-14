"""Seeded 'hero' library — curated VIDEO cuts so the Space loads alive.

Real first-person glasses moments, **muted** (the generated narration is the only
audio, which also strips any incidental conversation), narrated in the one signature
deadpan voice. The live "Try it" sandbox runs the real model; this seed just gives a
first-time visitor a channel with a few finished cuts to scroll. Five short, compressed,
face-free clips so the Space boots fast and respects bystander privacy.
"""

from __future__ import annotations

import os

from PIL import Image

STYLE_KEY = "deadpan"
SEED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_media")

# (clip, poster, title, narration, visibility) — ordered oldest → newest.
SEED: list[tuple[str, str, str, str, str]] = [
    (
        "desk-laptop.mp4",
        "desk-laptop.jpg",
        "Debugging His Own Ambition",
        "It is late — the specific, self-inflicted late of someone building a thing nobody "
        "asked for. On the monitor a small game he is making flickers half-finished, its rules "
        "still being argued into existence. His hands move with the patience of a man debugging "
        "his own ambition, and the coffee, just off-frame, went cold around the last good idea.",
        "private",
    ),
    (
        "the-stumble.mp4",
        "the-stumble.jpg",
        "He Meant to Do That",
        "He has stepped out of the bar for air and the small chemical comfort of the vape, and "
        "the pavement, sensing an opening, tilts very slightly underfoot. He recovers, as one "
        "does, with the careful dignity of a man who would prefer the record to show he meant to "
        "do that. The night says nothing. It has seen steadier, and worse.",
        "private",
    ),
    (
        "street-parked-car.mp4",
        "street-parked-car.jpg",
        "Just Five Minutes",
        "The car is parked with the easy confidence of a driver who said 'just five minutes' and "
        "meant it the way everyone means it. The street is in no hurry to disagree. Somewhere "
        "nearby a meter is running, patient and unread.",
        "public",
    ),
    (
        "night-drive.mp4",
        "night-drive.jpg",
        "Photographs Well at Night",
        "The city slides past at the speed of someone who knows the way and feels no need to "
        "prove it. Streetlight opens and closes on the windshield; the older facades hold their "
        "glow a little longer than the new ones. He is driving through the part of town that "
        "photographs well at night, which is, if one is honest about Barcelona, most of it.",
        "public",
    ),
    (
        "rayuela.mp4",
        "rayuela.jpg",
        "The Stone Almost Never Reaches the Sky",
        "Through the wire, a hopscotch waits on the schoolyard floor, its chalk gone soft with "
        "weather. At the bottom is the Earth; at the top, the Sky — and the old difficulty "
        "between them, that the stone, nudged by the toe of a shoe, almost never reaches the "
        "Sky. He passes on the far side of the fence now, a grown man in grown shoes, and does "
        "not stop. The ingredients were always so small: a sidewalk, a stone, the tip of a shoe.",
        "public",
    ),
]


def clip_path(name: str) -> str:
    """Absolute path to a bundled seed clip (served via gr.set_static_paths)."""
    return os.path.join(SEED_DIR, name)


def load_poster(name: str) -> Image.Image:
    """Load a bundled poster frame (the still shown before the clip plays / in the shelf)."""
    return Image.open(os.path.join(SEED_DIR, name)).convert("RGB")
