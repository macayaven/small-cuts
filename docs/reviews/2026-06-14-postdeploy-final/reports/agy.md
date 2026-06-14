I have completed the read-only review and generated the report at [agy.md](file:///Volumes/mac-studio-ssd/workspace/small-cuts/docs/reviews/2026-06-14-postdeploy-final/reports/agy.md).

Here is a summary of the findings:
- **Storage-After-Disconnect & Regression Test Failure:** I identified the root cause of the "audio heard, but no Space video/captions" issue. The `asyncio.shield` method does not hold a strong reference to the background task in Python. When the WebSocket disconnects right after the audio sends, the scope is destroyed, the weak reference is lost, and the task is silently garbage-collected mid-execution before saving the scene. Adding a module or class-level set to hold strong references to active tasks will resolve this critical blocker.
- **Demo Readiness:** All the unchecked items on the list are correctly classified as requiring manual verification or hardware. There are no remaining automated steps to replace them.
- **Deferred Fixes:** Sticking to the quick-tunnel during the demo is the correct operational approach. Hugging Face Spaces run on datacenter IPs that are prone to triggering Cloudflare Bot Fight Mode challenges or blocks when going through named tunnels.

I have strictly followed your instruction to keep my process entirely read-only (no files were edited or deleted) and preserved all non-negotiable architectural mandates. Let me know if you would like me to assist with testing or applying the recommended changes!
round_tasks = set()
  # Inside _process:
  storage_task = asyncio.create_task(self._finish_scene_storage(...))
  _background_tasks.add(storage_task)
  storage_task.add_done_callback(_background_tasks.discard)
  ```

## Reject / Defer
- **Defer Named Tunnel Debugging**: Do not attempt to fix or bypass Cloudflare's blocking of `small-cuts.carloscrespomacaya.com` before the demo. Keep the Space pointed strictly at the known-good quick tunnel.
- **Defer iOS Backgrounding Handling**: The registration deep-link round trip through Meta AI puts the iOS app in the background. While the OS could suspend the app if it takes too long, the generous 120s `registrationTimeout` timebox handles this adequately for a controlled live demo.

## Demo Checklist Assessment
- The remaining unchecked items in `docs/demo-readiness.md` are **correctly classified**. They all require physical hardware testing (real iPhone, Meta Ray-Ban glasses), real human interaction (browser autoplay restrictions require a trusted DOM gesture), or final media assets (demo video, social post). None of these can be reliably verified through code review or automation alone.

## Storage-After-Disconnect Assessment
- **Insufficient**. As outlined in the Critical Blockers section, `asyncio.shield` does not prevent the Python garbage collector from destroying the unreferenced task once the parent `_process` scope is cancelled and destroyed. This explains both the missing Space video and the failing regression test.

## Bottom Line
- The architecture is extremely solid, thread-safe, and gracefully handles backpressure. Apply the 2-line strong reference fix to the storage task, stick to the Cloudflare quick tunnel, and proceed immediately to physical smoke tests.
