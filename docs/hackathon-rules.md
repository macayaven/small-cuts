# Build Small Hackathon — Rules Summary (verified 2026-06-12)

Facts verified from primary sources:

- **Field Guide** (official): https://huggingface.co/spaces/build-small-hackathon/field-guide
  — read raw `details.md`, `faq.md`, `partner-resources.md`, and the site source
  (`src/lib/data/content.ts`, `src/lib/readme.ts`) on 2026-06-12.
- Organizer message in Discord (relayed by Carlos in issue #22, 2026-06-12).
- Registration emails from `yuvraj@huggingface.co` (2026-06-03/04). Carlos **is registered**.
- Official org: https://huggingface.co/build-small-hackathon (~1,916 members, 365 spaces on 2026-06-12).

## Identity

- **Name:** Build Small Hackathon — "Small Models, Big Adventures"
- **Hosts:** Gradio · Hugging Face. Sponsors: OpenAI, NVIDIA, OpenBMB, Cohere, BFL, Modal, JetBrains.
- **Hack window:** June 5 – June 15, 2026.
- **Deadline (CONFIRMED, organizer in Discord): June 15, 23:59 UTC.**
  The Space must be **public** and **moved under the org** by then — both have been
  forgotten by participants in past events; ours is already created (see below).

## Hard constraints

1. **Model size:** every individual model **under 32B total parameters** (combinations fine;
   each model's *total* — not active — count is what matters).
2. **Platform:** Gradio app hosted as a Space under `build-small-hackathon/` (Docker allowed
   only if the interface is still a Gradio Space).
3. **Demo video:** required — judges must be able to evaluate even if GPU/API limits block a
   live run. Upload to YouTube, as a file in the Space, or anywhere public.
4. **Social post:** required — one post showcasing the app, **linked from the Space README**.
5. **ZeroGPU limit:** max 10 ZeroGPU apps per user (we use 1).

## Submission mechanics (CONFIRMED)

Tracks/badges are claimed via **namespaced tags in the Space README frontmatter**
(`src/lib/readme.ts` is the official parser):

```yaml
tags:
  - track:wood          # or track:backyard
  - sponsor:openai      # sponsor prizes you're entering
  - achievement:offgrid # self-declared badges, verified at judging
```

Checklist from the Field Guide "submitting" page:

- [x] Join the org (macayaven is a member)
- [x] Space exists under the org: https://huggingface.co/spaces/build-small-hackathon/small-cuts
      (public, RUNNING placeholder since 2026-06-12; real app lands in M3, #14)
- [ ] Upload the real app (M3)
- [ ] Demo video — public link (M4)
- [ ] Social post — link it in the Space README (M4)
- [ ] README: track/achievement tags + short write-up of idea, how it was built, tech used
- [ ] Run the **submission analyzer** before the deadline (how-to: youtube.com/watch?v=1iR65sq0HmA)

## Tracks

- **Backyard AI** (`track:backyard`) — practical, problem-solving, daily-life apps.
- **Thousand Token Wood** (`track:wood`) — whimsical, delightful, AI-native fun.

**Small Cuts targets `track:wood`** (tag already on the placeholder Space).

## Bonus achievements (self-declared tags, no prize, verified at judging)

| id | name | our status |
|---|---|---|
| `offgrid` | Off the Grid — no cloud APIs at runtime | ✅ architecture complies (declared) |
| `offbrand` | Off-Brand — custom UI past default Gradio | ✅ custom theme landed in #13 (declared) |
| `llama` | Llama Champion — llama.cpp runtime | ⏳ pending M3 LlamaCppBackend |
| `fieldnotes` | Field Notes — blog post / write-up | ⏳ draft created: hf.co/blog/macayaven/small-cuts-field-notes |
| `sharing` | Sharing is Caring — agent trace on the Hub | 💡 optional: publish the dual-judge eval artifacts as a dataset |
| `welltuned` | Well-Tuned — published fine-tune | ❌ not planned pre-deadline |

These also feed **Bonus Quest Champion** ($2,000 — most bonus criteria met).

## Prized bonus badges

- Off-Brand $1,500 (judged; "gr.Server is your friend" — bar is higher than a theme)
- **Tiny Titan $1,500 — models must be ≤ 4B. We are NOT eligible (8B narrator).**
- Best Demo $1,000 · Best Agent $1,000 · Bonus Quest Champion $2,000 · Judges' Wildcard $1,000

## Sponsor prizes relevant to us

- **OpenAI ($10k pool):** requires **Codex-attributed commits** in the Space history or a
  linked GitHub repo. We genuinely use Codex for implementation but commits are not
  Codex-attributed. If we enter `sponsor:openai`: add Codex attribution to future commits
  and describe the Codex workflow in the README.
- **Modal ($20k credits prize):** requires using Modal for **development or runtime** + a
  README note. FAQ explicitly confirms development-side Modal use (e.g. training/eval)
  **stacks with `offgrid`** — offgrid is about the app's runtime only.
- OpenBMB (MiniCPM) / NVIDIA (Nemotron): different model families — not pursuing.

## Modal credits (participant perk — answered 2026-06-12)

Carlos holds **$250 Modal credits** from registration (plus $20 HF credits, expire
2026-07-31). **No Modal usage is planned in the current architecture**: dev/eval runs on
the Spark + Mac Studio, runtime is ZeroGPU. Using Modal would only matter for the Modal
prize (development-side use is rule-compatible with offgrid), but with a 3-day runway the
recommendation is: ship M3–M5 first; only port an eval/fine-tune job to Modal if time
remains. Redemption status of the credit code: Carlos to confirm.

## Implications for architecture (unchanged, re-verified)

- The **Space is the judged artifact** — Mac Studio / Spark / Tailnet are dev-only.
- `offgrid` + `llama` ⇒ all-local inference inside the Space (ZeroGPU + llama.cpp CPU fallback).
- Ray-Ban Meta glasses are a capture device for the demo video, not runtime infra.
- ZeroGPU is shared: graceful CPU fallback + short inference. 40 min/day quota as org member.

## Open questions

1. Team rules (Topi/nojose registration status) — only matters if co-credit is wanted.
2. Modal credit code redemption status — Carlos.
