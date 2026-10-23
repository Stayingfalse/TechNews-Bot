# Weekly quiz routine

The Claude Code Routine "Weekly quiz batch (TechNews-Bot)" (`trig_01AXXtZJkcAtdC4iAk7T2cYm`)
runs this prompt every **Monday at 19:05 Europe/London** in a fresh cloud session, 30 minutes
after the weekly review ([REVIEW_PROMPT.md](REVIEW_PROMPT.md)), whose findings it follows. It
writes the next 7 days of quizzes in one go and books them on the server; the server renders each
one 45 minutes before its slot (preview in Discord), posts it at `POST_TIME` (12:00) and deletes
the video. Keep this file and the trigger in sync.

---

You write next week's daily quiz shorts for YouTube Shorts and Instagram Reels: 7 quizzes, one per day. Each video is rendered by code from a JSON "quiz spec" you write: an intro, 3-5 rounds (each shows a clue with a countdown, then reveals the answer) and an outro asking viewers to comment their score. You do not make the videos yourself, and you do not need any repository.

App: APP_URL = https://quiz.cezz.co.uk
Auth: send `Authorization: Bearer $SHORTS_API_TOKEN` (environment variable) on every request. If that variable is empty, try without the header (a network secret may add it); if you then get 401, stop and report "SHORTS_API_TOKEN is not available in the environment".
Use curl from Bash for the app. Write the spec to a file and POST it with `-d @file`.
If GET APP_URL/schedule returns 404, the old tech-news version of the app is still deployed: stop and report "The quiz version of the app isn't deployed yet (no /schedule endpoint)". Don't submit anything else.

1. Load context:
   - GET APP_URL/schema: the quiz spec's JSON schema; follow its field limits exactly.
   - GET APP_URL/insights/latest: the weekly review written 30 minutes ago from last week's numbers (404 = no review yet). Follow its recommendations and run its experiments exactly as described, including the tags it asks for; where they conflict with the defaults below, the review wins (but never the safety and fact-checking rules).
   - GET APP_URL/schedule?days=7: the posting slots. `free_dates` are the days to fill (on a Monday evening: Tuesday to next Monday). Days already booked are left alone.
   - GET APP_URL/history?limit=60: past quizzes with their theme, title, palette, round types and answers. Never reuse an answer from the history or from quizzes already booked.
   - GET APP_URL/status: `voice_enabled` says whether the host voice-over can be used.
   - GET APP_URL/themes/suggestions: themes viewers commented on last week's "comment a theme" posts, grouped and ranked in `groups` (most suggested first); each group's `first` is the earliest viewer to suggest it.

2. Plan the week: one theme per free date, all different and none repeating the last few history entries. Mix broad themes (e.g. 90s movies, Disney/Pixar, sitcoms, 2000s pop songs, video games, cartoons, animals, food, world landmarks, sport, famous brands, books) with what's topical in that week: a big film release, a holiday or anniversary on that date, the season (horror in October, Christmas films in December). One day a week can be a general-knowledge mix with no theme. Give weekends the easier, broader themes. Rotate the 5 palettes so neighbouring days differ.
   Every week also include two special quizzes, on different days (not back to back):
   - HARD MODE (one a week, ideally midweek): genuinely tougher trivia for people who think they know it all. Use `choice`, `true_false` and `odd_one_out` rounds (an `emoji` or `unscramble` round is fine only if it is properly hard), with less obvious answers: deep cuts, exact years, "which came first", behind-the-scenes facts. Still fair: every answer must be checkable, nothing obscure for its own sake; aim for a typical score of 2/5. Give it 7-8 s of think time per round. Say so in the title, e.g. "*Hard* mode: only 1% get 5/5", and in the caption.
   - FORMAT SPECIAL (one a week, ideally at the weekend): every round uses the same round type, e.g. all `emoji`, all `bad_description`, all `unscramble`, all `true_false` ("Real or fake?") or all `odd_one_out`. Pick a different format from the last format special (check the history's round types), and say it in the title, e.g. "5 *scrambled* movies: can you solve them?", "Badly described *Disney* films".
   The other five quizzes follow the normal mix below.
   CLIFFHANGERS (2-3 quizzes a week, never two days in a row): the last round is the cliffhanger (`"cliffhanger": true` on that round). The video shows the question and countdown but not the answer; viewers comment their answer, and the next quiz reveals it with a shout-out to the first correct commenters, whose comments then get a reply pointing at the new video. So the cliffhanger round must be easy to judge from a short comment: an `emoji`, `unscramble`, `bad_description` or `choice` round whose answer is a well-known title or name, or a `true_false`. Give `accept` the common short forms (e.g. ["Lion King"] for "The Lion King"); typos are forgiven automatically. Make it a satisfying one (not the easiest round). Say it in the caption: "Comment your answer to the last one, right answers get a shout-out tomorrow 👇". Any quiz can be a cliffhanger, including a special.
   VIEWER-PICKED THEME (when there are suggestions): pick one group from the suggestions, usually the top one, skipping anything rude, political, tragic, about private individuals, too narrow for 4-5 famous answers, or a theme from the last few history entries. Make it one of the week's quizzes, ideally Wednesday to Friday, with that theme and `picked_by` = the group's `first` entry (`user`, `platform`, `comment_id` and `text`, copied exactly). The video shows their comment on screen as a comment card, and they get a reply under it once it posts. Say it in the caption, e.g. "You picked it: Disney villains! Thanks @early_bird 🙌". One a week; none if nothing suitable.
   THEME ASK (2 quizzes a week, not on a cliffhanger day, ideally Thursday and Sunday): set `ask_theme: true`. The outro then asks viewers to comment a theme for next week, and the caption should too: "Comment a theme for next week's quiz 👇".
   VOICE TEST (when `voice_enabled` is true, until the review says otherwise): set `voice: true` on 3 of the 7 days, spread across the intro types and weekdays/weekend, so the review can compare them with the silent ones.
   INTRO TEST (until the review says otherwise): viewers leave after 6-13 seconds, so the opening is being tested. Set `intro` to `card` (2.8 s title card) on 2 days, `quick` (1.2 s title card) on 3 days and `banner` (no card, the title rides a banner over round 1) on 2 days, spread across weekdays and weekend.

3. For each quiz write 4-5 rounds (3 is allowed for long clues, or when the review asks for shorter quizzes). In normal quizzes mix the types: at least one `emoji` and one `bad_description` round, then add others (the format special uses one type throughout; hard mode follows step 2):
   - `emoji`: 2-7 emojis that spell out a famous title. Make it solvable: literal pieces of the title or the most iconic plot elements, in order. Only use common emojis (no flags of obscure regions, no new-release emojis).
   - `bad_description`: a famous movie/show/book/song described badly: technically accurate but hilariously unhelpful, literal, or from the villain's point of view ("A man refuses to share a door and it costs him everything" = Titanic). Max 120 chars, one *highlighted* word.
   - `true_false` (shown as "Real or fake?"): a surprising statement plus a one-line explanation. About half should be fake, but fakes must be plausible.
   - `choice`: a question with 3-4 short options ("Which came out first?", "What year…?", "Who voiced…?").
   - `odd_one_out`: four items, one doesn't belong for a clear, checkable reason.
   - `unscramble`: just give the answer (4-22 letters); the renderer scrambles it. Best for short, well-known titles.
   Order rounds from easiest to hardest, with the most fun one last. In normal quizzes, answers must be famous enough that most viewers know them; aim for a typical score of 3/5. No answer may appear twice in the week.

4. Verify: every fact used in a `true_false`, `choice`, `odd_one_out` or a `note` (years, names, records) must be confirmed by at least one reputable source (two for anything surprising, and two for every fact in the hard-mode quiz). If you can't confirm it, replace the round. Nothing rude, political, tragic or about private individuals.

5. Write each spec (validate against the schema):
   - id: YYYY-MM-DD-short-slug (the date it posts; add -pm for an evening slot on the same day).
   - title: a hook of max ~8 words with exactly one *highlighted* word, e.g. "Only *real* 90s kids get 5/5", "Guess the Disney film from *emojis*". subtitle: short, e.g. "Guess before the timer runs out".
   - think: 5 s by default; 6-7 s for long descriptions or statements, 4 s for easy emoji rounds, 7-8 s in hard mode. reveal: leave the default.
   - palette: one of the schema's palettes, different from the quiz before.
   - music: "auto" (picks from the uploaded library, else built-in synth music).
   - caption: 1-2 short friendly lines ending with a question or call to action ("How many did you get? 👇"), no answers in the caption. 3-6 hashtags (#quiz plus theme tags; add #hardquiz for hard mode).
   - intro, cliffhanger, accept, picked_by, ask_theme, voice: see step 2. `ask_comment` (a "Comment your guess!" sticker on one round's countdown) and `pause_hint` (a "Pause to answer" sticker): leave off unless the review asks for them.
   - tags: labels the dashboard and next week's review compare by. Always set `special` (`hard`, `format` or `none`) and `cta` (a 1-3 word label for the call to action you used, e.g. `comment-score`, `cliffhanger-comment`, `tag-a-friend`), plus every tag an experiment from the review asks for. Lowercase keys, short values. intro, cliffhanger, ask_comment, pause_hint, ask_theme, picked_by and voice are labelled automatically; don't repeat them.

6. Book the week in one request: POST APP_URL/schedule with `{"items": [{"date": "YYYY-MM-DD", "spec": {...}}, ...]}` (Content-Type: application/json), one item per free date. Leave out `time` (each posts at the default time); add `"time": "HH:MM"` only if a human asked for extra posts on a day or the review recommends a posting-time test. It's all-or-nothing: on 409 the response lists every problem (a repeated answer, a taken slot, a quiz that can't be rendered); fix those quizzes and resend the whole batch. On 422 fix the spec it names and resend. Never pass `replace: true` unless a human asked you to.

7. Confirm: GET APP_URL/schedule?days=7 and check every slot you sent shows `booked` in its day's `bookings` (videos are made shortly before each post, not now). The server posts each one at its time and sends previews and results to Discord itself.

8. Report in one short message: which of the review's recommendations and experiments you applied (and where), the viewer-picked theme (whose, and why that one) or why none, then a table of date, time, theme, tags and the answers (mark the hard-mode and format-special quizzes), the sources for factual rounds, and anything that failed.
