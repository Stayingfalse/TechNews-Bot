# Second channel: daily "choose your adventure" dungeon crawl

Plan for a second channel on this server: one ~40 s Short/Reel a day of a tabletop adventure whose
next step is decided by viewers' comments (A/B/C). The look and timing come from the prototype
`episode_hybrid.html` (a single-file canvas player); the brief is the "Automated choose your own
adventure" project spec. This document maps that brief onto what this repo already does, lists
where the plan departs from the brief and why, and splits the work into milestones.

Nothing here changes the quiz channel.

## 1. What already exists and gets reused

Most of the brief's "daily job" is already built for the quiz, and channels were designed for this
([MULTI_ACCOUNT.md](MULTI_ACCOUNT.md)):

| Brief asks for | Already here |
|---|---|
| Daily render + upload at a fixed time, idempotent, restart-safe | `pipeline.py`: booked jobs render `RENDER_LEAD_MINUTES` before the slot, publish at the slot, per-platform results saved as they complete, restart recovery, deploy lease, missed-slot handling |
| `--dry-run` | `dry_run` on every job; `PUBLISH_ENABLED=false` renders and previews without posting |
| Read comments from the last video (YouTube Data API v3 + Instagram Graph API) | `cliffhanger.read_comments(job)` (both platforms, our own comments left out, errors per platform) |
| Post a comment listing the options | `youtube.comment()`, `instagram.comment()`; `link_previous()` already comments on yesterday's post |
| Voice from ElevenLabs v3 with emotion tags, cached | `render/voice.py` (per-line today; needs a one-clip + timestamps mode) |
| Logging, monitoring, retries | Discord previews/results/errors (`notify.py`), healthchecks.io (`health.py`), `/jobs/failed` + retry |
| Weekly AI step that books the week | The Monday Claude Code Routine pattern ([ROUTINE_PROMPT.md](ROUTINE_PROMPT.md)): writes JSON, POSTs it, the server validates (409/422 with every problem), the routine fixes and resends |
| Per-channel accounts | `channels.py` + per-channel tokens in `store.py` |

So the second channel is a new **content kind**, `adventure`, inside this server (step 5 of
MULTI_ACCOUNT.md), not a separate app with its own scheduler, publishers and `state.json`.

## 2. Architecture

```
Monday Routine (Claude, one call's worth of work)       This server (Python, Easypanel)
  read campaign state + last week's votes        ──►  POST /adventure/arc   (week of story nodes)
  write next week's arc (JSON, schema from              │ validate: node-cli validate (zod + graph checks
  GET /schema?kind=adventure)                           │           + headless smoke render of payload)
                                                        │ voice: one ElevenLabs v3 clip per node
                                                        │        (with-timestamps) → cues stored on node
                                                        │ book 7 slots for channel "adventure"
                                                        ▼
                                          daily, RENDER_LEAD before the slot (no AI):
                                            read yesterday's comments → tally → pick edge
                                            → fill recap → node-cli render → preview in Discord
                                          at the slot: upload YT + IG → comment the options
                                            → state update (one atomic write)
```

Two languages, on purpose:

- **`adventure/` (TypeScript, Node 20)**: the port of the prototype. Pure engine plus a CLI
  (`render`, `validate`, `cues`, `frame`). The prototype is Canvas 2D code; keeping it in TS keeps
  the port close to line-for-line, which is what "port it, do not redesign it" needs.
- **`app/` (Python, existing)**: scheduling, voting, voice generation, publishing, state. It calls
  the CLI as a subprocess with a JSON file in and an mp4 out, the same way it shells out to ffmpeg
  today.

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
  well inside the 3-minute target. M1 measures it.
- Licensing question disappears (Remotion is free only for individuals and companies of up to 3
  people; a company licence is needed above that).

If the visual match turns out to need Chrome's canvas (e.g. a shadow or text-rendering difference
we can't close), the engine stays the same and only the backend changes: `drawFrame(ctx, …)` takes
any `CanvasRenderingContext2D`-shaped context, so a Remotion `<Canvas>` composition or a Playwright
page can host it.

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
| `segs()` recap: "Forty-one of sixty-four of you picked…" | Number-free: "Most of you picked the iron door." Counts on screen only (§5). |

`die()`, `finalRot()` and the throw in `frame()` port unchanged: the face for `check.roll` is
rotated to face the camera at `land`, the tumble is `rot(AX1)·rot(AX2)` decaying to that rotation,
then a damped wobble. Landing is timed from cues so the die settles 0.5 s before the narrator says
the number (`t0 = checkB − 0.5 − 2.7`).

### Safe zones

At 1080×1920 the working numbers (verify in M1 against screenshots of both apps' overlays, and
render a debug frame with the overlay mask on):

| Zone kept clear | px (1080×1920) | prototype units (÷3) |
|---|---|---|
| Top (status, Shorts search / Reels header) | 0-220 | 0-73 |
| Bottom (caption, handle, music, progress) | 1440-1920 | 480-640 |
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
  hero: CreatureKey, foe?: CreatureKey,
  hook: [string, string], sub: string,
  story: string,                    // ≤ 20 words
  check?: { name: string, dc: 1..30, roll: 1..20 },
  after?: string,                   // ≤ 20 words
  ask: string,
  choices: [ {label, slot: "left"|"top"|"right", next: NodeId | null, recap: string} ] (2..3),
  default: 0..2,                    // used on zero votes
  tone?: Partial<Record<Segment, string>>,
  payload?: { scenes?, items?, props?, creatures? },   // same DSL as the built-ins
  // filled by the server, never by the AI:
  cues?: Cues, voice?: {file, chars, model, voice_id, confidence: "align"|"samples"|"low"},
  recap?: { pick: string, votes: [n,n,n], line_file: string }
}
```

`choices` is an object rather than the prototype's `[label, slot]` tuple so it can carry `next`
and `recap`; the engine adapter maps it back.

### Graph shape: departure from the brief (to confirm)

The brief says "each node has exactly one parent choice", which makes the week a tree. With 3
choices a day that is 3 + 9 + 27 + … nodes: 1,092 for seven days. Not workable.

Plan: a **layered DAG**. Each day is a layer of at most 3 nodes; each choice points at a node in
the next layer, and several choices may point at the same node (paths braid back together). A week
is at most 7 × 3 = 21 nodes, of which 7 get posted.

Because a node can now be reached by more than one choice, the spoken recap belongs to the
**edge**, not the node: every choice carries a `recap` line (≤ 12 words, number-free, e.g. "Most
of you chose the iron door. It groans open."). Voice:

- one clip per node (hook → story → check → after → CTA), as in the brief, and
- one short clip per edge (the recap line), generated in the same weekly batch.

At render time the edge clip and the node clip are joined (`[recap][0.4 s gap][node]`) and the
node's cues are shifted by the recap clip's length, so `plan()` sees one continuous timeline with a
`recap` cue. Node text must read right from every incoming edge; the specific consequence goes in
the edge's recap line. Validation checks it (§6).

Week-to-week: the Monday routine runs before Monday's vote closes, so the first layer of the new
arc is exactly the 3 targets of Monday's choices (the arc's `entry` maps each of Monday's choices
to a first-layer node).

### Campaign state

Kept by the server under `DATA_DIR/adventure/` (atomic temp-file + rename, as `store.py` does):

```
state.json      { node: NodeId, ep: int, hero: {class, look}, arc: ArcId,
                  last: {job_id, youtube_id, instagram_id}, history: [{ep, node, edge, votes, tiebreak}] }
arcs/<id>.json  validated arc + generated cues
voice/          node and edge clips, alignments
maps/           baked map PNGs by hash
```

`recap` is filled from the tally at render time and never written by the AI.

## 5. Daily job (no AI)

Runs as the existing render step for jobs of kind `adventure`:

1. Load state. Each day's job is booked for a layer of the arc, not a node: which node it shows is
   only known once yesterday's votes are in.
2. Read comments on yesterday's adventure post (`read_comments`), only those within 24 h of its
   `published_at`.
3. Parse votes: first valid vote per account (`platform:user id`). Valid = a standalone `A`, `B` or
   `C` (case-insensitive; `A`, `a!`, `(b)`, `I pick C`, `option b` count; `ABC` or `a or b` doesn't).
   Episode 0 parses `[A-C][1-3]` (`b2`, `B 2`) into class + look and tallies each separately.
   Parser is table-tested.
4. Tally across both platforms. Tie: `prng(hash(previous job id))` picks among the tied; zero votes:
   the node's `default`. Recorded either way.
5. Resolve the next node from the chosen edge, attach `recap {pick, votes}` and the edge clip,
   render, preview to Discord with the tally.
6. At the slot: upload (existing publishers; title/caption from the node), then comment the
   options under the new post ("A) Take the torchlit left · B) … · Comment a letter, next episode
   in 24 h"), and reuse `link_previous` on yesterday's post.
7. Update `state.json` in one atomic write after at least one platform succeeded.

Idempotency: the tally is stored on the job the first time it is computed; a re-render or retry
uses the stored tally (comments that arrive later don't change a decision already shown). The
`dry_run` path does steps 1-5 and writes nothing to state.

Pinning: the YouTube Data API has no endpoint to pin a comment, and neither does the Instagram
API: the options comment is posted, and pinning stays a manual tap (Discord message links it).
To verify in M5.

## 6. Weekly arc (one AI step)

Same pattern as the quiz: a Claude Code Routine on Monday evening reads
`GET /adventure/state` (current node, hero, last few episodes' story text and vote history, the
content library: scene/prop/creature keys), writes the next arc against
`GET /schema?kind=adventure`, and posts it to `POST /adventure/arc`.

This keeps "one AI step a week" (the routine is the only place a model runs) and uses the routine
we already operate instead of a server-side API key. If you'd rather the server call the Claude
Messages API with structured output directly, `/adventure/arc` doesn't change; only who calls it.

`POST /adventure/arc` validates, all-or-nothing, and returns every problem (409/422) so the
routine can fix and resend (the retry loop):

- zod schema (field limits; `story`/`after` ≤ 20 words; recap ≤ 12 words, no digits)
- graph: ≤ 3 nodes per layer, 7 layers, every `next` exists, every node reachable from `entry`,
  last layer's `next` is `null`, `default` in range
- every `check.roll` in 1-20 and the success/failure agrees with `after`'s tone tag
- payload: DSL keys and primitive shapes valid, names don't shadow built-ins unless marked
  `override`, and a headless smoke render (bake the map + draw 3 frames) succeeds with every
  payload item on screen
- estimated duration ≤ 45 s per node (words / 2.6 wps + fixed phases, as `plan()` without cues)

Then, in the background: voice generation (§7), map pre-bake, and booking 7 slots for the
channel. Discord gets the week summary with the arc as a small graph.

## 7. Voice pipeline

- Node clip: `scriptText(node)` (tags + `[long pause]` between segments) to
  `POST /v1/text-to-speech/{voice}/with-timestamps` with `eleven_v3`. `fromAlign()` on the returned
  alignment gives the cues, stored on the node. To check in M3: that `eleven_v3` returns alignment
  on that endpoint; if not, decode the mp3 and use `cuesFromSamples()`.
- Fallback: `cuesFromSamples()` on the mp3 alone. Its `sure` flag (the chosen gaps are among the
  longest) becomes `confidence: "samples"` or `"low"`; `low` sends a Discord warning with the cue
  table and retries the clip once.
- Edge clips: the recap line alone, no timestamps needed (its duration is the offset).
- Cost: about 21 node clips × ~650 chars + 63 edge clips × ~60 chars ≈ 17,500 characters a week,
  ~75k a month, on top of the quiz's voice use. ElevenLabs plan to be checked against that.
- Clips are cached by hash of (text, voice, model), so a re-render costs nothing.

## 8. Episode 0: character creator

A fixed template node, not AI-written: three hero classes (rogue, wizard, fighter: the existing
creatures) each shown in three looks (palette variants of the creature's part colours: `base`,
cloak, hair), the dice-less "Comment class + look, like B2" CTA, and a 3×3 card grid inside the safe
zone. The tally picks class and look independently; the result becomes `state.hero` and every
later node's `hero` is overridden with it (the AI writes `hero: "$hero"`).

## 9. Milestones

Stop for review after each.

| | Scope | Done when |
|---|---|---|
| **M1** | `adventure/` workspace; port of engine (dsl, gen, standee, die, plan, segs, cues) to TS with explicit PRNG; Skia backend; `render ep.json --audio clip.mp3 --out out.mp4`; safe-zone layout change; bundled fonts | EP1 from the prototype renders 1080×1920 30 fps with the prototype's audio in sync; golden frames at t = 1, 6, 12, 18.5 (die mid-air), 20 (landed), 30, 38 s; render time reported on 4 cores; side-by-side frames vs. prototype for sign-off |
| **M2** | zod schemas + JSON Schema export; content library (built-ins + payload merge); generator tests | Same seed ⇒ byte-identical map; props never overlap (min distance); path stays on floor pixels; all 4 `dir`s for all scenes; payload smoke render; `validate` CLI |
| **M3** | One-clip voice + with-timestamps + `fromAlign` → cues; sample-based fallback with confidence; edge clips + joining | Cues for EP1 from the API match the prototype's hand-set cues within 0.15 s; fallback flagged correctly on a clip without long pauses |
| **M4** | `kind=adventure` channel (MULTI_ACCOUNT steps 1-3, 5 for this channel only); `POST /adventure/arc` with all checks; background voice + map bake + booking; routine prompt `docs/ADVENTURE_ROUTINE_PROMPT.md` | A hand-written 7-layer arc books, renders every node in dry run; bad arcs get every problem back in one response |
| **M5** | Vote parsing, tally, tie-break, recap fill, state updates, options comment, dry-run end to end | Parser table tests; replaying a stored comment set always picks the same edge; restart mid-job doesn't double-post or double-advance |
| **M6** | Episode 0 template, looks as palette variants, `B2` parsing | Episode 0 renders and a mixed comment set yields the expected class + look |
| **M7** | Retries (TTS, render, upload: existing retry path), healthchecks for the adventure slot, cost log (TTS chars and Claude usage per week to the dashboard), dashboard channel switcher | A week runs unattended in dry run with Discord previews; then live |

## 10. Open questions

1. **Renderer**: Skia canvas instead of Remotion (§2)? Recommended yes.
2. **Graph**: layered DAG with per-edge recap clips instead of a tree (§4)? Needed for the numbers
   to work; the alternative is generating voice daily for the one chosen edge, which drops the
   edge clips (and could even speak the counts) at the cost of a TTS call on the daily path.
3. **Weekly step**: Claude Code Routine (as the quiz) or a server-side Messages API call?
4. **Accounts**: new YouTube channel + Instagram account. Instagram: the existing app (Instagram
   API with Instagram Login, `instagram_business_content_publish` + `…manage_comments`) covers it;
   in development mode the new account only has to be added as a tester, so no new app review.
   YouTube: the Google project's upload quota is shared (~6 uploads/day): two channels fit.
5. **Posting time**: same 12:00 slot as the quiz, or offset (e.g. 18:00) so the one render worker
   doesn't render both at once? The 24 h vote window is measured from each post.
6. **Content rules for the routine**: tone (spooky but all-ages), no gore, how often checks fail,
   arc length (does a "campaign" end, or run forever with weekly chapters?).
7. **Remotion licensing** only matters if (1) is "no": free for individuals and companies of up to
   3 people.
8. **Comment pinning**: no API on either platform (to confirm in M5); manual pin from the Discord
   link, or skip.
