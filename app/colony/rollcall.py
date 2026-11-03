"""Roll call: every COLONY_ROLLCALL_DAYS, a post of everyone living on Farside in their full look,
each tagged where they stand so they're told and can find themselves (docs/COLONY_PLAN.md).

One image for up to 9 settlers, a carousel (title card + up to 9 grids of 9) for more, the newest
first. Instagram allows 20 tags an image and 10 images a post, so a roll call holds 81; the rest
come round next time. A slide whose tags are refused posts untagged, and its people are named in
a comment instead. Blocked and opted-out people are never shown or tagged."""
from __future__ import annotations

import logging
import secrets
from datetime import date, datetime, timedelta, timezone

from .. import channels, notify, store
from ..config import settings
from ..publish import instagram
from ..render.colony import rollcall as art
from . import state

log = logging.getLogger(__name__)
MAX_PEOPLE = art.PER_SLIDE * 9
MIN_PEOPLE = 3


def who(s: dict) -> list[dict]:
    from ..privacy import opted_out

    gone = opted_out() | set(s["blocked"])
    people = [{"handle": st["handle"], "look": st.get("look") or {}, "rank": st.get("rank"), "joined": st.get("joined", "")}
              for st in s["settlers"].values() if st["handle"].lower() not in gone]
    people.sort(key=lambda p: (p["joined"], p["handle"]), reverse=True)  # newest first
    return people[:MAX_PEOPLE]


def make(s: dict, day: date) -> tuple[list, list[list[dict]], int]:
    """(slides as PIL images, tags per slide, how many settlers in all)."""
    people = who(s)
    total = len(s["settlers"])
    pages = [people[i:i + art.PER_SLIDE] for i in range(0, len(people), art.PER_SLIDE)]
    label = datetime(day.year, day.month, day.day).strftime("%A %-d %B").upper()
    slides, tags = [], []
    if len(pages) > 1:
        slides.append(art.cover(max(total, s["followers"]), len(pages), label))
        tags.append([])
    for i, page in enumerate(pages):
        img, spots = art.grid(page, i + 1, len(pages))
        slides.append(img)
        tags.append(spots)
    return slides, tags, len(people)


def caption(shown: int, total: int) -> str:
    more = f" (the newest {shown}; everyone else comes round next time)" if total > shown else ""
    return (f"Roll call 🪐 {total:,} settlers live on Farside{more}. You're tagged where you stand: find yourself, "
            "and tell us in the comments what you'd change. Not here yet? Comment on today's episode to move in."
            "\n\n#farside #pixelart #story")


def _save(slides) -> list[str]:
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    urls = []
    for img in slides:
        name = f"farside-rollcall-{secrets.token_urlsafe(8)}.jpg"
        img.convert("RGB").save(settings.videos_dir / name, quality=92)
        urls.append(f"{settings.public_base_url}/media/{name}")
    return urls


def run(dry_run: bool = False, day: date | None = None) -> dict:
    """Make the roll call; post it unless `dry_run` (then only the Discord preview)."""
    from . import jobs

    day = day or datetime.now(settings.tz).date()
    s = state.load()
    slides, tags, shown = make(s, day)
    if shown < MIN_PEOPLE:
        return {"posted": False, "why": f"only {shown} settlers so far (a roll call needs {MIN_PEOPLE})"}
    urls = _save(slides)
    out = {"slides": len(urls), "shown": shown, "tagged": sum(len(t) for t in tags), "urls": urls}
    if dry_run:
        notify.send(f":busts_in_silhouette: **Farside roll call preview**: {shown} settlers on {len(urls)} "
                    f"slide{'s' if len(urls) > 1 else ''}, {out['tagged']} tags. Not posted.\n" + "\n".join(urls[:3]))
        return {**out, "posted": False}
    if why := jobs.can_publish():
        raise RuntimeError(why)
    with channels.use(channels.COLONY):
        res = instagram.publish_tagged(list(zip(urls, tags)), caption(shown, len(s["settlers"])))
        missed = [t["username"] for u, ts in zip(urls, tags) if u in res.get("untagged", []) for t in ts]
        if missed:  # name them instead, so they still hear about it
            try:
                instagram.comment(res["media_id"], "Couldn't tag everyone, so: " + " ".join("@" + m for m in missed)[:2000])
            except Exception as e:
                log.warning("roll call comment: %s", e)
    jobs._set_channel(last_rollcall=day.isoformat(), last_rollcall_media=res.get("media_id"))
    notify.send(f":busts_in_silhouette: **Farside roll call posted**: {shown} settlers, {out['tagged'] - len(missed)} tagged"
                + (f", {len(missed)} named in a comment instead" if missed else "") + f"\n{res.get('url', '')}")
    return {**out, "posted": True, "result": res, "untagged": missed}


def due(now: datetime | None = None) -> bool:
    from . import jobs

    now = now or datetime.now(timezone.utc)
    ch = jobs.channel_state()
    if not ch.get("started") or settings.colony_rollcall_days <= 0:
        return False
    local = now.astimezone(settings.tz)
    h, m = (int(x) for x in settings.colony_rollcall_time.split(":"))
    if (local.hour, local.minute) < (h, m):
        return False
    last = ch.get("last_rollcall") or ch.get("start_date")
    return (local.date() - date.fromisoformat(last)).days >= settings.colony_rollcall_days


def tick(now: datetime | None = None) -> None:
    if not due(now):
        return
    try:
        res = run()
        if not res.get("posted"):  # too few people yet: try again next time it's due
            from . import jobs

            jobs._set_channel(last_rollcall=(now or datetime.now(timezone.utc)).astimezone(settings.tz).date().isoformat())
    except Exception as e:
        log.exception("farside roll call failed")
        from . import jobs

        jobs._set_channel(last_rollcall=(now or datetime.now(timezone.utc)).astimezone(settings.tz).date().isoformat())
        notify.send(f":warning: **Farside roll call** failed: {e}\nTry again with POST /colony/rollcall")
