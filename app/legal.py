"""Public legal pages and viewers' self-service data requests.

Pages: /privacy (policy, with the "how we use your comments" video), /terms, /privacy/request (a
form to opt out or delete), /privacy/status/<code> (where a request stands).

Automated routes to opting out / deletion, all applied at once and logged with a confirmation code:
  - commenting "#optout" under any of our videos (the platform vouches for who wrote it): found by
    scan_comment_optouts(), twice a day
  - the request form
  - Meta's data deletion and deauthorize callbacks (signed_request, verified with the app secret)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from string import Template

from . import notify, privacy, store
from .config import settings

UPDATED = "28 October 2026"
REQUEST_LOG_DAYS = 365  # deletion/opt-out records kept to show we honoured them (Art. 5(2) accountability)
OPTOUT_WORDS = re.compile(r"(?i)(#\s*opt\s*-?\s*out\b|\bopt\s*-?\s*out\b|#\s*nodata\b)")
TEMPLATES = Path(__file__).with_name("legal")
EXPLAINER = Path(__file__).resolve().parents[1] / "assets" / "explainer" / "how-we-use-comments.mp4"


# ------------------------------------------------------------------ requests log

def _log() -> dict:
    return store._read("privacy_requests.json", {})


def record(kind: str, platform: str, who: str, source: str, done: str) -> str:
    """Log a request (already carried out) and return its confirmation code."""
    code = secrets.token_hex(6).upper()
    with store._lock:
        log = _log()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=REQUEST_LOG_DAYS)).isoformat()
        log = {k: v for k, v in log.items() if v["at"] >= cutoff}
        log[code] = {"kind": kind, "platform": platform, "who": who, "source": source, "done": done,
                     "at": store.now_iso(), "status": "completed"}
        store._write("privacy_requests.json", log)
    return code


def lookup(code: str) -> dict | None:
    return _log().get(code.strip().upper())


def apply_request(kind: str, platform: str, user: str, source: str) -> str:
    """Opt out (and for 'delete', also erase) a viewer at once. Returns the confirmation code."""
    user = privacy._key(user)
    if kind == "delete":
        n = privacy.erase(user)
        done = f"opted out, and removed from {n} stored record(s)"
    else:
        privacy.opt_out(user)
        done = "opted out"
    code = record(kind, platform, f"@{user}", source, done)
    notify.send(f":lock: **Privacy request** {code}: {kind} for @{user} ({platform}, via {source}): {done}. "
                "If they also want a video that shows their name taken down, that's done by hand.")
    return code


# ------------------------------------------------------------------ "#optout" comments

def scan_comment_optouts(days: int = 14) -> int:
    """Opt out anyone who commented "#optout" under a recent post. Returns how many were added."""
    from .cliffhanger import read_comments

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    seen = store._read("optout_comments.json", [])
    added = 0
    for job in store.list_jobs(200):
        if job.get("status") != "done" or job.get("dry_run") or (job.get("published_at") or "") < since:
            continue
        rows, _, _ = read_comments(job)
        for c in rows:
            if c["id"] in seen or not OPTOUT_WORDS.search(c["text"]):
                continue
            seen.append(c["id"])
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

def _page(name: str, **values) -> str:
    handle = settings.brand_handle or "the quiz account"
    contact = settings.privacy_contact_email
    mail = (f'<a href="mailto:{html.escape(contact)}">{html.escape(contact)}</a>' if contact
            else "<em>(contact address not set)</em>")
    common = {"handle": html.escape(handle), "mail": mail, "updated": UPDATED,
              "controller": html.escape(settings.privacy_controller or f"the person who runs {handle}"),
              "base": html.escape(settings.public_base_url), "days": str(privacy.RETENTION_DAYS),
              "log_days": str(REQUEST_LOG_DAYS)}
    body = Template((TEMPLATES / f"{name}.html").read_text()).safe_substitute(common, **values)
    shell = Template((TEMPLATES / "shell.html").read_text())
    return shell.safe_substitute(common, title=values.get("title", name.title()), body=body)


def privacy_page() -> str:
    return _page("privacy", title="Privacy policy")


def terms_page() -> str:
    return _page("terms", title="Terms of service")


def request_page(message: str = "") -> str:
    return _page("request", title="Opt out or delete your data", message=message)


def status_page(code: str) -> str:
    req = lookup(code) if code.strip() else None
    if not code.strip():
        found = "<p>Enter the confirmation code you were given to see where your request stands.</p>"
    elif not req:
        found = f"<p>We have no request with the code <strong>{html.escape(code)}</strong>. Check it, or contact us.</p>"
    else:
        found = (f"<p><strong>Request {html.escape(code.upper())}</strong>: {html.escape(req['kind'])} for "
                 f"{html.escape(req['who'])} on {html.escape(req['platform'])}, received {html.escape(req['at'][:16].replace('T', ' '))} UTC "
                 f"via {html.escape(req['source'])}.</p><p class=\"ok\">Status: <strong>{html.escape(req['status'])}</strong>: "
                 f"{html.escape(req['done'])}.</p>")
    return _page("status", title="Request status", found=found)
