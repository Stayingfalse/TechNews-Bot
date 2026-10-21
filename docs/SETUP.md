# Setup

Order: deploy the app with publishing off → Discord → music → TikTok → Instagram → switch
publishing on → point the daily Routine at the quiz prompt. You can stop after any step; everything before it keeps working.

`APP_URL` below is the app's public URL, `https://mcwales-techshorts.apysn4.easypanel.host`.

## 1. Easypanel app

- Service `mcwales/techshorts`. Source: GitHub `Stayingfalse/TechNews-Bot`, branch `main`, build: Dockerfile.
- Port 8000, domain → `APP_URL` (HTTPS).
- Volume: mount `/data` (videos, history, tokens, music library).
- Resources: rendering uses up to `RENDER_WORKERS` CPU cores for ~40–90 s a day.

Environment variables:

| Variable | Value |
|---|---|
| `API_TOKEN` | long random string (`openssl rand -hex 32`); the routine uses it too |
| `PUBLIC_BASE_URL` | `APP_URL` |
| `BRAND_HANDLE` | e.g. `@yourhandle` (shown top-left; blank to hide) |
| `PUBLISH_ENABLED` | `false` until TikTok/Instagram are connected and tested |
| `DISCORD_WEBHOOK_URL` | see step 2 |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` | step 3 |
| `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET` | step 4 |
| `INSTAGRAM_MODE` | `auto` (publish via API, default) or `notify` (Discord only, post by hand) |
| `TIKTOK_MODE` | `draft` (inbox, you tap post; default) or `direct` (posts itself; see step 4) |
| `TIKTOK_PRIVACY` | for `direct`: `PUBLIC_TO_EVERYONE` (default), `MUTUAL_FOLLOW_FRIENDS`, `SELF_ONLY` |
| `REPEAT_DAYS` | default `365`: an answer can't be reused within this many days |
| `MUSIC_DIR` | default `/data/music` |
| `MUSIC_GAIN` | default `0.32`: library music level under the sound effects |
| `LOUDNESS_LUFS` | default `-15`: loudness of the final mix |
| `RENDER_WORKERS` | default `4` |
| `KEEP_VIDEOS_DAYS` | default `14` |

Check: `curl APP_URL/health` → `{"ok":true}`, and `APP_URL/status?token=API_TOKEN` in a browser.

## 2. Discord notifications

Discord channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy URL →
`DISCORD_WEBHOOK_URL`. Each day you get the video (attached when under 10 MB, otherwise a link),
the caption and the answers.

## 3. Music

With an empty library every video gets a synthesised game-show loop (different tempo, key and
chords per video), so this step is optional. To use your own tracks, upload them:

```bash
curl -T upbeat-1.mp3 -H "Authorization: Bearer $API_TOKEN" APP_URL/music/upbeat-1.mp3
curl -H "Authorization: Bearer $API_TOKEN" APP_URL/music          # list
```

Each video picks one at random (or the spec names one), loops it if short, normalises its
loudness and fades it out. Only upload music you're allowed to use in social videos: your own,
or royalty-free with a licence that covers TikTok/Instagram (e.g. YouTube Audio Library tracks
marked "no attribution required", Pixabay Music, or a paid library like Epidemic Sound or
Artlist). Platforms can mute or remove videos with unlicensed commercial music.

## 4. TikTok

1. https://developers.tiktok.com → log in → **Manage apps → Connect an app**. Fill in name, icon,
   category, description. It asks for Terms of Service and Privacy Policy URLs; simple pages on
   cezz.co.uk are fine.
2. Products: add **Login Kit** and **Content Posting API**. Scopes: `user.info.basic`,
   `video.upload`, plus `video.publish` with **Direct Post** enabled if you want `TIKTOK_MODE=direct`.
3. Login Kit → Redirect URI: `APP_URL/oauth/tiktok/callback`.
4. Copy **Client key / Client secret** → `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET`, redeploy.
5. While the app is in development/sandbox, add your TikTok account as a **target user / tester**.
   If TikTok requires review before your own account can authorise, submit it: the demo video
   is a screen recording of you visiting `/oauth/tiktok/start`, approving, and the draft
   appearing in TikTok's inbox.
6. In a browser: `APP_URL/oauth/tiktok/start?token=API_TOKEN` → approve → "TikTok connected".

The app refreshes the token twice a day; the refresh token lasts a year from last use.

**Fully automatic posting (`TIKTOK_MODE=direct`)**: TikTok only allows public direct posts from
apps that have passed its Content Posting API audit. Until then, direct posts are forced to
private (`SELF_ONLY`). So: run with `TIKTOK_MODE=draft` (one tap a day in the TikTok inbox), apply
for the audit in the developer portal (Content Posting API → Direct Post → request audit; the
demo video is a screen recording of the app posting a quiz), then switch to `direct` and
reconnect via `/oauth/tiktok/start` so the token includes `video.publish`.

## 5. Instagram

Default mode is `auto`: the Reel is published through the API with the built-in music.

1. Instagram app → Settings → Account type → switch to **Professional** (Creator or Business).
2. https://developers.facebook.com → **Create app** → use case "Manage messaging & content on
   Instagram" → it creates an app with **Instagram API with Instagram Login**.
3. Instagram → API setup with Instagram login → add your account as an **Instagram tester**
   (accept the invite in Instagram: Settings → Website permissions → Apps and websites → Tester invites).
4. Business login settings → OAuth redirect URI: `APP_URL/oauth/instagram/callback`.
5. Copy **Instagram app ID / secret** → `INSTAGRAM_APP_ID` / `INSTAGRAM_APP_SECRET`, redeploy.
6. `APP_URL/oauth/instagram/start?token=API_TOKEN` → approve.

The app stays in development mode (posting to your own account doesn't need Meta App Review).
Long-lived tokens last 60 days and are refreshed automatically.

## 6. Turn on publishing

Set `PUBLISH_ENABLED=true`, redeploy, then test:
```bash
curl -X POST "APP_URL/jobs?force=true" -H "Authorization: Bearer $API_TOKEN" \
     -H 'content-type: application/json' -d @examples/sample_quiz.json
```
(Delete the sample post afterwards.)

## 7. Daily quiz Routine (Claude Code)

1. In the Claude Code cloud environment's settings (environment menu in the session's title
   bar → Edit), add `SHORTS_API_TOKEN` = the `API_TOKEN` value (or a network secret for the app's
   host that sends `Authorization: Bearer …`). Make sure the network policy allows the app's host.
2. Once this version is deployed, update the existing Routine ("TechNews-Bot daily story") to the
   prompt in [ROUTINE_PROMPT.md](ROUTINE_PROMPT.md), e.g. daily at 07:41 Europe/London, fresh
   session each run. Don't switch it before deploying: the old app rejects quiz specs.
