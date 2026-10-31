"""Adventure jobs: render (and post) a video now, or book it for a time.

A booked job is prepared RENDER_LEAD before its slot: for a part that follows an earlier post, the
votes on that post are counted first (votes close as preparation starts), then it is voiced and
rendered; it posts at the slot. Episode 0 runs as a series: each part, once posted, books the next
for the same time the next day; after part 4 the story episodes follow the same way, each day's node
picked by the votes from the weekly arcs (campaign.py) and rolled for when the votes close. Jobs are small JSON files in DATA_DIR/adventure/jobs; one adventure
render runs at a time, and only the server holding the deploy lease schedules."""
from __future__ import annotations

import json
import logging
import os
import secrets
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import channels, lease, notify, privacy, store
from ..config import settings
from ..publish import instagram
from . import campaign, party, votes, voice

log = logging.getLogger(__name__)
_render_lock = threading.Lock()

RENDER_LEAD = timedelta(minutes=60)  # 08:00 for a 09:00 post: votes close, then voice and render
MISSED_AFTER = timedelta(hours=6)
STALE = timedelta(minutes=20)  # in progress this long untouched, and not ours: the process doing it died
_mine: set[str] = set()  # jobs this process is working on
WORKING = ("preparing", "voicing", "rendering", "publishing")
FEAR_KEYS = ["skeleton", "goblin", "wraith"]
CLASS_KEYS = ["fighter", "rogue", "wizard"]


class NotConnected(Exception):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


def _jobs_dir() -> Path:
    d = settings.data_dir / "adventure" / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(job: dict) -> None:
    p = _jobs_dir() / f"{job['id']}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(job, indent=1))
    tmp.replace(p)


def get(job_id: str) -> dict | None:
    p = _jobs_dir() / f"{job_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


def recent(limit: int = 20) -> list[dict]:
    files = sorted(_jobs_dir().glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]
    return [json.loads(f.read_text()) for f in files]


def _node(*args: str, timeout: int = 900) -> dict:
    """Run the renderer CLI; it prints a one-line JSON summary on stdout."""
    env = {**os.environ, "ADVENTURE_CACHE": str(settings.data_dir / "adventure" / "maps")}
    cmd = ["node", "--import", "tsx", "packages/renderer/src/cli.ts", *args]
    r = subprocess.run(cmd, cwd=settings.adventure_dir, env=env, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr.strip().splitlines() or ["renderer failed"])[-1][:500])
    return json.loads(r.stdout.strip().splitlines()[-1])


def script(spec: dict) -> dict:
    """The voice-over script, caption, options and default for a spec (also validates the spec)."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(spec, fh)
    try:
        return _node("script", fh.name, timeout=60)
    finally:
        os.unlink(fh.name)


def can_publish() -> str | None:
    """Why the adventure channel can't post right now, or None."""
    if not settings.publish_enabled:
        return "PUBLISH_ENABLED is off"
    if not instagram.configured():
        return "the Instagram app isn't configured"
    with channels.use(channels.ADVENTURE):
        if not store.get_tokens("instagram"):
            return "Instagram isn't connected for the adventure channel: /oauth/instagram/start?channel=adventure"
    return None


def _spawn(target, job: dict, name: str) -> None:
    """Run a step in its own thread, remembered as ours while it runs (so recover() leaves it be)."""
    _mine.add(job["id"])

    def run() -> None:
        try:
            target(job)
        finally:
            _mine.discard(job["id"])

    threading.Thread(target=run, args=(), daemon=True, name=name).start()


# The story episode's opening: "title" (the hook words alone, to 31 Oct 2026), then "question" (the
# hook words with today's question and options, complete in the first frame). Bump it when the opening changes.
HOOK_STYLE = "question"


def _new_id() -> str:
    return f"adv-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"


def submit(spec: dict, use_voice: bool = True, publish: bool = False, at: datetime | None = None,
           series: bool = False) -> dict:
    """Render now (and post if `publish`), or book it to post at `at` (UTC). `series` books each
    following Episode 0 part from this one's votes."""
    if publish and (why := can_publish()):
        raise NotConnected(why)
    if at is not None and at <= now() + timedelta(minutes=5):
        raise ValueError("pick a time at least 5 minutes ahead")
    job = {"id": _new_id(), "kind": spec.get("kind"), "spec": spec, "voice": use_voice, "publish": publish or at is not None,
           "series": series, "channel": channels.ADVENTURE, "created_at": store.now_iso(), "results": {}}
    job["script"] = script(spec)  # fails fast on a bad spec
    if at is not None:
        job.update(status="booked", publish_at=at.isoformat())
        save(job)
        return job
    job["status"] = "queued"
    save(job)
    _spawn(_run_now, job, f"adventure-{job['id']}")
    return job


def cancel(job: dict) -> None:
    job.update(status="cancelled")
    save(job)


# ------------------------------------------------------------------ the steps


def _resolve_votes(job: dict) -> None:
    """For a part that follows an earlier post: count that post's votes and build this part's spec."""
    prev = get(job["from_job"])
    if not prev:
        raise RuntimeError(f"previous post {job['from_job']} not found")
    opts, default = prev["script"]["options"], prev["script"]["default"]
    media = (prev.get("results", {}).get("instagram") or {}).get("media_id")
    comments, error = [], None
    if media:
        try:
            own, out = instagram.own_name().lower(), privacy.opted_out()  # one opt-out list for both channels
            comments = [c for c in instagram.comments(media) if c["user"].lower() != own and privacy._key(c["user"]) not in out]
        except Exception as e:
            error = str(e)[:300]
    else:
        error = "the previous part has no Instagram post"
    t = votes.tally(comments, opts)
    pick, how = votes.decide(t["counts"], default, prev["id"])
    if error:
        how = "default (comments unreadable)" if not any(t["counts"]) else how
        notify.send(f":warning: **Adventure**: couldn't read the votes on `{prev['id']}` ({error}); going with {'ABC'[pick]}")
    way = votes.top_way(t["ways"])
    job["votes"] = {"from_job": prev["id"], "counts": t["counts"], "comments": t["comments"], "voters": len(t["voters"]),
                    "pick": pick, "how": how, "option": opts[pick], "counted_at": store.now_iso(),
                    "ways": t["ways"], "way": votes.WAYS[way] if way is not None else None,
                    "joins": len(t["joins"]), "leaves": len(t["leaves"])}  # totals only
    if job["kind"] == "story":
        ep = campaign.state()["ep"] + 1
        moved = party.update(ep, t)
        bonus = party.rally(len(t["voters"]))
        job["votes"]["shouts"] = [{"word": s["word"], "n": s["n"]} for s in t["shouts"]]  # totals only
        crew = party.story_party(party.spec_party())
        story = {"party": crew, "moment": party.moment_slot(ep, len(crew)),
                 "voices": {"counts": t["counts"], "chosen": opts[pick], "voters": len(t["voters"]), "way": job["votes"]["way"],
                            "rally": bonus, "shouts": job["votes"]["shouts"]}}
        job.update(campaign.build_story(prev, pick, t["counts"], job["votes"]["way"], bonus, story=story))
        top = t["shouts"][0] if t["shouts"] and (job.get("writer") or {}).get("status") == "written" else None
        _add_party(job, party.pick_roller(ep, t["voters"]), moved, top)
    else:
        job["spec"] = next_spec(prev["spec"], pick, t["counts"])
        campaign.note_episode0(job["spec"])
    job["script"] = script(job["spec"])
    counts = " · ".join(f"{'ABC'[i]} {n}" for i, n in enumerate(t["counts"]))
    roll = (job["spec"].get("check") or {}).get("roll")
    rolled = f"\nRolled {roll['total']} vs DC {job['spec']['check']['dc']}: {'success' if roll['ok'] else 'failure'}" if roll else ""
    notify.send(f":ballot_box: **Adventure votes** on {_title(prev)}: {counts} "
                f"({t['comments']} comments) → **{'ABC'[pick]}: {opts[pick]}** ({how}){rolled}")


def _add_party(job: dict, roller: str | None, moved: dict | None = None, shout: dict | None = None) -> None:
    """The party, credits and the Voices' totals into today's spec, and what needs a moderation look:
    every name about to be shown that hasn't been approved before."""
    comp = party.spec_party()
    spec = job["spec"]
    spec["party"] = [{k: c[k] for k in ("name", "cls", "look", "handle")} for c in comp]
    spec["credits"] = {"rolledBy": party.shown_name(roller)}
    v = job.get("votes") or {}
    spec["voices"] = {"ways": v.get("ways") or [0, 0, 0], "way": v.get("way"), "voters": v.get("voters", 0)}
    items = [{"kind": "party", "key": c["key"], "handle": c["handle"], "companion": c["name"]} for c in comp if c["handle"]]
    if spec["credits"]["rolledBy"]:
        items.append({"kind": "rolled_by", "key": roller.lower(), "handle": spec["credits"]["rolledBy"]})
    if shout:  # the word made it into the story: credit the first to shout it
        blocked = set(party.load()["blocked"])
        names = [h for u in shout["first"] if u and u.lower() not in blocked and (h := party.shown_name(u))]
        spec["voices"]["shout"] = {"word": shout["word"], "n": shout["n"]}
        spec["credits"]["shouters"] = names
        items += [{"kind": "shout", "key": h.lower(), "handle": h, "word": shout["word"]} for h in names]
        items.append({"kind": "word", "key": f"word:{shout['word']}", "handle": None, "word": shout["word"]})
    for it in items:
        if it["kind"] in ("party", "rolled_by", "shout"):
            it["status"] = "approved" if party.approved(it["key"]) else "pending"
        else:
            it.setdefault("status", "pending")
    job["moderation"] = items
    job["credits"] = {"rolledBy": spec["credits"]["rolledBy"], "shouters": spec["credits"].get("shouters") or []}
    if (job.get("writer") or {}).get("status") == "written":
        items.append({"kind": "writer", "key": "writer", "handle": None, "status": "pending"})
    if moved:
        job["party_moves"] = {"joined": len(moved["joined"]), "left": len(moved["left"]), "places": moved["places"],
                              "members": moved["members"], "waiting": moved["waiting"]}


# ------------------------------------------------------------------ trying the writer


def writer_try(pick: int = 0, way: str | None = None, shouts: list[str] | None = None, voters: int = 12,
               node_id: str | None = None) -> dict:
    """Run the AI writer on the next episode's planned node with sample totals, and say what happened.
    Nothing is saved, rendered or posted. `pick`: which option of the latest episode won (0 = A);
    `node_id`: any node of an accepted arc instead."""
    from . import writer

    s = campaign.state()
    if node_id:
        arc = next((a for a in campaign.arcs() if any(n["id"] == node_id for n in a["nodes"])), None)
        if not arc:
            raise ValueError(f"no accepted arc has a node {node_id!r}")
        node, recap, label = campaign._node_of(arc, node_id), "You chose to press on.", "Press on"
    else:
        nxt = next((j for j in sorted(recent(50), key=lambda j: j.get("publish_at") or "")
                    if j.get("status") == "booked" and j.get("kind") == "story" and j.get("from_job")), None)
        prev = get(nxt["from_job"]) if nxt else None
        if not prev or not prev.get("script"):
            raise ValueError("no booked story episode to try it on; pass node=<id>")
        opts = prev["script"]["options"]
        pick = max(0, min(pick, len(opts) - 1))
        arc, node, choice = campaign.next_node(prev["spec"], {"arc": prev.get("arc"), "node": prev.get("node")}, pick, opts[pick])
        recap, label = choice["recap"], opts[pick]
    crew = party.story_party(party.spec_party())
    ep = s["ep"] + 1
    counts = [0, 0, 0][: len(node["choices"])]
    story = {"party": crew, "moment": party.moment_slot(ep, len(crew)), "ep": ep, "hero": s["hero"], "hearts": s["hearts"],
             "recap": recap, "recent": campaign._recent_text(s), "arc": {"title": arc.get("title", ""), "notes": arc.get("notes", "")},
             "voices": {"counts": counts, "chosen": label, "voters": voters, "way": way, "rally": party.rally(voters),
                        "shouts": [{"word": w, "n": 3} for w in (shouts or [])]}}
    check = lambda n: campaign._run_node("validate-node", payload={"node": n, "hero": s["hero"], "recap": recap})["problems"]  # noqa: E731
    out, record = writer.adapt(node, story, check)
    text = lambda n: {"hook": n["hook"], "story": n["story"], "check": n.get("check") and {k: n["check"][k] for k in ("skill", "dc", "success", "fail")},  # noqa: E731
                      "after": n.get("after")}
    return {"enabled": writer.enabled(), "model": settings.deepseek_model, "node": node["id"], "status": record["status"],
            "planned": text(node), "written": text(out) if record["status"] == "written" else None,
            "attempts": record["attempts"], "tokens": record["tokens"], "seconds": record.get("seconds"), "input": record["input"]}


# ------------------------------------------------------------------ moderation


def moderation_queue() -> list[dict]:
    """Episodes not yet posted with something to look at: viewers' names (the party, "rolled by", the
    first to shout) and the AI writer's text next to the plan's."""
    out = []
    for job in recent(30):
        if job.get("status") in ("scheduled", "rendering", "preparing", "voicing") and job.get("moderation"):
            spec, plan = job.get("spec") or {}, job.get("plan_node") or {}
            text = None
            if (job.get("writer") or {}).get("status") == "written":
                text = {"hook": spec.get("hook"), "story": spec.get("story"), "after": spec.get("after"),
                        "planned": {"hook": plan.get("hook"), "story": plan.get("story")}}
            out.append({"job": job["id"], "title": _title(job), "status": job["status"], "publish_at": job.get("publish_at"),
                        "video_url": job.get("video_url"), "items": job["moderation"], "text": text})
    return sorted(out, key=lambda j: j.get("publish_at") or "")


def _redo(job: dict, node: dict, story_writer: dict | None = None) -> None:
    """Resolve `node` again with the same dice and votes, keep the party and credits, render."""
    old = job["spec"]
    if story_writer is not None:  # the writer again, e.g. without the shouted word
        from . import writer

        s = campaign.state()
        check = lambda n: campaign._run_node("validate-node", payload={"node": n, "hero": s["hero"],  # noqa: E731
                                                                         "recap": job["resolve_ctx"]["recap"]["line"]})["problems"]
        node, job["writer"] = writer.adapt(job["plan_node"], story_writer, check)
    spec = campaign._run_node("resolve", payload={"node": node, "ctx": job["resolve_ctx"]})
    for k in ("party", "credits", "voices"):
        if k in old:
            spec[k] = old[k]
    job["spec"] = spec
    job["script"] = script(spec)
    _render(job)


def moderate(job: dict, key: str, action: str) -> dict:
    """approve: show it (names: now and in later episodes). remove: take it out and make the episode
    again (in the background; it posts as usual once ready):
      a name (party, rolled by, first to shout) → blocked from the party and credits for good;
      the shouted word → the writer writes the day again without it (no shout credits);
      the writer's text → the plan's own text plays (no shout credits either)."""
    if job.get("status") != "scheduled":
        raise ValueError(f"the episode is {job.get('status')}: it can be changed once it's ready and before it posts")
    items = [i for i in job.get("moderation") or []
             if (key == "*" and i["status"] == "pending") or i["key"] == key.lower()]
    if not items:
        raise ValueError("nothing like that in this episode")
    if action == "approve":
        for i in items:
            if i["kind"] in ("party", "rolled_by", "shout"):
                party.approve(i["key"])
            i["status"] = "approved"
        save(job)
        return job
    spec = job["spec"]
    redo_node, redo_writer = None, None  # a name only needs the video made again; text changes resolve again
    for i in items:
        i["status"] = "removed"
        if i["kind"] in ("party", "rolled_by", "shout"):
            party.block(i["key"])
        if i["kind"] == "party":
            spec["party"] = [c for c in spec.get("party", []) if c["name"] != i.get("companion")]
        elif i["kind"] == "rolled_by":
            spec.setdefault("credits", {})["rolledBy"] = None
        elif i["kind"] == "shout":
            spec.setdefault("credits", {})["shouters"] = [h for h in spec["credits"].get("shouters") or [] if h.lower() != i["key"]]
        elif i["kind"] in ("word", "writer"):
            spec.get("voices", {}).pop("shout", None)
            spec.setdefault("credits", {})["shouters"] = []
            for o in job["moderation"]:
                if o["kind"] in ("shout", "word"):
                    o["status"] = "removed"
            if i["kind"] == "writer":
                redo_node, redo_writer = job.get("plan_node"), None
            else:
                story = json.loads(json.dumps(job.get("writer_story") or {}))
                story.setdefault("voices", {})["shouts"] = []
                redo_writer = story
    job["credits"] = {"rolledBy": spec.get("credits", {}).get("rolledBy"), "shouters": spec.get("credits", {}).get("shouters") or []}
    job["status"] = "rendering"
    save(job)
    removed = [i.get("handle") and f"@{i['handle']}" or (f'the word "{i["word"]}"' if i["kind"] == "word" else "the AI text") for i in items]

    def again(_job: dict) -> None:
        try:
            with _render_lock, channels.use(channels.ADVENTURE):
                if job.get("resolve_ctx") and (redo_writer is not None or redo_node is not None):
                    _redo(job, redo_node if redo_node is not None else job["plan_node"], redo_writer)
                else:
                    job["script"] = script(spec)
                    _render(job)
                job["status"] = "scheduled"
                save(job)
                notify.send(f":broom: **Adventure**: {_title(job)} made again without " + ", ".join(removed)
                            + f"; posts at {_local(job['publish_at'])}\n{job['video_url']}")
        except Exception as e:
            _fail(job, e, "rendering again after moderation")

    _spawn(again, job, f"adventure-moderate-{job['id']}")
    return job


def next_spec(prev: dict, pick: int, counts: list[int]) -> dict:
    """The Episode 0 part after `prev`, given the winning option."""
    part = prev["part"] + 1
    recap = {"pick": pick, "votes": counts}
    spec = {"kind": "episode0", "part": part, "seed": prev.get("seed", 12), "recap": recap, "fear": prev.get("fear", "skeleton")}
    if part == 2:
        spec["fear"] = FEAR_KEYS[pick]
    elif part == 3:
        spec["hero"] = {"cls": CLASS_KEYS[pick], "look": 0}
    elif part == 4:
        spec["hero"] = {"cls": prev["hero"]["cls"], "look": pick}
    return spec


def _title(job: dict) -> str:
    spec = job["spec"]
    return f"Episode {spec['ep']}" if spec.get("kind") == "story" else f"Episode 0 part {spec.get('part')}"


def _voice(job: dict) -> list[str]:
    """The narration as renderer arguments: one clip for Episode 0; for a story episode the day's
    own clip plus the reusable check, roll and sign-off lines (cached by their words, so a line said
    before costs nothing). Nothing at all if this month's budget can't cover it."""
    s = job["script"]
    if job["spec"].get("kind") == "story":
        lines = {"daily": s["text"], "check": s.get("check"), "roll": s.get("roll"), "tail": s.get("tail")}
    else:
        lines = {"audio": s["text"]}
    args, chars, new = [], 0, 0
    for key, text in lines.items():
        if not text:
            continue
        mp3, align, made = voice.clip(text)
        chars, new = chars + len(text), new + (len(text) if made else 0)
        if key in ("audio", "daily"):
            try:
                mp3, align = voice.tighten(mp3, align, settings.adventure_max_pause)
            except Exception:  # long pauses are better than no video
                log.exception("adventure voice: could not shorten pauses")
            args += [f"--{key}", str(mp3), "--align", str(align)]
        else:
            args += [f"--{key}", str(mp3)]
    job["voice_clip"] = {"chars": chars, "new_chars": new, "new": new > 0, "month_spent": voice.spent()}
    return args


def _render(job: dict) -> None:
    """Voice (if wanted and affordable) and render the job's spec."""
    spec = job["spec"]
    audio: list[str] = []
    if job["voice"]:
        job["status"] = "voicing"
        save(job)
        try:
            audio = _voice(job)
        except voice.OutOfBudget as e:
            job["voice_clip"] = {"skipped": str(e)}  # goes out without narration
    job["status"] = "rendering"
    save(job)
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    out = settings.videos_dir / f"{job['id']}-{secrets.token_urlsafe(8)}.mp4"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(spec, fh)
    try:
        workers = str(max(1, min(os.cpu_count() or 1, int(os.environ.get("RENDER_WORKERS", "4")))))
        summary = _node(fh.name, "--out", str(out), "--workers", workers, *audio)
    finally:
        os.unlink(fh.name)
    # which opening the renderer drew, for comparing in GET /metrics?channel=adventure (tag `hook`)
    job["hook_style"] = HOOK_STYLE if spec.get("kind") == "story" else "episode0"
    job.update(video=out.name, video_url=f"{settings.public_base_url}/media/{out.name}", render=summary)
    save(job)


def _publish(job: dict) -> None:
    """Post the Reel to the adventure channel's Instagram, then comment the options under it."""
    s = job["script"]
    try:
        res = {"ok": True, **instagram.publish_reel(job["video_url"], s["caption"])}
    except Exception as e:
        log.exception("adventure post failed")
        job["results"]["instagram"] = {"ok": False, "error": str(e)[:500]}
        return
    try:
        res["comment_id"] = instagram.comment(res["media_id"], s["comment"])
    except Exception as e:  # the post is out; the options are in the caption too
        res["comment_error"] = str(e)[:300]
    job["results"]["instagram"] = res
    job["published_at"] = store.now_iso()


def _report(job: dict) -> None:
    spec, summary = job["spec"], job.get("render") or {}
    vc = job.get("voice_clip") or {}
    said = (f"voice {vc['chars']} chars ({vc.get('new_chars', 0)} new; {vc['month_spent']}/{settings.adventure_voice_budget} this month)"
            if "chars" in vc else f"no voice ({vc.get('skipped', 'off')})")
    ig = job["results"].get("instagram")
    if job.get("publish") and ig:
        title = "Adventure post" if ig.get("ok") else "Adventure post FAILED"
        posted = f"\nPosted to @{settings.adventure_handle}: {ig.get('url') or ig['media_id']}" if ig.get("ok") else f"\n{ig['error']}"
    elif job.get("status") == "scheduled":
        title, posted = "Adventure ready", f"\nPosts at {_local(job['publish_at'])}"
    else:
        title, posted = "Adventure preview", ""
    video = settings.videos_dir / job["video"] if job.get("video") else None
    what = f"{_title(job)} ({job['node']})" if job.get("node") else _title(job)
    dead = "\n:skull: The hero falls in this one." if spec.get("dead") else ""
    pend = [i for i in job.get("moderation") or [] if i["status"] == "pending" and i.get("handle")]
    w = job.get("writer") or {}
    if w and title != "Adventure post":
        why = "; ".join(p for a in w.get("attempts", []) for p in (a.get("problems") or [a.get("error", "")]) if p)[:300]
        dead += {"written": f"\n:pen_ballpoint: Written by the AI writer ({len(w.get('attempts', []))} tries); compare it with the plan on the dashboard.",
                 "fallback": f"\n:pen_ballpoint: The AI writer didn't manage it, so the plan plays as written ({why}).",
                 }.get(w.get("status"), "")
    if pend and title != "Adventure post":
        dead += (f"\n:eyes: {len(pend)} name(s) shown for the first time: " + ", ".join(f"@{i['handle']}" for i in pend)
                 + ". Check them on the dashboard (Adventure → Moderation) before it posts.")
    notify.send(f":crossed_swords: **{title}** `{job['id']}`: {what}{dead}, "
                f"{summary.get('duration', 0):.1f}s, rendered in {summary.get('seconds', 0):.0f}s, {said}{posted}\n{job.get('video_url', '')}",
                attach=video if title != "Adventure post" else None)


def _local(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(settings.tz).strftime("%a %d %b %H:%M")


def _fail(job: dict, e: Exception, step: str) -> None:
    log.exception("adventure job %s failed during %s", job["id"], step)
    job.update(status="failed", error=f"{step}: {e}"[:1000])
    save(job)
    notify.send(f":warning: **Adventure**: `{job['id']}` failed during {step}: {e}")


def _run_now(job: dict) -> None:
    try:
        with _render_lock, channels.use(channels.ADVENTURE):  # threads don't inherit the channel
            _render(job)
            if job.get("publish"):
                job["status"] = "publishing"
                save(job)
                _publish(job)
            job.update(status="done", finished_at=store.now_iso())
            save(job)
            _report(job)
    except Exception as e:
        _fail(job, e, job.get("status", "render"))


def _prepare(job: dict) -> None:
    """A booked job, an hour before its slot: count votes, voice, render; then wait for the slot."""
    try:
        with _render_lock, channels.use(channels.ADVENTURE):
            if job.get("from_job"):
                _resolve_votes(job)
            _render(job)
            job["status"] = "scheduled"
            save(job)
            _report(job)
    except campaign.NoArc as e:
        job.update(status="failed", error=f"no story to play: {e}", error_code="no_arc")
        save(job)
        notify.send(f":warning: **Adventure**: `{job['id']}` has no story to play ({e}). Submit the arc (the weekly "
                    f"routine, POST /adventure/arc) before {_local(job['publish_at'])} and it's prepared straight away.")
    except Exception as e:
        _fail(job, e, "preparing")


def _post(job: dict) -> None:
    try:
        with channels.use(channels.ADVENTURE):
            _publish(job)
            ok = (job["results"].get("instagram") or {}).get("ok")
            job.update(status="done" if ok else "failed", finished_at=store.now_iso())
            if not ok:
                job["error"] = job["results"]["instagram"]["error"]
            if ok and job["spec"].get("kind") == "story":
                campaign.commit(job)
                cr, ep = job.get("credits") or {}, job["state_after"]["ep"]
                if cr.get("rolledBy"):
                    party.credit(ep, job["id"], "rolled_by", cr["rolledBy"])
                for h in cr.get("shouters") or []:
                    party.credit(ep, job["id"], "shout", h, ((job["spec"].get("voices") or {}).get("shout") or {}).get("word"))
            save(job)
            _report(job)
            if ok and job.get("series"):
                _book_next(job)
    except Exception as e:
        _fail(job, e, "publishing")


def _book_next(prev: dict) -> dict | None:
    """Tomorrow's episode, same local time: the next Episode 0 part, or the next story episode."""
    spec = prev["spec"]
    if spec.get("dead"):
        notify.send(":skull: **Adventure**: the hero has fallen. Nothing more is booked: a new hero's Episode 0 "
                    "(not built yet) has to come next.")
        return None
    if spec.get("kind") == "episode0" and spec["part"] < 4:
        kind, nxt, name = "episode0", {"kind": "episode0", "part": spec["part"] + 1}, f"Episode 0 part {spec['part'] + 1}"
    else:
        ep = campaign.state()["ep"] + 1
        kind, nxt, name = "story", {"kind": "story"}, f"Episode {ep}"
    when = datetime.fromisoformat(prev["publish_at"]) + timedelta(days=1)
    local = when.astimezone(settings.tz)  # same local time tomorrow, across clock changes
    prev_local = datetime.fromisoformat(prev["publish_at"]).astimezone(settings.tz)
    when = local.replace(hour=prev_local.hour, minute=prev_local.minute).astimezone(timezone.utc)
    job = {"id": _new_id(), "kind": kind, "spec": nxt, "from_job": prev["id"],
           "voice": prev.get("voice", True), "publish": True, "series": True, "channel": channels.ADVENTURE,
           "created_at": store.now_iso(), "results": {}, "script": None, "status": "booked", "publish_at": when.isoformat()}
    save(job)
    notify.send(f":calendar: **Adventure**: {name} booked for {_local(job['publish_at'])}; "
                f"votes on {_title(prev)} close at {_local((when - RENDER_LEAD).isoformat())}.")
    if kind == "story" and not campaign.covers_next(prev):
        notify.send(f":warning: **Adventure**: no arc says where {name} goes yet. The weekly routine has to submit "
                    f"one (POST /adventure/arc) before {_local((when - RENDER_LEAD).isoformat())}.")
    return job


def retry_waiting() -> list[str]:
    """Story jobs that failed for want of an arc go back on the schedule once one arrives."""
    again = []
    for job in recent(200):
        if job.get("error_code") == "no_arc" and job.get("status") == "failed" \
                and now() - datetime.fromisoformat(job["publish_at"]) < MISSED_AFTER:
            job.update(status="booked", error=None, error_code=None)
            save(job)
            again.append(job["id"])
    return again


# ------------------------------------------------------------------ schedule


def tick(t: datetime | None = None) -> None:
    """Start whatever is due: preparation an hour ahead, posting at the slot."""
    t = t or now()
    for job in recent(200):
        if job.get("status") not in ("booked", "scheduled") or not job.get("publish_at"):
            continue
        due = datetime.fromisoformat(job["publish_at"])
        if t - due > MISSED_AFTER:
            job.update(status="missed", error=f"the server was not running at {due.isoformat()}")
            save(job)
            notify.send(f":warning: **Adventure**: `{job['id']}` missed its slot ({_local(job['publish_at'])})")
        elif job["status"] == "booked" and t >= due - RENDER_LEAD:
            job["status"] = "preparing"  # claimed before the thread starts, so the next tick skips it
            save(job)
            _spawn(_prepare, job, f"adventure-{job['id']}")
        elif job["status"] == "scheduled" and t >= due:
            job["status"] = "publishing"
            save(job)
            _spawn(_post, job, f"adventure-post-{job['id']}")


def recover(stale: timedelta = STALE) -> None:
    """Jobs a dead process left mid-way: unfinished preparation starts again; a post that was
    mid-flight is not retried blindly (it may have gone out), it's flagged. Only jobs untouched for
    `stale` and not ours: during a deploy the old server is still finishing its own."""
    cutoff = time.time() - stale.total_seconds()
    for job in recent(200):
        st = job.get("status")
        if st not in WORKING + ("queued",) or job["id"] in _mine:
            continue
        p = _jobs_dir() / f"{job['id']}.json"
        if p.exists() and p.stat().st_mtime > cutoff:
            continue
        if st in ("preparing", "voicing", "rendering") and job.get("publish_at"):
            job["status"] = "booked"
            save(job)
        elif st in WORKING + ("queued",):
            job.update(status="failed", error=f"the server restarted during {st}")
            save(job)
            if st == "publishing":
                notify.send(f":warning: **Adventure**: the server restarted while posting `{job['id']}`; check "
                            f"@{settings.adventure_handle} before retrying.")


def _loop() -> None:
    while True:
        try:
            if lease.held():
                recover()
                tick()
        except Exception:
            log.exception("adventure tick failed")
        time.sleep(30)


def start() -> None:
    threading.Thread(target=_loop, daemon=True, name="adventure-schedule").start()
