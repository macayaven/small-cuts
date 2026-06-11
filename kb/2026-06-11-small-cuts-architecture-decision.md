---
projectId: small-cuts
id: 2026-06-11-small-cuts-architecture-decision
---

# Small Cuts — Architecture Decisions (2026-06-11, post-confirmation)

- **What changed:** Carlos confirmed Track 2 + quest portfolio and added a
  requirement-if-feasible: real-time narration playback **on the glasses**.
  Decisions taken: (a) Live Mode layered design — Bluetooth audio-out through
  the glasses is free once TTS lands (M2); continuous camera-streaming Live
  Mode is stretch M3.5; glasses-camera capture via Meta Wearables DAT is
  post-hackathon. (b) **DGX Spark** is the M1 eval host (CUDA matches ZeroGPU;
  128GB fits all candidate VLMs). (c) `main` created from the bootstrap commit
  so branch protection can be applied; PR-based workflow from here on.
- **Why:** preserves the "hearing your life narrated" magic without making
  hardware load-bearing for judges; keeps the 4-day plan intact.
- **Evidence / commands:** `git push origin claude/adoring-clarke-49l3uk:main`
  (new branch `main` @ 7ca6d57); eval harness `src/small_cuts/eval.py` +
  `tests/test_eval.py` (pytest green); tailnet unreachable from cloud sessions
  (no MagicDNS resolution for `*.tail48bab7.ts.net`) — eval must run locally.
- **Current status:** solo entry confirmed; credits claimed; Carlos verifying
  deadline time + submission mechanics in Discord.
- **Next action:** Carlos runs the eval one-liner on the Spark
  (docs/implementation-plan.md M1) and reruns the branch-protection command.
- **Risks:** continuous Live Mode could eat M2–M4 time — strictly gated behind
  a green M3; scene-change detection quality unknown until prototyped.
