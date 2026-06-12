# Spec: Title-card renderer (M2)

## Purpose

Every narration gets a movie-style title card: a 16:9 image shown beside the
narration in the Gradio app, styled per director. Part of the **Off-Brand**
quest (custom visual identity) — pure PIL, no model, no network.

## Contract

New module `src/small_cuts/title_card.py`:

```python
def render_title_card(
    title: str,
    style_key: str,
    size: tuple[int, int] = (1280, 720),
) -> PIL.Image.Image
```

- Returns an RGB image of exactly `size`.
- `style_key` must be a key of `styles.STYLES`; unknown keys raise `KeyError`
  (same behavior as `build_messages`).
- **Deterministic**: identical inputs produce byte-identical output. No
  randomness, no timestamps.
- Layout: a kicker line (`A SMALL CUTS PICTURE`), the title (uppercased,
  wrapped, centered, dominant), and a style label subtitle (from
  `STYLES[style_key].label`).
- Title text wraps to fit; very long titles (200+ chars) must render without
  raising or overflowing the canvas.
- Empty title renders the kicker + subtitle only (no crash).

## Per-style art direction

One palette + typographic treatment per style, keyed off `STYLES`:

| style | background | text | treatment |
|---|---|---|---|
| deadpan | warm off-white `#F2EFE6` | near-black `#1A1A1A` | thin rule above+below title |
| noir | black `#0D0D0F` | bone white `#E8E4D8` | hard white 2px frame inset |
| nature_doc | deep green `#0E2A1B` | cream `#F0E9D2` | double-line frame |
| trailer | charcoal `#101014` | gold `#D4AF37` | wide letter-spacing (inserted spaces) |
| telenovela | crimson `#5C0A14` | rose white `#FFE9EC` | ornament line `♦ ─── ♦` under title |
| symmetrist | pastel pink `#F7D6C9` | brown `#5B3A29` | perfectly centered, thin border 8px inset |

Every key in `STYLES` must have an entry — add a module-level mapping and a
test guards the invariant (new styles must add palettes).

## Constraints

- Fonts: `ImageFont.load_default(size=...)` (Pillow ≥ 10.1 scalable default)
  — no bundled font files, no new dependencies.
- Must work headless (no display) — CI runs it.
- Keep the module under ~120 lines; this is a hackathon, not a layout engine.

## Out of scope (M2 later steps)

- Deriving the title from the narration text (caller's job).
- Animated cards, gradients, photo-blending.
- Gradio wiring (separate change).
