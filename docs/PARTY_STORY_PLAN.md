# Party story: a D&D adventure the commenters are part of

**Status: proposal, for decisions (§9).** It builds on the dungeon crawl
([ADVENTURE_PLAN.md](ADVENTURE_PLAN.md)), the channel that has done best so far (§1), and adds a
daily DeepSeek step that writes each episode from the planned story plus what viewers commented.

## 1. Why

On the dungeon crawl, commenting already changes the story, and it has done better than the other
channels (24 h, Instagram):

| | Quiz | Dungeon crawl | Racing |
|---|---|---|---|
| Median views | 139 | **492** | 34 |
| Comments per 1,000 views | 14 | **24** | – |
| Best post | 597 views | **1,114 views, 22 comments, 19 voters** | 133 |

Its best part asked viewers to choose who *they* would be (the hero's class). A vote only picks
one of three options, and the voter disappears into a total. The next step is to make each
commenter visible and lasting in the story: their name on screen, their idea in the plot, their
character in the party, something in the world named after them. Seeing yourself in the next
video is the strongest reason there is to comment, and to come back the next day to check.

## 2. What a viewer can do

Ranked by how much each should drive comments, against how hard it is to build and moderate.

| # | Mechanic | What the viewer sees | Why it works | Build |
|---|---|---|---|---|
| 1 | **Join the party** | Comment `join` (or vote) to become a companion: a small standee with `@handle` walking behind the hero. The party has up to 5 places, taken by the most active commenters, with one place a week given at random to someone new. | You're *in* the video, and you stay in it while you keep commenting | small: standees and names exist; persistent party state |
| 2 | **Write-in choices** | Beside A/B/C: "or comment your own idea". The best write-in that fits the story can become tomorrow's twist, credited on screen: "*@mira's idea*: the bard talks to the ghost" | Building your own story is the request; credit makes it worth trying | the DeepSeek step (§4) |
| 3 | **Companions act** | Each episode, one party member gets a moment: "*@tom* spots the trap" (one line of story). Who acts is weighted by who commented that day | Being written into the action, not just named | DeepSeek step |
| 4 | **Roll the die** | "Today's die is rolled by *@amy*": a voter picked at random. The server still makes the roll (real odds, as now); the credit is theirs | Cheap, personal, and comes back every day | tiny |
| 5 | **Own a piece of the world** | When a write-in is used, its author names something: a place, an item or a creature ("the Mirefang, named by @sam"). Kept in a public **Chronicle** page: who owns what, every episode, every credit | Lasting ownership; a page people share | medium: a page like the racing bets pages |
| 6 | **Companions can fall** | Party members can be wounded or lost in the story (never as a punishment, and never as anything that reads as being about the real person); a fallen companion gets an epitaph card and can rejoin as someone new | Stakes for the people in the party | DeepSeek step plus rules |

Start with 1, 2 and 4 (§8), then add 3, 5 and 6 once the safety side has been shown to work.

## 3. Same channel or a new one? (decision 1)

| | Evolve **@dungeoncrawlergram** into the party story | A new account |
|---|---|---|
| Audience | keeps the only story audience that comments (19 voters on its best day) | starts from zero, which is the cold start that has held racing back |
| Story | season 1 (*Childe Rowland*) is running; the party joins as the hero's companions, a natural story beat | a clean start with its own premise |
| Risk | a failed experiment affects the channel that works | a failure costs nothing |
| A/B | a before/after comparison on one channel | two channels to compare, but with very different reach |

**Recommendation: evolve the dungeon crawl.** Introduce it in the story ("travellers join you at
the inn"), first with 1 and 4 only, which need no AI step. Then switch on the daily DeepSeek step.
A new account can come later as a separate setting once the format is proven.

## 4. How an episode gets written

The weekly routine stays the story's planner and DeepSeek does the daily writing, so the story
keeps a direction while viewers' ideas still change it.

```
Tuesday (Claude routine, as now)          Every day, 08:00 (server)
  writes the week's SPINE:                   read comments on yesterday's post
  beats, goal, foe, scenes,                    → votes, joins, write-ins, party activity
  1-2 possible twists                          → filter (§6), pseudonymise (P1, P2…)
  (not every branch any more)                ─► DeepSeek: spine + campaign state + party
                                               + yesterday's episode + today's comments
                                               → today's node (same JSON as now) + credits
                                             validate with the engine (validate-arc: schema,
                                               scenes, foes, DCs, word and voice limits)
                                               ✗ → send the problems back, at most 2 retries
                                               ✗✗ → fall back to the spine's planned node
                                             roll dice (server, as now) → voice → render
                                             Discord preview, 45 min to veto (§6)
                                             09:00 post
```

- **The output is the node the renderer already draws** (`adventure/packages/shared/src/arc.ts`:
  hook, story, check, after, ask, 2-3 choices), plus a `credits` list. DeepSeek can't invent
  anything the renderer can't draw, and the engine's validator rejects anything off-schema or too
  long. This is the same check and retry loop the weekly routine uses now.
- **Fallback**: if DeepSeek fails, times out or keeps failing validation, the episode plays the
  spine's planned node and the day goes out anyway. The plan never depends on the API.
- **Dice stay honest**: DeepSeek sets the skill and DC within the validator's limits; the
  server rolls. Nobody can talk the dice into anything.
- **Prompt** (kept in the repo like `ADVENTURE_ROUTINE_PROMPT.md`): the rules, the season bible,
  this week's spine, the campaign state (hero, hearts, party, named things), the last 3 episodes,
  then the comments as *quoted data*, each with a token: `P3: "the bard should sing to the ghost"`.
  Expected output: JSON (DeepSeek's JSON mode), validated.
- **Cost**: a call is about 10-15 k tokens in and 1-2 k out. At DeepSeek's published
  flash-model prices ($0.14 per million tokens in, $0.28 out) that's under 1p a day, even with
  retries. The voice cost doesn't change: names are on screen only, never narrated, and narration
  stays under the current 280-character daily cap.

## 5. On screen

Within the current look (the episode stays roughly the same length; the hook shows today's choice, #12):

- **Party bar**: up to 5 small standees behind the hero, each with a parchment `@handle` tag.
- **Credits**: a parchment ribbon when a viewer's idea plays: "*@mira's idea*". The die card says
  "rolled by @amy".
- **The ask**: "Vote A, B or C, or comment your own idea", "comment `join` to join the party".
- **Chronicle page** (`/chronicle`, public): the party, who joined when, every credit, every named thing,
  every episode. It's the place to link to, like the racing bets pages.

## 6. Safety and privacy (must be in place before launch)

Viewers' comments become the prompt, and their names appear on screen, so:

1. **Names never go to DeepSeek.** The server replaces each commenter with a token (`P1`, `P2`)
   and strips @mentions, links and anything that looks like contact details from the comment text.
   DeepSeek only ever writes tokens; the server puts `@handle` back in when rendering. That means
   the model can't misspell, invent or insult a name.
2. **Only filtered comments reach the prompt.** Comments are capped at 200 characters, checked against
   a blocklist and limited to one per person, and the existing offensive-username check and the
   opt-out list apply. Comments are passed as quoted data, with an instruction that nothing in them
   is an instruction. The output is schema-checked anyway, and a
   comment saying "ignore your rules" can at worst become a rejected write-in.
3. **What's shown is DeepSeek's retelling of an idea, never the comment itself**, and it's previewed on
   Discord 45 minutes before posting, with a `hold` command that swaps in the fallback node.
4. **Privacy policy changes** (it currently says story videos show no names and the story AI only sees
   totals): add party names, credits, the Chronicle, "rolled by", DeepSeek as a processor and what
   it receives (pseudonymised comment text, no usernames), retention (credits as the quiz's
   shout-outs; party membership while active, then anonymised), and how to opt out (the existing
   `#optout` and form). Joining is opt-in by commenting `join`; credit for a write-in is
   announced in the ask.
5. **DeepSeek's terms**: its privacy policy says it stores personal data in mainland China, a
   country with no UK/EU adequacy decision, and sources disagree on whether API inputs can be used
   for training. Pseudonymising (1) keeps what's sent to the comment text alone, but that is still
   personal data in law, so this needs a transfer assessment, or (decision 3) DeepSeek's open models
   from a host in the UK, EU or US. Check the current Open Platform terms before launch.
6. **Teen and up**, as the season is now: the prompt sets the tone, and the validator and preview
   catch anything else. No real people, no real-world politics, no sexual content, and a companion's
   fate is never written as a comment on the real person.

## 7. What changes in the code

| Area | Change |
|---|---|
| `app/adventure/party.py` (new) | party state (members, joined, last active, status), join/leave parsing, weekly random place, opt-out hooks |
| `app/adventure/writer.py` (new) | comment filter + pseudonymiser, DeepSeek client (OpenAI-compatible, `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`), prompt build, validate/retry, fallback, cost log |
| `app/adventure/campaign.py` | spines instead of full branch graphs (the weekly routine writes beats plus a fallback node per day) |
| `app/adventure/jobs.py` | 08:00: tally → writer → dice → voice → render; `hold` from Discord |
| `adventure/packages/shared` | `credits`, `party`, `rolledBy` in the node/spec schema; spine schema |
| `adventure/packages/engine/story.ts` | party bar, credit ribbon, "rolled by" on the die card, write-in line in the ask |
| `app/legal` | privacy policy + `/chronicle` page |
| metrics | tags `writer: deepseek / fallback / spine`, `party_size`, `writeins_used`; extras: joins, write-ins, credited viewers |
| docs | `ADVENTURE_ROUTINE_PROMPT.md` (spines), new `PARTY_WRITER_PROMPT.md` |

## 8. Phases

| Phase | What | No AI? | Success looks like |
|---|---|---|---|
| **P1 Party** | join, party bar, "rolled by", the Chronicle page, privacy policy update | yes | joins and returning commenters; comments per 1,000 views above 24 |
| **P2 Writer** | the DeepSeek step on today's arc nodes: it adapts the planned node (wording, a companion moment, a credited write-in) but keeps its branches. Safe to fall back | DeepSeek | ≥ 90 % of days pass validation first or second time; no holds needed for content |
| **P3 Free story** | spines instead of graphs: DeepSeek writes the node itself; write-ins can change the plot; owning a piece of the world | DeepSeek | write-ins per post rising; watch time holding |
| **P4** | companions' fates, a second hero class from the party, YouTube Shorts | | |

Each phase is tagged in the metrics, so the review can compare before and after.

## 9. Decisions needed

1. **Where**: evolve @dungeoncrawlergram (recommended) or a new account?
2. **Which mechanics first**: P1's party, "rolled by" and the Chronicle (recommended), or straight to write-ins?
3. **DeepSeek host**: DeepSeek's own API (your credits; data stored in China, see §6.5) or its
   open models from a UK, EU or US host?
4. **Names in the voice-over**: on screen only (recommended: cheaper, and the privacy policy already
   says story narrators never say names), or read out too?
5. **Moderation**: Discord preview with `hold` (recommended), or also require approval before
   any write-in plays?
