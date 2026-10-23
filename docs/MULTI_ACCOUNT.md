# Multiple accounts (channels)

Goal: one server running several **channels**. A channel is a brand that posts one **kind** of
content to its own Instagram account and YouTube channel, on its own schedule, written by its own
weekly routine. Examples: the daily quiz (today), a "did you know?" facts channel, a sports-trivia
spin-off, a kids' quiz.

## What's in place (no change to what posts today)

- `app/channels.py`: the `Channel` record (id, name, kind, brand handle, posting time, platforms)
  and a registry with one channel, `main`, built from the current settings.
- **Jobs record their channel** (`job["channel"]`, `main` for everything so far; older jobs without
  the field count as `main`).
- **Each job runs as its channel**: the worker wraps rendering and posting in `channels.use(...)`, so
  anything below it that reads tokens gets that channel's accounts.
- **Tokens are stored per channel**: `store.get_tokens/set_tokens` file a channel's tokens under
  `"<channel>:<platform>"`; `main` keeps the plain `"instagram"` / `"youtube"` keys, so the
  connections made before channels existed stay where they are.

## Still to do, in order

1. **Channel config.** Load extra channels from `/data/channels.json` (id, name, kind, handle, post
   time, platforms, palette set, voices, hashtags), editable from the dashboard. Per-channel
   overrides fall back to the global settings.
2. **Connections per channel.** `/oauth/{platform}/start?channel=…`: carry the channel through the
   OAuth state and save with `set_tokens(..., channel=…)`. The Instagram app and Google project can
   be shared: each channel connects its own account through them. Each extra Instagram account must
   be added as a tester (development mode). YouTube needs one Google login per channel; the upload
   quota (10,000 units/day, about 6 uploads) is shared by the Google project, so ask for more before
   running 3+ channels.
3. **Schedules per channel.** Slots become (channel, date, time). `/schedule?channel=…` and
   `POST /schedule` items carry `channel`; the repeat-answer check and the empty-day warnings run per
   channel. The scheduler and render queue stay shared (one render at a time is plenty for a few
   channels: a render takes 2-3 minutes).
4. **Everything else keyed by channel.** History, metrics, insights, the cliffhanger/next-quiz
   comment loop (the previous post *of the same channel*), viewer themes, stories and the weekly
   carousel. The dashboard gets a channel switcher; sign-in lets you see the channels whose account
   you signed in with.
5. **Content kinds.** `kind` picks the spec model, renderer and caption rules: `quiz` is today's
   `QuizSpec` + `render/engine.py`. A new kind adds its spec model, its scenes (reusing the stage,
   palettes, timer, voice-over, music and audio mix) and its slide images; the pipeline, scheduler,
   publishers and metrics don't change. `/schema?kind=…` serves each kind's schema to its routine.
6. **Routines per channel.** One weekly review + batch pair per channel, with the channel id (and
   its kind) in the prompt, so each learns from its own numbers only.
7. **Branding per channel.** Handle, palette set, fonts, music folder and voices, so channels don't
   look alike.

## Things to decide before step 1

- Which second channel first, and does it reuse the quiz format (cheapest: a new channel of kind
  `quiz` with its own themes) or need a new kind?
- One Discord webhook for all channels, or one each?
- Does a channel ever post to TikTok again? The publisher was removed; it would come back as a
  per-channel platform.
