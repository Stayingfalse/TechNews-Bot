"""Public legal pages and viewers' self-service data requests.

Pages: /privacy (policy, with the "how we use your comments" video), /terms, /privacy/request (a
form to opt out or delete), /privacy/status/<code> (where a request stands).

Automated routes to opting out / deletion, logged with a confirmation code:
  - commenting "#optout" under any of our videos (the platform vouches for who wrote it): found by
    scan_comment_optouts(), twice a day, and applied at once
  - the request form: anyone can type any username, so it only opens a request. It's carried out once
    the named account comments the request's code under any of our videos (scan_confirmations(), every
    CONFIRM_EVERY while any are waiting) or the owner approves it; unconfirmed requests expire after
    PENDING_DAYS. Without this, anyone could wipe a rival's racing balance and opt them out.
  - Meta's data deletion and deauthorize callbacks (signed_request, verified with the app secret)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import re
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from string import Template

from . import notify, privacy, store
from .config import settings

UPDATED = "28 October 2026"
REQUEST_LOG_DAYS = 365  # deletion/opt-out records kept to show we honoured them (Art. 5(2) accountability)
OPTOUT_WORDS = re.compile(r"(?i)(#\s*opt\s*-?\s*out\b|\bopt\s*-?\s*out\b|#\s*nodata\b)")
TEMPLATES = Path(__file__).with_name("legal")
EXPLAINERS = Path(__file__).resolve().parents[1] / "assets" / "explainer"
VIDEOS = ("how-we-use-comments", "how-we-use-votes")  # the quiz's, the dungeon crawl's
PENDING_DAYS = 7  # a form request not confirmed by then expires
CONFIRM_EVERY = 15 * 60  # seconds between comment scans while requests wait
MAX_PENDING = 500  # the form can't grow the log without limit
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I: typed into a comment


# ------------------------------------------------------------------ requests log

def _log() -> dict:
    return store._read("privacy_requests.json", {})


def _new_code(log: dict) -> str:
    while (code := "".join(secrets.choice(CODE_CHARS) for _ in range(6))) in log:
        pass
    return code


def record(kind: str, platform: str, who: str, source: str, done: str, status: str = "completed", **extra) -> str:
    """Log a request and return its confirmation code."""
    with store._lock:
        log = _log()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=REQUEST_LOG_DAYS)).isoformat()
        log = {k: v for k, v in log.items() if v["at"] >= cutoff}
        code = _new_code(log)
        log[code] = {"kind": kind, "platform": platform, "who": who, "source": source, "done": done,
                     "at": store.now_iso(), "status": status, **extra}
        store._write("privacy_requests.json", log)
    return code


def lookup(code: str) -> dict | None:
    return _log().get(code.strip().upper())


def _carry_out(kind: str, user: str) -> str:
    if kind == "delete":
        return f"opted out, and removed from {privacy.erase(user)} stored record(s)"
    privacy.opt_out(user)
    return "opted out"


def apply_request(kind: str, platform: str, user: str, source: str) -> str:
    """Opt out (and for 'delete', also erase) a viewer at once, for routes that prove who asked.
    Returns the confirmation code."""
    user = privacy._key(user)
    done = _carry_out(kind, user)
    code = record(kind, platform, f"@{user}", source, done)
    notify.send(f":lock: **Privacy request** {code}: {kind} for @{user} ({platform}, via {source}): {done}. "
                "If they also want a video that shows their name taken down, that's done by hand.")
    return code


class TooManyPending(Exception):
    pass


def open_request(kind: str, platform: str, user: str, source: str = "web form") -> str:
    """A request from the form: waits until the named account confirms it by commenting its code under
    one of our videos, or the owner approves it. Returns the code."""
    user = privacy._key(user)
    if sum(r.get("status") == "pending" for r in _log().values()) >= MAX_PENDING:
        raise TooManyPending()
    expires = (datetime.now(timezone.utc) + timedelta(days=PENDING_DAYS)).isoformat(timespec="seconds")
    code = record(kind, platform, f"@{user}", source, "waiting for confirmation", status="pending",
                  user=user, expires=expires)
    notify.send(f":lock: **Privacy request** {code}: {kind} for @{user} ({platform}) is waiting for them to comment "
                f"the code under one of our videos. It can be approved by hand on the dashboard if they can't.")
    return code


def _settle(code: str, how: str, status: str = "completed") -> dict | None:
    """Carry out (or close) a pending request. Returns it, or None if it isn't pending."""
    with store._lock:
        req = _log().get(code)
        if not req or req.get("status") != "pending":
            return None
        done = _carry_out(req["kind"], req["user"]) if status == "completed" else how
        log = _log()
        log[code].update(status=status, done=done, settled_at=store.now_iso(), settled_by=how)
        store._write("privacy_requests.json", log)
        req = log[code]
    if status == "completed":
        notify.send(f":lock: **Privacy request** {code}: {req['kind']} for {req['who']} ({req['platform']}) confirmed "
                    f"({how}): {req['done']}. If they also want a video that shows their name taken down, that's done by hand.")
    return req


def approve(code: str) -> dict | None:
    return _settle(code.strip().upper(), "approved by the owner")


def reject(code: str) -> dict | None:
    return _settle(code.strip().upper(), "rejected by the owner", status="rejected")


def pending() -> list[dict]:
    return sorted(({"code": k, **v} for k, v in _log().items() if v.get("status") == "pending"), key=lambda r: r["at"])


def scan_confirmations() -> int:
    """Carry out pending form requests whose account commented the code, and expire old ones.
    Returns how many were confirmed."""
    waiting = pending()
    now = datetime.now(timezone.utc).isoformat()
    for r in [r for r in waiting if r["expires"] < now]:
        _settle(r["code"], "not confirmed within %d days" % PENDING_DAYS, status="expired")
    waiting = [r for r in waiting if r["expires"] >= now]
    if not waiting:
        return 0
    posts_since = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()  # any recent video will do
    confirmed = 0
    for c in _recent_comments(posts_since, everyone=True):  # an opted-out viewer may still confirm a deletion
        text = c["text"].upper()
        for r in waiting:
            if (r["code"] in re.findall(r"[A-Z0-9]+", text) and c["platform"] == r["platform"]
                    and privacy._key(c["user"]) == r["user"] and (c.get("at") or "") >= r["at"][:19]):
                if _settle(r["code"], f"they commented the code ({c['platform']})"):
                    confirmed += 1
        waiting = [r for r in waiting if lookup(r["code"]).get("status") == "pending"]
        if not waiting:
            break
    return confirmed


_last_confirm = 0.0
_scanning = threading.Lock()


def confirmations_tick() -> None:
    """From the scheduler: scan for confirmations every CONFIRM_EVERY while any request waits, in a
    thread of its own (reading every recent post's comments takes a while; posting mustn't wait)."""
    global _last_confirm
    if time.time() - _last_confirm < CONFIRM_EVERY or _scanning.locked() or not pending():
        return
    _last_confirm = time.time()

    def run() -> None:
        with _scanning:
            try:
                scan_confirmations()
            except Exception:
                logging.getLogger(__name__).exception("privacy confirmation scan failed")

    threading.Thread(target=run, daemon=True, name="privacy-confirm").start()


# ------------------------------------------------------------------ "#optout" comments

def _recent_comments(since: str, everyone: bool = False):
    """(platform, comment) for every comment under every channel's posts published since `since`
    (opted-out viewers' too with `everyone`)."""
    from . import channels
    from .adventure import jobs as adventure_jobs
    from .cliffhanger import read_comments
    from .publish import instagram

    for job in store.list_jobs(200):
        if job.get("status") == "done" and not job.get("dry_run") and (job.get("published_at") or "") >= since:
            with channels.use(job.get("channel")):
                rows, _, _ = read_comments(job, everyone=everyone)
            yield from rows
    for job in adventure_jobs.recent(60):
        media = ((job.get("results") or {}).get("instagram") or {}).get("media_id")
        if not media or (job.get("published_at") or "") < since:
            continue
        try:
            with channels.use(channels.ADVENTURE):
                rows = instagram.comments(media)
        except Exception:
            continue
        yield from ({**c, "platform": "instagram"} for c in rows)
    from .racing import jobs as racing_jobs

    for job in racing_jobs.recent(60):
        media = ((job.get("results") or {}).get("instagram") or {}).get("media_id")
        if not media or (job.get("published_at") or "") < since:
            continue
        try:
            with channels.use(channels.RACING):
                rows = instagram.comments(media)
        except Exception:
            continue
        yield from ({**c, "platform": "instagram"} for c in rows)


def scan_comment_optouts(days: int = 14) -> int:
    """Opt out anyone who commented "#optout" under a recent post on either channel (one list covers
    both). Returns how many were added."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    seen = store._read("optout_comments.json", [])
    added = 0
    for c in _recent_comments(since):
        if c["id"] in seen or not OPTOUT_WORDS.search(c["text"]):
            continue
        seen.append(c["id"])
        if not privacy.is_opted_out(c["user"]):
            apply_request("opt-out", c["platform"], c["user"], "#optout comment")
            added += 1
    store._write("optout_comments.json", seen[-2000:])
    return added


# ------------------------------------------------------------------ Meta callbacks

def parse_signed_request(signed: str) -> dict | None:
    """Meta's signed_request: base64url(signature).base64url(json), HMAC-SHA256 with the app secret."""
    try:
        sig_b64, payload_b64 = signed.split(".", 1)
        pad = lambda s: s + "=" * (-len(s) % 4)  # noqa: E731
        sig = base64.urlsafe_b64decode(pad(sig_b64))
        data = json.loads(base64.urlsafe_b64decode(pad(payload_b64)))
    except Exception:
        return None
    if str(data.get("algorithm", "")).upper() != "HMAC-SHA256":
        return None
    for secret in filter(None, (settings.instagram_app_secret, settings.meta_app_secret)):
        expected = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
        if hmac.compare_digest(sig, expected):
            return data
    return None


def meta_user_removed(user_id: str, kind: str) -> str:
    """Someone removed our app from their Instagram/Facebook account, or asked for its data to be
    deleted: forget their login (only the accounts the quiz posts from ever sign in) and log it."""
    with store._lock:
        tokens = store._read("tokens.json", {})
        gone = [k for k, v in tokens.items() if k.split(":")[-1] == "instagram" and str(v.get("user_id")) == str(user_id)]
        for k in gone:
            tokens.pop(k)
        if gone:
            store._write("tokens.json", tokens)
    done = (f"stored login removed ({', '.join(gone)})" if gone
            else "nothing stored for this account (the app only keeps logins of the accounts it posts from)")
    code = record(kind, "instagram", f"Meta user {user_id}", "Meta callback", done)
    if gone:
        notify.error(f"Meta says Instagram account {user_id} removed the app ({kind}); its login was deleted. "
                     "Reconnect from the dashboard if that wasn't intended.")
    return code


# ------------------------------------------------------------------ pages

# What each kind of channel does with comments, as the policy's account list describes it
FORMATS = {"quiz": "Quiz videos: answers in comments, shout-outs, viewer-picked themes",
           "adventure": "Story videos: A/B/C votes in comments decide what happens next",
           "racing": "Race videos: play-money bets in comments, balances and a league table"}
PLATFORM_NAMES = {"instagram": "Instagram", "youtube": "YouTube"}


def _at(handle: str) -> str:
    return "@" + handle.lstrip("@") if handle else ""


def accounts_table() -> str:
    """Every account we run, from the channel registry, so a new channel is listed (and covered) by itself."""
    from . import channels

    rows = "".join(
        f"<tr><td>{html.escape(ch.name)}</td><td><strong>{html.escape(_at(ch.brand_handle) or '(not set)')}</strong></td>"
        f"<td>{html.escape(', '.join(PLATFORM_NAMES.get(p, p.title()) for p in ch.platforms))}</td>"
        f"<td>{html.escape(FORMATS.get(ch.kind, ch.kind))}</td></tr>"
        for ch in channels.registry().values())
    return f'<div class="wrap"><table><tr><th>Channel</th><th>Account</th><th>Where</th><th>What it does with comments</th></tr>{rows}</table></div>'


def _page(name: str, **values) -> str:
    contact = settings.privacy_contact_email
    mail = (f'<a href="mailto:{html.escape(contact)}">{html.escape(contact)}</a>' if contact
            else "<em>(contact address not set)</em>")
    common = {"mail": mail, "updated": UPDATED, "accounts": accounts_table(),
              "controller": html.escape(settings.privacy_controller or "the person who runs these accounts"),
              "base": html.escape(settings.public_base_url), "days": str(privacy.RETENTION_DAYS),
              "log_days": str(REQUEST_LOG_DAYS)}
    body = Template((TEMPLATES / f"{name}.html").read_text()).safe_substitute(common, **values)
    body = Template(body).safe_substitute(common)  # placeholders inside the filled-in parts ($mail in a status)
    shell = Template((TEMPLATES / "shell.html").read_text())
    return shell.safe_substitute(common, title=values.get("title", name.title()), body=body)


PROFILE_URLS = {"instagram": "https://www.instagram.com/{}/"}
SHOWN = 30  # videos listed per account before "show all"


def published_videos() -> dict[str, list[dict]]:
    """Every public video, per channel, newest first: {at, title, links: [(platform, url)]}."""
    from . import channels
    from .adventure import jobs as adventure_jobs

    out: dict[str, list[dict]] = {cid: [] for cid in channels.registry()}

    def links(results: dict) -> list[tuple[str, str]]:
        return [(PLATFORM_NAMES.get(p, p.title()), r["url"]) for p, r in (results or {}).items()
                if r.get("ok") and r.get("url") and r.get("privacy", "public") == "public"]

    for job in store.list_jobs(5000):
        if job.get("status") != "done" or job.get("dry_run") or job["id"].startswith("test-"):
            continue
        spec = job.get("spec") or {}
        title = re.sub(r"[*_]", "", spec.get("title") or job["id"])
        if (ls := links(job.get("results"))) and (cid := job.get("channel") or channels.MAIN) in out:
            out[cid].append({"at": job.get("published_at") or job.get("created_at", ""), "title": title,
                             "theme": spec.get("theme", ""), "links": ls})
    for job in adventure_jobs.recent(5000):
        if job.get("dry_run") or not (ls := links(job.get("results"))):
            continue
        spec = job.get("spec") or {}
        title = f"Episode {spec['ep']}" if spec.get("kind") == "story" else f"Episode 0, part {spec.get('part')}"
        out.setdefault(job.get("channel") or channels.ADVENTURE, []).append(
            {"at": job.get("published_at", ""), "title": title, "theme": "", "links": ls})
    from .racing import jobs as racing_jobs

    for job in racing_jobs.recent(5000):
        if not (ls := links(job.get("results"))):
            continue
        title = "Launch: how to play" if job["kind"] == "launch" else f"Race {job['run']}"
        out.setdefault(channels.RACING, []).append({"at": job.get("published_at", ""), "title": title, "theme": "", "links": ls})
    for vids in out.values():
        vids.sort(key=lambda v: v["at"], reverse=True)
    return out


def _video_row(v: dict) -> str:
    when = v["at"][:10]
    try:
        when = datetime.fromisoformat(v["at"]).strftime("%-d %b %Y")
    except ValueError:
        pass
    theme = f' <span class="small">· {html.escape(v["theme"])}</span>' if v["theme"] else ""
    links = " ".join(f'<a href="{html.escape(u)}" rel="noopener">{html.escape(p)}</a>' for p, u in v["links"])
    return f'<li><span class="date">{html.escape(when)}</span> <span class="vt">{html.escape(v["title"])}</span>{theme} <span class="links">{links}</span></li>'


def home_page() -> str:
    from . import channels

    videos, parts = published_videos(), []
    for cid, ch in channels.registry().items():
        handle = _at(ch.brand_handle)
        profiles = " ".join(f'<a href="{PROFILE_URLS[p].format(html.escape(handle.lstrip("@")))}" rel="noopener">'
                            f'{handle} on {PLATFORM_NAMES[p]}</a>' for p in ch.platforms if p in PROFILE_URLS and handle)
        vids = videos.get(cid, [])
        rows = "".join(_video_row(v) for v in vids[:SHOWN])
        more = (f'<details><summary>All {len(vids)} videos</summary><ul class="vids">'
                + "".join(_video_row(v) for v in vids[SHOWN:]) + "</ul></details>") if len(vids) > SHOWN else ""
        listing = f'<ul class="vids">{rows}</ul>{more}' if vids else '<p class="small">No videos yet: the first one is on its way.</p>'
        parts.append(f'<section class="channel"><h2>{html.escape(ch.name)}</h2>'
                     f'<p class="meta">{html.escape(FORMATS.get(ch.kind, ch.kind))} · '
                     f'{html.escape(", ".join(PLATFORM_NAMES.get(p, p.title()) for p in ch.platforms))}</p>'
                     f'<p>{profiles}</p>{listing}</section>')
    return _page("home", title="Videos you play in the comments", channels="".join(parts))


def privacy_page() -> str:
    return _page("privacy", title="Privacy policy")


def terms_page() -> str:
    return _page("terms", title="Terms of service")


def request_page(message: str = "") -> str:
    return _page("request", title="Opt out or delete your data", message=message)


def _where_to_comment(platform: str) -> str:
    """Our accounts on a platform, for the "comment your code under any of our videos" step."""
    from . import channels

    links = []
    for ch in channels.registry().values():
        if platform not in ch.platforms or not ch.brand_handle:
            continue
        handle = html.escape(_at(ch.brand_handle))
        url = PROFILE_URLS.get(platform, "").format(html.escape(ch.brand_handle.lstrip("@")))
        links.append(f'<a href="{url}" rel="noopener">{handle}</a>' if url else f"<strong>{handle}</strong>")
    return ", ".join(links) or "our accounts"


def status_page(code: str) -> str:
    req = lookup(code) if code.strip() else None
    if not code.strip():
        found = "<p>Enter the confirmation code you were given to see where your request stands.</p>"
    elif not req:
        found = f"<p>We have no request with the code <strong>{html.escape(code)}</strong>. Check it, or contact us.</p>"
    elif req["status"] == "pending":
        what = "delete your data and opt you out" if req["kind"] == "delete" else "opt you out"
        until = datetime.fromisoformat(req["expires"]).strftime("%-d %B")
        platform = PLATFORM_NAMES.get(req["platform"], req["platform"])
        found = (f"<p><strong>One more step.</strong> To show it's really you, comment this code under any of our "
                 f"videos on {html.escape(platform)}, from <strong>{html.escape(req['who'])}</strong>:</p>"
                 f'<p class="code">{html.escape(code.upper())}</p>'
                 f"<p>Our {html.escape(platform)} accounts: {_where_to_comment(req['platform'])}. Any video will do. We check "
                 f"every 15 minutes, then {what}. Come back to this page to see it done; once it is, you can delete the comment. If it isn't confirmed by {html.escape(until)}, the request lapses.</p>"
                 f"<p class=\"small\">Can't comment from that account? Email $mail with this code and we'll sort it out. "
                 f"Commenting <strong>#optout</strong> under any of our videos also opts you out straight away.</p>")
    elif req["status"] in ("expired", "rejected"):
        found = (f"<p><strong>Request {html.escape(code.upper())}</strong> ({html.escape(req['kind'])} for "
                 f"{html.escape(req['who'])}) was {html.escape(req['status'])}: {html.escape(req['done'])}. Nothing was "
                 f"changed. You can <a href=\"$base/privacy/request\">make a new request</a> or email $mail.</p>")
    else:
        found = (f"<p><strong>Request {html.escape(code.upper())}</strong>: {html.escape(req['kind'])} for "
                 f"{html.escape(req['who'])} on {html.escape(req['platform'])}, received {html.escape(req['at'][:16].replace('T', ' '))} UTC "
                 f"via {html.escape(req['source'])}.</p><p class=\"ok\">Status: <strong>{html.escape(req['status'])}</strong>: "
                 f"{html.escape(req['done'])}.</p>")
    return _page("status", title="Request status", found=found)
