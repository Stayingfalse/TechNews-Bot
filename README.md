# TechNews-Bot (now: daily quiz shorts)

A daily quiz short (guess the movie from emojis, badly described films, real-or-fake, odd one
out, unscramble, multiple choice), rendered entirely in code with its own music and posted to
TikTok, YouTube Shorts and Instagram Reels with no manual steps.

```
Claude Code Routine (Mondays 19:05)        Easypanel app (this repo)
  plan 7 themes, write 7 quizzes,    ──►  POST /schedule (7 dated quiz specs)
  verify the facts                          │  checked + stored (no video yet) → week summary in Discord
                                            ├─ 45 min before each slot: render the video → preview in Discord
                                            │    intro → rounds (clue + countdown → reveal) → outro
                                            │    music: your library, or synthesised
                                            └─ at the slot (12:00 Europe/London by default):
                                                 post to each platform in PLATFORMS
                                                 (TikTok, YouTube, Instagram) → result in Discord
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

Each round has `think` (countdown seconds, default 5) and `reveal` (default 2.6). Wrap a word in
`*asterisks*` in the title, outro, descriptions and statements to highlight it. `music`: `auto`
(library, else synth), `synth`, `none`, or a library file name.

## API

All endpoints except `/health`, `/media/*` and the OAuth callbacks need
`Authorization: Bearer $API_TOKEN` (or `?token=` for browser use).

| Endpoint | |
|---|---|
| `GET /schedule?days=` | The next posting slots: what's booked, `free_dates` |
| `POST /schedule` | Book a batch: `{"items": [{"date": "YYYY-MM-DD", "time": "HH:MM", "spec": {...}}], "replace": false}`. All-or-nothing; 409 lists every problem (taken slot, repeated answer). `date` may be omitted to take the next free day; `time` defaults to `POST_TIME` (give one for extra posts on a day). |
| `DELETE /schedule/{date}?time=HH:MM` | Cancel a booked quiz (`time` needed when the day has more than one) |
| `POST /jobs?dry_run=&force=&only=` | Render and post one quiz now (`only=youtube` etc. limits it to some platforms). 409 if any answer was used in the last `REPEAT_DAYS` or is booked (unless `force`). |
| `GET /jobs/{id}` | Job status, video URL, publish results |
| `GET /history` | Posted quizzes (theme, palette, round types, answers, platforms) |
| `GET /schema` | Spec JSON schema |
| `GET /instagram/media/{id}` | Link, account and time of a published Reel |
| `GET /status` | Platforms + tokens + connected accounts, posting time, schedule, music library, recent jobs |
| `GET /music`, `PUT /music/{name}`, `DELETE /music/{name}` | Music library (raw file body, max 40 MB) |
| `GET /oauth/{tiktok,youtube,instagram}/start?token=…` | One-time account connection |
| `GET /media/{file}` | Rendered videos (unguessable names; Instagram fetches from here) |

## Configuration

See [docs/SETUP.md](docs/SETUP.md). The key switches: `PLATFORMS=tiktok,youtube,instagram` (any
subset), `POST_TIME=12:00`, `TIMEZONE=Europe/London`, `PUBLISH_ENABLED`.

Fonts: Bungee and Bricolage Grotesque (SIL Open Font License, in `assets/fonts`).
