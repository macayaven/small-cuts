# Small Cuts — Architecture

The single architecture-of-record. Small Cuts turns first-person moments into grounded, deadpan,
*spoken* narration using only **small (≤32B) open models** — no cloud LLM in the loop. Three paths
produce the **same finished artifact** (a short POV clip + generated title + Kokoro voice + synced
captions + library tile + source badge):

```
LIVE (private)   Ray-Ban Meta glasses ─frames→ iPhone app ─WS→ home engine (Qwen3-VL-8B + Kokoro)
                                                                      │ after Cut!: SceneAudio
                                                 ◄────── spoken in-ear (~6s warm) ──────┘
                                                                      └─ finished cut ─→ HF relay bucket

UPLOAD (judges)  browser ─short video→ Modal GPU app (Qwen3-VL-8B + Kokoro) ─→ finished cut ─→ relay bucket

VIEW (public)    HF Space (Gradio 6, CPU-basic) ──reads finished scenes── HF relay bucket  → theater + library
```

The **Space never runs inference** — it is the view platform + library, reading finished scenes from
an HF relay bucket. Judge uploads dispatch to a private **Modal** GPU app. The live in-ear loop runs
on a home node (Mac Studio) over the tailnet. (Earlier docs said "the Space is the product / inference
runs in the Space" — that is no longer true.)

## Shipped state vs. planned
- **Shipped:** batch narration (upload → frame pick → Qwen3-VL-8B → title + Kokoro TTS); the Gradio
  view platform + library + relay; the Modal judge-upload path; the iOS glasses capture app with a
  wired **post-Cut** in-ear loop (tap `Cut!` → one complete clip is spoken in-ear).
- **Planned (not shipped):** **rolling / continuous** in-ear narration *during* the moment. This is
  not a toggle — at the current model's speed a single moment produces ~35–44 s of audio per ~3 s of
  video, so the ear can never catch up to a live stream. Post-Cut, one-complete-clip narration is the
  shipped design; rolling narration needs a faster model/prompt and a future MAJOR contract version.

## Latency-of-record (the live loop)
After the wearer taps **`Cut!`**, the round trip is narration + TTS + WS hops. Measured / budgeted:

| Stage | Number |
|---|---|
| Phone: select + encode + send | ≤ 1.0 s (UNMEASURED phone-side; `sent_at`/`latency_ms` exist to attribute it) |
| Engine: narration (warm llama.cpp on Metal) | 2.0–4.2 s measured |
| Engine: TTS (warm Kokoro) | ~3.6 s measured |
| Return + playback start | ≤ 0.5 s |
| **End-to-end, warm p50** | **~6 s** (budget ≤ 10 s; rehearsal e2e p50 6321 ms) |
| End-to-end p90 (queue / cold worker) | ≤ 15 s |
| Cold (first moment after engine boot; first-ever run = GGUF download) | ~17 s (up to ~1 min) |

A ~6 s voice is **retrospective by design** — the deadpan-omniscient narrator comments on the moment
just past, the gate keeps moments sparse, and the captions mirror it line-for-line. `play_by` (default
`created_at + 60 s`) is the D9 *drop-stale* freshness guard, **not** the latency budget.

## The four viewer modes (env-selected, `viewer.py`)
Build-time, by precedence `ENGINE_URL > RELAY_BUCKET > local`:

| Mode | Env | What it is |
|---|---|---|
| **Engine** | `SMALL_CUTS_ENGINE_URL` | Polls a home/engine `GET /v1/scenes` (local/ops mode). |
| **Pure relay** | `SMALL_CUTS_RELAY_BUCKET` (no upload) | Viewer-only; reads a finished-scene manifest + media from an HF bucket. The safe public posture. |
| **Hybrid relay + upload** | `SMALL_CUTS_RELAY_BUCKET` + `SMALL_CUTS_ENABLE_UPLOAD_SANDBOX=1` | Relay library + a Modal-backed "try it" upload for judges. |
| **Upload (local)** | neither set | Local "try it" dropzone with the mock pipeline; dev/fallback. |

## The real-time loop (one narrated moment)
```mermaid
sequenceDiagram
    autonumber
    participant G as Glasses (DAT)
    participant M as iPhone app
    participant E as Engine (home node)
    participant V as Viewer (Gradio)
    participant L as Library (relay)
    Note over G,M: camera session; wearer taps Action! … Cut!
    G->>M: video frames (SDK callback)
    M->>M: frame select + downscale ≤1024px
    M->>E: MomentEnvelope (WS /v1/session) on Cut!
    E->>E: prompt build → narrate (llama.cpp) → TTS (Kokoro)
    E-->>M: SceneAudio (WS) — one complete voice clip
    M->>G: play in ear (BT speakers)
    E->>L: publish finished NarratedScene → HF relay bucket
    Note over V,L: Space reads the relay → theater + library
```

## Decisions (D1–D10)
- **D1** — Unit of work is a **gated Moment, not continuous video**; the phone selects/downscales
  frames and emits discrete `MomentEnvelope`s.
- **D2** — Transport is **one bidirectional WebSocket per session** (phone ↔ engine, over the tailnet).
- **D3** — The engine lives on the **home node** (Mac Studio), **llama.cpp-first** (warm narration
  2.0–4.2 s on Metal). The Space is the public shell, not the engine.
- **D4** — Audio returns as **one complete clip per scene** (v1). Streamed TTS is a future MAJOR
  contract version (needs mobile buffered playback), not an engine toggle.
- **D5** — **Session context lives engine-side; v1 scope is intra-clip** (no cross-clip memory). The
  phone sends only moment metadata; the engine owns prompts.
- **D6** — **Library is engine-side storage** (filesystem media + sqlite index); entries are
  `NarratedScene`s with visibility `private | shared | public` (default private). The viewer reads;
  it never writes media.
- **D7** — **Viewer subscribes over SSE**; its only write is visibility via `PATCH /v1/scenes/{id}`.
- **D8** — **Backpressure: queue depth ≤ 1, coalesce-to-newest**; every envelope is acked at
  admission (`accepted | duplicate | rejected | dropped_coalesced`).
- **D9** — **Playback freshness**: `SceneAudio` carries `play_by` (default `created_at + 60 s`); the
  app never overlaps clips and drops any whose deadline passed. Errors are first-class frames.
- **D10** — **Capture and publish are separated.** The glasses/phone render nothing public; all
  publishing + visibility happens in the Space/relay. Glasses-origin cuts (`source="glasses"`) are
  published from already-generated local artifacts after `Cut!`, never from the wearable.

## Models & contracts
- **Narrator:** `Qwen/Qwen3-VL-8B-Instruct` (8B, well under the 32B cap; chosen over Qwen2.5-VL-7B on
  a dual-judge eval). **Voice:** **Kokoro** (small open TTS). **No cloud LLM/TTS** anywhere.
- **Backends** (`SMALL_CUTS_BACKEND`): `mock` (CI/tests) · `transformers` (Qwen3-VL-8B) · `llama_cpp`
  (GGUF via the `llama-server` binary). TTS via `SMALL_CUTS_TTS_BACKEND` (`mock` | `kokoro`).
- **Wire contracts** ([`docs/contracts/`](contracts/README.md), v1.1.0, runtime-validated): four
  messages — `MomentEnvelope`, `ControlFrame`, `NarratedScene`, `SceneAudio`. JSON Schemas are the
  source of truth; CI validates golden samples; lockstep-minor versioning, `contract-change` PRs.

See [`docs/setup.md`](setup.md) to run it, the root [`CLAUDE.md`](../CLAUDE.md) for commands, and the
module `CLAUDE.md` files for space / engine / contracts / ios specifics.
