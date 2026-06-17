# Implementation Brief — Codex — Player Decoupled Redesign

**Branch (already checked out):** `codex/player-decoupled-redesign`.
**Read first (authoritative):** `docs/reviews/2026-06-17-player-redesign/02-consensus.md` — the APPROVED
design-of-record. Also `00-context.md` (current architecture + invariants) and `01-research-brief.md`.

**Approved scope: decoupled, event-driven, delete-don't-build.** Do EXACTLY this; do NOT exceed it.
This is mostly *deletion + rewiring* inside `src/small_cuts/viewer.py`. No new files needed beyond a
small caption helper + tests.

## Goal
Replace the 120 ms `setInterval` master-clock in `PLAYBACK_SYNC_JS` with **browser-native,
event-driven** clocking. Media stays **decoupled** (the muted looping `<video>` b-roll + the served
narration `<audio id="sc-voice">`). The narration audio is the authoritative clock when present; the
b-roll **free-runs** as decoration. **Keep all brand chrome.**

## DO
1. **Delete the sync core** in `PLAYBACK_SYNC_JS` (`viewer.py`, ~1572–1972). Remove:
   - the 120 ms `setInterval` clock (~line 1824);
   - the drift corrector `scSyncVideoToAudio` / `scVideoTargetTime` and the
     `video.currentTime = audio.currentTime % video.duration` snap (~1739);
   - the stall pause/resume modulo hack;
   - the caption-visibility logic driven by the interval;
   - the play-icon state derived from `audio.paused`.
   **KEEP:** favicon injection, header→back-to-live delegation, `scSyncHfHeaderSafeZone`, the
   trusted-gesture `pointerdown`/`click` play handler (~1812, it fixes a real `NotAllowedError`), and
   the volume control. Verify exact line numbers yourself before editing.
2. **Rewire to event-driven listeners (NO `setInterval` anywhere):** let `A` = the narration
   `<audio id="sc-voice">` when it has a `src`, else the stage `<video>` (the "authoritative element").
   - `A.addEventListener('play'|'pause', …)` → toggle `.sc-ico-play` / `.sc-ico-pause` on `.sc-play-btn`.
   - `A.addEventListener('timeupdate', …)` → set the gold progress fill width (`#sc-progress-fill`) and
     reveal the active caption cue.
   - Play tap (existing trusted-gesture handler): if narration audio has `src` → `audio.play()` +
     `video.play()` (or pause both); else toggle the `<video>`.
   - Volume slider: keep it bound to `#sc-voice` (the narration element is retained as the audio
     source — we only delete its role as a *polled* clock).
   - The b-roll `<video loop muted playsinline>` **free-runs**: start on play, pause on pause, but do
     **not** mirror its `currentTime`. Soft stall coupling (`waiting`/`playing`) is OPTIONAL — add only
     if trivial; the b-roll is decorative.
3. **Captions = event-driven cue painter.** Add a small pure helper (e.g. `caption_cues(text, duration)
   -> list[tuple[float, float, str]]`) reusing `_subtitle_chunks()` (~802) to assign each chunk an even
   time window across `duration`. Render the cues into the stage HTML (`render_stage_html`, ~821) as
   data the `timeupdate` listener reads (e.g. a `<script type="application/json">` cue list or
   `data-*` attributes), and show the cue whose window contains `A.currentTime`. This REPLACES the
   CSS-stepped hidden-span approach with a time-accurate one. **Do NOT add a native `<track>`** (it does
   not render on `<audio>`, and we are not muxing).
4. **Video-only scenes** (no audio `src`): the `<video>` is authoritative — play/pause icon + progress
   read from it; captions may be absent. This fixes the wrong-play-icon bug.
5. **Keep ALL chrome unchanged:** the `.sc-controls` gold pill, `.sc-icbtn` masked icon buttons
   (rewind/play/forward/like/flag), the source badge overlay, the gold progress fill (`#D4AF37`). Keep
   the `gr.Gallery` rail and **rewind/forward = clip-to-clip** (Gallery index re-render via `gr.State`)
   exactly as they are.

## DO NOT
- Do NOT modify `docs/contracts/**` or `MEDIA_KEYS` (`hf_relay.py:34`). No contract change.
- Do NOT add a Svelte/custom component or any frontend build step.
- Do NOT mux media or change the generation pipeline. (Still-only Ken-Burns mux is **DEFERRED** — skip.)
- Do NOT introduce `gr.Video(value=<remote URL>)` (forbidden; #3940/#10726). The stage stays a native
  `<video>` inside `gr.HTML`.
- Do NOT reintroduce `gr.Timer` relay polling or `gr.Video(streaming=True)`.
- Do NOT touch the SSE relay bridge, `@spaces.GPU` marks, or any HF deploy/Space config.
- Do NOT deploy, restart, unpause, poll, or smoke-test any HF Space (account-safety rules).
- Do NOT `git commit` or `git push` — leave the working tree dirty for orchestrator review.

## Validate
- Local gate (must mirror CI, run all three in order):
  `uv run ruff check . && uv run ruff format --check . && uv run pytest`. Fix all failures.
- Tests: add a unit test for `caption_cues()` (timing/coverage) and a `render_stage_html` markup golden
  that asserts the cue JSON is present and **no `setInterval`** is referenced; keep existing tests green.
  Watch the ruff isort I001 gotcha for new first-party imports.
- Optional, non-blocking: the `curl` Range probe in `02-consensus.md` §Experiment if a real bucket /
  Space URL is reachable from config/env — report results, do not block on it.

## Output
Implement on the current branch (uncommitted). Then report: a concise list of what you DELETED and
ADDED with `file:line` refs, the exact local-gate result (paste the tail), the new/changed tests, and
any deviations from this brief with justification.
