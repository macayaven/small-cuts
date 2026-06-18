# Small Cuts — M1 Eval, Scored (run-006, dual judge)

Head-to-head: run-005 provisional pick **Qwen2.5-VL-7B** vs challenger **Qwen3-VL-8B** (prompt v3, temp 0.3, 10 glasses photos × 3 styles).

Two independent judges, different model families, same rubric and photos:

- **Judge A — Codex** (GPT-5 vision), same judge as run-004/005.
- **Judge B — Antigravity** (Gemini 3.1 Pro vision), added to address the single-judge weakness of the earlier picks.

Rubric: S(pecificity), G(roundedness), V(oice), 1-5. Pick rule: S>=4 and G>=4 on most images (>=2 of 3 styles per image).

## Verdict — both judges, same ranking

### Judge A: Codex (GPT-5)

| Model | mean S | mean G | mean V | cells S>=4 & G>=4 | images passing |
|---|---|---|---|---|---|
| Qwen/Qwen2.5-VL-7B-Instruct | 3.10 | 3.53 | 3.03 | 4/30 | 0/10 |
| Qwen/Qwen3-VL-8B-Instruct | 4.33 | 3.83 | 4.20 | 19/30 | 7/10 |

### Judge B: Antigravity (Gemini 3.1 Pro)

| Model | mean S | mean G | mean V | cells S>=4 & G>=4 | images passing |
|---|---|---|---|---|---|
| Qwen/Qwen2.5-VL-7B-Instruct | 3.20 | 3.07 | 3.57 | 1/30 | 0/10 |
| Qwen/Qwen3-VL-8B-Instruct | 4.77 | 4.33 | 4.60 | 26/30 | 9/10 |

**Final pick: `Qwen/Qwen3-VL-8B-Instruct`.** It passes the pick rule for both judges (7/10 and 9/10 images) while the run-005 provisional pick Qwen2.5-VL-7B passes 0/10 for both. The provisional pick is overturned; the two judged conclusions agree independently.

## Inter-judge agreement

| Dim | MAE | exact | within ±1 | Pearson r | Codex mean | Gemini mean |
|---|---|---|---|---|---|---|
| S | 0.50 | 53% | 97% | 0.76 | 3.72 | 3.98 |
| G | 0.75 | 35% | 90% | 0.51 | 3.68 | 3.70 |
| V | 0.60 | 60% | 85% | 0.70 | 3.62 | 4.08 |

Cohen's kappa on the pass/fail decision per cell: **0.59** (moderate agreement). Gemini runs ~0.3-0.5 hotter on S and V; G means are nearly identical. Disagreements concentrate in V (style taste) — on factual grounding the judges typically flag the *same* errors and differ only in severity (see per-cell notes). The model ranking is unaffected by judge choice.

## Per-cell scores (Codex / Gemini)

| Image | Model | Style | S | G | V | Codex note | Gemini note |
|---|---|---|---|---|---|---|---|
| img-46AC-B1CB-06-0 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 5/4 | 5/4 | 4/2 | Accurate visible details; slightly more polished than deadpan. | Flowery language like 'proudly displaying' breaks the requested deadpan style. |
| img-46AC-B1CB-06-0 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 3/3 | 4/4 | 4/2 | Grounded but misses specifics like camera, 8,6, plant, flyers. | The phrase 'beacon of trust' completely contradicts the cynical noir tone. |
| img-46AC-B1CB-06-0 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 4/4 | 3/3 | 2/2 | Map location and pins are uncertain; style not documentary. | Misses the 'humans as observed species' angle and hallucinates map pins marking POIs. |
| img-46AC-B1CB-06-0 | Qwen/Qwen3-VL-8B-Instruct | deadpan | 5/5 | 4/4 | 5/5 | Very specific; air conditioner brand appears misread. | Excellent specifics and deadpan tone; minor hallucination on AC brand name (ferroli). |
| img-46AC-B1CB-06-0 | Qwen/Qwen3-VL-8B-Instruct | noir | 4/5 | 2/4 | 5/5 | Strong noir, but invents a man and story. | Incredible hardboiled tone with a very perceptive observation about the artificial plant. |
| img-46AC-B1CB-06-0 | Qwen/Qwen3-VL-8B-Instruct | nature_doc | 5/5 | 4/5 | 4/5 | Detailed and mostly grounded; map place and lavender are uncertain. | Perfectly extracts and translates Catalan text while treating the room as a human habitat. |
| img-46AC-B1CB-06-1 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 4/4 | 4/3 | 4/5 | Good shop details; denim skirt and conversation are slightly off. | Misidentifies denim jacket tied at waist as a denim skirt. |
| img-46AC-B1CB-06-1 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 3/4 | 4/3 | 3/5 | Mostly grounded, but generic noir and denim skirt is inaccurate. | Misidentifies the denim jacket tied at waist as a denim skirt. |
| img-46AC-B1CB-06-1 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 2/3 | 3/4 | 3/5 | Open-plan office is wrong; few concrete photo specifics. | Mischaracterizes the retail repair shop as an open-plan office. |
| img-46AC-B1CB-06-1 | Qwen/Qwen3-VL-8B-Instruct | deadpan | 5/5 | 5/5 | 5/5 | Strong visible specifics: clothing, clerk, bag, accessories, extinguisher sign. | Perfectly identifies clothing layers, bag, and the EXTINTOR sign. |
| img-46AC-B1CB-06-1 | Qwen/Qwen3-VL-8B-Instruct | noir | 4/5 | 4/5 | 5/5 | Noir lands; typing and man are inferred beyond visible evidence. | Accurately captures pale yellow walls and the exact sign text. |
| img-46AC-B1CB-06-1 | Qwen/Qwen3-VL-8B-Instruct | nature_doc | 4/5 | 4/4 | 5/5 | Style works; blinking devices and bowed heads are not clearly visible. | Hallucinates packaged goods on the shelves as 'blinking devices'. |
| img-46AC-B1CB-06-2 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 3/4 | 3/3 | 5/5 | Sign text is inaccurate; otherwise grounded and flat. | Misreads PLACES as Plaça and inaccurately describes the red car's shadow. |
| img-46AC-B1CB-06-2 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 2/3 | 4/3 | 4/5 | Mostly grounded, but light on photo-specific details. | Inaccurately claims the red car casts a shadow over the sidewalk. |
| img-46AC-B1CB-06-2 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 2/2 | 4/5 | 2/2 | Grounded but generic; nature documentary voice barely appears. | Fails the nature doc prompt by lacking the humans as species observational framing. |
| img-46AC-B1CB-06-2 | Qwen/Qwen3-VL-8B-Instruct | deadpan | 5/5 | 5/4 | 5/5 | Strong visible specifics, including shadow, cars, sign, and facade. | Car is parked parallel, not angled; shadow shows both hands raised holding camera. |
| img-46AC-B1CB-06-2 | Qwen/Qwen3-VL-8B-Instruct | noir | 4/5 | 3/3 | 5/5 | Noir lands, but gender and movement are invented. | Hallucinates the brightly lit brick building as being a dark silhouette. |
| img-46AC-B1CB-06-2 | Qwen/Qwen3-VL-8B-Instruct | nature_doc | 4/5 | 4/5 | 3/4 | Specific and mostly grounded, but more poetic than documentary. | Accurate details like the dual-tone facade and barred windows; decent documentary tone. |
| img-46AC-B1CB-06-3 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 4/4 | 4/3 | 3/3 | Good objects; lamp casting light is uncertain and prose slightly decorative. | Ends too editorial for deadpan; hallucinates lamp is woven and lit. |
| img-46AC-B1CB-06-3 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 3/4 | 4/3 | 4/4 | Noir mood works; claims stay mostly visible but fairly generic. | Good noir mood but hallucinates an intricate, glowing lamp. |
| img-46AC-B1CB-06-3 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 3/4 | 4/3 | 1/2 | Mostly grounded, but lacks nature-documentary framing. | Fails nature doc voice; hallucinates unlit lamp casting shadows. |
| img-46AC-B1CB-06-3 | Qwen/Qwen3-VL-8B-Instruct | deadpan | 5/5 | 5/5 | 5/5 | Highly specific, accurate, and flatly observational. | Highly accurate specifics, correctly notes unlit lamp, perfect deadpan. |
| img-46AC-B1CB-06-3 | Qwen/Qwen3-VL-8B-Instruct | noir | 4/5 | 4/5 | 5/5 | Strong noir voice; face reflection wording slightly overstates. | Superb noir voice grounded perfectly in the actual visual elements. |
| img-46AC-B1CB-06-3 | Qwen/Qwen3-VL-8B-Instruct | nature_doc | 4/5 | 3/3 | 2/3 | Invents rings of light; more poetic than documentary. | Animates objects instead of humans; hallucinates concentric lamp light. |
| img-46AC-B1CB-06-4 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 4/4 | 3/2 | 4/4 | Good specifics, but invents Coca-Cola bottle and sipping. | Mistakes Coca-Cola napkin dispenser for a bottle and hallucinates sipping action. |
| img-46AC-B1CB-06-4 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 3/3 | 3/2 | 2/3 | Invents Coca-Cola bottle; noir voice is weak. | Hallucinates a Coca-Cola bottle; noir voice is somewhat generic. |
| img-46AC-B1CB-06-4 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 3/4 | 4/3 | 2/4 | Mostly grounded, but style is not documentary-like. | Misidentifies the glasses of beer as a bottle. |
| img-46AC-B1CB-06-4 | Qwen/Qwen3-VL-8B-Instruct | deadpan | 5/5 | 5/5 | 5/5 | Strong visible details and flat delivery. | Exceptional accuracy and specificity; perfectly maintains a deadpan tone. |
| img-46AC-B1CB-06-4 | Qwen/Qwen3-VL-8B-Instruct | noir | 5/5 | 3/4 | 4/5 | Strong voice, but beer counts/status and brand claim are wrong. | Great style but falsely claims the beer brand isn't in the frame. |
| img-46AC-B1CB-06-4 | Qwen/Qwen3-VL-8B-Instruct | nature_doc | 3/5 | 2/4 | 2/5 | Overwritten, invents motion and untouched drinks. | Invented head movement and falsely claimed the partially empty drinks were untouched. |
| img-46AC-B1CB-06-5 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 3/3 | 3/2 | 4/4 | Mostly visible setup, but cap and sunglasses appear invented. | Hallucinates cap and sunglasses on the reflected person, likely confusing it with the sticker. |
| img-46AC-B1CB-06-5 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 3/2 | 4/4 | 4/5 | Grounded scene with decent noir mood, limited concrete specifics. | Captures noir atmosphere well but relies on generic descriptions rather than specific image details. |
| img-46AC-B1CB-06-5 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 2/3 | 2/4 | 2/2 | Invents swaying leaves, breeze, and cool gray backdrop. | Fails the nature doc prompt, providing poetic observation instead of clinical species analysis. |
| img-46AC-B1CB-06-5 | Qwen/Qwen3-VL-8B-Instruct | deadpan | 5/5 | 5/5 | 5/5 | Strong visible specifics: sticker, QR code, pipes, hanging lights. | Flawless deadpan delivery with highly accurate, specific observations of sticker text and interior details. |
| img-46AC-B1CB-06-5 | Qwen/Qwen3-VL-8B-Instruct | noir | 4/5 | 3/5 | 5/5 | Noir lands, but infers language meaning and shadow drama. | Masterful noir voice that brilliantly integrates specific real-world details like the foreign posted hours. |
| img-46AC-B1CB-06-5 | Qwen/Qwen3-VL-8B-Instruct | nature_doc | 3/4 | 4/5 | 3/3 | Mostly grounded, but nature-documentary voice is weak and vague. | Good specifics, but the voice is too poetic and misses the detached clinical tone. |
| img-46AC-B1CB-06-6 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 3/4 | 3/2 | 3/3 | Good ceiling details, but invents seated person and table activity. | Hallucinates a person sitting at a table in the background; plaid is in foreground. |
| img-46AC-B1CB-06-6 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 2/2 | 4/4 | 4/4 | Mostly grounded, but sparse and ignores visible room specifics. | Captures the noir mood well but lacks specific details from the room. |
| img-46AC-B1CB-06-6 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 3/3 | 4/5 | 1/2 | Grounded room details, but not nature-documentary narration. | Fails to capture the nature documentary persona, sounding more like a generic description. |
| img-46AC-B1CB-06-6 | Qwen/Qwen3-VL-8B-Instruct | deadpan | 5/5 | 4/5 | 4/5 | Strong specifics; plaid shirt and pillow relation seem misread. | Excellent specific details and perfect, matter-of-fact deadpan delivery without hallucinations. |
| img-46AC-B1CB-06-6 | Qwen/Qwen3-VL-8B-Instruct | noir | 3/5 | 4/5 | 5/5 | Noir lands; concrete claims mostly check, with speculative gendered simile. | Evocative noir style grounded perfectly in the actual visual elements of the room. |
| img-46AC-B1CB-06-6 | Qwen/Qwen3-VL-8B-Instruct | nature_doc | 3/4 | 3/4 | 1/5 | Poetic, not nature-doc; overstates unseen subject and plural lanterns. | Good documentary tone, but incorrectly claims the subject is unseen when legs are visible. |
| img-46AC-B1CB-06-7 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 5/4 | 5/3 | 4/4 | Accurate visible details; slightly more polished than flat deadpan | Hallucinates straps hanging over the edge. |
| img-46AC-B1CB-06-7 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 3/3 | 2/1 | 3/5 | Invents ajar oven door and towel; noir only partly lands | Completely hallucinates an open oven and towel. |
| img-46AC-B1CB-06-7 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 2/2 | 4/4 | 1/2 | Mostly grounded but generic, not nature-documentary style | Reads like real estate copy, not nature documentary. |
| img-46AC-B1CB-06-7 | Qwen/Qwen3-VL-8B-Instruct | deadpan | 5/5 | 5/4 | 5/5 | Specific, accurate, and flatly observational | Accurate and deadpan, but misses the leaning shelf. |
| img-46AC-B1CB-06-7 | Qwen/Qwen3-VL-8B-Instruct | noir | 5/5 | 4/4 | 5/5 | Strong noir with real TEKA detail; leather is uncertain | Excellent noir style and spots the TEKA logo. |
| img-46AC-B1CB-06-7 | Qwen/Qwen3-VL-8B-Instruct | nature_doc | 4/4 | 4/4 | 2/2 | Grounded specifics, but poetic noir-adjacent rather than nature documentary | Tone is poetic and reverent, not nature documentary. |
| img-46AC-B1CB-06-8 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 4/4 | 3/2 | 4/4 | Good specifics, but men are not at separate tables. | Men are at the same table, not separate ones. |
| img-46AC-B1CB-06-8 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 3/3 | 4/2 | 3/4 | Mostly grounded, but noir voice is mild. | Hallucinates dappled shadows and motion blur. |
| img-46AC-B1CB-06-8 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 3/2 | 3/3 | 2/2 | Generic, invents breeze and whispering ambiance. | Fails the nature doc voice; just sounds peaceful. |
| img-46AC-B1CB-06-8 | Qwen/Qwen3-VL-8B-Instruct | deadpan | 5/5 | 4/3 | 5/5 | Strong visible details; passing cars are inferred. | Catches upside-down logo, but hallucinates dappled shadows. |
| img-46AC-B1CB-06-8 | Qwen/Qwen3-VL-8B-Instruct | noir | 3/3 | 2/2 | 5/5 | Strong noir, but invents drinks, roar, flickering streetlamp, damp pavement. | Hallucinates night tropes like yellow glow and damp pavement. |
| img-46AC-B1CB-06-8 | Qwen/Qwen3-VL-8B-Instruct | nature_doc | 4/4 | 4/5 | 4/4 | Grounded and observant, though more poetic than documentary. | Accurate details with a solid observational documentary voice. |
| img-46AC-B1CB-06-9 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 4/3 | 3/2 | 3/4 | Good visible details, but invents readable Café sign. | Hallucinates 'Café' text on the sign. |
| img-46AC-B1CB-06-9 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 3/2 | 4/4 | 4/5 | Grounded mood, but light on concrete photo specifics. | Generic details but captures the moody noir tone well. |
| img-46AC-B1CB-06-9 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 2/2 | 2/2 | 2/4 | Invents plant-tending and a glass ceiling. | Hallucinates a glass ceiling and tending to a plant. |
| img-46AC-B1CB-06-9 | Qwen/Qwen3-VL-8B-Instruct | deadpan | 5/5 | 5/5 | 5/5 | Accurate, specific, and flatly observational. | Extremely accurate details with a perfectly flat, observant tone. |
| img-46AC-B1CB-06-9 | Qwen/Qwen3-VL-8B-Instruct | noir | 5/4 | 3/4 | 5/5 | Strong noir, but invents dust, smells, and cigarette traces. | Strong noir voice with great specifics; minor atmospheric embellishments. |
| img-46AC-B1CB-06-9 | Qwen/Qwen3-VL-8B-Instruct | nature_doc | 5/5 | 4/5 | 2/2 | Specific and mostly grounded, but not nature-documentary voice. | Highly accurate details, but voice sounds more like architectural commentary. |

## Method

Same loop as runs 004/005, run twice: photos relayed from the Spark, HEIC→JPEG, one judge call per photo with all six narrations + rubric, strict-JSON S/G/V, aggregated offline. Judge B uses the identical prompt with the photo opened from disk instead of attached.
