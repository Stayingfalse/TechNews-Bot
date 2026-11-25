# Launching raosanta.uk (@raosanta.uk)

The whole season is planned in [`santa_season/2026.json`](../santa_season/2026.json) (calendar:
[SANTA_SEASON_2026.md](SANTA_SEASON_2026.md)). There's no routine: once it's switched on, the
server books the plan 3 days ahead and makes and posts each video itself, until 7 January.
A second short video, the countdown to Christmas, posts every night at 00:00 UTC until 25 December.

## 1. The accounts (owner)

1. **Instagram:** create **@raosanta.uk** and switch it to a creator account (Settings → Account
   type and tools).
   - Bio, for example: "Anonymous Christmas gifts from Amazon wishlists. Random Acts, not Secret
     Santa. Free at raosanta.uk".
   - Profile picture: `assets/santa/stamp-2026.png`.
   - In the Meta developer app (the same one the other channels use), add @raosanta.uk as an
     **Instagram tester**, then accept the invite from the account (Settings → Website permissions
     → Apps and websites → Tester invites).
2. **YouTube:** create a channel called raosanta.uk on the Google account you want it under.

## 2. One shared token (owner)

Make a random token, e.g. `openssl rand -hex 32`. The same value goes in three places below.

## 3. Settings in Easypanel (owner)

Add these lines; leave everything else as it is.

| Service | Add | Why |
|---|---|---|
| `mcwales` / `techshorts` (this bot) | `RAOSANTA_API_URL=https://raosanta.uk` | where the figures come from |
| | `RAOSANTA_API_TOKEN=<the token>` | lets the bot read them |
| | `SANTA_ENABLED=false` | switched on in step 7 |
| `ras` / `raosanta-uk` (prod site) | `PROMO_API_TOKEN=<the token>` | turns on `/api/promo/stats` |
| `ras` / `raosanta-dev` (optional) | `PROMO_API_TOKEN=<the token>` | the same endpoint on dev, for testing |

Optional: the same value as the GitHub secret `E2E_PROMO_API_TOKEN` on rast3, so CI checks the figures.

## 4. Merge and deploy (owner approves)

1. **rast3:** merge the promo-stats PR into `main` and deploy `raosanta-uk` (it also carries the
   Next.js 16.4.6 security patch).
2. **TechNews-Bot:** merge the raosanta.uk PR into `main` and deploy `techshorts`.

## 5. Connect the accounts (owner, in a browser)

Signed in to the bot's dashboard (or add `?token=<API_TOKEN>`):
- https://quiz.cezz.co.uk/oauth/instagram/start?channel=santa, logged in **as @raosanta.uk**;
- https://quiz.cezz.co.uk/oauth/youtube/start?channel=santa, with the channel's Google login.

## 6. Check (owner, or Claude with the bot's API token)

- `GET /santa/stats`: `"connected": true` and `values` filled in (dates, rounded counts).
- `GET /santa/jobs`: `"can_publish": null` (both accounts connected, publishing on).
- `GET /santa/season`: `"problems": []`.
- `POST /santa/preview` with `examples/santa/pitch-workplace.json`: the video, with Lily's voice,
  arrives in Discord. Nothing is posted.

## 7. Switch on (owner)

Set `SANTA_ENABLED=true` on `techshorts` and restart it. The first slot is the next 21:30 (or set
another with `PUT /santa/anchor?at=YYYY-MM-DDTHH:MM`). Within 15 minutes Discord lists the first
bookings; each video's preview arrives 45 minutes before it posts.

## Day to day

| To... | Do |
|---|---|
| See the plan and where each item stands | `GET /santa/season` |
| See what's booked and when | `GET /santa/slots`, `GET /santa/jobs` |
| Stop one post | `DELETE /santa/jobs/<id>` (before it posts) |
| Post a failed or missed one | `POST /santa/jobs/<id>/retry` |
| Change a video not yet booked | edit `santa_season/2026.json` and deploy |
| Add a one-off | `POST /santa/book` with `{"items": [spec]}` |
| See the figures a video would quote | `GET /santa/stats` |
| Numbers | dashboard → raosanta.uk, or `GET /metrics?channel=santa` |
| Stop everything | `SANTA_ENABLED=false` (bookings are kept) |

## Next season

Copy the file to `santa_season/2027.json` with new ids and dates (`ends` too). The season the
server reads follows the date (August to July); `SANTA_SEASON_FILE` overrides it.
