# Submission Assets Review Context - 2026-06-15

Repo: `/Volumes/mac-studio-ssd/workspace/small-cuts`
Branch: `claude/adoring-clarke-49l3uk`

Review target:

- `README.md`
- `docs/submission-assets-2026-06-15.md`
- `docs/field-notes-small-cuts.md`
- `docs/demo-readiness.md`

Current product strategy:

- Final submission remains the live glasses-to-ear plus Hugging Face Space architecture.
- Ray-Ban Meta glasses and iPhone capture first-person image-frame moments.
- Mac Studio runs local Qwen3-VL-8B via llama.cpp plus Kokoro TTS.
- The wearer hears narration in-ear.
- The public Gradio Space is CPU viewer/library only and reads finished scenes through a
  Cloudflare read gate.
- Public write/session paths remain blocked.
- Do not migrate final runtime to Modal or rewrite the player/storage/contracts before submission.

Current verified state:

- Space `build-small-hackathon/small-cuts` is public and running on `cpu-basic`.
- Deployed Space SHA: `3654f4e89f44a994f64332bdea980290f7c2039f`.
- Space metadata includes `track:wood`, `achievement:offgrid`, `achievement:offbrand`,
  `achievement:llama`, and `achievement:fieldnotes`.
- Public read gate returns the five hero scenes and blocks public `/v1/session` and
  `PATCH /v1/scenes/*`.
- Public hero library contains five real first-person glasses clips with MP4, WAV, poster frame,
  and title card.
- Engine has been warmed with a hidden throwaway moment; the warm-up scene was pruned.

Known remaining blockers:

- Field Notes URL is still private/401.
- README still needs final demo video link.
- README still needs final social post link.
- Human click smoke and physical glasses/iPhone e2e remain pending.
- Submission analyzer/tag helper cannot pass until demo/social links and Field Notes are public
  or the `achievement:fieldnotes` tag is removed.

Reviewer task:

Act as an adversarial submission reviewer. Stay read-only. Do not edit files. Do not print or
request secrets. Focus only on correctness, performance/stability claims, narrative strength,
hackathon compliance, and winning/employer signal.

Answer:

1. Is the public story honest and strong enough for final submission?
2. Are any claims overbroad or likely to be penalized?
3. What exact copy or positioning changes would improve win potential without touching runtime code?
4. What must remain blocked/manual until Carlos returns?
5. What should explicitly not be changed before submission?
