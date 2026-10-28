"""The bets pages, served only on RACING_DOMAIN (race.onlydan.uk): the race card, the league table,
a page per player (balance, bets, bonuses) and a page per race (every bet, and the seal check).

Read-only, no sign-in: everything shown comes from public comments. Opted-out players never
appear; anonymised players show as "punter #1234". Player pages are looked up by exact handle.
"""
from __future__ import annotations

import hashlib
import html
import json
from datetime import datetime

from ..config import settings
from ..privacy import opted_out
from . import ledger, races, sim

CSS = """
:root{--bg:#0a0e1e;--panel:#161c34;--panel2:#1c2442;--muted:#8c96be;--dim:#3c466e;--text:#fff;
--yellow:#facd28;--green:#28c86e;--red:#e83434;--purple:#b450ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:760px;margin:0 auto;padding:24px 16px 64px}a{color:var(--yellow)}
h1{font-size:28px;margin:0 0 4px;letter-spacing:.02em}h2{font-size:20px;margin:32px 0 10px}
.muted{color:var(--muted)}.small{font-size:13px}.mono{font-family:ui-monospace,Menlo,Consolas,monospace}
table{width:100%;border-collapse:collapse}td,th{padding:8px 10px;text-align:left}
th{color:var(--muted);font-weight:600;font-size:13px}tr:nth-child(odd) td{background:var(--panel)}
tr:nth-child(even) td{background:var(--panel2)}td.r,th.r{text-align:right}
.bar{display:inline-block;width:6px;height:18px;vertical-align:middle;margin-right:8px;border-radius:2px}
.box{background:var(--panel);border-radius:14px;padding:16px;margin:12px 0}
.ok{color:var(--green)}.bad{color:var(--red)}.y{color:var(--yellow)}
form{display:flex;gap:8px}input{flex:1;padding:10px;border-radius:10px;border:1px solid var(--dim);
background:var(--panel);color:var(--text);font-size:16px}button{padding:10px 16px;border:0;border-radius:10px;
background:var(--yellow);color:#0a0e1e;font-weight:700;font-size:16px}
.wrap{overflow-x:auto}code{word-break:break-all}
"""
COLOURS = {"red": "#e83434", "green": "#28c86e", "yellow": "#facd28", "blue": "#3c78ff", "magenta": "#f050be",
           "cyan": "#1ed2e6"}
e = html.escape


def _page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{e(title)} · Sixel Speedway</title>'
            f'<style>{CSS}</style></head><body><main><p class="small muted"><a href="/">SIXEL SPEEDWAY</a> · '
            f'play money, no prizes</p>{body}<p class="small muted" style="margin-top:48px">'
            f'<a href="/privacy">Privacy</a> · <a href="/terms">Terms</a> · '
            f'Comment <span class="mono">#optout</span> under any video to leave the game.</p></main></body></html>')


def _car(no: int) -> str:
    c = sim.CARS[no - 1]
    return f'<span class="bar" style="background:{COLOURS[c["colour"]]}"></span>{no} {e(c["name"])}'


def _local(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(settings.tz).strftime("%a %d %b %H:%M")


def _name(b: dict) -> str:
    return b.get("name") or ledger.anon_name(b["pid"])


def _hidden(name: str | None) -> bool:
    return bool(name) and name.lower() in opted_out()


def home() -> str:
    parts = ["<h1>Sixel Speedway</h1><p class=\"muted\">A car race every day at "
             f"{e(settings.racing_post_time)} on Instagram. Comment a car and a stake under the latest video "
             "(like <b class=\"mono\">4 250</b>) to bet. Everyone starts with §1,000 of play money.</p>",
             '<form action="/find"><input name="name" placeholder="Your Instagram handle" aria-label="Handle">'
             '<button>Find me</button></form>']
    live = [r for r in races.all_races() if r["status"] == "open"]
    if live:
        r = live[-1]
        form = races.form(r["no"])
        rows = "".join(f'<tr><td>{_car(c["no"])}</td><td class="r mono y">{e(r["odds"][i])}</td>'
                       f'<td class="r mono">{e(form[c["no"]])}</td></tr>' for i, c in enumerate(sim.CARS))
        parts.append(f'<h2>Race {r["no"]} · {e(r["circuit"]["name"])} · bets close {e(_local(r["closes_at"]))}</h2>'
                     f'<div class="wrap"><table><tr><th>Car</th><th class="r">Odds</th><th class="r">Form</th></tr>{rows}'
                     f'</table></div><p class="small muted">Seal: <code>{e(r["seal"])}</code> '
                     f'(<a href="/race/{r["no"]}">what this is</a>)</p>')
    done = [r for r in races.all_races() if r["status"] == "run"]
    if done:
        items = "".join(f'<tr><td><a href="/race/{r["no"]}">Race {r["no"]}</a></td><td>{_car(r["result"]["order"][0])}</td>'
                        f'<td class="r mono">{e(r["odds"][r["result"]["order"][0] - 1])}</td></tr>' for r in reversed(done[-10:]))
        parts.append(f'<h2>Latest results</h2><div class="wrap"><table>{items}</table></div>')
    tb = ledger.table(limit=25)
    if tb["rows"]:
        rows = "".join(f'<tr><td class="mono">{i + 1}</td><td><a href="/p/{e(r["name"])}">@{e(r["name"])}</a></td>'
                       f'<td class="r mono">§{r["balance"]:,}</td></tr>'
                       if not r["name"].startswith("punter #") else
                       f'<tr><td class="mono">{i + 1}</td><td class="muted">{e(r["name"])}</td><td class="r mono">§{r["balance"]:,}</td></tr>'
                       for i, r in enumerate(tb["rows"]))
        parts.append(f'<h2>League table</h2><div class="wrap"><table>{rows}</table></div>'
                     f'<p class="small muted">{tb["players"]:,} punters · {tb["bust"]} bust. Every Sunday everyone gets §100, '
                     f'plus §50 for each video they commented on that week.</p>')
    parts.append(RULES)
    return _page("Bets and balances", "".join(parts))


RULES = """<h2>How it works</h2><div class="box"><ol>
<li>The first time you comment, you get §1,000 of play money.</li>
<li>Each comment is one bet: a car and a stake, like <b class="mono">4 250</b>, <b class="mono">250 on blue streak</b>
or <b class="mono">all in on 3</b>. A car on its own stakes §100. Bets are taken in the order you posted them until
your balance runs out.</li>
<li>Bets close an hour before the next video. The race runs in that video; winners get the odds shown when betting
opened (a 4/1 winner turns §250 into §1,250).</li>
<li>Every Sunday: §100 for everyone, plus §50 for each video you commented on that week.</li>
<li>Play money only. It has no cash value and there are no prizes.</li></ol></div>"""


def player(name: str) -> str | None:
    p = ledger.find(name)
    if not p or _hidden(p.get("name")):
        return None
    rows = []
    for x in reversed(ledger.entries(p["pid"])[-200:]):
        what = {"start": "Starting balance", "bonus": f"Weekly bonus ({x.get('videos', 0)} videos)"}.get(x["kind"])
        if x["kind"] in ("bet", "payout"):
            verb = "Bet" if x["kind"] == "bet" else "Won"
            what = f'{verb} · <a href="/race/{x["race"]}">race {x["race"]}</a> · {_car(x["car"])} at {e(x["odds"])}'
        cls = "ok" if x["amount"] > 0 else "bad"
        rows.append(f'<tr><td class="small muted">{e(_local(x["at"]))}</td><td>{what}</td>'
                    f'<td class="r mono {cls}">{x["amount"]:+,}</td></tr>')
    body = (f'<h1>@{e(p["name"])}</h1><p class="y mono" style="font-size:32px;margin:8px 0">§{p["balance"]:,}</p>'
            f'<p class="muted">{p.get("bets", 0)} bets · {p.get("wins", 0)} wins · playing since {e(p["first_seen"][:10])}</p>'
            f'<h2>Every change to your balance</h2><div class="wrap"><table>{"".join(rows)}</table></div>'
            f'<p class="small muted">A bet placed today shows once its race has run.</p>')
    return _page(f"@{p['name']}", body)


def race(no: int) -> str | None:
    r = races.get(no)
    if not r:
        return None
    pub = races.public(r)
    parts = [f'<h1>Race {no} · {e(r["circuit"]["name"])}</h1>']
    if r["status"] != "run":
        parts.append(f'<p class="muted">Betting {"is open until " + e(_local(r["closes_at"])) if r["status"] == "open" else "has closed"}. '
                     f'The race runs in the next video.</p>')
    else:
        res = r["result"]
        rows = "".join(f'<tr><td class="mono">{"X" if no_ in res["dnf"] else i + 1}</td><td>{_car(no_)}</td>'
                       f'<td class="r mono">{e(r["odds"][no_ - 1])}</td><td class="r mono">'
                       f'{"out" if no_ in res["dnf"] else ("" if i == 0 else "+%.3f s" % (res["times"][str(no_)] - res["times"][str(res["order"][0])]) if res["times"].get(str(no_)) is not None else "")}</td></tr>'
                       for i, no_ in enumerate(res["order"]))
        parts.append(f'<h2>Result</h2><div class="wrap"><table><tr><th>Pos</th><th>Car</th><th class="r">Odds</th>'
                     f'<th class="r">Gap</th></tr>{rows}</table></div>')
        bets = [b for b in r.get("bets", []) if not _hidden(b.get("name"))]
        if bets:
            rows = "".join(f'<tr><td>{e("@" + _name(b) if b.get("name") else _name(b))}</td><td>{_car(b["car"])}</td>'
                           f'<td class="r mono">{"refused" if b.get("refused") else "§%s" % format(b["stake"], ",")}</td>'
                           f'<td class="r mono {"ok" if b.get("returned") else ""}">{"+§%s" % format(b["returned"], ",") if b.get("returned") else ""}</td></tr>'
                           for b in bets)
            parts.append(f'<h2>{len(bets)} bets</h2><div class="wrap"><table><tr><th>Punter</th><th>Car</th>'
                         f'<th class="r">Stake</th><th class="r">Returned</th></tr>{rows}</table></div>')
    parts.append(seal_box(r, pub))
    return _page(f"Race {no}", "".join(parts))


def seal_box(r: dict, pub: dict) -> str:
    """The fairness check: the seal published before betting, and (once run) the seed it hides."""
    if "seed" not in pub:
        return (f'<h2>The seal</h2><div class="box"><p>Before betting opened we published this seal:</p>'
                f'<p><code>{e(r["seal"])}</code></p><p class="small muted">It is a SHA-256 fingerprint of the secret seed '
                f'that decides this race, plus the cars\' stats. The seed is revealed after the race, so you can check '
                f'that it matches and that the race wasn\'t changed after the bets came in.</p></div>')
    body = f'{r["no"]}|{pub["seed"]}|{json.dumps(pub["stats"], sort_keys=True, separators=(",", ":"))}'
    check = hashlib.sha256(body.encode()).hexdigest()
    ok = check == r["seal"]
    return (f'<h2>Check the seal</h2><div class="box"><p>Seal published before betting:<br><code>{e(r["seal"])}</code></p>'
            f'<p>Seed revealed after the race:<br><code>{e(pub["seed"])}</code></p>'
            f'<p>SHA-256 of <code>race|seed|stats</code>:<br><code>{e(check)}</code></p>'
            f'<p class="{"ok" if ok else "bad"}"><b>{"✓ Matches the seal" if ok else "✗ Does not match"}</b></p>'
            f'<details><summary class="small">The exact text that was hashed</summary><p><code>{e(body)}</code></p>'
            f'<p class="small muted">Run the race yourself with <code>sim.race({r["no"]}, seed, stats)</code> from '
            f'app/racing/sim.py: it gives the same result.</p></details></div>')


def find(name: str) -> str:
    """Where the lookup form goes: the player's page, or a not-found page."""
    p = ledger.find(name) if name.strip() else None
    if p and not _hidden(p.get("name")):
        return f"/p/{p['name']}"
    return ""


def not_found(what: str) -> str:
    return _page("Not found", f"<h1>Not found</h1><p class=\"muted\">{e(what)}</p><p><a href=\"/\">Back</a></p>")
