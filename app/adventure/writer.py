"""The story's AI writer (phase 2, docs/VOICES_STORY_PLAN.md §4-5): each morning it adapts the
day's planned node (the weekly routine's) to what the comments added up to: the winning way, how
many voted, the top shouted word and a companion's moment. It rewrites the node's words only: the
hook, story, outcomes or aftermath. The scene, foe, check (skill, DC), question and choices stay as
planned, so the story's branches and the dice are untouched.

**What DeepSeek is given is built here and only here** (`prompt_input`): the planned node, the
hero's class and hearts, the last episodes' text, the arc's title and notes, the party as story
characters (`party.story_party`), and totals. Never a username, account id, comment, or anything a
single viewer wrote or did. tests/test_writer.py checks that.

Every answer goes through the engine's node validator (`validate-node`: limits, teen-friendly,
narration length) and the checks below (the shouted word and the companion appear, nothing about
viewers). A failed answer is sent back with its problems, at most twice; after that, or if the API
is down, the planned node plays as written. The day never depends on the API.
"""
from __future__ import annotations

import json
import logging
import re
import time

import httpx

from ..config import settings
from . import shouts

log = logging.getLogger(__name__)
ATTEMPTS = 3  # the first answer and at most 2 corrections
WAY_HOW = {"bold": "head-on, loud and brave", "sly": "quietly and with tricks", "wise": "carefully and cleverly"}
TEXT_FIELDS = ("hook", "story", "success", "fail", "after")
# the writer must never speak to or about the audience as people
AUDIENCE = re.compile(r"@|\b(viewers?|comments?|commenters?|followers?|subscribe|instagram|youtube|username)\b", re.I)


class WriterError(Exception):
    pass


def enabled() -> bool:
    return settings.adventure_writer not in ("off", "none", "") and bool(settings.deepseek_api_key)


def prompt_input(node: dict, story: dict) -> dict:
    """Everything the AI writer is given. `story` holds story data and totals only (see
    jobs._writer_story): {"hero", "hearts", "ep", "recap", "recent", "arc", "party", "moment",
    "voices"}. Built field by field, so nothing else can slip in."""
    check = node.get("check")
    v = story.get("voices") or {}
    party_list = [{"slot": int(c["slot"]), "name": str(c["name"]), "cls": str(c["cls"])} for c in story.get("party") or []]
    moment = next((c for c in party_list if c["slot"] == story.get("moment")), None)
    return {
        "episode": int(story["ep"]),
        "hero": {"class": str(story["hero"]["cls"]), "hearts": int(story["hearts"])},
        "arc": {"title": str(story["arc"].get("title", "")), "notes": str(story["arc"].get("notes", ""))[:1500]},
        "recent_episodes": [{"story": str(e.get("story", "")), "outcome": str(e.get("outcome", ""))} for e in story.get("recent") or []][-3:],
        "previous_choice": str(story.get("recap") or ""),
        "planned": {
            "scene": str((node.get("scene") or {}).get("name") or (node.get("scene") or {}).get("type", "")),
            "foe": node.get("foe"),
            "hook": list(node["hook"]),
            "story": node["story"],
            "check": ({"skill": check["skill"], "dc": check["dc"], "success": check["success"], "fail": check["fail"]}
                      if check else None),
            "after": node.get("after"),
            "ask": node["ask"],
            "choices": [c["label"] for c in node["choices"]],
        },
        "voices": {
            "votes": [int(n) for n in v.get("counts") or []],
            "chosen": str(v.get("chosen") or ""),
            "voters": int(v.get("voters") or 0),
            "way": v.get("way"),
            "way_means": WAY_HOW.get(v.get("way") or "", None),
            "rally": int(v.get("rally") or 0),
            "shouted": [{"word": str(s["word"]), "times": int(s["n"])} for s in (v.get("shouts") or [])][:3],
        },
        "party": party_list,
        "companion_moment": moment,
    }


SYSTEM = """You adapt one scene of a daily dungeon-crawl story told in short narrated videos. A plan for
today's scene is given; rewrite only its words so the scene answers what the crowd (the Voices)
asked for. Reply with json only, in exactly this shape:

{"hook": ["LINE ONE", "LINE TWO"], "story": "...", "success": "...", "fail": "...", "after": null}

Rules:
- Keep the plan's events, scene, foe and meaning. Don't add new places, foes or items that the
  plan's choices or next scenes would contradict.
- "hook": two lines of at most 14 characters each, punchy, shown big on the title card.
- "story": at most 20 words. Second person, present tense, short concrete sentences. What the hero
  sees and does now.
- If the plan has a check, write "success" and "fail" (at most 20 words each) and set "after" to
  null. If it has no check, write "after" (at most 20 words) and set "success" and "fail" to null.
- The way (voices.way) is how the hero acts today: tell it that way (voices.way_means). Write the
  outcomes so they fit that way.
- If voices.shouted has words, the first word must appear in today's text: in "story", or (with a
  check) in both "success" and "fail", or (without one) in "after". Use it naturally.
- If companion_moment is set, that companion (by name) does one small helpful thing in "story".
  Other party members may be mentioned by name or not at all. They are story characters only.
- The Voices are a chorus the hero hears. You may mention them ("Thirty voices roar...") using
  voices.voters, never as people, viewers or comments.
- Teen and up: scary is fine, cruel isn't. No gore, swearing or anything sexual. No real people.
- Keep it short: the whole day is narrated, so shorter is better."""


def _ask(messages: list[dict]) -> tuple[dict, dict]:
    """One API call: (parsed json, usage). Blank or unparseable content is retried once.
    Thinking is off: it's a short rewrite, and with it on the reasoning used up max_tokens before any
    json came out (finish_reason "length", blank content)."""
    why = ""
    for _ in range(2):
        req = {"model": settings.deepseek_model, "messages": messages, "max_tokens": 1200,
               "temperature": 0.9, "response_format": {"type": "json_object"}}
        if settings.deepseek_thinking in ("disabled", "enabled"):
            req["thinking"] = {"type": settings.deepseek_thinking}
        r = httpx.post(f"{settings.deepseek_base_url}/chat/completions", timeout=90,
                       headers={"Authorization": f"Bearer {settings.deepseek_api_key}"}, json=req)
        if r.status_code >= 400:
            raise WriterError(f"DeepSeek {r.status_code}: {r.text[:200]}")
        body = r.json()
        choice = body["choices"][0]
        content = (choice["message"].get("content") or "").strip()
        if content:
            try:
                return json.loads(content), body.get("usage") or {}
            except json.JSONDecodeError:
                why = f"not json: {content[:80]!r}"
                continue
        why = f"blank content (finish_reason {choice.get('finish_reason')!r})"
    raise WriterError(f"DeepSeek returned no usable json: {why}")


def _apply(node: dict, out: dict) -> dict:
    """The planned node with the writer's words in it (only the text fields)."""
    n = json.loads(json.dumps(node))
    hook = out.get("hook")
    if isinstance(hook, list) and len(hook) == 2:
        n["hook"] = [str(h).strip().upper() for h in hook]
    if isinstance(out.get("story"), str):
        n["story"] = out["story"].strip()
    if n.get("check"):
        for k in ("success", "fail"):
            if isinstance(out.get(k), str):
                n["check"][k] = out[k].strip()
    elif isinstance(out.get("after"), str):
        n["after"] = out["after"].strip()
    return n


def _has_word(text: str, word: str) -> bool:
    return any(shouts._STEM.get(w) == word or w == word for w in re.findall(r"[a-z]+", text.lower()))


def own_problems(n: dict, inp: dict) -> list[str]:
    """The checks the engine's validator doesn't know about."""
    p = []
    texts = [n["hook"][0], n["hook"][1], n["story"], n.get("after") or "",
             *(([n["check"]["success"], n["check"]["fail"]]) if n.get("check") else [])]
    if any(AUDIENCE.search(t) for t in texts):
        p.append("don't mention viewers, comments, usernames or social media; the Voices are a chorus in the story")
    shouted = inp["voices"]["shouted"]
    if shouted:
        w = shouted[0]["word"]
        ok = _has_word(n["story"], w) or (
            n.get("check") and _has_word(n["check"]["success"], w) and _has_word(n["check"]["fail"], w)) or (
            not n.get("check") and _has_word(n.get("after") or "", w))
        if not ok:
            p.append(f'the shouted word "{w}" must appear in "story" (or in both outcomes, or in "after")')
    m = inp.get("companion_moment")
    if m and m["name"].lower() not in n["story"].lower():
        p.append(f'{m["name"]} (the companion) must do one small thing in "story", by name')
    return p


def adapt(node: dict, story: dict, validate) -> tuple[dict, dict]:
    """(the node to play, a record of what happened). `validate(node) -> problems` is the engine's
    validate-node. On any failure the planned node comes back with the record saying why."""
    inp = prompt_input(node, story)
    record = {"model": settings.deepseek_model, "input": inp, "attempts": [], "tokens": {"in": 0, "out": 0}}
    if not enabled():
        return node, {**record, "status": "off"}
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": "Today's input as json:\n" + json.dumps(inp, ensure_ascii=False)}]
    t0 = time.time()
    for _ in range(ATTEMPTS):
        try:
            out, usage = _ask(messages)
        except (WriterError, httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            record["attempts"].append({"error": str(e)[:300]})
            break  # the API itself failed: no point correcting
        record["tokens"]["in"] += int(usage.get("prompt_tokens") or 0)
        record["tokens"]["out"] += int(usage.get("completion_tokens") or 0)
        n = _apply(node, out)
        problems = validate(n) + own_problems(n, inp)
        record["attempts"].append({"output": out, "problems": problems})
        if not problems:
            record.update(status="written", seconds=round(time.time() - t0, 1), node=n)
            return n, record
        messages += [{"role": "assistant", "content": json.dumps(out, ensure_ascii=False)},
                     {"role": "user", "content": "Fix these problems and reply with the whole json again:\n- "
                                                 + "\n- ".join(problems)}]
    record.update(status="fallback", seconds=round(time.time() - t0, 1))
    return node, record
