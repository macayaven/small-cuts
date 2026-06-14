# Demo-Readiness Checklist

Last updated: 2026-06-14 18:10 CEST.

## Judged Space

- [x] Space lives at `build-small-hackathon/small-cuts` and is public.
- [x] Space runs on `cpu-basic` as a viewer/library, not as the inference host.
- [x] `SMALL_CUTS_ENGINE_URL` points at the public read gate.
- [x] Visibility controls are disabled in Space engine mode.
- [x] Space loads a live engine scene through Cloudflare.
- [x] Space fetches `frame.jpg`, `card.webp`, `voice.wav`, and `clip.mp4` through `/media/*`.
- [x] Custom player uses file-backed `<audio id="sc-voice">` as the master clock.
- [x] Play/pause is bound to trusted DOM gestures instead of a Gradio callback.
- [ ] Human browser smoke: click play on the Space and confirm video, sound, captions, and progress advance together.
- [ ] Mobile browser smoke on iPhone Safari.

## Private Live Path

- [x] Mac Studio engine listens privately on Tailnet-compatible `:8077`.
- [x] Public Cloudflare path points to read gate on `127.0.0.1:8078`, not directly to the engine.
- [x] Public `GET /v1/scenes` returns `200`.
- [x] Public `GET /v1/session` returns `403`.
- [x] Public `PATCH /v1/scenes/*` returns `403`.
- [x] Synthetic 12-frame moment returns `ack accepted` and `SceneAudio`.
- [x] Synthetic scene stores both audio and `clip.mp4`.
- [ ] Physical iPhone simulated-source smoke after reinstalling the latest app.
- [ ] Physical Ray-Ban Meta glasses smoke: in-ear narration returns while the Space receives the same cut.

## Submission Metadata

- [x] README identifies the app as the Gradio Space submission.
- [x] README documents models under 32B: Qwen3-VL-8B + Kokoro.
- [x] README claims `track:wood`, `achievement:offgrid`, `achievement:offbrand`, `achievement:llama`, and `achievement:fieldnotes`.
- [x] Redeploy README/frontmatter after this checklist update.
- [x] Verify the Space metadata shows `offgrid` and `llama` tags after redeploy.
- [ ] Add demo video link.
- [ ] Add social post link.
- [ ] Run the submission analyzer before final submission.

## Demo Video

- [ ] Capture one motion-rich first-person moment from the glasses.
- [ ] Show in-ear narration returning to the wearer.
- [ ] Show the HF Space receiving the same just-happened POV clip.
- [ ] Show the custom theater player replaying video, audio, captions, and title.
- [ ] Keep final cut under 2 minutes, ideally around 60-90 seconds.

## Known Constraints

- Capture is image-frame only for this version; source audio is intentionally not part of the payload.
- The Space is the public viewer, while local hardware runs the live small-model inference/TTS path.
- Browser autoplay with sound is intentionally not promised; sound starts from the explicit play gesture.
- Cloudflare quick-tunnel hostnames are ephemeral. Use the named `small-cuts.carloscrespomacaya.com` tunnel for final demo if time allows.
