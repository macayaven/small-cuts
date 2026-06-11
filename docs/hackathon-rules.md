# Build Small Hackathon — Rules Summary (grounded 2026-06-11)

All facts below were verified on 2026-06-11 from primary sources:

- Official org page: https://huggingface.co/build-small-hackathon (324 spaces, ~1,898 members as of 2026-06-11)
- Official rules: https://huggingface.co/spaces/build-small-hackathon/README (fetched raw README 2026-06-11)
- Registration emails from `yuvraj@huggingface.co` to macayaven@gmail.com
  (2026-06-03 "Registrations Close Midnight", 2026-06-04 "Claim your $270 in credits")
- Carlos **is registered** (received the participant credits email on 2026-06-04).

## Identity

- **Name:** Build Small Hackathon — "Small Models, Big Adventures"
- **Hosts:** Gradio · Hugging Face. Sponsors: OpenAI, NVIDIA, OpenBMB, Cohere, BFL, Modal.
- **Hack window:** June 5 – June 15, 2026. **Submissions close: June 15, 2026.**
  (Exact closing time-of-day/timezone: **unverified** — confirm in Discord/org page. Treat as June 15 00:00 UTC to be safe until verified.)

## Hard constraints

1. **Model size:** total parameters across models used must be **≤ 32 billion**.
2. **Platform:** the app **must be a Gradio app, hosted as a Hugging Face Space under the hackathon org** (`build-small-hackathon/<space>`).
3. **Submission materials:** Space link + **demo video** + **social media post**.
   (Exact required content of video/post: **unverified** — not specified on rules page.)

## Tracks

- **Track 1 — Backyard AI:** "Solve a real problem for someone you actually know."
  Judged on: problem is specific and real · the person *actually used it* ·
  honest fit between problem and the small-model constraint · polish of the Gradio app.
- **Track 2 — Thousand Token Wood:** "Build something delightful that wouldn't exist without AI."
  Judged on: genuinely delightful ("would you show a friend?") · **AI is load-bearing** for
  the experience · originality of concept · polish of the Gradio app.

**Small Cuts targets Track 2.**

## Bonus quests (merit badges)

1. **Off the Grid** — no cloud APIs; the whole thing runs on the model.
2. **Well-Tuned** — uses a fine-tuned model you've published on Hugging Face.
3. **Off-Brand** — custom frontend pushing past the default Gradio look.
4. **Llama Champion** — model runs through the llama.cpp runtime.
5. **Sharing is Caring** — shared agent trace on the Hub.
6. **Field Notes** — blog post or report about what you built.

Claiming mechanism (tags/metadata): **unverified** — confirm on the org page / Discord.

## Prizes (≈$48,000+ total)

- Per track: 1st $4,000 · 2nd $2,500 · 3rd $1,500 · 4th $1,000; Community Choice $2,000.
- Sponsor awards: OpenBMB $10,000 (3 winners/track) · OpenAI $10,000 (3 across all) ·
  NVIDIA 2× RTX 5080 · Modal $20,000 in credits.
- Special awards: Bonus Quest Champion $2,000 · Off-Brand $1,500 · **Tiny Titan 4B+ $1,500**
  (exact definition **unverified**; appears to reward strong results with ~≤4B models) ·
  Best Demo $1,000 · Best Agent $1,000 · Judges' Wildcard $1,000.

## Participant resources (already granted to Carlos)

- $250 Modal credits (code redeemed status: unknown — **Carlos to confirm**), Modal prize category exists ($20k credits).
- $20 HF credits (claim link in 2026-06-04 email; expire 2026-07-31).
- 40 min/day free ZeroGPU as hackathon-org member; beyond quota $1/10 min.
- Community: Gradio Discord `discord.gg/YHECTft87Z`; kickoff livestream recording: youtube.com/watch?v=7otgeJXailY.

## Implications for architecture

- The **Space is the judged artifact**. Mac Studio / DGX Spark / Tailnet services
  cannot be load-bearing for judges — they are dev/eval/preprocessing machinery only.
- "Off the Grid" + "Llama Champion" push toward **all-local inference inside the Space**
  (ZeroGPU or CPU + llama.cpp), which the original cloud-API (Gemini Live) trajectory violates.
- Ray-Ban Meta glasses are a **capture device for the demo video**, not runtime infrastructure.
- ZeroGPU is shared; design for graceful CPU fallback and short inference.

## Open questions (verify before submission)

1. Exact submission deadline time + timezone.
2. Exact demo video / social post requirements.
3. Bonus quest claiming mechanism (tags? README metadata? form?).
4. Team rules (Carlos invited Topi/nojose@gmail.com on 2026-06-03 — did he register?).
5. Tiny Titan award exact criteria.
6. Whether Modal can serve as the Space's inference backend without breaking "Off the Grid"
   (it would — Modal is a cloud API; decide which prize family to optimize).
