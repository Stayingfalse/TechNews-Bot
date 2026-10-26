// render <spec.json> --out out.mp4 [--audio voice.mp3 --align alignment.json] [--music auto|none|file] [--fps 30] [--workers 4]
// render <spec.json> --png dir --at 1,6.5,20     stills at those times, for checking a layout
// render script <spec.json>                      the voice-over script as JSON (what to send to ElevenLabs)
// Logs go to stderr; a one-line JSON summary goes to stdout.
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { cpus } from "node:os";
import { isAbsolute, join } from "node:path";
import { parseArgs } from "node:util";
import { Worker } from "node:worker_threads";
import { type Alignment, cuesFromAlignment, music0, plan0, script0, scriptChars, scriptText, sfx0 } from "../../engine/src/index.ts";
import { parseEpisode0 } from "../../shared/src/index.ts";
import { AUDIO, OUT_H, OUT_W, bakedMap, prepare, type Job } from "./canvas.ts";

const { values: o, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    out: { type: "string" }, audio: { type: "string" }, align: { type: "string" }, music: { type: "string", default: "auto" },
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
  if (positionals[0] === "script") {
    const spec = parseEpisode0(JSON.parse(readFileSync(positionals[1], "utf8")));
    const segs = script0(spec);
    process.stdout.write(JSON.stringify({ text: scriptText(segs), chars: scriptChars(segs), segments: segs }) + "\n");
    return;
  }
  const file = positionals[0];
  if (!file || (!o.out && !o.png)) throw new Error("usage: render <spec.json> --out out.mp4 | --png dir --at 1,2,3 | script <spec.json>");
  const spec = parseEpisode0(JSON.parse(readFileSync(file, "utf8")));
  if (o.align) {
    const raw = JSON.parse(readFileSync(o.align, "utf8"));
    spec.cues = cuesFromAlignment((raw.alignment || raw) as Alignment, script0(spec));
    log("cues", JSON.stringify(spec.cues));
  }
  const t0 = performance.now();
  const map = await bakedMap(spec.seed);
  log(`map ready in ${((performance.now() - t0) / 1000).toFixed(1)}s (${map.file})`);
  const job: Job = { spec, map };

  if (o.png) {
    const r = await prepare(job);
    mkdirSync(o.png, { recursive: true });
    for (const t of (o.at || "1").split(",").map(Number)) {
      r.draw(t);
      const out = join(o.png, `part${spec.part}-t${t.toFixed(1)}.png`);
      writeFileSync(out, await r.canvas.encode("png"));
      log(`wrote ${out}`);
    }
    return;
  }

  const fps = Number(o.fps), n = Number(o.workers || Math.min(4, cpus().length));
  const plan = plan0(spec);
  const frames = Math.ceil(plan.dur * fps);
  log(`part ${spec.part}: ${plan.dur.toFixed(1)}s, ${frames} frames, ${n} workers`);

  const music = o.music === "none" ? undefined : asset(o.music === "auto" ? music0(spec) : o.music!);
  const audio = audioArgs(plan.dur, o.audio, music, sfx0(spec, plan));
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
  process.stdout.write(JSON.stringify({ out: o.out, duration: plan.dur, frames, seconds: Math.round(total * 10) / 10, cues: spec.cues || null }) + "\n");
}

main().catch((e) => {
  // one readable line: the server shows the last line of stderr
  const issues = (e as { issues?: { path: (string | number)[]; message: string }[] }).issues;
  console.error(issues ? `invalid spec: ${issues.map((i) => `${i.path.join(".") || "spec"}: ${i.message}`).join("; ")}` : e instanceof Error ? e.message : e);
  process.exit(1);
});
