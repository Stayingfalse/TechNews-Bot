// The Skia canvas backend: fonts, canvases and the per-frame draw, shared by the CLI and its workers.
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { type Canvas, GlobalFonts, createCanvas, loadImage } from "@napi-rs/canvas";
import {
  type BakedMap, type Episode0Spec, type MakeCanvas, type MapFlame, type MapLight, type Scene0,
  H, W, bake, drawEpisode0, merge, paperTexture, plan0,
} from "../../engine/src/index.ts";

export const OUT_W = 1080, OUT_H = 1920, DPR = OUT_W / W;
const ROOT = join(dirname(fileURLToPath(import.meta.url)), "../../..");

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

export async function bakedMap(seed: number, cacheDir = join(ROOT, ".cache/maps")): Promise<MapFile> {
  loadFonts();
  const rq = { ...EPISODE0_MAP, seed };
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

export type Job = { spec: Episode0Spec; map: MapFile };

/** Everything a worker needs to draw any frame of a job. */
export async function prepare(job: Job) {
  loadFonts();
  const img = await loadImage(job.map.file);
  const scene: Scene0 = { defs: merge(), map: { ...job.map, cv: img as unknown as BakedMap["cv"] } };
  const paper = paperTexture(makeCanvas, 3, 768), dark = makeCanvas(OUT_W / 2, OUT_H / 2);
  const plan = plan0(job.spec);
  const canvas = createCanvas(OUT_W, OUT_H), ctx = canvas.getContext("2d");
  const draw = (t: number) => {
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    ctx.clearRect(0, 0, W, H);
    drawEpisode0({ c: ctx as unknown as CanvasRenderingContext2D, dpr: DPR, T: t, paper, dark }, job.spec, scene, plan);
  };
  return { plan, canvas, ctx, draw };
}
