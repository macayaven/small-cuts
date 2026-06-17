# Proposal: The Decoupled Svelte Player (Hybrid C + A)

## 1. Position
**Explicit Hybrid: (C) a real custom Svelte component (`VideoScene`) for the player, backed by (A)'s lazy data-layer hydration.**

*Why:* The fork in the road (Question #1) demands a choice on audio muxing. Our pipeline generates brief looping b-rolls and variable-length TTS narration. Forcing backend FFmpeg muxing (loop-padding video to match audio length) merely to satisfy native `gr.Video`'s limitations would destroy our lightweight generation pipeline, balloon storage costs, and waste compute on CPU-basic relay nodes. We must keep the media **decoupled**. However, keeping decoupled media requires a real, compiled frontend component to achieve perfect, event-driven browser sync, escaping the brittle `gr.HTML` XSS hacks we currently rely on.

## 2. Target Architecture
- **Components:** We build `class VideoScene(Component)` using the `gradio-imageslider` Svelte template. The backend defines `SceneData(GradioRootModel)` containing `FileData` objects for `clip`, `audio`, and `vtt`. The app shell uses standard `gr.Gallery(value=list, allow_preview=False)` for the library rail and `gr.State` to track the playlist index.
- **Data Flow:** The backend parses the manifest once into a global variable. `gr.Gallery.select()` fires an event that updates the `gr.State` index, which cascades into a `gr.update()` yielding the next `SceneData` payload directly to the `VideoScene` component.
- **Where the clock lives:** Inside the Svelte component, the native `<audio>` element is the sole authoritative clock. We eliminate the Python-side `gr.Audio` entirely. For video-only scenes, the component intelligently falls back to using the `<video>` element as the clock.
- **A/V/Captions Sync:** Sync is handled elegantly by native browser events and Svelte reactivity. We bind Svelte state variables to the media elements (`bind:currentTime={time}`, `bind:paused={isPaused}`). If the looping `<video>` throws a `waiting` event due to a network stall, a reactive Svelte block natively calls `.pause()` on the `<audio>`. When the `<video>` buffer recovers and fires `playing`, we `.play()` the audio. Captions are rendered natively by the browser via a `<track src={vtt.url} default>` tag inside the audio element, killing our manual DOM caption-sync logic.
- **Media Serving:** We kill synchronous hydration. We enforce `direct_media_urls=True` (`hf_relay.py:215-246`), meaning `_hydrate_scene` returns instantly with HF resolve URLs. For non-direct modes, we utilize Gradio's native `/gradio_api/file=` route alongside `gr.set_static_paths([cache_dir, bucket_mount_path])` (`viewer.py:1469, 2035`). This guarantees HTTP 206 + `Accept-Ranges: bytes` streaming out-of-the-box via `RangedFileResponse`.
- **State Management:** `gr.State` holds the active scene index for the session. `VideoScene` fires a native Gradio `.end()` event when the audio finishes, seamlessly triggering the Python handler to increment the `State` index and load the next scene.

## 3. How it kills the 5 symptoms
1. **Video startup latency (LCP):** Eradicated at the data layer. By removing `fs.cat()` in `_hydrate_scene` (`hf_relay.py:248-261`), media URLs are passed directly to the client. The browser uses HTTP 206 Range requests to stream the first frame instantly.
2. **A/V/caption desync on stall:** Eliminated structurally. Instead of manually polling `waiting`/`playing` in Python-injected JS, Svelte natively binds the media elements. A buffer underrun on `<video>` fires an event that instantly pauses the `<audio>`.
3. **Frame jump on pause/resume:** Cured entirely. We delete the 120ms `setInterval` drift guard that constantly overwrites `video.currentTime = audio.currentTime % video.duration`. The looping video plays freely without timeline manipulation; we only sync the play/pause booleans.
4. **Wrong play icon for video-only scenes:** The Svelte component manages its own UI state dynamically. If `audio.url` is null, the internal clock logic shifts seamlessly to the video element. The play/pause button icon is a reactive Svelte variable bound to the active media's state.
5. **General jank + maintenance cost:** 400 lines of string-concatenated, brittle JS are replaced by a standard, typed, and compiled `.svelte` file using framework-grade DOM bindings.

## 4. Migration Plan
1. **Fix the Data Layer (The 'A' prerequisite):** Modify `hf_relay.py` to ensure `_default_direct_media_urls()` explicitly prioritizes direct URLs. Ensure `gr.set_static_paths` in `viewer.py` explicitly covers all media caches and mount paths to enable range requests.
2. **Scaffold Component:** Run `gradio cc create VideoScene --template SimpleImage`. Define `SceneData` with typed `FileData` fields.
3. **Write Svelte:** Implement `Index.svelte` with `<audio bind:paused bind:currentTime>`, `<video loop muted>`, and the stylized 9:16 control pill.
4. **The Purge:** In `src/small_cuts/viewer.py`, we execute a massive deletion:
   - DELETE `PLAYBACK_SYNC_JS` entirely (`viewer.py:1572-1972`). This removes the dangerous `setInterval`.
   - DELETE `render_stage_html` (`viewer.py:821`) and `_audio_html` (`viewer.py:1519`).
   - DELETE the custom CSS mask button logic (`.sc-icbtn`) for controls (`viewer.py:2108-2134`) since the Svelte component will encapsulate its own clean transport controls.
5. **Rewire:** Replace the `gr.HTML` stage in `build_viewer_app` (`viewer.py:2009`) with the new `VideoScene(value=scene)`. Wire `VideoScene.end()` to advance `gr.State` and `gr.Gallery.select` (`viewer.py:2204`) to update the stage.

## 5. Resource Efficiency
- **Bytes:** Svelte compiles down to a tiny, optimized JS bundle, eliminating the bloat of injecting massive JS string blocks via `gr.HTML` on every load.
- **Requests:** Media is fetched asynchronously and lazily by the browser using range requests, rather than blocking the server's Python runtime.
- **Main-thread cost:** The 120ms DOM-thrashing `setInterval` is eradicated. Svelte's surgical DOM updates keep the browser thread idle, vastly improving performance on low-end mobile devices.
- **CPU-basic friendliness:** Zero video processing on the backend. No FFmpeg muxing required. The Python server merely passes typed URLs to the frontend.
- **Many viewers:** Highly scalable. State is tracked entirely client-side via Gradio sessions, and media streaming is offloaded to Hugging Face's CDN or local lazy file routes, meaning 1,000 concurrent viewers won't choke the Python process.

## 6. Risk + Unknowns
- **HF Spaces Specifics (SSR off & file routes):** Auth-gated spaces might return 401 Unauthorized for media assets on the `/gradio_api/file=` route if `login_check` behaves strictly for custom components. Additionally, deploying a compiled `.whl` custom component to a ZeroGPU Space adds build and supply-chain complexity.
- **Autoplay UX:** Browsers block autoplay-with-sound. Svelte requires us to render a one-time "Tap to Start" overlay.
- **The Single Cheapest Experiment:** Before writing the full player, scaffold a dummy `gradio cc` component that simply takes a `FileData` video and plays it. Build the `.whl`, push it to `macayaven/small-cuts-dev` (with Carlos's explicit approval per `CLAUDE.md`), and verify: 
  1. Does it render correctly with SSR off? 
  2. Does the `/gradio_api/file=` streaming route avoid 401s? 
  3. Does the `.whl` installation break the ZeroGPU environment startup?

## 7. Test / Verification Plan
- **Local Gate:** 
  - `ruff check src/` and `ruff format --check src/` to ensure no Python syntax regressions.
  - `pytest` to confirm the `hf_relay.py` hydration modifications still conform to the `Contracts v1.1.0` scene shape.
- **Live-Space Smoke:** 
  - Request approval to deploy to `macayaven/small-cuts-dev`.
  - Validate LCP (first frame should load in under 500ms). 
  - Test Autoplay UX: Ensure the "Tap to Start" overlay functions cleanly on initial load.
  - Test Sync Under Duress: Throttle the browser network to "Slow 3G" in Chrome DevTools and confirm that when the video buffer underruns, the audio pauses immediately and gracefully resumes when the buffer recovers.

## 8. Confidence + Strongest Dissent
**Confidence:** 0.85

**Strongest Dissent Against My Own Position:** 
"Building a custom Svelte component (C) violates the team's 'don't reinvent the wheel' mandate even more egregiously than our current `gr.HTML` hack. The absolute easiest, most Gradio-native, and robust path is **(B) with backend Muxing**. Storage is incredibly cheap, and FFmpeg muxing during the Modal upload/generation step is a one-time, backend cost. Muxing perfectly guarantees flawless native `gr.Video` sync, gives us out-of-the-box native `<track>` subtitles, provides native mobile OS lock-screen media controls (since there's only one cohesive media element), and allows us to use 100% pure Python without introducing npm, Node 20, `.whl` build steps, and a permanent frontend maintenance burden to a team that just wants to ship AI."
