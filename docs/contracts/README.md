# Inter-team contracts

These schemas are the **only coupling** between the three teams
([product architecture](../product/architecture.md)). Each team optimizes
freely inside its boundary; the contracts keep the system aligned.

| Contract | Producer → Consumer | Schema |
|---|---|---|
| MomentEnvelope | Mobile → Engine | [moment.schema.json](moment.schema.json) |
| NarratedScene | Engine → Viewer + Library | [narrated-scene.schema.json](narrated-scene.schema.json) |
| SceneAudio | Engine → Mobile | [scene-audio.schema.json](scene-audio.schema.json) |

## Transport bindings (D2/D7)

- **Mobile ↔ Engine**: one WebSocket per wearing session at
  `ws://<engine>/v1/session`. Client sends `MomentEnvelope` text frames;
  engine replies with `SceneAudio` and ack frames `{"ack": "<moment_id>"}`.
- **Engine → Viewer**: SSE at `GET /v1/scenes/stream` (live) and
  `GET /v1/scenes?session=…&visibility=…` (library reads). Both emit
  `NarratedScene` objects.
- Media URLs inside `NarratedScene.media` resolve against the engine origin.

## Session context (D5)

The engine owns session memory. Capture apps contribute only what is inside
`MomentEnvelope.context` + the chronology chain (`prev_moment_id`,
`captured_at`). The engine's prompt builder may use: recent narrations for
the session, time-of-day, `location_label`, `user_hint`, gate trigger.
Token budget for injected context: ≤ 400 tokens (inference team owns the
selection policy — #20).

## Enforcement

1. **Schemas are the source of truth.** Implementation types are generated
   from or validated against them — never hand-drifted.
2. **Golden samples in CI.** Each producer keeps at least one golden sample
   per message type in its repo; `tests/test_contracts.py` validates all
   samples against these schemas on every push (jsonschema).
3. **Versioning.** schema version lives in the `$id` path (`.../contracts/<semver>/...`). Additive optional fields = minor.
   Anything else = major + migration note. Consumers must tolerate unknown
   minor fields IF `additionalProperties` is relaxed in a future major —
   under 1.x, strictness is intentional: drift fails CI loudly.
4. **Change process.** Contract changes are PRs labeled `contract-change`,
   reviewed by the orchestrator, announced in the KB
   (`10-projects/small-cuts/`) before merge.
