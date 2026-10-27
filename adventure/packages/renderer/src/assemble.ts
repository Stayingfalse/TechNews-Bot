// A story episode's narration: the daily clip (hook, story, aftermath, question) cut where the
// aftermath starts, with the reusable check and roll lines between the halves and the call-to-action
// tail at the end. Returns one track and the cue times the video is timed by.
import { execFileSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { type Alignment, type Cues, type StorySpec, cuesFromAlignment, scriptStory } from "../../engine/src/index.ts";

const GAP = 0.35;

const duration = (f: string) =>
  Number(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f]).toString().trim());

export function assembleStory(spec: StorySpec, files: { daily: string; align: Alignment; check?: string; roll?: string; tail?: string }): { file: string; cues: Cues } {
  const sc = scriptStory(spec);
  const c = cuesFromAlignment(files.align, sc.daily); // hook, story, after, ask, end (in the daily clip)
  const dir = mkdtempSync(join(tmpdir(), "adv-voice-"));
  const cut = Math.max(0, c.after - 0.12);
  // pieces in order, each with where its own cues sit inside it
  type Piece = { file: string; from?: number; to?: number; marks: Record<string, number> };
  const pieces: Piece[] = [];
  if (files.check && files.roll) {
    pieces.push({ file: files.daily, from: 0, to: cut, marks: { hook: c.hook, story: c.story } });
    pieces.push({ file: files.check, marks: { check: 0 } });
    pieces.push({ file: files.roll, marks: { roll: 0 } });
    pieces.push({ file: files.daily, from: cut, marks: { after: c.after - cut, cta: c.ask - cut } });
  } else {
    pieces.push({ file: files.daily, from: 0, marks: { hook: c.hook, story: c.story, after: c.after, cta: c.ask } });
  }
  if (files.tail) pieces.push({ file: files.tail, marks: {} });

  const cues: Cues = {};
  const inputs: string[] = [], filters: string[] = [];
  let t = 0;
  pieces.forEach((pc, i) => {
    const full = duration(pc.file), from = pc.from ?? 0, to = pc.to ?? full, len = to - from;
    for (const [k, v] of Object.entries(pc.marks)) cues[k] = Math.round((t + v) * 100) / 100;
    inputs.push("-i", pc.file);
    const gap = i < pieces.length - 1 ? GAP : 0;
    filters.push(`[${i}:a]aresample=44100,aformat=channel_layouts=mono,atrim=start=${from.toFixed(3)}:end=${to.toFixed(3)},asetpts=PTS-STARTPTS,apad=pad_dur=${gap}[p${i}]`);
    t += len + gap;
  });
  cues.end = Math.round(t * 100) / 100;
  const out = join(dir, "voice.mp3");
  execFileSync("ffmpeg", ["-loglevel", "error", "-y", ...inputs, "-filter_complex",
    `${filters.join(";")};${pieces.map((_, i) => `[p${i}]`).join("")}concat=n=${pieces.length}:v=0:a=1[o]`, "-map", "[o]", "-c:a", "libmp3lame", "-b:a", "128k", out]);
  return { file: out, cues };
}
