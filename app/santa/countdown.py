"""raosanta.uk's midnight countdown to Christmas: a second, short video every day at
SANTA_COUNTDOWN_TIME (00:00 UTC), in the quiet hours the 22-hour pattern never uses.

Each one is made here, not in the season plan: the raosanta.uk advent calendar (render/santa/
advent.py), filled up to the day. A wide shot of the board, a pan past two earlier doors (picked by
the date), a zoom into the day's door, which opens and its treasure flies out with the sleeps left
and a line that goes with it. Every day differs: the board, the pan, the treasure, the line, the
carol and the end card's line. Before December door 1 rattles but stays shut; Christmas Day opens
the big door 25.
Music only, no voice-over (no credits). Booked SANTA_BOOK_AHEAD_DAYS ahead, like the plan, through
Christmas Day, made 45 minutes before and posted like every other promo (jobs.py), so a clash with
another channel is checked again before it's made. SANTA_COUNTDOWN=off switches it off.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from ..config import settings
from . import jobs
from .spec import HASHTAGS, PromoSpec

# December: each door's line goes with its treasure (advent.TREASURES). Every one is true; the
# facts are the well-documented ones the quizzes use too. No figures: the countdown never waits on
# the site.
DOOR_LINES = {
    1: "A star to start. Advent calendars began in Germany in the 1800s.",
    2: "Glass baubles were first made in Lauscha, Germany.",
    3: "A candy cane. Legend says they began in Cologne in the 1600s.",
    4: "Build a snowman, then pick up a wishlist: raosanta.uk",
    5: "Gifts on raosanta.uk come from real wishlists: no guessing sizes.",
    6: "Victorian postmen wore red coats and were nicknamed robins.",
    7: "Gingerbread figures are linked to the court of Elizabeth I.",
    8: "Jingle Bells by James Lord Pierpont was published in 1857.",
    9: "Holly and ivy have decked British homes in winter for centuries.",
    10: "Every gift on raosanta.uk comes from the person's own wishlist.",
    11: "Legend says Saint Nicholas's gold coins landed in stockings by the fire.",
    12: "Trees indoors are usually traced to 16th-century Germany.",
    13: "A Christingle: an orange, a candle and a red ribbon.",
    14: "Both male and female reindeer grow antlers.",
    15: "Christmas crackers were invented by London sweet-maker Tom Smith.",
    16: "Leave a mince pie out for Santa. And a carrot for the reindeer.",
    17: "Wrapped up warm? Pick up a wishlist tonight: raosanta.uk",
    18: "Got a gift? Say thanks with a postcard on raosanta.uk.",
    19: "Christmas puddings are traditionally made on Stir-up Sunday.",
    20: "Wreaths on the door: holly, ivy and a big red bow.",
    21: "The shortest day of the year falls around 21 December.",
    22: "Snowflakes nearly always have six sides.",
    23: "Amazon delivers, so no addresses are shared: Random Acts of Santa.",
    24: "Christmas Eve! In Iceland, the last of the 13 Yule Lads arrives tonight.",
    25: "Thank you to every Santa who made someone's Christmas this year.",
}
ENDS = ["Random Acts, not Secret Santa", "Give a gift, any day this season", "Pick up a wishlist tonight",
        "Free at raosanta.uk", "Someone's wishlist is waiting"]
CAROLS = ["carol:jingle-bells", "carol:deck-the-halls", "carol:we-wish-you", "carol:jingle-bells"]

# Before December: door 1 rattles but stays shut
NOVEMBER_LINES = {
    26: "Five more sleeps till the first door. Gifting opens tomorrow.",
    27: "No peeking! Gifting is open: pick up a wishlist on raosanta.uk.",
    28: "Patience... Pick up a random wishlist while you wait.",
    29: "Two more sleeps till door 1. Is your wishlist ready?",
    30: "Door 1 opens tomorrow. Gifts are already on their way.",
}
def christmas(year: int) -> date:
    return date(year, 12, 25)


def _when(day: date) -> datetime:
    h, m = (int(x) for x in settings.santa_countdown_time.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=timezone.utc)


def spec_for(day: date) -> PromoSpec:
    """The countdown video for `day` (a UTC date up to Christmas Day)."""
    n = (christmas(day.year) - day).days
    line = DOOR_LINES[day.day] if day.month == 12 else NOVEMBER_LINES.get(day.day, "The first door opens on 1 December.")
    sleeps = "It's Christmas!" if n == 0 else f"{n} sleep{'s' if n != 1 else ''} until Christmas."
    door = f"Door {day.day}" if day.month == 12 else "The advent calendar"
    return PromoSpec.model_validate({
        "id": f"countdown-{day.isoformat()}", "format": "countdown",
        "segments": [{"type": "countdown", "date": day.isoformat(), "days": n, "line": line},
                     {"type": "end", "line": "Merry Christmas" if n == 0 else ENDS[n % len(ENDS)], "seconds": 2.6}],
        "music": CAROLS[n % len(CAROLS)],
        "title": f"{sleeps} {door} | raosanta.uk"[:90],
        "caption": f"{sleeps} {door}: {line}",
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
