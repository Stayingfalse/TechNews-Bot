"""raosanta.uk's live figures: fetching (with a fallback), and filling them into a promo."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from pydantic import ValidationError

from app.config import settings
from app.santa import source
from app.santa.spec import PromoSpec

STATS = {
    "generatedAt": "2026-11-17T10:00:00Z",
    "season": {"year": 2026, "phase": "drive", "driveStartsOn": "2026-11-15", "opensOn": "2026-11-27",
               "closesOn": "2027-01-06", "lastOrderOn": None, "daysToOpen": 10, "daysToClose": 50, "daysToLastOrder": None},
    "allTime": {"members": "450+", "gifts": "1,200+", "thankYous": "300+"},
    "thisSeason": {"membersTakingPart": "120+", "gifts": None, "giftsLast7Days": None, "thankYous": None},
    "groups": {"workplaces": "20+", "communities": "10+", "friends": None},
}


def spec(**kw) -> PromoSpec:
    base = {"id": "update-test", "format": "update", "segments": [
        {"type": "title", "text": "Gifting opens *{season.opensOn}*", "say": "{allTime.gifts} gifts so far."},
        {"type": "figures", "figures": [{"value": "{allTime.gifts}", "label": "gifts"},
                                        {"value": "{groups.friends}", "label": "friends groups"}]},
        {"type": "points", "items": ["{thisSeason.gifts} gifts this season"]},
        {"type": "end", "line": "{season.daysToClose} days left"}]}
    return PromoSpec.model_validate(base | kw)


def test_values_format_dates_and_skip_hidden_counts():
    v = source.values(STATS)
    assert v["season.opensOn"] == "27 November" and v["season.closesOn"] == "6 January"
    assert v["season.daysToOpen"] == "10" and "season.daysToLastOrder" not in v and "season.lastOrderOn" not in v
    assert v["allTime.gifts"] == "1,200+" and "thisSeason.gifts" not in v and "groups.friends" not in v


def test_fill_drops_what_has_no_figure_and_reads_rounded_numbers_aloud():
    filled, notes = source.fill(spec(), STATS)
    segs = filled.segments
    assert [s.type for s in segs] == ["title", "figures", "end"]  # the points segment had no figure
    assert segs[0].text == "Gifting opens *27 November*" and segs[0].say == "over 1,200 gifts so far."
    assert [f.value for f in segs[1].figures] == ["1,200+"]
    assert segs[2].line == "50 days left"
    assert any("groups.friends" in n or "'{groups.friends}'" in n for n in notes) and any("points" in n for n in notes)


def test_captions_are_filled_sentence_by_sentence():
    filled, notes = source.fill(spec(caption="Opens {season.opensOn}. {thisSeason.gifts} gifts so far! Link in bio."), STATS)
    assert filled.caption == "Opens 27 November. Link in bio."
    assert any("caption" in n for n in notes)


def test_nothing_to_fill_is_untouched():
    plain = spec(segments=[{"type": "title", "text": "Hi"}, {"type": "end"}])
    assert source.fill(plain, None) == (plain, [])


def test_without_figures_the_end_card_cant_go():
    with pytest.raises(ValueError, match="end card"):
        source.fill(spec(), None)


def test_unknown_placeholders_are_refused_when_booked():
    with pytest.raises(ValidationError, match="unknown placeholders"):
        spec(segments=[{"type": "title", "text": "{allTime.gift}"}, {"type": "end"}])
    with pytest.raises(ValidationError, match="12 characters"):
        spec(segments=[{"type": "figures", "figures": [{"value": "thirteen chars", "label": "x"}]}, {"type": "end"}])


class Resp:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=self)

    def json(self):
        return self.data


def test_fetch_uses_the_token_and_falls_back_to_a_recent_copy(monkeypatch):
    monkeypatch.setattr(settings, "raosanta_api_token", "t" * 40)
    seen = []
    monkeypatch.setattr(httpx, "get", lambda url, **kw: seen.append((url, kw["headers"])) or Resp(STATS))
    assert source.fetch() == STATS
    assert seen[0][0] == "https://raosanta.uk/api/promo/stats" and seen[0][1]["Authorization"] == "Bearer " + "t" * 40
    monkeypatch.setattr(httpx, "get", lambda url, **kw: Resp({}, 503))
    assert source.fetch() == STATS  # the copy from a moment ago
    saved = json.loads(source._cache_path().read_text())
    saved["fetched_at"] = (datetime.now(timezone.utc) - timedelta(hours=13)).isoformat()
    source._cache_path().write_text(json.dumps(saved))
    assert source.fetch() is None  # too old to quote


def test_no_token_no_request(monkeypatch):
    monkeypatch.setattr(settings, "raosanta_api_token", "")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: pytest.fail("called the site without a token"))
    assert source.fetch() is None


def test_a_preview_quotes_the_live_figures(monkeypatch, discord):
    from app.santa import previews

    monkeypatch.setattr(source, "fetch", lambda: STATS)
    got = {}

    def fake_render(s, out, **kw):
        got["spec"] = s
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"v")
        return {"duration": 9.0, "music": "jingle-bells", "voice_lines": 0}

    monkeypatch.setattr(previews, "render_promo", fake_render)
    job = previews.create(spec(voice=False), background=False)
    assert job["status"] == "done" and got["spec"].segments[0].text == "Gifting opens *27 November*"
    assert job["left_out"] and "Left out" in discord[-1][0]
