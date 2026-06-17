# RESEARCH BRIEF: Replacing the Hand-Rolled Audio-Clock Video Player

**For:** Small Cuts engineering panel (Opus / codex / agy / opencode / agent)
**Subject:** Retiring `PLAYBACK_SYNC_JS` + synchronous media hydration in favor of Gradio-native facilities
**Date:** 2026-06-17 · **Source:** 8-agent doc/code research workflow (`gradio_video_slider` repo + 8 Gradio docs)

> Read alongside `00-context.md`. This brief is the shared evidence base; every proposal cites it.

---

## 1. Executive Summary

- **We are building at the wrong layer.** The hand-rolled player reimplements three things the
  browser + Gradio already give us free: (a) a playback clock + buffering + stall handling (the
  native `<video>`/`<audio>` element *is* the clock), (b) caption sync (native `<track>` via
  `gr.Video(subtitles=...)`), (c) lazy, range-streamed media delivery (Gradio's `/gradio_api/file=`
  route already returns **HTTP 206 + `Accept-Ranges: bytes`** via `RangedFileResponse`). Every
  symptom — desync, wrong-frame-on-resume, wrong play-icon, jank — is a self-inflicted consequence of
  the 120 ms `setInterval` master-slave loop that none of these native facilities need.

- **The "official" `gradio_video_slider` is NOT an escape hatch — it is the same trap.** Decisive
  finding: `class VideoSlider(gr.HTML)` (DEVAIEXP/gradio_component_videoslider,
  `src/gradio_video_slider/gradio_video_slider.py:7`) is itself a `gr.HTML` subclass with a
  hand-rolled master-slave JS sync and **base64 data-URI** media delivery. Adopting it would
  *re-package* our problem, not fix it — and base64 video for a multi-clip channel is catastrophic
  (no range requests, no streaming, no caching). The real reference is **pngwn/gradio-imageslider**
  (subclasses `gradio.components.base.Component`, uses a `FileData`-backed `data_model`).

- **The synchronous-hydration cold-start is a data-layer bug whose fix already exists in our code.**
  `hf_relay._hydrate_scene` calls `media_url() → fs.cat()` for every media key inside the
  manifest-read loop when `direct_media_urls` is false (`hf_relay.py:248-261`). The cure is in-repo:
  the `direct_media_urls=True` branch (`hf_relay.py:221`) returns non-proxied HF resolve URLs, and
  `gr.set_static_paths([...])` is already wired (`viewer.py:1469, 2035`). No new infra — just wiring.

- **Native `gr.Video` + `gr.Gallery` + `gr.State` + event chaining is a complete replacement.**
  `gr.Video(value=url, autoplay, loop, subtitles=<vtt>, playback_position)` makes the browser its own
  clock; `gr.Gallery` (supports video items) is the rail with native `.select()`; `gr.State` holds
  per-session playlist/index; `.end()`/`.select()`/`.then()` chain scene advance declaratively. No
  `setInterval`, no second muted video, no caption-visibility driver.

- **Themes, not CSS hacks, own the chrome.** Most of the hand-written CSS maps to theme tokens
  (`slider_color`=progress, `loader_color`=spinner, `block_background_fill`/`block_radius`/
  `block_shadow`=player card, `button_primary_*`=controls). Keep `css_paths=` only for the
  irreducible 9:16 geometry — and have that CSS read `var(--slider-color)` etc. to stay in sync.

---

## 2. How the "official" `gradio_video_slider` actually works (a cautionary tale)

| Aspect | What it does | Verdict |
|---|---|---|
| **Base class** | `class VideoSlider(gr.HTML)` from `html_template=`/`css_template=`/`js_on_load=` strings. | **Same gr.HTML hack we already have.** Not Svelte. |
| **Sync** | Event-driven master-slave: `v1.onplay→v2.play()`, `v1.onpause→v2.pause()`, drift `v1.ontimeupdate→ if |Δ|>0.2: v2.currentTime=v1.currentTime`. **No `setInterval`.** | **One idea worth lifting:** event-driven correction + 0.2 s threshold, vs our 120 ms poll. |
| **Media delivery** | `postprocess` → base64 `data:{mime};base64,…` URIs; browser sets `v.src=data[0]`. | **Anti-pattern for us.** No range/streaming/caching. |
| **"Slider"** | CSS `clip-path` wipe, mouse-driven. Not a seek bar; no captions/progress/playlist. | Two-video comparison widget — wrong use case. |
| **Typing** | `EVENTS=['change']`, `api_info→{'type':'string'}`, no `preprocess`/`data_model`; Alpha. | Weak typing, no clean server input. |

**The real template — pngwn/gradio-imageslider** (copy this for route C): backend
`class ImageSlider(Component)` with `data_model = SliderData(GradioRootModel)` whose fields are
`FileData`; `EVENTS=[Events.change, Events.upload]`; `preprocess`/`postprocess` wrap media as
**`FileData(url=...)` — NOT base64**, which is exactly what enables HTTP range / streaming / lazy
load. Layout from `gradio cc create`: `backend/<pkg>/<comp>.py` + `frontend/Index.svelte`
(Interactive vs Static) + `frontend/example/Example.svelte` + `frontend/shared/*.svelte` +
`package.json` + `demo/app.py` + `pyproject.toml`. Seek/drag = a self-contained `Slider.svelte`
(d3-drag, `transform: translateX`, `<slot/>`), framework-grade not hand-coded mouse math.

**Takeaway:** "adopt the official slider" is off the table. Go *more* native (B) or build a *real*
Svelte component from the imageslider template (C). The slider's only gift is event-driven drift.

---

## 3. Capability map: concern → best mechanism (exact APIs)

| Concern | Best mechanism | Exact APIs |
|---|---|---|
| **Render + seek a scene** | Native player, URL value, no download | `gr.Video(value=clip_url, autoplay=True, loop=True, playback_position=<secs>, height=, width=)`; seek works via file route **HTTP 206 + `Accept-Ranges`** (`RangedFileResponse`). |
| **Captions in sync** | Native `<track>` — *delete caption JS* | `gr.Video(subtitles='scene.vtt'\|'scene.srt'\|list[dict])`. |
| **Video ↔ audio sync** | **Prefer one muxed mp4** (native element = sole clock) | If decoupled: keep `gr.Audio`, advance on `.end()`; intra-clip sync via event-driven `timeupdate`/`seeking`/`waiting` (0.2 s threshold), **never** 120 ms `setInterval`. |
| **Transport controls** | Native controls + declarative state | Native scrubber free. Custom: `gr.Button(icon=, variant=, interactive=)` + `.click()`, docked via `gr.Video(buttons=[...])`; play/pause icon via `gr.update(icon=...)` — kills the wrong-icon bug (state in Python, not a poll). |
| **Library rail** | `gr.Gallery` (supports video items) | `gr.Gallery(value=list, columns=, object_fit=, allow_preview=, selected_index=, file_types=)`; `.select(fn)` → `SelectData` → set `State.current_index` → load scene. |
| **Lazy media / file-serving** | Stop synchronous hydration; serve by URL w/ range | `direct_media_urls=True` (HF resolve URLs) **or** lazy per-media GET + `gr.set_static_paths([SEED_DIR, GENERATED_AUDIO_DIR, cache_dir])`; `launch(allowed_paths=[...])`. **Caveat:** never pass a *remote* URL as a component **value** (`gr.Video(value=remote_url)` triggers server download/transcode → fails on CDN/pre-signed URLs; gradio #3940/#10726). Put remote URLs in `gr.HTML` markup or resolve to local path first. |
| **Continuous "live channel"** | Streaming output (chunk concat, NOT HLS) | `gr.Video(streaming=True, autoplay=True)` fed by a generator yielding `.mp4`/h.264 `.ts`; `gr.Audio(streaming=True, autoplay=True)` yields `.mp3`/`.wav`/bytes. Chunks **consistent length, >1 s** (~2 s proven). `demo.queue()` **required**. Sub-second → **FastRTC/gradio-webrtc**. |
| **Queuing / concurrency** | Per-listener queue + pooled scarce resources | `demo.queue(default_concurrency_limit=N, max_size=<finite>, status_update_rate='auto', api_open=False)`; per-listener `concurrency_limit=`/`concurrency_id='gpu_queue'`; `batch=True, max_batch_size=4` for the VLM. |
| **Per-user state** | `gr.State` (session) / global (shared) / `gr.BrowserState` (persisted) | `gr.State(value, time_to_live=, delete_callback=)` for current-scene id + rail order; shared manifest index → module-level global loaded once; returning-viewer → `gr.BrowserState`. Lifecycle: `demo.load`/`demo.unload`, `Blocks(delete_cache=(freq, age))`. |
| **Theming** | Tokens; CSS only for geometry | base `gr.themes.Glass()`/`Ocean()` + `primary_hue`/`neutral_hue`/`radius_size`/`font=GoogleFont` + `.set(slider_color=, loader_color=, block_background_fill=, …)`. **Gradio 6: `theme=` is a `launch()` kwarg.** Residual CSS via `css_paths=`, targeted by `elem_id`/`elem_classes`. |
| **SSE relay refresh** | Keep existing supported pattern | `gr.HTML(js_on_load=...)` + `trigger('relay_scene', data)` + `.relay_scene(fn)`. Matches the no-polling rule. Don't rebuild the player inside it. |

---

## 4. Three candidate architectures

### (A) Incremental — keep `gr.HTML` player, fix hydration + sync (cheap)
**What:** Leave the `gr.HTML` player. (1) Data layer: `direct_media_urls=True` or defer `fs.cat` to
lazy per-media GETs so `_hydrate_scene` returns instantly; ensure `set_static_paths` covers cache.
(2) Replace the 120 ms `setInterval` with **event-driven** correction lifted from the slider
(`onplay`/`onpause`/`ontimeupdate` + >0.2 s threshold), keeping video-or-audio master as authoritative.
**Pros:** Smallest diff; no toolchain; both levers already exist; lowest risk; kills cold-start +
most desync. **Cons:** Still hand-rolling inside `gr.HTML` — exactly what the owner wants to leave;
caption/progress/stall JS remain ours; XSS surface persists; no native captions/controls/theming.
**Risk:** Low tech, low schedule, medium "didn't fix the architecture" debt.

### (B) Native-first — `gr.Video` + `gr.Gallery` + `gr.State` + streaming + `set_static_paths` *(recommended)*
**What:** Delete the bespoke player. Player = `gr.Video(value=url, autoplay, loop, subtitles=<vtt>,
playback_position)`. Rail = `gr.Gallery` (video items) `.select()` → `gr.State.current_index` →
`gr.update()` player. Manifest parsed **once** into module global + per-session `gr.State` for
position. Advance via `.end()`/`.then()`. Media by URL (`direct_media_urls`/`set_static_paths`,
lazy + range). Controls = real `gr.Button(icon=) + gr.update`. Chrome = theme tokens. Optional
continuous channel = `gr.Video(streaming=True)` + ~2 s h.264 chunks + `demo.queue()`. Keep
`gr.HTML(js_on_load=...)` **only** for the SSE bridge. Concurrency: `default_concurrency_limit>1`
for UI, `concurrency_id='gpu_queue'` + `batch=True` for VLM/TTS.
**Pros:** Structurally eliminates desync / wrong-frame / wrong-icon / caption+progress JS — browser
owns playback; captions ride native `<track>`. Cold-start fixed at data layer. Coherent themed
chrome, dark-mode-correct. Pure Python, no JS build. Best effort/payoff.
**Cons / hard constraints:**
- **Autoplay-with-sound is browser-blocked** without a user gesture → need a "tap to start" overlay
  or muted-autoplay-then-unmute. Biggest UX caveat.
- **Two-clock problem returns if audio is a separate track.** A muted looping b-roll slaved to a
  *longer* separate narration is the one thing native `gr.Video` cannot do (`loop` loops the whole
  clip; can't loop b-roll to an audio length). **Mitigation: mux audio into the mp4** so one element
  plays both — this is what makes native work. Genuine decoupled b-roll+narration → the real
  justification for route C.
- Native streaming is **forward-only** (no scrub-back) → use plain `gr.Video(value=url)` for the
  replayable rail, reserve `streaming=True` for the live channel only.
- MP4s must be **faststart / moov-atom-at-front** + h.264 for instant range seek.
**Risk:** Medium-low (autoplay gesture + mux are the two things to validate empirically on Gradio 6).
**Efficiency:** Strongest — no per-frame JS; lazy range media; one shared index; bounded cache;
`batch=True` beats high concurrency on ZeroGPU/CPU-basic; finite `max_size` fails fast.

### (C) Real custom component — Svelte `VideoScene` (highest ceiling)
**What:** `gradio cc create VideoScene --template SimpleImage`, copy pngwn/gradio-imageslider:
backend `class VideoScene(Component)` + `data_model = SceneData(GradioRootModel)` of `FileData`;
`preprocess`/`postprocess` wrap as `FileData(url=...)`; `EVENTS=[Events.play, pause, end, change,
upload]`; render in `Index.svelte`. Build `gradio cc build` (.whl), install on Space via requirements.
**Pros:** Only path that expresses a bespoke 9:16 cinematic player with decoupled b-roll loop +
narration + custom scrubber/overlay as a first-class, typed, reusable, themeable component — no
`setInterval`, no XSS templates, native events, `FileData.url` lazy delivery. Version-pinnable.
**Cons:** Heaviest — Node 20+/npm, Svelte build, `gradio cc build/dev`; built `.whl` adds deploy
surface on HF; Svelte/`dispatch` internals to learn. Overkill unless a reusable widget is a goal.
**Risk:** Highest schedule/complexity; low *architectural* risk (sanctioned pattern). Justified only
if B's mux/autoplay constraints can't satisfy the cinematic UX.

**Recommendation:** Adopt **(B) Native-first**, executing the **(A) data-layer fixes first** (they're
a prerequisite for B and de-risk cold-start immediately). Hold **(C)** in reserve, triggered only if
the muxed-audio constraint can't satisfy a decoupled-b-roll cinematic requirement.

---

## 5. Open questions every proposal must resolve

1. **Audio: muxed or decoupled?** The fork in the road. Mux narration into each scene's mp4 → B is
   clean. Require muted looping b-roll under a longer separate narration → native can't; B(event) or
   C. **Decide first.**
2. **Autoplay UX:** Does the live channel start audio on load? If yes, design a one-time
   user-gesture "tap to start" (or muted-autoplay-then-unmute). Validate on the Space.
3. **Rail = replay vs live:** Confirm gallery replays finished scenes (→ plain `gr.Video(value=url)`,
   arbitrary seek); only the channel is live (→ `streaming=True`, forward-only). Don't stream the rail.
4. **Captions data shape:** Need `.vtt`/`.srt`/`list[dict]` per scene. If we only have text+timings
   JSON, build a converter. Mid-stream subtitle updates on a *streaming* video are undocumented.
5. **Public resolve-URL / file-route accessibility:** `direct_media_urls` needs web-resolvable bucket
   objects; private buckets → anonymous 401/403. `/gradio_api/file=` is behind `login_check` → can
   401 on auth-gated Spaces/embeds. **Validate against the actual public Space (under `macayaven/*`).**
6. **MP4 encoding discipline:** Are generated mp4s faststart (moov at front) + h.264? Non-faststart
   stalls on seek even with 206; non-h.264 won't stream. Verify the encode side.
7. **Concurrency sizing empirically:** A never-ending streaming generator holds one worker per
   viewer. For multi-viewer live, decide bounded chunked streams vs one infinite generator; size
   `concurrency_limit`. Measure on deployed Gradio 6 (#6866, #10453 report inconsistencies).
8. **Gradio 6 API/version parity:** Confirm the Space's pin has `gr.Video.playback_position`,
   `gr.Video.buttons=`, interactive `gr.HTML` (`js_on_load`/`trigger`/`watch`), and no removed v6
   params. Interactive `gr.HTML` is new — older pins won't have it.
9. **Non-deepcopyable per-session objects:** PyAV containers/locks/handles can't live in `gr.State`
   (deepcopy) → module-level `dict` keyed by `request.session_hash` + `demo.unload` teardown.
10. **Theme base + full surface audit:** Switching base restyles the *whole* app (rail, dropzone,
    buttons). Pick base, audit all three surfaces in light + dark; discover exact CSS-var token names
    via rendered-DOM inspection.

**Source files to touch (absolute):**
- `src/small_cuts/hf_relay.py` — `media_url`/`direct_media_urls` (218-237), `_hydrate_scene`
  (248-261), `_hf_resolve_url` (239-246), `_prune_cache` (296).
- `src/small_cuts/viewer.py` — `gr.set_static_paths` (1469, 2035), `/gradio_api/file=` URL building
  (1484, 1516), and the `PLAYBACK_SYNC_JS` / `gr.HTML` player block to be replaced.

*(Full per-source findings — queuing, streaming, file-access, themes, state, custom-buttons,
llms.txt — are in the workflow transcript `w5rdbqguu`.)*
