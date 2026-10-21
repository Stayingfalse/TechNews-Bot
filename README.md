# tech-shorts-bot

Daily tech-news shorts, made entirely in code (no generative AI video) and sent to TikTok and
Instagram Reels.

```
Claude Code Routine (daily)          Easypanel app (this repo)
  research + verify a story   ──►  POST /jobs (story spec JSON)
                                     │
                                     ├─ render 1080×1920 video (Pillow + numpy → ffmpeg)
                                     ├─ TikTok: upload to drafts (Content Posting API)
                                     ├─ Instagram: notify for manual post (or auto-publish)
                                     └─ Discord: video + caption + suggested trending sound
```

Trending sounds can't be added through either platform's API (they're licensed for in-app use
only), so the flow is: the video lands in your TikTok drafts and in Discord, you open each app,
add the suggested trending sound and post. About a minute a day.

## Run locally

```bash
pip install -r requirements.txt          # also needs ffmpeg
python render_cli.py examples/sample_spec.json out/sample.mp4

API_TOKEN=dev DATA_DIR=./data uvicorn app.main:app --reload
curl -X POST localhost:8000/jobs -H 'Authorization: Bearer dev' \
     -H 'content-type: application/json' -d @examples/sample_spec.json
```

## Story spec

See `app/spec.py` (or `GET /schema`). Beat types: `hook`, `title`, `stat`, `spec_list`,
`compare`, `price`, `cta`. Palettes: `neon_dark`, `sunset`, `mint`, `mono`, `electric`.
Wrap a word in `*asterisks*` in hook/cta text to highlight it.

## API

All endpoints except `/health`, `/media/*` and the OAuth callbacks need
`Authorization: Bearer $API_TOKEN` (or `?token=` for browser use).

| Endpoint | |
|---|---|
| `POST /jobs?dry_run=&force=` | Queue a spec. `dry_run` renders + notifies without uploading or recording history. 409 if the `topic_key` was covered in the last 30 days (unless `force`). |
| `GET /jobs/{id}` | Job status, video URL, publish results |
| `GET /history` | Previously covered stories |
| `GET /schema` | Spec JSON schema |
| `GET /status` | Config + token expiry + recent jobs |
| `GET /oauth/{tiktok,instagram}/start?token=…` | One-time account connection |
| `GET /media/{file}` | Rendered videos (unguessable names; Instagram fetches from here) |

## Configuration

See [docs/SETUP.md](docs/SETUP.md).
