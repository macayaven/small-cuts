# Player Redesign — Shared Context (2026-06-17)

> One briefing, read by all five proposal authors (Opus/orchestrator, codex, agy, opencode, agent).
> Goal of the redesign: a **smooth, scalable, resource-efficient** video player for the Small Cuts
> Gradio viewer that is **portfolio-grade**. The hackathon deadline (2026-06-15) has passed; we are
> now in **polish-for-portfolio** mode. The owner's framing: *"the big issue is pretending to build
> our own video player ourselves."* Question the layer, not just the bugs.

## 1. What Small Cuts is (player's job)
A Gradio v6 app (HF Spaces; CPU-basic in relay mode, ZeroGPU/Modal for narration) that plays
AI-narrated **vertical 9:16** "scenes" as a live-streaming-style channel. A scene = a short muted
video **clip** (or a still poster frame) + a **voice-over** (TTS WAV/MP3) + **narration captions** +
title. The page shows: a 9:16 **stage** (the active scene), a **progress bar + control pill**
(play/pause, rewind/forward = clip-to-clip, like, flag, volume), and a **Library** rail
(`gr.Gallery`) of past scenes. Header doubles as "back to live."

## 2. The current player architecture (as built in `src/small_cuts/viewer.py`, 2880 lines)
**It is a fully hand-rolled player inside `gr.HTML` blocks**, NOT a native component:

- **Master clock = a hidden custom `<audio id="sc-voice">`** injected via `gr.HTML`
  (`_audio_html`, viewer.py:1519). Re-rendered on each scene change to swap `src`.
  (gr.Audio was abandoned because it plays via wavesurfer, leaving its own `<audio>` empty/unreadable
  — so the "deferred Tier-2 swap" in the module CLAUDE.md is **already done**; that note is stale.)
- **The video** is a `<video muted loop playsinline preload="auto" fetchpriority="high">` inside the
  stage `gr.HTML` (`render_stage_html`, viewer.py:821). It is **slaved** to the audio clock.
- **Captions + progress bar** are DOM in the stage HTML, advanced off `audio.currentTime`.
- **Controls** are CSS-mask-icon `gr.Button`s (`.sc-icbtn`, viewer.py:2108–2134) with **no Python
  handler for play/pause** — a delegated DOM click in JS drives them.
- **`PLAYBACK_SYNC_JS`** (viewer.py:1572–1972, injected via `js_on_load`): a **120 ms `setInterval`
  loop** that (a) forces `video.currentTime = audio.currentTime % video.duration` with a 0.3s drift
  guard, (b) toggles video play/pause to match audio, (c) toggles the play-button icon, (d) shows
  the right caption line + sets progress width, (e) hand-codes **stall sync** via capturing
  `waiting`/`playing` media events, (f) injects the favicon, (g) wires header→back-to-live.
- **Library** = `gr.Gallery` (`shelf`, viewer.py:2204). **State** = `gr.State` for scenes / pinned /
  liked / reported / upload panel (viewer.py:2068–2076). **Relay refresh** = push-only: a publish
  hits `/small-cuts/hooks/relay-scene`, browsers refresh once from an SSE event
  (`/small-cuts/events`) via a `gr.HTML(js_on_load=...)` bridge. **No `gr.Timer` relay polling.**

## 3. Media serving (`src/small_cuts/hf_relay.py`, 445 lines) — corrected vs. the stale report
`docs/player_control_report.md` describes "240 synchronous downloads on cold start." That is **mostly
a prior state.** Current behavior:
- On the **Space** (`SPACE_ID` + relay bucket set), `_default_direct_media_urls()` → **True**, so
  `media_url()` returns **direct** `https://huggingface.co/buckets/<id>/resolve/<path>` URLs **with no
  server-side download** (hf_relay.py:215–246). The browser fetches media straight from HF.
- `list_scenes()` only hydrates `frame_url`/`card_url` (shelf thumbs) when NOT direct
  (`_list_media_keys()`, hf_relay.py:268). Manifest is cached 5s.
- So residual startup cost is **video LCP / first-frame latency**, not a 240-file stampede. (Branch of
  record: `codex/video-lcp-streaming`; recent commit "Optimize video streaming startup".)

## 4. Symptoms to solve (portfolio blockers)
1. **Video startup latency** — slow first frame / LCP on the stage video.
2. **A/V/caption desync on stall** — when the video buffer underruns, audio + captions keep moving
   (the report's Issue 2). Hand-coded `waiting`/`playing` sync is fragile.
3. **Frame jump on pause/resume** — repeated toggles snap the video to the wrong frame (Issue 3).
4. **Wrong play icon for video-only scenes** (audio has no `src`) (Issue 4).
5. **General jank + maintenance cost** — a 120ms global `setInterval` driving everything; a giant
   bespoke JS/CSS layer that is hard to reason about and "feels homemade."

## 5. Hard invariants / constraints (do not break)
- **9:16 stage ratio** is a hard invariant; **single viewport, no main scrollbar**; mobile
  (`max-width:860px`) collapses to one column + horizontal gallery rail.
- **Gradio 6**; `theme=` is a `launch()` kwarg. **SSR is off** on Spaces (custom routes).
- **Relay refresh is push/SSE, never `gr.Timer`-polled.** Do not reintroduce timer polling or
  hidden-button bridges.
- **CPU-basic in relay mode** — the Space must not warm Qwen/Kokoro; narration/TTS run on
  ZeroGPU/Modal workers (`@spaces.GPU`), never the main process.
- **Four build-time modes** (env-selected): pure **relay** (current safe posture), **hybrid
  relay+upload** (Modal), **engine** (`/v1/scenes` polling), **upload** (local try-it). The player
  must work across all four; scenes are dicts with `media.{frame_url,clip_url,audio_url,card_url}`,
  `narration`, `title`, `created_at`, `duration`, `source_icon`.
- **Contracts v1.1.0** in `docs/contracts/` are source of truth for the scene/manifest shape.
- **Anti-divergence:** one home per fact; operational truth lives in CLAUDE.md + docs/, strategy in
  the KB. Keep the player's public surface (modes, scene dict) stable.

## 6. The three candidate directions (each proposal must take a position)
- **(A) Incremental** — keep the `gr.HTML` player; fix hydration + sync + stall + icon (the
  `docs/player_control_report.md` path). Lowest risk, keeps the bespoke clock.
- **(B) Native-first** — replace the bespoke player with **native `gr.Video`** (native controls /
  buffering / seeking) + `gr.Gallery` + `gr.State` + `set_static_paths` + streaming, with minimal
  glue. Removes most custom JS. The likely sweet spot for resource-efficiency + smoothness.
- **(C) Real custom component** — build a proper **Svelte custom component** (like the official
  `gradio_video_slider`) for the cinematic 9:16 player + synced captions. Highest polish, highest
  build cost, real frontend toolchain.

## 7. Required proposal structure (every author follows this)
1. **Position** — A / B / C / explicit hybrid, in one sentence + why.
2. **Target architecture** — components, data flow, where the clock lives, how A/V/captions stay in
   sync, how media is served/streamed, how state is managed. Cite exact Gradio APIs.
3. **How it kills each of the 5 symptoms** (map 1:1).
4. **Migration plan** — concrete steps against the real files; what is deleted (esp. how much of
   `PLAYBACK_SYNC_JS` survives).
5. **Resource efficiency** — bytes, requests, main-thread cost, CPU-basic friendliness, many
   concurrent viewers.
6. **Risk + unknowns** — what could go wrong on HF Spaces (SSR off, file routes, ZeroGPU), and the
   cheapest experiment to de-risk it.
7. **Test/verification plan** — incl. the local gate (`ruff` + `pytest`) and a live-Space smoke.
8. **Confidence (0–1) + strongest dissent** — where you might be wrong; the best argument against
   your own position.

## 8. Files to read
- `src/small_cuts/viewer.py` (the player) · `src/small_cuts/hf_relay.py` (media serving) ·
  `src/small_cuts/CLAUDE.md` (module notes; note the stale "deferred swap") · `app.py` (entrypoint) ·
  `docs/player_control_report.md` (incremental-fix baseline) · `docs/contracts/` (scene shape).
- Research brief: `docs/reviews/2026-06-17-player-redesign/01-research-brief.md`.
