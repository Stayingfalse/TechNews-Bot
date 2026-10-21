# Daily quiz routine

The scheduled Claude Code Routine runs this prompt every day in a fresh cloud session
(trigger "TechNews-Bot daily story", 07:41 Europe/London; rename it to "Daily quiz" when you switch
it over). Keep this file and the trigger in sync.

---

You write a daily quiz short for TikTok and Instagram Reels. The video is rendered by code from a JSON "quiz spec" you write: an intro, 3-5 rounds (each shows a clue with a countdown, then reveals the answer) and an outro asking viewers to comment their score. You do not make the video yourself, and you do not need any repository.

App: APP_URL = https://mcwales-techshorts.apysn4.easypanel.host
Auth: send `Authorization: Bearer $SHORTS_API_TOKEN` (environment variable) on every request. If that variable is empty, try without the header (a network secret may add it); if you then get 401, stop and report "SHORTS_API_TOKEN is not available in the environment".
Use curl from Bash for the app. Write the spec to a file and POST it with `-d @file`.

1. Load context: GET APP_URL/schema (the spec's JSON schema; follow its field limits exactly) and GET APP_URL/history?limit=60 (past quizzes with their theme, palette, round types and answers). Never reuse an answer from the history.

2. Pick today's theme. Rotate so consecutive days feel different, e.g. 90s movies, Disney/Pixar, sitcoms, 2000s pop songs, video games, cartoons, animals, food, world landmarks, Christmas films (in season), horror films (October), sport, famous brands, books. Use what's topical: a big film release, a holiday, an anniversary. Or leave the theme blank for a general-knowledge mix. Don't repeat the theme of either of the last two history entries.

3. Write 4-5 rounds (3 is allowed for long clues). Mix the types; every quiz should have at least one `emoji` and one `bad_description` round, then add others:
   - `emoji`: 2-7 emojis that spell out a famous title. Make it solvable: literal pieces of the title or the most iconic plot elements, in order. Only use common emojis (no flags of obscure regions, no new-release emojis).
   - `bad_description`: a famous movie/show/book/song described badly: technically accurate but hilariously unhelpful, literal, or from the villain's point of view ("A man refuses to share a door and it costs him everything" = Titanic). Max 120 chars, one *highlighted* word.
   - `true_false` (shown as "Real or fake?"): a surprising statement plus a one-line explanation. About half should be fake, but fakes must be plausible.
   - `choice`: a question with 3-4 short options ("Which came out first?", "What year…?", "Who voiced…?").
   - `odd_one_out`: four items, one doesn't belong for a clear, checkable reason.
   - `unscramble`: just give the answer (4-22 letters); the renderer scrambles it. Best for short, well-known titles.
   Order rounds from easiest to hardest, with the most fun one last. Answers must be famous enough that most viewers know them; aim for a typical score of 3/5.

4. Verify: every fact used in a `true_false`, `choice`, `odd_one_out` or a `note` (years, names, records) must be confirmed by at least one reputable source (two for anything surprising). If you can't confirm it, replace the round. Nothing rude, political, tragic or about private individuals.

5. Write the spec (validate against the schema):
   - id: YYYY-MM-DD-short-slug (today's date).
   - title: a hook of max ~8 words with exactly one *highlighted* word, e.g. "Only *real* 90s kids get 5/5", "Guess the Disney film from *emojis*". subtitle: short, e.g. "Guess before the timer runs out".
   - think: 5 s by default; 6-7 s for long descriptions or statements, 4 s for easy emoji rounds. reveal: leave the default.
   - palette: different from the last two history entries.
   - music: "auto" (picks from the uploaded library, else built-in synth music).
   - caption: 1-2 short friendly lines ending with a question ("How many did you get? 👇"), no answers in the caption. 3-6 hashtags (#quiz plus theme tags).

6. Submit: POST APP_URL/jobs with the spec as JSON (Content-Type: application/json). On 409 the response lists answers already used: replace those rounds and resubmit. On 422 fix the spec and resubmit. Then poll GET APP_URL/jobs/{job_id} every 20 s until status is done or failed (about 2 minutes). The app publishes and sends the video to Discord itself.

7. Report in one short message: the theme, each round with its answer and (for factual rounds) the source, the music used, the publish results and the video_url. If anything failed, say exactly what.
