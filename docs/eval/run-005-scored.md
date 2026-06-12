# Small Cuts — M1 Eval, Scored (run-005)

Judge: Codex (GPT-5 vision) scoring each narration against the actual photo.
Rubric: S(pecificity), G(roundedness), V(oice), 1-5. Pick rule: S>=4 and G>=4 on most images.

## Verdict

| Model | mean S | mean G | mean V | cells S>=4 & G>=4 | images passing (>=2/3 styles) |
|---|---|---|---|---|---|
| Qwen/Qwen2.5-VL-3B-Instruct | 3.73 | 3.13 | 2.43 | 9/30 | 2/10 |
| Qwen/Qwen2.5-VL-7B-Instruct | 3.47 | 3.40 | 3.03 | 7/30 | 1/10 |
| google/gemma-3-4b-it | 3.33 | 2.70 | 2.63 | 5/30 | 1/10 |

## Per-cell scores

| Image | Model | Style | S | G | V | Judge note |
|---|---|---|---|---|---|---|
| img-46AC-B1CB-06-0 | google/gemma-3-4b-it | deadpan | 4 | 3 | 5 | Good objects, but poster text and pot color are wrong. |
| img-46AC-B1CB-06-0 | google/gemma-3-4b-it | noir | 3 | 2 | 2 | TripAdvisor, pillow image, and poster text are invented. |
| img-46AC-B1CB-06-0 | google/gemma-3-4b-it | nature_doc | 3 | 2 | 1 | Key text and pot color wrong; no nature-documentary voice. |
| img-46AC-B1CB-06-0 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 5 | 4 | 5 | Strong specifics; digital sign and 2026 are questionable. |
| img-46AC-B1CB-06-0 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 3 | 3 | 2 | Real objects, but shelf placement is wrong and noir is thin. |
| img-46AC-B1CB-06-0 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 4 | 3 | 2 | Good text, but office/digital display are invented and style is weak. |
| img-46AC-B1CB-06-0 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 5 | 5 | 4 | Accurate specifics; slightly too expressive for deadpan. |
| img-46AC-B1CB-06-0 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 4 | 3 | 4 | Noir lands, but corkboard and long shadows are shaky. |
| img-46AC-B1CB-06-0 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 3 | 3 | 2 | Invents motion and lacks exact visible sign text. |
| img-46AC-B1CB-06-1 | google/gemma-3-4b-it | deadpan | 3 | 3 | 5 | Plain and factual, but sign text is wrong. |
| img-46AC-B1CB-06-1 | google/gemma-3-4b-it | noir | 4 | 3 | 2 | Good clothing/counter detail; wrong sign and weak noir. |
| img-46AC-B1CB-06-1 | google/gemma-3-4b-it | nature_doc | 4 | 2 | 1 | Wrong sign and blue screen; no nature-documentary voice. |
| img-46AC-B1CB-06-1 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 5 | 3 | 4 | Many specifics, but jeans, tied hair, laptop, waiting are unsupported. |
| img-46AC-B1CB-06-1 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 5 | 4 | 2 | Mostly grounded specifics, but little noir atmosphere. |
| img-46AC-B1CB-06-1 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 5 | 3 | 1 | Specific but monitor/sign details blur together; no documentary voice. |
| img-46AC-B1CB-06-1 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 4 | 4 | 4 | Mostly accurate, though man and desk activity are inferred. |
| img-46AC-B1CB-06-1 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 3 | 3 | 4 | Noir tone works; shadows and intrigue are embellished. |
| img-46AC-B1CB-06-1 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 2 | 2 | 2 | Mislabels store as office/workplace and stays generic. |
| img-46AC-B1CB-06-2 | google/gemma-3-4b-it | deadpan | 3 | 3 | 4 | White car is right; sign text appears invented. |
| img-46AC-B1CB-06-2 | google/gemma-3-4b-it | noir | 3 | 3 | 2 | Correct car and yellow line; sign text not visible. |
| img-46AC-B1CB-06-2 | google/gemma-3-4b-it | nature_doc | 2 | 2 | 1 | Sign text is garbled and style is not nature documentary. |
| img-46AC-B1CB-06-2 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 3 | 4 | 4 | Mostly accurate scene description, but red car is foreground, not parked. |
| img-46AC-B1CB-06-2 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 4 | 4 | 2 | Good visible specifics; noir voice is weak. |
| img-46AC-B1CB-06-2 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 4 | 5 | 1 | Grounded specifics, but no nature-documentary framing. |
| img-46AC-B1CB-06-2 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 4 | 5 | 4 | Accurate concrete details with a suitably flat voice. |
| img-46AC-B1CB-06-2 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 2 | 3 | 4 | Noir tone lands, but relies on invented mystery atmosphere. |
| img-46AC-B1CB-06-2 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 2 | 4 | 2 | Mostly grounded but generic and not documentary-like. |
| img-46AC-B1CB-06-3 | google/gemma-3-4b-it | deadpan | 4 | 4 | 5 | Concise and mostly accurate; wall location is slightly imprecise. |
| img-46AC-B1CB-06-3 | google/gemma-3-4b-it | noir | 4 | 3 | 2 | Invents sheet spilling onto floor; noir voice is weak. |
| img-46AC-B1CB-06-3 | google/gemma-3-4b-it | nature_doc | 5 | 3 | 1 | Good objects, but lantern glow and hanger are uncertain; not nature-doc. |
| img-46AC-B1CB-06-3 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 5 | 3 | 3 | Many specifics, but workspace, glow, and folded blanket are off. |
| img-46AC-B1CB-06-3 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 2 | 2 | 3 | Invents desk lamp, chair, and dim lighting. |
| img-46AC-B1CB-06-3 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 3 | 2 | 1 | Misreads bed as desk and room as clean office; not nature-doc. |
| img-46AC-B1CB-06-3 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 5 | 3 | 3 | Strong specifics, but wooden lamp, hook, and cool-room inference are unsupported. |
| img-46AC-B1CB-06-3 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 4 | 3 | 4 | Good noir mood, but glow and whispering shadows are invented. |
| img-46AC-B1CB-06-3 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 3 | 3 | 2 | Some grounded objects, but vent sound and dancing shadows are invented. |
| img-46AC-B1CB-06-4 | google/gemma-3-4b-it | deadpan | 2 | 1 | 4 | Invents pipe and Coca-Cola bottle; mostly generic. |
| img-46AC-B1CB-06-4 | google/gemma-3-4b-it | noir | 2 | 1 | 2 | Invents cigarette, smoke, and Coca-Cola bottle. |
| img-46AC-B1CB-06-4 | google/gemma-3-4b-it | nature_doc | 2 | 1 | 1 | Invents pipe and smoke; weak documentary voice. |
| img-46AC-B1CB-06-4 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 5 | 4 | 4 | Strong specifics; pink beer wording is questionable. |
| img-46AC-B1CB-06-4 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 5 | 4 | 1 | Grounded details, but almost no noir voice. |
| img-46AC-B1CB-06-4 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 4 | 3 | 2 | Misstates drinks; limited nature-documentary framing. |
| img-46AC-B1CB-06-4 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 5 | 3 | 2 | Mistakes napkin dispenser for bottle; adds interpretation. |
| img-46AC-B1CB-06-4 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 3 | 3 | 3 | Some noir tone, but invents note implication and bottle. |
| img-46AC-B1CB-06-4 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 4 | 3 | 1 | Park and Coca-Cola bottle are wrong; not documentary style. |
| img-46AC-B1CB-06-5 | google/gemma-3-4b-it | deadpan | 2 | 2 | 4 | Flat voice, but bench, awning, D&G, and hours are wrong. |
| img-46AC-B1CB-06-5 | google/gemma-3-4b-it | noir | 2 | 3 | 3 | Some real door details, but bench and D&G sign are false. |
| img-46AC-B1CB-06-5 | google/gemma-3-4b-it | nature_doc | 3 | 2 | 1 | Hours text is close, but bench and red D&G sign hallucinated. |
| img-46AC-B1CB-06-5 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 4 | 4 | 4 | Strong visible specifics; cap and inside-person claim are uncertain. |
| img-46AC-B1CB-06-5 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 3 | 2 | 3 | Wet street, held sign, and neon Yes You Can are false. |
| img-46AC-B1CB-06-5 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 4 | 3 | 1 | Good specifics, but Dog Friendly cap claim is wrong. |
| img-46AC-B1CB-06-5 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 3 | 3 | 4 | Mostly grounded, but walking individual and Spanish hours are unsupported. |
| img-46AC-B1CB-06-5 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 2 | 4 | 4 | Moody and mostly grounded, but low on concrete photo details. |
| img-46AC-B1CB-06-5 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 3 | 3 | 2 | Some grounded details, but bustling street and nature-doc voice are weak. |
| img-46AC-B1CB-06-6 | google/gemma-3-4b-it | deadpan | 4 | 4 | 5 | Mostly concrete and accurate; hand/directly-below details are shaky. |
| img-46AC-B1CB-06-6 | google/gemma-3-4b-it | noir | 3 | 3 | 3 | Some specifics, but blanket floor and gray doorway are questionable. |
| img-46AC-B1CB-06-6 | google/gemma-3-4b-it | nature_doc | 3 | 3 | 1 | Grounding slips on wall/floor/object; no documentary voice. |
| img-46AC-B1CB-06-6 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 3 | 2 | 2 | Invents floor lamp, footrest, bed sway; only partly deadpan. |
| img-46AC-B1CB-06-6 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 2 | 2 | 3 | Invents circular window and motion; noir mood is present. |
| img-46AC-B1CB-06-6 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 2 | 2 | 1 | Invents circular window and ajar door; lacks nature-documentary framing. |
| img-46AC-B1CB-06-6 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 3 | 3 | 4 | Accurate hand and lampshade, but person/table/checkered shirt are off. |
| img-46AC-B1CB-06-6 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 2 | 2 | 4 | No ceiling fan visible; mood fits noir better than facts. |
| img-46AC-B1CB-06-6 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 4 | 4 | 1 | Good visible-room details, but essentially no nature-documentary voice. |
| img-46AC-B1CB-06-7 | google/gemma-3-4b-it | deadpan | 5 | 4 | 5 | Strong specifics, but invents a key on the cabinet door. |
| img-46AC-B1CB-06-7 | google/gemma-3-4b-it | noir | 4 | 3 | 2 | Invents key and lock; voice is mostly plain description. |
| img-46AC-B1CB-06-7 | google/gemma-3-4b-it | nature_doc | 5 | 3 | 1 | Specific, but key claim is false and nature-doc voice absent. |
| img-46AC-B1CB-06-7 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 4 | 5 | 4 | Grounded cabinet and backpack details; slightly interpretive at the end. |
| img-46AC-B1CB-06-7 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 4 | 3 | 4 | Noir tone works, but invents a doorway-like threshold. |
| img-46AC-B1CB-06-7 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 3 | 2 | 1 | Invents open-plan office setting and misses nature-documentary framing. |
| img-46AC-B1CB-06-7 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 5 | 3 | 4 | Many real details, but falsely says the oven is open. |
| img-46AC-B1CB-06-7 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 4 | 5 | 4 | Grounded details with a competent moody noir atmosphere. |
| img-46AC-B1CB-06-7 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 5 | 4 | 1 | Mostly grounded kitchen details, but nature-documentary voice is missing. |
| img-46AC-B1CB-06-8 | google/gemma-3-4b-it | deadpan | 4 | 4 | 5 | Concrete and flat; likely one seated man, bin placement roughly right |
| img-46AC-B1CB-06-8 | google/gemma-3-4b-it | noir | 4 | 3 | 2 | Pale rectangle and single chair are questionable; weak noir voice |
| img-46AC-B1CB-06-8 | google/gemma-3-4b-it | nature_doc | 4 | 4 | 2 | Mostly accurate specifics, but barely nature-documentary narration |
| img-46AC-B1CB-06-8 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 3 | 2 | 2 | Invents logo text, pedestrians, sound, and man alone |
| img-46AC-B1CB-06-8 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 2 | 3 | 3 | Grounded broad scene, but invents solitude and inner reflection |
| img-46AC-B1CB-06-8 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 3 | 3 | 1 | Some accurate setting details, but invents thoughts and lacks documentary voice |
| img-46AC-B1CB-06-8 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 4 | 5 | 4 | Specific and grounded; relaxed urban setting is slightly interpretive |
| img-46AC-B1CB-06-8 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 4 | 3 | 4 | Good noir tone, but invents readable Cafe text and some shadows |
| img-46AC-B1CB-06-8 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 3 | 3 | 2 | Invents rustling soundtrack and sky detail; style is generic pastoral |
| img-46AC-B1CB-06-9 | google/gemma-3-4b-it | deadpan | 4 | 3 | 4 | Good desk, plant, staircase, box; invents hands/document and curved stairs. |
| img-46AC-B1CB-06-9 | google/gemma-3-4b-it | noir | 3 | 2 | 2 | Counter is right, but hands, brown plant, curved stairs are shaky. |
| img-46AC-B1CB-06-9 | google/gemma-3-4b-it | nature_doc | 2 | 2 | 1 | Wrong sweater color, hands/document, plant color; no nature-documentary voice. |
| img-46AC-B1CB-06-9 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 5 | 4 | 3 | Strong visible details; mental-state inference and glass railing weaken grounding. |
| img-46AC-B1CB-06-9 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 4 | 3 | 3 | Braids, sweater, chair work; desk lamp is invented. |
| img-46AC-B1CB-06-9 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 4 | 3 | 1 | Good person/table details; sign is mislocated and voice misses nature-doc style. |
| img-46AC-B1CB-06-9 | Qwen/Qwen2.5-VL-7B-Instruct | deadpan | 3 | 4 | 3 | Mostly grounded but generic, with contemplative inference instead of flat deadpan. |
| img-46AC-B1CB-06-9 | Qwen/Qwen2.5-VL-7B-Instruct | noir | 3 | 2 | 4 | Noir mood lands, but shadow, swaying braids, gaze are invented. |
| img-46AC-B1CB-06-9 | Qwen/Qwen2.5-VL-7B-Instruct | nature_doc | 3 | 4 | 1 | Grounded broad scene, but poetic contemplation is not nature-documentary narration. |
