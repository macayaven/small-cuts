# Demo-Readiness Checklist

Last updated: 2026-06-15 08:18 CEST.

## Judged Space

- [x] Space lives at `build-small-hackathon/small-cuts` and is public.
- [x] Space runs on `cpu-basic` as a viewer/library, not as the inference host.
- [x] `SMALL_CUTS_ENGINE_URL` points at the public read gate.
- [x] Active Space endpoint uses the known-good quick tunnel:
  `https://lincoln-greene-paragraph-tcp.trycloudflare.com`.
- [x] Visibility controls are disabled in Space engine mode.
- [x] Space loads a live engine scene through Cloudflare.
- [x] Space fetches `frame.jpg`, `card.webp`, `voice.wav`, and `clip.mp4` through `/media/*`.
- [x] Custom player uses file-backed `<audio id="sc-voice">` as the master clock.
- [x] Play/pause is bound to trusted DOM gestures instead of a Gradio callback.
- [x] Latest Space source deploy includes final thumbnail/title polish:
  `3654f4e89f44a994f64332bdea980290f7c2039f`.
- [x] Browser automation verifies the active Space renders the real POV `rayuela` scene with
  ready `clip.mp4` and `voice.wav` on desktop.
- [x] Browser automation verifies the active Space library uses real POV `frame.jpg` thumbnails
  after the final deploy.
- [ ] Human browser smoke: click play on the Space and confirm video, sound, captions, and progress advance together.
- [x] Mobile viewport smoke verifies no document overflow, ready `clip.mp4`/`voice.wav`, captions,
  and POV library thumbnails.
- [ ] Physical mobile smoke on iPhone Safari.

## Private Live Path

- [x] Mac Studio engine listens privately on Tailnet-compatible `:8077`.
- [x] Public Cloudflare path points to read gate on `127.0.0.1:8078`, not directly to the engine.
- [x] Public `GET /v1/scenes` returns `200`.
- [x] Public `GET /v1/session` returns `403`.
- [x] Public `PATCH /v1/scenes/*` returns `403`.
- [x] Synthetic 12-frame moment returns `ack accepted` and `SceneAudio`.
- [x] Synthetic scene stores both audio and `clip.mp4`.
- [x] Real seed POV clip (`rayuela.mp4`) returns `ack accepted`, `SceneAudio`, idle status,
  and public `clip.mp4`/`voice.wav` through the read gate.
- [x] Latest local engine restart is on the retained-storage-task fix, then warmed with
  `rayuela.mp4` scene `0330bfcc-e5d1-4615-bcf6-95e57e164c6a`.
- [x] iOS simulator suite passes: 63 tests, 1 live-engine smoke skipped, 0 failures.
- [x] Opt-in Swift live-engine smoke passes against `ws://127.0.0.1:8077/v1/session`
  with real `SceneAudio` in 4.4 s.
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
- Cloudflare quick-tunnel hostnames are ephemeral. The named `small-cuts.carloscrespomacaya.com`
  tunnel direct smoke is `200` for reads and `403` for writes, but the HF Space stayed on
  "Signal lost" when pointed at it during this run. Keep the Space on the known-good quick tunnel
  until that Cloudflare/HF interaction is isolated.
