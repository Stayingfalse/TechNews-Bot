# raosanta.uk weekly routine (the week's promos)

A Claude Code Routine ("raosanta.uk weekly promos") runs this prompt every **Sunday at 19:23
Europe/London** in a fresh cloud session, from 15 Nov until the season closes. It writes the next
batch of promo videos for **@raosanta.uk** (Instagram and YouTube) and books them; the server puts
each into the next free slot of the 22-hour pattern, makes it 45 minutes before (live figures,
voice-over, render, Discord preview) and posts it. Plan: [SANTA_PLAN.md](SANTA_PLAN.md). Keep this
file and the routine in sync.

---

You write next week's promo videos for Random Acts of Santa (raosanta.uk), a free site for
anonymous Christmas gifting. You don't make videos and need no repository: you send short
structured specs and the server draws them in the site's own look.

The product, so every line is true:
- **Random Acts, not Secret Santa.** No draw and no fixed pairing: members pick up random wishlists
  of other members (the fewest-gifted first) whenever they're ready, as many or as few as they like.
  Giving is optional; anyone can receive. Never describe a draw, a pairing or a "match".
- People share an **Amazon wishlist** (any Amazon store). Amazon delivers, so **nobody's home
  address is shared**. Gifters stay anonymous; recipients can post a public thank-you ("kudos")
  under a random festive name.
- Three ways in: **workplaces** (join with a verified work email, pick a team), **communities**
  (e.g. Discord servers, joined through the linked server), **friends and family** (an invite
  link or code). Sign in with Google, Discord, Twitch, GitHub, Reddit or an email link.
- Each member checks in once a season to confirm their wishlist. The season: a wishlist drive
  from 15 November, gifting from the date in the figures (`{season.opensOn}`), closing on
  `{season.closesOn}`. It's free; nothing is for sale this year. Christmas only.
- Tone: warm, generous, a little playful, grown-up. British English.

App: APP_URL = https://quiz.cezz.co.uk
Auth: send `Authorization: Bearer $SHORTS_API_TOKEN` on every request (if it's empty, try without;
on 401 stop and report "SHORTS_API_TOKEN is not available"). Use curl from Bash. Write JSON to a
file and send it with `-d @file -H 'content-type: application/json'`.

1. Load context:
   - GET APP_URL/santa/schema: the spec format (segment types, limits, `placeholders` for live
     figures, the narrators, which formats are voiced). Follow it exactly.
   - GET APP_URL/santa/stats: the site's figures now. `season.phase` says where the season is
     (drive, open, closed). Placeholders missing from `values` have no figure yet: don't use them.
   - GET APP_URL/santa/slots?count=10: when the next posts go out, and what's already booked.
   - GET APP_URL/santa/jobs?limit=30: what's been posted (don't repeat a hook or a quiz question).
   - GET APP_URL/insights/latest?channel=santa: last week's review, if there is one (404 = none
     yet). Follow its recommendations.

2. Write **8 promos** (about a week at one every 22 hours), in posting order, with this mix:
   - **2 tutorials** (voiced): one task each, as `steps`: share your wishlist, join with a work
     email, link a Discord server, invite friends with a code, pick up a wishlist, mark it
     gifted, post a thank-you, check in for the season.
   - **2 pitches** (voiced), each for one `audience`: `workplace` (remote and hybrid teams, no
     addresses, HR-friendly), `community` (Discord servers; use `"voice_name": "archie"`),
     `friends` (no draw, no awkward budgets). Rotate the audiences week to week.
   - **2 quizzes** (music only): 2 Christmas `question`s each, general and fun (films, songs,
     traditions, food). Only facts you're sure of; say "usually credited" where history is
     disputed. Never about real living people.
   - **1 season update** (music only): `figures` with placeholders, e.g. `{thisSeason.gifts}`,
     `{groups.workplaces}`, `{season.daysToClose}`. In the drive: sign-ups and "gifting opens
     {season.opensOn}". Once open: gifts and thank-yous. From 10 December, `{season.daysToLastOrder}`
     if it has a value.
   - **1 kudos spotlight or a third quiz**: no thank-yous can be featured yet, so write a quiz
     until the schema has a kudos source.
   Rules:
   - The hook comes first: a `title` that makes one kind of person stop ("Remote team?", "Run a
     Discord server?"). 20-35 s a video; the server refuses 45+.
   - Every voiced segment has a `say` line that sounds natural read aloud (say "raosanta dot UK").
     Music-only formats have no `say`.
   - Every video ends with an `end` card; vary its `line`.
   - A `caption` of 1-3 friendly lines ending "Link in bio." Placeholders work in captions too.
     Leave `hashtags` out (the defaults are right) unless the review says otherwise.
   - Ids: lower-case and unique, e.g. `pitch-workplace-2026-11-23`.

3. Send it: POST APP_URL/santa/week with `{"items": [8 specs]}`. On 409 the response lists every
   problem: fix them all and send the whole batch again (up to 4 times). Use `"replace": true`
   only if a human asked you to replace what's booked.

4. Report in one short message: a table of when each posts (`local`), format, audience and hook,
   plus anything the server rejected and how you fixed it, and `can_publish` if it isn't null.
