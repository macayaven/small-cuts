I've now read the full review surface: the contract schemas, the engine session/library/read-gate/app, the iOS capture path (gate → clip buffer → builder → transport → voice player), and the Gradio viewer. Below is my read-only report.

Note on process: the task is explicitly read-only ("Do not edit files… Return markdown only"), so I have not written to the assigned report path or made any changes — the report is delivered here as markdown.

---

# Small Cuts — Demo-Readiness Review (Claude)

Date: 2026-06-14 · Branch `claude/adoring-clarke-49l3uk` · HEAD `9f7ceea`
Scope: read-only. Focus: live-path correctness, the 12-frame POV clip tradeoff, iOS→engine→viewer contract alignment, public read-gate security, minimal pre-deadline fixes.

## Critical Findings

### C1 — `GET /v1/scenes` returns the *oldest* N, so a non-empty library hides the live moment
`SceneLibrary.list_scenes` (`src/small_cuts/engine/library.py:220`) does:
```sql
SELECT * FROM scenes ... ORDER BY captured_at, seq LIMIT ?
```
That is ascending order with `LIMIT`, so it returns the **earliest** N rows. The viewer treats `scenes[-1]` as "newest / live" (`poll_engine`, `src/small_cuts/viewer.py:539`) and polls with `limit=60` (`SHELF_LIMIT`). The sqlite DB **persists across restarts** at `~/.small-cuts/library`. So if ≥60 scenes already exist from development/warm-up testing, every *new* live moment sorts after the 60 oldest and **never reaches the public Space** — the "this is what I just saw" channel silently freezes on stale content. Failure is silent (no error), which makes it the most dangerous demo risk.

- Minimal operational fix (do this regardless): start the demo against a **clean** library — `SMALL_CUTS_LIBRARY_DIR=/path/to/fresh-dir` or move aside `~/.small-cuts/library`.
- Minimal code fix: take the newest N by `seq`, then re-order chronologically, e.g.
  `SELECT * FROM (SELECT * FROM scenes [WHERE …] ORDER BY seq DESC LIMIT ?) ORDER BY captured_at, seq`.
- Verify: send 65+ moments, confirm the 65th appears on stage.

### C2 — The in-ear audio route is the core promise and is the least-tested link
The non-negotiable is glasses→…→glasses **in-ear**. `AVAudioClipPlayer.play()` (`ios/.../Capture/VoicePlayer.swift:34`) sets `AVAudioSession.setCategory(.playback)` + `setActive(true)` and relies entirely on the OS's *current* output route being the glasses' Bluetooth A2DP sink. Two live-only unknowns can break this on stage:
1. Whether the Ray-Ban Meta glasses actually present as an iOS audio **output** route while the DAT camera stream is active (vs. audio landing on the phone speaker).
2. Whether forcing the session to `.playback` mid-capture perturbs or tears down the DAT camera stream / BT link.

Code-wise this is reasonable, but it is unverified hardware integration. **Run the full `ios/SmallCuts/RUNBOOK.md` device path end-to-end at least once before judging** and confirm the voice lands in-ear and capture keeps streaming. There is no code change to recommend until that test tells us which way it fails.

## Important Findings

### I1 — All security rests on the public tunnel pointing at the read-gate, not the engine
The gate (`src/small_cuts/engine/read_gate.py`) is correct: it allowlists only `GET /v1/scenes`, `/v1/scenes/stream`, `/media/*` and 403s everything else, and it has **no** websocket route, so `/v1/session` cannot be proxied through it. But that protection only exists if the Cloudflare tunnel's origin is the **read-gate app**, and the read-gate's `SMALL_CUTS_ORIGIN_ENGINE_URL` points at the local engine. If the tunnel is accidentally pointed straight at the engine (`:8077`), the public internet gets the WS write socket and `PATCH /v1/scenes/{id}` — a full write/visibility-tamper surface.
- Verify from an **off-Tailnet** network: `GET …/v1/scenes` → 200; `POST`/`PATCH …/v1/scenes/x` → 403; a `ws://`/`wss://` connect to `…/v1/session` → fails. This 3-probe check is the single highest-leverage security gate before going live.

### I2 — Visibility is not enforced on read: every captured frame is world-readable
`list_scenes` is called with no `visibility` filter and the gate never constrains it, so **private scenes are publicly served**. New scenes default to `"private"` (`library.py:167`) and the visibility radio is off by default (`SMALL_CUTS_ENABLE_VISIBILITY_CONTROLS`). The demo *depends* on the gate ignoring visibility (otherwise nothing would show), which is a deliberate tradeoff — but it means anything the glasses capture during the event is immediately public via the tunnel and the `/v1/scenes` JSON (including `session_id`, `owner`, model/latency provenance). For a live event: **assume the camera is a public broadcast** — don't capture anything sensitive. No code fix needed for the demo; just be aware.

### I3 — 12-frame payload can approach the server WebSocket size ceiling
A moment now carries up to 12 JPEGs (≤1024px, q0.9) base64-encoded in **one** WS text frame (`MomentBuilder.maxFramesPerMoment = 12`). Worst case (detailed 1024px frames ~0.4–0.6 MB each) ≈ 7 MB raw → ~9 MB base64. uvicorn's default `ws_max_size` is 16 MB, so typical moments (~3–5 MB) are fine, but a heavy moment that crosses 16 MB is closed by the server (1009), which drops the socket → reconnect → idempotent resend → fails identically → that moment wedges. The iOS side's `maximumMessageSize = 32MB` (`EngineSessionClient.swift:178`) is *inbound* and doesn't help here.
- Mitigation (cheap, optional): encode the **supplemental** (clip-only) frames smaller/lower-quality than the narrated frame[0] — they never reach the VLM, only the POV clip. Or drop `maxClipFrames` to ~8.
- Verify: log the largest envelope byte size across a capture session; keep it comfortably under 16 MB.

### I4 — Engine-mode public Space has no fallback if the engine/tunnel is down
The seed "hero" library only loads in **upload mode** (`_seed_scenes`, `viewer.py:712`, gated on `client is None`). In engine mode (the live demo config) a dead engine or tunnel shows "Signal lost — engine unreachable" with no content. Decide the posture deliberately: either (a) keep engine+tunnel rock-solid and pre-seed a few `public` scenes into the engine library so the judged page is never empty, or (b) treat the seeded upload-mode Space as the resilient judged artifact and use engine mode only for the live segment.

### I5 — Cold start (~17s first moment) will look frozen if not pre-warmed
Per `engine/CLAUDE.md`, the first moment costs ~17s (llama-server spawn + model load); warm e2e is ~5.7–6.9s. This isn't a bug, but if the first *live* moment of the demo is also the cold one, it reads as a hang. **Send a throwaway warm-up moment after starting the engine** and before judging. (Freshness is safe: `play_by = created_at + 60s` and `created_at` is stamped *after* narration, so even the cold clip stays playable.)

## Minor Findings

- **M1 — Contract version not bumped for an additive change.** `moment.schema.json` raised `frames.maxItems` 4→12 and added `ts_offset_ms`, and `clip_url` is repurposed — all still tagged `1.1.0` across schema, `session.py` (`CONTRACT_VERSION`), and `MomentBuilder.contractVersion`. In-repo consumers are consistent so there's no demo impact, but it deviates from the documented "additive ⇒ minor, lockstep bump + golden samples" rule (`docs/contracts/CLAUDE.md`). Latent risk only if an external consumer pinned the old 1.1.0 (maxItems:4 would reject 12-frame moments).
- **M2 — `clip_url` description is now stale.** Schema says "Source video segment when the capture app uploaded one" (`narrated-scene.schema.json:84`), but the engine now *assembles* the clip from sampled frames (`library.py:_write_clip_mp4`). Update the description to match (one-home-per-fact).
- **M3 — POV clip alignment is actually well-designed.** Engine narrates only `frames[0]` (`session.py:_decode_and_narrate`), so extra frames add no narration latency; clip frames are sorted by `ts_offset_ms` (selected frame at offset 0 lands last), giving a chronological past→present clip whose final frame equals `frame.jpg` (the poster). The clip is built in the sink *after* SceneAudio is sent, so the glasses→ear contract is untouched. The only seam: the looping `<video>` jump-cuts present→past each loop — acceptable.
- **M4 — Clip encode sits inside the awaited sink**, so `busy`/gate-suppression extends ~0.5–1s per moment (`_process` awaits `store()` which awaits `_write_clip_mp4`). Negligible against the 8s `minInterval`, but it is on the suppression path.
- **M5 — iOS `FrameClipBuffer` holds up to 160 full-res `CapturedFrame`s** (4s window, `CaptureCoordinator.swift:61`). Bounded by window trim, but worth a glance for memory pressure on long high-FPS sessions.
- **M6 — SSE error frames are world-readable and may leak internal detail.** Pipeline error messages (truncated to 300 chars, possibly file paths/model errors) fan out to the public `/v1/scenes/stream`. The Gradio viewer polls rather than subscribing, so it won't surface them, but a public `curl -N …/stream` would.
- **M7 — Decompression-bomb ordering.** Frames are decoded before the post-decode ≤1024px check (`session.py:_decode_frames`). Mitigated by PIL's `MAX_IMAGE_PIXELS` and the Tailnet-only write path; low risk.

## Recommended Fix Order

1. **C1 operational** — run the demo against a **fresh library dir** (and ideally apply the newest-N query fix). One command, removes a silent demo-killer.
2. **C2 / I1** — run the **RUNBOOK device path once** end-to-end (voice in-ear + capture survives) and the **3-probe off-Tailnet gate check** (200 on read, 403 on write, WS fails). These two confirm the two non-negotiables.
3. **I5** — bake a **warm-up moment** into the start sequence.
4. **I4** — decide engine-mode-vs-seeded posture; if engine mode, pre-seed a couple of `public` scenes so the page is never empty.
5. **I3** — measure max envelope size; only act (smaller supplemental frames / `maxClipFrames=8`) if it's near 16 MB.
6. **M1/M2** — version-bump + description fix as a follow-up housekeeping PR (not demo-blocking).

## Deferred Work (post-submission)

- Proper visibility enforcement on the read path (gate forces `public`/`shared`), with a real publish flow — today's "all public" is a demo shortcut (I2).
- Schema `$id` minor-bump discipline + golden samples for the 12-frame/`ts_offset_ms`/`clip_url` change (M1).
- Per-quality encoding for clip-only frames; move clip MP4 encode fully off the suppression path (I3/M4).
- Read-gate hardening: shared httpx client, per-request timeout/size caps, rate limiting (M6 + read_gate robustness).
- The deferred custom slim `<audio>` player swap noted in `src/small_cuts/CLAUDE.md` (live-Space audio test gated).

## Confidence And Unknowns

- **High confidence (read directly):** C1 (query order + viewer `scenes[-1]` assumption), I1 (no WS route on the gate; allowlist logic), I2 (no visibility filter on read), M1/M2/M3/M4. These are determinable from source.
- **Medium confidence:** I3 — exact worst-case payload depends on real glasses frame entropy and the deployed `ws_max_size`; I verified the 16 MB default but did not confirm the actual uvicorn launch flags.
- **Unverified (need hardware/deployment, out of read-only scope):** C2 (in-ear route + DAT/`.playback` interaction — only the live device test settles this), I1's deployment half (where the tunnel actually points), and whether PyAV on the engine has a working libx264 encoder (code degrades gracefully to a still frame if not, so not demo-breaking either way).
- **Did not inspect:** `GlassesSessionController.swift`, `RUNBOOK.md`, `narrator.py`/`tts.py` internals, and the test suites — I relied on the context packet's "verification already run" (160 Python tests pass; iOS builds + 62 sim tests pass) for those. My findings are about live-path/runtime/deployment risks the green test suite does not cover.
