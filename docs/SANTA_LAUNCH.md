# Launching raosanta.uk (@raosanta.uk)

What's built: [SANTA_PLAN.md](SANTA_PLAN.md) §4 steps 1-4. Switch it on in this order.

## 1. The accounts

1. **Instagram:** create **@raosanta.uk** and switch it to a creator (or business) account.
   - Bio, for example: "Anonymous Christmas gifts from Amazon wishlists. Random Acts, not Secret
     Santa 🎁 Free at raosanta.uk".
   - Profile picture: the 2026 stamp (`assets/santa/stamp-2026.png`).
   - In the Meta developer app, add it as an **Instagram tester** and accept the invite from the
     account (Settings → Website permissions → Apps and websites → Tester invites).
2. **YouTube:** a channel named raosanta.uk, on its own Google login. The upload quota is shared by
   the Google project (about 6 uploads a day). The quiz uses 1 and raosanta.uk about 1.

## 2. Settings (Easypanel, this app)

| Setting | Value | Why |
|---|---|---|
| `SANTA_ENABLED` | `true` | runs the schedule (off: nothing is made or posted) |
| `RAOSANTA_API_TOKEN` | the site's `PROMO_API_TOKEN` | live figures |
| `RAOSANTA_API_URL` | `https://raosanta.uk` (`https://dev.raosanta.uk` while testing) | where the figures come from |
| `SANTA_VOICE_BUDGET` | `7000` (default) | narrator characters a month |
| everything else | defaults | 22 h cadence, 07:00-22:30, anchor 21:30, 60 min clear of other channels |

`PUBLISH_ENABLED` is already on for the other channels.

## 3. Connect the accounts

Signed in to the dashboard (or with `?token=`):
- `https://quiz.cezz.co.uk/oauth/instagram/start?channel=santa`, logged in **as @raosanta.uk**;
- `https://quiz.cezz.co.uk/oauth/youtube/start?channel=santa`, with the channel's Google login.

Check: `GET /santa/jobs` shows `"can_publish": null`, and `GET /santa/stats` shows `"connected": true`
with values.

## 4. A dry run, then start

1. `POST /santa/preview` with `examples/santa/pitch-workplace.json`: the video (with Lily's voice)
   arrives in Discord. Nothing is posted.
2. `PUT /santa/anchor?at=<date>T21:30`: where the pattern starts. Without it, the first slot is
   the next 21:30.
3. Book the first week: fire the weekly routine by hand (below), or `POST /santa/week` with
   `{"items": [...]}`. Check `GET /santa/slots`.

## 5. The routine

| Routine | When | Prompt |
|---|---|---|
| raosanta.uk weekly promos | Sundays 19:23 Europe/London | [SANTA_ROUTINE_PROMPT.md](SANTA_ROUTINE_PROMPT.md) |

It runs in a fresh cloud session in the same environment as the other routines (it needs
`SHORTS_API_TOKEN`), with no connectors. Create it switched off, and switch it on once step 3 is
done.

## Day to day

| To... | Do |
|---|---|
| See what's booked and when | `GET /santa/slots`, `GET /santa/jobs` |
| Stop a post | `DELETE /santa/jobs/<id>` (before it posts) |
| Post a failed or missed one | `POST /santa/jobs/<id>/retry` |
| See the figures a video would quote | `GET /santa/stats` |
| Numbers | dashboard → raosanta.uk, or `GET /metrics?channel=santa` (tags: format, audience, voice, hour) |
| Stop everything | `SANTA_ENABLED=false` (bookings are kept) |
