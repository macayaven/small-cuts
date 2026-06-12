# Prompt A/B: judged comparison of v1 (run-002) vs v2 (run-004)

Judge: Codex (GPT-5 vision), scoring every narration against the actual photo,
rubric S/G/V 1-5, pick rule S>=4 and G>=4. Same 10 photos, same judge, same
model (gemma-3-4b-it) — only the system prompt differs between the two runs.

## Result

| Variant | n | mean S | mean G | mean V | S>=4 & G>=4 |
|---|---|---|---|---|---|
| gemma-3-4b-it @ v1 prompt (run-002, strict) | 30 | 3.37 | 2.57 | 2.53 | 2/30 |
| gemma-3-4b-it @ v2 prompt (run-004, "find the story") | 30 | 2.60 | 1.90 | 2.53 | 0/30 |
| Qwen2.5-VL-3B @ v2 prompt (run-004) | 30 | 2.73 | 2.70 | 2.50 | 4/30 |

## Conclusions

1. **v2 was a pure loss**: −0.77 S, −0.67 G, ±0.00 V for gemma. The style
   examples already carry the voice; the extra "find the story / lead with the
   human moment" license only licensed confabulation (invented rain, people,
   actions). Reverted and hardened as v3 in `styles.py`.
2. **Model size is the real ceiling**: even strict v1 passes only 2/30 cells.
   Qwen2.5-VL-3B is the best so far (G 2.70). Qwen2.5-VL-7B is the most
   important untested candidate (was blocked on torchvision, fixed in run-003).
3. **Generation temperature was 0.7 with sampling in both runs** — a second
   G-suppressor, lowered to 0.3 default (SMALL_CUTS_TEMPERATURE) for run-005.
4. run-005 bundles prompt v3 + temp 0.3 + Qwen-7B. The v3-vs-v1 deltas are
   confounded with the temperature change — accepted; both push G the same
   way and the deadline is June 15.

## Method note

Scoring loop is fully automated: `fetch-eval-photos` workflow relays photos
off the Spark → HEIC→JPEG → one `codex exec -i <photo>` call per image with
the report's narrations → strict-JSON S/G/V → aggregate. Re-running a scoring
pass on a new eval report costs ~7 minutes and zero manual effort.
