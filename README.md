# TechNews-Bot (now: daily quiz shorts)

A daily quiz short (guess the movie from emojis, badly described films, real-or-fake, odd one
out, unscramble, multiple choice), rendered entirely in code with its own music and posted to
TikTok and Instagram Reels with no manual steps.

```
Claude Code Routine (daily)          Easypanel app (this repo)
  pick a theme, write 3-5 rounds,  ──►  POST /jobs (quiz spec JSON)
  verify the facts                     │
                                       ├─ render 1080×1920 video (Pillow + numpy → ffmpeg)
                                       │    intro → rounds (clue + countdown → reveal) → outro
                                       ├─ music: a track from your library, or synthesised
                                       ├─ TikTok: direct post (or drafts) via Content Posting API
                                       ├─ Instagram: publish the Reel via the Graph API
                                       └─ Discord: video + caption + answers
```

Trending sounds can't be added through either platform's API, so the music is baked into the
video: upload your own royalty-free tracks to the library (`PUT /music/{name}`), or let the bot
synthesise a game-show loop (unique per video, no licensing).

## Run locally

```bash
pip install -r requirements.txt          # also needs ffmpeg and fonts-noto-color-emoji
python render_cli.py examples/sample_quiz.json out/sample.mp4            # synth music
python render_cli.py examples/sample_quiz.json out/sample.mp4 ./music    # random track from ./music

API_TOKEN=dev DATA_DIR=./data uvicorn app.main:app --reload
curl -X POST localhost:8000/jobs -H 'Authorization: Bearer dev' \
     -H 'content-type: application/json' -d @examples/sample_quiz.json
```

## Quiz spec

See `app/spec.py` (or `GET /schema`). A spec has a `title` (intro hook), 3-5 `rounds` and an
`outro`. Round types:

| type | clue | reveal |
|---|---|---|
| `emoji` | 2-7 emojis pop in ("Guess the movie") | answer card |
| `bad_description` | a badly described plot | answer card |
| `true_false` | statement with REAL / FAKE buttons | right button lights up + explanation |
| `choice` | question + 3-4 options | correct option lights up + note |
| `odd_one_out` | 2×2 grid of items | odd one lights up + reason |
| `unscramble` | shuffled letter tiles | tiles fly into place |

Each round has `think` (countdown seconds, default 5) and `reveal` (default 2.6). Palettes:
`candy`, `arcade`, `neon_dark`, `sunset`, `mint`, `mono`, `electric`. Wrap a word in
`*asterisks*` in the title, outro, descriptions and statements to highlight it.
`music`: `auto` (library, else synth), `synth`, `none`, or a library file name.

## API

All endpoints except `/health`, `/media/*` and the OAuth callbacks need
`Authorization: Bearer $API_TOKEN` (or `?token=` for browser use).

| Endpoint | |
|---|---|
| `POST /jobs?dry_run=&force=` | Queue a quiz. `dry_run` renders + notifies without uploading or recording history. 409 if any answer was used in the last `REPEAT_DAYS` (unless `force`). |
| `GET /jobs/{id}` | Job status, video URL, publish results |
| `GET /history` | Previous quizzes (theme, palette, round types, answers) |
| `GET /schema` | Spec JSON schema |
| `GET /status` | Config + token expiry + music library + recent jobs |
| `GET /music`, `PUT /music/{name}`, `DELETE /music/{name}` | Music library (raw file body, max 40 MB) |
| `GET /oauth/{tiktok,instagram}/start?token=…` | One-time account connection |
| `GET /media/{file}` | Rendered videos (unguessable names; Instagram fetches from here) |

## Configuration

See [docs/SETUP.md](docs/SETUP.md).
