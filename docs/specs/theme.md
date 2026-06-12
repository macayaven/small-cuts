# Spec: Off-Brand custom Gradio theme (M2, issue #13)

## Purpose

Replace the placeholder `gr.themes.Monochrome` in `ui.py` with a custom
cinematic theme — the **Off-Brand** quest (own visual identity). The house
style already exists in `title_card.STYLE_CARDS`; the theme borrows from it:
a dark screening-room canvas with gold marquee accents.

## Contract

### 1. `src/small_cuts/theme.py` (new module)

```python
class OffBrand(gr.themes.Base): ...

def build_theme() -> gr.themes.Base
```

- `OffBrand.__init__` configures fonts: body/headings `Spectral`
  (GoogleFont, serif fallback) — the existing house font — and
  `IBM Plex Mono` (GoogleFont, monospace fallback) for code/metadata.
- Then `.set()` overrides establishing the palette (light AND `*_dark`
  variants set to the same values — the screening room ignores OS mode):
  - `body_background_fill` / `body_background_fill_dark`: `#101014`
    (charcoal, trailer card background)
  - `body_text_color` / `body_text_color_dark`: `#E8E4D8` (bone white,
    noir card text)
  - `button_primary_background_fill` / `_dark`: `#D4AF37` (marquee gold)
  - `button_primary_text_color` / `_dark`: `#101014`
  - `block_background_fill` / `_dark`: a slightly lifted charcoal
    (e.g. `#16161C`)
  - `block_title_text_color` / `_dark`: `#D4AF37`
  - plus whatever minimal extra overrides (borders, input fills, link
    color) are needed so no component renders as a glaring white patch on
    the dark canvas. Use STYLE_CARDS hexes where a choice is needed.
- `build_theme()` returns a constructed `OffBrand()` instance.
- Module stays small (≈60 lines); no new dependencies.

### 2. `src/small_cuts/ui.py`

Replace the placeholder assignment (and its comment):

```python
THEME = gr.themes.Monochrome(font=[gr.themes.GoogleFont("Spectral"), "serif"])
```

with an import from the new module:

```python
from .theme import build_theme
THEME = build_theme()
```

`app.py` already does `demo.launch(theme=THEME)` (Gradio 6 API) — do not
change it, and do not touch anything else in `ui.py` (parallel changes wire
title cards and TTS into the same file; keep this diff to the THEME swap).

## Verification

`tests/test_theme.py` (committed alongside this spec) must pass, plus the
full local gate: `uv run pytest && uv run ruff check && uv run ruff format --check`.
Do not modify the tests; if a test looks wrong, flag it instead.
