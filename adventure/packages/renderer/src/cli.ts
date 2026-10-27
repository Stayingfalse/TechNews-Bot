// render <spec.json> --out out.mp4 [--audio voice.mp3 --align alignment.json] [--music auto|none|file] [--fps 30] [--workers 4]
// render <spec.json> --png dir --at 1,6.5,20     stills at those times, for checking a layout
// render script <spec.json>                      the voice-over script as JSON (what to send to ElevenLabs)
// render validate-arc <{arc,context}.json>       every problem with a weekly arc
// render resolve <{node,ctx}.json>               a story node + the day's dice → the episode's spec
// render vocab <{hero}.json>                     scenes, foes, skills (with the hero's odds) and limits, for the routine
// story voice: --daily clip.mp3 --align a.json [--check c.mp3 --roll r.mp3] --tail t.mp3
// render avatar --out dir                        profile pictures (1080×1080)
// Logs go to stderr; a one-line JSON summary goes to stdout.
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { cpus } from "node:os";
import { isAbsolute, join } from "node:path";
import { parseArgs } from "node:util";
import { Worker } from "node:worker_threads";
import {
  type Alignment, type ArcNode as EngineNode, type StorySpec, caption0, captionStory, comment0, commentStory, ctaOf, cuesFromAlignment,
  dailyText, music0, plan0, planStory, resolveNode, script0, scriptChars, scriptStory, scriptText, sfx0, storyMusic, storySfx,
} from "../../engine/src/index.ts";
import { CLASSES, type ClassKey, SKILLS, modifier, odds } from "../../engine/src/sheet.ts";
import { type AnySpec, DAILY_CHARS, DCS, FOES, SCENES, parseSpec, validateArc } from "../../shared/src/index.ts";
import { assembleStory } from "./assemble.ts";
import { AUDIO, OUT_H, OUT_W, mapFor, prepare, type Job } from "./canvas.ts";

const { values: o, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    out: { type: "string" }, audio: { type: "string" }, align: { type: "string" }, music: { type: "string", default: "auto" },
    daily: { type: "string" }, check: { type: "string" }, roll: { type: "string" }, tail: { type: "string" },
    fps: { type: "string", default: "30" }, workers: { type: "string" },
    png: { type: "string" }, at: { type: "string" },
  },
});
const log = (...a: unknown[]) => console.error(`[${new Date().toISOString()}]`, ...a);
const asset = (f: string) => (isAbsolute(f) || f.includes("/") ? f : join(AUDIO, f));

/** The ffmpeg audio graph: voice on top, music ducked under it, sound effects at their times. */
function audioArgs(dur: number, voice: string | undefined, music: string | undefined, sfx: { t: number; file: string; gain: number }[]) {
  const ins: string[] = [], parts: string[] = [], mixIn: string[] = [];
  let i = 1;
  let v: string | undefined;
  if (voice) {
    ins.push("-i", voice);
    parts.push(`[${i}:a]aresample=48000,loudnorm=I=-16:TP=-1.5,apad,asplit=2[v][vk]`); // padded: the ducked music runs to the end
    v = "vk";
    mixIn.push("[v]");
    i++;
  }
  if (music) {
    ins.push("-stream_loop", "-1", "-i", music);
    const fade = `afade=t=in:d=1,afade=t=out:st=${Math.max(0, dur - 1.5).toFixed(2)}:d=1.5`;
    if (v) parts.push(`[${i}:a]aresample=48000,loudnorm=I=-22:TP=-3,${fade}[m0];[m0][${v}]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=450[m]`);
    else parts.push(`[${i}:a]aresample=48000,loudnorm=I=-17:TP=-2,${fade}[m]`);
    mixIn.push("[m]");
    i++;
  } else if (v) parts.push(`[${v}]anullsink`);
  for (const [k, s] of sfx.entries()) {
    ins.push("-i", asset(s.file));
    const ms = Math.round(s.t * 1000);
    parts.push(`[${i}:a]aresample=48000,volume=${s.gain},adelay=${ms}|${ms}[s${k}]`);
    mixIn.push(`[s${k}]`);
    i++;
  }
  if (!mixIn.length) return { ins, map: [] as string[] };
  parts.push(`${mixIn.join("")}amix=inputs=${mixIn.length}:duration=longest:normalize=0,alimiter=limit=0.95[a]`);
  return { ins, map: ["-filter_complex", parts.join(";"), "-map", "0:v", "-map", "[a]", "-c:a", "aac", "-b:a", "160k"] };
}

async function main() {
  if (positionals[0] === "avatar") {
    const { avatars } = await import("./avatar.ts");
    for (const f of await avatars(o.out || "out/avatars")) log(`wrote ${f}`);
    return;
  }
  const out = (o: unknown) => process.stdout.write(JSON.stringify(o) + "\n");
  if (positionals[0] === "script") {
    const spec = parseSpec(JSON.parse(readFileSync(positionals[1], "utf8")));
    if (spec.kind === "story") {
      const sc = scriptStory(spec), text = dailyText(sc.daily);
      return out({ kind: "story", text, chars: text.length, segments: sc.daily, check: sc.check || null, roll: sc.roll || null, tail: sc.tail,
        caption: captionStory(spec), comment: commentStory(spec), options: spec.choices.map((c) => c.label), default: spec.default });
    }
    const segs = script0(spec);
    return out({ text: scriptText(segs), chars: scriptChars(segs), segments: segs, caption: caption0(spec), comment: comment0(spec),
      options: ctaOf(spec).options.map((o) => o.label), default: ctaOf(spec).dflt });
  }
  if (positionals[0] === "validate-arc") {
    const { arc, context } = JSON.parse(readFileSync(positionals[1], "utf8"));
    const r = validateArc(arc, context);
    return out({ ok: r.problems.length === 0, problems: r.problems, arc: r.problems.length ? undefined : r.arc });
  }
  if (positionals[0] === "resolve") {
    const { node, ctx } = JSON.parse(readFileSync(positionals[1], "utf8"));
    return out(resolveNode(node as EngineNode, ctx));
  }
  if (positionals[0] === "vocab") {
    const { hero } = JSON.parse(readFileSync(positionals[1], "utf8")) as { hero: { cls: ClassKey; look: number } | null };
    const skills = Object.fromEntries(Object.entries(SKILLS).map(([k, ab]) => {
      const mod = hero ? modifier(hero.cls, k) : null;
      const at = mod === null ? undefined : Object.fromEntries(DCS.map((dc) => [dc, Math.round(odds(mod, dc) * 100)]));
      return [k, { ability: ab, modifier: mod, success_pct_by_dc: at }];
    }));
    return out({ scenes: SCENES, foes: FOES, dcs: DCS, daily_chars: DAILY_CHARS, skills,
      hero: hero ? { ...hero, class: CLASSES[hero.cls].name, look_name: CLASSES[hero.cls].looks[hero.look]?.name, proficient: CLASSES[hero.cls].skills } : null });
  }
  const file = positionals[0];
  if (!file || (!o.out && !o.png)) throw new Error("usage: render <spec.json> --out out.mp4 | --png dir --at 1,2,3 | script <spec.json>");
  const spec: AnySpec = parseSpec(JSON.parse(readFileSync(file, "utf8")));
  let voice = o.audio;
  if (spec.kind === "story" && o.daily && o.align) {
    const raw = JSON.parse(readFileSync(o.align, "utf8"));
    const v = assembleStory(spec, { daily: o.daily, align: (raw.alignment || raw) as Alignment, check: o.check, roll: o.roll, tail: o.tail });
    spec.cues = v.cues;
    voice = v.file;
    log("cues", JSON.stringify(spec.cues));
  } else if (spec.kind === "episode0" && o.align) {
    const raw = JSON.parse(readFileSync(o.align, "utf8"));
    spec.cues = cuesFromAlignment((raw.alignment || raw) as Alignment, script0(spec));
    log("cues", JSON.stringify(spec.cues));
  }
  const t0 = performance.now();
  const map = await mapFor(spec);
  log(`map ready in ${((performance.now() - t0) / 1000).toFixed(1)}s (${map.file})`);
  const job: Job = { spec, map };

  if (o.png) {
    const r = await prepare(job);
    mkdirSync(o.png, { recursive: true });
    for (const t of (o.at || "1").split(",").map(Number)) {
      r.draw(t);
      const f = join(o.png, `${spec.kind === "story" ? `ep${spec.ep}` : `part${spec.part}`}-t${t.toFixed(1)}.png`);
      writeFileSync(f, await r.canvas.encode("png"));
      log(`wrote ${f}`);
    }
    return;
  }

  const fps = Number(o.fps), n = Number(o.workers || Math.min(4, cpus().length));
  const plan = spec.kind === "story" ? planStory(spec) : plan0(spec);
  const frames = Math.ceil(plan.dur * fps);
  log(`${spec.kind === "story" ? `episode ${spec.ep}` : `part ${spec.part}`}: ${plan.dur.toFixed(1)}s, ${frames} frames, ${n} workers`);

  const music = o.music === "none" ? undefined : asset(o.music === "auto" ? (spec.kind === "story" ? storyMusic(spec) : music0(spec)) : o.music!);
  const sfx = spec.kind === "story" ? storySfx(spec, plan as ReturnType<typeof planStory>) : sfx0(spec, plan as ReturnType<typeof plan0>);
  const audio = audioArgs(plan.dur, voice, music, sfx);
  const args = ["-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", `${OUT_W}x${OUT_H}`, "-r", String(fps), "-i", "-",
    ...audio.ins, ...audio.map, "-t", plan.dur.toFixed(3), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
    "-movflags", "+faststart", o.out!];
  const ff = spawn("ffmpeg", args, { stdio: ["pipe", "inherit", "inherit"] });
  const done = new Promise<void>((res, rej) => ff.on("close", (code) => (code === 0 ? res() : rej(new Error(`ffmpeg exited ${code}`)))));

  const workers = Array.from({ length: n }, () => new Worker(new URL("./worker.ts", import.meta.url), { workerData: { job, fps }, execArgv: ["--import", "tsx"] }));
  await Promise.all(workers.map((w) => new Promise((res) => w.once("message", res))));
  const tr = performance.now();

  const ready = new Map<number, Buffer>();
  let next = 0, sent = 0;
  const window = n * 3;
  await new Promise<void>((resolve, reject) => {
    const pump = async () => {
      while (ready.has(next)) {
        const b = ready.get(next)!;
        ready.delete(next);
        next++;
        if (!ff.stdin.write(b)) await new Promise((r) => ff.stdin.once("drain", r));
        if (next % (fps * 5) === 0) log(`${next}/${frames} frames`);
      }
      if (next >= frames) return resolve();
      while (sent < frames && sent < next + window) workers[sent % n].postMessage(sent++);
    };
    let busy = Promise.resolve();
    for (const w of workers) {
      w.on("message", (m: { i: number; buf: ArrayBuffer }) => {
        ready.set(m.i, Buffer.from(m.buf));
        busy = busy.then(pump).catch(reject);
      });
      w.on("error", reject);
    }
    busy = busy.then(pump);
  });
  ff.stdin.end();
  await done;
  await Promise.all(workers.map((w) => w.terminate()));
  const secs = (performance.now() - tr) / 1000, total = (performance.now() - t0) / 1000;
  log(`wrote ${o.out}: ${frames} frames in ${secs.toFixed(1)}s (${(frames / secs).toFixed(1)} fps), total ${total.toFixed(1)}s`);
  out({ out: o.out, duration: plan.dur, frames, seconds: Math.round(total * 10) / 10, cues: spec.cues || null });
}

main().catch((e) => {
  // one readable line: the server shows the last line of stderr
  const issues = (e as { issues?: { path: (string | number)[]; message: string }[] }).issues;
  console.error(issues ? `invalid spec: ${issues.map((i) => `${i.path.join(".") || "spec"}: ${i.message}`).join("; ")}` : e instanceof Error ? e.message : e);
  process.exit(1);
});
