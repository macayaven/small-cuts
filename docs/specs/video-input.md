# Spec: video input + device-free Live Mode tests (M3.5 prep)

Image flow stays primary; video is additive. Ground truth measured from the
five real glasses clips (relayed from the Spark, staged at
`~/small-cuts-fixtures/videos/`, never committed):

| Clip | Codec | Resolution | fps | Duration |
|---|---|---|---|---|
| IMG_8165.MOV | HEVC | 1424×1904 | 29.9 | 180.0s |
| IMG_8175.MOV | HEVC | 1376×1824 | 29.7 | 180.0s |
| IMG_8216.MOV | HEVC | 1552×2064 | 30.0 | 180.0s |
| IMG_8292.MP4 | H.264 | 976×1296 | 30.0 | 46.9s |
| IMG_8368.MOV | HEVC | 1504×2016 | 30.0 | 180.4s |

Measured facts that override earlier guesses: frames are **natively portrait
with no rotation side-data** — PyAV decodes them upright, no display-matrix
handling needed (verified visually on IMG_8292 mid-frame). Real clips run to
**180s** (glasses max) — the upload cap must be ≥180s, not 60s.

## 1. Video ingest contract (minimal change, three edits)

1. **Extract sampler** → new `src/small_cuts/frames.py`:
   - `sample_frames(path, every_n_seconds=3.0, max_frames=None) -> list[PIL.Image]`
   - Body lifted from `eval.py:_sample_video_frames` minus the sibling-JPEG
     writes — return in-memory RGB PIL Images only.
   - `pick_frame(frames) -> PIL.Image` — middle frame for v1.
   - `eval.py:_sample_video_frames` becomes a thin wrapper that saves the
     returned images (eval behavior unchanged).
2. **UI** (`ui.py`): add `gr.Video(sources=["upload"])` beside the existing
   image input; handler = `sample_frames(path)` → `pick_frame` → unchanged
   `narrate()`. No changes to `narrator.py` or the Backend protocol.
3. **Deps**: `av>=12.0` moves to core `[project.dependencies]` +
   `requirements.txt` (the Space has no `av` today → instant ImportError).

## 2. Frame→narration strategy

- **v1 (ship)**: one narration per clip, middle sampled frame. Eval evidence
  says groundedness is the weak axis on single frames already; multi-image
  prompts add vision tokens and hallucination surface with no evidence yet.
- **v1.5 (if time)**: sharpest-of-sampled via Laplacian variance, still one
  frame.
- **Deferred**: multi-frame prompts — gate behind the judged eval. A full
  video eval naively costs 5 clips × ~60 frames × 3 styles × N models ≈
  thousands of generations; `pick_frame` must land first.

## 3. Device-free preliminary tests (real footage, no hardware)

- `tests/test_frames.py` (CI-safe, synthetic clips encoded with PyAV into
  tmp_path): frame count at cadence, short-clip ≥1 frame, no side-effect
  files, RGB PIL output, eval wrapper still writes JPEGs.
- Local-only smoke (skipif fixtures missing): parametrize over the five real
  clips — decodes, ≥1 frame, portrait orientation preserved.
- One manual Gradio smoke: upload IMG_8292.MP4 → narration appears, frame
  upright, round-trip acceptable. Repeat once on the deployed Space (only
  test that catches missing-`av`-class failures).

## 4. Deferred to real-device work (post-hackathon)

Live DAT capture (streaming off the glasses) is out of scope for v1 — clips
enter via phone export → upload. When the native bridge starts, build against
MockDeviceKit from day one (`pairRaybanMeta()`, `camera.setCameraFeed(fileURL:)`
with HEVC fixtures) per the KB note
`2026-06-11-directors-cut-claude-ios-dat-bridge-reference`. Genuinely needs
hardware: Meta AI registration, Developer-Mode-after-firmware gotcha, real BT
bandwidth degradation, tap/hinge quirks.

## 5. Scene-change gate (M3.5, after video input)

32×32 grayscale mean-abs-diff in `frames.py`, threshold tuned by replaying
the five clips at 1s cadence. Proves frames → gate → narrate on recorded
footage before any Gradio streaming work.

## Open questions for Carlos

1. Is `gr.Video` upload part of the judged demo, or insurance? If judged,
   the deployed-Space smoke moves up.
2. OK to pin Gradio to 6.x now so M3.5 streaming lands on a stable API?
