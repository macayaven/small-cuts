# Dress rehearsal — 2026-06-12

- Engine: `ws://127.0.0.1:8077` (session `rehearsal-20260612T183149Z`)
- Video: `/Users/carlos/small-cuts-fixtures/videos/IMG_8175.MOV` — 3 gated moments, style `symmetrist`
- Narrator: `Qwen/Qwen3-VL-8B-Instruct-GGUF` via `llama_cpp`
- TTS: `hexgrad/Kokoro-82M`

## Per-moment latency

Engine numbers come from the persisted scene's `engine.latency_ms`; wall is the
client-measured send→SceneAudio round trip (includes WS transfer + queueing).

| # | Narration (first 80 chars) | narration_ms | tts_ms | total_ms (engine) | wall_ms (client) | narration ≤4500 | tts ≤4000 |
|---|---|---|---|---|---|---|---|
| 1 | The man in the foreground holds a glass tilted at precisely the angle a bartende | 9198 | 7657 | 16855 | 16935 | FAIL | FAIL |
| 2 | The man’s hand rests just above his temple, fingers brushing the thick black fra | 3701 | 2022 | 5723 | 5792 | PASS | PASS |
| 3 | The man’s hand hovers over a bottle with a coral cap, its label blurred like a f | 4226 | 2533 | 6759 | 6850 | PASS | PASS |

## Budget comparison (docs/product/architecture.md, Latency budget v1)

Warm = moments after the first; moment 1 pays the llama-server spawn and
Kokoro weight load once per engine process.

| Budget line | Target | Measured (warm max) | Verdict |
|---|---|---|---|
| Narration, warm llama.cpp | ≤ 4500 ms | 4226 ms | PASS |
| TTS, warm Kokoro | ≤ 4000 ms | 2533 ms | PASS |
| End-to-end warm p50 (client wall) | ≤ 10000 ms | 6321 ms | PASS |

Cold first moment: narration 9198 ms, tts 7657 ms, wall 16935 ms (one-time per engine process).
All-moments e2e p50 including the cold first moment: 6850 ms.
Moments narrated: 3/3; audio: 40.8s, 34.4s, 43.9s.

## Full narrations

**Moment 1** (scene `ba7978ea-46e5-4117-a5c6-5f91af79e9b2`):

> The man in the foreground holds a glass tilted at precisely the angle a bartender might approve, its rim catching the amber glow of the single, perfect circle of light above. Behind him, the bar’s menus—Cocktails and Shots—hang like miniature, illuminated maps, their text sharp against the dark wood. A neon sign to the left, glowing in a warm, slightly garish red, reads “LOVE, LOVE WILL APART” in a font that looks like it was cut from a child’s coloring book. The scene is framed with the quiet symmetry of a still life: the man’s glasses, the glass, the light, the menus, the sign—all arranged with the careful, slightly off-kilter precision of a Wes Anderson storyboard.

**Moment 2** (scene `20f0dfb0-b2c7-4de5-912d-a1da648abdaf`):

> The man’s hand rests just above his temple, fingers brushing the thick black frames of his glasses, as if adjusting them for a portrait. Two empty glasses, one with a star etched on its base, sit beside him on the table, catching the warm, amber glow from the bar’s recessed lighting. Behind him, the bar’s shelving is symmetrically arranged with bottles, and a single, glowing sign hangs above the counter like a tiny, silent lantern. The scene is framed with the quiet geometry of a storybook, where every angle is intentional and every shadow holds a secret.

**Moment 3** (scene `0f514958-508e-4083-9ba2-58795f036885`):

> The man’s hand hovers over a bottle with a coral cap, its label blurred like a forgotten story, while the amber glow of the overhead orb casts a warm, uneven light across his glasses and the rim of his glass. Behind him, the bar’s backlit menu glows with a faint, orderly precision, its rows of text standing like silent, illuminated tombstones in the dim. The scene is framed with the quiet symmetry of a still life—his elbow, the bottle, the glass, all aligned under the single, golden eye of the lamp. There is a small, formal detail: the red of the cap, the yellow of the light, the dark brown of his sweater, all arranged with the careful, melancholic balance of a Wes Anderson storyboard.

