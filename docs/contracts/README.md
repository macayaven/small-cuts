# Inter-team contracts

These schemas are the **only coupling** between the three teams
([product architecture](../product/architecture.md)). Each team optimizes
freely inside its boundary; the contracts keep the system aligned.
Current contract set: **1.1.0** (post adversarial review — Codex + Gemini,
2026-06-12).

| Contract | Producer → Consumer | Schema |
|---|---|---|
| MomentEnvelope | Mobile → Engine | [moment.schema.json](moment.schema.json) |
| ControlFrame (ack / error / status) | Engine → Mobile | [control.schema.json](control.schema.json) |
| SceneAudio | Engine → Mobile | [scene-audio.schema.json](scene-audio.schema.json) |
| NarratedScene | Engine → Viewer + Library | [narrated-scene.schema.json](narrated-scene.schema.json) |

## Transport bindings

### Mobile ↔ Engine — one WebSocket per wearing session (`ws://<engine>/v1/session`)

- Client sends `MomentEnvelope` text frames. Engine answers **every**
  envelope with a `ControlFrame{kind=ack}` whose `result` means *admission*:
  `accepted` (in the pipeline), `duplicate` (idempotent resend ignored),
  `rejected` (validation failure — never retry unchanged),
  `dropped_coalesced` (replaced by a newer moment, D8).
- Completion is signaled by `SceneAudio` (success) or
  `ControlFrame{kind=error}` (stage, code, retryable) — the app is never
  blind to downstream failures.
- **Backpressure (D8):** engine emits `ControlFrame{kind=status}` with
  `busy`/`queue_depth`; apps suppress the gate while `busy`. Engine policy:
  queue depth ≤ 1, **coalesce-to-newest** (a queued, un-started moment is
  replaced by a newer arrival and acked `dropped_coalesced` — narrating
  stale moments is worse than skipping them).
- **Reconnect & idempotency:** after reconnect the app may resend envelopes
  that never received an ack; the engine dedupes on `moment_id`. Chronology
  authority is `captured_at`, not arrival order; `prev_moment_id` and `seq`
  are advisory.
- **Playback (D9):** the app never overlaps clips; a clip whose `play_by`
  passed before playback starts is dropped (engine default: `created_at`
  + 60 s).

### Engine → Viewer — SSE (`GET /v1/scenes/stream`)

- Emits `NarratedScene` with the SSE `id:` field set to `seq`; clients
  resume with `Last-Event-ID`. Pipeline failures appear as
  `ControlFrame{kind=error}` events on the same stream so the timeline
  stays honest.
- Library reads: `GET /v1/scenes?session=…&visibility=…` (same schema,
  ordered by `captured_at`).
- **Visibility mutations** (the viewer's only write — metadata, never
  media): `PATCH /v1/scenes/{scene_id}` body
  `{"visibility": "private"|"shared"|"public"}`. Auth + `share_token`
  enforcement specs land with the library milestone (#30); v1 engines are
  single-user on the tailnet, and `owner`/`share_token` fields are already
  reserved in the schema so sharing is additive.
- Media URLs inside `NarratedScene.media` resolve against the engine origin.

## Session context (D5)

The engine owns session memory. Capture apps contribute only what is inside
`MomentEnvelope.context` + the chronology chain (`captured_at`,
`prev_moment_id`). The prompt builder may use: recent narrations for the
session, time-of-day (via `tz_offset_min`), `location_label`, `user_hint`,
gate trigger. Token budget for injected context: ≤ 400 tokens (inference
team owns the selection policy — #20).

## Enforcement

1. **Schemas are the source of truth.** Implementation types are generated
   from or validated against them — never hand-drifted.
2. **Golden samples in CI.** Each producer keeps at least one golden sample
   per message type; `tests/test_contracts.py` validates all samples
   against these schemas on every push (jsonschema).
3. **Versioning — strict + lockstep.** Schema version lives in the `$id`
   path (`…/contracts/<semver>/…`). Schemas are strict
   (`additionalProperties: false`) and live in ONE repo, so any field
   change — additive included — is a **lockstep minor bump**: schemas,
   golden samples, and all consumers update in the same `contract-change`
   PR. Tolerant-reader semantics only become relevant if schemas are ever
   vendored into separate repos; until then, drift fails CI loudly.
   Breaking shape changes (removals, type changes, transport semantics)
   are a major bump + migration note.
4. **Change process.** Contract changes are PRs labeled `contract-change`,
   reviewed by the orchestrator, announced in the KB
   (`10-projects/small-cuts/`) before merge.
