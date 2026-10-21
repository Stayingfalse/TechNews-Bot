from __future__ import annotations

import os
from pathlib import Path


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

        self.tiktok_client_key = os.environ.get("TIKTOK_CLIENT_KEY", "")
        self.tiktok_client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "")

        self.instagram_app_id = os.environ.get("INSTAGRAM_APP_ID", "")
        self.instagram_app_secret = os.environ.get("INSTAGRAM_APP_SECRET", "")
        # notify = send the video to Discord for manual posting with a trending sound (default)
        # auto   = publish the Reel via the API with the built-in audio
        self.instagram_mode = os.environ.get("INSTAGRAM_MODE", "notify")
        self.graph_version = os.environ.get("GRAPH_API_VERSION", "v23.0")

        self.discord_webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
        self.keep_videos_days = int(os.environ.get("KEEP_VIDEOS_DAYS", "14"))

    @property
    def videos_dir(self) -> Path:
        return self.data_dir / "videos"

    @property
    def tiktok_enabled(self) -> bool:
        return bool(self.tiktok_client_key and self.tiktok_client_secret)

    @property
    def instagram_enabled(self) -> bool:
        return bool(self.instagram_app_id and self.instagram_app_secret)


settings = Settings()
