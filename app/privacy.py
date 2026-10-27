"""Viewers' personal data: the public privacy policy, opt-outs, erasure and automatic anonymising.

The only personal data the quiz handles is what viewers post publicly in comments (username, the
comment's text and id, its time). See the policy text below for what is done with it. This module
makes the policy's promises true in code:
  - opt-out: a list of usernames the bot never reads, shows, credits or replies to
  - erase(): removes a username from every stored record (and opts them out)
  - anonymise_old(): names in post records are removed RETENTION_DAYS after the post
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone

from . import store
from .config import settings

RETENTION_DAYS = 90
POLICY_UPDATED = "27 October 2026"


def _key(user: str) -> str:
    return re.sub(r"^@", "", user.strip()).lower()


def opted_out() -> set[str]:
    return set(store._read("optout.json", []))


def opt_out(user: str) -> None:
    with store._lock:
        names = opted_out() | {_key(user)}
        store._write("optout.json", sorted(names))


def is_opted_out(user: str) -> bool:
    return _key(user) in opted_out()


def _scrub(job: dict, user: str | None = None) -> bool:
    """Remove viewer data from a job record: one user's, or (user=None) everyone's. True if changed."""
    changed = False
    rv = job.get("reveal") or {}
    keep = lambda name: user is not None and _key(name) != user  # noqa: E731
    if rv.get("winners"):
        before = len(rv["winners"])
        rv["winners"] = [w for w in rv["winners"] if keep(w["user"])]
        changed |= len(rv["winners"]) != before
    if rv.get("shoutouts"):
        before = len(rv["shoutouts"])
        rv["shoutouts"] = [n for n in rv["shoutouts"] if keep(n)]
        changed |= len(rv["shoutouts"]) != before
    if rv.get("replies"):
        rv["replies"] = [r for r in rv["replies"] if keep(r["user"])]
    picked = (job.get("spec") or {}).get("picked_by")
    if picked and not keep(picked["user"]):
        job["spec"]["picked_by"] = None
        job.pop("picked_reply", None)
        changed = True
    return changed


def erase(user: str) -> int:
    """Article 17: delete a viewer's data from every stored post record, and opt them out so it isn't
    collected again. Returns how many records changed. (Their name in videos already posted stays on
    the platforms until those posts are removed there.)"""
    key = _key(user)
    opt_out(key)
    n = 0
    with store._lock:
        jobs = store._read("jobs.json", {})
        for job in jobs.values():
            if _scrub(job, key):
                n += 1
        store._write("jobs.json", jobs)
    return n


def anonymise_old(days: int = RETENTION_DAYS) -> int:
    """Storage limitation: strip viewer names from records of posts older than `days`."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    n = 0
    with store._lock:
        jobs = store._read("jobs.json", {})
        for job in jobs.values():
            if (job.get("published_at") or "9") < cutoff and not job.get("anonymised"):
                _scrub(job)
                job["anonymised"] = True
                n += 1
        if n:
            store._write("jobs.json", jobs)
    return n


# ------------------------------------------------------------------ the policy page

def policy_html() -> str:
    handle = html.escape(settings.brand_handle or "the quiz account")
    controller = html.escape(settings.privacy_controller or f"the person who runs {handle}")
    contact = html.escape(settings.privacy_contact_email)
    mail = f'<a href="mailto:{contact}">{contact}</a>' if contact else "<em>(contact address not set)</em>"
    return POLICY.format(handle=handle, controller=controller, mail=mail, days=RETENTION_DAYS,
                         updated=POLICY_UPDATED, base=html.escape(settings.public_base_url))


POLICY = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Privacy policy · {handle}</title>
<style>
:root {{ --bg:#0D5C6B; --card:#FFF7E8; --ink:#06262C; --sign:#FFC22E; --hot:#FF5A3C; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif; }}
main {{ max-width:760px; margin:24px auto; padding:28px 24px; background:var(--card); border:3px solid var(--ink);
  border-radius:18px; box-shadow:8px 8px 0 var(--ink); }}
@media (max-width:800px) {{ main {{ margin:16px; padding:20px 16px; }} }}
h1 {{ margin-top:0; font-size:1.7rem; }} h2 {{ font-size:1.15rem; margin-top:1.8em; border-bottom:3px solid var(--sign); display:inline-block; }}
table {{ border-collapse:collapse; width:100%; font-size:.95rem; }} td,th {{ border:1px solid #c9bfae; padding:6px 8px; text-align:left; vertical-align:top; }}
th {{ background:#f3e8d2; }} .note {{ background:#fff; border-left:5px solid var(--hot); padding:10px 14px; }}
a {{ color:#0b5563; font-weight:600; }}
</style></head><body><main>
<h1>Privacy policy</h1>
<p>For the daily quiz videos posted by <strong>{handle}</strong> on Instagram and YouTube. Last updated {updated}.</p>

<p class="note">In short: the quiz only uses what you post <strong>publicly</strong> in comments under its videos, to
judge quiz answers, give shout-outs, pick viewer themes and reply to you. Nothing is sold, nothing is used for
advertising, and you can opt out or have your data deleted at any time by emailing {mail}.</p>

<h2>Who is responsible</h2>
<p>The data controller is {controller} (the “quiz”, “we”). Contact for anything about your data: {mail}.
We are not required to appoint a Data Protection Officer.</p>

<h2>What we collect</h2>
<p>Only from comments you post under our videos, read through the platforms' official APIs:</p>
<ul>
<li>your <strong>username</strong> (and on YouTube your channel id),</li>
<li>the <strong>text</strong> of your comment, its <strong>id</strong> and the <strong>time</strong> you posted it.</li>
</ul>
<p>We do <strong>not</strong> read direct messages, your profile, followers, location or anything you post elsewhere,
and we don't collect email addresses or contact details from viewers. We also see anonymous totals the platforms
give every account (views, likes, watch time), which identify no one.</p>

<h2>What we use it for, and why we're allowed to</h2>
<table>
<tr><th>Use</th><th>What happens</th><th>Lawful basis (UK/EU GDPR)</th></tr>
<tr><td>Quiz answers (“cliffhangers”)</td><td>An automatic check of whether your comment has the right answer.</td><td rowspan="4">Legitimate interests (Art. 6(1)(f)): running an interactive quiz that viewers have chosen to take part in by commenting. You can object at any time (see below).</td></tr>
<tr><td>Shout-outs</td><td>The first correct commenters' usernames are shown, and may be read out by a computer-generated voice, in the next day's video.</td></tr>
<tr><td>Viewer-picked themes</td><td>Comments suggesting a theme are grouped; if yours is picked, your username and comment are shown in that quiz.</td></tr>
<tr><td>Replies</td><td>We may reply under your comment (for example to tell you that you won a shout-out) and comment on our own posts.</td></tr>
</table>
<p>We weighed these uses against your interests: the data is already public, you posted it in reply to our quiz,
use is limited to the quiz itself, and anyone can opt out. Usernames that contain offensive words are never shown.
The answer check is automated, but it has no legal or similarly significant effect on you (Art. 22 doesn't apply);
if you think we got your answer wrong, tell us.</p>

<h2>Who else handles it</h2>
<p>We use these services to run the quiz; each only gets what it needs:</p>
<ul>
<li><strong>Meta (Instagram)</strong> and <strong>Google (YouTube)</strong>: where your comment lives; we read it and post replies through their APIs. Their own privacy policies cover what they do.</li>
<li><strong>Our hosting provider</strong>: the server that runs the quiz and stores the records described below.</li>
<li><strong>ElevenLabs</strong>: turns the host's lines into speech, which can include a winner's username.</li>
<li><strong>Anthropic</strong>: the AI that writes each week's quizzes reads the week's theme suggestions (username and comment text) to pick one.</li>
<li><strong>Discord</strong>: our private channel for previews and posting notes, which can name shout-out winners.</li>
</ul>
<p>Some of these are based in the USA. Transfers rely on the UK/EU adequacy arrangements for the US (the Data
Privacy Framework and the UK Extension) where the provider is certified, or on the standard contractual clauses /
UK International Data Transfer Addendum in their terms.</p>

<h2>How long we keep it</h2>
<ul>
<li>Comments are read when a quiz is made and are <strong>not stored</strong>, except for the few we act on: shout-out winners
and a picked theme's author (username, comment id, time) are kept with that post's record.</li>
<li>Those names are <strong>removed automatically {days} days</strong> after the post.</li>
<li>Recorded voice lines that contain a name are deleted once unused for 60 days.</li>
<li>Names shown in videos stay in the videos on Instagram and YouTube; we can remove a video on request.</li>
</ul>

<h2>Your rights</h2>
<p>Under the UK GDPR and EU GDPR you can ask us to: <strong>access</strong> the data we hold about you, <strong>correct</strong> it,
<strong>delete</strong> it, <strong>restrict</strong> its use, and you can <strong>object</strong> to our use of it (we'll stop and never
read, show or reply to you again). Email {mail} from, or mentioning, the account concerned. We reply within one month
and it's free. You can also delete your comment yourself at any time.</p>
<p id="deletion"><strong>Data deletion:</strong> email {mail} with your username and platform. We remove you from every record we keep,
add you to our opt-out list so you're not picked up again, and, if you ask, remove or edit any video that shows your name.</p>
<p>If you're unhappy with how we handle your data you can complain to the UK Information Commissioner's Office
(<a href="https://ico.org.uk/make-a-complaint/">ico.org.uk</a>) or your local data protection authority in the EU.</p>

<h2>Children</h2>
<p>Instagram and YouTube require users to be at least 13. If we learn a shout-out or credit names someone under 13
we will remove it. Parents can contact us at {mail}.</p>

<h2>Cookies</h2>
<p>Viewers aren't tracked: the quiz has no public website besides this page, which sets no cookies. The owner's
private dashboard uses one strictly necessary sign-in cookie.</p>

<h2>Changes</h2>
<p>We'll update this page if anything changes and change the date at the top. This page lives at
<a href="{base}/privacy">{base}/privacy</a>.</p>
</main></body></html>
"""
