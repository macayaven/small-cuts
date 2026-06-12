# Spec: Kokoro TTS behind the backend pattern (M2, issue #11)

## Purpose

Give the narrator a voice. New module `src/small_cuts/tts.py` mirroring the
`narrator.py` backend pattern exactly (Protocol + mock + real, env-var
selection), plus an on-demand "read it to me" button in the Gradio app.
All local — no cloud TTS (Off the Grid quest).

## Contract

### 1. `src/small_cuts/tts.py`

```python
@dataclass(frozen=True)
class Speech:
    sample_rate: int
    audio: np.ndarray  # mono float32, values in [-1.0, 1.0]
    backend: str
    model_id: str
    latency_s: float

class TTSBackend(Protocol):
    name: str
    model_id: str
    def synthesize(self, text: str) -> tuple[int, np.ndarray]: ...

def get_tts_backend(name: str | None = None) -> TTSBackend
def speak(text: str, backend: TTSBackend | None = None) -> Speech
```

- `get_tts_backend`: reads `SMALL_CUTS_TTS_BACKEND` env var, default `mock`;
  unknown name → `ValueError("Unknown TTS backend …")` (mirror
  `narrator.get_backend`).
- `speak`: empty / whitespace-only text → `ValueError` mentioning "empty";
  otherwise times the backend call and returns a `Speech`.

### 2. `MockTTSBackend` — `name = "mock"`, `model_id = "mock-tts-0"`

Deterministic, weightless, CI-safe:
- 24_000 Hz mono float32 sine wave, amplitude ≤ 0.3.
- Duration scales with text length, clamped to [0.2s, 2.0s].
- Pitch derives from the text content (e.g. `220 + sum(text.encode()) % 220`
  Hz) so different texts produce different audio, same text identical audio.

### 3. `KokoroBackend` — `name = "kokoro"`, `model_id = "hexgrad/Kokoro-82M"`

- Lazy: constructing the backend must NOT import `kokoro`; first
  `synthesize` call does. If the import fails, raise `RuntimeError` with an
  actionable message (mention `uv sync --extra tts`).
- Uses `kokoro.KPipeline(lang_code="a")`, voice from `SMALL_CUTS_TTS_VOICE`
  env var (default `af_heart`), 24_000 Hz output; concatenate segment audio
  into one mono float32 array.
- Add optional dependency group to `pyproject.toml`:
  `tts = ["kokoro>=0.9", "soundfile>=0.12"]`. CI does NOT install it; no
  import of kokoro at module import time (CI must stay green without it).

### 4. UI wiring (`src/small_cuts/ui.py`)

- Right column, under the narration textbox: a secondary button
  `🔊 Read it to me` and `gr.Audio(label="The narrator speaks…", interactive=False)`.
- New handler:
  ```python
  def _speak_handler(text: str) -> tuple[int, np.ndarray] | None
  ```
  Returns `None` when `text` is empty/whitespace (clears the player),
  otherwise `(speech.sample_rate, speech.audio)` via `speak(text)`.
- Wiring: `speak_btn.click(_speak_handler, inputs=[narration], outputs=[audio])`.
- TTS is on-demand only — narration handlers stay untouched (a parallel
  change wires title cards into them; do not modify their signatures).

## Verification

`tests/test_tts.py` (committed alongside this spec) must pass, plus the full
local gate: `uv run pytest && uv run ruff check && uv run ruff format --check`.
Do not modify the tests; if a test looks wrong, flag it instead.
Manual sanity (optional, not CI): `uv sync --extra tts` then
`SMALL_CUTS_TTS_BACKEND=kokoro uv run python -c "from small_cuts.tts import speak; print(speak('One man. One sandwich.').audio.shape)"`.
