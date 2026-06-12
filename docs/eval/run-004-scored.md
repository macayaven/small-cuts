# Small Cuts — M1 Eval, Scored (run-004)

Judge: Codex (GPT-5 vision) scoring each narration against the actual photo.
Rubric: S(pecificity), G(roundedness), V(oice), 1-5. Pick rule: S>=4 and G>=4 on most images.

## Verdict

| Model | mean S | mean G | mean V | cells S>=4 & G>=4 | images passing (>=2/3 styles) |
|---|---|---|---|---|---|
| Qwen/Qwen2.5-VL-3B-Instruct | 2.73 | 2.70 | 2.50 | 4/30 | 1/10 |
| google/gemma-3-4b-it | 2.60 | 1.90 | 2.53 | 0/30 | 0/10 |

## Per-cell scores

| Image | Model | Style | S | G | V | Judge note |
|---|---|---|---|---|---|---|
| img-46AC-B1CB-06-0 | google/gemma-3-4b-it | deadpan | 2 | 1 | 2 | Invents man, coffee, mug, robin; only rating and map align |
| img-46AC-B1CB-06-0 | google/gemma-3-4b-it | noir | 3 | 2 | 4 | Good noir mood, but invents a person and actions |
| img-46AC-B1CB-06-0 | google/gemma-3-4b-it | nature_doc | 2 | 1 | 2 | Invents hand, person, motion, dust, Tuscan photo |
| img-46AC-B1CB-06-0 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 5 | 4 | 4 | Mostly accurate specifics; “digital sign” and office framing are shaky |
| img-46AC-B1CB-06-0 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 2 | 3 | 4 | Noir lands, but stack of papers and desk are unsupported |
| img-46AC-B1CB-06-0 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 1 | 1 | 3 | Invents male, coffee machine, cups, and ritual |
| img-46AC-B1CB-06-1 | google/gemma-3-4b-it | deadpan | 2 | 2 | 3 | Brochures, travel guides, expression, and transaction are unsupported. |
| img-46AC-B1CB-06-1 | google/gemma-3-4b-it | noir | 2 | 1 | 4 | Invents stapler, rain, window, tracing fingers, and emotional claims. |
| img-46AC-B1CB-06-1 | google/gemma-3-4b-it | nature_doc | 3 | 2 | 1 | Sign is close, but paperback, tremor, and blue screen are invented. |
| img-46AC-B1CB-06-1 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 5 | 4 | 4 | Strong visible details; clothing and sign wording are slightly off. |
| img-46AC-B1CB-06-1 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 4 | 4 | 3 | Mostly grounded, but adds inner states and overstates noir mood. |
| img-46AC-B1CB-06-1 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 1 | 2 | 1 | Generic and invents walking, turning away, urgency, and sequence. |
| img-46AC-B1CB-06-2 | google/gemma-3-4b-it | deadpan | 3 | 2 | 2 | Some visible shadow/car details, but invents damp pavement, sign text, man watching. |
| img-46AC-B1CB-06-2 | google/gemma-3-4b-it | noir | 3 | 1 | 4 | Noir mood lands, but wet asphalt, overcast sky, cone, pothole, sign text invented. |
| img-46AC-B1CB-06-2 | google/gemma-3-4b-it | nature_doc | 2 | 2 | 1 | Mostly not nature-documentary; invents wet pavement, overcast sky, clinic door focus. |
| img-46AC-B1CB-06-2 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 2 | 4 | 1 | Mentions visible red car and shadows, but tone is ominous, not deadpan. |
| img-46AC-B1CB-06-2 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 2 | 2 | 3 | Some glare and shadow fit, but invents a man walking past. |
| img-46AC-B1CB-06-2 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 2 | 4 | 2 | Mostly grounded but generic; weak nature-documentary framing. |
| img-46AC-B1CB-06-3 | google/gemma-3-4b-it | deadpan | 4 | 3 | 3 | Good objects, but invents chair/person mood. |
| img-46AC-B1CB-06-3 | google/gemma-3-4b-it | noir | 3 | 4 | 4 | Mostly grounded, noir mood lands. |
| img-46AC-B1CB-06-3 | google/gemma-3-4b-it | nature_doc | 3 | 3 | 1 | Grounded objects, but not nature-documentary voice. |
| img-46AC-B1CB-06-3 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 3 | 2 | 2 | Invents desk, door, and air-conditioner sound. |
| img-46AC-B1CB-06-3 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 2 | 1 | 3 | Invents sleeping user and exaggerated lighting. |
| img-46AC-B1CB-06-3 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 3 | 3 | 1 | Some specifics, but invents figure and lacks documentary style. |
| img-46AC-B1CB-06-4 | google/gemma-3-4b-it | deadpan | 2 | 1 | 2 | Invents cigarette, smoke, Coke bottle, unopened beer, and shirt location. |
| img-46AC-B1CB-06-4 | google/gemma-3-4b-it | noir | 3 | 2 | 4 | Noir voice works, but cigarette packet and Coke bottle are invented. |
| img-46AC-B1CB-06-4 | google/gemma-3-4b-it | nature_doc | 3 | 2 | 1 | Several visible anchors, but cigarette, smoke, condensation, and sleeve text are wrong. |
| img-46AC-B1CB-06-4 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 5 | 3 | 3 | Specific, but mislabels tray and invents prior visitor and precarious cap. |
| img-46AC-B1CB-06-4 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 5 | 4 | 2 | Mostly grounded specifics; beverage color is wrong and noir voice is weak. |
| img-46AC-B1CB-06-4 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 4 | 3 | 2 | Uses real objects, but invents untouched beer and bustling suburban context. |
| img-46AC-B1CB-06-5 | google/gemma-3-4b-it | deadpan | 3 | 2 | 2 | Invents scent, knuckles, D&G neon; voice too lyrical. |
| img-46AC-B1CB-06-5 | google/gemma-3-4b-it | noir | 2 | 1 | 4 | Noir lands, but rain and falling ID card are invented. |
| img-46AC-B1CB-06-5 | google/gemma-3-4b-it | nature_doc | 4 | 3 | 2 | Good visible details; invents sweat and misses nature-documentary voice. |
| img-46AC-B1CB-06-5 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 4 | 2 | 4 | Flat and specific; invents masked cap-wearing man talking. |
| img-46AC-B1CB-06-5 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 3 | 3 | 3 | Some real pose details; rain and clothing colors are wrong. |
| img-46AC-B1CB-06-5 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 2 | 4 | 1 | Mostly grounded but generic; nature-documentary style barely appears. |
| img-46AC-B1CB-06-6 | google/gemma-3-4b-it | deadpan | 3 | 3 | 2 | Vent and blanket grounded; phone beam and dust motes invented. |
| img-46AC-B1CB-06-6 | google/gemma-3-4b-it | noir | 2 | 1 | 4 | Invents ceiling fan, paper, sheet, blue glow, and hum. |
| img-46AC-B1CB-06-6 | google/gemma-3-4b-it | nature_doc | 2 | 2 | 1 | Some bedding detail, but invents sneaker and lacks documentary voice. |
| img-46AC-B1CB-06-6 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 2 | 1 | 2 | Invents ceiling fans, posture, armrests, and vent state. |
| img-46AC-B1CB-06-6 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 2 | 2 | 4 | Noir lands, but cigarette box, rain, and small table are invented. |
| img-46AC-B1CB-06-6 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 3 | 3 | 2 | Wicker lamps and circular light grounded; posture and vent phrasing wrong. |
| img-46AC-B1CB-06-7 | google/gemma-3-4b-it | deadpan | 3 | 2 | 2 | Good backpack/cabinet details, but invents list, apple core, unseen events. |
| img-46AC-B1CB-06-7 | google/gemma-3-4b-it | noir | 3 | 2 | 4 | Noir lands, but invents key and misstates oven/cabinet relation. |
| img-46AC-B1CB-06-7 | google/gemma-3-4b-it | nature_doc | 3 | 2 | 1 | Invents bag contents and open oven; not nature-documentary style. |
| img-46AC-B1CB-06-7 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 3 | 3 | 2 | Mostly visible scene, but claims empty bag, key, departure speculation. |
| img-46AC-B1CB-06-7 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 2 | 1 | 3 | Invents cigarette, detective, breeze; only backpack/counter are grounded. |
| img-46AC-B1CB-06-7 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 2 | 4 | 1 | Mostly grounded but generic, with little actual nature-documentary voice. |
| img-46AC-B1CB-06-8 | google/gemma-3-4b-it | deadpan | 2 | 2 | 2 | Umbrella and man fit, but glass, newspaper, timing invented. |
| img-46AC-B1CB-06-8 | google/gemma-3-4b-it | noir | 2 | 1 | 4 | Noir tone works; glasses, lemon, briefcase, truck, exhaust hallucinated. |
| img-46AC-B1CB-06-8 | google/gemma-3-4b-it | nature_doc | 2 | 1 | 2 | Mentions umbrella and paving, but briefcase, bottle, cyclist invented. |
| img-46AC-B1CB-06-8 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 3 | 3 | 2 | Tables, chairs, umbrella, tree visible; reflection and smile invented. |
| img-46AC-B1CB-06-8 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 2 | 2 | 3 | Solitary figure and cigarette are wrong; mood partly noir. |
| img-46AC-B1CB-06-8 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 1 | 3 | 2 | Mostly vague, misses visible details; falsely implies man is alone. |
| img-46AC-B1CB-06-9 | google/gemma-3-4b-it | deadpan | 2 | 2 | 2 | Mostly invents hand, document, action; tone too literary. |
| img-46AC-B1CB-06-9 | google/gemma-3-4b-it | noir | 2 | 2 | 4 | Noir works, but invents hands, paper, dust, waiting. |
| img-46AC-B1CB-06-9 | google/gemma-3-4b-it | nature_doc | 3 | 2 | 2 | Good counter and staircase; invents bread flyer and inner state. |
| img-46AC-B1CB-06-9 | Qwen/Qwen2.5-VL-3B-Instruct | deadpan | 3 | 3 | 3 | Braids and bowed head fit; yellow cushion is not visible. |
| img-46AC-B1CB-06-9 | Qwen/Qwen2.5-VL-3B-Instruct | noir | 2 | 1 | 4 | Noir tone, but candle, papers, floorboards, detective are invented. |
| img-46AC-B1CB-06-9 | Qwen/Qwen2.5-VL-3B-Instruct | nature_doc | 2 | 2 | 1 | Invents sign text and cafe; little nature-documentary voice. |
