# Small Cuts — Product Strategy

## Essence of the experience

In *The Invention of Lying*, the world is narrated by people who can only say
what is true — and the comedy and tenderness come from hearing ordinary moments
described with omniscient, cinematic certainty. **Small Cuts gives you that
narrator.** You show it a moment of your life; it tells you what kind of scene
you are actually in.

The emotional target is the gap between how a moment *feels* from inside and how
it *reads* from outside: a narrator that is observant, specific, a little too
honest, and unmistakably cinematic.

## How the inspiration translates into UX

1. **You bring a moment** — a photo or short clip from your phone, webcam, or
   Ray-Ban Meta glasses footage.
2. **You choose a director** — narration styles are *directors' cuts*: Noir
   Detective, Nature Documentary, Trailer Voice, Deadpan Omniscient
   (the *Invention of Lying* default), Telenovela, Wes Anderson Symmetrist…
3. **The narrator speaks** — a small VLM looks at the scene and writes 2–4
   sentences of narration grounded in what is actually visible; a small TTS
   model performs it; the app renders a title card so the result is shareable.
4. **One tap to re-cut** — same moment, different director. The re-cut is the
   delight loop and the social loop ("show a friend" is literally the Track 2
   judging criterion).

## What the Director's Cut trajectory gets right

- The core concept (cinematic POV narration of lived moments) is original and
  emotionally strong — worth keeping intact.
- The pivot toward Gradio (`wearables-gradio-poc`) correctly read the hackathon
  rules: the judged artifact must be a Gradio Space.
- The local-model option (Qwen3-Omni) was prescient: it is exactly what the
  "Off the Grid" quest rewards.

## What it gets wrong / under-exploits (unverified where noted)

- **iOS companion app is unjudgeable.** Judges run a Space; a Swift app for
  Ray-Ban Display can't be evaluated and consumes the remaining 4 days.
- **Gemini Live (cloud) breaks the rules' spirit and the best quests.**
  Cloud narration forfeits "Off the Grid" and weakens the small-model story.
- **Glasses-as-infrastructure is fragile.** Device pairing on stage/video is a
  demo killer; glasses should be a *capture source*, not a dependency.
- (Unverified — peer notes unreachable from this environment: the exact state
  of `wearables-gradio-poc` may already address some of this.)

## Improved concept: why Small Cuts can beat the original

- **Zero-friction for judges:** open the Space, drop any photo, get narrated.
  No hardware, no account, no pairing.
- **Rule-maximal:** ≤32B local models inside the Space → eligible for Off the
  Grid, Llama Champion, Tiny Titan, Off-Brand, Field Notes on top of Track 2.
  Quests are scoring multipliers; the original trajectory could claim almost none.
- **The glasses still star** — in the demo video: Carlos walks through Madrid
  wearing Ray-Ban Metas, the footage flows into the Space, and his day comes
  back narrated. Emotional wow preserved, fragility removed.
- **Small-model fit is honest:** scene → short narration is a task a 2–8B VLM
  genuinely does well; nobody needs GPT-class weights to be wry about your coffee.

## Core demo flow (the video, ≤90s)

1. POV clip from Ray-Ban Metas: ordinary morning moment (coffee, street, desk).
2. Cut to the Space: frame dropped in, "Deadpan Omniscient" selected.
3. Narration appears word-by-word and is *spoken*: specific, true, funny.
4. Re-cut as "Noir" → same moment, new genre. Show a second moment.
5. Closing card: "Every model under 32B. Everything runs in this Space."

## Minimum lovable submission (must ship by June 14)

- Space under `build-small-hackathon/` org: image → styled narration → TTS audio
  → shareable title card. 6 director styles. Custom cinematic theme.
- Local VLM (≈2–8B) + local TTS, ZeroGPU with CPU fallback.
- Demo video + social post + README.

## Stretch (only after MLS is live)

- Short-clip input (sample frames → narrate the sequence as a scene).
- "Day reel": multiple moments stitched into one narrated cut.
- **Well-Tuned:** LoRA fine-tune of the narrator voice on a style corpus,
  published on the Hub.
- llama.cpp runtime path for the Llama Champion badge (if VLM+GGUF is stable).

## Riskiest assumptions

1. A ≤8B VLM produces *specific, grounded* narration (not generic captions) —
   prompt + few-shot needs early validation.
2. ZeroGPU latency stays demo-acceptable under load; CPU fallback is tolerable.
3. TTS quality carries the "performed narrator" feeling at small size.
4. Space-under-org submission mechanics are as simple as they look (unverified).

## First implementation milestones

| # | Milestone | Target |
|---|---|---|
| M0 | Repo bootstrap: CI, lint, tests, docs, mock-backend Gradio app runs | **done in this session** |
| M1 | Real VLM narration end-to-end locally (eval 2–3 candidate models, pick one) | June 12 |
| M2 | TTS + title card + custom theme (Off-Brand) | June 13 |
| M3 | Space live under org (ZeroGPU + CPU fallback), llama.cpp path decision | June 13–14 |
| M4 | Demo video filmed/cut, social post, Field Notes blog draft | June 14 |
| M5 | Submit + buffer day | June 15 |
