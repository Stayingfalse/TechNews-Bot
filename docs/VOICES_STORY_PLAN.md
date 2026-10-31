# The Voices and the party: a story the commenters steer and join

**Status: proposal, for decisions (§10).** An upgrade to the dungeon crawl
([ADVENTURE_PLAN.md](ADVENTURE_PLAN.md)), the channel that has done best so far (§1):

- **The party**: viewers can join the story. Their username goes on a companion who travels with
  the hero, as the quiz shows shout-out winners. The privacy policy gets the matching update (§7).
- **The Voices**: comments decide *what* the hero does, *how*, *how well*, and *what* turns up.
- **A daily DeepSeek step** writes each episode from the planned story and the comments' totals.
  **DeepSeek never receives anything about a person** (§5), so it isn't a processor of personal
  data and doesn't need listing in the privacy policy.

## 1. Why

On the dungeon crawl, commenting already changes the story, and it has done better than the other
channels (24 h, Instagram):

| | Quiz | Dungeon crawl | Racing |
|---|---|---|---|
| Median views | 139 | **492** | 34 |
| Comments per 1,000 views | 14 | **24** | – |
| Best post | 597 views | **1,114 views, 22 comments, 19 voters** | 133 |

Today a comment only picks one of three options, and the voter disappears into a total. Two
things should drive more comments, and bring people back: seeing *yourself* in the next video
(the party, credits), and seeing *the crowd you were part of* change the story (the Voices).

## 2. The party: viewers in the story (names on screen)

| Mechanic | What happens | On screen |
|---|---|---|
| **Join** | Comment `join` under an episode. There are up to **5 companion places**. Open places go to joiners in the order they commented, and once a week one place goes to a random joiner who hasn't had one, so newcomers get in. | A companion walks behind the hero with a parchment `@handle` tag |
| **Stay or leave** | You stay while you keep commenting. After **3 episodes without a comment**, your companion heads home in the story and the place opens up. Comment `leave` (or `#optout`) to go now. | "Ash (@amy) heads home" |
| **Companion moments** | Each episode, one companion gets a line in the story ("Ash spots the trap"). The server picks who, at random from the companions; it's never based on what anyone wrote. | The story line, with the `@handle` tag lit up |
| **Rolled by** | One of the day's voters, picked at random, is credited with the roll. The server still rolls, with the same real odds. | "ROLLED BY @tom" on the die card |
| **First to shout** | The first 3 people (by time) who shouted the word that made it into the story (§3.3) are credited. | "@mira, @sam, @lee and 11 others cried: TORCH" |
| **The Chronicle** | A public page (`/chronicle`) with the party now, past companions and credits per episode. | Linked in the bio and captions |

**Companions are story characters, drawn by the server.** A joiner's companion gets a class, a
look and a name from fixed lists (seeded draws, so they're the same on every re-render), not from
anything the person wrote. The link between a companion and a username exists only on our server
and in the rendered video. That's what lets DeepSeek write the companions without ever knowing who
they belong to (§5).

**What companions face:** they can be wounded, and in a dramatic moment fall. That's always the
story's doing (dice, choices), never aimed at the person, and handled gently: a fallen companion
gets an epitaph card, and its owner can rejoin with a new one.

Names are **shown, never spoken**: the narrator never says usernames, so voice costs don't change and
nothing new goes to ElevenLabs. Offensive usernames are never shown, as on the quiz: they're dropped
from joining and from credits.

## 3. The Voices: what the comments decide

All of this fits in one comment with the vote: `A sly torch` counts as option A, done slyly, shouting
"torch" (the parser already reads `A ...` as a vote for A).

### 3.1 What: the option (as now)

### 3.2 How: a way as well as an option

| Way | Comment | Skills it uses | In the story |
|---|---|---|---|
| **BOLD** | `A bold` | athletics, intimidation | head-on, loud, brave |
| **SLY** | `A sly` | stealth, sleight of hand, deception | quiet, tricky |
| **WISE** | `A wise` | perception, arcana, persuasion | careful, clever |

The winning way sets the check's skill (from this hero's real odds) and the story's tone. If nobody
names a way, the node's own skill is used.

### 3.3 How well: Rally

Turnout adds to the roll: **+1 at 10 voters, +2 at 25, +3 at 50**, shown on the die card
("+2 RALLY · 31 VOICES"), and the odds on screen include it. The thresholds go up as the channel grows.

### 3.4 What turns up: shouted words

A word from the **Shout List** (about 300 fantasy words: torch, rope, wolf, sing, bread…) in a comment
counts as that person's shout, one each. Once **3 or more different people** have shouted a word, it
goes to DeepSeek as a count, and **the top word has to appear in the next episode** (the validator
checks). The list is fixed, so nothing free-form or offensive can reach the story, and one person
can't steer it.

### 3.5 The Voices as a character

The crowd is a chorus the hero hears. The text can use the totals ("Thirty voices roar *fight*",
"The Voices are split. The hero hesitates."), so a close vote and a landslide read differently.

## 4. How an episode gets made

```
Tuesday (Claude routine, as now)          Every day, 08:00 (server)
  the week's plan: beats, foe, scenes,      read yesterday's comments (on the server only):
  a planned node per day (the fallback)       votes, ways, shouts, joins, leaves, who voted
                                            party: joins/leaves → places → server draws class/look/name
                                            credits chosen on the server (rolled by, first to shout)
                                          ─► DeepSeek gets STORY DATA ONLY (§5) → today's node
                                            validate with the engine (+ follows the winning option,
                                              top shout word appears, skill matches the way,
                                              the chosen companion gets its moment) → ✗ retry ×2 → planned node
                                            server rolls (with Rally) → server adds @handles to the spec
                                            voice (no names) → render → Discord preview, 45 min to `hold`
                                            09:00 post
```

The dice stay honest: the server sets the skill, the Rally bonus and the roll; DeepSeek only sets
the DC within the validator's limits and writes the words. Each call costs under 1p a day.

## 5. The DeepSeek boundary

**What DeepSeek receives**, all of it story data or totals:

- the season bible, this week's plan, the campaign state and the last 3 episodes (our own text);
- the party as **story characters only**: `slot 2: "Ash", dwarf rogue, wounded`. The server drew those,
  so nothing in them comes from a person;
- which slot gets today's moment (picked at random on the server);
- totals: votes per option, per way, shouted words with 3 or more shouters, the number of voters.

**What it never receives:** usernames, account ids, comment text, who voted or shouted what,
who's in which slot, credits, or anything a single viewer wrote or did. The server adds the
`@handle` tags to the spec *after* DeepSeek has answered, at render time.

**How it's enforced in code:** the DeepSeek prompt is built from a fixed set of fields
(`writer.prompt_input()`), with a test that fails if any username, account id or comment text from
the day's tally appears in it. The request is also logged (the input without the key), so it can
be checked.

So DeepSeek handles no personal data: there's nothing to list in the privacy policy, and its
storing data in China doesn't involve viewers.

## 6. On screen

Within the current look (the episode stays about the same length; the hook already shows today's choice):

- **Hook**: "TODAY YOU DECIDE" with the options, plus "how? BOLD · SLY · WISE · shout a word · `join` the party".
- **Party**: up to 5 companions behind the hero, each with a parchment `@handle` tag.
- **Recap card**: "The Voices chose **A**, **sly**, 23 to 9", then "@mira, @sam, @lee and 11 others cried: **TORCH**".
- **Die card**: the way's skill, "+2 RALLY · 31 VOICES", "ROLLED BY @tom", and odds including Rally.
- **Ask**: "Comment A, B or C + bold, sly or wise + a word to shout. `join` to join the party."

## 7. Privacy policy update (ships with phase 1)

Stories become like the quiz: names can appear in videos, on the same lawful basis (legitimate
interests) and with the same opt-out. Changes to `app/legal/privacy.html`:

1. **In short**: "on story videos, to count your vote, way and shouted word (only the totals are
   kept), and if you comment *join*, to put your username on a companion in the story".
2. **Section 2 (what we collect)**: add party members (account id, username, place, when you joined,
   when you last commented) and story credits (username, episode).
3. **Section 3 (purposes)**:
   - *Story videos: votes*: votes, ways and shouted words counted, one per account. Only totals are kept,
     except that a random voter may be credited with the roll ("rolled by @you") and the first 3 people
     to shout the word that's used may be named in the next episode.
   - *Story videos: the party (new)*: comment *join* to be given a companion with your username in each
     episode while you're in the party. You leave after 3 episodes without a comment, by commenting
     *leave*, or by opting out. Party members and credits are listed on `/chronicle`.
   - The balancing test also covers story videos (you chose to comment and to join, it's limited to
     the story, and you can leave or opt out at any time).
4. **Section 4 (who else)**: Discord "can name quiz shout-out winners and story party members and credits";
   ElevenLabs is unchanged (story narrators never say names). Add one sentence, without naming
   a processor (it isn't one): "Story episodes are drafted with the help of an AI writing tool that
   is given only the story and vote totals: never usernames, comments or anything about you."
5. **Section 5 (retention)**: party members while in the party, then the username is removed **$days days**
   after leaving (the companion stays in the story under its story name); credits for **$days days** after
   the episode, like shout-outs; names in published videos stay until removed on request (as now).
6. **Erasure and opt-out** (`app/privacy.py`): `#optout` and the request form also remove party membership
   and credits, and the companion leaves the party in the next episode.
7. **The story explainer video** (`render_explainer_adventure.py`) gets a scene for joining and
   credits, so the policy's videos stay accurate.

## 8. What changes in the code

| Area | Change |
|---|---|
| `app/adventure/votes.py` | tally ways, shouts (fixed list, first per person, ≥3 people), joins and leaves; keep voter names only in memory for the day's credits |
| `app/adventure/party.py` (new) | places, queue, weekly random place, 3-episode rule, server-drawn companions, credits, retention, opt-out and erasure hooks |
| `app/adventure/shouts.py` (new) | the Shout List, companion name/class/look lists |
| `app/adventure/writer.py` (new) | DeepSeek client (OpenAI-compatible: `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`), `prompt_input()` (story data + totals only), validate/retry, fallback, cost log; the boundary test |
| `app/adventure/campaign.py`, `jobs.py` | Rally, skill from the way; 08:00 tally → party → writer → dice → handles → voice → render; `hold` |
| `adventure/packages/shared`, `engine/story.ts` | spec fields `party`, `voices`, `rally`, `credits`; party bar, tags, recap/die-card lines, ask |
| `app/legal`, `app/privacy.py`, explainer | §7; `/chronicle` |
| metrics | tags `writer: deepseek / fallback`; extras: joins, party size, way votes, shouts counted, rally, voters |

## 9. Phases

| Phase | What | AI | Success looks like |
|---|---|---|---|
| **P1 Party + ways + Rally** | joining, companions with `@handle`, rolled by, the 3-episode rule, ways, Rally, the policy update (§7), `/chronicle` | none (the planned nodes as now; companions appear and walk, without lines) | comments per 1,000 views above 24; voters and returning commenters rising |
| **P2 Writer** | DeepSeek adapts each planned node: the way's tone, the Voices, the top shout, a companion's moment; safe fallback | DeepSeek (no personal data) | ≥ 90 % of days pass validation first or second time; no holds needed |
| **P3 Free plan** | the weekly routine writes beats, and DeepSeek writes the node; naming votes; companions' fates | DeepSeek | shouts and joins per post rising; watch time holding |

## 10. Decisions needed

1. **Where**: upgrade @dungeoncrawlergram (recommended) or a new account?
2. **Party size and rules**: 5 places, leave after 3 episodes without a comment, one random place a week (recommended)?
3. **Start with P1** (party, ways, Rally, policy; no AI) (recommended)?
4. **Moderation**: Discord preview with `hold` (recommended), or your approval before each post?
