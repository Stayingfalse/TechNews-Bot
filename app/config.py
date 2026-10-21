from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

PLATFORMS = ("tiktok", "youtube", "instagram")


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
        # Where to post, comma-separated: any of tiktok, youtube, instagram.
        self.platforms = [p.strip().lower() for p in os.environ.get("PLATFORMS", "tiktok,youtube,instagram").split(",") if p.strip()]
        unknown = set(self.platforms) - set(PLATFORMS)
        if unknown:
            raise ValueError(f"PLATFORMS has unknown entries {sorted(unknown)}; use any of {PLATFORMS}")

        # Scheduled quizzes go out at POST_TIME (24h, local to TIMEZONE) on their day.
        self.tz = ZoneInfo(os.environ.get("TIMEZONE", "Europe/London"))
        self.post_time = os.environ.get("POST_TIME", "12:00")
        h, m = (int(x) for x in self.post_time.split(":"))
        if not (0 <= h < 24 and 0 <= m < 60):
            raise ValueError("POST_TIME must be HH:MM")

        self.tiktok_client_key = os.environ.get("TIKTOK_CLIENT_KEY", "")
        self.tiktok_client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "")
        # draft  = upload to the TikTok inbox; you tap post (works without TikTok's app audit)
        # direct = post straight to the profile (needs the video.publish scope; until TikTok audits
        #          the app, direct posts are forced to private / SELF_ONLY)
        self.tiktok_mode = os.environ.get("TIKTOK_MODE", "draft")
        self.tiktok_privacy = os.environ.get("TIKTOK_PRIVACY", "PUBLIC_TO_EVERYONE")

        self.instagram_app_id = os.environ.get("INSTAGRAM_APP_ID", "")
        self.instagram_app_secret = os.environ.get("INSTAGRAM_APP_SECRET", "")
        self.graph_version = os.environ.get("GRAPH_API_VERSION", "v23.0")

        self.youtube_client_id = os.environ.get("YOUTUBE_CLIENT_ID", "")
        self.youtube_client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
        # public | unlisted | private. Uploads from an unaudited Google API project are locked to private.
        self.youtube_privacy = os.environ.get("YOUTUBE_PRIVACY", "public")

        self.discord_webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
        self.keep_videos_days = int(os.environ.get("KEEP_VIDEOS_DAYS", "14"))
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
    def tiktok_enabled(self) -> bool:
        return bool(self.tiktok_client_key and self.tiktok_client_secret)

    @property
    def instagram_enabled(self) -> bool:
        return bool(self.instagram_app_id and self.instagram_app_secret)

    @property
    def youtube_enabled(self) -> bool:
        return bool(self.youtube_client_id and self.youtube_client_secret)


settings = Settings()
