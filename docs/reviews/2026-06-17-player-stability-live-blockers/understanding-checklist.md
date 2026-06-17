# Player Stability Live Blockers - Understanding Checklist

## Problem

- [x] Playback stutter can come from a race between intended playback state and transient `audio.paused` during audio startup.
- [x] Relay media proxying can block Gradio callbacks if the server downloads large media files synchronously.
- [x] Missing shelf media can make a scene disappear if listing drops the whole scene on `FileNotFoundError`.
- [x] The Python 3.13 invalid file descriptor message is a process-exit warning, not a runtime player failure.

## Solution

- [x] The playback clock now follows `window.__scUserWantsPlayback` plus the video-buffer stall guard, not transient `audio.paused`.
- [x] Relay clients default to direct HF media URLs in Space relay mode when no explicit override is set.
- [x] Missing shelf images now resolve to a lightweight inline placeholder so the library item remains visible.
- [x] Regression tests cover each live blocker.

## Impact

- [x] Play/resume should no longer flip video between play and pause while audio is still starting.
- [x] Gallery selection in Space relay mode avoids synchronous server-side media downloads by default.
- [x] Active uploads or temporarily missing bucket files should not make existing library rows collapse unpredictably.
