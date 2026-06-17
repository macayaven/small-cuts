# Verified Consensus & Converged Plan — Player Redesign (2026-06-17)

> Built from 5 independent proposals (`proposals/{opus,codex,agent,opencode,agy}.md`) + a 3-lens
> adversarial verification (workflow `we8njuvsp`). Verdict: **GO-WITH-CHANGES.** This is the
> design-of-record; it supersedes the over-reaching "mux everything" framing in the proposals.

## The decision in one paragraph
Stop synchronizing two media clocks in JavaScript. Keep the media **decoupled** (the pipeline already
is), let the **browser own each element's clock**, and **delete the 120 ms `setInterval`** sync core.
The cinematic chrome (gold pill, icon buttons, source badge, progress fill) is CSS+markup decoupled
from the clock — **keep all of it**, rewired to a handful of **event-driven** DOM listeners. **No mux
by default, no contract change, no Svelte component** for this pass. This is mostly *deletion +
rewiring* of `viewer.py`'s player JS.

## What the panel agreed on (4–5 of 5)
- Kill the 120 ms `PLAYBACK_SYNC_JS` core (`viewer.py:1824`): the drift corrector
  (`scSyncVideoToAudio`/`scVideoTargetTime`, the `audio.currentTime % video.duration` snap), the
  stall pause/resume hack, the caption-visibility poll, the play-icon-from-`audio.paused` guess.
- Browser is the clock. Data layer stays as-is (`direct_media_urls` + `set_static_paths`); no
  manifest-time synchronous hydration. Rail = `gr.Gallery` posters + `.select()`. Relay refresh =
  the existing push-only SSE bridge. **No `gr.Timer`. No `gr.Video(streaming=True)` for replay** (a
  streaming generator pins one worker per viewer — fatal on CPU-basic; the channel boots paused).

## What verification CHANGED (with evidence)
1. **No mux by default.** Measured: `-shortest` truncates narration (rayuela → 10.97 s, wrong);
   loop-extending balloons storage **2.1×** (9.75 MB vs 4.56 MB; +519 MB at 100 scenes); audio is
   **MP3** so every mux re-encodes anyway; upload "try-it" has no narration to mux. The data model is
   **already decoupled** (`MEDIA_KEYS`, `hf_relay.py:34`). → Keep decoupled; mux is **not** a
   simplification.
2. **`gr.Video(value=<remote URL>)` is FORBIDDEN, not just unsafe** (gradio #3940 →
   `FileNotFoundError` via `shutil.copy2` on the URL; #10726 → `move_files_to_cache` downloads through
   the worker). Never pass a remote URL to `gr.Video.value`.
3. **Delivery vehicle = `gr.HTML` `<video preload="metadata">` (NO `controls`)**, `src` via the
   Space's own range-capable `/gradio_api/file=` route (`route_utils.file_fetch` → `RangedFileResponse`
   = HTTP 206). Direct HF-bucket `src` is an *optimization* gated on the §Experiment Range/CORS check
   (Xet-backed objects redirect to `cas-bridge.xethub.hf.co`; browser CORS preflight for Range can
   fail). `<video controls>`/bare `gr.Video` chrome fails the portfolio bar.
4. **Captions:** native `<track>` renders cues only on `<video>`, never bare `<audio>` (MDN). Our
   looping short b-roll can't carry the longer narration track → in the decoupled design, captions are
   a **single event-driven painter off the audio `timeupdate`** (reads a cue list derived from
   `_subtitle_chunks()` + `duration`), replacing the 120 ms poll. Truly-native `<track>` rendering is
   a **muxed-path-only** upgrade (deferred).
5. **Chrome preservation is explicit & non-negotiable** (so a literal implementer can't ship bare
   `gr.Video` and "pass"): KEEP the gold pill (`.sc-controls`), masked icon buttons (`.sc-icbtn`), the
   source badge overlay (a design invariant), the gold progress fill.
6. **Public Space invariant:** no Gradio `auth=` / no HF gating for anonymous viewers, else
   `login_check` 401s the `<video>` file requests.
7. **Repoint the volume slider** from the deleted hidden `<audio id="sc-voice">` to the surviving
   audio/video element.
8. **Rewind/forward stay clip-to-clip** (Gallery index re-render), NOT within-clip `currentTime` seek.

## Target player (decoupled, event-driven)
- Stage = `gr.HTML` rendering `<video loop muted playsinline preload="metadata" poster=frame>` (the
  decorative b-roll, free-running) + a served `<audio preload="auto">` (narration = the authoritative
  clock) + the caption/progress DOM, inside the existing `.sc-stage-shell` overlay host.
- **Coupling = a few listeners, no interval:** play tap → `audio.play()`+`video.play()`; pause → both
  pause; `audio` `play`/`pause` → toggle `.sc-ico-play/pause`; `audio` `timeupdate` → set visible
  caption cue + gold progress width; (optional) `audio`/`video` `waiting`/`playing` for soft stall
  coupling. The b-roll **free-runs** — we no longer force its `currentTime`, so the frame-jump bug is
  gone by construction.
- Video-only scenes: the `<video>` is the authoritative element (no audio `src`); play-icon reads its
  `play`/`pause` events → bug #4 gone.

## How it kills the 5 symptoms
1. **Startup latency** — direct/served URLs with HTTP 206 range; `preload="metadata"`; shelf loads
   posters only (unchanged). 2. **A/V/caption desync on stall** — captions+progress track the audio
   clock only; the b-roll is decorative and free-runs, so its stalls are cosmetic. 3. **Frame jump on
   resume** — the modulo `currentTime` snap is deleted; native resume holds position. 4. **Wrong play
   icon** — driven by `play`/`pause` events on the authoritative element. 5. **Jank** — one `setInterval`
   doing 5 jobs → a handful of native event listeners.

## Migration plan (against the real files)
- **Phase 0 — de-risk (no code):** Range probe (see below) + confirm the public Space has no auth.
- **Phase 1 — delete the sync core** in `PLAYBACK_SYNC_JS` (`viewer.py:~1572–1972`): the `setInterval`,
  drift corrector, stall hack, caption poll, icon guess. KEEP favicon, header back-to-live, HF-header
  safe-zone, the trusted-gesture play handler (`viewer.py:~1812`).
- **Phase 2 — event-driven chrome:** rewire icon/progress/captions/volume to listeners; generate the
  caption cue list (`_subtitle_chunks` + `duration`) → a small helper; render it in the stage HTML.
- **Phase 3 — free-run the b-roll:** stop mirroring `video.currentTime` to audio; start/pause together
  only. Fix video-only authoritative element.
- **Phase 4 (optional, narrow):** still-only Ken-Burns scenes → one mp4 upstream (engine/Modal only),
  `-movflags +faststart`, **additive** `muxed_url` key (never collapse `MEDIA_KEYS`).
- **Phase 5 (optional):** migrate brand accents to theme tokens where it removes CSS.
- **Tier-2 (deferred, gated on the product question):** Svelte `VideoScene` component; native `<track>`
  via per-scene mux.

**Net:** delete ~250–350 lines of JS; **zero** contract change; **zero** new toolchain. Reversible.

## Test / verification
- Local gate (mirror CI): `uv run ruff check . && uv run ruff format --check . && uv run pytest`.
- New unit tests: caption-cue generation (chunk→timing), `render_stage_html` markup golden, a
  regression that no media `fs.cat` runs on the Space profile.
- Local 4-mode boot (relay/hybrid/engine/upload). Live-Space smoke under `macayaven/*` only (one
  explicit approval): LCP, scrub, captions, pause/resume holds frame, rewind/forward clip-to-clip,
  gallery select, SSE single-refresh, no 503 loop.

## The ONE experiment before code (cheap, read-only)
```
curl -sI -H 'Range: bytes=0-1' '<HF bucket resolve URL for one real clip>'
curl -sI -H 'Range: bytes=0-1' '<Space /gradio_api/file= URL for the same object>'
```
Assert **HTTP/206 + Accept-Ranges + Content-Range** on both. A `200` (or Xet CORS-preflight failure on
the bucket URL) means the `<video src>` must route through the Space's range-capable file endpoint
rather than the direct bucket URL. Resolves the only remaining empirical unknown.

## The one product question that could expand scope
**Is "short b-roll looping on its own cadence under a longer narration" a designed effect to keep?**
Yes (it's the current behavior) — and it's achievable **decoupled, without Svelte**. Svelte/mux are
only warranted if you later want a typed, reusable, pixel-bespoke component or truly-native captions;
both are explicitly **deferred** Tier-2, not submission work.

## Dissent on record
**agy** argued for building the Svelte component *now* with decoupled media. Verification agreed on
*decoupled* but found agy's "captions via `<track>` in `<audio>`" doesn't render natively (re-incurs a
painter), and that the deadline/portfolio bar is cleared by plain `gr.HTML` + the existing CSS pill +
listeners at far lower risk. Svelte stays the Tier-2 fast-follow.
