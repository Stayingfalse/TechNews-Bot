# Next channel: a pixel-art colony that its followers build

Plan, 3 Nov 2026 (decisions updated the same day: §0a). It replaces Sixel Speedway, which is switched off (`RACING_ENABLED=false`; the
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

## 0a. Decisions so far

| | Decision |
|---|---|
| Setting | **A planet colony**: a small crew lands on a strange moon and builds from a landing pod upwards |
| Platforms | **Instagram only** at launch, on a **new account** (name: §9) |
| AI | **The most AI of any channel.** A writer reads the comments every day, settler by settler, and changes the people and the story to match, the way "an old man in a barrel" was taken in on the dungeon crawl (§5a). A weekly arc gives the direction. |

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
| **Story** | Written every day from the comments (§5a): settlers become who their owners say they are, feuds and friendships start from what people write, and a weekly arc brings in storms, signals, ruins and visitors. Now and then a vote. |

### The setting

A small moon with violet grass, glass-shelled plants, two suns setting at different times, and
the landing pod the colony starts from. "Answer the signal" is the follow hook. The build tree
is open-ended: pod → habitat domes → water condenser → greenhouse → workshop → beacon →
market → landing pad → a second district → ... Pixel sci-fi can look cold, so it should be lit
cosy: warm lamps in the domes, campfire-like heaters, little lit windows at night.

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

## 5a. The adaptive story (the AI step)

The reference only counts followers. Here **every settler is a character their owner can shape
by commenting**. Someone writes "can I be an old man in a barrel?" and the next video has an old
man in a barrel with their name on him. If they later write "my barrel has a leak", that goes in
too. Requests and running jokes become the story.

### The daily cycle

```
every 15 min   read new comments on the channel's posts → store them by settler
               (joins, job words and streaks are counted by code, as in §3)
T-90 min       the writer is given: the colony (buildings, resources, today's milestone),
               the week's arc beat, the story so far, and each active settler's sheet plus
               their new comments
               → it answers in JSON (the schema below), checked by code; problems sent back
                 at most twice
T-75 min       Discord preview of the plan: every look change, quote and reply, each with a
               Block button (as the dungeon crawl's party names are moderated)
T-45 min       render → video preview in Discord
slot           post; then the replies go out slowly (the racing reply queue's limits)
```

### What the writer can change

It returns **structured changes, not free drawing**. The renderer only draws things it already has:

| Field | What it is | Checked by |
|---|---|---|
| `looks` | Per settler: picks from the **sprite kit**: body (age, build), skin/hair palette, outfit, hat, held item, *carrier* (barrel, crate, hover-chair, wheelbarrow...), pet, idle animation | Every id is in the kit |
| `traits` | Up to 3 short words per settler (grumpy, inventor, sleepwalker), kept between days | Length, word list check |
| `sheet` | A short running summary of each settler, written by the writer and given back to it the next day. It's the writer's memory of the person (who they are, what they've asked for, their running jokes). | ≤ 300 characters, no personal data beyond what's in-story |
| `episode` | Today's beats: what happens, which settlers are in it, up to 3 speech bubbles (≤ 60 characters each), the caption | Engine's validator: length, teen-and-up, safe zones |
| `replies` | A short in-story reply to any comment it acted on ("Pull up a barrel, the east row has room") | Length; one per person per day |
| `wanted` | Requests it couldn't draw: the nearest kit parts were used, and this lists what's missing | - |

**The kit grows from what people ask for.** `wanted` collects over the week. The weekly routine
(a Claude Code routine, as for the quiz) draws the most asked-for parts as new pixel sprites in
code and opens a PR. Until a part lands, the writer uses the closest one ("a barrel" now, "a
barrel with a leak" a week later).

### The weekly arc

A routine on Sunday night (as the adventure's): reads the season premise, the story so far and
the week's comments in summary, and writes the next week as **beats, not scripts**, e.g. "Tue:
the condenser breaks; Thu: a second signal; Sat: the festival if the greenhouse is done". The
daily writer fills each beat with the people who are actually around, so the arc keeps
direction and the days stay reactive.

### Scale

Everyone who comments gets a settler, but each video gives detail to a few. The writer
**features 2-5 settlers a day**: newcomers first, then whoever wrote something it can act on,
then a rotation so nobody waits too long. The rest are drawn walking around. Comments are capped
per person per day, and a settler's older comments go into their sheet, so the input stays
short as the colony grows.

### Guardrails

- **Comments are data.** They go in a clearly marked block. The answer can only be JSON against
  the schema, with kit ids from a fixed list and capped text. Nothing in a comment can make the
  server post, link or tag anything.
- **What isn't accommodated:** anything sexual, hateful, violent beyond teen-and-up, real people or
  public figures, other creators' characters or brands, links, or someone else's name. The writer
  declines in-story or ignores it, and a code check (word list, @/link filter) backs it up.
- **Human last look:** the T-75 preview. Anything blocked is replaced by the settler's previous
  look or line. A blocked user's requests stop for good (the party's block list).
- **Never depends on the API:** if the writer fails, the day runs on counts alone (§3-4) with
  yesterday's looks.
- **Privacy:** this is the first channel that sends **usernames and comment text** to an AI
  provider. The privacy policy (`app/legal/privacy.html`) and the channel's caption or bio need to
  say so before launch. Opted-out users' comments are never sent. Sheets and comments are
  anonymised after `RETENTION_DAYS`, and erasure removes a settler, their sheet and their comments.

### Which model

The writer sits behind one function like `app/adventure/writer.py`, so the provider is a setting.
For this one I'd start with **Claude** (Sonnet 5.5): it has to judge what to accommodate and
what to decline, keep characters consistent over weeks and write in a voice, which is more than
the dungeon crawl's word-swaps. DeepSeek (already wired up) is the fallback. One call a day
with a few thousand words in; check the cost at M2.

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

Also new: the writer (§5a: `app/colony/writer.py`, schema, checks), the sprite kit with its ids, the
comment store by settler, the Discord moderation preview, and the weekly arc routine prompt.
Without the AI the colony still runs on its counts alone, which is the fallback.

## 7. Milestones

| | What | Done when |
|---|---|---|
| M1 Look test | Pixel renderer: the landing or first night, a build going up, 30 named settlers, a progress bar. Three stills and a 25 s video in Discord for each setting in §1. | Owner picks the setting and look |
| M2 Counts | `followers()`, the colony and roster store, the comment rules of §3, milestone and resource rules of §4, tests | A dry run over a fake week posts nothing and renders 7 correct videos |
| M2.5 Writer | §5a: sprite kit v1 (≈ 40 parts, barrel included), the writer and its checks, the moderation preview, a replay test over a fake week of comments (requests, a troll, a prompt injection, a returning settler) | The fake week reads well and every bad comment is handled |
| M3 Launch | New account connected; "Day 0" (an empty world: the first follower is the first settler); daily posts at a slot clear of the others (09:00 / 12:00; 19:00 is free now racing is off) | First automatic post |
| M4 Story | Weekly arc routine, occasional votes, the `wanted` → new sprites loop; weekly review covers the channel | Two weeks of posts |
| M5 Decide | 14 posts in, against the dungeon crawl's numbers | below |

**Keep or kill after 14 posts** (24 h Instagram snapshot): keep if **median views ≥ 300 and %
watched ≥ 35 %**, and the account is growing (followers are the whole point). Otherwise change
one thing (length, hook, ask) for a week, then decide.

## 8. Open questions for the owner

1. The handle (§9).
2. Who checks the T-75 preview: does a post go out if nobody looks (as the party names do), or wait?
3. Claude for the writer (recommended), or DeepSeek to start?

## 9. Handle ideas

Checked for meaning only. Availability has to be checked in the Instagram app (it shows
logged-out visitors a login wall), and each also needs a check for an existing brand, like
Sixel Speedway had.

| Handle | Why |
|---|---|
| **@landfall.colony** | The moment the story starts, and it reads as "a colony" at a glance |
| **@moonlet.colony** | A tiny moon: cosy, fits pixel art, and the moon's in-story name |
| @answerthesignal | The follow hook as the name; strong, but long |
| @podthirteen | The landing pod's number; mysterious, short |
| @farside.colony | The far side of a moon; slightly ominous |
| @smallmoonsociety | Friendly; the community is the point |
| @driftmoon | Short, a moon drifting into a story |
| @tinycolony.exe | Pixel and game feel; the suffix may look like spam |

My picks: **@landfall.colony** (the clearest) or **@moonlet.colony** (the warmest). Either keeps
a world name of its own, so the story can say "the Moonlet colony" or "Landfall" in-world.
