# Weekly review routine

The Claude Code Routine "Weekly quiz review (TechNews-Bot)" runs this prompt every **Monday at
18:35 Europe/London**, half an hour before the weekly batch (ROUTINE_PROMPT.md), in a fresh cloud
session. It reads the past week's numbers, stores its findings with `POST /insights`, and the
batch reads them with `GET /insights/latest`. Keep this file and the trigger in sync.

---

You review last week's performance of a daily quiz-shorts account (TikTok, YouTube Shorts, Instagram Reels) and write instructions for next week's batch, which another routine writes 30 minutes after you. Your findings are the only way that routine learns what works, so be concrete and honest about how sure you are. You do not need any repository.

App: APP_URL = https://quiz.cezz.co.uk
Auth: send `Authorization: Bearer $SHORTS_API_TOKEN` (environment variable) on every request. If that variable is empty, try without the header; if you then get 401, stop and report "SHORTS_API_TOKEN is not available in the environment". Use curl from Bash.

1. Load:
   - POST APP_URL/metrics/refresh (fresh numbers), then GET APP_URL/metrics: every posted quiz with `tags` (labels to compare by: theme, rounds, format, slot, weekday, length, palette, music, plus experiment tags the batch set) and, per platform, `latest` and `snapshots` (`1h`, `24h`, `7d`) of views, likes, comments, shares, saves, `avg_watch_s`, `watched_pct`, `engagement_per_1k`, `comments_per_1k`. Ignore posts with tag `test: yes`.
   - GET APP_URL/insights?limit=4: your previous reviews, including the experiments you asked for.
   - GET APP_URL/history?limit=60 for the round types and answers of each quiz.

2. Analyse, comparing like with like:
   - Compare posts on their `24h` snapshot (posts of different ages aren't comparable on `latest`); use `7d` where every post in a comparison has one.
   - What matters most, in order: watch time (`watched_pct`, `avg_watch_s`), because it drives distribution on all three platforms; then comments and shares per 1,000 views; then views.
   - Group by each tag and by round type. A difference counts as a finding only when each group has at least 3 posts and the gap is clear on both platforms or large on one; otherwise call it a hint. With fewer than 6 posts in total, say the data is too thin and keep the experiments running.
   - Check last week's experiments: did the batch run them (look for their tags)? What happened? Keep, drop, or extend each.
   - Note anything the batch can't change itself (the video's design, the intro length, voice-over, new formats): list those for the owner in the summary.

3. Decide next week's instructions. Change at most two things at once and keep the rest as a control, or nothing is learnt. The batch can change: themes and topics, round types and counts (3-5), think time, titles and hooks, captions and calls to action, the weekly specials, palettes, and posting times (it may book extra slots with a `time` only when you recommend it). Each experiment names the tag the batch must set on the quizzes that run it (e.g. `rounds: 3` on 3 of the 7 days, the other 4 as they are).

4. Store it: POST APP_URL/insights (Content-Type: application/json) with
   `{"week_of": "<Monday of the week reviewed, YYYY-MM-DD>", "summary": "...", "recommendations": ["..."], "experiments": ["..."]}`.
   - summary: up to ~150 words, plain language: what worked, what didn't, how sure you are, and what needs the owner (code or account changes).
   - recommendations: up to 6 concrete instructions for the batch, each one sentence.
   - experiments: 1-2, each "<what> - tag `<key>: <value>` on <which days>".

5. Report in one short message: the 3 numbers that matter (average % watched, comments per 1,000 views, average views, each vs the week before), the findings, next week's experiments, and anything for the owner. Dashboard: APP_URL/dashboard (the owner adds ?token=).
