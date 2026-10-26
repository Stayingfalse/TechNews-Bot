# Second channel: daily "choose your adventure" dungeon crawl

Plan for a second channel on this server: one ~40 s Reel a day of a tabletop adventure whose
next step is decided by viewers' comments (A/B/C). The look and timing come from the prototype
`episode_hybrid.html` (a single-file canvas player); the brief is the "Automated choose your own
adventure" project spec. This document maps that brief onto what this repo already does, lists
where the plan departs from the brief and why, and splits the work into milestones.

Nothing here changes the quiz channel, except the shared voice budget (§7).

## 0. Decisions so far

| | Decision |
|---|---|
| Platforms | **Instagram only** at launch. YouTube later: the publisher, comment reader and vote parser already handle it, so it's a per-channel `platforms` switch plus connecting the account. |
| Cadence | **Daily** at **09:00** Europe/London. Every other day only if the voice budget forces it (§7). |
| Vote window | From the post at 09:00 until **08:00 the next day**. At 08:00 the server reads the comments, picks the next scene, makes its voice-over, renders and posts at 09:00. |
| Weekly planning | Routine **5 hours after the quiz routine**: the quiz batch runs Monday 19:05, so this runs **Tuesday 00:05** (§6). |
| Voice credits | **10,000 a month shared with the quiz** (30,000 in the first month). Voice is made only for the scene that actually happens, on the day (§7). |

## 1. What already exists and gets reused

Most of the brief's "daily job" is already built for the quiz, and channels were designed for this
([MULTI_ACCOUNT.md](MULTI_ACCOUNT.md)):

| Brief asks for | Already here |
|---|---|
| Daily render + upload at a fixed time, idempotent, restart-safe | `pipeline.py`: booked jobs render `RENDER_LEAD_MINUTES` before the slot, publish at the slot, per-platform results saved as they complete, restart recovery, deploy lease, missed-slot handling |
| `--dry-run` | `dry_run` on every job; `PUBLISH_ENABLED=false` renders and previews without posting |
| Read comments from the last video | `cliffhanger.read_comments(job)` (Instagram and YouTube, our own comments left out, errors per platform) |
| Post a comment listing the options | `instagram.comment()` / `youtube.comment()`; `link_previous()` already comments on yesterday's post |
| Voice from ElevenLabs v3 with emotion tags, cached | `render/voice.py` (per line, cached by text) |
| Logging, monitoring, retries | Discord previews/results/errors (`notify.py`), healthchecks.io (`health.py`), `/jobs/failed` + retry |
| Weekly AI step that books the week | The Claude Code Routine pattern ([ROUTINE_PROMPT.md](ROUTINE_PROMPT.md)): writes JSON, POSTs it, the server validates (409/422 with every problem), the routine fixes and resends |
| Per-channel accounts | `channels.py` + per-channel tokens in `store.py` |

So the second channel is a new **content kind**, `adventure`, inside this server (step 5 of
MULTI_ACCOUNT.md), not a separate app with its own scheduler, publishers and `state.json`.

## 2. Architecture

```
Tuesday 00:05 Routine (the only AI step)                 This server (Python, Easypanel)
  read campaign state + vote history             ──►  POST /adventure/arc   (next week's story graph, text only)
  write next week's arc (JSON, schema from              │ validate: node-cli validate (zod + graph checks
  GET /schema?kind=adventure)                           │           + headless smoke render of payload)
                                                        │ pre-bake maps; book 7 slots (09:00) for channel "adventure"
                                                        ▼
                                          every day 08:00 (no AI):
                                            close the vote → tally → pick the next scene
                                            → voice-over for that one scene (ElevenLabs, ~250 credits)
                                            → node-cli render → preview in Discord
                                          09:00: post the Reel → comment the options
                                            → state update (one atomic write)
```

Two languages, on purpose:

- **`adventure/` (TypeScript, Node 20)**: the port of the prototype. Pure engine plus a CLI
  (`render`, `validate`, `cues`, `frame`). The prototype is Canvas 2D code; keeping it in TS keeps
  the port close to line-for-line, which is what "port it, do not redesign it" needs.
- **`app/` (Python, existing)**: scheduling, voting, voice, publishing, state. It calls the CLI as
  a subprocess with a JSON file in and an mp4 out, the same way it shells out to ffmpeg today.

```
adventure/
  package.json, tsconfig.json, vitest.config.ts      (npm workspaces)
  packages/shared/    zod schemas: Node, Arc, Payload, Cues; emits JSON Schema for /schema
  packages/engine/    no I/O: prng, dsl, gen (scene baker), standee, die/finalRot/throw,
                      plan, segs/scriptText, cuesFromSamples, fromAlign, drawFrame(ctx, state, t)
  packages/renderer/  CLI: render | validate | cues | frame; canvas backend + ffmpeg pipe
  fonts/              bundled OFL hand-lettering + display fonts (determinism)
  test/golden/        reference frames
```

The brief's `pipeline` package becomes the Python side (`app/adventure/`), because the scheduler,
publishers, comment readers and Discord already live there.

### Rendering backend: departure from the brief (to confirm)

The brief names Remotion. Recommended instead: **`@napi-rs/canvas` (Skia) drawing each frame in
Node and piping raw RGBA to ffmpeg**, for these reasons, to go in ARCHITECTURE.md:

- The engine is plain Canvas 2D (gradients, shadows, `ellipse`, `setTransform`, `getImageData`,
  `destination-out`), all supported by Skia canvas. Remotion adds React and a headless Chrome
  around code that doesn't need either.
- The server image is `python:3.12-slim`. Remotion needs Chrome Headless Shell plus its deps
  (~300 MB); Skia canvas is one prebuilt binary (~30 MB) plus Node.
- Determinism: one Skia version pinned in the lockfile, fonts loaded from files, no browser font
  fallback or GPU path differences, so golden frames are stable in CI.
- Speed: no per-frame screenshot. The map is a pre-baked bitmap, so a frame is one cropped
  `drawImage`, 1-3 standees, a few cards and gradients. Estimate 10-25 ms/frame at 1080×1920;
  1,200 frames (40 s @ 30 fps) across 4 worker threads plus x264 `veryfast` is about 1 minute,
  well inside the 3-minute target and the 08:00-09:00 hour. M1 measures it.
- Licensing question disappears (Remotion is free only for individuals and companies of up to 3
  people; a company licence is needed above that).

If the visual match turns out to need Chrome's canvas, the engine stays the same and only the
backend changes: `drawFrame(ctx, …)` takes any `CanvasRenderingContext2D`-shaped context, so a
Remotion `<Canvas>` composition or a Playwright page can host it.

## 3. Porting the prototype

Port as-is, with these mechanical changes:

| Prototype | Port |
|---|---|
| Global `s` + `rnd()` (Park-Miller 16807), reset inside `gen()` | `prng(seed)` closure passed explicitly. Keep the **same** algorithm and seeding (`(seed*7919+13) % 2147483647`) and call order, so `seed: 12` gives the prototype's map: that is the first golden test. |
| Globals `T`, `N`, `PL`, `SC`, `RF`, `FAIL`, `ctx`, `W`, `H` | `FrameState` object; `drawFrame(ctx, state, t)` is pure |
| 360×640 logical canvas | Keep 360×640 as the coordinate system, `ctx.scale(3,3)` for 1080×1920, so every constant ports unchanged |
| Map baked at 1200 px for 600 world units (2×) | Bake at 4.5× (2700 px): the camera zoom reaches 1.5 and the output is 3× the prototype, so 2× would look soft. Cached on disk by hash of `(scene, seed, dir, size, style, accessories, name, stains, payload)` |
| `FP` system cursive fonts, `Impact` | Bundled OFL fonts (e.g. Patrick Hand / Gochi Hand for hand-lettering, Anton for the hook). Font choice is a visual sign-off item in M1. |
| `parch()` defined twice | The second (shadowed, with tape) is the one in use; port only that |
| `tok()` | Unused: drop |
| `Math.random` in the "new seed" button | UI only; the engine bans `Math.random` (lint rule + test that stubs it to throw) |
| `document.createElement('canvas')` | `createCanvas()` from the backend, injected |
| `segs()`: one long script per episode (713 characters for EP1) | The lean script of §7: a short daily clip plus stock clips made once. `plan()` takes the clip boundaries as cues. |

`die()`, `finalRot()` and the throw in `frame()` port unchanged: the face for `check.roll` is
rotated to face the camera at `land`, the tumble is `rot(AX1)·rot(AX2)` decaying to that rotation,
then a damped wobble. Landing is timed so the die settles 0.5 s before the narrator says the
number (`t0 = checkB − 0.5 − 2.7`); with a stock clip for the number, `checkB` is known exactly.

### Safe zones

At 1080×1920 the working numbers (verify in M1 against screenshots of the Reels overlay, and
render a debug frame with the overlay mask on; keep Shorts-safe too so YouTube needs no relayout):

| Zone kept clear | px (1080×1920) | prototype units (÷3) |
|---|---|---|
| Top (status, Reels header) | 0-220 | 0-73 |
| Bottom (caption, handle, audio, progress) | 1440-1920 | 480-640 |
| Right rail (like/comment/share) | 920-1080 | 307-360 |
| Left margin | 0-48 | 0-16 |

The prototype breaks these and this is the one place the layout must change, not just port:

- The three choice cards sit at y 454-618 (1362-1854 px), inside the bottom zone, and run to
  x 346 (under the right rail). They move up to y ≈ 300-470 and narrow to x 16-300; the
  choice pins above the hero and the "WHAT DO YOU DO?" banner move up with them (the camera already
  zooms out at the CTA, so the hero sits higher).
- Narration card at y 52 and the "EPISODE n" tag at y 12: move to y ≥ 76.
- Hook title text at y 420-525 is fine. The red progress bar at the bottom is decorative and can
  stay under the overlay.

A test asserts every text/card bounding box at each phase lies inside the safe rect.

## 4. Data contracts

### Node (zod, `packages/shared`)

As the prototype's `EP1`, plus graph fields:

```ts
Node = {
  id: string,                       // "w44-d3-b"
  ep: number, scene: SceneKey, seed: int, size: 3..8, dir: "N"|"E"|"S"|"W",
  style: "ink"|"pencil"|"sepia"|"blueprint", accessories?: string[], name?: string, stains?: 0..4,
  hero: CreatureKey | "$hero", foe?: CreatureKey,
  hook: [string, string], sub: string,
  story: string,                    // ≤ 14 words (spoken; §7)
  check?: { skill: SkillKey, dc: 5..20, roll: 1..20 },
  after?: string,                   // ≤ 14 words (spoken)
  ask: AskKey,                      // one of the stock questions ("Which way?", "What do you do?", …)
  choices: [ {label, slot: "left"|"top"|"right", next: NodeId | null, pick: string} ] (2..3),
  default: 0..2,                    // used on zero votes
  tone?: { story?: Tag, after?: Tag },
  payload?: { scenes?, items?, props?, creatures? },   // same DSL as the built-ins
  // filled by the server on the day, never by the AI:
  cues?: Cues, voice?: {file, chars, credits, model, voice_id, confidence: "align"|"samples"|"low"|"none"},
  recap?: { pick: string, votes: [n,n,n] }
}
```

`choices` is an object rather than the prototype's `[label, slot]` tuple so it can carry `next`
and `pick` (the short name the recap uses: "the iron door"). `skill` and `ask` are keys into fixed
lists because their spoken versions are stock clips (§7).

### Graph shape: departure from the brief (to confirm)

The brief says "each node has exactly one parent choice", which makes the week a tree. With 3
choices a day that is 3 + 9 + 27 + … nodes: 1,092 for seven days. Not workable, even as text.

Plan: a **layered graph**. Each day is a layer of at most 3 nodes; each choice points at a node in
the next layer, and several choices may point at the same node (paths braid back together). A week
is at most 7 × 3 = 21 nodes of text, of which 7 get posted and voiced.

Because voice is now made on the day for the choice that actually won, the recap is simply part
of that day's clip ("You chose the iron door."), so a node can have several parents at no extra
cost. Node text must read right from every incoming choice; validation checks the `pick`
wording fits the recap sentence.

Week-to-week: the Tuesday 00:05 routine runs before Monday's vote closes (08:00 Tuesday), so the
first layer of the new arc is exactly the targets of Monday's choices (the arc's `entry` maps each
of Monday's choices to a first-layer node).

### Campaign state

Kept by the server under `DATA_DIR/adventure/` (atomic temp-file + rename, as `store.py` does):

```
state.json      { node: NodeId, ep: int, hero: {class, look}, arc: ArcId,
                  last: {job_id, instagram_id, youtube_id?}, history: [{ep, node, choice, votes, tiebreak}] }
arcs/<id>.json  validated arc
voice/          daily clips + alignments; stock/ library
maps/           baked map PNGs by hash
credits.json    voice credits used per month per channel (§7)
```

## 5. Daily job (no AI)

The adventure channel's slot is 09:00 with a 60-minute render lead (`RENDER_LEAD_MINUTES` becomes
per channel; the quiz keeps 45). At 08:00:

1. Load state. Each day's job is booked for a layer of the arc, not a node: which node it shows is
   only known once yesterday's votes are in.
2. Read the comments on yesterday's Reel (`read_comments`), keeping those posted before 08:00
   today (`timestamp < cutoff`). Top-level comments only.
3. Parse votes: first valid vote per account. Valid = a standalone `A`, `B` or `C`
   (case-insensitive; `A`, `a!`, `(b)`, `I pick C`, `option b` count; `ABC` or `a or b` doesn't).
   Episode 0 parses `[A-C][1-3]` (`b2`, `B 2`) into class + look and tallies each separately.
   Parser is table-tested.
4. Tally (both platforms once YouTube is on). Tie: `prng(hash(yesterday's job id))` picks among
   the tied; zero votes or comments unreadable: the node's `default`, with a Discord warning.
5. Resolve the next node, attach `recap {pick, votes}`, make the voice-over (§7), render, preview
   to Discord with the tally and the credits spent.
6. 09:00: post the Reel (existing publisher; caption from the node), comment the options under it
   ("A) Take the torchlit left · B) … · Comment a letter by 8am tomorrow"), and reuse
   `link_previous` on yesterday's Reel.
7. Update `state.json` in one atomic write once the post succeeded.

Idempotency: the tally and the chosen node are stored on the job the first time they're computed;
a re-render or retry reuses them (and the cached clip), so comments arriving later never change a
decision already shown, and a retry never spends credits twice. The `dry_run` path does steps 1-5
with a placeholder voice (no credits) and writes nothing to state.

Late 08:00 render: if the render fails, the existing retry runs; if 09:00 passes, the post goes out
when ready (the 6-hour missed-slot rule already covers a server outage), and the next day's
cutoff stays 08:00.

## 6. Weekly arc (the one AI step)

A Claude Code Routine, **Tuesday 00:05 Europe/London** (5 h after the quiz batch at Monday 19:05),
reads `GET /adventure/state` (current node, hero, recent episodes' text and vote history, the
content library: scene/prop/creature/skill/ask keys), writes the next arc against
`GET /schema?kind=adventure`, and posts it to `POST /adventure/arc`. It writes text only, so it
costs no voice credits.

Its first slot is Tuesday 09:00, 9 hours later: if the routine fails, the server warns in Discord
at 06:00 that Tuesday has no arc, the same way the quiz warns about empty days.

`POST /adventure/arc` validates, all-or-nothing, and returns every problem (409/422) so the
routine can fix and resend (the retry loop):

- zod schema (field limits; `story`/`after` ≤ 14 words; `pick` ≤ 5 words, no digits)
- graph: ≤ 3 nodes per layer, 7 layers, every `next` exists, every node reachable from `entry`,
  last layer's `next` is `null`, `default` in range
- every `check.roll` in 1-20 and the success/failure agrees with `after`'s tone tag
- payload: DSL keys and primitive shapes valid, names don't shadow built-ins unless marked
  `override`, and a headless smoke render (bake the map + draw 3 frames) succeeds with every
  payload item on screen
- spoken length per node ≤ the daily character budget (§7), and duration ≤ 45 s

Then, in the background: map pre-bake for all 21 nodes (cheap, no credits) and booking 7 slots.
Discord gets the week summary with the arc as a small graph.

## 7. Voice: only what happens, on the day

### The numbers

The prototype's EP1 script is 713 characters with its tags (479 spoken). Daily at that length is
~21,400 credits a month, twice the whole shared budget, and the brief's weekly generation of every
branch would be three times that again. Assuming eleven_v3 costs 1 credit per character (checked
in M3), the budget has to look like this:

| Monthly | Credits |
|---|---|
| Shared budget | 10,000 |
| Quiz (≈ 2 voiced quizzes a week × ~220 new characters; "Round two!" etc. are cached) | ~2,000 |
| Safety margin (a retake, a new voice line) | ~800 |
| **Adventure, 30 episodes** | **~7,200 → ≈ 240 a day** |

### Lean script: a short daily clip + stock clips made once

Everything that repeats is recorded once (from the first month's 30,000) and reused forever;
only the story is voiced each day:

| Segment | EP1 today | Lean version | Daily credits |
|---|---|---|---|
| Hook + recap | "You chose the rogue. Now survive the dark." + "Forty-one of sixty-four of you picked the Hooded Rogue." | "[whispers] You chose the iron door." (counts on screen only) | ~40 |
| Story | 76 chars | ≤ 14 words | ~85 |
| Check | "Stealth check. Difficulty thirteen." | stock: skill clip + "difficulty N" clip | 0 |
| Roll | "Seventeen. Success." | stock: 20 numbers × success/failure | 0 |
| After | 90 chars | ≤ 14 words | ~85 |
| CTA | 162 chars, reads all three choices | stock: the `ask` clip + "A, B or C? Comment your letter. Next episode tomorrow." Choices on screen only. | 0 |
| | **713** | | **~210-240** |

Stock library (made once, ≈ 2,500 credits): 20 roll numbers × 2 outcomes, ~10 skills, DC 5-20,
~8 ask questions, 2-3 CTA variants, the Episode 0 lines. Same voice, model and settings as the
daily clip.

The daily clip is the three variable segments in one request, with `[long pause]` between them,
through the with-timestamps endpoint; `fromAlign()` finds the segment starts, with
`cuesFromSamples()` as the fallback (flagged `low` → Discord). The server then lays out
`[daily: hook] [daily: story] [stock: skill + DC] [stock: roll] [daily: after] [stock: ask + CTA]`
with fixed gaps, so every cue is known exactly and the die lands on the spoken number by
construction.

### Guard rails

- **Ledger**: every request records its characters in `credits.json`; the server also reads
  `GET /v1/user/subscription` before each daily clip. Per-channel monthly allowances
  (`VOICE_BUDGET_QUIZ`, `VOICE_BUDGET_ADVENTURE`) shown on `/status`, and the quiz routine reads the
  quiz's remaining allowance before setting `voice: true` (a small quiz change).
- **Out of budget**: the episode still posts, without narration (on-screen text, music and dice
  sounds; `plan()` already has a no-cues timing mode), and Discord says so. Optionally switch the
  rest of the month to every other day; see open questions.
- **Cache**: clips are keyed by (text, voice, model, settings), so retries and re-renders cost 0.
- **No retakes by default**: a bad take is replaced only on request from Discord.

Every other day, if ever needed: the same graph, 15 episodes a month, ~480 credits each (room to
voice the choices again), and a 47-hour vote window. It's a booking change, not a design change.

## 8. Episode 0: character creator

A fixed template, not AI-written, voiced once into the stock library: three hero classes (rogue,
wizard, fighter: the existing creatures) each shown in three looks (palette variants of the
creature's part colours), the dice-less "Comment class + look, like B2" CTA, and a 3×3 card grid
inside the safe zone. The tally picks class and look independently; the result becomes
`state.hero` and every later node's `hero: "$hero"` resolves to it.

## 9. Milestones

Stop for review after each.

| | Scope | Done when |
|---|---|---|
| **M1** | `adventure/` workspace; port of engine (dsl, gen, standee, die, plan, segs, cues) to TS with explicit PRNG; Skia backend; `render ep.json --audio clip.mp3 --out out.mp4`; safe-zone layout change; bundled fonts | EP1 from the prototype renders 1080×1920 30 fps with the prototype's audio in sync; golden frames at t = 1, 6, 12, 18.5 (die mid-air), 20 (landed), 30, 38 s; render time reported on 4 cores; side-by-side frames vs. prototype for sign-off |
| **M2** | zod schemas + JSON Schema export; content library (built-ins + payload merge); generator tests | Same seed ⇒ byte-identical map; props never overlap (min distance); path stays on floor pixels; all 4 `dir`s for all scenes; payload smoke render; `validate` CLI |
| **M3** | Lean script; stock library generation; daily clip with timestamps + `fromAlign` + fallback; clip assembly; credit ledger + budget guard | Measured credits per character for v3 (and whether tags count); stock library made once; a daily clip ≤ 240 credits; cues exact on the assembled track |
| **M4** | `kind=adventure` channel (MULTI_ACCOUNT steps 1-3, 5 for this channel only: Instagram only, 09:00 slot, 60-min lead); `POST /adventure/arc` with all checks; map pre-bake + booking; `docs/ADVENTURE_ROUTINE_PROMPT.md` + the Tuesday 00:05 routine | A hand-written 7-layer arc books and every node renders in dry run (placeholder voice); bad arcs get every problem back in one response |
| **M5** | Vote parsing, 08:00 cutoff, tally, tie-break, recap, state updates, options comment, dry run end to end | Parser table tests; replaying a stored comment set always picks the same node; restart mid-job doesn't double-post, double-advance or double-spend credits |
| **M6** | Episode 0 template, looks as palette variants, `B2` parsing | Episode 0 renders and a mixed comment set yields the expected class + look |
| **M7** | Retries, healthcheck for the 09:00 post, cost log (credits and routine runs) on the dashboard, channel switcher; YouTube switch-on | A week runs unattended in dry run with Discord previews; then live on Instagram |

## 10. Open questions

**Need your call**

1. **Renderer**: Skia canvas instead of Remotion (§2)? Recommended yes.
2. **Shorter spoken script** (§7): story and aftermath voiced at ≤ 14 words each, the three
   choices shown and not read out, the check/roll/CTA from stock clips. That is what makes daily fit
   ~240 credits. OK, or would you rather go every other day and keep the fuller script?
3. **Out of credits mid-month**: post without narration (recommended), skip days, or switch to
   every other day for the rest of the month?
4. **Quiz share**: is ~2,000 a month right for the quiz (≈ 2 voiced quizzes a week), and should
   the quiz routine respect a hard allowance?
5. **Narrator voice**: an existing ElevenLabs voice (a deep "dungeon master"), or design one?
   Designing previews costs credits, so better done in the first month.
6. **Routine time**: Monday 19:05 + 5 h is **Tuesday 00:05**. OK, or did you mean earlier on
   Monday (e.g. 14:05)?
7. **Instagram account**: the new account must be a professional (creator/business) account,
   added as a tester to the existing Instagram app, then connected with
   `/oauth/instagram/start?channel=adventure`. Handle and name?
8. **Story rules**: tone (spooky but all-ages?), how often checks fail, and does the campaign
   run forever in weekly chapters or end in seasons (each starting with Episode 0)?
9. **Music and sound**: synthesised ambient loop plus dice sounds, made in code like the quiz's
   music (no credits)? Or the uploaded music library?

**Technical, answered during the milestones**

10. Whether eleven_v3 bills 1 credit per character and whether audio tags and `[long pause]`
    count (M3: measure with the subscription endpoint before/after a test clip).
11. Whether the with-timestamps endpoint returns alignment for eleven_v3 (M3; fallback ready).
12. Comment pinning: no pin endpoint on Instagram's or YouTube's API as far as known (M5:
    confirm; otherwise a manual pin from the Discord link).
13. Votes in replies to other comments: counted or not (plan: top-level only).
14. Remotion licensing only matters if (1) is "no".
