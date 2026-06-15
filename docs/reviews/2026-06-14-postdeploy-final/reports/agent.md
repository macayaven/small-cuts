# Cursor Agent Review — Post-Deploy Final Demo (2026-06-14)

**Branch:** `claude/adoring-clarke-49l3uk` · **HEAD:** `1104e259`  
**Scope:** Read-only inspection per `docs/reviews/2026-06-14-postdeploy-final/context.md`

---

## Critical Blockers

**No confirmed code blockers.** The verified rehearsal (rayuela seed POV → `SceneAudio` → public `/v1/scenes` with `frame.jpg`, `card.webp`, `voice.wav`, `clip.mp4`) matches the intended architecture. Remaining risks are operational or require human/hardware verification.

1. **Human-click audio playback (unverified).** `PLAYBACK_SYNC_JS` correctly delegates play/pause to trusted DOM gestures (`pointerdown` on touch, `click` on desktop) and drives `#sc-voice` as the master clock. Browser automation hitting `NotAllowedError` is expected. Until a real human click on the live Space advances video, voice, captions, and progress together, the judged viewer half of the story is not fully proven.

2. **Cloudflare quick-tunnel ephemerality (ops).** The Space depends on a known-good quick tunnel (`lincoln-greene-paragraph-tcp.trycloudflare.com`). If it dies mid-demo, `<video>`/`<audio>` URLs and polling both fail (“Signal lost”). The named tunnel is verified for reads but leaves the Space on “Signal lost” — do not switch before the demo.

3. **Physical glasses → iPhone → engine path (unverified).** Synthetic and seed rehearsals passed on Mac Studio. The decisive checks — reinstall latest iOS app, simulated source, Ray-Ban Meta in-ear narration — are still unchecked in `docs/demo-readiness.md`.

---

## Important Risks

- **Engine cold start (~17 s first moment).** If the engine restarts before the demo, the first live moment pays llama-server spawn + model load. Warm with one throwaway moment immediately before going live (`src/small_cuts/engine/CLAUDE.md`).

- **Single-frame moments produce no `clip.mp4`.** `library.store` only writes a clip when `len(clip_frames) >= 2` (`library.py:132-140`). A gate that fires too early yields a still `frame.jpg` on the Space stage, not video. `FrameClipBuffer(window: 4.0, maxClipFrames: 12)` and glasses at 7 fps need ~4 s of streaming before the gate fires for a multi-frame clip.

- **New-scene audio swap during playback.** In engine mode, `poll_engine` re-renders `#sc-voice` whenever `payload["scene_id"] != playing_id` (`viewer.py:559-562`). A second moment while the host is replaying the first resets playback. During the demo, pin a shelf item or avoid firing a second moment until the first replay finishes.

- **Pre-`SceneAudio` disconnect loses the moment (distinct from the fixed symptom).** If the WebSocket drops during narration/TTS (before `SceneAudio`), `_drain` cancellation aborts processing; `moment_id` stays in `seen_moment_ids`, so an iOS resend gets `duplicate` with no audio. Low probability on a stable Tailnet; not the “audio heard, no Space clip” path.

- **Read gate is path-precise, not method-complete for HEAD.** `is_public_read_allowed` allows only `GET` on `/v1/scenes`, `/v1/scenes/stream`, and `/media/*` (`read_gate.py:33-36`). HEAD returns 403. Harmless for the current Space (polling uses GET; media uses GET).

---

## Minimal Pre-Demo Changes

**No mandatory code edits.** The storage-after-disconnect fix, read gate, and viewer playback wiring are demo-safe as deployed.

**Ops only (do these before physical test):**

1. Warm the engine with one throwaway moment.
2. Confirm the quick tunnel is alive; keep the relaunch + `SMALL_CUTS_ENGINE_URL` update command ready.
3. Run the **human-click Space smoke first** — tap `.sc-play-btn` (the pill play icon), not surrounding chrome.
4. Frame demo moments so glasses stream ~4 s before the scene gate fires (multi-frame clip).
5. Avoid firing a second moment while replaying the first on the Space (or pin the first scene in the shelf).

**Optional belt-and-suspenders (only if paranoia warrants a 3-line change):** retain strong references to in-flight storage tasks in a module-level `set` with `add_done_callback(discard)`. This is defensive; the existing `asyncio.shield` + done-callback pattern is already covered by `test_disconnect_after_scene_audio_still_publishes_scene` and the rayuela rehearsal. Not required before physical test unless that test fails locally.

---

## Reject / Defer

*Wait until after submission:*

- **Named-tunnel / “Signal lost” debugging** — keep the known-good quick tunnel for the demo.
- **Swapping `gr.Audio` for a custom seekable player** — Tier-2 per `src/small_cuts/CLAUDE.md`; current `#sc-voice` + delegated gestures is the lower-risk path.
- **Pre-`SceneAudio` disconnect / dedupe-before-ack redesign** — real but low-probability; intentional idempotency tradeoff.
- **Architecture migrations** — streamed audio chunks, SSE-based viewer, multi-user library, CORS on read gate.
- **Binding hardening on `0.0.0.0:8077`** — acceptable on Tailnet/LAN for v1; not a demo blocker.
- **iOS registration backgrounding rework** — 120 s `registrationTimeout` is adequate for a controlled demo.

---

## Demo Checklist Assessment

`docs/demo-readiness.md` unchecked items are **correctly classified**:

| Unchecked item | Correct? | Rationale |
|---|---|---|
| Human browser smoke (play → AV+captions+progress) | Yes | Requires trusted human gesture; automation cannot certify audio unlock |
| Physical iPhone Safari smoke | Yes | Device + Safari autoplay policy |
| Physical iPhone simulated-source smoke | Yes | Latest app build not exercised end-to-end on device |
| Physical Ray-Ban Meta glasses smoke | Yes | Core demo path; only synthetic/seed verified so far |
| Demo video / social post / submission analyzer | Yes | Submission deliverables, not code gates |
| Demo Video section (all items) | Yes | Production task after the live path works |

Checked items align with verified state in `context.md`. “Known Constraints” honestly documents image-only capture, Space-as-viewer, no autoplay-sound promise, and quick-tunnel ephemerality.

---

## Storage-After-Disconnect Assessment

**Sufficient for the stated symptom** (“audio heard, but no Space video/captions”).

Evidence chain:

1. **`SceneAudio` is sent before storage work** (`session.py:224` before `session.py:238-250`).
2. **Storage runs in a shielded detached task** — on `CancelledError` (socket disconnect), `storage_task` continues with `_log_worker_failure` registered (`session.py:251-255`).
3. **Storage path is resilient** — `_decode_clip_frames_for_storage` falls back to `[selected]` on supplemental decode failure (`session.py:408-421`); `library.__call__` fans out `library_write_failed` on disk/sqlite errors (`library.py:91-111`).
4. **Regression test pins behavior** — `test_disconnect_after_scene_audio_still_publishes_scene`: slow decode, WS closed after `SceneAudio`, scene appears in `GET /v1/scenes`.
5. **Live rehearsal confirms** — rayuela scene `3527ae37-…` has public `clip.mp4` and `voice.wav` through the read gate.

The prior symptom matched storage running *before* `SceneAudio` and being cancelled on disconnect. Reordering + shield addresses that path. A disconnect *during* narration (before `SceneAudio`) is a separate, lower-probability failure mode (see Important Risks).

---

## Bottom Line

**Demo-ready from a code perspective.** Non-negotiables hold: glasses→ear path is center, HF Space is the judged public surface, capture is image-frame-only, public internet cannot mutate visibility (`read_gate.py`), Mac Studio runs local inference. No architecture migration is warranted.

The demo now hinges on **three non-code gates**: (1) keep the quick tunnel alive, (2) warm the engine, (3) pass the human-click Space audio check. Then run physical iPhone and Ray-Ban smokes. If those three ops gates hold, the verified seed rehearsal is strong evidence the full glasses→ear→Space story will work on stage.
