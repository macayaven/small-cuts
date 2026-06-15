# OpenCode Review — Post-Deploy Final Demo (2026-06-14Report written to `docs/reviews/2026-06-14-postdeploy-final/reports/opencode.md`.

**Bottom line:** No code blockers. The storage-after-disconnect fix is correct and well-tested (SceneAudio sent first, storage task `asyncio.shield`ed, library failures fan out as error frames). The read gate enforces the write-non-negotiable. The demo hinges on three non-code items: (1) keep the Cloudflare quick tunnel alive (highest risk — named tunnel leaves Space on "Signal lost"), (2) warm the engine before the demo, (3) pass the human-click audio check on the Space. I also flagged two minor correctness gaps to defer: single-frame moments yield no `clip.mp4`, and a pre-SceneAudio disconnect loses the moment (distinct from the fixed symptom).
 URLs (`<video src>`, `<audio src>`) break at the same time. The named tunnel
   (`small-cuts.carloscrespomacaya.com`) is verified for reads but leaves the Space on "Signal
   lost" — that interaction is unresolved (`docs/demo-readiness.md:62-66`).
2. **Human-click audio playback (unverified).** The trusted-gesture binding (delegated
   `pointerdown`/`click` on `.sc-play-btn` in `PLAYBACK_SYNC_JS`, `viewer.py:860-896`) is the right
   approach and reads correctly, but it has only been exercised by browser automation, which hit
   `NotAllowedError`. Until a real human click advances video + voice + captions + progress
   together on the Space, the e2e glasses→ear→Space story is unconfirmed.
3. **Engine cold start (ops).** Engine was warmed by the seed rehearsal, but if it restarts before
   the demo the first live moment takes ~17s (llama-server spawn + load). Send a throwaway warm-up
   moment before the demo (`src/small_cuts/engine/CLAUDE.md`).

## Important Risks

- **Single-frame moments produce no `clip.mp4`.** `library.store` only writes a clip when
  `len(clip_frames) >= 2` (`library.py:132-140`); a single-frame moment degrades to a static
  `frame.jpg` on the stage. Graceful, not a crash, but the demo wants video. `FrameClipBuffer`
  (`window=4.0, maxClipFrames=12`) yields multi-frame moments only if the glasses stream a few
  seconds before the gate fires.
- **Pre-SceneAudio disconnect loses the moment.** The new fix shields storage that starts AFTER
  `SceneAudio` is sent. If the socket drops DURING narration (before `SceneAudio`), the drain task
  is cancelled (`session.py:184-186`), the moment is never stored, and `moment_id` stays in
  `seen_moment_ids` (`session.py:157`) — so an iOS resend gets `duplicate` and never receives
  audio. Low probability on Tailnet; it's a correctness gap distinct from the fixed symptom.
- **New-scene audio swap mid-playback.** Engine-mode `poll_engine` swaps the `<audio>` source
  whenever a newer scene arrives and nothing is pinned (`viewer.py:559-562`). A second moment fired
  while the host is playing the first on the Space resets playback. Pin via shelf select or
  rewind/forward to freeze playback during the demo.
- **`0.0.0.0:8077` engine binding.** Engine listens on all interfaces. Fine on Tailnet/LAN; if the
  Mac Studio were ever directly exposed the WS would be publicly writable. Not a demo blocker on a
  home network, but the private write socket is only "private" by network topology, not by bind.

## Minimal Pre-Demo Changes

**No code edits required.** Fixes are in place and tested. Recommended ops steps only:

1. **Warm the engine** with one throwaway moment right before the demo (mitigates cold start).
2. **Monitor the quick tunnel**; have the re-launch command ready. If it drops, re-point
   `SMALL_CUTS_ENGINE_URL` and restart the Space. Only chase the named-tunnel "Signal lost" issue
   if it's a quick win.
3. **Run the human-click check first.** If `NotAllowedError` somehow persists, make sure the click
   lands on `.sc-play-btn` (not a child element) so `closest('.sc-play-btn')` resolves — the
   current delegated binding is already correct.
4. **Frame the demo moments** so the glasses stream ~4s before the gate fires, guaranteeing a
   multi-frame `clip.mp4`.

## Reject / Defer (wait until after submission)

- **Swapping `gr.Audio` for a custom slim `<audio>` with a seekable progress bar.** Already flagged
  Tier-2 in `src/small_cuts/CLAUDE.md`. The file-backed `<audio id="sc-voice">` + delegated-gesture
  path is the lower-risk option; don't touch it now.
- **Fixing pre-SceneAudio disconnect / `_pending`-on-cancel loss.** Real but low-probability on
  Tailnet; dedupe-before-processing is intentional for idempotent resends. Revisit post-hackathon
  (two-phase admit or ack-then-dedupe).
- **Named-tunnel migration / debugging.** Only if it's a 5-minute fix; otherwise keep the
  known-good quick tunnel and watch it.
- **Any architecture migration** (streamed-audio chunks, multi-user library, SSE-based viewer).
  Explicitly out of scope for v1; the 2s poll is fine on `cpu-basic`.
- **Adding CORS headers to the read gate.** Not needed: `<video>`/`<audio>` media loads and
  `currentTime`/`duration` reads work without CORS; the Space's polling is server-side via
  `httpx.Client`, not from the browser.

## Demo Checklist Assessment

`docs/demo-readiness.md` unchecked items are correctly classified:

- **Human browser smoke** and **Physical mobile smoke on iPhone Safari** (Judged Space) — correctly
  unchecked; these are the decisive unverified steps.
- **Physical iPhone simulated-source smoke** and **Physical Ray-Ban Meta glasses smoke** (Private
  Live Path) — correctly unchecked; the physical-device path is unverified.
- **Demo video / social post / submission analyzer** and all **Demo Video** items — correctly
  unchecked; production/delivery tasks, not code.

No checked item is mis-classified, and the "Known Constraints" section honestly documents both the
autoplay-sound caveat and the quick-tunnel-ephemerality caveat.

## Storage-After-Disconnect Assessment

The fix is **sufficient for the stated symptom** ("audio heard, but no Space video/captions"):

- `session.py:224` sends `SceneAudio` before creating the storage task.
- `session.py:238-255` creates `_finish_scene_storage` as a separate task and `asyncio.shield`s it.
  On `CancelledError` (socket disconnect) the storage task is detached with `_log_worker_failure`
  as a done-callback and continues to completion.
- `_finish_scene_storage` → `_hand_to_sink` → `library.__call__` runs `store()` (media + sqlite
  row) then `publish_event()` (SSE fan-out). Both are inside the shielded task, so the scene
  reaches `/v1/scenes` and SSE subscribers even after disconnect.
- `_decode_clip_frames_for_storage` swallows its own decode errors and falls back to `[selected]`
  (`session.py:413-421`), so a bad supplemental frame can't block storage.
- `library.__call__` catches `store()` failures and publishes a `library_write_failed` error frame
  (`library.py:91-111`), so a storage failure is observable, not silent.
- Regression `test_disconnect_after_scene_audio_still_publishes_scene` (slow decode + post-audio
  disconnect → scene appears in `/v1/scenes`) pins the behavior.

**Gap (not the stated symptom):** a disconnect DURING narration (before `SceneAudio`) cancels the
drain task; the moment is never stored and the `moment_id` remains deduped, blocking iOS resend.
Low probability on Tailnet — defer.

## Bottom Line

Code is demo-ready. The storage-after-disconnect fix is correct and well-tested. The read gate
enforces the non-negotiables (`GET /v1/scenes` 200; `/v1/session` and `PATCH /v1/scenes/*` 403;
allow-list is path-precise at `read_gate.py:33-36`). No code edits are needed before the physical
test. The demo hinges on three non-code things: (1) keep the quick tunnel alive, (2) warm the
engine, (3) pass the human-click audio check. If those three hold, the glasses→ear→Space story
works as verified in the seed rehearsal.
