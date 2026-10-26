# Adventure renderer (@dungeoncrawlergram)

The video engine for the second channel: a daily choose-your-adventure dungeon crawl, ported from
the `episode_hybrid.html` prototype and drawn with Skia canvas (`@napi-rs/canvas`) straight into
ffmpeg. The plan is [../docs/ADVENTURE_PLAN.md](../docs/ADVENTURE_PLAN.md).

So far it renders **Episode 0**, the four launch videos that teach the format:

| Part | Shows | Vote (default if nobody comments) |
|---|---|---|
| 1 How it works | daily episodes, A/B/C comments, a real dice roll with its odds, defaults | which monster scares you most (A, skeletons) |
| 2 Pick a hero | fighter / rogue / wizard with their best skill, 3 hearts, permadeath | class (B, rogue) |
| 3 Pick a look | that class in three looks | look (A) |
| 4 The quest | Ellen vanished; the crypt; the hero's sheet | the first choice, each with its odds (the best odds) |

```bash
npm ci
npm run render -- examples/episode0-part1.json --out out/part1.mp4 [--music track.ogg] [--audio voice.mp3]
npm run render -- examples/episode0-part4.json --png out/stills --at 1,10,34     # stills for checking layout
npm test            # determinism, d20 faces, odds, schema, safe zones
npm run typecheck
```

Needs Node 20+ and ffmpeg. A 40 s video renders in about 45 s on 4 cores (1080×1920, 30 fps).

## Look

Painted paper miniatures on an old adventurer's map:

- **Map**: iron-gall ink on procedurally aged parchment (mottling, fibres, foxing, folds), walls with
  old-school hatching tufts outside and a soft relief shadow inside, a light wash and grid on the
  floors only; outdoors, a ground colour off the trail and a dirt wash on it.
- **Props**: shaded solids from the drawing language (`cyl`, `box`, `cone`, `sph`, `dome`), soft
  contact shadows, outlines taken from each fill.
- **Minis**: printed figures with a die-cut white paper edge on dark round bases; the rim is gold
  for the hero, red for foes.
- **Light**: darkness with flickering pools around torches, candles, glowing mushrooms and the
  hero's lantern; flames are drawn live each frame.
- **UI**: torn parchment cards, wax-seal letters, a red ribbon for the question, Cinzel for titles
  and Alegreya for text.

## Layout

- `packages/engine`: pure drawing code, no I/O. `map.ts` (scene generator), `draw.ts` (cards,
  seals, ribbon, paper minis, hearts, lighting, flames), `tex.ts` (paper grain), `dice.ts` (the d20; it lands on whatever face it's given), `sheet.ts` (classes,
  skills, odds), `episode0.ts` (the four launch videos). Seeded PRNG only; never `Math.random`.
- `packages/shared`: zod schemas for the specs the renderer accepts.
- `packages/renderer`: fonts, the map cache (`.cache/maps`), worker threads, ffmpeg.

Everything is drawn in the prototype's 360×640 coordinates and scaled ×3. Text stays inside
x 16-307, y 73-480 (clear of the Reels/Shorts caption, buttons and header; a test checks every
string in every beat).

Fonts: Cinzel and Alegreya (SIL Open Font License, in `fonts/`).
