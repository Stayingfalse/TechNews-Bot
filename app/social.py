"""Instagram extras beyond the daily Reel: a story when each quiz posts, and a weekly carousel.

Story: today's title card with "new quiz out now", posted right after the Reel (INSTAGRAM_STORIES).
Carousel: once a week (CAROUSEL_DAY at CAROUSEL_TIME, Monday 20:00), the week's most-viewed quiz again as swipeable
slides, clue then answer (INSTAGRAM_CAROUSELS). Both are image posts, so they cost no rendering time.
"""
from __future__ import annotations

import logging
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import notify, store
from .config import settings
from .publish import instagram, youtube
from .render.slides import carousel_images, story_image
from .spec import QuizSpec

log = logging.getLogger(__name__)

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _url(name: str) -> str:
    return f"{settings.public_base_url}/media/{name}"


def post_story(job: dict) -> dict:
    """Post the 'new quiz' story for a quiz that's on Instagram. Recorded on the job as `story`."""
    spec = QuizSpec.model_validate(job["spec"])
    name = f"{spec.id}-story-{secrets.token_urlsafe(8)}.jpg"
    story_image(spec, settings.videos_dir / name, settings.brand_handle)
    try:
        res = {"ok": True, **instagram.publish_story(_url(name)), "at": store.now_iso()}
    except Exception as e:
        log.warning("story for %s failed: %s", job["id"], e)
        res = {"ok": False, "error": str(e)[:300], "at": store.now_iso()}
    job["story"] = res
    store.save_job(job)
    return res


def after_publish(job: dict) -> None:
    if (settings.instagram_stories and not job.get("dry_run") and not job["id"].startswith("test-")
            and job.get("results", {}).get("instagram", {}).get("ok") and not (job.get("story") or {}).get("ok")):
        post_story(job)


def _views(job_id: str, data: dict) -> int:
    return sum((rec.get("latest") or {}).get("views") or 0 for rec in data.get(job_id, {}).values())


def carousel_pick(days: int = 7) -> dict | None:
    """The most-viewed quiz of the last `days` days that hasn't had a carousel yet."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    data = store._read("metrics.json", {})
    jobs = [j for j in store.list_jobs(200)
            if j.get("status") == "done" and not j.get("dry_run") and not j["id"].startswith("test-")
            and (j.get("published_at") or "") >= since and not (j.get("carousel") or {}).get("ok")]
    return max(jobs, key=lambda j: (_views(j["id"], data), j["published_at"]), default=None)


def post_carousel(job: dict, dry_run: bool = False) -> dict:
    """Make (and unless dry_run, post) the carousel for a quiz. Returns the slide URLs and the result."""
    spec = QuizSpec.model_validate(job["spec"])
    stem = f"{spec.id}-carousel-{secrets.token_urlsafe(8)}"
    urls = [_url(p.name) for p in carousel_images(spec, settings.videos_dir, stem, settings.brand_handle)]
    if dry_run:
        return {"job_id": job["id"], "slides": urls, "posted": False}
    caption = ("Missed this one? Swipe to play 👉 the answer is on the slide after each clue.\n"
               "How many did you get? 👇\n\n" + " ".join(spec.hashtags))
    try:
        res = {"ok": True, **instagram.publish_carousel(urls, caption), "at": store.now_iso()}
    except Exception as e:
        log.warning("carousel for %s failed: %s", job["id"], e)
        res = {"ok": False, "error": str(e)[:300], "at": store.now_iso()}
    job["carousel"] = res
    store.save_job(job)
    notify.send(f"**Weekly carousel** of `{job['id']}`: " + (f"posted {res.get('url', '')}" if res["ok"] else f"failed: {res['error']}"))
    return {"job_id": job["id"], "slides": urls, "posted": res["ok"], **res}


def weekly_tick(now_local: datetime) -> None:
    """Called by the scheduler: post this week's carousel once its day and time have come."""
    if not settings.instagram_carousels or "instagram" not in settings.platforms:
        return
    if DAYS[now_local.weekday()] != settings.carousel_day or now_local.strftime("%H:%M") < settings.carousel_time:
        return
    week = now_local.strftime("%G-W%V")
    state = store._read("social.json", {})
    if state.get("carousel_week") == week:
        return
    state["carousel_week"] = week  # once a week, even if it fails (Discord says so)
    store._write("social.json", state)
    job = carousel_pick()
    if job:  # off the scheduler's thread: making and posting the slides takes a minute or two
        threading.Thread(target=post_carousel, args=(job,), daemon=True, name="carousel").start()


# ------------------------------------------------------------------ profile picture rotation

AVATAR_DIRS = (Path(__file__).resolve().parents[1] / "assets" / "avatars", settings.data_dir / "avatars")


def avatars() -> list[Path]:
    """The pictures in rotation, in a fixed order (repo ones first, then any added on the server)."""
    return [p for d in AVATAR_DIRS if d.exists() for p in sorted(d.glob("avatar-*.png"))]


def send_next_avatar() -> dict:
    """Send the next picture in the rotation to Discord, to upload on both platforms."""
    pics = avatars()
    if not pics:
        return {"sent": False, "reason": "no avatar-*.png files"}
    state = store._read("social.json", {})
    names = [p.name for p in pics]
    last = state.get("avatar")
    pick = pics[(names.index(last) + 1) % len(pics)] if last in names else pics[0]
    banner_note, banner = "", _banner_for(pick)
    if banner and "youtube" in settings.platforms and youtube.configured() and store.get_tokens("youtube"):
        try:  # the banner, unlike the picture, the bot can change itself
            youtube.set_banner(banner)
            banner_note = "\nThe matching **YouTube banner** is already up."
        except Exception as e:
            log.warning("banner update failed: %s", e)
            banner_note = f"\nThe matching YouTube banner couldn't be set ({str(e)[:150]}); it's `{banner.name}` in assets/avatars."
    notify.send(
        f"**Time for a fresh profile picture** ({names.index(pick.name) + 1} of {len(pics)} in the rotation). "
        "Neither platform lets the bot change it, so here it is to upload:\n"
        "• **Instagram:** profile → Edit profile → Edit picture\n"
        "• **YouTube:** YouTube Studio → Customisation → Branding → Picture → Change"
        f"{banner_note}\nNext one in {settings.avatar_every_weeks} weeks.",
        attach=pick)
    state.update(avatar=pick.name, avatar_at=store.now_iso(), banner_ok=bool(banner_note and "already up" in banner_note))
    store._write("social.json", state)
    return {"sent": True, "picture": pick.name, "banner": banner.name if banner else None,
            "banner_set": state["banner_ok"]}


def _banner_for(avatar: Path) -> Path | None:
    """banner-<name>.jpg (or .png) next to avatar-<name>.png."""
    stem = avatar.stem.removeprefix("avatar-")
    return next((p for p in (avatar.with_name(f"banner-{stem}.jpg"), avatar.with_name(f"banner-{stem}.png")) if p.exists()), None)


def avatar_tick(now_local: datetime) -> None:
    """Monday from 10:00, every AVATAR_EVERY_WEEKS weeks: hand over the next profile picture."""
    if settings.avatar_every_weeks <= 0 or now_local.weekday() != 0 or now_local.strftime("%H:%M") < "10:00":
        return
    last = store._read("social.json", {}).get("avatar_at")
    if last and datetime.now(timezone.utc) - datetime.fromisoformat(last) < timedelta(weeks=settings.avatar_every_weeks, hours=-12):
        return
    send_next_avatar()
