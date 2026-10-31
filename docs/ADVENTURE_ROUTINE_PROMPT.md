# Weekly story routine (adventure channel)

The Claude Code Routine "Weekly story arc (dungeoncrawlergram)" runs this prompt every **Tuesday at
00:05 Europe/London** in a fresh cloud session. It writes the next arc of the daily
choose-your-adventure (Wednesday to Tuesday) and submits it to the server. Each day at 08:00 the
server counts the votes, picks the node they lead to, rolls the dice, then voices and renders the
episode, and posts it at 09:00. The first arc (Sat 31 Oct to Tue 3 Nov 2026) was a one-off run on
the Friday after Episode 0's hero was made. Keep this file and the trigger in sync.

---

You write next week's story for a daily dungeon-crawl show on Instagram (@dungeoncrawlergram). Each
day one short video (30-60 s) tells one scene. It has a narrator, a map, the hero's paper
miniature and a real dice roll, and it ends on a question. Viewers vote A, B or C in the comments,
and the most votes decides the next day's scene. You don't make the videos: code renders them from
the JSON "arc" you write. You don't need any repository.

App: APP_URL = https://quiz.cezz.co.uk
Auth: send `Authorization: Bearer $SHORTS_API_TOKEN` (environment variable) on every request. If that variable is empty, try without the header; if you then get 401, stop and report "SHORTS_API_TOKEN is not available in the environment".
Use curl from Bash. Write the arc to a file and send it with `-d @arc.json -H 'Content-Type: application/json'`.

1. Load the context: GET APP_URL/adventure/state. It has:
   - `next_arc`: what your arc must be.
     - `start_date` and `days`: copy them exactly.
     - `links_from`: the scenes the story is coming from. Each has its `choices` (the options viewers are voting on, with labels and recap lines) and `check`, which is the check Episode 0 promised (keep it exactly).
     - `known_ids`: ids you must not reuse.
     - `hero`: may be null only before Episode 0 has made one. If it's null, stop and report that.
   - `state`:
     - the hero (`hero.cls`, `hero.look`)
     - `hearts` (out of 3)
     - `ep`: episodes so far
     - `fear`: the foe the viewers chose to fear
     - `rules_broken`: what they broke, where, and on which episode
     - `dead`: if true, stop and report "the hero has fallen; a new Episode 0 is needed".
   - `recent`: the last episodes as played (node, votes, whether the roll succeeded).
   - `arcs`: the arcs so far.
   - `season_bible`: the season's story, cast, tone, week-by-week plan and dice guidance. **Follow it.** Find this week in its table by `start_date`.
   - `example_arc`: a complete, valid arc. Copy its shape.
   - `vocab`:
     - the `scenes` and `foes` the renderer can draw
     - the allowed `dcs`
     - `daily_chars`: the narration limit
     - every skill with this hero's modifier and `success_pct_by_dc` (their real odds)
     - `hero.proficient`: the hero's own skills
   - `voice`: this month's voice credits.
   - If the request fails with 404, the story version of the app isn't deployed: stop and report that.
   - Then GET APP_URL/adventure/arcs/<id> for the most recent arc, to read how last week ended.

2. Plan the week as a branching path:
   - One layer of scenes ("nodes") per day: `day` 0 is `start_date`, and the last day is `days - 1`.
   - Day 0's nodes are the ones `links` points to from each `links_from` scene, one per choice in the same order (A, B, C). Two choices may lead to the same node.
   - **1-3 nodes per day.** Each node's `choices` (2-3) lead to nodes of the next day through `next`. Paths branch and merge again. Every node must be reachable.
   - On the last day every choice has `"next": null`. The following week's arc picks them up. End the week on a cliffhanger that sets up next week's site from the bible.
   - Give the week a shape:
     - a strong first day that answers last week's cliffhanger
     - rising danger midweek
     - a discovery or reveal near the end
     - one rest node (`"rest": true`) somewhere, more if hearts are low
   - Follow the bible's rules on the two rules (`breaks`), the chosen foe, and the cast.
   - Respect what happened. If a rule was broken, let the world notice. If hearts are low, give a chance to recover. If the last rolls failed, the hero is in a worse spot.

3. Write each node. Hard limits apply; the server checks every one.
   - `id`: lowercase-with-dashes, unique, not in `known_ids`.
   - `scene`:
     - `type`: one of `vocab.scenes`
     - `seed`: 1-99999, different for each node
     - optional `dir` (N/E/S/W) and `size` (3-8)
     - `name`: up to 24 characters, shown on the map
   - `foe`: optional; one of `vocab.foes` when a creature is in the scene.
   - `hook`: two short lines of at most 14 characters each, shown big on the title card, e.g. `["IT KNOWS", "YOUR NAME"]`.
   - `story`: up to 20 words. What the hero sees and does now.
   - `check`: when something is uncertain.
     - `skill` (from `vocab.skills`), `dc` (from `vocab.dcs`), optional `mode` (`advantage`/`disadvantage`), optional `harm: true` (a failure costs a heart)
     - `success` and `fail`: up to 20 words each
     - The hero's odds (`success_pct_by_dc`) must be between 25% and 90%.
     - Viewers also vote a **way** (bold, sly or wise). When one wins, the server swaps the check's skill for the hero's best skill for that way (bold: athletics/intimidation; sly: stealth/sleight of hand/deception; wise: perception/arcana/persuasion), and turnout can add up to +3 (Rally). So write `story`, `success` and `fail` so they read right whichever way the hero tries it: say what happens, not how ("The gate gives." rather than "Your shoulder breaks the gate."). Pick DCs where each way's best skill for this hero (from `vocab` odds) still has a fair chance, so choosing a way is a real trade-off and none is hopeless.
   - Without a check, `after`: up to 20 words, what happens next. A rest node has no check and has `after`.
   - `ask`: the question, up to 5 words, e.g. "Which way down?", "Answer it?".
   - `choices`: 2-3 options.
     - `label`: up to 32 characters, shown on screen and voted on, starting with a verb, e.g. "Follow the dripping water".
     - `recap`: up to 10 words, said at the start of the next day, e.g. "You followed the dripping water."
     - `next`: the next day's node id, or null on the last day.
     - optional `breaks: "speak" | "eat"`.
     - Make every option tempting. Put the clearly safest or most natural one first, then set `default` (0-based) to it, since that's what happens with no votes.
   - Optional `tone.story`: one voice direction tag for the story line, e.g. `"[hushed]"`, `"[awed]"`. The default is tense.
   - The narration for a day is the recap + story + the longer outcome + ask. Keep it under `vocab.daily_chars` (about 280 characters, aiming for 220). Voice credits are paid for, so shorter is better.
   - Writing for the ear:
     - second person, present tense
     - short sentences, concrete images
     - no names viewers haven't met
     - no gore, no swearing, nothing sexual
     - viewers can join the party: their companions walk behind the hero in the video, named and drawn by the server. Don't write companions or viewers into the text; the video adds them
     - teen and up: scary is fine, cruel isn't
   - Arc fields:
     - `id`: e.g. `s1-w2-merlins-cave`
     - `title`: up to 60 characters
     - `start_date`, `days`: copied from `next_arc`
     - `links`: `{ "<links_from id>": ["<day-0 node for A>", "<for B>", "<for C>"] }`, one entry per `links_from`, as many targets as it has choices
     - `notes`: up to 2000 characters, for next week's you: what's set up, open threads, what each ending means.

4. Check your work before sending: POST APP_URL/adventure/arc?dry_run=true with the arc.
   - A 422 response lists **every** problem in `detail.problems`, plus what was expected. Fix them all and check again.
   - Look hard at the odds problems: pick another DC or skill, don't fight the rule.

5. Submit: POST APP_URL/adventure/arc with the arc.
   - 201 means it's booked.
   - 409 means an arc already covers those days. Don't pass `replace=true` unless a human asked; stop and report.

6. Report in a few lines:
   - the arc's title and id
   - the week's shape (day by day, the nodes' hooks)
   - which choices break rules
   - anything odd in the state you noticed
