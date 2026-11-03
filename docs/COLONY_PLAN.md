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
| Platforms | **Instagram only** at launch, on a **new account: @farside.colony** |
| AI | **The most AI of any channel.** A writer reads the comments every day, settler by settler, and changes the people and the story to match, the way "an old man in a barrel" was taken in on the dungeon crawl (§5a). |
| Models | **Claude for the heavy work** (the week's plan, the daily story, deciding what to accommodate); **DeepSeek for the easy work** (sorting comments, wording replies, captions, condensing settler sheets) (§5b) |
| How Claude runs | **Claude Code Routines call the server**, as the quiz batch does: a weekly one and a daily one. The server never calls Claude and holds no Anthropic key, so it all runs on the existing Claude usage, not paid API usage. |
| Week ahead | Claude plans the **whole week as complete, playable episodes**. If the AI can't run on a day (out of credits, API down), that day plays as planned; if it can, it builds in what people asked for (§5b). |
| Moderation | A Discord preview before each post with Block buttons. **Not blocked means it goes out**, as the dungeon crawl's party names do. |
| The core | **People get their decisions.** What does best on every channel is content about the viewer, so most of each video shows what particular people asked for and chose (§1a). The counts are the backdrop. |
| Views | **Four views, picked per scene** (§5c): side-on (story beats, the bunkers), top-down (the colony at scale), inside buildings, and the whole planet (later, planets) |
| Voice | **ElevenLabs on this channel too.** The subscription stays at 30,000 credits a month for three channels, and the colony gets 15,000 (§5d). |

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

## 1a. People get their decisions

The numbers from the other channels all point the same way: the best part on any channel was
the dungeon crawl's "pick your class", where the question was about the viewer. So the counts
(followers, shares) build the colony in the background, and **each video is mostly about
particular people and what they decided**:

- **Every request gets an answer on screen, by name.** "@oldbarrel wanted a barrel. He got the
  drafty corner." Requests that can't be done get an in-story answer too ("The council says no
  pets bigger than the airlock").
- **Personal decisions:** a settler's owner picks their job, home, look, a side in a dispute, or
  what to do with a find ("@mossbyte found a sealed door in the cellar: comment OPEN or LEAVE").
  The writer offers a personal choice to 1-3 featured settlers per episode, and their next
  appearance shows what came of it.
- **Colony decisions** (where the next dome goes, what to do about the signal) are votes as on
  the dungeon crawl, but the video names who swung it and shows the first few voters' settlers
  doing it.
- **Consequences stick.** A settler who chose the night shift is drawn on it from then on.
  Someone who opened the door is "the one who opened the door". The settler sheet (§5a) keeps
  this.
- **Order on screen:** the people (arrivals, answers, consequences) come first. Colony progress
  comes after, as the payoff.

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
every 15 min   DeepSeek sorts each new comment: join / job / request / reply-to-story /
               chatter / not OK (code rules first; see §5b)
T-3 h          the daily Claude routine fires: GET /colony/today gives it today's planned
               episode (from the week plan), the colony (buildings, resources, today's
               milestone), the story so far, and each active settler's sheet plus their
               sorted new comments
               → it sends today's episode adapted (the schema below) to POST /colony/today;
                 the server checks it and answers 422 with every problem; the routine fixes
                 and resends
T-90 min       the cut-off: whatever has been accepted by now is used. Nothing accepted
               means the planned episode stands. Comments after the routine read them go
               into tomorrow.
T-80 min       DeepSeek words the replies and the caption, and condenses each featured
               settler's sheet
T-75 min       Discord preview of the plan: every look change, quote and reply, each with a
               Block button. Anything not blocked by the render goes out.
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

### The week plan

See §5b: Claude writes the next week on Sunday night as complete episodes, and each day's
writer adapts that day's episode. The plan keeps the story's direction ("Tue: the condenser
breaks; Thu: a second signal; Sat: the festival if the greenhouse is done") and the days react
to whoever is around.

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
- **Human last look:** the T-75 preview. **Anything not blocked by the render goes out.**
  Anything blocked is replaced by the settler's previous look or the planned line. A blocked
  user's requests stop for good (the party's block list).
- **Never depends on the API:** if the writer fails, that day's planned episode plays (§5b).
- **Privacy:** this is the first channel that sends **usernames and comment text** to an AI
  provider. The privacy policy (`app/legal/privacy.html`) and the channel's caption or bio need to
  say so before launch. Opted-out users' comments are never sent. Sheets and comments are
  anonymised after `RETENTION_DAYS`, and erasure removes a settler, their sheet and their comments.

## 5c. Views: picking the camera for each scene

The side-on diorama is good for story beats and the bunkers below, but it fits a few dozen
people. Thousands need other views. Each scene in an episode names its view, and the writer
picks one to suit what's happening:

| View | For | Holds | What it shows |
|---|---|---|---|
| **Side-on** (the look test) | Arrivals, a settler's moment, a request answered, building a dome, the **bunkers and tunnels** underground | ~30 people, 3-5 named | Sky and the planet above, the surface, a slice of the underground |
| **Top-down** | The colony at scale: districts, roads, farms, crowds, a march or festival, where a new building goes | thousands (one pixel each when far out, sprites when close) | A tile map of the surface. The camera can fly to a district or someone's home. |
| **Inside** | A dome, the workshop, the council room, someone's quarters, a cellar | 2-8 | A cut-away room with furniture and their looks up close. This is where personal scenes and decisions play. |
| **Planet** | Milestones, the follower count as lights on the night side, later a second moon or planet | everyone, as lights | The whole moon turning, with the colony's districts lit up |

All four use the same palette, font, sprite kit and settler sheets, so a settler looks the same
in each. One episode can cut between them: planet → top-down push in → side-on → inside.

**As it grows:** in the first weeks it's mostly side-on and inside. Top-down becomes the overview
once the colony spreads beyond a couple of screens (around 100 people). The planet view is for
milestones from the start, and becomes the overview past a few thousand. Every view keeps the
named, featured settlers at sprite size, so the people stay the centre whatever the scale.

## 5d. Voice

ElevenLabs stays on **30,000 credits a month** now that three channels use it. Budgets:

| Channel | Credits a month | Notes |
|---|---|---|
| Quiz | 2,000 | as now |
| Dungeon crawl | 10,000 | up from 7,200 (`ADVENTURE_VOICE_BUDGET`) |
| **Colony** | **15,000** | A narrator plus character voices |
| Spare | 3,000 | retries and tests |

- **A narrator** (a calm "colony log" voice): ~250 characters a day, ~7,500 a month.
- **Character voices** for featured settlers' lines: a cast of ~8 designed voices from the voice
  library (old, young, gruff, bright...), assigned by the writer to suit each settler's sheet and
  kept from then on. ~150 characters a day, ~4,500 a month. The barrel elder gets the old one.
- **The founding crew** each have a fixed voice.
- Out of credits: speech bubbles stay, voice drops out (as on the other channels). Voice is made
  only for the episode that actually posts, after the day's adaptation.

## 5b. Who does what, and what happens when the AI can't run

### The split

| Job | Who | When | Why |
|---|---|---|---|
| **The week plan**: 7 complete episodes plus 2 spare ones | **Claude**, a Claude Code Routine (as the quiz batch) | Sunday 20:05 | The big creative and story call, once a week |
| **The daily adaptation**: fit today's episode to what people asked for, decide what to accommodate or decline, keep characters consistent | **Claude**, a daily Claude Code Routine calling `GET`/`POST /colony/today` | T-3 h (cut-off T-90 min) | Judgment and a voice. It runs on Claude usage, so the server needs no Anthropic key. |
| **Sorting comments**: join / job / request / reply-to-story / chatter / not OK | **DeepSeek** (already wired up), after code rules (job words, `JOIN`, links, @mentions) | every 15 min | Many small calls; easy |
| **Wording**: replies, caption, condensing settler sheets | **DeepSeek** | T-80 min | Short, low-stakes writing |
| **Counts**: population, streaks, ranks, milestones, resources | **Code** | always | Never an AI call |

The routine sends its plan to `POST /colony/week`. The server checks it (schema, kit ids,
lengths, teen-and-up, a still render of each episode) and answers 409/422 with every problem,
and the routine fixes and resends, as the quiz batch does.

### The week plan stands on its own

Each planned episode is **complete and renderable without any viewer input**:

- the beats, the scenes, every line, the caption, and the build it shows;
- a **founding crew** of 4-6 colonists of our own, so a day with no new comments, or no
  commenters at all in the first week, still has characters and a story;
- **slots** where viewers can come in: "newcomers arrive here", "a settler with a request
  features here", "today's job tallies go here". With no AI, code fills the slots it can (newcomers
  by @name, job counts, milestones) and leaves the rest to the crew;
- two **spare episodes** that fit any week (a dust storm, a quiet night under the two moons), in
  case Sunday's routine fails and a week starts with nothing planned.

### When something can't run

| What's up | That day |
|---|---|
| Claude and DeepSeek | Planned episode, with what people asked for built in (looks, lines, small plot turns), sorted comments and worded replies |
| DeepSeek, but not Claude (out of usage, outage, the routine didn't fire or missed the cut-off) | **Planned episode as written.** Code fills the newcomer and job slots, and DeepSeek words the replies. Requests wait in a queue for the next day Claude runs, so none are lost. |
| Claude, but not DeepSeek | Claude sorts the comments itself within its daily call, and replies come from fixed templates |
| Neither | Planned episode, code-filled slots, template replies ("Welcome to the colony, @name") |
| No week plan (the routine failed) | The spare episodes, then a Discord alert to re-run the routine |

Discord says which row each day ran on. The dashboard tags every post with it (`ai: full / plan /
counts`), so the weekly review can see whether the adapted days do better than the planned ones.

### Cost and limits

- Claude: one daily routine run plus the weekly one, on the existing Claude usage (no API
  billing). `GET /colony/today` caps what it hands over (featured settlers, comments per person;
  see "Scale"), so a run stays small as the colony grows. DeepSeek: a small call per batch of
  comments. Measure both at M2.5.
- If routine runs ever need cutting back, the daily one can drop to every other day: the plan
  covers the days in between.

## 6. Build: what's reused, what's new

| Need | From |
|---|---|
| Daily booked jobs, render lead, publishing, retries, Discord previews | `pipeline.py` / the adventure jobs pattern |
| Channel and accounts | `channels.py`: a new `Channel("colony", …)`, a **new account** connected with `/oauth/{platform}/start?channel=colony` |
| Reading comments, replies, opt-outs | `cliffhanger.read_comments`, `instagram.comment()`, `privacy.py` |
| Per-post shares/saves/reach | `metrics.py` (already collects them per channel) |
| Weekly story | The quiz batch's routine pattern (`POST`, 409/422 with every problem, fix and resend), with a `colony` schema |
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

Also new: the week plan (`POST /colony/week`, its checks, the spare episodes), the daily writer
(§5a/5b: `GET`/`POST /colony/today`, the schema and checks, the cut-off), the comment sorter (DeepSeek), the
sprite kit with its ids, the comment store by settler, the Discord moderation preview, and the
weekly and daily routine prompts (`docs/COLONY_ROUTINE_PROMPT.md`, `docs/COLONY_DAILY_PROMPT.md`).

## 7. Milestones

| | What | Done when |
|---|---|---|
| M1 Look test | ~~Side-on~~ (done 3 Nov: `render_colony.py`). Then the top-down view, an interior and the planet, all in the same style, plus one episode that cuts between them. | Owner picks the look of each view |
| M2 Counts | ~~Done 3 Nov~~: `instagram.followers()`, `app/colony/` (rules, state, episode, dryrun: `python -m app.colony.dryrun out/week --video`), side-on drawings for every building to the beacon, privacy erase, tests | A dry run over a fake week posts nothing and renders 7 correct videos |
| M2.5 Writer | §5a-b: sprite kit v1 (≈ 40 parts, barrel included), `POST /colony/week` and the spare episodes, `GET`/`POST /colony/today` and the DeepSeek sorter with their checks, the moderation preview, a replay test over a fake week of comments (requests, a troll, a prompt injection, a returning settler) run four times: full AI, no Claude, no DeepSeek, neither | Every run gives 7 good videos and every bad comment is handled |
| M3 Launch | New account connected; "Day 0" (an empty world: the first follower is the first settler); daily posts at a slot clear of the others (09:00 / 12:00; 19:00 is free now racing is off) | First automatic post |
| M4 Story | The weekly routine live, occasional votes, the `wanted` → new sprites loop; weekly review covers the channel | Two weeks of posts |
| M5 Decide | 14 posts in, against the dungeon crawl's numbers | below |

**Keep or kill after 14 posts** (24 h Instagram snapshot): keep if **median views ≥ 300 and %
watched ≥ 35 %**, and the account is growing (followers are the whole point). Otherwise change
one thing (length, hook, ask) for a week, then decide.

## 8. Open questions for the owner

1. Posting time: 19:00 (free now racing is off) or another slot?

## 9. Handle ideas (decided: **@farside.colony**)

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
