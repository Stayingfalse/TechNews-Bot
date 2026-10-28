"""Bet replies: what the bot answers under each bet, sent through a paced queue.

Replies are queued as bets are seen (every RACING_POLL_MINUTES) and sent RACING_REPLY_GAP seconds
apart, at most RACING_REPLY_PER_HOUR an hour. Every kind of reply has a few wordings, picked by the
comment id, because many identical replies look like spam. If Instagram refuses ("action blocked",
rate limits), the queue pauses for an hour and Discord hears about it. Bets never depend on replies.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from .. import notify
from ..config import settings
from . import ledger
from .bets import car_name

log = logging.getLogger(__name__)
PAUSE = timedelta(hours=1)
BLOCKED = ("action is blocked", "spam", "rate limit", "too many", "(#4)", "(#17)", "(#32)", "(#613)", "368")

TEMPLATES = {
    "taken": ["✅ §{stake:,} on {car} at {odds}. §{left:,} left. Every bet and balance: {domain}",
              "Bet in: §{stake:,} on {car} ({odds}). Balance left: §{left:,}. {domain}",
              "Got it: {car}, §{stake:,} at {odds}. You've §{left:,} left. Bets & balances: {domain}"],
    "cut": ["Only §{stake:,} left, so it's §{stake:,} on {car} at {odds}. Balance: §0. {domain}",
            "You had §{stake:,} left, so that's all on {car} at {odds}. Balance: §0. {domain}"],
    "broke": ["No § left for race {no}. Sunday's bonus: §100 plus §50 for each video you comment on. {domain}",
              "You're out of § for race {no}. The Sunday bonus tops you up: §100 + §50 per video you comment on."],
    "help": ["Didn't catch that: comment a car and a stake, like 4 250 (= §250 on 4 BLUE STREAK).",
             "To bet, comment a car number and a stake, e.g. 4 250. One bet per comment."],
    "closed": ["Betting on race {no} has closed. Today's video takes bets on race {next}.",
               "Race {no} is closed now: bet on race {next} under today's video."],
}
WELCOME = "Welcome! You start with §1,000. "


def text(kind: str, comment_id: str, **values) -> str:
    opts = TEMPLATES[kind]
    pick = int(hashlib.sha256(comment_id.encode()).hexdigest(), 16) % len(opts)
    return opts[pick].format(domain=settings.racing_domain, **values)


def for_bet(row: dict, race: dict) -> tuple[str, str] | None:
    """(kind, text) to answer one comment of an open race (a row of ledger.provisional), or None."""
    c, b = row["comment"], row["bet"]
    if not b:
        from .bets import looks_like_bet

        return ("help", text("help", c["id"])) if looks_like_bet(c["text"]) else None
    car = f"{b['car']} {car_name(b['car'])}"
    odds = race["odds"][b["car"] - 1]
    if row["stake"] < 1:
        return "broke", text("broke", c["id"], no=race["no"])
    kind = "cut" if row["cut"] else "taken"
    body = text(kind, c["id"], stake=row["stake"], car=car, odds=odds, left=row["left"])
    return kind, (WELCOME + body if row["new"] else body)


# ------------------------------------------------------------------ the queue


def queue() -> dict:
    return ledger._read("replies.json", {"items": [], "sent": [], "paused_until": None})


def _save(q: dict) -> None:
    q["sent"] = q["sent"][-2000:]
    q["items"] = q["items"][-2000:]
    ledger._write("replies.json", q)


def known() -> set[str]:
    q = queue()
    return {i["comment_id"] for i in q["items"]} | {i["comment_id"] for i in q["sent"]}


def add(items: list[dict]) -> int:
    """Queue replies ({comment_id, platform, kind, text, race, pid}); ones already queued or sent are skipped."""
    with ledger._lock:
        q = queue()
        seen = {i["comment_id"] for i in q["items"]} | {i["comment_id"] for i in q["sent"]}
        new = [{**i, "queued_at": ledger.now_iso()} for i in items if i["comment_id"] not in seen]
        q["items"] += new
        _save(q)
    return len(new)


def send_due(now: datetime | None = None) -> int:
    """Send what the pace allows right now. Returns how many went out."""
    from ..publish import instagram

    now = now or datetime.now(timezone.utc)
    sent = 0
    with ledger._lock:
        q = queue()
        if q.get("paused_until") and datetime.fromisoformat(q["paused_until"]) > now:
            return 0
        hour_ago = (now - timedelta(hours=1)).isoformat()
        last = max((i["sent_at"] for i in q["sent"] if i.get("sent_at")), default=None)
        in_hour = sum(1 for i in q["sent"] if (i.get("sent_at") or "") > hour_ago)
        while q["items"] and in_hour < settings.racing_reply_per_hour:
            if last and (now - datetime.fromisoformat(last)).total_seconds() < settings.racing_reply_gap:
                break
            item = q["items"].pop(0)
            try:
                if item.get("platform", "instagram") == "instagram":
                    item["reply_id"] = instagram.reply(item["comment_id"], item["text"])
                item["sent_at"] = now.isoformat()
                q["sent"].append(item)
                sent += 1
                in_hour += 1
                last = item["sent_at"]
            except Exception as e:
                err = str(e)
                if any(k in err.lower() for k in BLOCKED):
                    q["items"].insert(0, item)
                    q["paused_until"] = (now + PAUSE).isoformat()
                    notify.send(f":no_entry: **Racing replies paused for an hour**: Instagram refused a reply ({err[:200]}). "
                                f"{len(q['items'])} waiting. Consider lowering RACING_REPLY_PER_HOUR.")
                    break
                item.update(error=err[:300], sent_at=None, failed_at=now.isoformat())
                q["sent"].append(item)  # a deleted comment can't be answered; don't retry it forever
                log.warning("racing reply to %s failed: %s", item["comment_id"], err)
            break  # one per call: the loop runs every few seconds, which spaces them out
        _save(q)
    return sent
