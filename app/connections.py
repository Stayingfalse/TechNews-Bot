"""Every channel's platform accounts: connected or not, still working, and the link that reconnects
each one. The dashboard's Accounts card reads this; reconnecting from there needs only the sign-in
cookie, never the API token."""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import channels, store
from .publish import LABELS, PUBLISHERS

EXPIRING_DAYS = 7  # an Instagram login this close to its end isn't renewing


def reconnect_url(provider: str, channel: str) -> str:
    return f"/oauth/{provider}/start" + ("" if channel == channels.MAIN else f"?channel={channel}")


def _granted(tok: dict) -> list[str]:
    return tok.get("permissions") or (tok.get("scope") or "").split()


def plain(err: Exception | str) -> str:
    """The readable part of a platform's error ("Error validating access token: ..."), not its JSON."""
    text = str(err)
    brace = text.find("{")
    if brace < 0:
        return text[:300]
    prefix = text[:brace].rstrip(" :")
    msg = None
    try:
        body = json.loads(text[brace:])
        e = body.get("error", body)
        msg = (e.get("message") or e.get("error_description")) if isinstance(e, dict) else (body.get("error_description") or e)
    except ValueError:  # often cut short: take the message from what's there
        if found := re.search(r'"(?:message|error_description)"\s*:\s*"([^"]+)', text):
            msg = found.group(1)
    return (f"{prefix}: {msg}" if prefix else str(msg))[:300] if msg else text[:300]


def _check(cid: str, name: str) -> dict:
    """One account's state: not_connected, broken, missing_permissions, expiring or ok."""
    ch, mod = channels.get(cid), PUBLISHERS[name]
    row = {"channel": cid, "channel_name": ch.name, "platform": name, "label": LABELS[name],
           "handle": ch.brand_handle, "reconnect_url": reconnect_url(name, cid), "account": None}
    if not mod.configured():
        return row | {"state": "not_configured", "detail": f"The {LABELS[name]} app credentials aren't set on the server."}
    with channels.use(cid):
        tok = store.get_tokens(name)
        if not tok:
            return row | {"state": "not_connected", "detail": "Not connected yet."}
        try:
            acct = mod.account()
            row["account"] = acct.get("username") or acct.get("title")
        except Exception as e:
            return row | {"state": "broken", "detail": plain(e)}
    wanted = mod.SCOPES.replace(",", " ").split()
    missing = [w for w in wanted if w not in _granted(tok)]
    if missing:
        return row | {"state": "missing_permissions", "missing": missing,
                      "detail": f"Works, but was connected without {len(missing)} permission(s) the bot now uses."}
    if name == "instagram" and tok.get("expires_at"):
        days = (tok["expires_at"] - time.time()) / 86400
        row["expires_in_days"] = round(days, 1)
        if days < EXPIRING_DAYS:
            return row | {"state": "expiring", "detail": f"The login ends in {max(0, days):.0f} days and isn't renewing."}
    return row | {"state": "ok", "detail": ""}


def report() -> list[dict]:
    """Every (channel, platform) account, checked live and side by side, in registry order."""
    pairs = [(cid, name) for cid, ch in channels.registry().items() for name in ch.platforms if name in PUBLISHERS]
    with ThreadPoolExecutor(max_workers=max(1, len(pairs))) as pool:
        return list(pool.map(lambda p: _check(*p), pairs))
