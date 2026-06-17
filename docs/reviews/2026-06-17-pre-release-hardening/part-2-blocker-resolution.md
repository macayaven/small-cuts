# Pre-Release Hardening Review Part 2: Blocker Resolution

**Date:** 2026-06-17  
**Branch:** `codex/pre-release-hardening`  
**Blocker fix commit:** `a1dede0 Hydrate relay scenes for gallery controls`  
**Prior hardening commits:** `5461407 Harden upload budget and playback`, `169151c Add pre-release hardening review report`  
**Scope:** Relay-mode gallery interaction hydration in the Gradio viewer.  
**Explicit non-scope:** iOS/native app code.

## Verdict Response

The reviewer's remaining blocker was valid.

The previous lazy-hydration change correctly reduced bucket list refresh work by hydrating only
thumbnail/card media during `BucketSceneClient.list_scenes()`. The missed follow-through was in the
gallery interaction callbacks. They read scenes from `scenes_state`, where `clip_url` and
`audio_url` may still be raw bucket-relative paths, and passed those raw scenes directly into
`format_stage(scene, engine.base_url)`.

That could render browser media URLs such as:

```text
media/scene_123/clip.mp4
media/scene_123/voice.wav
```

Those paths are not valid Gradio-served URLs, so a gallery select, rewind/forward, or back-to-live
interaction could break media playback in relay bucket mode.

## Fix Summary

The fix introduces one shared control-rendering path:

```python
_engine_scene_control_outputs(...)
```

That helper:

1. Receives the selected/stepped/live scene.
2. Hydrates the active scene through `_scene_with_media_urls(scene, engine)`.
3. Calls `format_stage(...)` only after media has usable URLs.
4. Renders header, stage, and audio.
5. Packs the updated engine UI state.

The three relay-mode callbacks now use that shared path:

- `_on_select`
- `_step_engine`
- `_back_to_live_engine`

## Why This Fix Is Preferable

This keeps the lazy hydration boundary from Part 1:

- library refresh: hydrate only shelf media,
- active scene render: hydrate full media.

It avoids reverting to eager audio/video hydration for every library item, and it removes the
duplicate stage-rendering logic that allowed `poll_engine()` and gallery callbacks to drift apart.

## Files Changed

Application/runtime:

- `src/small_cuts/viewer.py`

Tests:

- `tests/test_viewer.py`

No iOS files were touched.

## Regression Tests Added

### `test_engine_scene_control_outputs_hydrates_raw_relay_media`

Proves that a raw relay scene with:

```text
media/scene/frame.jpg
media/scene/clip.mp4
media/scene/voice.wav
```

is rendered through the media client before reaching the stage/audio HTML:

```text
/tmp/frame.jpg
/tmp/clip.mp4
/tmp/voice.wav
```

### `test_engine_gallery_callbacks_do_not_format_raw_relay_scenes_directly`

Guards against reintroducing the exact old pattern:

```python
payload = format_stage(scene, engine.base_url)
```

inside `build_viewer_app()` relay gallery callbacks.

## Verification Evidence

Blocker-specific red/green check:

```bash
uv run pytest \
  tests/test_viewer.py::test_engine_scene_control_outputs_hydrates_raw_relay_media \
  tests/test_viewer.py::test_engine_gallery_callbacks_do_not_format_raw_relay_scenes_directly \
  -q
```

Observed after fix:

```text
.. [100%]
```

Viewer regression suite:

```bash
uv run pytest tests/test_viewer.py -q
```

Observed:

```text
70 passed
```

Full local gate:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Observed:

```text
ruff check: All checks passed.
ruff format --check: 56 files already formatted.
pytest: 310 passed, 6 warnings.
```

Warnings are existing dependency/test warnings:

- Starlette `httpx` deprecation warning from FastAPI TestClient.
- Pillow `Image.getdata` deprecation warnings in title-card tests.
- Torch/Kokoro warnings in the mock/local viewer test path.

## Reviewer Retest Plan

1. Check out the branch:

```bash
git fetch origin
git checkout codex/pre-release-hardening
git log --oneline -5
```

Expected to include:

```text
a1dede0 Hydrate relay scenes for gallery controls
169151c Add pre-release hardening review report
5461407 Harden upload budget and playback
```

2. Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

3. Specifically inspect/verify the relay interaction behavior:

- bucket list refresh still hydrates only shelf media,
- selecting a gallery item hydrates `clip_url` and `audio_url`,
- rewind/forward hydrates `clip_url` and `audio_url`,
- back-to-live hydrates `clip_url` and `audio_url`,
- stage HTML does not contain raw `media/.../clip.mp4` paths after those interactions.

4. On a deployed HF Space after promotion:

- open DevTools Network,
- click multiple library clips,
- click rewind/forward,
- click back-to-live,
- confirm no `media/.../clip.mp4` or `media/.../voice.wav` root-level 404s appear,
- confirm selected clips play with valid Gradio/HF bucket URLs.

## Reviewer Questions to Close

- Does this shared helper satisfy the blocker without reintroducing eager audio/video hydration?
- Are the two regression tests sufficient to prevent the exact callback drift that caused the bug?
- After deployed-Space validation, can the verdict move from `NOT GO` to `GO`?

## Recommended Verdict Criteria

Move to `GO` if:

- the full local gate passes,
- the reviewer accepts the shared helper as the active-scene hydration boundary,
- the deployed Space no longer emits root-level media 404s on gallery select, step, or back-to-live.

Request changes only if:

- any relay gallery interaction still renders raw `media/...` URLs into stage/audio HTML,
- the helper regresses non-relay engine mode,
- or the deployed HF Space shows new playback failures not covered by the current local tests.
