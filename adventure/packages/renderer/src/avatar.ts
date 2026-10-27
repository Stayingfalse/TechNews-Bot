// Profile pictures in the videos' style: render avatar --out dir   (1080×1080 PNGs, one per variant)
// Everything important sits inside the centre circle, which is all Instagram and YouTube show.
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createCanvas, loadImage } from "@napi-rs/canvas";
import { type Frame, type Light, CREAM, GOLD, finalRot, die, flame, lighting, merge, paperTexture, recolor, seal, standee } from "../../engine/src/index.ts";
import { CLASSES } from "../../engine/src/sheet.ts";
import { bakedMap, loadFonts, makeCanvas } from "./canvas.ts";

const S = 1080, L = 360; // pixels, logical units

export async function avatars(out: string) {
  loadFonts();
  mkdirSync(out, { recursive: true });
  const m = await bakedMap(12), map = await loadImage(m.file), defs = merge();
  const paper = paperTexture(makeCanvas, 3, 768);

  const frame = (draw: (F: Frame) => void, centre: [number, number], z: number, lights: (sx: (x: number) => number, sy: (y: number) => number) => Light[]) => {
    const cv = createCanvas(S, S), c = cv.getContext("2d") as unknown as CanvasRenderingContext2D;
    c.scale(S / L, S / L);
    const vw = L / z, cl = (v: number) => Math.min(600 - vw / 2, Math.max(vw / 2, v));
    const vx = cl(centre[0]) - vw / 2, vy = cl(centre[1]) - vw / 2;
    const sx = (x: number) => (x - vx) * z, sy = (y: number) => (y - vy) * z;
    c.drawImage(map as unknown as CanvasImageSource, vx * m.k, vy * m.k, vw * m.k, vw * m.k, 0, 0, L, L);
    const F: Frame = { c, dpr: S / L, T: 1.7, paper, dark: makeCanvas(540, 960) };
    const ls = m.lights.map((l) => ({ x: sx(l.x), y: sy(l.y), r: l.r * z, rgb: l.rgb }));
    lighting(F, [...ls, ...lights(sx, sy)], 0.62);
    m.flames.forEach((f, i) => flame(F, sx(f.x), sy(f.y), f.s * z, i));
    // darken outside the circle a touch more, so the centre reads first
    const v = c.createRadialGradient(180, 180, 120, 180, 180, 255);
    v.addColorStop(0, "rgba(10,6,8,0)");
    v.addColorStop(1, "rgba(10,6,8,.7)");
    c.fillStyle = v;
    c.fillRect(0, 0, L, L);
    draw(F);
    return cv;
  };
  // the lit room nearest the middle of the map
  const mid = [...m.flames].sort((a, b) => Math.hypot(a.x - 300, a.y - 330) - Math.hypot(b.x - 300, b.y - 330))[0];
  const torchRoom: [number, number] = [mid?.x ?? 300, mid?.y ?? 330];

  // 1. a natural 20, glowing
  const d20 = frame((F) => {
    const g = F.c.createRadialGradient(180, 180, 10, 180, 180, 150);
    g.addColorStop(0, "rgba(255,190,90,.55)");
    g.addColorStop(1, "rgba(255,190,90,0)");
    F.c.fillStyle = g;
    F.c.fillRect(0, 0, L, L);
    F.c.fillStyle = "rgba(20,10,0,.45)";
    F.c.beginPath();
    F.c.ellipse(186, 262, 74, 18, 0, 0, 7);
    F.c.fill();
    die(F, 180, 178, 92, finalRot(20));
  }, torchRoom, 1.6, () => [{ x: 180, y: 180, r: 230, rgb: "255,190,110" }]);

  // 2. the hooded rogue, lantern-lit
  const rogue = frame((F) => {
    standee(F, recolor(defs.creatures.rogue, CLASSES.rogue.looks[0].swap), 180, 262, 4.4, 1, 1.7, 0);
  }, torchRoom, 1.5, () => [{ x: 180, y: 170, r: 220, rgb: "255,190,110" }]);

  // 3. a wax seal with the die on it
  const sealed = frame((F) => {
    seal(F, 180, 180, 112, "", "#9b2c1e");
    die(F, 180, 176, 62, finalRot(20));
    F.c.font = "900 20px Cinzel";
    F.c.textAlign = "center";
    F.c.fillStyle = CREAM;
    void GOLD;
  }, torchRoom, 1.6, () => [{ x: 180, y: 180, r: 220, rgb: "255,190,110" }]);

  const files: string[] = [];
  for (const [name, cv] of [["d20", d20], ["rogue", rogue], ["seal", sealed]] as const) {
    const f = join(out, `avatar-${name}.png`);
    writeFileSync(f, await cv.encode("png"));
    files.push(f);
  }
  return files;
}
