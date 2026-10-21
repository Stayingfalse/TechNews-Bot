"""Platform publishers. Each module has configured(), publish(video, spec, job), the OAuth helpers
authorize_url(state) / exchange_code(code), and refresh_if_needed()."""
from __future__ import annotations

from ..config import settings
from . import instagram, tiktok, youtube

PUBLISHERS = {"tiktok": tiktok, "youtube": youtube, "instagram": instagram}
LABELS = {"tiktok": "TikTok", "youtube": "YouTube", "instagram": "Instagram"}


def refreshers():
    """Token refreshers for the platforms in use."""
    return [(name, PUBLISHERS[name].refresh_if_needed) for name in settings.platforms]
