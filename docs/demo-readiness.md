# Demo-Readiness Checklist

Last updated: 2026-06-15 15:30 CEST.

## Current Architecture Override - 2026-06-15

This section supersedes the older Cloudflare engine-mode checklist items below. Keep the old
evidence for audit/history, but do not use it as the active deploy posture for the final run.

- Active judged Space: `build-small-hackathon/small-cuts-live`, public, `cpu-basic`.
- Paused/private Spaces: `build-small-hackathon/small-cuts` and
  `build-small-hackathon/small-cuts-buffer-poc`.
- The live Space is currently viewer-only. It reads finished scenes from the HF bucket relay, not
  from Cloudflare or a live engine URL. The next implementation pass should make this same Space
  hybrid by adding the judge upload path below.
- Current relay settings:
  - `SMALL_CUTS_RELAY_BUCKET=build-small-hackathon/small-cuts-scenes`
  - `SMALL_CUTS_RELAY_PREFIX=relay`
  - `SMALL_CUTS_BACKEND=mock`
  - `SMALL_CUTS_TTS_BACKEND=mock`
- The relay bucket currently has only the canary/health object; intentional library population is
  still pending.
- Private live path remains: Ray-Ban Meta glasses -> iPhone app -> Mac Studio engine over
  Tailnet/local network -> immediate `SceneAudio` back to the iPhone/glasses. This glasses-to-ear
  loop is non-negotiable.
- Public Space path is post-cut: after the take is completed, publish the finished clip, generated
  title, narration, voice, thumbnail/poster, and manifest into the HF bucket relay.
- Test order for the final run:
  1. Short physical glasses smoke first, before populating the public library.
  2. Populate the library only from controlled, honest pipeline outputs.
  3. Run the full demo rehearsal after both private ear playback and public relay playback are
     proven.
- Judge verification upload target for the next implementation pass: the submitted Gradio Space
  must expose a finished-video upload path so judges can verify the app without glasses, iOS, or
  local Tailnet access. Allow uploads up to 60 seconds by default and process them as completed
  cuts. This matches an instant-clip/reel-length posture while keeping the Modal path bounded.
- Before deploying upload controls to the submitted org Space, prove this through the private Modal
  app `small-cuts-postcut`.
- The final org Space should become a hybrid surface only after the Modal POC passes:
  - relay/library mode for the live demo and public just-happened clips;
  - on-demand upload mode for judge verification, with real Modal-hosted narration/TTS, not mock
    output.
- Keep the submitted Space on `cpu-basic` for the Modal path. The Space should not warm Qwen/Kokoro;
  it accepts uploads, requires HF login for upload only, calls Modal server-side, and renders the
  returned scene.
- Modal upload inference should use the hackathon grant aggressively but bounded: H100 first with
  A100-80GB and L40S fallbacks, one warm GPU container, one active buffer container, and up to four
  GPU containers for parallel uploads. Do not use same-container GPU concurrency for Qwen/Kokoro
  unless the model/TTS pipeline is explicitly proven thread-safe.
- Glasses-origin public clips should not go through Modal. `Action!` starts capture and `Cut!`
  finalizes the take; after the local engine has produced clip, title, narration, and speech for
  in-ear playback, the completed scene can be auto-published to the relay bucket by the local/admin
  publisher. Those scenes should include `source="glasses"` and render a small glasses icon in the
  top-left of the Space stage/library tile.
- Library population target: use longer, controlled, honest clip artifacts for the public relay
  library instead of the current very short 24-frame samples.
- iOS should restore real-time wearer captions/status for the private glasses path. Do not stretch
  the iOS/engine real-time payload just to satisfy the Space upload requirement.
- `cpu-basic` remains correct for the Space if Modal handles judge-upload inference. ZeroGPU is now
  only a contingency if Modal is deliberately ruled out after a measured failure.

## Modal Post-Cut POC Evidence - 2026-06-15 15:30 CEST

- [x] Modal CLI authenticated as profile `macayaven`.
- [x] Stale Small Cuts Modal app `small-cuts-buffer-inference-poc` was stopped before creating the
  new post-cut infra. The two interrupted `small-cuts-postcut` dev serve attempts are also stopped.
- [x] Modal secret `small-cuts-postcut` exists in Modal environment `main` with keys `HF_TOKEN` and
  `SMALL_CUTS_MODAL_API_TOKEN`; no token values were written to repo docs.
- [x] Private Modal app `small-cuts-postcut` deployed at
  `https://macayaven--small-cuts-postcut-api.modal.run`.
- [x] Modal GPU policy encoded as H100 -> A100-80GB -> L40S, with
  `min_containers=1`, `buffer_containers=1`, `max_containers=4`, and no same-container GPU
  concurrency on the Qwen/Kokoro worker.
- [x] Upload cap is now 60 seconds by default, with the Space-facing
  `SMALL_CUTS_UPLOAD_MAX_SECONDS` remaining the deployment override. A 61-second synthetic MP4 was
  rejected by the deployed Modal API with HTTP 422 and message
  `video is too long; upload up to 60 seconds`.
- [x] Local syntax/lint smoke passed:
  `python -m py_compile modal_app/small_cuts_postcut.py`,
  `uv run ruff check modal_app/small_cuts_postcut.py src/small_cuts/engine/library.py tests/test_engine_library.py`,
  `uv run ruff format --check modal_app/small_cuts_postcut.py src/small_cuts/engine/library.py tests/test_engine_library.py`,
  and
  `uv run pytest tests/test_engine_library.py::test_write_clip_mp4_can_disable_blends -q`.
- [x] Clean Modal dev serve smoke accepted `/private/tmp/small-cuts-codec-smoke.mp4` in 0.63 s,
  completed with real Qwen/Kokoro output, and returned scene `modal-6da427b60106`:
  title `The Green Screen`, model `Qwen/Qwen3-VL-8B-Instruct`, TTS `hexgrad/Kokoro-82M`.
- [x] HF bucket artifact writing smoke passed: `relay/uploads/modal-6da427b60106/` contains exactly
  `scene.json`, `media/frame.jpg`, `media/card.webp`, `media/clip.mp4`, and `media/voice.wav`.
  Relay root was checked after cleanup and contains only `health.txt` plus `uploads/`.
- [ ] Warm 5-60 second upload timings are still pending; only a 1-second cold smoke has been
  measured so far.

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
- [x] Space README-only copy update deployed as `8dfd628308a0849d4e9fc0baa646af94c33b949d`;
  runtime returned to `RUNNING` and post-rebuild browser smoke still loaded the five hero cuts.
- [x] Browser automation verifies the active Space renders the real POV `rayuela` scene with
  ready `clip.mp4` and `voice.wav` on desktop.
- [x] Browser automation verifies the active Space library uses real POV `frame.jpg` thumbnails
  after the final deploy.
- [x] Public library is populated with five preselected first-person glasses clips sent through the
  regular `/v1/session` engine pipeline, using 24-frame key-marked moment envelopes.
- [x] Public generated library serves each scene with `frame.jpg`, `card.webp`, `voice.wav`, and
  24-frame / 6 fps `clip.mp4` through the Cloudflare read gate.
- [ ] Human browser smoke: click play on the Space and confirm video, sound, captions, and progress advance together.
- [x] Gradio API smoke verifies the active Space `_tick` renders the latest generated title, video
  stage, Cloudflare `clip.mp4`, ready `voice.wav`, visibility `public`, and five gallery captions.
- [x] Mobile viewport smoke verifies no document overflow, ready `clip.mp4`/`voice.wav`, captions,
  and the five generated library thumbnails.
- [ ] Physical mobile smoke on iPhone Safari.

## Private Live Path

- [x] Mac Studio engine listens privately on Tailnet-compatible `:8077`.
- [x] Public Cloudflare path points to read gate on `127.0.0.1:8078`, not directly to the engine.
- [x] Public `GET /v1/scenes` returns `200`.
- [x] Public `GET /v1/session` returns `403`.
- [x] Public `PATCH /v1/scenes/*` returns `403`.
- [x] Synthetic 24-frame moment returns `ack accepted` and `SceneAudio`.
- [x] Synthetic scene stores both audio and `clip.mp4`.
- [x] Real seed POV clip (`rayuela.mp4`) returns `ack accepted`, `SceneAudio`, idle status,
  and public `clip.mp4`/`voice.wav` through the read gate.
- [x] Latest local engine restart is on the retained-storage-task fix, then warmed with
  `rayuela.mp4` scene `162a9e89-3494-45d2-b28e-bf2a03d8c3cf` on the final thumbnail code.
- [x] Final warm-up scene stores `clip.mp4`, `voice.wav`, and a POV `frame.jpg`; active Space
  renders it as the newest cut with no desktop overflow.
- [x] Model-generated library audit populated a clean five-scene run from the preselected glasses
  clips before the hero-library switch. Quality was mixed: car-door, night-drive, and rayuela were
  usable; the desk-laptop opener was too literal because the selected frame emphasized an overlay.
- [x] Curated hero rows were archived into SQLite table
  `hidden_scenes_20260615_regular_pipeline_swap` and removed from the active `scenes` table, with
  media preserved.
- [x] The final public library now comes from session
  `regular-pipeline-24f-keymark-glasses-20260615T083000Z`; the previous 24-frame final-frame run
  is archived in `hidden_scenes_20260615_final_frame_24f`.
- [x] Public media smoke confirms all five active scenes return `200` for `clip.mp4`, `voice.wav`,
  `frame.jpg`, and `card.webp`.
- [x] Hidden warm-up moment against the hero-root engine returned `SceneAudio` in 15.4 s on
  2026-06-15 09:09 CEST; the warm-up row/media were pruned, leaving exactly the five hero cuts
  visible through Cloudflare.
- [x] `tmux` session `small-cuts-awake` is running `caffeinate -dimsu` to keep the Mac Studio
  awake for the live services.
- [x] iOS simulator suite passes: 64 tests, 1 live-engine smoke skipped, 0 failures.
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
- [ ] Make the field-notes URL public; `https://huggingface.co/blog/macayaven/small-cuts-field-notes`
  returned `401` on 2026-06-15 09:06 CEST. Full publishable draft is in
  `docs/field-notes-small-cuts.md`.
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
- The current public library root is `/private/tmp/small-cuts-demo-library-generated-24f-20260615`.
  A full curated-library backup exists at
  `/private/tmp/small-cuts-demo-library-hero-20260615.pre-generated-backup-20260615T080924Z`.
  Earlier model-generated roots remain available as
  `/private/tmp/small-cuts-demo-library-hero-20260615` and
  `/private/tmp/small-cuts-demo-library-curated-20260615`.
