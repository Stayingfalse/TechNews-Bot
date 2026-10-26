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
| Platforms | **Instagram only** at launch, account **@dungeoncrawlergram** (creator account). YouTube later: the publisher, comment reader and vote parser already handle it, so it's a per-channel `platforms` switch plus connecting the account. |
| Cadence | **Daily** at **09:00** Europe/London. Every other day only if the voice budget forces it (§7). |
| Vote window | From the post at 09:00 until **08:00 the next day**. At 08:00 the server reads the comments, picks the next scene, makes its voice-over, renders and posts at 09:00. |
| Weekly planning | Routine **Tuesday 00:05** (5 h after the quiz batch at Monday 19:05) (§6). |
| Voice credits | **10,000 a month shared with the quiz** (30,000 in the first month). Voice is made only for the scene that actually happens, on the day (§7). |
| Renderer | **Skia canvas** (`@napi-rs/canvas`), not Remotion (§2). |
| Script | **Lean script** (§7): story and aftermath ≤ 14 words each, choices on screen only, stock clips for everything that repeats. |
| Out of credits | **Post without narration** (§7). |
| Narrator | **Obsidian – A Dark Fantasy Storyteller** (ElevenLabs library, `acrqYoDVmcpJemOxjC39`), chosen after the voice test (§7). |
| Story | Our own campaign on **SRD 5.2.1** (CC BY 4.0), each week adapting one openly licensed **one-page dungeon** (§8). **Seasons** of ~6 weeks; season 1 follows ***Childe Rowland***. **Teen and up.** |
| Dice | **Real rolls**: the AI sets skill and DC, the server rolls d20 + the hero's modifier on the day, odds shown on screen (§5). |
| Quiz voice | **2,000 credits a month**, a hard allowance (§7). |
| Hero death | **Permanent.** 0 hearts = a death episode, then a one-video Episode 0 for the next hero (§5, §10). |
| Launch | **Episode 0 as four videos** teaching the format, each with a default vote (§10). |
| Music | **CC0 tracks** from OpenGameArt per scene type, mixed with **synthesised** drones and sound effects; dice from Kenney's CC0 packs (§9). |

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

`die()`, `finalRot()` and the throw in `frame()` port unchanged: the face for `roll.kept` is
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
  check?: {                         // the AI sets the challenge, never the result (§5, Dice)
    skill: SkillKey, dc: 5|10|12|15|18|20, mode?: "normal"|"advantage"|"disadvantage",
    success: { after: string, choices?: Choice[] },   // after ≤ 14 words (spoken)
    fail:    { after: string, choices?: Choice[], harm?: 0|1 }
  },
  after?: string,                   // nodes without a check, ≤ 14 words (spoken)
  ask: AskKey,                      // one of the stock questions ("Which way?", "What do you do?", …)
  choices: Choice[] (2..3),         // Choice = {label, slot: "left"|"top"|"right", next: NodeId | null, pick: string}
  default: 0..2,                    // used on zero votes
  tone?: { story?: Tag, after?: Tag },
  payload?: { scenes?, items?, props?, creatures? },   // same DSL as the built-ins
  // filled by the server on the day, never by the AI:
  roll?: { dice: [1..20] | [1..20, 1..20], kept: 1..20, mod: int, total: int, ok: bool, p: number, proof: string },
  cues?: Cues, voice?: {file, chars, credits, model, voice_id, confidence: "align"|"samples"|"low"|"none"},
  recap?: { pick: string, votes: [n,n,n] }
}
```

`choices` is an object rather than the prototype's `[label, slot]` tuple so it can carry `next`
and `pick` (the short name the recap uses: "the iron door"). `skill` and `ask` are keys into fixed
lists because their spoken versions are stock clips (§7). A check's outcome can swap in its own
choices (a failed climb offers different options than a successful one); otherwise the node's
choices are used either way.

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
4. Tally (both platforms once YouTube is on). Tie: the roll HMAC (§5, Dice) keyed on yesterday's job picks among
   the tied; zero votes or comments unreadable: the node's `default`, with a Discord warning.
5. Resolve the next node, attach `recap {pick, votes}`, **roll its check** (Dice, below) and take
   that outcome's text and choices, make the voice-over for that outcome only (§7), render, preview
   to Discord with the tally, the roll and the credits spent.
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

### Dice: real rolls, real odds (departure from the brief)

The brief had the AI predetermine every roll. Instead the AI only sets the challenge (skill, DC,
advantage) and writes both outcomes; the server rolls on the day, with odds from the rules, so a
success is never scripted.

- **The hero's sheet** (from Episode 0, SRD 5.2.1 rules): level-1 standard-array scores per class,
  +2 proficiency on the class's skills. Roughly: fighter STR +3 (Athletics, Intimidation), rogue
  DEX +3 (Stealth, Sleight of Hand, Acrobatics, Perception), wizard INT +3 (Arcana, History,
  Investigation). Every SRD skill maps to its ability, so a wizard *can* try to climb, just badly.
  The sheet goes up a little each season (proficiency +3 from season 3, an ability bump at
  season 4: level-ups as the reward for surviving).
- **The roll**: total = d20 + modifier, success when total ≥ DC. Advantage rolls two dice and keeps
  the higher, disadvantage the lower (a choice can earn either: "sneak in with the torch out"). House
  rule for drama: a natural 20 always succeeds and a natural 1 always fails.
- **Odds are shown**, so viewers see it's genuine: the check card reads `STEALTH · DC 15 · 55%`
  before the throw and `14 + 5 = 19 · SUCCESS` after. `p` is computed exactly (with advantage:
  1 − (1 − p)²; disadvantage: p²).
- **Randomness**: `HMAC-SHA256(ROLL_SECRET, "<season>:<ep>:<node>:<check>")` turned into a uniform
  1-20 by rejection sampling. Unpredictable without the server's secret (nobody can work out
  tomorrow's roll, the AI included), yet the same on a retry or re-render, so the video, the voice
  and the stored state always agree. The roll is made once, when the vote closes, and stored on the
  job with `proof` (the HMAC input); the Discord preview lists it. Revealing the week's secret
  afterwards would let anyone check every roll, if that's ever wanted.
- **The die lands on the kept face** (`finalRot`), so the physics show the actual roll; with
  advantage the second die tumbles alongside and is knocked aside, dimmed.
- **Failing forward, with stakes**: a failure always moves the story on (a worse room, a lost item,
  a foe that's now awake), never a dead end. Dangerous failures (`harm: 1`) cost the hero a heart
  out of 3, shown on screen; rests (a node type) restore them. At 0 hearts the hero falls: that
  episode is a death scene, and the next day's Episode 0 brings in a new hero who picks up the
  quest where the last one fell. Teen+ peril with real loss, never gore.
- **Pacing**: the validator keeps every check between 25% and 90% and aims the week at about 1
  failure in 3; not every node has a check (talk, travel and rest nodes don't).
- **Tie-breaks** on votes use the same HMAC with the vote's own key, so they're fair the same way.

Because the roll happens before the voice-over is made, only the outcome that happened is voiced:
the AI writes both branches as text (free), the server voices one.

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
- every check has both a `success` and a `fail` branch, both valid from every incoming choice;
  each node's odds (§5, Dice) lie between 25% and 90%, and across the week the expected failures
  come to roughly 1 in 3 (the server computes the odds from the hero's sheet and reports them back
  to the routine)
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
branch would be three times that again. **Measured** in the voice test: eleven_v3 bills 1 credit
per character, audio tags included (a 72-character line with two tags cost 72 credits). So the
budget has to look like this:

| Monthly | Credits |
|---|---|
| Shared budget | 10,000 |
| Quiz: a hard allowance (≈ 2 voiced quizzes a week × ~220 new characters; "Round two!" etc. are cached) | 2,000 |
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
| Roll | "Seventeen. Success." | stock: the total (1-30) × success/failure, "Natural twenty!", "Natural one…" | 0 |
| After | 90 chars | ≤ 14 words | ~85 |
| CTA | 162 chars, reads all three choices | stock: the `ask` clip + "A, B or C? Comment your letter. Next episode tomorrow." Choices on screen only. | 0 |
| | **713** | | **~210-240** |

Stock library (made once, ≈ 3,000 credits): totals 1-30 × 2 outcomes, the two naturals, "with advantage" / "with disadvantage", ~12 skills, the 6 DCs,
~8 ask questions, 2-3 CTA variants, the Episode 0 lines, "you've lost a heart", the death and
new-hero lines. Same voice, model and settings as the daily clip. Tags are billed, so each line
carries one tag at most.

The daily clip is the three variable segments in one request, with `[long pause]` between them,
through the with-timestamps endpoint; `fromAlign()` finds the segment starts, with
`cuesFromSamples()` as the fallback (flagged `low` → Discord). The server then lays out
`[daily: hook] [daily: story] [stock: skill + DC] [stock: roll] [daily: after] [stock: ask + CTA]`
with fixed gaps, so every cue is known exactly and the die lands on the spoken number by
construction.

### Narrator voice

Chosen from the ElevenLabs voice library (listening to a library preview is free; only
generating costs credits):

| | Voice | Why |
|---|---|---|
| **Pick** | **Obsidian – A Dark Fantasy Storyteller** (`acrqYoDVmcpJemOxjC39`), deep, gravelly, American | The only library voice described as tuned for Eleven v3, and built for dark fantasy narration, villain and grizzled-soldier reads: matches the whisper → tense → grim range the script's tags ask for |
| Backup | **Cormac – The Irish Fantasy Storyteller** (`tEo3d4j7gzVojBL5Z4Pt`) | Made for D&D / tabletop narration, trained across dread, awe, urgency and humour; lighter, warmer, more "friendly DM" |
| Also good | Daniel – The Gruff Old British Wizard (`htZQqY7WtacRNV7s62Iy`), Zane – Deep Dramatic Late Night (`mfxPGiKweaQEsXJix2Ve`) | British alternatives: wizardly / horror-podcast |

**Test done** (26 Oct 2026, 144 credits): one take each of `[whispers] The iron door groans open…
[dramatically] something BREATHES.` on eleven_v3 (5.8 s Obsidian, 5.6 s Cormac). The pick is
confirmed by ear before the stock library is recorded, since every stock clip is tied to the voice;
changing voice later means re-recording the library (~3,000 credits). **Chosen: Obsidian.** Library voices need a paid ElevenLabs plan for API use,
which the quiz's voices already need.

### Guard rails

- **Ledger**: every request records its characters in `credits.json`; the server also reads
  `GET /v1/user/subscription` before each daily clip. Per-channel monthly allowances
  (`VOICE_BUDGET_QUIZ=2000`, `VOICE_BUDGET_ADVENTURE=7200`) shown on `/status`. The quiz's is
  hard: the quiz routine reads the remaining allowance before setting `voice: true`, and the server
  renders a quiz without voice rather than go over (a small quiz change).
- **Out of budget**: the episode still posts, without narration (on-screen text, music and dice
  sounds; `plan()` already has a no-cues timing mode), and Discord says so. The stock clips
  (rolls, CTA) are already paid for, so only the story lines go silent.
- **Cache**: clips are keyed by (text, voice, model, settings), so retries and re-renders cost 0.
- **No retakes by default**: a bad take is replaced only on request from Discord.

Every other day, if ever needed: the same graph, 15 episodes a month, ~480 credits each (room to
voice the choices again), and a 47-hour vote window. It's a booking change, not a design change.

## 8. Campaign sources

### What we can and can't adapt

| Source | Licence | Use it? |
|---|---|---|
| **SRD 5.2.1** (Wizards of the Coast's System Reference Document: rules, classes, spells, ~300 monsters incl. skeleton, goblin, wraith, ochre jelly, gelatinous cube, mimic, owlbear, minotaur, kobold, ghoul, bugbear, lich, dragons) | **CC BY 4.0**, irrevocable, commercial use fine with attribution | **Yes: the rules and monster layer.** Checks, DCs, classes and monsters come from here. |
| **One Page Dungeon Contest** entries (dungeoncontest.com; ~100 entries a year since 2009, each a whole dungeon on one page) | **CC BY-SA** (3.0 for older years, 4.0 for recent entries; some entries state their own) | **Yes: the weekly dungeons.** One page ≈ 6-12 rooms ≈ one week of 7 episodes. Licence checked per entry at intake. |
| **Basic Fantasy RPG** adventure modules (free PDFs; classic multi-level dungeons) | 4th edition moved the line to **CC BY-SA**; not confirmed for every older module | **Yes, per module after checking**: good for a longer multi-week arc later. |
| Other CC BY-SA OSR dungeons on itch.io (e.g. *Tomb of the Silver Mage*, Cairn adventures) | CC BY-SA 4.0 where stated | Case by case. |
| Public-domain myth and legend (Beowulf, Childe Rowland and the Dark Tower, Norse myths, Arthurian *Green Knight*) | Public domain | **Yes: season frames and villains.** |
| *Tomb of the Serpent Kings* (Skerples) | CC BY-NC-SA (non-commercial) | **No** while the channel may ever earn money. |
| Official D&D adventures (Lost Mine of Phandelver, Curse of Strahd, …) | Copyright; only the non-commercial Fan Content Policy | **No.** |
| Robert E. Howard / Lovecraft stories | Public domain in the UK, not all yet in the US | **No** (keeps the YouTube launch simple). |

Rules this puts on the routine and the content library:

- Monsters and names from the SRD only: none of Wizards' reserved creatures (beholder, mind
  flayer, displacer beast and others are not in the SRD) and no "Dungeons & Dragons"/"D&D" names or
  logos on screen or in titles. Hashtags like `#ttrpg`, `#dungeoncrawl` instead of the trademark.
- Attribution in every caption (Instagram captions can't link; the line is the credit):
  `Includes material from the SRD 5.2.1 by Wizards of the Coast LLC (CC BY 4.0).` plus, in a week
  adapted from a one-page dungeon, `Adapted from "<title>" by <author> (CC BY-SA 4.0).` The bio
  links a page listing every source with full licence links.
- Share-alike: a week adapted from a CC BY-SA dungeon is itself CC BY-SA (anyone may reuse those
  videos with credit). Fine for a channel like this; the caption says so.

### Shape of the campaign

A **season** is ~6 weeks, one site a week, held together by a public-domain legend as its spine.
Each season opens with Episode 0 (a new hero); a hero who falls mid-season is replaced by a new
Episode 0 the next day and the quest carries on.

**Tone: teen and up.** Dark fairy-tale peril, real danger and real loss (the hero can die), scary
monsters, morally grey choices. No gore described, no torture, nothing sexual, no swearing, no real
religions or real-world groups as villains. The routine prompt carries these rules and the
validator rejects banned words.

### Season 1: *Childe Rowland* (public domain)

Source: "Childe Rowland" in Joseph Jacobs, *English Fairy Tales* (1890). Burd Ellen runs round a
church widdershins and is carried off to the Dark Tower of the King of Elfland. Her brothers go
after her and don't return. The youngest learns two rules from Merlin: in Elfland, **speak to no
one who speaks to you, and eat or drink nothing**. On the way he asks a horse-herd, a cow-herd and a
hen-wife for the road, finds a green hill ringed with terraces, walks round it widdershins three
times saying "Open, door!", and inside, in a hall lit by a great glowing lamp, faces the King of
Elfland to free his sister and brothers.

Our version: the viewers' hero goes after their sibling, Ellen. The two rules become the season's
running temptation: choices that break them are always tempting (the food is warm, the voice knows
your name), and every broken rule is remembered and comes due in the finale (disadvantage on the
final checks, one per broken rule).

| Week | Site | Engine scene | Adapted from |
|---|---|---|---|
| 1 | Tue: **Episode 0**. Wed-Mon: the crypt under the church where Ellen vanished; the way into Elfland | `dungeon` ("The Sunken Altar", the prototype's map) | a crypt one-pager (e.g. *Tomb of the Forsworn* or *The Crypt of Crimson Ice*, licence checked at intake) |
| 2 | Merlin's cave: reach the seer, earn the two rules | `cave` | the legend + a cave one-pager |
| 3 | The fey wood: the horse-herd and the cow-herd, who both speak to you | `forest` | the legend |
| 4 | The hen-wife and the climb to the terraced green hill | `mountain` | the legend |
| 5 | Inside the hill: "Open, door!", the halls of Elfland, the feast you mustn't touch | `dungeon` | a one-pager for the halls |
| 6 | The Dark Tower and the King of Elfland (a payload creature); free Ellen and the brothers | payload scene | the legend |

Season 2+ use another legend as spine (Beowulf's mere, the Green Knight's chapel, a Norse
descent), chosen when season 1 is half done.

Intake (done by hand or by an occasional research routine, not the weekly one): pick an entry,
confirm its licence on its own page, and write a **site brief** for it in our own words (rooms as a
list, monsters mapped to SRD stat names, the secret, the treasure, 3-4 dramatic choice points).
Briefs and their licence/credit lines live in `DATA_DIR/adventure/sources/`; `GET /adventure/state`
hands the week's brief to the routine, which writes the 7-layer arc from it. The prototype's
"Sunken Altar" (dungeon, rogue, skeleton) stays as the season 1 opener so M1's golden frames double
as real content.

Starting shortlist to check at intake (2024 contest winner and winners' circle):
*Findlay's Lamp Emporium* (imps overrun a wizard's lamp-shop tower), *Tomb of the Forsworn* (a
knightly order's tomb), *The Crypt of Crimson Ice* (grave robbers find something worse below),
*Over the Moon* (a mouldy dungeon to reseal before a god wakes), *The Book of Wisdom* (a minotaur's
labyrinth library). Each one's own licence statement is confirmed before use.

## 9. Music and sound

Only tracks we can use on Instagram now and YouTube later without credits or Content ID claims:
**CC0** (public-domain dedication, no attribution needed). Library tracks go in a per-channel music
folder (`/data/music/adventure`, MULTI_ACCOUNT step 7), mixed under the voice with the existing
ducking.

| Scene | Track (OpenGameArt, all CC0) | Author |
|---|---|---|
| `dungeon` | *Dungeon Ambience*; *Loopable Dungeon Ambience* (low wind and drips) | yd; JaggedStone |
| `cave` | *Dark Cavern Ambient* (two loops); *Crystal Cave (song18)* | Paul Wortmann; cynicmusic |
| `forest` | *Dark Forest Theme*; *Forest Ambience* | cynicmusic; TinyWorlds |
| `mountain` / travel | *Medieval: Exploration* | RandomMind |
| Episode 0, tavern, rest | *Medieval: The Old Tower Inn*; *Medieval: The Bard's Tale* | RandomMind |
| Failed check / fight | *Battle Theme A* | cynicmusic |
| Season finale, sad turn | *Fantasy: Lament for a Warrior's Soul* | RandomMind |

Left out on purpose: CC BY / OGA-BY tracks (they'd need a credit line in every caption), Pixabay
(its tracks can carry Content ID claims on YouTube), Tabletop Audio and Kevin MacLeod (credit or a
licence needed).

**Synthesised in code** (no credits, different every episode, from the episode seed, extending
`render/music.py` and `render/audio.py`):

- an ambient drone bed under the library track (low pad, filtered noise "air", tuned to the
  scene: dripping for caves, wind for mountains),
- hook sting (low boom + reverse swell) at the episode title, a tension riser into the dice throw,
  success chime or failure thud on the landing, a soft "page turn" on the choice cards,
- torch crackle when torches are on screen.

**Recorded effects** from Kenney's CC0 packs: *Casino Audio* (dice rolls and lands, for the d20
throw, synced to the physics bounces) and *RPG Audio* (footsteps, doors, metal, cloth) for the hero's
walk and the scene's props. CC0, so no credit needed.

Licences are recorded in `assets/adventure/LICENSES.md` with each file's source URL, author and
licence as downloaded, so a claim can be answered.

## 10. Episode 0

### At launch: a four-part series (built: `adventure/`)

Reach is tiny at launch, so the first Episode 0 teaches the format over four short videos, one a
day, each ending in an easy vote that works with zero comments (the default is stated on screen:
"No votes? We go with B."):

| Part | Teaches | Vote → effect (default) |
|---|---|---|
| 1 How it works | a new episode daily at 9am, comment A/B/C, most votes wins, the dice are real and the odds are shown (a live demo roll), no votes = the default path | "What scares you most?" skeletons / goblins / wraiths → season 1's first foe (A) |
| 2 Pick a hero | fighter, rogue, wizard with their best skill; 3 hearts; heroes die for good | class (B, rogue) |
| 3 Pick a look | the chosen class in three looks; a fallen hero is replaced | look (A) |
| 4 The quest | Ellen vanished; the crypt below the church; the hero's sheet | the first real choice (force the gate / pick the lock / search), each card showing the skill and the hero's odds (the best odds) |

Fixed templates: the inputs are only the previous part's vote (`recap`), the fear, and the hero,
validated so the recap can't disagree with what it decided. Voiced once into the stock library.
Episode 1 (the first AI-written week) follows part 4.

### Later: one video

Each new season, and the day after a hero dies, a single Episode 0 video: the three classes ×
three looks on one screen and one comment like `B2` (class + look), default B1.

## 11. Milestones

Stop for review after each.

| | Scope | Done when |
|---|---|---|
| **M1** (in progress) | `adventure/` workspace; port of engine (dsl, gen, standee, die, plan, segs, cues) to TS with explicit PRNG; Skia backend; `render ep.json --audio clip.mp3 --out out.mp4`; safe-zone layout change; bundled fonts. **Done so far:** workspace, map generator, DSL, standees, d20, character sheet and odds, Skia + ffmpeg renderer with 4 workers, the four Episode 0 videos, safe-zone and determinism tests, CI. **Left:** the story-episode template (`plan`/`segs`/cues, EP1) and audio sync | EP1 from the prototype renders 1080×1920 30 fps with the prototype's audio in sync; golden frames at t = 1, 6, 12, 18.5 (die mid-air), 20 (landed), 30, 38 s; render time reported on 4 cores (**measured: Episode 0 renders 20-29 s per 26-41 s video**); side-by-side frames vs. prototype for sign-off |
| **M2** | zod schemas + JSON Schema export; content library (built-ins + payload merge); generator tests | Same seed ⇒ byte-identical map; props never overlap (min distance); path stays on floor pixels; all 4 `dir`s for all scenes; payload smoke render; `validate` CLI |
| **M3** | Voice test (Obsidian vs Cormac, ~120 credits); lean script; stock library generation; daily clip with timestamps + `fromAlign` + fallback; clip assembly; credit ledger + budget guard; music folder, synth beds and effects, Kenney dice synced to the throw | Measured credits per character for v3 (and whether tags count); stock library made once; a daily clip ≤ 240 credits; cues exact on the assembled track; audio mix signed off |
| **M4** | `kind=adventure` channel (MULTI_ACCOUNT steps 1-3, 5 for this channel only: Instagram only, 09:00 slot, 60-min lead); `POST /adventure/arc` with all checks; map pre-bake + booking; source briefs + credit lines (§8) for season 1; `docs/ADVENTURE_ROUTINE_PROMPT.md` + the Tuesday 00:05 routine | A hand-written 7-layer arc books and every node renders in dry run (placeholder voice); bad arcs get every problem back in one response; captions carry the right credits |
| **M5** | Vote parsing, 08:00 cutoff, tally, tie-break, recap, dice (sheet, HMAC roll, advantage, hearts, rules broken), state updates, options comment, dry run end to end | Parser table tests; 100,000 simulated rolls match the shown odds within 0.5% (normal, advantage, disadvantage, naturals); replaying a stored comment set always picks the same node and roll; restart mid-job doesn't double-post, double-advance or double-spend credits |
| **M6** | Episode 0 template, looks as palette variants, `B2` parsing | Episode 0 renders and a mixed comment set yields the expected class + look |
| **M7** | Retries, healthcheck for the 09:00 post, cost log (credits and routine runs) on the dashboard, channel switcher; YouTube switch-on | A week runs unattended in dry run with Discord previews; then live on Instagram |

## 12. Open questions

**Need your call:** none right now.

**Technical: answered during the milestones**

1. ~~Whether eleven_v3 bills audio tags~~: measured, 1 credit per character including tags.
2. Whether the with-timestamps endpoint returns alignment for eleven_v3 (M3; fallback ready).
3. Comment pinning: no pin endpoint on Instagram's or YouTube's API as far as known (M5: confirm;
   otherwise a manual pin from the Discord link).
4. Votes in replies to other comments: top-level only unless numbers show people vote in replies.
5. Each one-page dungeon's own licence statement, at intake (§8).
6. The server image is Python-only: M4 adds Node 22 to the Dockerfile (or a second container) so
   the server can call the renderer.
