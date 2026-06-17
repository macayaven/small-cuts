1. **Position**

Hybrid: **B native-first, but only after muxing narration into the scene MP4; A’s relay/data fixes are prerequisite, and C becomes the fallback if decoupled audio remains a product invariant.** The current failure is not “bad sync code”; it is the decision to make a hidden `<audio>` clock drive a separate looping `<video>` and captions by DOM polling.

2. **Target Architecture**

Each published scene should have one browser-playable, faststart `mp4` whose video track is loop-extended to the narration duration and whose audio track is the narration. That keeps the existing `media.clip_url` contract surface instead of adding `playback_url` immediately; `media.audio_url` can remain for legacy/mobile until a later contract bump. This works with the strict current schema, where `media` only permits `frame_url`, `card_url`, `audio_url`, and `clip_url` ([narrated-scene.schema.json](/Volumes/mac-studio-ssd/workspace/small-cuts/docs/contracts/narrated-scene.schema.json:62)).

The stage becomes a native [`gr.Video`](https://www.gradio.app/docs/gradio/video) output: `gr.Video(value=clip_url, subtitles=subtitle_value, autoplay=False, loop=False, show_label=False, container=False, elem_classes=["sc-stage-video"])`. The browser’s `<video>` element is the only clock. Audio, video, seek, pause, buffering, and caption time all share that one media timeline. Captions move from `render_stage_html()` spans to `gr.Video(subtitles=...)`, either a generated VTT file or Gradio’s documented `list[{"text": str, "timestamp": [start, end]}]` format.

The Library remains [`gr.Gallery`](https://www.gradio.app/docs/gradio/gallery), using thumbnail/card images for cheap rail rendering, not eager video rail previews. It already exists at [viewer.py](/Volumes/mac-studio-ssd/workspace/small-cuts/src/small_cuts/viewer.py:2204). `shelf.select(fn)` continues to map `SelectData.index` to the chosen scene. `gr.State` keeps session-level `scenes`, `pinned_id/current_id`, liked/reported sets, and upload panel state, as it does today at [viewer.py](/Volumes/mac-studio-ssd/workspace/small-cuts/src/small_cuts/viewer.py:2068). Avoid storing PyAV containers or locks in `gr.State`, because Gradio deep-copies state values per its [`gr.State`](https://www.gradio.app/docs/gradio/state) docs.

Media serving stays relay-first. On Spaces, `_default_direct_media_urls()` returns true when `SPACE_ID` and the relay bucket are set, so `media_url()` returns direct HF bucket resolve URLs instead of downloading files into the Space ([hf_relay.py](/Volumes/mac-studio-ssd/workspace/small-cuts/src/small_cuts/hf_relay.py:215), [hf_relay.py](/Volumes/mac-studio-ssd/workspace/small-cuts/src/small_cuts/hf_relay.py:439)). For local/upload files, keep `gr.set_static_paths(...)`, already used for seed/audio/upload paths ([viewer.py](/Volumes/mac-studio-ssd/workspace/small-cuts/src/small_cuts/viewer.py:1469), [viewer.py](/Volumes/mac-studio-ssd/workspace/small-cuts/src/small_cuts/viewer.py:2035)); official docs confirm it serves files directly without copying to cache: [`gr.set_static_paths`](https://www.gradio.app/docs/gradio/set_static_paths). If direct remote URLs force Gradio server-side download/transcode in practice, the fallback is lazy cache-on-select, not manifest-time hydration.

State transitions stay Python-declarative: `.select()`, rewind/forward `.click()`, back-to-live, upload completion, and relay SSE all return `gr.update(value=clip_url, subtitles=...)` for the player plus header/feed/gallery/state updates. `gr.Video.end()` can optionally advance clip-to-clip. The existing SSE bridge should survive, because relay refresh is push-only and currently wired through `gr.HTML(js_on_load=...)` and `relay_events.relay_scene(...)` ([viewer.py](/Volumes/mac-studio-ssd/workspace/small-cuts/src/small_cuts/viewer.py:2215), [viewer.py](/Volumes/mac-studio-ssd/workspace/small-cuts/src/small_cuts/viewer.py:2511)); [`gr.HTML`](https://www.gradio.app/docs/gradio/html) explicitly supports `js_on_load`, `trigger`, and event hooks.

3. **How It Kills Each Symptom**

1. **Video startup latency:** no hidden audio preload plus muted-loop video preload race. One faststart H.264/AAC MP4 loads through byte-range media delivery; shelf still loads only thumbnails. Current direct relay already avoids server-side media downloads in the happy path ([hf_relay.py](/Volumes/mac-studio-ssd/workspace/small-cuts/src/small_cuts/hf_relay.py:221)).
2. **A/V/caption desync on stall:** a single media element stalls as a unit. Audio cannot run ahead of video because it is in the same MP4. Captions are native subtitles tied to video time, not JS driven from `audio.currentTime`.
3. **Frame jump on pause/resume:** delete the modulo assignment `audio.currentTime % video.duration` in `scVideoTargetTime()` and `scSyncVideoToAudio()` ([viewer.py](/Volumes/mac-studio-ssd/workspace/small-cuts/src/small_cuts/viewer.py:1739)). Native pause preserves `currentTime`.
4. **Wrong play icon for video-only scenes:** remove the custom play icon state machine at [viewer.py](/Volumes/mac-studio-ssd/workspace/small-cuts/src/small_cuts/viewer.py:1846). Native controls or Python-owned `gr.Button(icon=...)` state no longer branches on whether hidden audio has a `src`.
5. **Homemade jank:** delete the 120 ms `setInterval` that drives video, captions, progress, and icon state ([viewer.py](/Volumes/mac-studio-ssd/workspace/small-cuts/src/small_cuts/viewer.py:1824)). The player becomes a Gradio component plus small layout CSS.

4. **Migration Plan**

1. In the publishing/upload path, produce a muxed `clip_url`: loop/extend visual frames to narration duration, mux narration as AAC, write H.264 MP4 with moov atom at front. Keep `audio_url` during migration.
2. Add a small formatter beside `format_stage()` ([viewer.py](/Volumes/mac-studio-ssd/workspace/small-cuts/src/small_cuts/viewer.py:752)) that returns player value, subtitle payload, frame fallback, title, visibility, and source badge.
3. In `build_viewer_app()`, replace `stage = gr.HTML(...)` and hidden `audio = gr.HTML(...)` with `player = gr.Video(...)` and a still-image fallback for scenes without `clip_url`.
4. Rewrite `poll_engine()`, `_engine_scene_control_outputs()`, `_on_local_select()`, `_step_local()`, upload success, and relay tick outputs to update `player` instead of `stage + audio`.
5. Delete `_audio_html()` and the playback parts of `PLAYBACK_SYNC_JS`: trusted gesture handling, volume slider, video buffer event syncing, `setInterval`, play icon toggling, caption/progress updates. Roughly [viewer.py](/Volumes/mac-studio-ssd/workspace/small-cuts/src/small_cuts/viewer.py:1734) through [viewer.py](/Volumes/mac-studio-ssd/workspace/small-cuts/src/small_cuts/viewer.py:1867) should not survive. Keep or split unrelated JS: favicon, HF header safe zone, upload form hardening, and clapperboard reveal.
6. Remove the custom progress bar and pill play/volume controls at [viewer.py](/Volumes/mac-studio-ssd/workspace/small-cuts/src/small_cuts/viewer.py:2102) through [viewer.py](/Volumes/mac-studio-ssd/workspace/small_cuts/viewer.py:2134). Rewind/forward, like, flag, upload remain Gradio buttons.
7. Keep `RELAY_EVENT_BRIDGE_JS`, `demo.load(_tick, ...)`, and no timer polling.

5. **Resource Efficiency**

This removes one media request in the steady state if WAV/MP3 no longer loads separately, and it replaces uncompressed WAV upload-mode playback with AAC inside MP4. During migration, duplicate `audio_url` costs bytes but avoids breaking mobile/legacy. There is no base64 video path, no per-frame JS, no global polling loop, and no per-viewer Python streaming generator for replay. The Space serves manifest/SSE and Gradio UI; HF bucket/CDN or Gradio static file routes serve media. For many viewers, that is the correct shape for CPU-basic. Use [`gr.Video(streaming=True)`](https://www.gradio.app/guides/streaming-outputs) only for a future true live generator; replayable scenes should stay plain URL media.

6. **Risk + Unknowns**

Biggest risk: Gradio docs say `gr.Video(value=...)` accepts a URL, but the deployed Gradio version may still proxy, copy, or transcode remote URLs. Cheapest experiment: on local first, then one explicitly approved `macayaven/*` Space smoke, render a single direct HF resolve MP4 and a single local static MP4 through `gr.Video(value=..., subtitles=...)`; inspect Network for range behavior, server logs for downloads/transcodes, first-frame latency, captions, mobile Safari, and `.end()`.

Other risks: audible autoplay is browser-blocked, so the UX should remain tap-to-start. SSR must stay off because `app.py` disables it on Spaces for custom routes ([app.py](/Volumes/mac-studio-ssd/workspace/small-cuts/app.py:19)). `/gradio_api/file=` and `set_static_paths` expose directories, so keep the allow surface narrow. ZeroGPU stays out of viewer startup; `app.py` already builds the viewer without warming local inference in relay/engine/upload modes ([app.py](/Volumes/mac-studio-ssd/workspace/small-cuts/app.py:88)). Captions need real timing eventually; approximate chunks are acceptable only as a transitional portfolio polish.

7. **Test / Verification Plan**

Local gate, exactly: `uv run ruff check . && uv run ruff format --check . && uv run pytest` ([CLAUDE.md](/Volumes/mac-studio-ssd/workspace/small-cuts/CLAUDE.md:51)).

Add focused tests for scene-to-player formatting, subtitle generation, no-clip fallback, direct-vs-cached media resolution, and “do not hydrate all clips when direct URLs are off.” Manual browser smoke: initial load, first frame, tap-to-start, pause/resume, seek, captions, video-only scene, missing audio, shelf select, rewind/forward, back-to-live, upload completion, SSE relay refresh, mobile 9:16/no-scroll layout, and network verification for 206/range or no Space-side media stampede. Live-Space smoke should be under `macayaven/*` only and only after explicit approval, matching the repo safety rule.

8. **Confidence**

**0.78.** Strongest dissent: native `gr.Video` may not be portfolio-grade enough once the owner sees the loss of custom chrome, source badge overlay, and cinematic control pill. If Gradio remote URL handling is proxy-heavy, or if the product truly requires independently looping b-roll under a separately generated narration track, then the correct answer is not more incremental JS; it is route **C**, a real Svelte component with typed `FileData` media and event-driven playback.


