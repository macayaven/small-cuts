# CLAUDE.md — `docs/contracts/` (inter-team contracts, v1.1.0)

Module-local notes for the **contract schemas** — the *only* coupling between the space, mobile, and
inference teams, and the **source of truth** for message shapes. Rationale + history are in the **KB**
(`10-projects/small-cuts/contracts/` and `…/architecture/`).

## The four message types
- **MomentEnvelope** (mobile → engine) — `moment.schema.json`: frames (≤1024px) + gate + context.
- **ControlFrame** (engine → mobile) — `control.schema.json`: `ack`
  (`accepted|duplicate|rejected|dropped_coalesced`), `error` (stage/code/retryable), `status`
  (busy/queue_depth).
- **SceneAudio** (engine → mobile) — `scene-audio.schema.json`: audio + `play_by` freshness deadline.
- **NarratedScene** (engine → viewer & library, SSE) — `narrated-scene.schema.json`: `seq` (resume),
  `captured_at`, narration, media URLs, `visibility`.

## Enforcement
- Strict JSON Schema (`additionalProperties: false`) + **golden samples** in `tests/test_contracts.py`,
  validated on every push (CI). Run locally: `uv run pytest tests/test_contracts.py`.

## Change process (the one rule that matters)
- Bump the schema `$id` (semver) **+** golden samples **+** ALL consumers (Python engine/viewer +
  iOS `MomentBuilder`/`EngineSessionClient`) **in ONE PR**. Additive = **minor, lockstep**; breaking =
  **major + migration note**.
- Label the PR **`contract-change`** ⇒ **orchestrator review required**.
- The ≤6 s streamed-audio stretch is a **future MAJOR** version (cross-team), not a v1 toggle.
