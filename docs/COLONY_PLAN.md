# Next channel: a pixel-art colony that its followers build

Plan, 3 Nov 2026. It replaces Sixel Speedway, which is switched off (`RACING_ENABLED=false`; the
code and data are kept). It draws on [CHANNEL_REVIEW_AND_NEXT.md](CHANNEL_REVIEW_AND_NEXT.md)
(what has worked so far) and [ADVENTURE_PLAN.md](ADVENTURE_PLAN.md) (the story machinery we reuse).

## 0. The reference, and how we stay clear of it

The reel the owner shared (@wyrmfell, 58 s) is a top-down pixel-art forest. A counter reads
"This page has 2 followers", and the camera drops into a clearing where two settlers sit at a
campfire. "One cuts down" a tree, "clears the ground", "first walls", and a cabin "is born". A
"+1 follower" ghost walks in, then a flash-forward shows what's to come (houses, blacksmiths,
the ruins) and it ends on "Follow the page, the next one could be yours."

**The idea we take: the account's real follower count is the story.** Every follower is someone
living in the world, and the world grows as the account grows.

**What we change so it's ours:** a different setting, our own art and names, and more mechanics
than the reference has (named settlers, personal upgrades, colony milestones, events viewers vote
on). We don't use a forest clearing with a campfire and a cabin opening, a "This page has N
followers" title card, a flash-forward montage, or their wording.

## 1. The concept: "the colony"

One short vertical video a day (**20-30 s**: the review found that people watch 8-12 s
whatever the length, and the shortest parts did best). Each video is the next day in a small
settlement that only grows when the account does.

| | What it is |
|---|---|
| **Population** | The real follower count. Each follower is one settler on screen (past ~150 they're drawn as crowds and houses). An unfollow shows a settler leaving at night. |
| **Your settler** | Comment once to claim one under your @name. You get a job and a little sprite with your initial. |
| **Personal upgrades** | Things you do yourself, read from comments (§3): rank goes up with streaks, you pick a job, you recruit by tagging a friend. |
| **Colony upgrades** | Milestones the colony reaches together: follower thresholds and post totals (shares, saves) unlock buildings (§4). |
| **Story** | A weekly arc (as in the adventure) brings in events like storms, strangers, ruins and a festival. Now and then viewers vote A/B/C on one. |

### Setting (to pick at the M1 look test)

| Option | Why | Against |
|---|---|---|
| **A planet colony** (recommended): a landing pod on a strange moon, alien flora, domes, a beacon | Clearly not the reference. "Landing" and "signal" make a natural follow hook ("answer the signal"), and the build tree (habitat → greenhouse → beacon → spaceport) is open-ended. | Pixel sci-fi is harder to make read as cosy |
| A ruined city being resettled | Strong visual progression from rubble to rebuilt streets | Busier tiles; less cosy |
| A forest or valley settlement | Cosiest and easiest to draw | Closest to the reference; we'd have to work hardest to differ |

## 2. What the platforms let us see (this shapes every mechanic)

| Interaction | What we can read | Used for |
|---|---|---|
| Follows | **Only the follower total** (`followers_count` on the IG user; YouTube `subscriberCount`, rounded above 1,000). The API never says *who* followed. | Population, follower milestones |
| Comments | Who wrote what, and when (already used for votes, bets and shout-outs) | Claiming a settler, jobs, streaks, votes, recruiting (tagged @names) |
| Shares, saves, likes, reach | **Totals per post** (already collected in `metrics.py`) | Colony resources and milestones |
| Reposts | Not confirmed in the Instagram API; check at M2. If missing, leave it out. | (maybe) a resource |
| Who shared or saved | Not available | Nothing personal can be tied to sharing |

So: **follows and shares grow the colony as a group, and comments are how a person gets into
it.** We can't check whether a commenter follows the account. The caption says "follow and
comment to move in", and we take that on trust.

## 3. Personal upgrades (from comments)

Every one of these can be checked from the comment text and the comment's author.

| Action | Effect |
|---|---|
| First comment on any episode | You arrive as a **Newcomer** with your @name, and the next video shows you walking in |
| Comment a job word (e.g. `FARM`, `BUILD`, `SCOUT`, `GUARD`, `TINKER`) | Your settler takes that job and is drawn doing it; it also adds to that job's colony progress |
| Comment on N episodes in a row (streak) | Rank goes up: Newcomer → Settler (3) → Veteran (7) → Elder (14), each with a visible badge or hat. Missing a day keeps your rank but ends the streak. |
| Tag a friend who then comments | **Recruiter** badge; both get a shout-out. We see the @mention and the friend's own comment, nothing else. |
| Winning a vote, or the first correct guess at a story mystery | A named moment in the next video, like the quiz's shout-outs |

Limits: one job change a day, and only text and handles we've read are used. The existing opt-out
(`app/privacy.py`) applies: anyone can ask not to appear, and old names are anonymised.

## 4. Colony upgrades (milestones)

Two kinds, both shown on a progress bar in every video so there's always a next goal close by:

- **Follower milestones** (permanent): e.g. 5 → first shelter, 10 → water, 25 → greenhouse/farm,
  50 → workshop, 100 → beacon/tower, 250 → market, 500 → a second district, 1,000 → something
  big. Each one is its own construction episode. Early goals are close together so the first
  week has unlocks.
- **Daily resources** (from yesterday's post): its shares become *materials* and its saves
  become *supplies*, and those pay for what's being built. "Yesterday's 12 shares finished the
  greenhouse roof." Building is always visible progress, never a hard wall: the colony gets
  there slowly anyway, and faster with help.

Jobs (§3) decide *what* gets built next: the busiest job's building goes to the front of the queue.

## 5. A video, second by second (~25 s)

| s | Beat |
|---|---|
| 0-2 | **Hook straight away, with the world already moving**: the population number counting up over the colony ("37 live here"). No title card. |
| 2-8 | What changed since yesterday: newcomers walk in by name, an unfollower leaves at night |
| 8-18 | Today's beat: a building goes up (resources spent), or a story event; settlers do their jobs |
| 18-23 | The next goal: "12 more and we light the beacon" and a progress bar |
| 23-25 | The ask, as part of the story ("comment to move in"), then cut back to the opening frame so it loops |

Instagram's recommendation rules hold back "engagement bait" (lines like "like if…" or "share
to…"). The ask should read as part of the world, without listing likes or shares. The review
routine should watch for reach dropping when the ask changes.

## 6. Build: what's reused, what's new

| Need | From |
|---|---|
| Daily booked jobs, render lead, publishing, retries, Discord previews | `pipeline.py` / the adventure jobs pattern |
| Channel and accounts | `channels.py`: a new `Channel("colony", …)`, a **new account** connected with `/oauth/{platform}/start?channel=colony` |
| Reading comments, replies, opt-outs | `cliffhanger.read_comments`, `instagram.comment()`, `privacy.py` |
| Per-post shares/saves/reach | `metrics.py` (already collects them per channel) |
| Weekly story | The adventure's routine and writer, with a `colony` schema |
| Votes | `app/adventure/votes.py` |
| Rendering | The adventure's TS + Skia engine (`adventure/`). Pixel art is drawn at 180×320 and scaled ×6 with nearest-neighbour, which is far cheaper per frame than the painted look. |

New:

- `app/colony/state.py`: the colony (population, buildings, resources, queue) and the settler
  roster (@name, job, rank, streak, recruits). One atomic JSON file, like the racing ledger.
- `app/colony/jobs.py`: the daily cycle. 45 min before the slot it reads the follower count,
  yesterday's numbers and the comments; applies joins, jobs, streaks and milestones; renders.
  At the slot it posts and replies to newcomers.
- `instagram.followers()` (`followers_count`) and, for YouTube, `subscriberCount`.
- A pixel tileset and sprites: our own procedural pixel art, plus CC0 packs where they fit
  (e.g. Kenney), each listed in a `LICENSES.md` as the music is.
- Dashboard tags: `beat` (build/event/vote), `milestone`, `ask`, `length`.

No AI is needed day to day. The weekly arc is optional flavour: without it, the colony still
runs on its counts alone.

## 7. Milestones

| | What | Done when |
|---|---|---|
| M1 Look test | Pixel renderer: the landing or first night, a build going up, 30 named settlers, a progress bar. Three stills and a 25 s video in Discord for each setting in §1. | Owner picks the setting and look |
| M2 Counts | `followers()`, the colony and roster store, the comment rules of §3, milestone and resource rules of §4, tests | A dry run over a fake week posts nothing and renders 7 correct videos |
| M3 Launch | New account connected; "Day 0" (an empty world: the first follower is the first settler); daily posts at a slot clear of the others (09:00 / 12:00; 19:00 is free now racing is off) | First automatic post |
| M4 Story | Weekly arc and occasional votes; weekly review covers the channel | Two weeks of posts |
| M5 Decide | 14 posts in, against the dungeon crawl's numbers | below |

**Keep or kill after 14 posts** (24 h Instagram snapshot): keep if **median views ≥ 300 and %
watched ≥ 35 %**, and the account is growing (followers are the whole point). Otherwise change
one thing (length, hook, ask) for a week, then decide.

## 8. Open questions for the owner

1. Setting: planet colony (recommended), ruined city, or forest/valley?
2. Name and handle for the new account (checked as Sixel Speedway's was).
3. Instagram only at launch (like the dungeon crawl), or YouTube too?
4. Weekly story routine from the start, or counts-only first and story at M4?
