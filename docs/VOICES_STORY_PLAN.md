# The Voices: a story the comments steer more directly

**Status: proposal, for decisions (§9).** An upgrade to the dungeon crawl
([ADVENTURE_PLAN.md](ADVENTURE_PLAN.md)), the channel that has done best so far (§1). Comments
get far more say over each episode, a daily DeepSeek step writes each episode from the planned
story plus what the comments added up to, and **nothing about any commenter leaves the server or
appears on screen**.

## 1. Why

On the dungeon crawl, commenting already changes the story, and it has done better than the other
channels (24 h, Instagram):

| | Quiz | Dungeon crawl | Racing |
|---|---|---|---|
| Median views | 139 | **492** | 34 |
| Comments per 1,000 views | 14 | **24** | – |
| Best post | 597 views | **1,114 views, 22 comments, 19 voters** | 133 |

Today a comment can only pick one of three options. The aim is for the comments to decide *how*
things happen, *how well*, and *what* turns up in the story, and for every commenter to see that
the crowd they were part of did it.

## 2. The rule: totals only (the current privacy policy, unchanged)

The privacy policy says that on story videos we read comments to count votes, keep "only the totals
and how many people voted", and that names "aren't stored, shown or read out", and that the AI that
plans story videos "only sees vote totals". Everything below works within that:

- Comments are read on the server, as now. **Only counts come out**: how many voted for each
  option, each way of doing it (§3.1), each word from a fixed list (§3.3), and how many voted in all.
- **No usernames, no comment text and nothing a single person wrote** reach DeepSeek, the screen,
  Discord or the stored records. A shouted word only counts once **3 or more different people**
  have used it, so no single comment can be picked out. That rule also stops one troll from steering
  the story.
- Opted-out viewers aren't counted (the existing opt-out list).
- DeepSeek receives the story plan, the campaign state and these totals, none of which is personal
  data. That's also why DeepSeek storing data in China (its own privacy policy) doesn't affect
  commenters here.
- **Optional, for transparency (decision 2)**: one line in the policy's processors list saying
  that the AI writing story episodes (DeepSeek) also sees only totals, including counts of shouted
  words. No new data is collected, so this is a clarification, not a change.

## 3. What the comments decide

All of this goes in the same comment as the vote: `A sly torch` counts as option A, done slyly, shouting "torch".
The existing parser already reads `A ...` as a vote for A; the rest is new.

### 3.1 How: choose a way as well as an option

Every ask offers three **ways**, the same three all season so they become familiar:

| Way | Comment | Skills it uses | In the story |
|---|---|---|---|
| **BOLD** | `A bold` | athletics, intimidation | head-on, loud, brave |
| **SLY** | `A sly` | stealth, sleight of hand, deception | quiet, tricky |
| **WISE** | `A wise` | perception, arcana, persuasion | careful, clever |

The winning option says *what* the hero does; the winning way says *how*. The server picks the check's
skill from the way (with this hero's real odds), so the comments decide which skill gets rolled.
If nobody names a way, the node's default skill is used.

### 3.2 How well: turnout matters (Rally)

The number of people who voted adds to tomorrow's roll: **+1 at 10 voters, +2 at 25, +3 at 50**.
It's shown on the die card ("+2 RALLY · 31 VOICES"), and the odds on screen include it. More
comments make the hero more likely to succeed, so every comment helps, and it gives a reason to bring a
friend. The thresholds go up as the channel grows, so it stays a goal rather than a given.

### 3.3 What turns up: shouted words

"**Shout a word to the hero**": any comment containing a word from the **Shout List**, about 300
fantasy words for items, elements, creatures, actions and moods (torch, rope, fire, sing, run, pray, bread,
wolf…). Each person's first list word counts once. The words with 3 or more shouters are passed to DeepSeek
as totals, and **the top word has to appear in the next episode**: the validator checks for it. On
screen: "**THE VOICES CRIED: TORCH** (14)". Because the list is fixed, nothing free-form or offensive can
reach the story, and viewers can see their word land the next morning.

### 3.4 The Voices as a character

The audience becomes a character in the story: the hero hears **the Voices**, a chorus that urges
them on. The narration and text can use the totals ("Thirty voices roar *fight*", "The Voices are
split. The hero hesitates."). A close vote (winner under 50 %) and a landslide read differently in the story, though
only Rally touches the dice.

### 3.5 Naming by vote

When the plan introduces a companion, a pet, an inn or a weapon, its name is a vote between three options
from a server-side name list ("Name the hound: A Ash, B Brindle, C Moss"). The crowd owns the name,
and a public **Chronicle** page (`/chronicle`) lists every name, every vote total and every shouted
word that made it into the story. It holds totals only, so no viewer is named there either.

## 4. How an episode gets written

```
Tuesday (Claude routine, as now)          Every day, 08:00 (server)
  writes the week's plan: beats, foe,        read yesterday's comments → TOTALS only:
  scenes, a planned node per day             option counts, way counts, shout counts (≥3 people),
  (the fallback)                             voters, yesterday vs the week's average
                                           ─► DeepSeek: plan + campaign state + last 3 episodes
                                             + totals → today's node (the JSON the renderer draws)
                                           validate with the engine (schema, scenes, foes, DCs,
                                             voice limit) + new checks: follows the winning option,
                                             the top shout word appears, the skill matches the way
                                             ✗ → problems back, at most 2 retries
                                             ✗✗ → the planned node (the day still goes out)
                                           server rolls (with Rally) → voice → render
                                           Discord preview, 45 min to `hold` → 09:00 post
```

- **The dice stay honest**: the server sets the skill (from the way), the Rally bonus and the roll;
  DeepSeek only sets the DC within the validator's limits and writes the words.
- **Cost**: each call is about 10 k tokens in and 1-2 k out, under 1p a day at DeepSeek's flash-model
  prices. Voice cost is unchanged: narration stays under the current 280-character daily cap.
- **Prompt** kept in the repo (`docs/VOICES_WRITER_PROMPT.md`), like the routine's.

## 5. On screen

Within the current look (the episode stays about the same length; the hook already shows today's choice):

- **Hook**: "TODAY YOU DECIDE" with the options, plus "how? BOLD · SLY · WISE · shout a word".
- **Recap card** (exists): "Yesterday the Voices chose **A**, **sly**, 23 to 9", then
  "**THE VOICES CRIED: TORCH**".
- **Die card** (exists): skill from the way, "+2 RALLY · 31 VOICES", and odds that include the bonus.
- **Ask**: "Comment A, B or C + bold, sly or wise + a word to shout. Example: `A sly torch`".

## 6. Safety

- Only list words and counts reach DeepSeek, so there's nothing for a comment to inject.
- The output is schema-checked and rendered from the engine's fixed scenes and creatures, and each
  episode is previewed on Discord 45 minutes before posting with `hold`, which swaps in the planned node.
- Tone stays teen and up, as the season is now; the prompt sets it and the validator and preview catch the rest.

## 7. What changes in the code

| Area | Change |
|---|---|
| `app/adventure/votes.py` | tally ways (bold/sly/wise) and shout words (fixed list, first per person, ≥3 people) alongside options; still one vote per account |
| `app/adventure/shouts.py` (new) | the Shout List and name lists |
| `app/adventure/writer.py` (new) | DeepSeek client (OpenAI-compatible: `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`), prompt from plan + state + totals, validate/retry, fallback, cost log |
| `app/adventure/campaign.py` | Rally, skill from the way, named things in the campaign state |
| `app/adventure/jobs.py` | 08:00: tally → writer → dice → voice → render; `hold` |
| `adventure/packages/shared` | node/spec fields: `voices` (way, totals, shout), `rally`; validator checks |
| `adventure/packages/engine/story.ts` | hook and ask lines, recap card with the way and shout, die card with Rally |
| `app/legal` | `/chronicle` (totals only); optional policy line (decision 2) |
| metrics | tags `writer: deepseek / fallback`; extras: way votes, shouts counted, rally, voters |

## 8. Phases

| Phase | What | AI | Success looks like |
|---|---|---|---|
| **P1 Ways + Rally** | tally ways and turnout; the way picks the skill, Rally adds to the roll; hook/recap/die card/ask | none | comments per 1,000 views above 24; voters per post rising |
| **P2 Writer** | DeepSeek adapts each planned node: the way's tone, the Voices, the top shout word; falls back safely | DeepSeek | ≥ 90 % of days pass validation first or second time; no holds needed |
| **P3 Free plan** | the weekly routine writes beats instead of every branch, and DeepSeek writes the node; naming votes; the Chronicle | DeepSeek | shouts per post rising; watch time holding |

Each phase is tagged in the metrics, so before and after can be compared on the dashboard.

## 9. Decisions needed

1. **Where**: upgrade @dungeoncrawlergram (recommended: it's the story audience that comments) or a new account?
2. **Policy line**: add "the AI writing story episodes (DeepSeek) also sees only totals, including
   shouted words" to the processors list (recommended, for transparency), or leave the policy as it is?
3. **Start with**: P1 (ways + Rally, no AI, quick to ship, recommended) or go straight to P2?
4. **Moderation**: Discord preview with `hold` (recommended), or your approval before each episode posts?
