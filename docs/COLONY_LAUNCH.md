# Launching Farside (@farside.colony)

What's built: [COLONY_PLAN.md](COLONY_PLAN.md) §7, milestones M1-M3. This is the order to switch
it on in.

## 1. The account

1. Create **@farside.colony** on Instagram and switch it to a **creator** (or business) account
   (Settings → Account type and tools), as was done for @dungeoncrawlergram.
2. Bio, for example: "A colony on the far side of a moon. Follow to live here. Comment to get your
   own settler 🪐". Profile picture: a still from the look test (the pod at dusk).
3. In the Meta developer app, add @farside.colony as an **Instagram tester** (the app is in
   development mode) and accept the invite from the account (Settings → Website permissions → Apps
   and websites → Tester invites).

## 2. Deploy and settings (Easypanel)

Merge this branch and deploy. Then set, and restart:

| Setting | Value | Why |
|---|---|---|
| `COLONY_ENABLED` | `true` | switches the schedule on |
| `COLONY_POST_TIME` | `19:00` | the slot racing used to have (default) |
| `COLONY_CUTOFF_MINUTES` | `90` | the daily routine's deadline before the post (default) |
| `COLONY_RENDER_LEAD_MINUTES` | `60` | renders after the cut-off (default) |
| `ADVENTURE_VOICE_BUDGET` | `10000` | the new split of the 30,000 credits (COLONY_PLAN §5d) |
| `RACING_ENABLED` | leave unset (off) | Sixel Speedway stays switched off |

`DEEPSEEK_API_KEY` is already set for the dungeon crawl; Farside's comment sorter uses it too
(`COLONY_SORTER=off` to turn just that off).

## 3. Connect the account

Signed in to the dashboard (or with `?token=`), open
`https://quiz.cezz.co.uk/oauth/instagram/start?channel=colony` and log in **as @farside.colony**.
Check: `GET /colony/state` shows `"can_publish": null`, and `GET /status` lists the colony's
Instagram account.

## 4. Check the privacy wording

`app/legal/privacy.html` now says what Farside does with usernames and comments (the AI reads
them, DeepSeek sorts the text, settlers go on opt-out, comments go after 30 days). Read it before
the first post: it's the legal page.

## 5. The routines

Two Claude Code Routines, created switched **off**, to switch on once steps 2-3 are done:

| Routine | When | Prompt |
|---|---|---|
| Farside weekly plan (`trig_0141jgKc2wQkRjsBqvUjdZP6`) | Sundays 20:41 Europe/London | [COLONY_ROUTINE_PROMPT.md](COLONY_ROUTINE_PROMPT.md) |
| Farside daily episode (`trig_017krnrETPjNx22Dgx9ivMQf`) | every day 15:47 Europe/London (about 3 h before the 19:00 post) | [COLONY_DAILY_PROMPT.md](COLONY_DAILY_PROMPT.md) |

Both run in a fresh cloud session in the same environment as the quiz routines (which has
`SHORTS_API_TOKEN`), and need no connectors.

Before the first week: run the weekly routine once by hand (fire it now) so the first days have a
plan, and check the server accepted it (`GET /colony/week?date=<first day>` shows `"from": "plan"`).

## 6. A dry run, then start

1. `POST /colony/preview?date=<first day>`: renders that day as it stands and sends it to Discord.
   Nothing is posted or saved.
2. `POST /colony/start?date=<first day>`: books the first day. From then on it runs by itself:
   comments read every 15 minutes, the daily routine's episode by 17:30, the render at 18:00 with a
   preview in Discord, the post at 19:00, then the replies.

## Day to day

| To... | Do |
|---|---|
| See the colony, today's job, the reply queue | `GET /colony/state` |
| Keep someone out of it for good | `POST /colony/block?user=@name` (today's episode renders again if there's time) |
| Take a drawn part out | `POST /colony/block?part=pet/dragon` |
| Stop today's post | `DELETE /colony/jobs/<date>` |
| Post a failed or missed day | `POST /colony/jobs/<date>/retry` |
| Look at a day without posting | `POST /colony/preview?date=<date>` |
| Numbers | dashboard → Farside, or `GET /metrics?channel=colony` (tag `ai`: full / plan / spare / counts) |
