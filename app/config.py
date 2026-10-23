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

        # Instagram extras: a "new quiz out now" story after each Reel, and a weekly carousel of the
        # week's most-viewed quiz on CAROUSEL_DAY (mon..sun) at CAROUSEL_TIME (local).
        self.instagram_stories = _bool("INSTAGRAM_STORIES", False)
        self.instagram_carousels = _bool("INSTAGRAM_CAROUSELS", False)
        self.carousel_day = os.environ.get("CAROUSEL_DAY", "sun").strip().lower()[:3]
        self.carousel_time = os.environ.get("CAROUSEL_TIME", "18:00")

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
