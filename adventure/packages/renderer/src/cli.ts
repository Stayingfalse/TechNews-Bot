// render <spec.json> --out out.mp4 [--audio voice.mp3] [--music track] [--fps 30] [--workers 4]
// render <spec.json> --png dir --at 1,6.5,20     (stills at those times, for checking a layout)
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { cpus } from "node:os";
import { join } from "node:path";
import { parseArgs } from "node:util";
import { Worker } from "node:worker_threads";
import { parseEpisode0 } from "../../shared/src/index.ts";
import { OUT_H, OUT_W, bakedMap, prepare, type Job } from "./canvas.ts";

const { values: o, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    out: { type: "string" }, audio: { type: "string" }, music: { type: "string" },
    fps: { type: "string", default: "30" }, workers: { type: "string" },
    png: { type: "string" }, at: { type: "string" },
  },
});
const log = (...a: unknown[]) => console.error(`[${new Date().toISOString()}]`, ...a);

async function main() {
  const file = positionals[0];
  if (!file || (!o.out && !o.png)) throw new Error("usage: render <spec.json> --out out.mp4 | --png dir --at 1,2,3");
  const spec = parseEpisode0(JSON.parse(readFileSync(file, "utf8")));
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
  const { plan } = await prepare(job);
  const frames = Math.ceil(plan.dur * fps);
  log(`part ${spec.part}: ${plan.dur.toFixed(1)}s, ${frames} frames, ${n} workers`);

  const args = ["-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", `${OUT_W}x${OUT_H}`, "-r", String(fps), "-i", "-"];
  const mix: string[] = [];
  if (o.audio) args.push("-i", o.audio);
  if (o.music) args.push("-stream_loop", "-1", "-i", o.music);
  const fadeOut = Math.max(0, plan.dur - 1.5).toFixed(2);
  if (o.audio && o.music) {
    mix.push("-filter_complex", `[2:a]loudnorm=I=-18:TP=-2,volume=0.35,afade=t=in:d=1,afade=t=out:st=${fadeOut}:d=1.5[m];[1:a][m]amix=inputs=2:duration=longest:normalize=0[a]`, "-map", "0:v", "-map", "[a]");
  } else if (o.music) {
    mix.push("-filter_complex", `[1:a]loudnorm=I=-16:TP=-1.5,afade=t=in:d=1,afade=t=out:st=${fadeOut}:d=1.5[a]`, "-map", "0:v", "-map", "[a]");
  }
  args.push(...mix, "-t", plan.dur.toFixed(3), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p");
  if (o.audio || o.music) args.push("-c:a", "aac", "-b:a", "160k");
  args.push("-movflags", "+faststart", o.out!);
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
  const secs = (performance.now() - tr) / 1000;
  log(`wrote ${o.out}: ${frames} frames in ${secs.toFixed(1)}s (${(frames / secs).toFixed(1)} fps), total ${((performance.now() - t0) / 1000).toFixed(1)}s`);
}

main().catch((e) => {
  console.error(e instanceof Error ? e.message : e);
  process.exit(1);
});
