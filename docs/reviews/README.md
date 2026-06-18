# Design reviews

These are the design records behind notable decisions in Small Cuts. They exist because I run
non-trivial changes as a **directed multi-model process** rather than a single pass:

1. **Pose a brief** — frame the problem, the constraints, and the invariants.
2. **Research** — fan out across the relevant docs/codebase to build a shared evidence base.
3. **Fan out for diverse takes** — several independent models each produce a proposal without seeing
   the others, so I get genuinely different angles instead of one model agreeing with itself.
4. **Adversarially verify** — a separate pass tries to *break* the front-running idea (measure the
   costs, fact-check the load-bearing claims) before anything is committed.
5. **Ratify the design-of-record** — I make the call, write it down, and only then implement.

I'm the author and director throughout: I set the brief, weigh the trade-offs, and own the result.
The models are leverage for breadth and rigor — not a substitute for the decision.

## Index
- [`2026-06-17-player-redesign/`](2026-06-17-player-redesign/) — replacing the hand-rolled video
  player with a native, event-driven one. The clearest example of the loop above:
  [`02-consensus.md`](2026-06-17-player-redesign/02-consensus.md) is the verified design-of-record,
  and `proposals/` holds the five independent proposals it was synthesized from. Notably, the
  adversarial pass *overturned* the initial instinct (mux everything) with measured evidence.
