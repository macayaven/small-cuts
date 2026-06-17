# Proposal — Opus (orchestrator)

## 1. Position
**B (native-first), realized by muxing each scene into one self-contained `.mp4` upstream and
playing it with a single native `<video controls>` + `<track>` element.** The player jank is an
architectural smell: we are synchronizing two media clocks in JavaScript. Collapse them to **one
stream at generation time** (where ffmpeg already lives) and let the browser's native media stack own
playback. This answers the brief's open question #1 decisively: **mux, don't decouple.**

I reject pure (C): a Svelte component is still "building our own player," and for a *replay* channel
of finished cuts it buys nothing over a native `<video>`. I reject staying in (A): event-driven sync
is better than a 120 ms loop but still leaves us hand-driving captions and two clocks.

## 2. Target architecture

**Upstream (the worker that already does narration/TTS — engine or Modal, never the CPU-basic Space):**
- A new `compose_scene()` step runs **ffmpeg** once per scene to produce **`scene.mp4`**: the b-roll
  looped/padded to the narration's duration (`-stream_loop -1 -t <audio_dur>`), with the narration
  WAV/MP3 as the **audio track**, encoded **h.264 + faststart** (`-movflags +faststart`). Video-only
  scenes → the clip as-is, no audio track. Still-only scenes → a 6–8 s Ken-Burns over the poster.
- A `narration_to_vtt()` helper turns the existing caption chunks (`_subtitle_chunks`, viewer.py:802)
  + `audio_dur` into a sidecar **`scene.vtt`** (evenly-timed cues; later, real TTS word timings).
- Contract bump **v1.1.0 → v1.2.0**: add `media.scene_url` + `media.subtitle_url`; keep
  `clip_url`/`audio_url`/`frame_url`/`card_url` for back-compat + the rail poster. New golden samples.

**Player (Space side) — the stage is one `gr.HTML` rendering native markup:**
```html
<video id="sc-stage" class="sc-video" controls playsinline preload="metadata"
       poster="{frame_url}" src="{scene_url}">
  <track default kind="subtitles" srclang="en" src="{subtitle_url}">
</video>
```
The browser is the **sole clock**: native buffering, seek, stall recovery, play/pause icon, and
caption sync (native `<track>`) all come free. `src` is the **direct HF resolve URL**
(`direct_media_urls=True`, hf_relay.py:221) so media streams straight from the bucket with **HTTP 206
range requests** — no server-side copy, no transcode. We deliberately use a native `<video>` in
`gr.HTML`, **not** `gr.Video(value=...)`, because passing a remote URL as a component value triggers
Gradio's server-side download/transcode (brief §3 caveat; gradio #3940/#10726).

- **Rail:** `gr.Gallery` of scene posters (viewer.py:2204 stays). `.select()` → `SelectData.index`
  → `gr.State.current_index` → re-render the stage `gr.HTML`. (Already the shape of `_on_local_select`.)
- **Transport at the right layer:** *within-clip* play/pause/seek/volume = **native controls**;
  *across-scene* prev/next = `gr.Button.click` → `gr.State` index → re-render (the existing
  rewind/forward = clip-to-clip semantics, viewer.py:2114/2123); like/flag = `gr.Button` + `gr.update`.
- **State:** the manifest index is a process-global loaded once; per-session **`gr.State`** holds
  `current_scene_id` only (small, deepcopy-safe). No per-frame state.
- **Relay refresh:** the existing push-only SSE bridge (`gr.HTML(js_on_load=...)` →
  `/small-cuts/events`) is **unchanged**. No `gr.Timer`.
- **Chrome:** keep the Off-Brand theme; migrate the gold accents to `.set(slider_color=…,
  block_radius=…)` tokens; retain `VIEWER_CSS` only for the **9:16 frame geometry** + gallery rail.

## 3. How it kills each of the 5 symptoms
1. **Slow video startup** — `preload="metadata"` + faststart mp4 + 206 range streaming from the bucket;
   the first byte is the moov atom, so playback starts on the first range, not a full download.
2. **A/V/caption desync on stall** — *structurally impossible*: there is one stream. If it buffers,
   audio + video + captions stall and resume **together** because they are the same element's timeline.
3. **Frame jump on pause/resume** — there is no `currentTime = audio.currentTime % video.duration`
   reconciliation anymore; the native element resumes exactly where it paused.
4. **Wrong play icon for video-only scenes** — native controls render the correct state from the
   element itself; no `audio.paused`-derived guess.
5. **Jank / "feels homemade"** — the 120 ms `setInterval`, the audio-master clock, the drift
   corrector, the caption-visibility driver, the hand-coded `waiting`/`playing` stall handlers, and
   the progress-fill JS are all **deleted**.

## 4. Migration plan (phased; each phase ships value)
- **Phase 0 — data layer (≈done, verify):** confirm `direct_media_urls` + `set_static_paths`
  (viewer.py:1469, 2035) cover all served dirs; assert no synchronous `_hydrate_scene` loop runs on
  the Space path. Add a regression test that `list_scenes()` issues **zero** `fs.cat` for media on the
  Space profile.
- **Phase 1 — native single `<video>` for combined scenes:** add `compose_scene()` + `narration_to_vtt()`
  to the worker; emit `scene_url`/`subtitle_url`; re-encode the 5 seed cuts (`demo_seed.py`). Swap
  `render_stage_html` (viewer.py:821) to the native `<video>`+`<track>` markup above. Delete the
  audio-master sections of `PLAYBACK_SYNC_JS` (viewer.py:1572–1972) — keep only favicon + header
  back-to-live + HF-header safe-zone. Remove `_audio_html` (viewer.py:1519) and the
  `gr.HTML(boot_audio…)` host (viewer.py:2134).
- **Phase 2 — rail/controls wiring on native state:** rewire prev/next/select/back-to-live to
  re-render the stage `gr.HTML` from `gr.State`; like/flag unchanged. Theme-token the chrome.
- **Phase 3 (optional, gated on visual review):** if native controls aren't cinematic enough, overlay
  a slim custom control bar that calls the native element API (`el.play()/pause()/currentTime`) via
  **event-driven** listeners — *never* a polling loop. This is the only place any new JS returns, and
  only if Phase 2 fails the portfolio bar.

**Net deletion:** ~350–450 lines of JS/CSS/Python (the sync loop, the second audio element, the
caption driver, much of `VIEWER_CSS`).

## 5. Resource efficiency
- **Main thread:** zero per-frame JS; one `<video>` element vs. an interval + two media elements +
  DOM caption thrash.
- **Bytes/requests:** one ranged stream per active scene from the bucket CDN; the rail loads only
  poster thumbnails (already shelf-only hydration). No base64. No re-copy (vs. the file-route copy).
- **CPU-basic Space:** the Space never encodes or warms a model; the ffmpeg mux is one-time on the
  worker that already runs the VLM/TTS under `@spaces.GPU`/Modal.
- **Many viewers:** stateless replay — every browser streams its own scene directly from HF; the
  Space serves only small HTML/JSON over the existing queue (`default_concurrency_limit>1` for the
  cheap UI handlers; the heavy worker stays pooled under one `concurrency_id`).
- **Storage:** +1 combined mp4 per scene (modest; we can drop the standalone `clip_url`/`audio_url`
  from the relay once `scene_url` is canonical).

## 6. Risk + unknowns + cheapest de-risking experiment
- **Biggest assumption:** a native `<video src=<HF resolve URL>>` in `gr.HTML` streams with **206
  range + native captions** from an **anonymous** browser against the real public Space (the
  `/gradio_api/file=` route is behind `login_check`; bucket `resolve` URLs may 401 if private).
- **Cheapest experiment (do first):** on a `macayaven/*` test Space, render one hand-authored
  `<video controls><track></video>` pointing at one pre-muxed `scene.mp4` + `scene.vtt` already in the
  bucket; open it in an incognito browser; confirm (a) seek issues 206, (b) captions show, (c) no
  server transcode in logs. ~30 min, no pipeline work, fully answers the architecture.
- **Other unknowns:** autoplay-with-sound needs a user gesture → the native play button *is* that
  gesture (we do not need channel autoplay for replay); ffmpeg loop-to-duration edge cases for very
  short b-roll; the contract bump must update all consumers in one PR (lockstep, `contract-change`
  label). SSR stays off.

## 7. Test / verification plan
- **Local gate (must mirror CI):** `uv run ruff check . && uv run ruff format --check . && uv run pytest`.
- **New unit tests:** `compose_scene()` (durations/codec via `av`), `narration_to_vtt()` (cue
  timing), `render_stage_html()` native-markup golden, and the Phase-0 "zero media `fs.cat` on Space"
  regression. Update contract golden samples for v1.2.0.
- **Live-Space smoke (under `macayaven/*` only, per safety rules):** the incognito range+caption test
  above, plus rail-select / prev-next / back-to-live and a video-only scene (no caption track).

## 8. Confidence + strongest dissent
**Confidence: 0.8.** The native single-stream player is correct and is the cleanest portfolio story
("I deleted the player and let the browser do its job").

**Strongest dissent against myself:** the win is gated on a **pipeline + contract change** (ffmpeg
mux, `scene_url`, re-encoding seeds, a v1.2.0 lockstep PR) — heavier than the brief's "just wire
`gr.Video`." If the muxed-b-roll cinematic look disappoints (e.g., looping artifacts, or we later
*want* the b-roll to drift freely under the voice), I've spent that scope for a result a cheaper
event-driven decoupled player (A+, no contract change) could have approximated. The 30-minute incognito
experiment in §6 is the hinge: if it passes, mux is clearly worth it; if remote-URL streaming is
blocked, the whole native-`<video>` premise wobbles and C (FileData.url in a real component) becomes
the fallback, not A.
