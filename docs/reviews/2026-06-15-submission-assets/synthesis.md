# Submission Assets Review Synthesis - 2026-06-15

Reviewers: Claude, OpenCode, Agy, Agent.

Agent returned an empty report. Claude produced a plan-style summary instead of the assigned full
file. OpenCode and Agy returned actionable reports. The consensus was still clear enough to act.

## Accepted Improvements

- Tighten README language from "real-time/chunk-by-chunk/intra-clip coherence" to the actual v1:
  one selected first-person frame produces one grounded line, while the Space replays a short POV
  clip with synced media.
- Reframe authorship so Carlos is visibly the architect and lead, with AI tools credited as an
  accelerated development toolchain.
- Mark demo video and social links as pending rather than implying those gates are already done.
- Clarify that the seeded hero library is curated from real glasses footage, while live captures
  write model-generated cuts into the same theater.
- Add a Field Notes sentence making the Cloudflare tunnel a hackathon-time transport, not the
  production security model.

## Rejected Suggestions

- Do not migrate to Modal, rewrite the player, change contracts, change storage, or switch away
  from the known-good quick tunnel before submission.
- Do not replace the verified five hero scenes.
- Do not open public write/session routes.

## Open Questions

- Field Notes remains binary: publish the HF blog and verify `200`, or remove
  `achievement:fieldnotes` before the final analyzer/submission.
- Demo video and social post links remain manual until Carlos records/posts them.

## Spec Or Code Changes

- Public copy only: `README.md` and `docs/field-notes-small-cuts.md`.
- No runtime code or contracts changed.

## Reviewer Consensus

The product story is strong and distinctive, but submit safety depends on honest copy and final
manual artifacts. The public Space must stay on the verified CPU viewer + Cloudflare read-gate
path, and final submission should avoid new architecture work.

## Residual Risks

- The current quick tunnel is ephemeral.
- The public hero library is runtime state under `/private/tmp`; if the Mac reboots, it must be
  restored before judging.
- Physical e2e, human audio click smoke, Field Notes publication, demo video, social post, README
  link redeploy, and final analyzer remain pending.
