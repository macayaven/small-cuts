# Submission Assets Review — opencode (GLM-5.2)

**Scope:** read-only review of `README.md`, `docs/submission-assets-2026-06-15.md`,
`docs/field-notes-small-cuts.md`, `docs/demo-readiness.md`, and the review `context.md`.
No reviewed files were edited; no secrets requested or printed.
**Timestamp:** 2026-06-15, ~09:20 CEST (~14h40m to deadline 23:59 UTC).
**Deployed SHA under review:** `3654f4e89f44a994f64332bdea980290f7c2039f`.

## Verdict

The story is **honest in spirit and strong in framing**, but **not yet submit-safe**. Three
issues will hurt if a judge clicks through: a **broken badge** (`fieldnotes` → 401), a
**narration over-claim** the field notes explicitly contradict, and a **public authorship
line that credits the AI agents over Carlos** (bad for the employer/portfolio goal this
project explicitly targets). All are copy-level fixes — none require touching runtime code.

---

## 1. Is the public story honest and strong enough for final submission?

**Strong enough: yes, with one copy fix.** The "one narrator, no menus, look → mark → hear →
replay" gesture is differentiated and memorable. The private-capture / public-replay split is
the right product boundary and reads as deliberate, not improvised.

**Honest: mostly, with one material drift.** The README's "real-time loop" prose
(`README.md:49-52`) describes the experience as **"chunk by chunk, in near-real-time �[0m
[0m← [0mWrite docs/reviews/2026-06-15-submission-assets/reports/opencode.md
Wrote file successfully.
[0m
Report written to `docs/reviews/2026-06-15-submission-assets/reports/opencode.md`.

**Headline findings:**

1. **Story is strong and honest in spirit, but not yet submit-safe.** The single biggest honesty gap: `README.md:49-52` claims "chunk by chunk … intra-clip coherence … one continuous story," while your own `field-notes-small-cuts.md:76-78` and `submission-assets-2026-06-15.md:41` say v1 is **one frame → one line per moment**. That's the first copy fix.

2. **Overbroad / penalty risks, ranked:** broken `achievement:fieldnotes` badge (401) → compliance table showing TODOs as done → narration over-claim → **authorship line crediting Claude/Codex/GLM/Gemini over Carlos** (directly contradicts your root "credit the user" rule and undercuts the portfolio goal) → fragile judged surface (ephemeral tunnel + sleeping Mac + `/private/tmp` root) → "near-real-time" vs. logged 15.4 s.

3. **Copy changes** (exact replacement strings in §3): v1-honest narration prose, authorship reframe, pending marks in the compliance table, one "model-written, human-curated" library line, "near-real-time" → "local/live". All pure copy; no runtime touched.

4. **Stay manual for Carlos:** fieldnotes publish/strip decision, demo video, social post, single README-links redeploy, human click smoke, physical e2e + iPhone Safari smoke, final analyzer run, and a pre-submit liveness check (Mac awake, tunnel up, tmp root intact).

5. **Do not change:** no Modal/player/contract rewrite, stay on the quick tunnel, keep the five hero scenes + picked thumbnail, keep public writes blocked at 403, keep the audio-clock player, don't touch the deployed SHA except the one README redeploy, keep `cpu-basic` viewer-only.
rop them until the links exist.

3. **Narration over-claim** (see §1) — penalty risk is *credibility*, not a rule violation.

4. **Authorship framing undermines the stated goal.** `README.md:79-80`: *"Implementation is a
   cross-model team effort: **Claude (Opus) orchestrates, Codex (GPT-5.x) implements**, with
   GLM review and a Gemini eval judge."* The root `CLAUDE.md` (and the user-level PR
   guideline) explicitly says *"Credit the user as the author (not Claude)."* This line does
   the inverse in the most visible surface: it lists Carlos only implicitly and hands
   **"implements"** to GPT-5.x. For a project whose goal is *"portfolio-grade,
   door-opening"* signal, this is a self-inflicted wound, and it also invites hackathon
   scrutiny about original human authorship. **Reframe before submission.**

5. **Judged-surface availability is fragile, not overclaimed.** The Space depends on three
   things staying alive unattended: the **ephemeral `trycloudflare.com` tunnel**, the **Mac
   Studio being awake** with the engine running, and the **`/private/tmp/small-cuts-demo-
   library-hero-20260615`** root not being cleared (macOS tmp can be swept on reboot). None of
   this is dishonest — but "polished and alive" can't survive any of the three dying during
   judging. Carlos owns this before final submit (see §4).

6. **"near-real-time" vs. logged 15.4 s.** `demo-readiness.md:53-54` records a **15.4 s**
   warm-up `SceneAudio` (4.4 s on the subsequent Swift smoke). "near-real-time" is defensible
   *warm*, but a cold judge click could land in the 15 s band. agy already flagged this —
   agreed: lead with the warmed number or use "local/live," not "real-time."

Not penalized but worth noting: the `short_description` ("A deadpan narrator for your life,
from small open models.") and the *"Invention of Lying"* framing are on-brand and strong — keep.

---

## 3. Exact copy / positioning changes (no runtime code)

**A. Narration loop — replace `README.md:49-52`** with v1-honest prose. Suggested:
> You walk through a moment; the narrator watches a single selected frame and speaks **one
> grounded, deadpan line** back in your ear while the moment is still *recent past*. The
> finished cut then lands in the Space as a short POV clip with synced captions. (Multi-frame,
> chunk-by-chunk narration is the v2 direction — see Field Notes.)

This converts the overclaim into a *scope statement judges reward*.

**B. Field Notes badge — binary decision, no middle ground.**
- **Preferred:** publish the blog, verify `200`, keep `achievement:fieldnotes`.
- **Fallback (if not published by ~T-2h):** remove `achievement:fieldnotes` from the YAML
  (`README.md:17`), from the compliance bullets (`README.md:99-100`), and from the assets-doc
  checklist. Do **not** leave a claimed badge pointing at a 401.

**C. Authorship — replace `README.md:79-80`** to center Carlos as architect/builder with AI as
tooling. Suggested:
> Built by Carlos Crespo Macaya as architect and lead. Development was accelerated with an
> AI toolchain — Claude (Opus) for design, Codex (GPT-5.x) for paired implementation, GLM for
> review, and Gemini for eval — all of which Carlos directed.

This matches the root convention and *strengthens* the employer signal instead of diffusing it.

**D. Compliance table — mark pending honestly.** In `README.md:88-89`, append "*(pending — link
added before submission)*" to the Demo/Social rows, or remove those two rows until live. Keep
the table itself (it reads well) but don't let it imply done-ness on TODO items.

**E. Seeded library — add one honest line.** After `README.md:67` ("… seeded so the channel is
never empty"), add: *"These five cuts are model-written and human-curated from real glasses
footage."* This pre-empts the "did the model actually write these?" probe and turns the
assets-doc admission (curated seed, mixed audit) into a strength.

**F. Latency adjective — swap "near-real-time" for "local / live"** in `README.md:50` and the
"How it was built" table (`README.md:76`) to stay consistent with §1.A and avoid the 15.4 s
cold-start mismatch.

**G. Stability note for the write-up (optional, Field Notes only).** The field notes already
discuss the read-gate boundary well; consider one sentence acknowledging the quick-tunnel is a
hackathon-time transport so a reader doesn't mistake it for the production design.

These seven are pure copy and can land in a single README + (optional) Field Notes edit +
redeploy. No contract, player, or engine change.

---

## 4. What must remain blocked / manual until Carlos returns

All of these require physical presence, authenticated accounts, or human judgment — do **not**
automate:

- **Field Notes publish** (or the keep/drop-tag decision) — HF blog editor, human call.
- **Demo video** — physical glasses/iPhone capture, on-camera, 60-90 s cut.
- **Social post** — Carlos's account/voice; then paste real link.
- **README link insertion + Space redeploy** — only *after* demo/social/fieldnotes URLs exist.
  Redeploy exactly once, with links; don't churn the SHA.
- **Human click smoke** — confirm audio + video + captions + progress advance together on the
  live Space (`demo-readiness.md:28`, still unchecked).
- **Physical e2e** — glasses → iPhone → in-ear narration → same cut appears in Space
  (`demo-readiness.md:60`).
- **Physical iPhone Safari smoke** (`demo-readiness.md:33`).
- **Final submission analyzer run** — must be last, after all links public and badge decision
  made (`context.md:42-44`).
- **Pre-submit liveness check** — confirm Mac Studio awake, engine warm, `trycloudflare` tunnel
  resolving, and `/private/tmp/small-cuts-demo-library-hero-20260615` intact, immediately
  before the analyzer pass (see §2.5).

---

## 5. What should explicitly NOT be changed before submission

- **No Modal migration, no player/storage/contract rewrite** (`context.md:22`) — out of scope
  for the remaining window.
- **Do not switch off the known-good `trycloudflare.com` quick tunnel** to the named tunnel
  (`small-cuts.carloscrespomacaya.com`) — the named tunnel returned 200/403 on direct smoke but
  left the Space on "Signal lost" (`demo-readiness.md:89-92`). Stay on quick tunnel.
- **Do not change the five hero scenes or the picked thumbnail** ("The Stone Almost Never
  Reaches the Sky") — verified rendering, legible, unusual, already the active latest cut.
- **Do not open public write paths.** `GET /v1/session` and `PATCH /v1/scenes/*` must stay
  `403`; the read-only gate is a feature, not a limitation.
- **Do not change the audio-clock player sync** — file-backed `<audio id="sc-voice">` as master
  clock is the working solution; don't reintroduce Gradio-callback play/pause.
- **Do not add new tags/badges** without a public backing artifact (the fieldnotes lesson,
  generalized).
- **Do not touch the deployed SHA** except for the single README-links redeploy. If a redeploy
  is needed, treat `3654f4e…` as the anchor to return to if anything regresses.
- **Do not drop the `cpu-basic` viewer-only posture** of the Space — inference stays on the
  home node; the Space reads.

---

## Priority fix list (copy-only, pre-submission)

1. Decide fieldnotes: **publish → 200**, or **strip the badge everywhere**. (Blocking.)
2. Reframe `README.md:79-80` authorship to credit Carlos as architect/builder. (Employer signal.)
3. Rewrite `README.md:49-52` to v1-honest one-frame-per-moment narration. (Credibility.)
4. Mark Demo/Social rows pending or drop them in the compliance table (`README.md:88-89`).
5. Add the one-line "model-written, human-curated" note to the hero library section.
6. Swap "near-real-time" → "local/live" in README prose + table.
7. Insert real demo/social links, redeploy README **once**, run the analyzer, do the human
   click + physical e2e smokes.

1–6 are minutes of copy work and survive any demo outcome; 7 is Carlos's manual close.


(exit 0)
