# Player Redesign Proposal — opencode (GLM), 2026-06-17

## 1. Position

**B′ — Native-first via generation-side mux (a deliberate variant of the brief's B).** The hand-rolled player exists only because we ship a *separate* muted b-roll `<video>` slaved to a *separate* `<audio>` clock (`scVideoTargetTime` = `audio.currentTime % video.duration`, viewer.py:1739–1742). Kill the separation and the player vanishes: one muxed mp4 → one native `gr.Video` → the browser is the only clock. I **dissent from the brief** on one point: its "mux or decoupled — decide first" framing hides that *decoupled-native is incoherent* — two media elements always reintroduce a sync clock, which is the exact thing we're removing. So the real fork is binary: **mux → clean native (B′)**, or **insist on decoupled b-roll → you must build C**. Incremental (A) is "more of the thing the owner wants to stop doing" and I reject it.

## 2. Target architecture

**One asset, one element, one clock.** At generation time, bake the narration into the b-roll: loop/trim the clip to the narration duration, attach the TTS as AAC, write h.264 + **faststart (moov-at-front)**.

- **Player = native `gr.Video`**: `gr.Video(value=served_muxed_url, autoplay=False, loop=False, show_download_button=False, subtitles=<captions>, height=, width=, elem_classes="sc-stage-video")`. Replaces the `gr.HTML(render_stage_html(...))` stage block (viewer.py:2099) and the `<video muted loop>` it emits (viewer.py:839–842). The native element owns buffering, seeking, stall-pauses-everything (no desync possible), and play/pause icon state (no wrong-icon bug).
- **Captions ride native `<track>`**: `subtitles=` accepts a `list[dict]` (`{start,end,text}`) or `.vtt`. Build it from the existing `_subtitle_chunks` (viewer.py:802) by distributing chunks evenly across `audio_duration` — or, better, from real per-word timings if the TTS path exposes them. **Deletes every line of caption-driving JS.**
- **Transport**: rewind/forward stay clip-to-clip via real `.click()` handlers mutating `scenes_state` (viewer.py:2068) → `gr.update(value=next_muxed_url, subtitles=next_vtt)`. Play/pause = native. Volume = native. The `.sc-icbtn` mask buttons (viewer.py:2114–2132) collapse to `gr.Video(buttons=[…])` or a thin skinned overlay.
- **Rail = `gr.Gallery`** (viewer.py:2204), unchanged; `.select()` → `SelectData` → set `pinned_state` → load scene. Plain seekable `gr.Video(value=url)` for replays — **no `streaming=True`** (see §5).
- **Media serving**: keep `media_url`/`direct_media_urls` (hf_relay.py:215) and `gr.set_static_paths([SEED_DIR, GENERATED_AUDIO_DIR, …])` (viewer.py:1469, 2035). **Critical Gradio-6 gotcha:** never put a *remote* URL as `gr.Video(value=…)` — it triggers a server-side download/transcode (gradio #3940/#10726). The muxed asset is served via `/gradio_api/file=` or static path, never a raw HF resolve URL in the value.
- **State**: `gr.State` for scenes/pinned/liked/reported (unchanged); manifest parsed once into a module global, per-session index in `gr.State`. The push/SSE relay bridge (viewer.py:2222) is **untouched** — liveness is an SSE signal, not media streaming.
- **Relay refresh**: stays push/SSE via `gr.HTML(js_on_load=…)` (no `gr.Timer`). Unchanged.

## 3. How it kills each of the 5 symptoms (1:1)

| # | Symptom | Cause in current code | How B′ kills it |
|---|---|---|---|
| 1 | Slow video startup | `preload="auto"` on separate clip; hydration; moov-at-back mp4s | One faststart muxed mp4 + HTTP **206 range** via the file route → instant first frame |
| 2 | A/V/caption desync on stall | Hand-coded `waiting`/`playing` re-pauses audio (viewer.py:1770–1777) races the 120 ms loop | Native element: a buffer stall pauses **everything** atomically. No second clock to drift |
| 3 | Wrong frame on pause/resume | `video.currentTime = audio.currentTime % video.duration` snap (viewer.py:1746, 1800) | Native pause/resume holds the exact frame; no modulo resnap |
| 4 | Wrong play icon (video-only) | `hasAudio` check in the 120 ms loop (viewer.py:1848–1853) | Native control state; `gr.update` icon from Python if skinned — single source of truth |
| 5 | General jank / maintenance | 120 ms `setInterval` + 4 `MutationObserver`s + bespoke CSS masks | No interval, no caption/progress JS, native controls; ~60% of the JS blob deleted |

## 4. Migration plan (against real files; what's DELETED)

`PLAYBACK_SYNC_JS` (viewer.py:1572–1972) is **three concerns tangled together**. The migration cleanly splits them:

- **DELETED entirely** — the `__scClock` 120 ms `setInterval` (1824–1867), the `togglePlayback` pointerdown/click gesture binding (1734–1822), the video-buffer stall helpers `scPauseVoiceForVideoBuffer`/`scResumeVoiceAfterVideoBuffer`/`scWireVideoBufferEvents` (1750–1777), and `scVideoTargetTime`/`scSyncVideoToAudio` (1739–1749). Also delete `_audio_html`/`_audio_url` (1508–1529) and the `audio` gr.HTML host (2134). `render_stage_html`'s `<video>`/`<img>` body (834–846) is replaced by the native component.
- **SURVIVES — renamed `UPLOAD_SANDBOX_JS`** — the upload form-field fixing + submit-lock + clapperboard generation loader (1631–1732, 1869–1964). This is upload UX, not playback. It must be **rebound**: it keys off `.sc-stage-shell video`; under B′ the stage is a `gr.Video` with a different DOM testid, so the stage `MutationObserver` (1953–1964) and `scArmReveal`/`scRevealResult` re-target `[data-testid="video"]` inside the stage column.
- **SURVIVES — renamed `CHROME_JS`** — favicon injection (1577–1600), HF-header safe-zone toggle (1602–1612), header→back-to-live forwarding (1614–1621). Volume delegation (1623–1629) becomes native.

Concrete steps:
1. **`src/small_cuts/frames.py` (or new `mux.py`)**: add `mux_scene(clip, audio, out) -> Path` — PyAV (already a dep): loop clip frames to `audio_duration`, mux AAC, write `+faststart`, h.264 yuv420p, moov-at-front. Called in the **generation** path (upload→Modal, engine `/v1/scenes`), plus a **one-time offline backfill** for the existing relay/seed library (5 seed cuts in `demo_seed.py`) so every scene ships a `media.muxed_url`.
2. **`src/small_cuts/hf_relay.py`**: `_hydrate_scene` (248) gains `muxed_url`; `media_url` (215) serves it (direct → HF resolve URL; cached → `/gradio_api/file=`). `MEDIA_KEYS` gains `muxed_url`.
3. **`docs/contracts/`**: scene schema v1.1.0 → v1.2.0 adds `media.muxed_url` (optional, falls back to clip+audio for legacy). Lockstep bump + golden samples + all consumers, label `contract-change`.
4. **`src/small_cuts/viewer.py`**: replace stage `gr.HTML` with `gr.Video`; wire rewind/forward/like/flag as real `.click()` handlers; split the JS blob as above. Build `captions_for(scene)` → `list[dict]`.
5. Re-skin the 9:16 geometry: keep the `.sc-stage-shell` aspect-ratio CSS, point it at `gr.Video` via `elem_classes`, read theme tokens (`var(--slider-color)` etc.) so the native scrubber matches.

## 5. Resource efficiency

- **Bytes/requests**: one muxed mp4 per scene instead of clip+audio (≈half the media requests). Posters (`frame_url`/`card_url`) still hydrate only when `direct_media_urls=False` (hf_relay.py:268) — unchanged.
- **Main thread**: remove one 120 ms `setInterval` and ~4 playback-tied `MutationObserver`s. Native `<track>` captions = zero JS per frame.
- **CPU-basic friendliness**: mux happens **off-Space** (Modal/engine/offline backfill). The viewer only resolves URLs — no `fs.cat` per media key in the hot path, no torch, no TTS.
- **Many concurrent viewers**: I **reject `gr.Video(streaming=True)` for both rail and "channel."** A streaming generator pins one worker per viewer — fatal on CPU-basic, and the product isn't actually a continuous media stream (it boots *paused*; "liveness" is the SSE relay). Pure URL serving scales to HF's CDN, not the Space's process. This is the biggest efficiency lever and an explicit dissent from the brief's streaming suggestion.

## 6. Risk + unknowns + cheapest de-risk

**Risks**: (a) mux pipeline scope-creep into generation (see §8); (b) raw-remote-URL-in-`gr.Video(value=)` download trap (#3940) — must serve via static path/file route; (c) native controls vs. the "cinematic" pill — portfolio polish meets native chrome; (d) Gradio-6 version pin must have `gr.Video(buttons=)` + interactive `gr.HTML` (`js_on_load`/`trigger`) — verify; (e) non-faststart mp4s still stall on seek even with 206 — enforce at the muxer.

**Cheapest de-risk experiment (~30 min, zero Space risk)**: take **one** `demo_seed` scene (mp4 + Kokoro mp3). Locally `ffmpeg -stream_loop -1 -i clip.mp4 -i voice.mp3 -t <audio_dur> -c:v libx264 -pix_fmt yuv420p -c:a aac -movflags +faststart muxed.mp4`. Build a 20-line `gr.Blocks` with `gr.Video(value=muxed_path, subtitles=[{…}])` + `gr.set_static_paths([muxed_dir])`, run on the mac-studio tailnet (`GRADIO_SERVER_NAME=0.0.0.0 … python app.py`, http://mac-studio:7861). Verify: instant first frame (206 range), scrub seeks, captions show, pause/resume holds frame, play icon correct. Pass → whole B′ thesis de-risked before touching `viewer.py`.

## 7. Test / verification plan

- **Local gate (mirrors CI)**: `uv run ruff check . && uv run ruff format --check . && uv run pytest`.
- **New unit tests**: `captions_for(scene)` (golden-sample chunk→timing), `mux_scene` (PyAV: asserts `+faststart`, AAC stream, duration ≈ audio), contract test for `media.muxed_url`.
- **Local**: all four modes (relay/hybrid/engine/upload) boot, scenes carry or fall back from `muxed_url`.
- **Live-Space smoke** — `macayaven/*` only, one explicit Carlos approval: relay load → first-frame LCP, scrub, captions, pause/resume, rewind/forward clip-to-clip, gallery `.select()`, SSE relay push still single-refreshes, no `503`/restart loop (HF account-safety stop rule).

## 8. Confidence 0.72 — strongest dissent against my own position

My clean answer **depends on a pipeline change the owner didn't scope**. B′ moves work from the viewer into generation (`mux.py` + relay/seed backfill + Modal/engine integration). If the owner says "viewer-only, don't touch generation," B′ is blocked — and then the honest alternatives collapse to:

- The brief's *decoupled-B* — which I argue is **incoherent**: two media elements (`gr.Video` + `gr.Audio`) always reintroduce a sync clock, so you'd re-derive a fragile version of the very `PLAYBACK_SYNC_JS` you deleted. That's not B; it's A in a costume.
- **C (real Svelte component from the pngwn/gradio-imageslider template, `FileData.url`-backed)** — the only architecturally honest way to keep decoupled b-roll-loop-under-narration as a first-class, typed, themeable widget.

So: **if pipeline is in scope → B′ (0.72). If viewer-only → C, and A should be rejected outright.** The worst outcome is a half-B that keeps two elements and re-invents the clock — that's the trap the owner already smells.

**Open questions resolved**: (1) mux — decisive; (2) boots paused + tap-to-start gesture for sound; (3) rail = seekable `gr.Video(value=url)`, no streaming; (4) captions = `list[dict]`/`.vtt` from `_subtitle_chunks`; (5) serve via static path/file route, never raw remote in value; (6) faststart+h.264 enforced at mux; (7) no streaming → no per-viewer worker, CPU-basic-safe; (8) verify pin has `gr.Video(buttons=)` + interactive `gr.HTML`; (9) muxed assets are URLs (deepcopy-safe); engine PyAV handles stay module-level keyed by `session_hash`; (10) switch theme base, audit stage+rail+dropzone in light/dark.
