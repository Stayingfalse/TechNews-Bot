"""Players, balances and the ledger.

Every change to anyone's money is one line in ledger.jsonl (start, bet, payout, bonus), never
edited, so any balance can be rebuilt and any dispute checked (`rebuild`). players.json keeps each
player's name and current balance for quick reads; it always equals the ledger's sum.

A player is a platform account: "instagram:<id>" (the username when the platform gives no id).
Someone on two platforms is two players: the accounts can't be linked.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import settings

START_BALANCE = 1000
_lock = threading.RLock()


def _dir() -> Path:
    d = settings.data_dir / "racing"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read(name: str, default):
    p = _dir() / name
    return json.loads(p.read_text()) if p.exists() else default


def _write(name: str, data) -> None:
    p = _dir() / name
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, p)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pid_for(platform: str, uid: str, user: str) -> str:
    return f"{platform}:{uid or user.lstrip('@').lower()}"


def players() -> dict[str, dict]:
    return _read("players.json", {})


def player(pid: str) -> dict | None:
    return players().get(pid)


def find(name: str) -> dict | None:
    """A named player by exact handle (case-insensitive, @ optional)."""
    key = name.strip().lstrip("@").lower()
    return next((p for p in players().values() if (p.get("name") or "").lower() == key), None)


def balance(pid: str) -> int:
    return (player(pid) or {}).get("balance", 0)


def entries(pid: str | None = None) -> list[dict]:
    p = _dir() / "ledger.jsonl"
    if not p.exists():
        return []
    out = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    return [e for e in out if pid is None or e["pid"] == pid]


def _post(entry: dict, ps: dict) -> None:
    """Append one ledger line and apply it to the player (caller holds the lock and saves players)."""
    entry = {"at": now_iso(), **entry}
    with open(_dir() / "ledger.jsonl", "a") as fh:
        fh.write(json.dumps(entry, separators=(",", ":")) + "\n")
    ps[entry["pid"]]["balance"] = ps[entry["pid"]].get("balance", 0) + entry["amount"]


def ensure(ps: dict, platform: str, uid: str, user: str, at: str | None = None) -> tuple[dict, bool]:
    """The player for a commenter, created with START_BALANCE the first time we see them."""
    pid = pid_for(platform, uid, user)
    p = ps.get(pid)
    if p is None:
        p = ps[pid] = {"pid": pid, "platform": platform, "uid": uid, "name": user.lstrip("@"), "balance": 0,
                       "first_seen": at or now_iso(), "last_active": at or now_iso(), "bets": 0, "wins": 0}
        _post({"pid": pid, "kind": "start", "amount": START_BALANCE}, ps)
        return p, True
    if user:  # people rename themselves; an anonymised player who comes back gets their name back
        p["name"] = user.lstrip("@")
        p["anonymised"] = False
    if at and at > p.get("last_active", ""):
        p["last_active"] = at
    return p, False


def stake_for(want, bal: int) -> int:
    """What a bet actually stakes: the default, everything, or the ask cut to the balance."""
    from .bets import DEFAULT_STAKE

    if want == "all":
        return max(bal, 0)
    return max(0, min(DEFAULT_STAKE if want is None else int(want), bal))


def settle(race: dict, comments: list[dict], winner: int | None, odds: list[str]) -> dict:
    """Take every bet in posting order (each new player starts with START_BALANCE), then pay the
    winners. `comments` are this race's comments with {id, user, uid, text, at, platform}, already
    without our own and opted-out accounts. Returns what was taken; the race record gets the bets."""
    from . import bets as parser
    from .sim import payout

    with _lock:
        if any(e.get("race") == race["no"] and e["kind"] in ("bet", "payout") for e in entries()):
            # settled already (a restart between settling and saving the race): taking the bets again
            # would charge and pay everyone twice
            raise RuntimeError(f"race {race['no']} is already settled in the ledger; check it by hand")
        ps = players()
        taken, commenters, new = [], set(), 0
        for c in sorted(comments, key=lambda c: c["at"]):
            p, fresh = ensure(ps, c.get("platform", "instagram"), c.get("uid", ""), c["user"], c["at"])
            new += fresh
            commenters.add(p["pid"])
            b = parser.parse(c["text"])
            if not b:
                continue
            stake = stake_for(b["stake"], p["balance"])
            row = {"pid": p["pid"], "name": p["name"], "car": b["car"], "asked": b["stake"], "stake": stake,
                   "odds": odds[b["car"] - 1], "comment_id": c["id"], "at": c["at"]}
            if stake < 1:
                row["refused"] = "no balance"
                taken.append(row)
                continue
            _post({"pid": p["pid"], "kind": "bet", "amount": -stake, "race": race["no"], "car": b["car"],
                   "odds": row["odds"], "comment_id": c["id"]}, ps)
            p["bets"] = p.get("bets", 0) + 1
            p["last_bet"] = c["at"]
            taken.append(row)
        for row in taken:
            if row.get("refused") or winner is None:
                row["returned"] = 0
                continue
            won = row["car"] == winner
            row["returned"] = payout(row["stake"], row["odds"]) if won else 0
            if won:
                _post({"pid": row["pid"], "kind": "payout", "amount": row["returned"], "race": race["no"],
                       "car": row["car"], "odds": row["odds"], "comment_id": row["comment_id"]}, ps)
                ps[row["pid"]]["wins"] = ps[row["pid"]].get("wins", 0) + 1
        _write("players.json", ps)
    return {"bets": taken, "commenters": sorted(commenters), "new_players": new}


def provisional(comments: list[dict]) -> list[dict]:
    """The bets in an open race so far, as settlement would take them now, without writing
    anything: each with the balance left after it. What the bet replies say."""
    from . import bets as parser

    ps = players()
    left: dict[str, int] = {}
    out = []
    for c in sorted(comments, key=lambda c: c["at"]):
        pid = pid_for(c.get("platform", "instagram"), c.get("uid", ""), c["user"])
        bal = left.setdefault(pid, ps[pid]["balance"] if pid in ps else START_BALANCE)
        b = parser.parse(c["text"])
        row = {"comment": c, "pid": pid, "new": pid not in ps, "bet": b}
        if b:
            row["stake"] = stake_for(b["stake"], bal)
            row["cut"] = 0 < row["stake"] < int(b["stake"]) if b["stake"] not in (None, "all") else False
            left[pid] = bal - row["stake"]
            row["left"] = left[pid]
        out.append(row)
    return out


def weekly_bonus(week: str, activity: dict[str, int], doubled: bool = False) -> dict:
    """Pay every known player BONUS plus PER_VIDEO for each video they commented on this week.
    `activity` = pid → videos commented on. Once per `week` (an ISO week like "2026-W44")."""
    base, per = (200, 100) if doubled else (100, 50)
    with _lock:
        from ..privacy import opted_out

        out_names = opted_out()
        paid = _read("bonus_weeks.json", [])
        if week in paid:
            return {"week": week, "already": True}
        ps = players()
        total, n = 0, 0
        for pid, p in ps.items():
            if p.get("anonymised") or (p.get("name") or "").lower() in out_names:
                continue
            amount = base + per * activity.get(pid, 0)
            _post({"pid": pid, "kind": "bonus", "amount": amount, "week": week, "videos": activity.get(pid, 0)}, ps)
            total, n = total + amount, n + 1
        _write("players.json", ps)
        _write("bonus_weeks.json", paid + [week])
    return {"week": week, "players": n, "paid": total, "doubled": doubled}


def table(limit: int = 10, since: str | None = None) -> dict:
    """The league table: named players who have bet at least once, by balance; plus the week's
    biggest climber (balance change since `since`) and how many are bust."""
    from .bets import MIN_STAKE

    from ..privacy import opted_out

    out_names = opted_out()
    ps = [p for p in players().values() if p.get("bets") and (p.get("name") or "").lower() not in out_names]
    rows = sorted(ps, key=lambda p: (-p["balance"], p["first_seen"]))
    out = {"rows": [{"name": p.get("name") or anon_name(p["pid"]), "balance": p["balance"],
                     "pid": p["pid"]} for p in rows[:limit]],
           "players": len(ps), "bust": sum(p["balance"] < MIN_STAKE for p in ps)}
    if since:
        before: dict[str, int] = {}
        for e in entries():
            if e["at"] < since:
                before[e["pid"]] = before.get(e["pid"], 0) + e["amount"]
        gains = [(p["balance"] - before.get(p["pid"], START_BALANCE), p) for p in ps if p.get("name")]
        if gains:
            g, p = max(gains, key=lambda x: x[0])
            if g > 0:
                out["climber"] = {"name": p["name"], "gain": g}
    return out


def anon_name(pid: str) -> str:
    return f"punter #{int(hashlib.sha256(pid.encode()).hexdigest(), 16) % 10000:04d}"


def rebuild() -> dict[str, int]:
    """Balances recomputed from the ledger alone (for audits and tests)."""
    out: dict[str, int] = {}
    for e in entries():
        out[e["pid"]] = out.get(e["pid"], 0) + e["amount"]
    return out


# ------------------------------------------------------------------ privacy


def erase(user: str) -> int:
    """Delete a viewer's player record and every ledger line of theirs. Returns lines removed."""
    key = user.strip().lstrip("@").lower()
    with _lock:
        ps = players()
        gone = {pid for pid, p in ps.items() if (p.get("name") or "").lower() == key or pid.split(":", 1)[1] == key}
        for pid in gone:
            ps.pop(pid)
        lines = entries()
        keep = [e for e in lines if e["pid"] not in gone]
        with open(_dir() / "ledger.tmp", "w") as fh:
            fh.writelines(json.dumps(e, separators=(",", ":")) + "\n" for e in keep)
        os.replace(_dir() / "ledger.tmp", _dir() / "ledger.jsonl")
        _write("players.json", ps)
    from . import races

    races.scrub(gone)
    return len(lines) - len(keep)


def anonymise_idle(days: int = 90) -> int:
    """Players with no bet in `days` lose their name (their balance stays, as "punter #1234")."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    n = 0
    with _lock:
        ps = players()
        for p in ps.values():
            if not p.get("anonymised") and (p.get("last_bet") or p["first_seen"]) < cutoff:
                p.update(name=None, anonymised=True)
                n += 1
        if n:
            _write("players.json", ps)
    if n:
        from . import races

        races.scrub({pid for pid, p in ps.items() if p.get("anonymised")}, names_only=True)
    return n
