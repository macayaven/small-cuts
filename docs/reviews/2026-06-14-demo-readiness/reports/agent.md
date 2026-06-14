# Demo-Readiness Review — Agent

**Repo:** `small-cuts` @ `9f7ceea`  
**Scope:** Context packet + listed source paths (read-only)  
**Assigned path (orchestrator):** `docs/reviews/2026-06-14-demo-readiness/reports/agent.md`

---

## Critical Findings

### C1 — All 12 frames are decoded on the glasses→ear critical path before narration starts

In `session.py`, `_decode_and_narrate` calls `_decode_frames`, which decodes **every** frame in the envelope before `narrator.narrate` runs on frame 0 only:

```353:370:src/small_cuts/engine/session.py
def _decode_frames(envelope: dict[str, Any]) -> tuple[Image.Image, list[Image.Image]]:
    decoded: list[tuple[int, int, Image.Image]] = []
    selected: Image.Image | None = None
    for index, frame in enumerate(envelope["frames"]):
        image = _decode_frame(frame)
        ...
    clip_frames = [image for _, _, image in sorted(decoded, key=lambda item: (item[0], item[1]))]
    return selected, clip_frames
```

Clip assembly is viewer-only (`library.py` writes `clip.mp4` after `SceneAudio` is sent), but supplemental JPEG decode still sits in front of VLM + TTS. With 12 frames at ≤1024 px, this can add hundreds of ms to multi‑MB moments and erode the ≤10 s warm e2e budget — the path that must stay reliable for in-ear playback.

**Demo risk:** Slower narration return → higher `play_by` pressure on `VoicePlayer` (D9, 60 s deadline).

---

### C2 — Engine listens on `0.0.0.0:8077` with unauthenticated WebSocket writes; security depends entirely on network isolation

```24:28:src/small_cuts/engine/__main__.py
    uvicorn.run(
        build_engine_app(),
        host=os.environ.get("SMALL_CUTS_ENGINE_HOST", "0.0.0.0"),
        port=int(os.environ.get("SMALL_CUTS_ENGINE_PORT", "8077")),
    )
```

`/v1/session` accepts arbitrary `MomentEnvelope` writes with no auth. The read gate blocks writes on the **public** hostname, but if port 8077 is reachable beyond Tailnet (misconfigured tunnel, LAN exposure, wrong firewall rule), anyone can inject moments.

**Demo risk:** Misconfiguration is a show-stopper for the “private write / public read” story and for hackathon judging on security posture.

---

### C3 — Cold-start first moment (~17 s) is unverified in the live glasses loop

Documented in `engine/CLAUDE.md` and `RUNBOOK.md`: first moment after engine boot includes llama-server spawn + model load. `play_by` is 60 s, so it usually survives, but:

- `session_start` fires on the first frame (often before the 4 s clip buffer fills → still image on Space).
- The skipped live-engine smoke test (`EngineLoopSmokeTests`) sends a **single-frame** envelope only.
- `dress_rehearsal.py` also sends single-frame moments — it does **not** exercise the 12-frame POV path.

**Demo risk:** First live capture after reboot is the most likely moment to miss the “just happened” POV feel and to stress latency.

---

## Important Findings

### I1 — 12-frame POV design preserves the glasses→ear contract; clip value is HF Space–only (good split)

| Layer | Behavior | Glasses impact |
|-------|----------|----------------|
| iOS | `FrameClipBuffer` (4 s window, max 12) + `MomentBuilder` (frame 0 first, negative `ts_offset_ms`) | Sends larger WS payload; encode runs off main actor |
| Engine | Narrates frame 0 only; sorts by `ts_offset_ms` for clip | No extra VLM calls |
| Library | `_write_clip_mp4` at 3 fps when ≥2 frames; optional `media.clip_url` | After `SceneAudio` — non-blocking |
| Viewer | `format_stage` maps `clip_url` → `clip_src`; muted looping `<video>` synced to audio clock | Public read only |

The architecture correctly keeps narration grounded on one frame while the Space gets a short POV loop. **Tradeoff:** ~1–3 MB JSON per moment (12 JPEGs base64) increases upload time and decode cost on phone and engine; iOS `maximumMessageSize` is 32 MB, so size is unlikely to hard-fail.

---

### I2 — First auto-fired moment (`session_start`) will usually have no clip

`SceneGate` fires immediately on the first frame; `FrameClipBuffer` needs ~2+ frames over the 4 s window before `clip.mp4` exists. Expect still + audio for moment 1, POV video from moment 2 onward (after ~4 s of streaming at 24 fps).

**Demo tip:** Warm the engine with a throwaway moment, then walk for ≥5 s before the “hero” scene change.

---

### I3 — Gate suppression lags behind local JPEG encode (race window)

`CaptureCoordinator` sets `gate.suppressed` only on engine `status.busy`, not when encode/send starts. Between fire and first `accepted`/`status`, another automatic scene change could start a second 12-frame encode. `minInterval` (8 s) mitigates auto-fire; manual fire is also blocked only when `suppressed`.

**Demo risk:** CPU spikes on iPhone during rapid scene changes; wasted encode work.

---

### I4 — Public read gate: correct path allowlist, but no visibility enforcement on reads

`is_public_read_allowed` permits only `GET /v1/scenes`, `GET /v1/scenes/stream`, and `GET /media/*`. PATCH/WS paths return 403 — verified in tests.

However:

- `GET /v1/scenes` with no filter returns **all** scenes, including `visibility: private` (stored default in `library.py`).
- The viewer polls without a visibility filter (`EngineClient.list_scenes`).
- `SMALL_CUTS_ENABLE_VISIBILITY_CONTROLS` defaults off; when on, `PATCH` through the public gate would fail anyway.

**Security posture:** Write protection is solid for v1 demo. Read privacy is not enforced — anyone with the public URL can scrape the full library and media. Acceptable for single-user hackathon demo; not acceptable post-demo.

---

### I5 — Read gate creates a new `httpx.AsyncClient` per request

```64:72:src/small_cuts/engine/read_gate.py
        client = httpx.AsyncClient(timeout=None)
        upstream = await client.send(
            client.build_request(
                "GET",
                _origin_url(origin, request),
                headers=_forward_headers(request.headers),
            ),
            stream=True,
        )
```

HF Space polls every 2 s (`POLL_SECONDS`); each poll + media fetch opens a new client. Under demo load or tunnel flakiness this adds connection churn and latency. No integration test exercises the proxy end-to-end (only `is_public_read_allowed` unit tests).

---

### I6 — Viewer poll latency (2 s) + 5 s HTTP timeout

Engine mode uses timer polling, not SSE (`viewer.py`). New scenes can appear up to ~2 s late on the Space. `HTTP_TIMEOUT_S = 5.0` — a slow tunnel or busy Mac Studio yields “Signal lost — engine unreachable” even when the engine is fine.

**Demo risk:** Judges see stale “Happening now” or off-air header during load spikes.

---

### I7 — Contract alignment is good; minor golden-sample drift

Aligned:

- `moment.schema.json` `maxItems: 12` ↔ iOS `maxFramesPerMoment = 12`
- `ts_offset_ms` optional; iOS sends `0` on anchor frame, negatives on history
- Engine sorts clip frames by `(ts_offset_ms, index)`
- `narrated-scene.schema.json` optional `clip_url` ↔ `library.to_narrated_scene`

Gaps:

- Golden `narrated-scene` sample has no `clip_url` (optional — OK).
- `dress_rehearsal` / live smoke never send multi-frame envelopes — **12-frame path unverified e2e**.
- `narrated-scene` schema description says clip is “when the capture app uploaded one”; engine now **generates** it from frames (doc drift only).

---

### I8 — Clip write failure degrades gracefully

If PyAV/libx264 fails, `library.store` logs and continues without `clip_url`. Viewer falls back to still frame. Glasses audio unaffected. Worth confirming `libx264`/`h264` encoder availability on the Mac Studio demo host once.

---

## Minor Findings

### M1 — `HEAD` blocked on read gate

Tests expect `HEAD /v1/scenes` → denied. Some health checks use HEAD; unlikely to break Gradio (server-side GET polling).

### M2 — Engine-mode scenes have no `duration` field

`format_stage` sets `duration: None` for engine scenes. Captions sync to audio via `PLAYBACK_SYNC_JS` — acceptable; clip loops under longer narration by design.

### M3 — `read_gate.py` has no dedicated launcher in repo

Only `app = build_read_gate_app()`. Ops must run e.g. `uvicorn small_cuts.engine.read_gate:app` behind Cloudflare — verify the exact demo command before showtime.

### M4 — Golden contracts still single-frame

`tests/test_contracts.py` golden moment has one frame. Schema allows 12; no golden multi-frame sample (CI gap, not runtime break).

### M5 — Developer Mode reset on glasses firmware update

Documented in `RUNBOOK.md` as check-first item — operational, not code.

---

## Recommended Fix Order

Minimal, high-leverage work before deadline:

1. **Ops verification (no code required)**
   - Confirm engine reachable only on Tailnet; public hostname hits read gate only.
   - Confirm `SMALL_CUTS_ENGINE_URL` on HF Space points at read-gate HTTPS origin.
   - Warm engine: one throwaway moment before glasses demo.
   - Live checklist: Tailscale on iPhone, `ws://mac-studio:8077`, Bluetooth route to glasses, Developer Mode on.

2. **Decode-first-frame-only on critical path** (smallest code fix for C1)
   - Decode frame 0 → narrate → TTS → send `SceneAudio`.
   - Decode remaining frames + write `clip.mp4` in library `store()` thread (already async after audio).
   - Expected win: remove 11 JPEG decodes from glasses latency.

3. **One multiframe rehearsal**
   - Extend `dress_rehearsal.py` or manual test: send 3–12 frames with `ts_offset_ms`, assert `clip_url` served through **read-gate URL** (not just localhost engine).
   - Open HF Space in phone Safari; confirm `<video>` plays and audio syncs.

4. **Demo script adjustment**
   - Skip relying on `session_start` for POV video; wait ≥5 s after stream start or manual-fire after moving.
   - Plan for ~6 s warm e2e per moment; avoid rapid-fire scene changes while engine is busy.

5. **Optional hardening if time permits**
   - Reuse a shared `httpx.AsyncClient` in read gate (I5).
   - Set `gate.suppressed = true` at start of `sendMoment` until ack/status (I3).
   - Filter public `list_scenes` to `visibility=public` only (post-hackathon if demo is single-user).

---

## Deferred Work

- Visibility enforcement + auth on reads (`share_token`, owner scoping).
- SSE-driven viewer instead of 2 s polling.
- Golden multi-frame contract sample + e2e test through public gate.
- Rate limiting / auth on read gate.
- CORS hardening (not required for `<audio>`/`<video>` playback today).
- Parallel encode suppression on iOS beyond D8 status frames.
- `PATCH` visibility via Tailnet-only admin path if publish controls are needed on Space.

---

## Confidence And Unknowns

| Area | Confidence | Unknowns |
|------|------------|----------|
| Contract schemas (12 frames, `clip_url`) | **High** | None material |
| iOS ↔ engine WS (single/multi frame) | **Medium** | Real 12-frame payload over Tailnet latency/size; live smoke skipped |
| Glasses→ear latency with 12-frame decode | **Medium** | No benchmark on `9f7ceea`; prior rehearsal was single-frame (~6.3 s warm p50) |
| HF Space POV clip playback | **Medium** | No test through public read-gate URL + tunnel; MP4 codec on host assumed |
| Read-gate write blocking | **High** | Path allowlist tested; proxy behavior not integration-tested |
| Read privacy | **High** (not enforced) | Intentional for v1 demo? |
| Production ops (tunnel, gate process, env vars) | **Low** | Not in reviewed source; must be verified manually |
| Cold start | **High** (documented) | Whether demo includes engine restart |

**Overall demo readiness:** The POV clip design is sound and contract-aligned. The main correctness risks are **(1)** multiframe decode on the narration critical path, **(2)** unverified e2e path from 12-frame iOS capture → read gate → HF viewer, and **(3)** ops dependency on Tailnet isolation + warm engine + first-moment still-image expectation. With a warm engine, a 5 s buffer fill before the hero moment, and a quick multiframe rehearsal through the public URL, the demo should hold; without those verifications, POV video on the Space is the most likely visible gap.
