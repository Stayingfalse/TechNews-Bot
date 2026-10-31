# Channel review (31 Oct 2026) and the next channel to build

## 1. What we run today

| Channel | Account | Platforms | Live since | Posts | AI step | Needs comments to work? |
|---|---|---|---|---|---|---|
| Daily quiz | @mediaquiz.daily | Instagram, YouTube | 22 Oct | 16 (incl. 1 re-post) | weekly routine writes 7 quizzes | no (cliffhangers and theme asks are extras) |
| Dungeon crawl | @dungeoncrawlergram | Instagram | 27 Oct | 5 (Episode 0 parts 1-4, Episode 1) | weekly arc routine | **yes**: A/B/C votes drive the story |
| Sixel Speedway | @sixelspeedway | Instagram | 28 Oct | 4 (launch, races 1-3) | none | **yes**: play-money bets are the point |

Numbers below come from `GET /metrics` on 31 Oct 21:20. That endpoint only covers the quiz;
the adventure and racing numbers (`/racing/metrics`, adventure job stats) weren't pulled for this
review. Both channels are under a week old anyway, so they can't be judged yet.

## 2. How the quiz has done

Totals after 10 days: **3,136 Instagram views, 2,250 YouTube views**, 56 likes, 45 comments,
4 shares, 4 saves.

Compared on the 24 h Instagram snapshot (14 posts that have one):

| | |
|---|---|
| Median views at 24 h | 146 (mean 217) |
| Average % watched | 24 % (about **12 s** of a ~50 s video) |
| Watch % vs views | correlation **0.61**: the posts people watch longer get pushed further |
| Best | "Only true superhero fans get 5/5": 597 views, 32 % watched · "Only true cartoon fans get 5/5": 548 IG + 768 YT, 31 % |
| Worst | "Sitcom fans: 5/5 or bust": 129, 12 % · "Gamers only": 125, 15 % · "Hard mode": 118, 18 % |
| Latest | "5 scrambled Halloween films" (all-unscramble): 9 views after 9 h, against ~100 for most posts at that age |

What it says, from strongest to weakest:

1. **Retention is the bottleneck.** Every post gets a seed batch of ~70-140 Instagram views in the
   first hour; only the ones watched past ~30 % break out to 500+. Viewers leave at around 12 s,
   so most never see round 2. The 50 s length works against us.
2. **Identity hooks on broad nostalgic fandoms win.** "Only real X fans get 5/5" titles average
   279 views and 27 % watched vs 154 and 21 % for the rest (7 posts each), and the two broad ones
   (superheroes, cartoons) are the only breakouts. Niche ones (AI, 2000s songs) didn't break out.
3. **Hints, not findings yet (3-4 posts each):** voice-over (313 vs 190 views), the quick intro
   (279 vs 192), cliffhangers (302 vs 193). Worth keeping on the review's list.
4. **Comments are thin:** 3-5 a post. Nobody shares or saves (4 of each in total).
5. **YouTube is a lottery:** 0 to 776 views with no link to Instagram's numbers. It still gave the
   single biggest result, so a new channel should post there from day one.

What this means for the other two channels: both depend on comments, and the quiz, with more
reach than either, gets 3-5 comments a post. With a few hundred views a video, races will have very
few bettors and episodes very few voters. They need more reach before their mechanics can work. A
third comment-driven channel would hit the same cold-start problem.

## 3. What the next channel has to do

From the numbers:

- **Hold people to the end without asking them to do anything.** It should work for a viewer who
  never comments; comments add to it but it shouldn't depend on them.
- **Get to the point within the first second**, with the payoff in the last second, and **20-35 s** long.
- **Use an identity hook**, the one thing that has worked: "find yours".
- **Give people a reason to share** ("which one are you?").
- **Run on the server with no AI step and no fact checking.** It should cost nothing per video
  (no voice credits) so it can post more than once a day.
- **Instagram and YouTube from launch.**
- **Reuse what's built:** the racing seeded sim, its seal and odds, the frame renderer and synth
  sound, the scheduler, publishers and Discord previews.

## 4. Candidates

| Idea | Hold to the end | Hook | Works with no comments | Build cost | Running cost | Verdict |
|---|---|---|---|---|---|---|
| **Pick-your-side elimination sim** (see §5) | very high: the winner is only known in the last second, and it loops | find your birth month, sign or country | yes | low: reuses the racing sim and renderer | none | **build this** |
| "Higher or lower" stat duels (which is bigger, older, more popular) | high: a decision every 3 s | weak (general knowledge) | yes | medium: needs a weekly routine and a fact source | routine time | second choice; could also run as a quiz format |
| 15 s single-question micro-quiz | high | fandom titles | yes | very low | as the quiz | test it **inside the quiz channel** first (a batch experiment) rather than as a new account |
| Another story or betting channel | depends on comments | - | no | high | voice credits | no: same cold-start problem |
| Fact countdowns / "this day in history" | low-medium | weak | yes | medium | fact checking | no: crowded and the weakest hook |

## 5. Recommendation: "Last One Standing", a daily pick-your-side survival sim

Working name, to be checked like Sixel Speedway was. One original **~30 s** vertical video a day:
a group of 8-12 labelled balls (one for each birth month, star sign, continent, colour, or
favourite emoji) bounce around an arena that shrinks, has obstacles that change each day, or has
hazards that knock a ball out. Balls go out one by one until **one is left**. The winner gets a
crown, and the video cuts straight back to the opening frame so it loops.

**First frame** (the title is burned into the video, no intro card): *"Find your birth month. Does it survive?"*
with all 12 balls already moving. The viewer picks theirs in the first second and has a reason to
stay until it goes out or wins. The payoff comes in the last 2 seconds.

**What brings people back:**
- **Standings that carry over.** Each group's wins are kept for the season. Every video ends on a
  one-line tally ("JUNE: 3 wins this month · SCORPIO is on a 2-win streak"), and on Sunday the
  video shows the season table. People come back to see if their side wins again, as with the racing league.
- **Rotating groups through the week** (Mon months, Tue signs, Wed continents, Thu colours, Fri
  emoji, Sat a "champions" race of each group's leader, Sun the table), so the same people come
  back for "their" day. All of these groups are generic: no IP and nothing to fact-check.
- **Provably fair:** the same seal as the racing channel (hash in the caption, seed revealed the
  next day), so "it's rigged" has an answer.
- **Comments as an extra:** the caption asks "comment your month 👇". There's no betting and no
  replies at launch. Later, the most-commented side can get a visible "crowd favourite" halo
  (purely cosmetic, never changes the result).

**Why it should beat the quiz:**
- It deals with the drop at ~12 s directly. There's no reading, no rounds and no countdown. The
  reason to keep watching is still there at second 29.
- It uses the hook that worked ("only real X") in a version anyone can join.
- It doesn't depend on language. Labels are short words or emoji, so it can reach viewers outside the UK.
- It costs nothing per video: synth sound only, no voice credits, no Claude routine. That
  means it could post twice a day once it works.

**What it reuses:**

| Need | From |
|---|---|
| Seeded, reproducible sim + seal/reveal | `app/racing/sim.py` (`new_seed`, `seal`, the race-from-seed pattern) |
| Frame rendering, themes, synth sound | `app/render/racing/engine.py`, `themes/`, `sound.py` |
| Daily self-booking job, render lead, publishing, retries, Discord preview | `app/racing/jobs.py` pattern + `pipeline.py`, publishers |
| A per-channel account and tokens | `channels.py` (a fourth `Channel`, kind `survival`) |
| Metrics and the weekly review | `metrics.py` tags (`group`, `arena`, `hazard`, `length`) so the review routine can compare them |

New code: the 2D physics (circle collisions, walls, the shrinking arena; either our own numpy
step, as the racing sim does, or `pymunk` (MIT)), one theme, the standings store, and the
weekly group calendar. That's roughly the size of the racing sim plus its video module, with no
ledger, bet parser or reply queue.

**Risks:**
- *A crowded genre.* Bouncing-ball and marble-race sims are common on Shorts. Ours stands out by
  having a new arena every day, standings people follow, the seal, and the look. Make the arena,
  rules and art our own, not a copy of any particular channel's video.
- *It can look cheap.* The physics needs to read clearly on a phone: big balls, thick outlines,
  slow motion on the final two, impact sounds. The first milestone is a look test before any posting.
- *Instagram's "unoriginal content" rule.* Every video is a new render from a new seed, so it's
  original. Don't reuse clips between posts.

## 6. Plan

| Milestone | What | Done when |
|---|---|---|
| M0 | Pull racing and adventure numbers into the review routine (`/racing/metrics`, adventure job views), so all three channels are measured the same way. | The weekly review covers every channel |
| M1 Look test | `render_survival.py`: sim + one theme, 30 s, four arenas, sent to Discord. Pick the look, as with the racing styles. | Owner picks a look |
| M2 Channel | Channel `survival` in `channels.py`, daily job (render 45 min before, post at **16:00**, clear of 09:00 / 12:00 / 19:00), seal in the caption, standings store, IG + YT accounts connected. | First automatic post |
| M3 Retention loop | End tally, Sunday table, champions day, loop ending. Metrics tags. | Two weeks of posts |
| M4 Decide | After 14 posts, compare with the quiz on the 24 h snapshot. | see below |

**Keep or kill after 14 posts** (24 h Instagram snapshot): keep and go to two posts a day if
**watched % ≥ 40 %** (the quiz averages 24 %) **and median views ≥ 300** (the quiz: 146).
Otherwise change one thing (length, arena, groups) for one more week, then stop.

## 7. For the quiz in the meantime (for the weekly review/batch to pick up)

- Shorter: try 3 rounds / ~30 s on some days (tag `rounds: 3`). Viewers leave at 12 s.
- Lean on broad nostalgic fandoms (cartoons, superheroes, Disney, 90s films) with "Only real X fans" titles.
- Open on the emoji round, which is the fastest to read.
- Don't run all-one-format specials (the all-unscramble Halloween post stalled at 9 views in 9 h).
- Keep testing voice, the quick intro and cliffhangers until each has enough posts to count.
