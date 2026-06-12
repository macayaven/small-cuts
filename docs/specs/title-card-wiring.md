# Spec: Title-card wiring + title derivation (M2, issue #12)

## Purpose

`title_card.render_title_card` exists but nothing calls it. Wire it into the
Gradio app so every narration is accompanied by its movie-style title card,
with the title derived from the narration's first clause (caller-side, per
docs/specs/title-card.md "out of scope" note).

## Contract

### 1. `derive_title` (new, in `src/small_cuts/title_card.py`)

```python
def derive_title(text: str, max_len: int = 60) -> str
```

- Strips surrounding whitespace.
- Strips one leading bracketed style tag if present (`"[Noir Detective] The
  rain…"` → `"The rain…"`) — the mock backend emits narrations in this shape.
- Returns the **first clause**: everything before the first sentence-ending
  punctuation (`.`, `!`, `?`, `;`) or em-dash (`—`). The terminator itself is
  not included. Trailing ellipsis in the source ("Lunch... changes") must not
  produce an empty or one-word title: a `...`/`…` only terminates the clause
  when followed by whitespace + an uppercase letter, otherwise it is kept.
  (Simplification allowed: treat `...` like any terminator BUT only after the
  clause already has ≥ 3 words.)
- If the clause is longer than `max_len` characters, cut at the last word
  boundary that fits and append `…` (single ellipsis char). Never cut
  mid-word; never return more than `max_len` chars total.
- Empty / whitespace-only input → `"Untitled Scene"`.
- Pure + deterministic. No new dependencies.

### 2. UI wiring (`src/small_cuts/ui.py`)

- Right column gains a card display **above** the narration textbox:
  `gr.Image(label="Title card", interactive=False)`.
- `_narrate_handler` and `_narrate_video_handler` now return
  `tuple[PIL.Image.Image, str]` = `(card, narration_text)`:
  `card = render_title_card(derive_title(text), style_key)` at the default
  1280×720 size, using the **requested** style key.
- The no-image / no-video placeholder paths also render a card from the
  placeholder text (the show must go on).
- All three event wirings (`go.click`, `image.change`, `video.change`) get
  `outputs=[card, narration]`.

## Verification

`tests/test_title_wiring.py` (committed alongside this spec) must pass, plus
the full local gate: `uv run pytest && uv run ruff check && uv run ruff format --check`.
Do not modify the tests; if a test looks wrong, flag it instead.
