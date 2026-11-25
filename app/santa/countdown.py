"""raosanta.uk's midnight countdown to Christmas: a second, short video every day at
SANTA_COUNTDOWN_TIME (00:00 UTC), in the quiet hours the 22-hour pattern never uses.

Each one is made here, not in the season plan: an advent-calendar door with the date on it swings
open on the sleeps left until Christmas Day, then the day's line, then the end card. Every day
differs: the number and date, the door's colour, the carol, the line and the end card's line (they
take turns at different lengths, so no two days match). Christmas Day's opens on "It's Christmas!".
Music only, no voice-over (no credits). Booked SANTA_BOOK_AHEAD_DAYS ahead, like the plan, through
Christmas Day, made 45 minutes before and posted like every other promo (jobs.py), so a clash with
another channel is checked again before it's made. SANTA_COUNTDOWN=off switches it off.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from ..config import settings
from . import jobs
from .spec import HASHTAGS, PromoSpec

# A different line each day (picked by the sleeps left). No figures: the countdown never waits on
# the site. Every one is true; facts are the well-documented ones the quizzes use too.
LINES = [
    "Thank you to every Santa who made someone's Christmas this year.",  # Christmas Day
    "Leave out a mince pie for Santa. And a carrot for the reindeer.",
    "Mark your gift as Gifted, so they know one's on its way.",
    "Still to pick up a wishlist? There's time: raosanta.uk",
    "Brussels sprouts belong to the cabbage family.",
    "Krampus, Santa's scary companion, comes from Alpine folklore.",
    "Every gift on raosanta.uk comes from the person's own wishlist.",
    "In France, Father Christmas is *Père Noël*.",
    "A Christingle is an orange with a candle and a red ribbon.",
    "Organisers can make a Wall of Kindness from their group's thank-yous.",
    "The Twelve Days of Christmas gives 364 gifts in all.",
    "Bing Crosby's White Christmas is listed as the best-selling single ever.",
    "A late gift still counts: gifting stays open into January.",
    "Saint Nicholas, who inspired Santa, was a 4th-century bishop.",
    "Stir-up Sunday is when Christmas puddings are traditionally made.",
    "Snowflakes almost always have six sides.",
    "No draw and no fixed pairs: gift as many or as few as you like.",
    "In Iceland, 13 Yule Lads visit in the nights before Christmas.",
    "Got a gift? Say thanks with a postcard on raosanta.uk.",
    "Rudolph first appeared in a 1939 department store booklet.",
    "Workplaces, Discord servers, friends and family: all welcome.",
    "A poinsettia's red 'petals' are really leaves.",
    "Mistletoe berries are white, and not for eating.",
    "Your Santa stays anonymous. Your thank-you shows a festive name.",
    "A Christmas Carol was first published in December 1843.",
    "Pick up a random wishlist tonight: raosanta.uk",
    "Norway has sent London's Trafalgar Square tree every year since 1947.",
    "Christmas trees indoors are usually traced to 16th-century Germany.",
    "The fewest-gifted wishlists are handed out first, so nobody's left out.",
    "Amazon wishlists deliver without showing anyone your address.",
    "The countdown starts now. Is your wishlist ready?",
]
ENDS = ["Random Acts, not Secret Santa", "Give a gift, any day this season", "Pick up a wishlist tonight",
        "Free at raosanta.uk", "Someone's wishlist is waiting"]
DOORS = ["post", "pine", "night"]
CAROLS = ["carol:jingle-bells", "carol:deck-the-halls", "carol:we-wish-you", "carol:jingle-bells"]


def christmas(year: int) -> date:
    return date(year, 12, 25)


def _when(day: date) -> datetime:
    h, m = (int(x) for x in settings.santa_countdown_time.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=timezone.utc)


def spec_for(day: date) -> PromoSpec:
    """The countdown video for `day` (a UTC date up to Christmas Day)."""
    n = (christmas(day.year if day.month == 12 else day.year) - day).days
    line = LINES[n % len(LINES)]
    plain = line.replace("*", "")
    sleeps = "It's Christmas!" if n == 0 else f"{n} sleep{'s' if n != 1 else ''} until Christmas."
    return PromoSpec.model_validate({
        "id": f"countdown-{day.isoformat()}", "format": "countdown",
        "segments": [{"type": "countdown", "days": n, "line": line, "door": "gold" if n == 0 else DOORS[n % len(DOORS)],
                      "label": str(day.day)},
                     {"type": "end", "line": "Merry Christmas" if n == 0 else ENDS[n % len(ENDS)], "seconds": 2.6}],
        "music": CAROLS[n % len(CAROLS)],
        "title": f"{sleeps} Christmas countdown | raosanta.uk"[:90],
        "caption": f"{sleeps} {plain}",
        "hashtags": list(HASHTAGS) + ["#christmascountdown", "#adventcalendar"],
    })


def sync(t: datetime | None = None) -> list[dict]:
    """Book the countdown's next few midnights (through Christmas Day) that aren't booked yet."""
    if not settings.santa_countdown:
        return []
    t = t or jobs.now()
    used = {j["spec"]["id"] for j in jobs.all_jobs() if j["status"] != "cancelled"}
    soonest = t + timedelta(minutes=settings.santa_render_lead_minutes + 10)
    horizon = t + timedelta(days=settings.santa_book_ahead_days)
    day, pairs = t.astimezone(timezone.utc).date(), []
    while _when(day) <= horizon:
        at = _when(day)
        if day.month in (11, 12) and day <= christmas(day.year) and at >= soonest:
            spec = spec_for(day)
            if spec.id not in used:
                pairs.append((spec, {"planned": at.isoformat(), "at": at.isoformat()}))
        day += timedelta(days=1)
    return jobs.book_into(pairs, "countdown")
