# Demo-Readiness Checklist

Last updated: 2026-06-15 17:51 CEST.

## HF Deployment Safety Override - 2026-06-15

This section supersedes the older org-Space and Cloudflare engine-mode checklist items below. Keep
the old evidence for audit/history, but do not use it as the active deploy posture for development,
testing, or the final run.

- Development/testing Space policy: use only Carlos's personal HF profile (`macayaven/*`) for all
  Space deploys, upload smoke tests, relay smoke tests, and bucket writes.
- Development/testing bucket policy: use only a personal bucket such as
  `macayaven/small-cuts-scenes-dev`, prefix `relay`. Do not write to org buckets while iterating.
- Org submission policy: do **not** deploy to, unpause, poll-test, mutate variables/secrets on, or
  write buckets under `build-small-hackathon/*` until the personal-profile product is fully proven.
- Reserved final org Space: `build-small-hackathon/small-cuts-buffer-poc`. It is private/paused by
  Carlos, remains the only available org submission slot, and should be renamed and made public only
  at the final submission promotion step.
- Do not use `build-small-hackathon/small-cuts-live` as an active target. It was flagged by the HF
  abuse handler after a deployment containing stale Cloudflare/Tailnet material; treat it as
  unavailable and do not try to recover it during development.
- HF account-safety stop rule: if a personal Space is `PAUSED` and restart/rebuild returns `503`,
  stop all HF Space actions immediately. Do not keep retrying restarts, polls, logs, uploads,
  replacement Space creation, or variable/secrets mutations. Continue with local-only checks and
  direct Modal checks until Carlos explicitly approves one specific next HF Space action.
- Active personal dev Space: `macayaven/small-cuts-dev`. It is private, uses paid hardware one tier
  above free CPU Basic, and has Dev Mode enabled for careful interactive work from Cursor/VS Code.
  Treat it as the only current personal Space target, and do not deploy, restart, poll, mutate
  variables/secrets, open Dev Mode sessions, or smoke-test it without explicit approval for that
  exact action.
- Current personal relay settings for local/staging runs:
  - `SMALL_CUTS_RELAY_BUCKET=macayaven/small-cuts-scenes-dev`
  - `SMALL_CUTS_RELAY_PREFIX=relay`
  - `SMALL_CUTS_BACKEND=mock`
  - `SMALL_CUTS_TTS_BACKEND=mock`
- The staging Space should be viewer-only or hybrid on `cpu-basic`. It reads finished scenes from a
  personal HF bucket relay, not from Cloudflare or a live engine URL.
- Private live path remains: Ray-Ban Meta glasses -> iPhone app -> Mac Studio engine over
  Tailnet/local network -> `SceneAudio` back to the iPhone/glasses after the wearer taps `Cut!`.
  This local glasses-to-ear return path is non-negotiable.
- Public Space path is post-cut: after the take is completed, publish the finished clip, generated
  title, narration, voice, thumbnail/poster, and manifest into the personal HF bucket relay.

## HF Space Upload Hardening - 2026-06-15 17:51 CEST

- [x] Local upload path hardening added after Claude/OpenCode/agy review: expected upload validation,
  missing auth, and Modal failures soft-fail through `gr.Warning` while preserving the current stage.
- [x] Upload OAuth state capture is defensive against unexpected profile/session shapes.
- [x] Modal upload click is single-concurrency and the Gradio queue has an explicit bounded max size.
- [ ] Not deployed or smoked on HF. `macayaven/small-cuts-dev` still needs explicit one-action
  approval before any deploy, Dev Mode session, log read, restart, poll, or smoke test.

- Test order for the final run:
  1. Short physical glasses smoke first, before populating the public library.
  2. Populate the library only from controlled, honest pipeline outputs.
  3. Run the full demo rehearsal after both private ear playback and public relay playback are
     proven.
- Judge verification upload target for the next implementation pass: a personal-profile Gradio
  staging Space must expose a finished-video upload path so judges can later verify the app without
  glasses, iOS, or local Tailnet access. Allow uploads up to 60 seconds by default and process them
  as completed cuts. This matches an instant-clip/reel-length posture while keeping the Modal path
  bounded.
- Before deploying upload controls to the reserved org Space, prove this through the private Modal
  app `small-cuts-postcut` and the personal-profile staging Space/bucket.
- The final org Space should become a hybrid surface only after the personal-profile path passes:
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
  in-ear playback, the completed scene can be auto-published to the personal relay bucket by the local/admin
  publisher. Those scenes should include `source="glasses"` and render a small glasses icon in the
  top-left of the Space stage/library tile.
- Library population target: use longer, controlled, honest clip artifacts for the public relay
  library instead of the current very short 24-frame samples.
- iOS restores wearer captions/status for the private glasses path: after `Cut!`, the phone shows a
  waiting caption, then swaps to the generated narration when `SceneAudio` arrives. This baseline is
  live post-cut, not continuous narration while rolling.
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
- [x] Space-side Modal client smoke accepted `/private/tmp/small-cuts-upload-5s.mp4` in 121.66 s
  against the deployed endpoint, returned scene `modal-04f98e2795cd` with title
  `The Smoke Test`, `source="upload"`, generated narration, `media/clip.mp4`, and
  `media/voice.wav`.
- [x] HF bucket artifact writing smoke passed for
  `relay/uploads/modal-04f98e2795cd/`: `scene.json`, `media/frame.jpg`, `media/card.webp`,
  `media/clip.mp4`, and `media/voice.wav`.

## Local Hybrid Verification - 2026-06-15 15:49 CEST

- [x] Full Python gate passed:
  `uv run ruff check . && uv run ruff format --check . && uv run pytest`
  (`205 passed`, 4 warnings).
- [x] Full iOS simulator gate passed with the plan command on `iPhone 17, OS=26.5`:
  `66 tests`, `1` expected live-engine smoke skipped, `0` failures.
- [x] Local Gradio relay/upload-sandbox app launched on `http://127.0.0.1:7860` with
  `SMALL_CUTS_ENABLE_UPLOAD_SANDBOX=1`, the deployed Modal URL, and the HF relay bucket.
- [x] Local Gradio OAuth mock sign-in worked as `macayaven`; the upload icon opened the
  video-only upload drawer while anonymous cookie-free page load returned HTTP `200`.
- [x] Local >60-second guard rejected `/private/tmp/small-cuts-upload-61s.mp4` before any Modal
  call with `Please upload a clip up to 60 seconds.`

## Judged Space

- [x] Historical org Space evidence below is retained for audit only; it is not the active
  development or test posture.
- [ ] Personal-profile staging Space under `macayaven/*` is the only place to test the upload and
  relay experience before submission.
- [ ] Reserved final org Space is `build-small-hackathon/small-cuts-buffer-poc`; rename and make it
  public only after the personal staging path passes.
- [x] Space runtime target remains `cpu-basic` as a viewer/library, not as the inference host.
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
- [x] Physical-device prep: `xcrun xctrace list devices` sees the iPhone 14 Pro on iOS 26.6,
  and `xcodebuild build` for destination `00008120-001045510C3B401E` succeeded with
  command-line signing overrides only.
- [x] Current build installed to the physical iPhone via `xcrun devicectl device install app`.
- [x] Relay publisher dry-run against `http://127.0.0.1:8077` with
  `--include-private --source glasses` staged one scene locally and wrote `source="glasses"` plus
  `source_icon="glasses"` into the staged manifest without syncing the HF bucket.
- [x] Manual physical app launch happened after install; observed behavior is live post-cut:
  narration returns after `Cut!`, not continuously while rolling.
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
- The current iOS capture path is `Action!` -> `Cut!` -> local narration return. True rolling
  micro-segment narration with chronological continuity metadata is planned next.
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
