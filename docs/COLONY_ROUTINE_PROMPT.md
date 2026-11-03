# Farside weekly routine (the week plan)

A Claude Code Routine runs this prompt every **Sunday evening (Europe/London)** in a fresh cloud
session. It writes next week's 7 episodes of Farside (@farside.colony) and 2 spares, and sends
them to the server, which checks them. Each day another routine ([COLONY_DAILY_PROMPT.md](COLONY_DAILY_PROMPT.md))
adapts that day's episode to what people asked for. If that doesn't happen, the plan plays as
written, so **every planned episode must work with nobody new and nothing adapted**. Plan:
[COLONY_PLAN.md](COLONY_PLAN.md) §5a-5b. Keep this file and the trigger in sync.

---

You plan next week of Farside, a daily pixel-art story on Instagram about a small colony on the
far side of a moon. Every follower is a settler, and anyone who comments gets a named settler of
their own. The videos are drawn by code from the episodes you write; you don't make videos and
need no repository.

App: APP_URL = https://quiz.cezz.co.uk
Auth: send `Authorization: Bearer $SHORTS_API_TOKEN` on every request (if it's empty, try without; on 401 stop and report "SHORTS_API_TOKEN is not available").
Use curl from Bash. Write JSON to a file and send it with `-d @file -H 'content-type: application/json'`.

1. Load context:
   - GET APP_URL/colony/schema: the episode format (beat types, slots, events, the sprite kit, the founding crew and the length limits). Follow it exactly.
   - GET APP_URL/colony/today: the colony now (followers, what's built and being built, the next milestone), the story so far (one line per episode), and the people who've been commenting, with their sheets.
   - GET APP_URL/insights/latest?channel=colony: last week's review, if there is one (404 = none yet). Follow its recommendations.

2. Plan the week as a story with one thread through it (a signal, a stranger, something under the ice, a festival to get ready for) and one beat a day that moves it on. Rules:
   - People first. The channel works when it's about the people in it. Every episode starts with the `arrivals` slot, so newcomers are welcomed first, and most have the `people` slot (jobs, ranks, recruits). Give featured settlers moments with `"who": "$1"` (and `$2`), which the server fills with that day's newcomers and most active settlers. If nobody's there, the beat is left out, so never put a story-critical line on `$n`.
   - The founding crew (MAREN, TOLU, BASK, IKO; see the schema for who they are) carry the story on quiet days. Keep them in character.
   - One `decision` in the week (or two, not on neighbouring days), always about a person or the colony: "@$1 found a sealed door: OPEN IT / LEAVE IT". A decision ends its episode. The next day's episode should start by showing what was decided (the daily routine fills in who chose what).
   - Use story `event`s (dust_storm, signal, aurora, meteors, quake, night) for the thread, not as filler: two or three a week.
   - Short: aim for about 30 s an episode (the server estimates every slot at its longest). 40 s is the hard limit, for big days; the response's `notes` say which episodes are over 30.
   - Text: caption lines at most 24 characters, speech lines at most 18, split with `|`. `*word*` makes a word gold. Only the characters the font has (A-Z, 0-9, . , ! ? ' : - + % @ / # &). No links, nothing a 13-year-old shouldn't see, and no real people, brands or other creators' characters.
   - Each episode has `date`, a `title`, a one-line `summary` (the story so far, at most 200 characters), `beats` and the post's `caption` (1-3 friendly lines that end by inviting people to comment to move in; no hashtags beyond #farside #pixelart #story).
   - Two `spares` (no date) that fit any day of any week: a quiet night, a meteor shower, something cosy. They play if a week ever starts without a plan.

3. Send it: POST APP_URL/colony/week with `{"week_start": "<Monday's date>", "episodes": [7], "spares": [2]}`. On 422 the response lists every problem: fix them all and send the whole week again (up to 4 times). Use `?replace=true` only if a plan for that week already exists and a human asked you to replace it.

4. Report in one short message: the week's thread in a sentence, a table of date, title and the beats (slots in brackets), the decision(s), and anything the server rejected and how you fixed it.
