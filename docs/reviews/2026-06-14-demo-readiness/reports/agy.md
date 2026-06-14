# Demo-Readiness Review Report

## Critical Findings
- **iOS App Memory Crash (OOM)**: The new `FrameClipBuffer` in iOS keeps up to 160 `CapturedFrame` instances in memory to cover a 4.0-second rolling window. If these hold full-resolution, uncompressed camera frames (e.g. `UIImage` or `CVPixelBuffer`), this will consume hundreds of megabytes to over a gigabyte of RAM. The OS will likely jet-sam (kill) the app for memory pressure very quickly during continuous live capture.

## Important Findings
- **Payload Latency Risk**: Sending 12 JPEGs encoded at up to 1024x1024 (q=0.9) inside a single base64 WebSocket message creates a massive payload (potentially 1.5–3 MB). Over a conference network, this upload time directly blocks the glasses-to-ear TTS loop, jeopardizing the low-latency illusion. 
- **Engine Decoding Blocks Inference**: In `session.py`, `_decode_frames` synchronously decodes all 12 JPEGs using `PIL.Image.open().load()` in the worker thread *before* `narrator.narrate` starts. This adds 100–250ms of blocking CPU time to the critical path, delaying the audio response.

## Minor Findings
- **Implicit Negative Timestamps**: In `MomentBuilder.swift`, `offsetMs` is calculated using `timeIntervalSince(capturedAt)`. Since the supplemental frames are from the past, this yields negative offsets. Fortunately, `session.py` sorts these offsets ascending, which naturally reorders them into the correct chronological playback sequence for the MP4. It works, but relies on a quirk.
- **Read-Gate Traversal Quirk**: `read_gate.py` uses a naive `path.startswith("/media/")` check, technically allowing paths like `/media/../v1/session`. However, downstream FastAPI routing and the gate's stripping of `Upgrade` hop-by-hop headers prevent any actual WebSocket exploitation. It is functionally safe.
- **Read-Gate Connection Exhaustion**: `read_gate.py` instantiates a new `httpx.AsyncClient` for every request. If the HF Space experiences high polling traffic, this defeats connection pooling and could exhaust ephemeral ports.

## Recommended Fix Order
1. **Reduce iOS Buffer Cap**: Drastically lower `maxStoredFrames` in `FrameClipBuffer` (e.g., to 24–30) or downscale the frames *before* appending them to the buffer to prevent OOM crashes.
2. **Aggressive Supplemental Downscaling**: Modify `MomentBuilder.swift` to encode the 11 extra frames at a much lower resolution (e.g., 320px or 512px max side) to slash the upload payload size, while keeping the primary selected frame at 1024px.
3. **Defer Engine Decoding**: In `session.py`, only decode the selected frame (`envelope["frames"][0]`) before kicking off `narrator.narrate()`. Decode the remaining 11 frames asynchronously or wait until the TTS `SceneAudio` is dispatched before processing them for the library.

## Deferred Work
- Refactoring the capture pipeline to stream true H.264 video fragments instead of bundling bulk base64 JPEGs.
- Tightening the path traversal logic in `read_gate.py`.
- Implementing `httpx.AsyncClient` connection pooling globally in the read gate.

## Confidence And Unknowns
- **Confidence**: High. The contract schema between iOS, the Engine, and the Viewer aligns correctly (`maxItems: 12`, `clip_url` propagation, etc.). The read-gate architecture securely protects the private-write paths as designed. The tradeoff of the 12-frame clip mostly affects performance, not functional correctness.
- **Unknowns**: The exact memory footprint of `CapturedFrame` depends on how the unlisted `FrameSource` delivers buffers. Furthermore, the true upload bandwidth on the day of the hackathon will dictate exactly how damaging the 12-frame payload size is to the end-to-end latency.
