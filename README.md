# TechNews-Bot (now: daily quiz shorts)

A daily quiz short (guess the movie from emojis, badly described films, real-or-fake, odd one
out, unscramble, multiple choice), rendered entirely in code with its own music and posted to
YouTube Shorts and Instagram Reels with no manual steps.

```
Claude Code Routine (Mondays 19:05)        Easypanel app (this repo)
  plan 7 themes, write 7 quizzes,    ──►  POST /schedule (7 dated quiz specs)
  verify the facts                          │  checked + stored (no video yet) → week summary in Discord
                                            ├─ 45 min before each slot: render the video → preview in Discord
                                            │    intro → rounds (clue + countdown → reveal) → outro
                                            │    music: your library, or synthesised
                                            └─ at the slot (12:00 Europe/London by default):
                                                 post to each platform in PLATFORMS
                                                 (YouTube, Instagram) → result in Discord
                                                 → delete the video file
```

Claude only runs once a week; the server's own scheduler does the daily rendering and posting,
and only ever keeps the next video or two on disk. Trending
sounds can't be added through any platform's API, so the music is baked into the video: upload
your own royalty-free tracks (`PUT /music/{name}`), or let the bot synthesise a game-show loop
(different for every video, no licensing).

## Look

A Saturday-night TV quiz set: flat stage colours with a slowly turning sunburst, a frame of
chasing marquee bulbs, sign-painted headings (Bungee) with hard ink drop shadows, clue text in
condensed Bricolage Grotesque on tilted paper cue cards, a split-flap countdown over a strip of
bulbs that go out each second, and an answer podium with confetti. Palettes (studio colourways):
`teatime`, `primetime`, `jackpot`, `bingo`, `pitch`.

## Run locally

```bash
pip install -r requirements.txt          # also needs ffmpeg and fonts-noto-color-emoji
python render_cli.py examples/sample_quiz.json out/sample.mp4            # synth music
python render_cli.py examples/sample_quiz.json out/sample.mp4 ./music    # random track from ./music

API_TOKEN=dev DATA_DIR=./data uvicorn app.main:app --reload
curl -X POST localhost:8000/jobs?dry_run=true -H 'Authorization: Bearer dev' \
     -H 'content-type: application/json' -d @examples/sample_quiz.json
```

## Quiz spec

See `app/spec.py` (or `GET /schema`). A spec has a `title` (intro hook), 3-5 `rounds` and an
`outro`. Round types:

| type | clue | reveal |
|---|---|---|
| `emoji` | 2-7 emojis pop in on paper plates ("Guess the movie") | answer podium |
| `bad_description` | a badly described plot on a cue card | answer podium |
| `true_false` | statement with REAL / FAKE buttons | right button lights up, wrong one struck out, explanation |
| `choice` | question + 3-4 options | correct option lights up + note |
| `odd_one_out` | 2×2 grid of items | odd one lights up + reason |
| `unscramble` | shuffled letter tiles | tiles hop into place |

Each round has `think` (countdown seconds, default 5) and `reveal` (default 2.6).

Engagement options:
- `intro`: `card` (2.8 s title card), `quick` (1.2 s) or `banner` (no card; the title rides a banner over round 1).
- **Cliffhanger** (`"cliffhanger": true` on the last round): the video asks viewers to comment their answer
  instead of revealing it. Shortly before the next quiz is rendered, the server reads that post's Instagram
  and YouTube comments, judges them (typos forgiven; `accept` lists other correct forms), and the next
  video shows the answer plus a shout-out to the first 5 correct commenters. Once it's posted, each of
  them gets a reply under their comment pointing at it (a link on YouTube; Instagram comments can't
  carry clickable links). Needs the comments permissions (reconnect from the dashboard).
- **Viewer-picked themes:** `ask_theme` makes the outro ask viewers to comment a theme for next week;
  `GET /themes/suggestions` groups and ranks what they suggested. Monday's batch picks one and sets
  `picked_by` on that quiz: the video shows their comment as a comment card ("@name picked this theme")
  and the viewer gets a reply under
  their suggestion once it posts.
- **Next-quiz links** (every post, `NEXT_LINK_COMMENTS=true`): once a quiz is posted, the bot comments on the
  previous post pointing at it ("Next quiz is up", or "Answer revealed" under a cliffhanger), so every
  comment section leads to the next video.
- `voice`: a game-show host voice-over (ElevenLabs): reads the title, calls each round, announces each
  answer, asks for comments on a cliffhanger and reads yesterday's answer and shout-outs. The music ducks
  under it. Needs `ELEVENLABS_API_KEY`; each line is cached in `/data/voice`. If ElevenLabs fails, the video
  goes out without it.
- **Instagram extras** (switched on in env): a "New quiz out now" story after each Reel
  (`INSTAGRAM_STORIES`), and a weekly carousel of the week's most-viewed quiz, clue then answer on
  alternate slides (`INSTAGRAM_CAROUSELS`). Both are still images made from the quiz, so they cost
  no rendering time. The API can't add stickers or links to stories.
- **Loop ending** (every video): the outro clears back to the empty stage the video opens on, so an
  autoplay replay runs on without a visible jump.
- `ask_comment` (per round): a "Comment your guess!" sticker on that round's countdown; `pause_hint`: a
  "Pause to answer" sticker. Wrap a word in
`*asterisks*` in the title, outro, descriptions and statements to highlight it. `music`: `auto`
(library, else synth), `synth`, `none`, or a library file name.

## API

All endpoints except `/health`, `/media/*`, `/login` and the OAuth callbacks need
`Authorization: Bearer $API_TOKEN` (or `?token=` for browser use). In a browser you can instead
sign in at `/login` with the connected Instagram or YouTube account. That sign-in can read
everything, refresh the numbers, and move, edit or cancel single bookings from the dashboard's
Schedule tab, and retry a failed post; booking a batch and posting new quizzes still need the token.

| Endpoint | |
|---|---|
| `GET /schedule?days=` | The next posting slots: what's booked, `free_dates` |
| `POST /schedule` | Book a batch: `{"items": [{"date": "YYYY-MM-DD", "time": "HH:MM", "spec": {...}}], "replace": false}`. All-or-nothing; 409 lists every problem (taken slot, repeated answer). `date` may be omitted to take the next free day; `time` defaults to `POST_TIME` (give one for extra posts on a day). |
| `PATCH /schedule/job/{job_id}` | Move a booked quiz (`date`, `time`) and/or replace its content (`spec`), with the same checks as booking; a content change re-renders it |
| `DELETE /schedule/{date}?time=HH:MM` | Cancel a booked quiz (`time` needed when the day has more than one) |
| `POST /jobs?dry_run=&force=&only=` | Render and post one quiz now (`only=youtube` etc. limits it to some platforms). 409 if any answer was used in the last `REPEAT_DAYS` or is booked (unless `force`). |
| `GET /jobs/{id}` | Job status, video URL, publish results |
| `GET /jobs/failed?days=14`, `POST /jobs/{id}/retry` | Recent posts that missed a platform, with each error; retry posts again to just those platforms (the video is made again if it was deleted). The dashboard shows them with a Retry button. |
| `GET /history` | Posted quizzes (theme, palette, round types, answers, platforms) |
| `GET /login`, `GET /logout` | Sign in with the Instagram or YouTube account the bot posts to (30-day cookie; read-only plus the dashboard's refresh) |
| `GET /dashboard` | Performance dashboard: totals, views per post, compare posts by any label, the latest weekly review (signed in, or `?token=…`) |
| `GET /metrics`, `POST /metrics/refresh` | Every posted quiz with its labels and per-platform numbers (latest + 1h/24h/7d snapshots); refresh fetches now |
| `POST /insights`, `GET /insights/latest` | The weekly review's findings; the Monday batch reads the latest |
| `GET /schema` | Spec JSON schema |
| `POST /instagram/story/{job_id}` | Post the "new quiz out now" story for a quiz already on Instagram |
| `POST /instagram/carousel?job_id=&dry_run=true` | Make the swipe-to-play carousel slides (default: the week's most viewed); `dry_run=false` posts it |
| `GET /themes/suggestions?days=8` | Themes viewers commented on recent `ask_theme` posts, grouped and ranked |
| `GET /instagram/media/{id}` | Link, account and time of a published Reel |
| `GET /status` | Platforms + tokens + connected accounts, posting time, schedule, music library, recent jobs |
| `GET /music`, `PUT /music/{name}`, `DELETE /music/{name}` | Music library (raw file body, max 40 MB) |
| `GET /oauth/{youtube,instagram}/start?token=…` | One-time account connection |
| `GET /media/{file}` | Rendered videos (unguessable names; Instagram fetches from here) |

## Configuration

See [docs/SETUP.md](docs/SETUP.md). The key switches: `PLATFORMS=youtube,instagram` (either or
both), `POST_TIME=12:00`, `TIMEZONE=Europe/London`, `PUBLISH_ENABLED`.

Fonts: Bungee and Bricolage Grotesque (SIL Open Font License, in `assets/fonts`).
