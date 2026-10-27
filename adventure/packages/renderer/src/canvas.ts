// The Skia canvas backend: fonts, canvases and the per-frame draw, shared by the CLI and its workers.
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { type Canvas, GlobalFonts, createCanvas, loadImage } from "@napi-rs/canvas";
import {
  type BakedMap, type Episode0Spec, type MakeCanvas, type MapFlame, type MapLight, type MapRequest, type Scene0, type StorySpec,
  H, W, bake, drawEpisode0, drawStory, merge, paperTexture, plan0, planStory,
} from "../../engine/src/index.ts";

export const OUT_W = 1080, OUT_H = 1920, DPR = OUT_W / W;
export const ROOT = join(dirname(fileURLToPath(import.meta.url)), "../../..");
export const AUDIO = join(ROOT, "assets/audio");

let fontsLoaded = false;
export function loadFonts() {
  if (fontsLoaded) return;
  for (const f of ["Cinzel-Bold", "Cinzel-Black"]) GlobalFonts.registerFromPath(join(ROOT, `fonts/${f}.ttf`), "Cinzel");
  for (const f of ["Alegreya-Medium", "Alegreya-Bold", "Alegreya-MediumItalic"]) GlobalFonts.registerFromPath(join(ROOT, `fonts/${f}.ttf`), "Alegreya");
  fontsLoaded = true;
}

export const makeCanvas: MakeCanvas = (w, h) => createCanvas(w, h) as unknown as ReturnType<MakeCanvas>;

export const EPISODE0_MAP = { type: "dungeon", seed: 12, size: 5, dir: "N" as const, style: "ink" };

/** Bake the scene map once and cache it as a PNG keyed by everything that shapes it. */
export type MapFile = { file: string; tp: number[][]; len: number[]; k: number; lights: MapLight[]; flames: MapFlame[] };

export async function bakedMap(req: number | MapRequest, cacheDir = process.env.ADVENTURE_CACHE || join(ROOT, ".cache/maps")): Promise<MapFile> {
  loadFonts();
  const rq: MapRequest = typeof req === "number" ? { ...EPISODE0_MAP, seed: req } : { size: 5, dir: "N", style: "ink", ...req };
  const key = createHash("sha256").update(JSON.stringify(rq) + "|k4.5|v5").digest("hex").slice(0, 16);
  const file = join(cacheDir, `${key}.png`), meta = join(cacheDir, `${key}.json`);
  if (existsSync(file) && existsSync(meta)) return { file, ...JSON.parse((await import("node:fs")).readFileSync(meta, "utf8")) };
  mkdirSync(cacheDir, { recursive: true });
  const m = bake(rq, merge(), makeCanvas, 4.5);
  const cv = m.cv as unknown as Canvas;
  writeFileSync(file, await cv.encode("png"));
  const info = { tp: m.tp, len: m.len, k: m.k, lights: m.lights, flames: m.flames };
  writeFileSync(meta, JSON.stringify(info));
  return { file, ...info };
}

export type Job = { spec: Episode0Spec | StorySpec; map: MapFile };

/** The map a spec is drawn on. */
export const mapFor = (spec: Episode0Spec | StorySpec) => bakedMap(spec.kind === "story" ? spec.scene : spec.seed);

/** Everything a worker needs to draw any frame of a job. */
export async function prepare(job: Job) {
  loadFonts();
  const img = await loadImage(job.map.file);
  const scene: Scene0 = { defs: merge(), map: { ...job.map, cv: img as unknown as BakedMap["cv"] } };
  const paper = paperTexture(makeCanvas, 3, 768), dark = makeCanvas(OUT_W / 2, OUT_H / 2);
  const spec = job.spec;
  const plan = spec.kind === "story" ? planStory(spec) : plan0(spec);
  const canvas = createCanvas(OUT_W, OUT_H), ctx = canvas.getContext("2d");
  const draw = (t: number) => {
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const F = { c: ctx as unknown as CanvasRenderingContext2D, dpr: DPR, T: t, paper, dark };
    if (spec.kind === "story") drawStory(F, spec, scene, plan as ReturnType<typeof planStory>);
    else drawEpisode0(F, spec, scene, plan as ReturnType<typeof plan0>);
  };
  return { plan, canvas, ctx, draw };
}
