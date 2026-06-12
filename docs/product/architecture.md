# Small Cuts — Product Architecture (the real-time loop)

> Scope: the **product** (post-hackathon #29). The hackathon Space remains
> described by [docs/architecture.md](../architecture.md) — it is the public
> demo shell of this architecture, with uploads standing in for the live
> glasses stream.

## Current state (2026-06-12)

Batch pipeline, fully working: photo/clip upload → frame pick → Qwen3-VL-8B
narration (ZeroGPU or llama.cpp) → title card + on-demand Kokoro TTS. Live on
the hackathon Space. **No streaming, no session memory, no library, no mobile
app yet** — those are exactly what the three teams build.

## Components & teams

| Component | Owner | Optimization goal |
|---|---|---|
| **Capture apps** (iOS/Android + Meta Wearables DAT) | Team Mobile | minimize signal sent, maximize moment quality, real-time delivery |
| **Narration engine** (home node: llama.cpp + Kokoro + session context) | Team Inference | prompt + session context + frames → Wes-Anderson-grade voice-over; max quality, min latency |
| **Viewer platform** (Gradio app: live view + library) + hackathon Space | Team Space | feel like a reference live-streaming platform (#28) |

Coordination: contracts below are the only coupling. Each team optimizes
freely inside its boundary; **contract changes are PRs labeled
`contract-change` and require orchestrator review**.

## The temporal diagram

One narrated moment, end to end ("scene-gated discrete pipeline", see D1):

```mermaid
sequenceDiagram
    autonumber
    participant G as Glasses (DAT)
    participant M as Mobile app
    participant E as Engine (home node)
    participant V as Viewer (Gradio)
    participant L as Library

    Note over G,M: continuous camera session (DAT stream)
    G->>M: video frames (SDK callback)
    M->>M: scene gate + frame select + downscale ≤1024px
    M->>E: MomentEnvelope (WS) — frames + context metadata
    E->>E: session context → prompt build
    E->>E: narrate (llama.cpp, warm 2–4.5s)
    E->>E: TTS (Kokoro, ~3.5s)
    E-->>M: SceneAudio (WS) — voice-over
    M->>G: play in ear (BT speakers)
    E-->>V: NarratedScene event (SSE) — live view
    E->>L: append NarratedScene (visibility: private)
    Note over V,L: user revisits in library → share / make public / go public-live
```

**Latency budget v1** (gate fires → voice in ear), measured numbers in
parentheses:

| Stage | Budget |
|---|---|
| Phone: gate + select + encode + send | ≤ 1.0 s |
| Engine: narration, warm llama.cpp on Metal | ≤ 4.5 s (measured 2.0–4.2 s) |
| Engine: TTS, warm Kokoro CPU | ≤ 3.5 s (measured 3.6 s) |
| Return + playback start | ≤ 0.5 s |
| **End-to-end v1 target** | **≤ 10 s** |
| Stretch (sentence-pipelined narration→TTS, streamed audio) | ≤ 6 s |

The stretch path is Team Inference's optimization space — it changes no
contract shape (the `audio.format` field already admits chunked delivery).

## Decisions (status: adopted unless challenged via PR)

- **D1 — Unit of work is a gated Moment, not continuous video.** The phone
  runs the cheap signal processing (scene-change gate — #15's M3.5 work
  becomes mobile-side; frame selection; downscale to ≤1024px longest side,
  matching the verified Qwen-VL vision-token constraint) and emits discrete
  `MomentEnvelope`s. Rationale: bandwidth (the "optimize signal sent" goal),
  battery, and the validated single-frame narration strategy. Continuous
  streaming later = same contract at higher envelope frequency.
- **D2 — Transport is one bidirectional WebSocket per session** (phone ↔
  engine, over the tailnet): envelopes up, audio + acks down. WebRTC only
  becomes interesting if D1 flips to raw media. Team Mobile may challenge
  with measurements.
- **D3 — The engine lives on the home node (Mac Studio), llama.cpp-first.**
  Measured: warm narration 2.0–4.2 s on Metal — faster than ZeroGPU warm.
  The HF Space is the public demo shell, not the product engine.
- **D4 — Audio returns as one complete clip per scene (v1).** Kokoro clips
  are 5–15 s; streaming TTS buys ~2 s at real complexity cost. The contract
  carries `format` so chunking can land later without a breaking change.
- **D5 — Session context lives engine-side.** The phone sends only moment
  metadata (time, optional location label, optional user hint); the engine
  owns session memory (recent narrations, day timeline → #20) and prompt
  construction. Mobile never sees prompts; Inference never sees raw streams.
- **D6 — Library is engine-side storage** (filesystem media + sqlite index),
  entries are `NarratedScene`s with visibility `private | shared | public`
  (default private). The viewer reads; it never writes media.
- **D7 — Viewer subscribes over SSE** to the engine's scene stream; library
  entries and live events share the same `NarratedScene` schema. "Public
  live" later = the same stream behind an auth/visibility check.

## Contracts

Defined and enforced in [docs/contracts/](../contracts/README.md):

1. **MomentEnvelope** (Mobile → Engine) — `moment.schema.json`
2. **NarratedScene** (Engine → Viewer & Library) — `narrated-scene.schema.json`
3. **SceneAudio** (Engine → Mobile) — `scene-audio.schema.json`
4. **Session context spec** (engine-internal, but the metadata mobile must
   supply is part of MomentEnvelope) — in the contracts README

Enforcement: JSON Schemas are the source of truth; every team's CI validates
its golden samples against them (`tests/test_contracts.py` pattern); schemas
are semver'd in their `$id`; breaking changes bump major and require a
migration note in the PR.
