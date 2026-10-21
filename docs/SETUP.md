# Setup

Order: deploy the app with publishing off → Discord → TikTok → Instagram → switch publishing on
→ create the daily Routine. You can stop after any step; everything before it keeps working.

`APP_URL` below is the app's public URL, e.g. `https://techshorts-app.apysn4.easypanel.host`.

## 1. Easypanel app

- Source: GitHub `Stayingfalse/tech-shorts-bot`, branch `main`, build: Dockerfile.
- Port 8000, domain → `APP_URL` (HTTPS).
- Volume: mount `/data` (videos, history, tokens).
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
| `INSTAGRAM_MODE` | `notify` (manual post with trending sound, default) or `auto` |
| `RENDER_WORKERS` | default `4` |
| `KEEP_VIDEOS_DAYS` | default `14` |

Check: `curl APP_URL/health` → `{"ok":true}`, and `APP_URL/status?token=API_TOKEN` in a browser.

## 2. Discord notifications

Discord channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy URL →
`DISCORD_WEBHOOK_URL`. Each day you get the video attached, the caption ready to copy, the suggested
sound and the sources.

## 3. TikTok (upload to drafts)

1. https://developers.tiktok.com → log in → **Manage apps → Connect an app**. Fill in name, icon,
   category, description. It asks for Terms of Service and Privacy Policy URLs; simple pages on
   cezz.co.uk are fine.
2. Products: add **Login Kit** and **Content Posting API**. Scopes: `user.info.basic`,
   `video.upload` only. Do **not** enable Direct Post / `video.publish` (that needs the full audit
   and isn't needed for drafts).
3. Login Kit → Redirect URI: `APP_URL/oauth/tiktok/callback`.
4. Copy **Client key / Client secret** → `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET`, redeploy.
5. While the app is in development/sandbox, add your TikTok account as a **target user / tester**.
   If TikTok requires review before your own account can authorise, submit it: the demo video
   is a screen recording of you visiting `/oauth/tiktok/start`, approving, and the draft
   appearing in TikTok's inbox.
6. In a browser: `APP_URL/oauth/tiktok/start?token=API_TOKEN` → approve → "TikTok connected".

The app refreshes the token twice a day; the refresh token lasts a year from last use.
Daily: open TikTok → inbox notification → edit the draft → **Add sound** → pick the suggested
trending sound → turn **Original sound** down if needed → post.

## 4. Instagram

Default mode is `notify`: you post from Discord manually so you can add the trending sound. You only
need the API if you want `INSTAGRAM_MODE=auto` (built-in audio, fully hands-off).

To connect anyway:
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

## 5. Turn on publishing

Set `PUBLISH_ENABLED=true`, redeploy, then test:
```bash
curl -X POST "APP_URL/jobs?force=true" -H "Authorization: Bearer $API_TOKEN" \
     -H 'content-type: application/json' -d @examples/sample_spec.json
```
(Delete the sample draft afterwards.)

## 6. Daily research Routine (Claude Code)

1. In the Claude Code cloud environment's settings (environment menu in the session's title
   bar → Edit), add `SHORTS_API_TOKEN` = the `API_TOKEN` value (or a network secret for the app's
   host that sends `Authorization: Bearer …`). Make sure the network policy allows the app's host.
2. Claude creates the Routine with the prompt in [ROUTINE_PROMPT.md](ROUTINE_PROMPT.md),
   e.g. daily at 07:41 Europe/London, fresh session each run.
