# Small Cuts Demo-Readiness Review — opencode (GLM-5.2)

**Scope:** Read-only review of commit `9f7ceea` (just-happened POV clips) against the live-demo
contract: glasses → iPhone → engine → VLM+TTS → iPhone → glasses in-ear, with the HF Space as the
public judged surface. Reviewed paths: `src/small_cuts/engine/{app,session,library,read_gate,__main__}.py`,
`src/small_cuts/viewer.py`, `docs/contracts/*`, and the iOS capture/transport files.

**Headline:** The change iReport written to `docs/reviews/2026-06-14-demo-readiness/reports/opencode.md`.

## Summary

**No Critical (demo-stopping) code defects.** The 12-frame POV clip design is sound and the glasses→ear contract is preserved — `_decode_and_narrate` (session.py:332) decodes only `frames[0]` and ships `SceneAudio` (session.py:224) **before** any supplemental decode or clip encode, so a bad supplemental frame degrades gracefully to a still image rather than blocking narration (locked by `test_bad_supplemental_clip_frame_does_not_block_scene_audio`).

**Highest-leverage pre-demo actions (all operational, no code):**
1. Smoke-test the **public HTTPS** path to the read gate from outside the tailnet (`curl https://<host>/v1/scenes`) — the one thing I can't verify from inside the repo.
2. Confirm `SMALL_CUTS_ENABLE_VISIBILITY_CONTROLS` is **unset** on the Space — PATCH is blocked by the read gate (Important I1).
3. Pre-warm the engine (≈17 s cold) and run it under supervision.
4. Plan demo moments around **motion** — a 4 s / 3 fps clip from stationary glasses reads as a slideshow.

**Small optional tightenings:** finite `httpx.Timeout` for non-stream paths in `read_gate.py:64`; explicit `ws_max_size` on `uvicorn.run` in `__main__.py:24`. Each <5 lines, each independently safe.

**Read-gate security:** tight. Allow-list of exactly three GET path prefixes + the library's `media_path` allowlist/traversal guard provides defense-in-depth. No SSRF (origin fixed at startup from env). No rate limiting — fine for a hackathon, defer.

**Deferred:** schema prose sync (`moment.schema.json:36` still says "best first"), end-to-end proxy test, shared keepalive client, the SSE-based viewer (already plumbed but the polling path is the safer demo choice).
 toast.

- The radio is gated by `SMALL_CUTS_ENABLE_VISIBILITY_CONTROLS` and defaults to hidden/non-interactive
  (`viewer.py:992-1003`). **Verify this env is unset on the Space for the demo.** Do not enable it.

### I2. Read-gate proxy has no timeout on non-stream paths
`read_gate.py:64` uses `httpx.AsyncClient(timeout=None)`. Correct for the long-lived SSE stream,
but for `GET /v1/scenes` it means a hung origin hangs the public request forever. Under judge load
this could stack up. Small, cheap fix: a `httpx.Timeout(connect=2.0, read=20.0, write=5.0, pool=2.0)`
with a separate longer/no timeout only when `path == "/v1/scenes/stream"`. Safe to defer if origin is
healthy, but worth a 3-line tighten.

### I3. No `ws_max_size` / `timeout` / `limit_concurrency` on uvicorn
`engine/__main__.py:24-28` calls `uvicorn.run(...)` with only host/port. Defaults: `ws_max_size=16 MiB`,
unlimited concurrency, 20 s ping interval. A 12-frame envelope at quality 0.9 / ≤1024 px lands around
1.5–3 MiB (well under 16 MiB), so this is **not** urgent — but if you want belt-and-suspenders before
the demo, pass `ws_max_size=8 * 1024 * 1024` explicitly so a runaway frame size fails loudly at the
socket rather than OOMing. Optional.

### I4. Engine pre-warm + process supervision is a runbook step, not guaranteed
Nothing in `__main__.py` auto-restarts on crash. If `llama-server` or the Python process dies mid-demo,
the Space goes dark. Recommend: launch the engine under `tmux`/`launchd` with `Restart=on-failure`,
and send one throwaway moment after start to warm the VLM (already documented in the engine
`CLAUDE.md` — make sure it's actually on the pre-demo checklist).

### I5. Clip quality depends on motion in the 4 s window
`FrameClipBuffer(window: 4.0, maxStoredFrames: 160, maxClipFrames: 12)` (`CaptureCoordinator.swift:61`)
and `_write_clip_mp4(..., fps=3)` (`library.py:276`) ⇒ a 12-frame clip is ~4 s of 3 fps. That reads
as a slideshow, not video, when the glasses were stationary. The "this is what I just saw" feeling
shines when the wearer is **walking / turning / reaching**. For the demo, plan POV moments with
motion; a still desk shot will produce a near-static clip under the (good) narration.

### I6. `docs/contracts/README.md` + schema prose lag the new shape
`moment.schema.json:36` still says "Representative frames, best first" — the new intent is
"selected (current) first + timestamped supplemental for the POV clip." The **shape** is right and
the `$id` is still `1.1.0` (additive), so this is prose drift, not a contract break. Fix the
description text post-submission to keep the KB honest. The contracts `CLAUDE.md` "four message
types" table is fine; only the `frames` field description is stale.

---

## Minor Findings

### M1. Read-gate test coverage is allow-list only
`tests/test_engine_read_gate.py` asserts `is_public_read_allowed` for the four allowed/denied cases
but does **not** exercise the streaming proxy itself (header forwarding, SSE pass-through, query
string, the 403 body). A 5-line `httpx.MockTransport` test would lock in the proxy behavior. Defer.

### M2. Per-request `httpx.AsyncClient` churn
`read_gate.py:64` builds a fresh `AsyncClient` per request and closes it in a `BackgroundTask`. For
the SSE stream that's correct (long-lived). For `GET /v1/scenes` polled every 2 s by each viewer, it
churns TLS/TCP connections to `127.0.0.1` — cheap on localhost, but a single shared client with a
keepalive pool would be tidier. Defer.

### M3. No rate limiting / no per-IP throttle on the public gate
A motivated visitor could poll `/v1/scenes` at high rate; the origin handles it (sqlite WAL read,
no write), so impact is small. Add Cloudflare/Tailnet-side rate limits post-demo if the project
stays public.

### M4. `_decode_clip_frames_for_storage` swallows over-cap supplemental silently
`session.py:376-389` catches any `Exception` from supplemental decode (including the
`_ValidationFailure("frame_exceeds_cap", ...)` from `_validate_frame_size`) and falls back to
`[selected]` — meaning the moment ships without a clip. That is the right demo behavior (clip is
decorative, narration is the product), and `test_bad_supplemental_clip_frame_does_not_block_scene_audio`
locks it in. Just be aware a single oversized supplemental frame quietly drops the clip.

### M5. `demo-readiness.md` checklist is fully unchecked
Every box is `[ ]`. That's a tracking doc, not code, but several items (cold start < 60 s, iPhone
Safari path, no cloud calls, ≤32B params documented, example gallery) are demo-critical and should
be walked through before the window closes.

### M6. ClipMP4 silent failure on PyAV/codec miss
`library.py:135-140` catches any exception from `_write_clip_mp4` and logs to stderr; the
`clip_url` is then absent and the viewer falls back to `<img>` (`viewer.py:389-401`). Resilient, but
if `libx264` is unavailable at runtime the **entire demo** silently degrades to still frames with no
error visible. Worth a one-time `python -c "import av; ..."` smoke before the demo to confirm H.264
encode works on the Mac Studio.

---

## Recommended Fix Order (smallest → highest leverage)

Do these in order; nothing here is a rewrite.

1. **Operational (no code):**
   - Confirm the Space's `SMALL_CUTS_ENGINE_URL` is the **public HTTPS** read-gate URL and that a
     `curl https://<public-host>/v1/scenes` from outside the tailnet returns JSON. *(highest
     leverage — verifies the whole public path.)*
   - Confirm `SMALL_CUTS_ENABLE_VISIBILITY_CONTROLS` is **unset** on the Space (I1).
   - Pre-warm the engine with one throwaway moment; keep it under `tmux`/`launchd` with restart
     (I4).
   - Smoke-test `av`/`libx264` encode on the host (M6).
   - Walk through `docs/demo-readiness.md` (M5).
2. **Tiny code tightenings (each <5 lines, each independently safe):**
   - Add a finite `httpx.Timeout` for non-stream paths in `read_gate.py` (I2).
   - Pass `ws_max_size=8 * 1024 * 1024` to `uvicorn.run` in `__main__.py` (I3, optional).
3. **Re-verify after any change:** `uv run ruff check . && uv run ruff format --check . && uv run pytest`.
4. **Plan the demo moments around motion** so the POV clip actually moves (I5).

---

## Deferred Work (post-submission)

- Prose sync on `moment.schema.json:36` and the contracts README (M6 / I6).
- A real end-to-end proxy test in `tests/test_engine_read_gate.py` (M1).
- Shared keepalive `httpx.AsyncClient` in the read gate (M2).
- Rate limiting / abuse protection on the public surface (M3).
- The Tier-2 gr.Audio → custom `<audio>` swap already noted in `src/small_cuts/CLAUDE.md`.
- SSE-based viewer (the polling path works fine for the demo; SSE is plumbed end-to-end but unused
  by `viewer.py`, which polls every 2 s — a resilient choice for the demo).

---

## Confidence And Unknowns

**High confidence:**
- The glasses→ear contract is **not** at risk from this change. `_decode_and_narrate`
  (`session.py:332-346`) decodes only `frames[0]`, narrates, and `SceneAudio` is sent
  (`session.py:224`) **before** any supplemental decode or clip encode runs. Verified by
  `test_bad_supplemental_clip_frame_does_not_block_scene_audio`.
- Contract alignment iOS ↔ engine ↔ viewer is correct for the clip path: iOS sends selected first
  with `ts_offset_ms=0` and supplementals with negative offsets
  (`CaptureCoordinator.swift:198`, `MomentBuilder.swift:202`); the engine sorts ascending
  (`session.py:365-373`) so the clip plays forward in time toward the narrated present; the viewer
  renders `<video>` when `media.clip_url` is present and falls back to `<img>` otherwise
  (`viewer.py:347, 389-411`). NarratedScene schema (`narrated-scene.schema.json:81-85`) declares
  `clip_url` and the library populates it (`library.py:186-187`).
- The read gate's allow-list is correct and the library's `media_path` (`library.py:250-257`)
  provides defense-in-depth against path traversal (`MEDIA_FILES` allowlist + `is_relative_to`
  check). `tests/test_engine_read_gate.py` covers the allow-list matrix.
- WS payload size is comfortably under uvicorn's 16 MiB default for 12 × ≤1024 px JPEG at q=0.9.

**Medium confidence:**
- The exact public tunnel topology (Cloudflare Tunnel vs Tailnet Funnel vs raw tailnet). I can see
  the read-gate code and that the viewer polls (does not depend on SSE), but I cannot verify the
  public hostname/HTTPS wiring from inside the repo. **This is the one thing I'd most want to
  confirm with a real external `curl` before the demo.**

**Unknowns (out of repo scope):**
- Real Ray-Ban Meta DAT frame rate and JPEG size distribution at the configured `.high`/24 fps
  stream — the math above assumes ~720×1280 @ q=0.9 ≈ 100–250 KiB/frame. If actual frames are much
  larger, revisit `ws_max_size` (I3).
- Whether the glasses actually claim the active Bluetooth audio route on demo day (an A2DP pairing
  / routing issue, not a code issue — covered by `ios/SmallCuts/RUNBOOK.md`).
- Cloudflare Tunnel's idle timeout for the (currently unused-by-viewer) SSE path — irrelevant for
  the judged polling path, relevant only if the viewer is later switched to SSE.

**Overall:** Code is demo-ready. Spend the remaining time on the runbook, the public tunnel
smoke-test, and motion-rich demo moments — not on the code.
