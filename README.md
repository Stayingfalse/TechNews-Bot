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
  under it. `voice_name` picks the host (alex, liam, althea, milly), which the review compares. Needs `ELEVENLABS_API_KEY`; each line is cached in `/data/voice`. If ElevenLabs fails, the video
  goes out without it.
- **Instagram extras** (switched on in env): a "New quiz out now" story after each Reel
  (`INSTAGRAM_STORIES`), and every Monday at 20:00 a carousel of the week's most-viewed quiz, clue then answer on
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
| `POST /adventure/episode0?voice=&publish=&at=&series=` | Adventure channel: render an Episode 0 part (body `{"part": 1}`, or with `recap`/`fear`/`hero` for parts 2-4), voiced unless `voice=false`, to Discord. `publish=true` posts it now to the adventure Instagram (options as the first comment). `at=09:00` books it: votes on the previous part counted and the video rendered an hour before, posted at that time, and (with `series`, the default) the next part booked for the same time tomorrow, built from this one's votes. |
| `GET /adventure/jobs`, `GET /adventure/jobs/{id}`, `DELETE /adventure/jobs/{id}` | Adventure jobs: status, votes, video, post; cancel a booked or ready one |
| `GET /adventure/jobs/{id}/votes` | The A/B/C votes so far on a posted part (one per account; nothing saved) |
| `GET /adventure/credits` | Narrator credits spent this month against `ADVENTURE_VOICE_BUDGET` (default 7200) |

## Privacy (GDPR)

Public pages (no sign-in) covering every channel, now and later (the account list is built from the channel registry), written in `app/legal/*.html` and served by `app/legal.py`:

| URL | What |
|---|---|
| `/` | Home page: every account (from the channel registry) with all its public videos, newest first, and links to the legal pages |
| `/privacy` | Privacy policy (UK/EU GDPR): what is read from comments, why (legitimate interests, with the balancing test), who else handles it (Meta, Google, the host, ElevenLabs, Anthropic, Discord), transfers, retention, security, rights, YouTube API Services and Instagram notices; embeds both channels' explainer videos |
| `/terms` | Terms of service |
| `/privacy/request` | Self-service form: opt out, or delete and opt out; applied at once, with a confirmation code |
| `/privacy/status/{code}` | Where a request stands (also `/privacy/status?code=`) |
| `POST /privacy/meta/deletion` | Meta's data deletion callback (`signed_request`, verified with the app secret); answers `{url, confirmation_code}` |
| `POST /privacy/meta/deauthorize` | Meta's deauthorize callback |
| `/data-deletion` | Redirects to the policy's deletion section |

Viewers can also opt out by commenting `#optout` (or "opt out") under any post on either channel: the
maintenance loop scans the last 14 days of posts twice a day. There is one opt-out list for both channels:
the quiz never reads an opted-out viewer, and the Dungeon crawl doesn't count their votes. Every request is logged for 365 days
(`privacy_requests.json`) and posted to Discord; taking down a video that shows a name stays manual.
Owner-only: `POST /privacy/optout` and `POST /privacy/erase` (token). Viewer names leave post records
automatically after 90 days. The videos in `assets/explainer/` come from `render_explainer.py` (the quiz,
42 s) and `render_explainer_adventure.py` (the Dungeon crawl's votes, 36 s; needs `npm ci` in `adventure/`).

## Tests

`pip install -r requirements-dev.txt && python -m pytest` runs the suite (about 45 s; it renders one
short video, so it needs ffmpeg and the emoji font, as in the Dockerfile). It covers cliffhanger
judging, shout-outs and replies, next-quiz links, viewer themes, the scheduler and deploy safety
(lease, restart recovery, stuck-job watchdog), per-channel tokens, the voice-over fallback and mix,
the API's booking checks, every scene and opening, the story/carousel images and the profile picture
rotation. Nothing talks to a real platform. GitHub Actions runs it on every push and pull request
(`.github/workflows/tests.yml`); deploy only when it's green.

## Profile pictures

`python render_avatar.py assets/avatars` draws four profile pictures in the videos' style (question
mark, 5/5 podium, split-flap timer, emoji round), one per palette, sized for the circle crop, and a
matching YouTube banner for each (`banner-*.jpg`, 2560×1440, text inside the strip every device shows).
Every `AVATAR_EVERY_WEEKS` weeks (default 3), on Monday from 10:00, the bot puts up the next banner on
YouTube itself and sends the matching picture to Discord to upload: neither Instagram's nor YouTube's
API can change a profile picture. `POST /avatars/banner` puts up the banner for the current picture.
Add more by dropping `avatar-*.png` files into `/data/avatars`. `GET /avatars` shows the rotation,
`POST /avatars/next` hands over the next one now.

## Adventure channel

A second channel, a daily choose-your-adventure dungeon crawl, is being built: plan in
[docs/ADVENTURE_PLAN.md](docs/ADVENTURE_PLAN.md), renderer in [adventure/](adventure/) (Node,
installed into the image by the Dockerfile). For now the server can render its Episode 0 videos as
Discord previews (`POST /adventure/episode0`). Settings: `ADVENTURE_VOICE_ID` (default Obsidian),
`ADVENTURE_VOICE_MODEL` (`eleven_v3`), `ADVENTURE_VOICE_BUDGET` (characters a month, default 7200).

## Racing channel (Sixel Speedway)

A third channel: a daily ~40 s car race that viewers bet on with play money in the comments. A
different format each day (oval, rally, Grand Prix, figure 8, drag, endurance with pit stops) on a
newly generated track, with cars that suit some formats more than others. It runs on the server
alone, with no AI step and no routine. Plan and rules: [docs/RACING_PLAN.md](docs/RACING_PLAN.md).

```
every 15 min   read new comments on the open race's post → reply to each bet (paced queue)
18:00          close race N → run it from its sealed seed → settle bets → (Sun: bonus + table)
               → open race N+1 (new seed, seal, odds) → render → Discord preview
19:00          post the Reel + an example bet as the first comment → book tomorrow
```

- **Launch**: connect the account (`/oauth/instagram/start?channel=racing`), then
  `POST /racing/start` (optional `at=19:00`). Race 1 opens and the launch video (how to play +
  race 1's card) posts at the next 19:00; from then on it books itself every day.
- **Bets pages** on `RACING_DOMAIN` (default `race.onlydan.uk`, pointed at this app in Easypanel):
  the race card, league table, a page per player and per race with the seal check. That domain
  serves nothing else, and the racing pages exist on no other domain.
- **Themes** (`app/render/racing/themes/`): each is one look for the whole video. `RACING_THEMES=pitwall,other`
  makes videos take turns (an A/B test); `GET /racing/metrics` compares them. `POST /racing/preview?theme=&format=`
  sends a sample video (with a throwaway seed) to Discord.
- **Endpoints** (token): `POST /racing/start`, `GET /racing/state`, `GET /racing/races/{n}`,
  `GET /racing/jobs[/{id}]`, `POST /racing/jobs/{id}/retry`, `GET /racing/players?q=`,
  `GET /racing/metrics`, `POST /racing/preview`.
- **Settings**: `RACING_HANDLE`, `RACING_POST_TIME` (19:00), `RACING_CLOSE_MINUTES` (60),
  `RACING_PLATFORMS` (instagram), `RACING_DOMAIN`, `RACING_THEMES` (pitwall), `RACING_POLL_MINUTES` (15),
  `RACING_REPLY_GAP` (20 s), `RACING_REPLY_PER_HOUR` (60), `RACING_REPLIES` (on), `RACING_LAUNCH_WEEKS` (4),
  `RACING_CALENDAR` (`mon=oval,tue=rally,wed=gp,thu=figure8,fri=drag,sat=endurance,sun=gp`).

Fonts for the race videos: Inter (OFL) and JetBrains Mono, in `assets/fonts/racing`.

## Channels

Built for one channel today (the quiz account) with the seams for several: jobs record their channel,
run as it, and OAuth tokens are stored per channel. The plan is in [docs/MULTI_ACCOUNT.md](docs/MULTI_ACCOUNT.md).

## Configuration

See [docs/SETUP.md](docs/SETUP.md). The key switches: `PLATFORMS=youtube,instagram` (either or
both), `POST_TIME=12:00`, `TIMEZONE=Europe/London`, `PUBLISH_ENABLED`.

Fonts: Bungee and Bricolage Grotesque (SIL Open Font License, in `assets/fonts`).
