from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

PLATFORMS = ("youtube", "instagram")
RETIRED = {"tiktok"}  # once supported; still accepted in PLATFORMS so an old env value doesn't stop the app


def _bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    def __init__(self) -> None:
        self.api_token = os.environ.get("API_TOKEN", "")
        self.public_base_url = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
        self.data_dir = Path(os.environ.get("DATA_DIR", "/data"))
        self.brand_handle = os.environ.get("BRAND_HANDLE", "")

        # Master switch: when false, videos are rendered and you're notified, but nothing is uploaded.
        self.publish_enabled = _bool("PUBLISH_ENABLED", False)
        # Where to post, comma-separated: any of youtube, instagram.
        listed = [p.strip().lower() for p in os.environ.get("PLATFORMS", "youtube,instagram").split(",") if p.strip()]
        self.platforms = [p for p in listed if p not in RETIRED]
        unknown = set(self.platforms) - set(PLATFORMS)
        if unknown:
            raise ValueError(f"PLATFORMS has unknown entries {sorted(unknown)}; use any of {PLATFORMS}")

        # Scheduled quizzes go out at POST_TIME (24h, local to TIMEZONE) on their day.
        self.tz = ZoneInfo(os.environ.get("TIMEZONE", "Europe/London"))
        self.post_time = os.environ.get("POST_TIME", "12:00")
        h, m = (int(x) for x in self.post_time.split(":"))
        if not (0 <= h < 24 and 0 <= m < 60):
            raise ValueError("POST_TIME must be HH:MM")

        self.instagram_app_id = os.environ.get("INSTAGRAM_APP_ID", "")
        self.instagram_app_secret = os.environ.get("INSTAGRAM_APP_SECRET", "")
        self.graph_version = os.environ.get("GRAPH_API_VERSION", "v23.0")

        self.youtube_client_id = os.environ.get("YOUTUBE_CLIENT_ID", "")
        self.youtube_client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
        # public | unlisted | private. Uploads from an unaudited Google API project are locked to private.
        self.youtube_privacy = os.environ.get("YOUTUBE_PRIVACY", "public")

        # After each post, comment on the previous one pointing at it ("Next quiz is up"), and reply
        # under each correct cliffhanger answer. Needs the comments permission on each platform.
        self.next_link_comments = _bool("NEXT_LINK_COMMENTS", True)

        # Host voice-over for quizzes with "voice": true. Lines are cached in DATA_DIR/voice.
        self.elevenlabs_api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        # Default "Liam" (built-in, energetic). Library voices need a paid ElevenLabs plan for API use.
        self.elevenlabs_voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "TX3LPaxmHKxFdv7VOQHJ")
        self.elevenlabs_model = os.environ.get("ELEVENLABS_MODEL", "eleven_v3")  # v3/v4 read in an [excited] delivery
        # Host voices a quiz can pick by name (`voice_name`), being tested against each other.
        # ELEVENLABS_VOICES=name=id,name=id replaces the list.
        voices = os.environ.get("ELEVENLABS_VOICES", "alex=dEc1rkm0ul0kDedEuETS,liam=TX3LPaxmHKxFdv7VOQHJ,"
                                                     "althea=UDYENShoqlMksjDyKqGV,milly=rSeWUeOepJe3YA3pacAe")
        pairs = [v.split("=", 1) for v in voices.split(",") if "=" in v]
        self.voices = {name.strip().lower(): vid.strip() for name, vid in pairs}  # ids are case-sensitive

        # Instagram extras: a "new quiz out now" story after each Reel, and a weekly carousel of the
        # week's most-viewed quiz on CAROUSEL_DAY (mon..sun) at CAROUSEL_TIME (local).
        self.instagram_stories = _bool("INSTAGRAM_STORIES", False)
        # Monday 20:00: after the week has run and the 19:05 routine has booked the next one
        self.instagram_carousels = _bool("INSTAGRAM_CAROUSELS", True)
        self.carousel_day = os.environ.get("CAROUSEL_DAY", "mon").strip().lower()[:3]
        self.carousel_time = os.environ.get("CAROUSEL_TIME", "20:00")

        # Profile picture rotation: every AVATAR_EVERY_WEEKS weeks (0 = off), on Monday morning, Discord
        # gets the next picture to upload (neither platform's API can change it). Pictures: the
        # avatar-*.png files in assets/avatars, plus any added to DATA_DIR/avatars.
        self.avatar_every_weeks = int(os.environ.get("AVATAR_EVERY_WEEKS", "3"))

        # The adventure channel (docs/ADVENTURE_PLAN.md): its own accounts, connected with
        # /oauth/{platform}/start?channel=adventure. Its renderer lives in adventure/ (Node).
        self.adventure_handle = os.environ.get("ADVENTURE_HANDLE", "dungeoncrawlergram")
        self.adventure_post_time = os.environ.get("ADVENTURE_POST_TIME", "09:00")
        self.adventure_platforms = [p.strip().lower() for p in os.environ.get("ADVENTURE_PLATFORMS", "instagram").split(",") if p.strip()]
        self.adventure_dir = Path(os.environ.get("ADVENTURE_DIR", Path(__file__).resolve().parents[1] / "adventure"))
        # Narrator: "Obsidian - A Dark Fantasy Storyteller" from the ElevenLabs library, on eleven_v3.
        self.adventure_voice_id = os.environ.get("ADVENTURE_VOICE_ID", "acrqYoDVmcpJemOxjC39")
        self.adventure_voice_model = os.environ.get("ADVENTURE_VOICE_MODEL", "eleven_v3")
        # Voice credits the adventure channel may spend per calendar month (1 credit per character,
        # tags included); past it, videos go out without narration.
        self.adventure_voice_budget = int(os.environ.get("ADVENTURE_VOICE_BUDGET", "7200"))
        # The narrator's pauses are shortened to this many seconds (its [long pause] runs to 3-4 s).
        self.adventure_max_pause = float(os.environ.get("ADVENTURE_MAX_PAUSE", "0.6"))

        # The racing channel, Sixel Speedway (docs/RACING_PLAN.md): its own accounts, connected with
        # /oauth/{platform}/start?channel=racing. Bets close RACING_CLOSE_MINUTES before each post.
        self.racing_handle = os.environ.get("RACING_HANDLE", "sixelspeedway")
        self.racing_post_time = os.environ.get("RACING_POST_TIME", "19:00")
        self.racing_close_minutes = int(os.environ.get("RACING_CLOSE_MINUTES", "60"))
        self.racing_platforms = [p.strip().lower() for p in os.environ.get("RACING_PLATFORMS", "instagram").split(",") if p.strip()]
        # The bets pages (balances, bets, seed checks) are served on this domain only
        self.racing_domain = os.environ.get("RACING_DOMAIN", "race.onlydan.uk").strip().lower()
        # Looks to use, comma-separated; with more than one, videos take turns (an A/B test, by race number)
        self.racing_themes = [t.strip() for t in os.environ.get("RACING_THEMES", "pitwall").split(",") if t.strip()]
        # Bet replies: checked every RACING_POLL_MINUTES, sent RACING_REPLY_GAP seconds apart, at most
        # RACING_REPLY_PER_HOUR an hour (start low on a new account and raise it slowly)
        self.racing_poll_minutes = int(os.environ.get("RACING_POLL_MINUTES", "15"))
        self.racing_reply_gap = float(os.environ.get("RACING_REPLY_GAP", "20"))
        self.racing_reply_per_hour = int(os.environ.get("RACING_REPLY_PER_HOUR", "60"))
        self.racing_replies = _bool("RACING_REPLIES", True)
        # Which race runs on which day (the day its video posts): oval, gp, rally, figure8, endurance, drag.
        # "a|b" takes turns week by week (sat=endurance|oval: endurance every other Saturday).
        cal = os.environ.get("RACING_CALENDAR", "mon=oval,tue=rally,wed=gp,thu=figure8,fri=drag,sat=endurance|oval,sun=gp")
        self.racing_calendar = {k.strip().lower()[:3]: v.strip().lower() for k, v in
                                (pair.split("=", 1) for pair in cal.split(",") if "=" in pair)}
        # The weekly bonus is doubled for this many weeks after launch
        self.racing_launch_weeks = int(os.environ.get("RACING_LAUNCH_WEEKS", "4"))

        # healthchecks.io: with an API key the server creates its own checks (see app/health.py)
        self.healthchecks_api_key = os.environ.get("HEALTHCHECKS_API_KEY", "")

        # Shown on the public privacy policy (/privacy): who's responsible and where to write
        self.privacy_controller = os.environ.get("PRIVACY_CONTROLLER", "")
        self.privacy_contact_email = os.environ.get("PRIVACY_CONTACT_EMAIL", "")
        # Verifies Meta's data deletion / deauthorize callbacks when the Facebook app's secret differs
        # from INSTAGRAM_APP_SECRET (either one is accepted)
        self.meta_app_secret = os.environ.get("META_APP_SECRET", "")

        self.discord_webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
        # Videos are deleted once posted everywhere; anything left (failed posts, dry runs) goes after this.
        self.keep_videos_days = int(os.environ.get("KEEP_VIDEOS_DAYS", "3"))
        # Booked quizzes are rendered this long before their slot (a render takes 2-4 minutes).
        self.render_lead_minutes = int(os.environ.get("RENDER_LEAD_MINUTES", "45"))
        # A quiz is rejected (409) if any of its answers was used within this many days.
        self.repeat_days = int(os.environ.get("REPEAT_DAYS", "365"))
        self._music_dir = os.environ.get("MUSIC_DIR", "")

    @property
    def videos_dir(self) -> Path:
        return self.data_dir / "videos"

    @property
    def music_dir(self) -> Path:
        return Path(self._music_dir) if self._music_dir else self.data_dir / "music"

    @property
    def instagram_enabled(self) -> bool:
        return bool(self.instagram_app_id and self.instagram_app_secret)

    @property
    def youtube_enabled(self) -> bool:
        return bool(self.youtube_client_id and self.youtube_client_secret)


settings = Settings()
