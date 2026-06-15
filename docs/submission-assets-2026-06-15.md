# Submission Assets - 2026-06-15

Working timestamp: 2026-06-15 14:16 UTC / 16:16 CEST.

Deadline: 2026-06-15 23:59 UTC / 2026-06-16 01:59 CEST.
Time remaining at this pass: about 9 hours 43 minutes.
Target latest demo start with six-hour buffer: 2026-06-15 17:59 UTC / 19:59 CEST.

## Final Product Submission

Submit **Small Cuts** as a public Gradio Space that turns first-person glasses moments into
short cinematic cuts: a local small-model engine narrates the wearer POV, speaks it back in-ear,
and publishes the finished clip to a polished Space theater/library.

One-line pitch:

> A deadpan AI narrator for your life: Ray-Ban Meta POV moments become tiny narrated films,
> spoken in your ear and replayed on a public Hugging Face Space.

Short description:

> Small Cuts is a glasses-to-ear-to-Space loop. The iPhone sends image-frame moments from
> Ray-Ban Meta glasses to a private Mac Studio engine. Qwen3-VL-8B through llama.cpp writes a
> grounded deadpan narration, Kokoro speaks it, the wearer hears it, and the same just-happened
> POV clip lands in a Gradio theater with synced captions, title, voice, and library thumbnail.

Submission baseline:

- The public Space is source-agnostic once a cut is complete: glasses-origin scenes and
  authenticated browser uploads render as the same theater artifact with video, generated title,
  generated narration, Kokoro voice, synced captions, and a library tile.
- The browser upload path is for judge verification. It requires Hugging Face login, sends the
  finished video to the private Modal `small-cuts-postcut` service, and does not promise glasses,
  iOS, or real-time capture.
- The current glasses path is live post-cut: `Action!` records, `Cut!` sends the moment to the
  private local engine, and `SceneAudio` returns to the wearer. Rolling micro-segment narration
  while the take is still in progress is the next production-grade phase.

## Why It Can Win

- It is not another chat wrapper. The product gesture is physical: look, mark, hear, replay.
- The judged Space is polished and alive: five real first-person glasses clips now populate the
  public library after being sent through the same WebSocket/read-gated media path as live cuts.
- The architecture maps cleanly to the hackathon quests: small open models, Gradio Space, custom
  Off-Brand frontend, local/offgrid inference, and llama.cpp.
- The demo has an obvious "show a friend" moment: ordinary life becomes a tiny film with a
  narrator that notices the absurdity.
- If hardware is unstable, the fallback is still strong: real glasses footage, local narration,
  Kokoro voice, and Space replay.

## Known Weaknesses

- The live model narrates one selected frame per moment; the mini-MP4 gives context in the viewer
  but the VLM is not yet doing full video reasoning.
- The current iOS wearer path is not continuous narration while rolling; narration returns after
  `Cut!`. The planned next phase is chronological micro-segments with device metadata and continuity
  state.
- Browser audio cannot autoplay; the Space correctly requires a user click before sound.
- Public viewing depends on the current Cloudflare quick tunnel until the named tunnel/HF
  interaction is isolated.
- The public library now uses engine-generated narration, so it is honest as a model-quality sample.
  The take end point is curated per source clip, matching how a wearer would tap Cut! when the
  moment is readable.

## Current Public Generated Library

Live root: `/private/tmp/small-cuts-demo-library-generated-24f-20260615`

Public read gate:

```text
https://lincoln-greene-paragraph-tcp.trycloudflare.com
```

Scenes visible in the Space:

| Order | Title | Role |
|---:|---|---|
| 1 | A hand, palm up, blocks the camera's view, revealing a... | Builder/desk sample; still literal but coherent |
| 2 | The camera lingers on a concrete alleyway at night, the... | Night urban atmosphere |
| 3 | The car door is open, revealing a black interior and a... | Strong physical POV situation |
| 4 | The driver grips the steering wheel with both hands, thumbs... | Motion/interior sample |
| 5 | The yellow circle with numbers is painted on the floor... | Strongest current generated hero cut |

Recommended library/thumbnail hero:

```text
The yellow circle with numbers is painted on the floor...
scene_id: aead3e4d-2459-4638-81b8-74abddd2a149
poster: /private/tmp/small-cuts-demo-library-generated-24f-20260615/media/aead3e4d-2459-4638-81b8-74abddd2a149/frame.jpg
clip: /private/tmp/small-cuts-demo-library-generated-24f-20260615/media/aead3e4d-2459-4638-81b8-74abddd2a149/clip.mp4
```

Reason: it is visually legible, currently active on the Space, uses the regular engine path, and
has the best current generated line: "as if marking a spot for something that never happened."

## Demo Video Plan

Target duration: 60-90 seconds.

Shot list:

1. 3-5 seconds: show the live Space already populated with the five-cut library.
2. 6-10 seconds: show iPhone app connected to `ws://mac-studio.tail48bab7.ts.net:8077/v1/session`
   or current Tailnet MagicDNS equivalent.
3. 10-25 seconds: wear glasses and capture one readable motion-rich moment.
4. 25-40 seconds: trigger/mark the moment and capture in-ear narration returning.
5. 40-60 seconds: show the same cut appear in the HF Space.
6. 60-80 seconds: click play in the Space; show video, Kokoro voice, captions, progress, title,
   and library thumbnail moving together.
7. Final 5 seconds: hold on the Space URL and the "Small Cuts" brand.

Primary live take criteria:

- Move for at least four seconds before marking.
- Choose a scene with one readable object/situation, not a visually noisy crowd.
- Avoid faces if possible.
- Do not trigger several marks in a row; one clean moment beats a cluttered library update.
- Warm the engine with one throwaway moment before recording the hero take.

Fallback demo if glasses/Bluetooth wobble:

- Use a real glasses-recorded POV clip.
- Send it through the local engine as a simulated moment.
- Show in the video that the Space receives a finished cut with clip, voice, captions, title, and
  thumbnail. State truthfully that the judged Space is the product surface and the live glasses
  path is the intended input path under test.

## Social Post Draft

Short version:

> Built **Small Cuts** for the @huggingface Build Small Hackathon: Ray-Ban Meta POV moments become
> tiny narrated films. A local Qwen3-VL-8B + Kokoro engine speaks the narration in-ear, while a
> Gradio Space replays the same just-happened cut with synced captions and a cinematic library.
> #buildsmall

Longer version:

> Small Cuts is my Build Small Hackathon submission: a deadpan AI narrator for ordinary life.
> Ray-Ban Meta glasses capture first-person moments, an iPhone sends image frames privately to a
> Mac Studio, Qwen3-VL-8B through llama.cpp writes a grounded narration, Kokoro speaks it back in
> the ear, and the finished POV cut lands in a public Gradio Space with video, voice, captions,
> title, and library thumbnail. It is deliberately small, local, and weirdly cinematic. #buildsmall

Add after posting:

```text
Space: https://huggingface.co/spaces/build-small-hackathon/small-cuts-live
Demo: TODO
```

## Field Notes Draft

Suggested title:

```text
Small Cuts: Building a narrator for the moments that just happened
```

Outline:

1. The product idea: life becomes small narrated cuts, not a chatbot.
2. Why glasses: first-person context makes the narration feel lived, not uploaded.
3. Why small models: Qwen3-VL-8B is enough when the prompt is grounded and the moment is chosen.
4. Why local/offgrid: latency, privacy, and hackathon constraints all point to the home engine.
5. The hard parts:
   - selecting the right frame,
   - returning in-ear audio quickly,
   - making the Space feel like a streaming platform, not a model demo,
   - keeping public read separate from private write.
6. What worked:
   - audio-clock-driven video/caption sync,
   - real POV thumbnails,
   - read-gated public Cloudflare endpoint,
   - model-generated public library from real glasses clips.
7. What is next:
   - rolling micro-segment narration for the glasses path,
   - optional device metadata for chronology and narrative continuity,
   - full video reasoning over buffered clips,
   - stronger title generation,
   - durable named tunnel,
   - publish controls/auth.

Closing paragraph:

> The best version of Small Cuts is not a camera feature. It is a private narrator that notices
> the little cinematic beats a person usually walks past, says one honest line in the ear, and
> leaves behind a tiny film that feels like it happened on purpose.

## Final Submission Checklist

Official field guide requirements checked from `build-small-hackathon/field-guide`:

- Ship a Gradio Space inside the `build-small-hackathon` org.
- Record a public demo video.
- Publish one social media post.
- Put both links in the Space README.
- Put track and badge tags in the README YAML frontmatter.

- [x] Space is public and running on `cpu-basic`.
- [x] Deployed Space SHA is `3654f4e89f44a994f64332bdea980290f7c2039f`.
- [x] Space variable `SMALL_CUTS_ENGINE_URL` points at
  `https://lincoln-greene-paragraph-tcp.trycloudflare.com`.
- [x] HF metadata includes `track:wood`, `achievement:offgrid`, `achievement:offbrand`,
  `achievement:llama`, and `achievement:fieldnotes`.
- [x] Cloudflare public read gate serves the five key-marked generated scenes with `clip.mp4`,
  `voice.wav`, `frame.jpg`, and `card.webp`.
- [x] Cloudflare blocks public `/v1/session` and `PATCH /v1/scenes/*` with `403`.
- [x] Space Gradio `_tick` smoke returns latest video/audio/subtitle markup and all five generated
  gallery captions.
- [ ] Field Notes URL is public, not `401`.
- [ ] Demo video uploaded and linked in README.
- [ ] Social post published and linked in README.
- [ ] README redeployed to HF Space after links are inserted.
- [ ] Human click confirms Space play starts audio, video, captions, and progress together.
- [ ] Physical e2e: glasses/iPhone produce in-ear narration and the same cut appears in Space.
- [ ] Submission analyzer passes.

Deadline rule: if the Field Notes URL is still private near final submission, either make it public
through the HF web editor or remove `achievement:fieldnotes` from README/frontmatter before the
final analyzer pass. Do not submit a broken badge claim.
