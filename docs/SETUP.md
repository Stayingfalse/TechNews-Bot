# Setup

Order: deploy the app with publishing off → Discord → music → the platforms you want (YouTube,
Instagram) → switch publishing on → switch the Routine to the weekly quiz prompt. You can stop after any step; everything before it keeps working.

`APP_URL` below is the app's public URL, `https://quiz.cezz.co.uk`.

## 1. Easypanel app

- Service `mcwales/techshorts`. Source: GitHub `Stayingfalse/TechNews-Bot`, branch `main`, build: Dockerfile.
- Port 8000, domain → `APP_URL` (HTTPS).
- Volume: mount `/data` (videos, history, tokens, music library).
- Resources: each video is rendered 45 minutes before it posts (2–4 minutes on up to
  `RENDER_WORKERS` CPU cores) and deleted once every platform has it, so disk use stays at one or
  two videos (~15 MB each).
- Keep the service running all the time: the scheduler inside it posts each day. If it's down at
  posting time it catches up when it comes back (up to 6 hours late; after that the day is
  skipped and Discord says so).

Environment variables:

| Variable | Value |
|---|---|
| `API_TOKEN` | long random string (`openssl rand -hex 32`); the routine uses it too |
| `PUBLIC_BASE_URL` | `APP_URL` |
| `BRAND_HANDLE` | e.g. `@yourhandle` (shown top-left; blank to hide) |
| `PUBLISH_ENABLED` | `false` until the platforms are connected and tested |
| `PLATFORMS` | where to post, comma-separated: `youtube`, `instagram` or both (default both) |
| `TIMEZONE` | default `Europe/London` |
| `POST_TIME` | default `12:00`: daily posting time in `TIMEZONE` |
| `DISCORD_WEBHOOK_URL` | see step 2 |
| `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` | step 4 |
| `YOUTUBE_PRIVACY` | `public` (default), `unlisted` or `private` |
| `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET` | step 5 |
| `NEXT_LINK_COMMENTS` | default `true`: after each post, comment on the previous one pointing at it, and reply under correct cliffhanger answers and picked theme suggestions (needs the comments permissions in step 5b) |
| `INSTAGRAM_STORIES` | default `false`: after each Reel, post a "New quiz out now" story of its title card |
| `INSTAGRAM_CAROUSELS` | default `true`: once a week, post the week's most-viewed quiz again as a swipe-to-play carousel (clue, then answer) |
| `CAROUSEL_DAY`, `CAROUSEL_TIME` | when the weekly carousel goes out: default `mon` and `20:00` (local), after the week has run and the Monday batch has booked the next |
| `AVATAR_EVERY_WEEKS` | default `3`: how often Discord gets the next profile picture to upload (0 = off) |
| `HEALTHCHECKS_API_KEY` | optional: a healthchecks.io project API key (read-write). On start the server creates three checks there itself, tagged `quizbot`: **heartbeat** (pings every 5 min; alerts after 15 min of silence), **daily-post** (alerts if nothing has posted by 45 min after `POST_TIME`, or at once when a post fails everywhere), **weekly-batch** (alerts if Monday's routine hasn't booked the next week by 22:00). They alert through the project's integrations (email by default). |
| `ELEVENLABS_API_KEY` | optional: turns on the host voice-over for quizzes with `"voice": true` (ElevenLabs → Developers → API keys; text-to-speech permission is enough) |
| `ELEVENLABS_VOICE_ID` | default `TX3LPaxmHKxFdv7VOQHJ` ("Liam", a built-in energetic voice). For another, copy its ID in ElevenLabs (the voice's ⋯ menu → Copy voice ID). On the free plan only built-in voices work through the API; a refused library voice falls back to Liam |
| `ELEVENLABS_VOICES` | the host voices quizzes pick by `voice_name`, as `name=id,…`; default `alex`, `liam`, `althea` (female, game-show host), `milly` (female, Australian presenter) |
| `ELEVENLABS_MODEL` | default `eleven_v3`; `eleven_v3` and `eleven_v4` read each line in an `[excited]` delivery, `eleven_multilingual_v2` is steadier |
| `REPEAT_DAYS` | default `365`: an answer can't be reused within this many days |
| `MUSIC_DIR` | default `/data/music` |
| `MUSIC_GAIN` | default `0.32`: library music level under the sound effects |
| `LOUDNESS_LUFS` | default `-15`: loudness of the final mix |
| `RENDER_WORKERS` | default `4` |
| `RENDER_LEAD_MINUTES` | default `45`: how long before its slot each video is rendered |
| `KEEP_VIDEOS_DAYS` | default `3`: leftovers (failed posts, dry runs) are deleted after this; posted videos go straight away |

Check: `curl APP_URL/health` → `{"ok":true}`, and `APP_URL/status?token=API_TOKEN` in a browser.

## 2. Discord notifications

Discord channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy URL →
`DISCORD_WEBHOOK_URL`. On Monday evening you get the week's line-up (times, themes, answers);
45 minutes before each post you get its video preview (pull it with
`DELETE APP_URL/schedule/YYYY-MM-DD?time=HH:MM`); at posting time you get the results per
platform with links. Discord also warns if a day has nothing booked
or fewer than two days are left in the schedule.

## 3. Music

With an empty library every video gets a synthesised game-show loop (different tempo, key and
chords per video), so this step is optional. To use your own tracks, upload them:

```bash
curl -T upbeat-1.mp3 -H "Authorization: Bearer $API_TOKEN" APP_URL/music/upbeat-1.mp3
curl -H "Authorization: Bearer $API_TOKEN" APP_URL/music          # list
```

Each video picks one at random (or the spec names one), loops it if short, normalises its
loudness and fades it out. Only upload music you're allowed to use in social videos: your own,
or royalty-free with a licence that covers Instagram and YouTube (e.g. YouTube Audio Library tracks
marked "no attribution required", Pixabay Music, or a paid library like Epidemic Sound or
Artlist). Platforms can mute or remove videos with unlicensed commercial music.

## 4. YouTube Shorts

Vertical videos under 3 minutes are filed as Shorts automatically.

1. https://console.cloud.google.com → create a project → **APIs & Services → Library** → enable
   **YouTube Data API v3**.
2. **OAuth consent screen**: External, app name, your email; add scope
   `https://www.googleapis.com/auth/youtube.upload`. Then **Publish app** (to "In production").
   Leave it unverified; you'll click through an "unverified app" warning once. Don't leave it in
   "Testing": refresh tokens of testing apps expire after 7 days and posting would stop.
3. **Credentials → Create credentials → OAuth client ID** → Web application → Authorised redirect
   URI: `APP_URL/oauth/youtube/callback`.
4. Copy the client ID / secret → `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET`, redeploy.
5. `APP_URL/oauth/youtube/start?token=API_TOKEN` → pick the channel's Google account → approve.

**Public uploads need YouTube's API audit.** Videos uploaded through a project that hasn't passed
the [YouTube API Services audit](https://support.google.com/youtube/contact/yt_api_form) are
locked to private. Submit the audit form (use case: posting your own channel's videos); until it's
approved, uploads stay private and you can make them public in YouTube Studio. The default quota
(10,000 units a day; an upload costs 1,600) is plenty for one video a day.

## 5. Instagram

The Reel is published through the API with the video's own music.

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

### A second account (the adventure channel, @dungeoncrawlergram)

Same Meta app; nothing to create.

1. Make the account Professional (Creator or Business) in the Instagram app.
2. Meta app → Instagram → API setup with Instagram login → Roles → add the account as an
   **Instagram tester**, and accept the invite in Instagram while signed in to that account
   (Settings → Website permissions → Apps and websites → Tester invites).
3. In a **private window**, sign in to instagram.com as that account, then open
   `APP_URL/oauth/instagram/start?channel=adventure&token=API_TOKEN` and approve. The page names the
   account it connected; the quiz's own account is refused, so the quiz's connection can't be
   overwritten this way. `GET /status` → `channels` shows both.

Never use the plain `/oauth/instagram/start` link (no `?channel=`) for the second account: that one
replaces the quiz's connection.

## 5b. Performance numbers and comments (dashboard, weekly review, cliffhangers)

The bot collects each post's numbers at about 1 hour, 24 hours and 7 days, and refreshes them
every 4 hours for 14 days. See them at `APP_URL/dashboard`: sign in with the Instagram or
YouTube account the bot posts to (YouTube sign-in needs the reconnect below first). Two platforms need
extra permissions for this, granted by reconnecting once:

- **Instagram:** in the Meta app → Instagram → **Permissions and features**, add
  `instagram_business_manage_insights` (views, reach, shares, saves, watch time) and
  `instagram_business_manage_comments` (reading cliffhanger answers, replying to winners, and the "next quiz" comment on each post). Then reconnect at
  `APP_URL/oauth/instagram/start?token=API_TOKEN`. Without it you still get likes and comments.
- **YouTube:** in Google Cloud → **APIs & Services → Library**, enable **YouTube Analytics
  API**. In **Google Auth Platform → Data access**, add the scopes `youtube.readonly`,
  `yt-analytics.readonly` and `youtube.force-ssl`. Then reconnect at
  `APP_URL/oauth/youtube/start?token=API_TOKEN`. Watch time from YouTube lags 1–2 days.

`APP_URL/status?token=API_TOKEN` lists the permissions each connection was granted (`granted`).

## 6. Turn on publishing

Set `PUBLISH_ENABLED=true`, redeploy, then test (posts immediately to every platform in `PLATFORMS`):
```bash
curl -X POST "APP_URL/jobs?force=true" -H "Authorization: Bearer $API_TOKEN" \
     -H 'content-type: application/json' -d @examples/sample_quiz.json
```
(Delete the sample post afterwards.)

## 7. Weekly quiz Routine (Claude Code)

1. In the Claude Code cloud environment's settings (environment menu in the session's title
   bar → Edit), add `SHORTS_API_TOKEN` = the `API_TOKEN` value (or a network secret for the app's
   host that sends `Authorization: Bearer …`). Make sure the network policy allows the app's host.
2. The Routine "Weekly quiz batch (TechNews-Bot)" runs the prompt in
   [ROUTINE_PROMPT.md](ROUTINE_PROMPT.md) weekly on **Monday 19:05 Europe/London** (cron
   `CRON_TZ=Europe/London 5 19 * * 1`), fresh session each run. If the old app is still deployed
   it stops and reports that instead of submitting anything.
3. First week: deploy on any day and fire the Routine once by hand; it fills the next 7 days,
   then each Monday run fills whatever is free from Tuesday to the following Monday.
