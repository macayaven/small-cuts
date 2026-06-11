---
projectId: directors-cut
id: 2026-06-11-directors-cut-peer-synthesis-for-small-cuts
status: PARTIAL — written from a cloud session without access to the canonical KB
---

# Director's Cut — Onboarding Synthesis for Small Cuts (2026-06-11)

## ⚠️ Evidence limitation (read first)

This synthesis was produced in a **cloud Claude Code session**, not on the Mac
Studio. The following prescribed sources were **unreachable** and are NOT
reflected below:

- `.knowledge/INDEX.md`, `00-guidelines/agent-operating-contract.md`,
  `30-resources/cli-app-setup.md`, `10-projects/directors-cut/*` (no `.knowledge/`
  dir, no `knowledge_base-*` MCP tools in this environment)
- Peer notes from Codex and Claude (live only in the KB above)
- Source code of `macayaven/directors-cut` and `macayaven/wearables-gradio-poc`
  (GitHub access in this session is scoped to `macayaven/small-cuts` only)

Everything below comes from: GitHub repo metadata (names/descriptions/dates),
Carlos's own emails (Gmail), the Notion workspace (SparkClaw lineage), and the
official hackathon sources. Items that could not be verified are labeled
**unverified**. **A Mac Studio session must re-run the prescribed KB reads and
amend this note.**

## 1. What Director's Cut is

A cinematic POV narration product for Meta Ray-Ban (Display) glasses: an
intelligent narrator that watches what you see and produces film-style
commentary. Evidence: repo `macayaven/directors-cut` (created 2026-05-18) —
"iOS companion for Meta Ray-Ban Display glasses — Director's Cut cinematic POV
narration (Gemini Live cloud / Qwen3-Omni local)".

## 2. Intended emotional/product experience

The omniscient narrator characters of *The Invention of Lying*: lived moments
transformed into meaningful, contextual, cinematic commentary (per Carlos's
mission statement for this project).

## 3. Hackathon/submission context

**Confirmed:** Build Small Hackathon (Gradio × HF), submissions close June 15,
2026; Gradio Space under org; ≤32B params; Carlos registered (credits email
2026-06-04). **Unverified:** which sidequests Carlos previously "selected";
whether any submission draft exists under the org (none found by name on
2026-06-11); team status with Topi (invited by email 2026-06-03, outcome unknown).

## 4. What Codex contributed

**Unknown from this environment** — Codex's notes live in the canonical KB.
(Repo commit history unreadable here.)

## 5. What Claude contributed

**Unknown from this environment** — same limitation. Notion shows extensive
Claude-authored work on the *predecessor* wearables project (SparkClaw, April
2026): bridge architecture, reply-envelope design, demo-thesis notes.

## 6–7. Peer agreement / conflicts

**Cannot be assessed without the peer notes.** Known objective tension in the
trajectory itself: a native iOS + cloud Gemini Live path vs. hackathon rules
that require a Gradio Space and reward local ≤32B inference. The existence of
`wearables-gradio-poc` (created 2026-06-07, two days after the hack window
opened) suggests the pivot was already understood.

## 8. Current architecture (best available evidence)

- `directors-cut`: Swift iOS companion; narration via Gemini Live (cloud) or
  Qwen3-Omni (local). Details unverified.
- `wearables-gradio-poc`: Gradio proof-of-concept, presumed hackathon pivot.
  Contents unverified.
- Prior art (SparkClaw, Notion-verified): Mac Studio/DGX local-first stack,
  WhatsApp bridge to glasses, vLLM vision on DGX `:8000/v1`, Meta Wearables
  Device Access Toolkit (github.com/facebook/meta-wearables-dat-ios).

## 9. Current implementation state

Unverified beyond repo metadata: directors-cut last pushed ~2026-05-21 (2 open
issues); wearables-gradio-poc created 2026-06-07, no language stats visible.

## 10. Highest-risk assumptions (for any successor)

1. That glasses integration can be load-bearing in a judged demo (it can't —
   judges run the Space).
2. That cloud narration (Gemini Live) is acceptable — it forfeits Off the Grid
   and weakens the small-model story.
3. That a small VLM can narrate with grounded specificity (needs eval, M1).
4. That the remaining 4 days suffice for any native-app work (they don't).

## 11. First 5 actions before coding (executed in this session)

1. ✅ Verify hackathon rules from primary sources (emails + org README).
2. ✅ Inventory actually-reachable knowledge (Notion, Gmail, repo metadata).
3. ✅ Decide track (2) and quest portfolio.
4. ✅ Decide architecture: Space-is-the-product, glasses-as-capture.
5. ✅ Bootstrap `small-cuts` repo with discipline + vertical slice.

## 12. Evidence ledger

- Gmail thread `19e8db3f17a5a437` (2026-06-03, rules + Carlos's forward to Topi)
- Gmail thread `19e9480d1438494e` (2026-06-04, registration confirmed, credits, deadline)
- https://huggingface.co/spaces/build-small-hackathon/README (raw fetch 2026-06-11)
- https://huggingface.co/build-small-hackathon (org stats, no macayaven space found)
- GitHub repo metadata via API search `user:macayaven` (2026-06-11)
- Notion: "SparkClaw Documentation Hub - 2026-04-18" and children (prior project)
