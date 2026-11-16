# raosanta.uk: promo videos for Random Acts of Santa

Plan agreed with the owner on 16 Nov 2026. The channel promotes [raosanta.uk](https://raosanta.uk)
(Random Acts of Santa: anonymous Christmas gifting from Amazon wishlists, for workplaces, communities
and friends groups) during the season, which runs from 15 Nov to 6 Jan. The site's own repo is
`Stayingfalse/rast3`.

## 0. Decisions

| | Decision |
|---|---|
| Account | **@raosanta.uk** on Instagram and YouTube (`SANTA_HANDLE`, `SANTA_PLATFORMS`) |
| Cadence | **One post every 22 hours**, inside 07:00-22:30 UK: each post lands two hours earlier in the day than the one before (§2) |
| Other channels | Never within 60 minutes of another channel's post, and never rendering while another channel renders (§2). The Santa channel always gives way. |
| Voice-over | **Half the posts.** Tutorials and pitches have a voice-over; quizzes, season updates and kudos spotlights use music and on-screen text (§3). |
| Kudos | Every kudos posted before the opt-in checkbox ships counts as consented (an older privacy policy covered it). New ones need the poster's tick. **Every one still needs a site admin's approval** before the bot can use it (§5). |
| Figures | Rounded, site-wide totals only, as the home page shows (under 10 hidden). Never names or per-group numbers. |

## 1. What the channel posts (about 7 a week, 20-35 s each)

| Format | Per week | What's in it | Voice |
|---|---|---|---|
| **Tutorials** | 2 | Real screen recordings of the site on a phone, made from the e2e seed data on dev (§5): share your wishlist, join with a work email, link a Discord server, invite friends, pick up a wishlist, mark it gifted, post kudos, the stamp album | Narrator |
| **Pitches by audience** | 1-2 | One audience at a time: **workplaces** ("Remote team? No home addresses needed"), **communities and Discord servers**, **friends and family** ("Hate the Secret Santa draw?"). Each ends on "Random Acts, not Secret Santa". | Narrator |
| **Christmas quizzes** | 2 | The quiz engine in the site's colours (postbox red, night blue, gold), Christmas themes | Music only |
| **Season updates** | 1 | Live rounded figures, days left to Amazon's last order date, gifts this week | Music only |
| **Kudos spotlights** | 1 | An approved thank-you postcard: photos and message under its festive name | Music only |

**How the mix shifts through the season:**
- **November:** tutorials and pitches, to get sign-ups.
- **December:** more season updates, kudos and the last-order countdown.
- **January:** a recap, then quiet until next season.

From the channel review (CHANNEL_REVIEW_AND_NEXT.md), every video:
- gets to the point in the first second;
- uses an identity hook ("Remote team?");
- stays short (people watch 8-12 s whatever the length).

## 2. When it posts (built: `app/santa/schedule.py`, `app/slots.py`)

**The pattern.** One post every `SANTA_CADENCE_HOURS` (22), counted from an anchor:
21:30, 19:30, 17:30 … 07:30. A step that would land before `SANTA_WINDOW` opens (07:00) goes to
`SANTA_ANCHOR` (21:30) that evening instead. That makes an 8-day cycle with one 38-hour gap, about
7 posts a week. A step after the window closes would go to the next morning's opening time; that
only happens with other cadences.

**Keeping clear of the other channels.** `app/slots.py` reads every running channel's schedule:
- the quiz's daily `POST_TIME` and any extra bookings;
- the weekly quiz carousel;
- the Dungeon crawl's daily time and booked parts;
- Farside's daily post, extras and roll call;
- racing when it's switched on.

Each post has a render window before it: the channel's render lead, lasting `SLOT_RENDER_MINUTES`.
A Santa slot clashes if it's within `SANTA_BUFFER_MINUTES` (60) of another channel's post, or if its
render overlaps another channel's render. A clash nudges that one post in 15-minute steps:
- nearest first, later before earlier;
- up to `SANTA_NUDGE_MAX_MINUTES` (180), inside the window;
- the rest of the pattern stays where it was.

If there's no free time within that range, the slot is skipped and the reason recorded.

The next slots from 17 Nov, with Farside on:

| Slot | Posts at | Why |
|---|---|---|
| Tue 21:30 | 21:30 | |
| Wed 19:30 | **20:00** | Farside posts at 19:00 |
| Thu 17:30 | 17:30 | |
| Fri 15:30 | 15:30 | |
| Sat 13:30 | **13:45** | Farside roll call at 12:40 |
| Sun 11:30 | **11:00** | the quiz posts at 12:00 |
| Mon 09:30 | **10:00** | the Dungeon crawl posts at 09:00 |
| Tue 07:30 | 07:30 | |
| Wed 21:30 | 21:30 | back to the anchor |

**Endpoints (token):**

| Endpoint | What |
|---|---|
| `GET /santa/state` | Settings, anchor, the next 3 slots |
| `GET /santa/slots?count=` | The next slots, with `nudged`, `avoided` or `skipped` |
| `PUT /santa/anchor?at=YYYY-MM-DDTHH:MM` | Set the pattern's first slot (local time, inside the window) |
| `GET /slots/busy?hours=&channel=` | Every running channel's posts and renders (`channel` leaves that one out) |

## 3. Voice-over

Tutorials and pitches have a voice-over, about 3-4 posts a week at about 400 characters each:
roughly 6-7k ElevenLabs credits a month. The 30k a month is already split: Farside 15k, Dungeon
crawl 10k, quiz about 5k. **Still to decide:** trim the others until 6 Jan, or add credits for
December. `SANTA_VOICE_BUDGET` will cap it, and past the cap a video goes out without the voice.

## 4. TechNews-Bot: the build, one step a day

1. ✅ **The clash guard and the channel**: the `santa` channel (kind `promo`, off unless
   `SANTA_ENABLED`), its settings, `app/slots.py`, `app/santa/schedule.py`, the endpoints above,
   and tests (`tests/test_santa_slots.py`).
2. ✅ **Renderer and look, previews to Discord.**
   - **Spec** (`app/santa/spec.py`, `GET /santa/schema`): a promo is 2-10 segments: `title`,
     `points`, `steps`, `figures`, `question`, `kudos` and a closing `end` card. Each segment can
     have a narrator line (`say`). *Asterisks* make words gold. Emoji are refused, because Archivo
     has none.
   - **Look** (`app/render/santa/`): rast3's `DESIGN.md`, meaning a night-blue sky with snow and gold
     stars, cream postcards with an airmail edge, the 2026 stamp (rasterised from rast3's
     `public/brand/stamps/2026.svg` into `assets/santa/`), Archivo copied from rast3
     (`assets/fonts/Archivo-*.ttf`, OFL), postbox red and gold.
   - **Music** (`app/render/santa/carols.py`): Jingle Bells (1857), Deck the Halls and We Wish You a
     Merry Christmas (traditional), played on a glockenspiel over sleigh bells, made in code, so
     there's nothing to license.
   - **Narrator** (`app/santa/voice.py`):
     - `SANTA_VOICES`: Lily (a built-in voice, works on any plan) by default, or Archie (a young
       British library voice) by `voice_name`;
     - `SANTA_VOICE_MODEL`: `eleven_multilingual_v2`;
     - `SANTA_VOICE_BUDGET`: 7,000 characters a month, recorded in `DATA_DIR/santa/credits.json`;
     - only tutorials and pitches are voiced unless the spec sets `voice`;
     - lines are cached, so a re-render costs nothing;
     - with no key, an exhausted budget or an ElevenLabs error, the video goes out with music and
       text only.
   - **Timing:** a segment stays on screen until its line has been said; a read-out question starts
     its countdown once it's been asked; anything over 45 s is refused before rendering.
   - **Previews:** `POST /santa/preview` (a spec) renders in the background and sends the video to
     Discord; nothing is posted. `GET /santa/previews[/{id}]`. Locally:
     `python render_santa.py examples/santa/quiz-christmas.json out/q.mp4`.
3. **Booking.** `POST /santa/week` takes the routine's posts and places them into the next free slots;
   preview, cancel and retry as Farside does; the scheduler renders `SANTA_RENDER_LEAD_MINUTES`
   before each post and posts at the slot. Metrics tags: `format`, `audience`, `voice`.
4. **Live data** (`app/santa/source.py`): figures and approved kudos come from raosanta's promo API at
   render time. If the site can't be reached, or a figure is hidden, that card is left out and the
   video still goes out.
5. **Tutorial clips**: uploaded from rast3's recording script (`PUT /santa/clips/{name}`).
6. **The weekly routine** (`docs/SANTA_ROUTINE_PROMPT.md`): picks the week's mix for the season
   phase and last week's numbers, writes the scripts and quizzes, and checks quiz facts. The weekly
   review covers this channel too.

## 5. rast3 (raosanta.uk)

Branch → `dev` → test on dev.raosanta.uk → PR into `main`; one fundamental change a day.

1. **`GET /api/promo/stats`** (server-to-server token `PROMO_API_TOKEN`):
   - totals rounded with `roundForPublic`, and groups by type, also rounded;
   - gifts this week;
   - season dates and days to the last order date.
2. **Kudos for social media:**
   - a migration adds `socialConsent` (yes/no, when, why) to `Kudos`, with every existing kudos set
     to consented ("older privacy policy");
   - a "Happy for this to be featured on Instagram/YouTube" checkbox for new kudos, changeable later;
   - a site admin's "For social" approval queue;
   - `GET /api/promo/kudos` returns only kudos that are consented, approved and not hidden;
   - the privacy policy names the use and the recipients (Meta, Google);
   - a withdrawn kudos drops off the list, and the bot flags videos already posted for a manual
     take-down.
3. **Sign-up attribution:** keep `utm_source` and `utm_campaign` from the first visit on the
   account, so the dashboard shows which pitch brings sign-ups.
4. **Tutorial recordings** (`scripts/promo-clips`): Playwright on dev with the e2e seed data at
   phone size, re-recorded when the UI changes. Real members never appear.
5. **Prod:** the owner sets `PROMO_API_TOKEN` on `ras/raosanta-uk`.

## 6. Still open

- Where the extra ~7k ElevenLabs credits come from (§3).
- Outside the season: pause the channel, or post a weekly countdown.
