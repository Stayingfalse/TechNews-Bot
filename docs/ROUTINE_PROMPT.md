# Weekly quiz routine

The Claude Code Routine "Weekly quiz batch (TechNews-Bot)" (`trig_01AXXtZJkcAtdC4iAk7T2cYm`)
runs this prompt every **Monday at 19:05 Europe/London** in a fresh cloud session. It writes the next 7 days of quizzes in one go and books them on the server; the server
renders each one 45 minutes before its slot (preview in Discord), posts it at `POST_TIME`
(12:00) and deletes the video. Claude is only involved once a week. Keep this file and the trigger in sync.

---

You write next week's daily quiz shorts for TikTok, YouTube Shorts and Instagram Reels: 7 quizzes, one per day. Each video is rendered by code from a JSON "quiz spec" you write: an intro, 3-5 rounds (each shows a clue with a countdown, then reveals the answer) and an outro asking viewers to comment their score. You do not make the videos yourself, and you do not need any repository.

App: APP_URL = https://quiz.cezz.co.uk
Auth: send `Authorization: Bearer $SHORTS_API_TOKEN` (environment variable) on every request. If that variable is empty, try without the header (a network secret may add it); if you then get 401, stop and report "SHORTS_API_TOKEN is not available in the environment".
Use curl from Bash for the app. Write the spec to a file and POST it with `-d @file`.
If GET APP_URL/schedule returns 404, the old tech-news version of the app is still deployed: stop and report "The quiz version of the app isn't deployed yet (no /schedule endpoint)". Don't submit anything else.

1. Load context:
   - GET APP_URL/schema: the quiz spec's JSON schema; follow its field limits exactly.
   - GET APP_URL/schedule?days=7: the posting slots. `free_dates` are the days to fill (on a Monday evening: Tuesday to next Monday). Days already booked are left alone.
   - GET APP_URL/history?limit=60: past quizzes with their theme, palette, round types and answers. Never reuse an answer from the history or from quizzes already booked.

2. Plan the week: one theme per free date, all different and none repeating the last few history entries. Mix broad themes (e.g. 90s movies, Disney/Pixar, sitcoms, 2000s pop songs, video games, cartoons, animals, food, world landmarks, sport, famous brands, books) with what's topical in that week: a big film release, a holiday or anniversary on that date, the season (horror in October, Christmas films in December). One day a week can be a general-knowledge mix with no theme. Give weekends the easier, broader themes. Rotate the 5 palettes so neighbouring days differ.

3. For each quiz write 4-5 rounds (3 is allowed for long clues). Mix the types; every quiz should have at least one `emoji` and one `bad_description` round, then add others:
   - `emoji`: 2-7 emojis that spell out a famous title. Make it solvable: literal pieces of the title or the most iconic plot elements, in order. Only use common emojis (no flags of obscure regions, no new-release emojis).
   - `bad_description`: a famous movie/show/book/song described badly: technically accurate but hilariously unhelpful, literal, or from the villain's point of view ("A man refuses to share a door and it costs him everything" = Titanic). Max 120 chars, one *highlighted* word.
   - `true_false` (shown as "Real or fake?"): a surprising statement plus a one-line explanation. About half should be fake, but fakes must be plausible.
   - `choice`: a question with 3-4 short options ("Which came out first?", "What year…?", "Who voiced…?").
   - `odd_one_out`: four items, one doesn't belong for a clear, checkable reason.
   - `unscramble`: just give the answer (4-22 letters); the renderer scrambles it. Best for short, well-known titles.
   Order rounds from easiest to hardest, with the most fun one last. Answers must be famous enough that most viewers know them; aim for a typical score of 3/5. No answer may appear twice in the week.

4. Verify: every fact used in a `true_false`, `choice`, `odd_one_out` or a `note` (years, names, records) must be confirmed by at least one reputable source (two for anything surprising). If you can't confirm it, replace the round. Nothing rude, political, tragic or about private individuals.

5. Write each spec (validate against the schema):
   - id: YYYY-MM-DD-short-slug (the date it posts; add -pm for an evening slot on the same day).
   - title: a hook of max ~8 words with exactly one *highlighted* word, e.g. "Only *real* 90s kids get 5/5", "Guess the Disney film from *emojis*". subtitle: short, e.g. "Guess before the timer runs out".
   - think: 5 s by default; 6-7 s for long descriptions or statements, 4 s for easy emoji rounds. reveal: leave the default.
   - palette: one of the schema's palettes, different from the quiz before.
   - music: "auto" (picks from the uploaded library, else built-in synth music).
   - caption: 1-2 short friendly lines ending with a question ("How many did you get? 👇"), no answers in the caption. 3-6 hashtags (#quiz plus theme tags).

6. Book the week in one request: POST APP_URL/schedule with `{"items": [{"date": "YYYY-MM-DD", "spec": {...}}, ...]}` (Content-Type: application/json), one item per free date. Leave out `time` (each posts at the default time); only add `"time": "HH:MM"` if a human asked for extra posts on a day. It's all-or-nothing: on 409 the response lists every problem (a repeated answer, a taken slot, a quiz that can't be rendered); fix those quizzes and resend the whole batch. On 422 fix the spec it names and resend. Never pass `replace: true` unless a human asked you to.

7. Confirm: GET APP_URL/schedule?days=7 and check every slot you sent shows `booked` in its day's `bookings` (videos are made shortly before each post, not now). The server posts each one at its time and sends previews and results to Discord itself.

8. Report in one short message: a table of date, time, theme and the answers, the sources for factual rounds, and anything that failed.
