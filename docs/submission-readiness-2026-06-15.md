# Final Submission Readiness - 2026-06-15

Working timestamp: 2026-06-15 05:57 UTC / 07:57 CEST.

Deadline: 2026-06-15 23:59 UTC / 2026-06-16 01:59 CEST. Time remaining at this pass: about 18.0 hours. Recommended live e2e recording window: no later than 2026-06-15 17:59 UTC / 19:59 CEST, preserving a six-hour upload, social, analyzer, and submission buffer.

## Final Recommendation

Submit the current Small Cuts architecture:

- Ray-Ban Meta glasses and iPhone capture first-person frames.
- The private Tailnet path sends moments to the Mac Studio local engine.
- The local engine runs the small-model narrator and Kokoro TTS, stores the finished cut, and returns voice to the glasses path.
- The Hugging Face Space remains the public judged surface: theater, synced replay, captions, title, and library.
- Cloudflare exposes only the public read gate, not the capture/write path.

Do not move the final demo runtime to Modal or the buffered POC. The POC proved a useful v2 direction, especially for pre-buffered clip display and segment orchestration, but the final submission wins more strongly by demonstrating the actual glasses-to-ear loop with local small-model inference and a polished HF Space. Modal should stay available as a backup/research story, not the path of record for the judged demo.

## Judging Positioning

Primary track: `track:wood` / Thousand Token Wood.

Claimed achievements:

- `achievement:offgrid` - local inference and TTS; no cloud LLM/TTS API in the live loop.
- `achievement:offbrand` - custom cinematic viewer rather than default component chrome.
- `achievement:llama` - local live engine goes through `llama.cpp`.
- `achievement:fieldnotes` - field notes link is already in README, but it must be made public
  before final submission.

Do not claim Tiny Titan, because the submission model is 8B, not <=4B.

Target sponsor/attention prizes:

- Best Demo, because the glasses-to-ear-to-Space path is the most memorable proof.
- OpenAI/Wildcard-style attention, because the system is an applied AI product with real-time UX, contracts, local inference, and deployment discipline.
- Employer signal, even if it does not win: the project shows product sense, edge capture, model evaluation, low-latency systems thinking, frontend polish, and pragmatic launch execution.

## Data-Driven Decisions

### Latency

- Keep Qwen3-VL-8B local for the final path. It is the best current balance of narrative quality and judging credibility.
- Modal Qwen2.5-VL-3B was promising when warm, but first-request and model-load behavior make it risky as the final live-demo path.
- Modal Qwen3-VL-8B was too cold-start-heavy in the simple endpoint shape for a same-day architecture migration.
- Warm the local engine before recording and do not use the first live moment as the hero take.

### Resiliency

- Keep the Space CPU viewer-only. It should not load the narrator or TTS stack.
- Keep the Space pointed at a known-good public read gate during the live segment.
- Keep the demo video as the judging fallback if the tunnel, phone, Bluetooth, or glasses path becomes unstable.
- Retain public write blocking: no `/v1/session`, no `PATCH`, no non-GET access through the public hostname.

### Stability

- Do not add SSE, rewrite the player, alter visibility semantics, or migrate storage before submission.
- Keep polling. It is less elegant than streaming but already works through the Space and Cloudflare.
- Avoid rapid repeated marks during the demo; one clean 8-15 second POV moment is stronger than several half-finished cuts.
- Maintain a seeded/public library so the Space is never visually empty.

### Narrative Coherency

- The strongest demo is not just a clever caption. It is a short lived moment where the narration feels like it noticed cause, context, and timing.
- Use one coherent POV clip with visible motion and an obvious situation. The narrator should sound like it is interpreting the moment, not describing isolated frames.
- For the live recording, tap Action!, move for a clear take, then tap Cut! once so the stored cut has enough frames for a real `clip.mp4`.
- Prefer a mundane but legible situation over an impressive but visually confusing one.

### Visual Polish

- Library thumbnails now use a selected POV key frame instead of the title card.
- The key-frame selector prefers exposed, contrasty, detailed, mid-clip frames. This makes the library read like a channel of just-happened clips instead of a grid of generated cards.
- Title generation now comes from the same structured model response as the narration, with deterministic first-clause derivation as a fallback.

## Demo Asset Plan

Record one primary demo take:

1. Open with the glasses/iPhone capture UI connected to the private Tailnet engine.
2. Walk through a motion-rich, readable moment for at least four seconds.
3. Trigger the moment and capture in-ear narration returning.
4. Show the HF Space receiving the same just-happened POV cut.
5. Click play in the Space and show video, voice, captions, progress, generated title, and library thumbnail.

Keep the final video around 60-90 seconds. If time is short, prioritize the proof over explanation: glasses POV, in-ear line, Space replay, synced captions, library thumbnail.

## Remaining Gates

Code gate:

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

Space deploy gate:

```bash
hf upload build-small-hackathon/small-cuts . --repo-type=space \
  --exclude '.git/*' \
  --exclude '.venv/*' \
  --exclude 'ios/*' \
  --exclude 'docs/reviews/*' \
  --exclude 'docs/superpowers/*' \
  --exclude 'docs/submission-readiness-*.md' \
  --exclude '__pycache__/*' \
  --exclude '.pytest_cache/*'
```

Public read gate:

```bash
curl -i "$PUBLIC_ENGINE_URL/v1/scenes?limit=5"
curl -i "$PUBLIC_ENGINE_URL/v1/session"
curl -i -X PATCH "$PUBLIC_ENGINE_URL/v1/scenes/example" \
  -H 'content-type: application/json' \
  -d '{"visibility":"public"}'
```

Expected: scenes read returns `200`; session and PATCH return `403`.

Human Space gate:

- Desktop click advances video, voice, captions, and progress together.
- iPhone Safari click advances the same controls without overflow.
- Library shows real POV thumbnails and generated titles.

Physical e2e gate:

- iPhone app connects over Tailnet.
- Ray-Ban Meta source streams frames.
- Engine returns in-ear narration.
- Same cut appears in the HF Space with `clip.mp4`, `voice.wav`, title, captions, and frame thumbnail.

Submission gate:

- README has final demo video link.
- README has final social post link.
- Field notes link resolves.
- HF metadata still includes `track:wood`, `achievement:offgrid`, `achievement:offbrand`, `achievement:llama`, and `achievement:fieldnotes`.
- Submission analyzer passes.

## Fallback Posture

If physical glasses are unstable, submit the strongest truthful demo using:

- A real glasses-recorded POV clip.
- The local engine generating narration and title from that clip.
- The HF Space displaying it as a finished just-happened cut.
- A clear note that the live capture path exists and is under test, while the judged Space remains the actual product surface.

This fallback still preserves the core employer signal: an end-to-end applied AI system with real media handling, local inference, clean contracts, and a polished public interface.
