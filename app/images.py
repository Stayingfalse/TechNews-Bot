"""Download the spec's images before rendering. Failures are reported, never fatal."""
from __future__ import annotations

import io
import logging
from pathlib import Path

import httpx
from PIL import Image

from .spec import StorySpec

log = logging.getLogger(__name__)

MAX_BYTES = 20 * 1024 * 1024
MAX_SIDE = 2000
MIN_SIDE = 400
# Wikimedia and many newsrooms reject requests without a descriptive User-Agent.
HEADERS = {
    "User-Agent": "TechNews-Bot/1.0 (+https://cezz.co.uk; daily tech news shorts)",
    "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*;q=0.5",
}


def fetch_images(spec: StorySpec, dest: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Returns ({image_id: local_path}, {image_id: error})."""
    dest.mkdir(parents=True, exist_ok=True)
    ok: dict[str, str] = {}
    errors: dict[str, str] = {}
    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        for ref in spec.images:
            try:
                with client.stream("GET", ref.url) as r:
                    r.raise_for_status()
                    buf = bytearray()
                    for chunk in r.iter_bytes():
                        buf += chunk
                        if len(buf) > MAX_BYTES:
                            raise ValueError("image larger than 20MB")
                img = Image.open(io.BytesIO(bytes(buf)))
                img.load()
                if min(img.size) < MIN_SIDE:
                    raise ValueError(f"image too small ({img.width}x{img.height})")
                img = img.convert("RGB")
                img.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
                path = dest / f"{ref.id}.jpg"
                img.save(path, quality=92)
                ok[ref.id] = str(path)
            except Exception as e:
                log.warning("image %s (%s) failed: %s", ref.id, ref.url, e)
                errors[ref.id] = f"{type(e).__name__}: {e}"[:200]
    return ok, errors
