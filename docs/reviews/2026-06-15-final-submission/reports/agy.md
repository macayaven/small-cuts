Here is the final submission read-only review based on the provided context, readiness document, and current diff:

### 1. Breakage Risk (Space, Engine, Upload, Tests)
**Severity: Low**
- **Diff Analysis:** The diff safely replaces `pick_frame` with `pick_key_frame` in video upload handlers. It correctly resizes the stage frame as the `card_thumb` in upload mode and prefers `frame_url` over `card_url` in the viewer gallery. 
- **Backward Compatibility:** `shelf_items` safely falls back to `card_url` if `frame_url` is missing, preventing breakage on legacy engine scenes that haven't generated a `frame.jpg`.
- **Tests:** The test suite accurately reflects the changes, and the previous run passed (`169 passed, 3 warnings`). The code changes are tight and localized to presentation logic.

### 2. Key-Frame Scoring Risks
**Severity: Low**
- **Analysis:** The deterministic scoring explicitly favors exposed, high-contrast, mid-clip frames. The risk of a "bad" thumbnail exists if the scene has sudden lighting changes or blurring, but in the context of this demo, a slightly blurry *real* POV frame is still superior to a generated title card.
- **Demo Alignment:** As noted in the readiness doc, a real frame makes the library look like an authentic feed of "just-happened clips" rather than artificial generations, which strongly supports the product story.

### 3. Strategic Soundness
**Severity: None (Strategically Excellent)**
- **Hackathon Alignment:** Sticking to the local Mac Studio path rather than Modal perfectly secures `achievement:offgrid` and `achievement:llama`. 
- **Prizes:** The end-to-end "glasses-to-ear-to-Space" loop makes an incredibly strong case for "Best Demo."
- **Constraints:** Correctly dropping `achievement:Tiny Titan` (since Qwen3-VL-8B > 4B) avoids disqualification risks on a technicality. The decision to keep the Space as a CPU-only viewer guarantees stability and zero cold-start latency for the judges.

### 4. What Exactly Should Be Tested Next?
**Severity: High (Operational Risk)**
Run the **Physical e2e gate** and the **Human Space gate** immediately, as these are the biggest remaining operational risks before recording:
1. **Physical Glasses to Engine:** Verify the iPhone app connects over Tailnet and successfully streams frames to the local engine.
2. **Audio Return:** Verify the engine returns the synthesized Kokoro TTS narration to the ear.
3. **Space Replay:** Verify the exact cut appears in the HF Space with the new POV thumbnail, generated title, synced captions, and no UI overflow on mobile Safari.
4. **Read/Write Gate Check:** Run the `curl` commands to ensure public GETs return `200` but POST/PATCH return `403`. 

### 5. What Should Be Deferred?
**Severity: Critical (Do not touch before submission)**
- **Modal Migration:** Do not move the inference to Modal.
- **Buffered POC / Streaming:** Do not add SSE or v2 parallel segment orchestration. Keep polling.
- **UI Rewrites:** Do not rewrite the player or alter storage semantics. Keep the public write block intact. 

**Conclusion:** The diff is clean, the strategy is sharp, and the fallback posture is sound. You are clear to run the final e2e gate and record the demo.
