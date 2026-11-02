// The side-on close-up: the scene as a paper toy theatre. A backdrop for the scene type (the crypt
// wall, the cave's rock, the wood at night, the mountain at dusk), the focus object cut out large
// on the boards, the party and the foe as the same paper minis as on the map, and a front frame the
// whole thing is seen through. Each layer is a die-cut sheet (white edge, drop shadow) and drifts
// at its own speed, so the stage has depth.
import type { Creature, Defs } from "./defs.ts";
import { type Frame, type Light, flame, lighting, standee } from "./draw.ts";
import { dsl, markers } from "./dsl.ts";
import { prng } from "./prng.ts";
import { THINGS } from "./things.ts";
import { CREAM, GOLD, H, INK, RED, W } from "./util.ts";

type Ctx = CanvasRenderingContext2D;
export type StageCast = { hero: Creature; party: Creature[]; foe?: Creature; fail: boolean };

/** Where the boards are, and where the object stands on them. */
export const FLOOR_Y = 476, THING_AT: [number, number] = [236, 480], THING_K = 3.7;

/** A die-cut paper layer: white edge and drop shadow behind, then the printed face. */
function cut(c: Ctx, path: () => void, fill: string | CanvasGradient, shadow = 0.55) {
  c.save();
  c.shadowColor = `rgba(0,0,0,${shadow})`;
  c.shadowBlur = 14;
  c.shadowOffsetY = 6;
  c.shadowOffsetX = 3;
  c.lineJoin = "round";
  c.strokeStyle = "#f4ead6";
  c.lineWidth = 5;
  path();
  c.stroke();
  c.restore();
  c.save();
  path();
  c.fillStyle = fill;
  c.fill();
  c.strokeStyle = INK;
  c.lineWidth = 1.1;
  c.stroke();
  c.restore();
}

function stones(c: Ctx, x0: number, y0: number, x1: number, y1: number, h: number, base: string, seed: number) {
  const rnd = prng(seed);
  for (let y = y0, row = 0; y < y1; y += h, row++) {
    let x = x0 - (row % 2) * 20;
    while (x < x1) {
      const w = 34 + rnd() * 26;
      c.globalAlpha = 0.85 + rnd() * 0.25;
      c.fillStyle = base;
      c.fillRect(x + 1, y + 1, w - 2, h - 2);
      c.globalAlpha = 1;
      c.strokeStyle = "rgba(42,29,20,.55)";
      c.lineWidth = 0.8;
      c.strokeRect(x + 1, y + 1, w - 2, h - 2);
      if (rnd() < 0.22) {
        c.beginPath();
        c.moveTo(x + w * 0.3, y + 3);
        c.lineTo(x + w * 0.45, y + h * 0.5);
        c.lineTo(x + w * 0.38, y + h - 3);
        c.stroke();
      }
      x += w;
    }
  }
}

/** A ragged edge of rock, foliage or ridge, as a closed path from `x0` to `x1` around `y`. */
function ragged(c: Ctx, seed: number, x0: number, x1: number, y: number, amp: number, step: number, base: number) {
  const r = prng(seed);
  c.beginPath();
  c.moveTo(x0, base);
  for (let x = x0; x <= x1 + step; x += step) c.lineTo(x, y + (r() - 0.5) * amp * 2 + Math.sin(x * 0.03 + seed) * amp);
  c.lineTo(x1, base);
  c.closePath();
}

function floor(c: Ctx, fill: string, line = "rgba(42,29,20,.55)", planks = true) {
  cut(c, () => {
    c.beginPath();
    c.rect(-30, FLOOR_Y - 8, W + 60, H - FLOOR_Y + 40);
  }, fill, 0.4);
  if (!planks) return;
  c.strokeStyle = line;
  c.lineWidth = 0.9;
  for (let i = -5; i < 12; i++) {
    c.beginPath();
    c.moveTo(40 * i + 20, FLOOR_Y - 8);
    c.lineTo(70 * i - 60, H + 30);
    c.stroke();
  }
  c.beginPath();
  c.moveTo(-30, FLOOR_Y + 26);
  c.lineTo(W + 30, FLOOR_Y + 26);
  c.stroke();
}

// ---------------------------------------------------------------- backdrops

function crypt(c: Ctx, sway: number, seed: number, lights: Light[]) {
  c.save();
  c.translate(sway * 0.3, 0);
  cut(c, () => {
    c.beginPath();
    c.rect(-20, 176, W + 40, 320);
  }, "#7d756a", 0.3);
  c.save();
  c.beginPath();
  c.rect(-20, 176, W + 40, 320);
  c.clip();
  stones(c, -20, 176, W + 40, 496, 22, "#8f877b", seed);
  c.restore();
  // a niche of skulls
  cut(c, () => {
    c.beginPath();
    c.moveTo(42, 330);
    c.lineTo(42, 270);
    c.arc(76, 270, 34, Math.PI, 0);
    c.lineTo(110, 330);
    c.closePath();
  }, "#2a2226", 0.2);
  for (let i = 0; i < 3; i++) {
    const x = 56 + i * 20, y = 314 - (i % 2) * 4;
    c.fillStyle = "#e6dcc4";
    c.beginPath();
    c.ellipse(x, y, 7.5, 7, 0, 0, 7);
    c.fill();
    c.strokeStyle = INK;
    c.lineWidth = 0.8;
    c.stroke();
    c.fillStyle = INK;
    c.beginPath();
    c.ellipse(x - 2.6, y - 1, 1.8, 2.2, 0, 0, 7);
    c.ellipse(x + 2.6, y - 1, 1.8, 2.2, 0, 0, 7);
    c.fill();
  }
  // a torch in its bracket
  c.fillStyle = "#3e3a40";
  c.fillRect(296, 300, 8, 4);
  c.fillStyle = "#6b4524";
  c.fillRect(298, 284, 4, 18);
  lights.push({ x: 300 + sway * 0.3, y: 276, r: 120, rgb: "255,170,80" });
  c.restore();
}

function caveBack(c: Ctx, sway: number, seed: number, lights: Light[]) {
  c.save();
  c.translate(sway * 0.3, 0);
  cut(c, () => ragged(c, seed, -20, W + 20, 230, 22, 18, 500), "#5d5a55", 0.3);
  cut(c, () => ragged(c, seed + 1, -20, W + 20, 300, 16, 24, 500), "#6e6a63", 0.35);
  // stalactites from the roof
  const r = prng(seed + 2);
  for (let i = 0; i < 9; i++) {
    const x = 10 + i * 42 + r() * 20, h = 30 + r() * 60;
    cut(c, () => {
      c.beginPath();
      c.moveTo(x - 9, 150);
      c.lineTo(x + 9, 150);
      c.lineTo(x + 1, 150 + h);
      c.closePath();
    }, "#4f4b47", 0.4);
  }
  for (const [x, y] of [[40, 466], [318, 470], [70, 472]]) {
    c.fillStyle = "#ddd5c4";
    c.fillRect(x - 1, y - 8, 2, 8);
    c.fillStyle = "#3fb8a6";
    c.beginPath();
    c.ellipse(x, y - 8, 7, 4, 0, Math.PI, 0);
    c.fill();
    lights.push({ x: x + sway * 0.3, y: y - 10, r: 55, rgb: "90,230,210" });
  }
  c.restore();
}

function wood(c: Ctx, sway: number, seed: number, lights: Light[], T: number) {
  const sky = c.createLinearGradient(0, 150, 0, 480);
  sky.addColorStop(0, "#1b2340");
  sky.addColorStop(1, "#3a3a52");
  c.fillStyle = sky;
  c.fillRect(-20, 150, W + 40, 340);
  c.fillStyle = "#efe8cf";
  c.beginPath();
  c.arc(270, 210, 22, 0, 7);
  c.fill();
  lights.push({ x: 270, y: 210, r: 140, rgb: "220,225,255" });
  const trees = (k: number, col: string, y: number, n: number, par: number) => {
    c.save();
    c.translate(sway * par, 0);
    const r = prng(seed + k);
    for (let i = 0; i < n; i++) {
      const x = -10 + (i + r() * 0.6) * ((W + 40) / n), h = 120 + r() * 80;
      cut(c, () => {
        c.beginPath();
        c.moveTo(x, y - h);
        c.lineTo(x + 26, y - h * 0.45);
        c.lineTo(x + 12, y - h * 0.45);
        c.lineTo(x + 34, y);
        c.lineTo(x - 34, y);
        c.lineTo(x - 12, y - h * 0.45);
        c.lineTo(x - 26, y - h * 0.45);
        c.closePath();
      }, col, 0.35);
    }
    c.restore();
  };
  trees(1, "#24402e", 470, 6, 0.3);
  trees(2, "#2f5a3a", 486, 4, 0.6);
  // fireflies
  for (let i = 0; i < 8; i++) {
    const x = 30 + ((i * 47 + T * 9) % 300), y = 300 + Math.sin(T * 1.3 + i) * 40 + (i % 3) * 30;
    c.fillStyle = `rgba(230,255,150,${0.4 + 0.4 * Math.sin(T * 3 + i)})`;
    c.beginPath();
    c.arc(x, y, 1.4, 0, 7);
    c.fill();
  }
}

function peaks(c: Ctx, sway: number, seed: number, lights: Light[]) {
  const sky = c.createLinearGradient(0, 150, 0, 480);
  sky.addColorStop(0, "#3a2d4a");
  sky.addColorStop(0.6, "#b8705a");
  sky.addColorStop(1, "#e0a070");
  c.fillStyle = sky;
  c.fillRect(-20, 150, W + 40, 340);
  lights.push({ x: 180, y: 420, r: 260, rgb: "255,180,120" });
  c.save();
  c.translate(sway * 0.2, 0);
  cut(c, () => {
    c.beginPath();
    c.moveTo(-20, 470);
    c.lineTo(60, 250);
    c.lineTo(120, 330);
    c.lineTo(200, 210);
    c.lineTo(290, 320);
    c.lineTo(W + 20, 260);
    c.lineTo(W + 20, 470);
    c.closePath();
  }, "#6e6a76", 0.3);
  c.restore();
  c.save();
  c.translate(sway * 0.5, 0);
  cut(c, () => ragged(c, seed, -20, W + 20, 400, 26, 30, 500), "#8a8478", 0.4);
  c.restore();
}

/** The front frame the stage is seen through: a stone arch underground, branches outdoors. */
function proscenium(c: Ctx, sway: number, open: boolean, seed: number) {
  c.save();
  c.translate(sway * 1.6, 0);
  const shape = () => {
    c.beginPath();
    c.moveTo(-30, 150);
    c.lineTo(W + 30, 150);
    c.lineTo(W + 30, H + 20);
    c.lineTo(W - 12, H + 20);
    c.lineTo(W - 12, 300);
    c.bezierCurveTo(W - 12, 172, 12, 172, 12, 300);
    c.lineTo(12, H + 20);
    c.lineTo(-30, H + 20);
    c.closePath();
  };
  if (open) {
    cut(c, shape, "#1e2a22", 0.7);
    const r = prng(seed);
    c.fillStyle = "#2d4a34";
    for (let i = 0; i < 18; i++) {
      const a = (i / 18) * Math.PI, x = W / 2 - Math.cos(a) * (W / 2 - 10), y = 300 - Math.sin(a) * 120;
      c.beginPath();
      c.ellipse(x + (r() - 0.5) * 10, y + (r() - 0.5) * 10, 16, 9, a, 0, 7);
      c.fill();
    }
  } else {
    cut(c, shape, "#3a3236", 0.7);
    c.save();
    shape();
    c.clip();
    stones(c, -30, 150, W + 30, H + 20, 26, "#4a4146", seed);
    c.restore();
  }
  c.restore();
}

// ---------------------------------------------------------------- the stage

export function drawStage(F: Frame, scene: string, thing: string | undefined, defs: Defs, cast: StageCast, a: number) {
  const { c, T } = F;
  const sway = Math.sin(T * 0.5) * 3, seed = 7;
  const push = 1 + 0.04 * a; // a slow dolly in while the beat plays
  const lights: Light[] = [];
  c.save();
  c.fillStyle = "#0c080c";
  c.fillRect(0, 0, W, H);
  c.translate(W / 2, FLOOR_Y);
  c.scale(push, push);
  c.translate(-W / 2, -FLOOR_Y);
  const open = scene === "forest" || scene === "mountain";
  if (scene === "cave") caveBack(c, sway, seed, lights);
  else if (scene === "forest") wood(c, sway, seed, lights, T);
  else if (scene === "mountain") peaks(c, sway, seed, lights);
  else crypt(c, sway, seed, lights);
  floor(c, scene === "forest" ? "#3d4a2c" : scene === "mountain" ? "#7d6a52" : scene === "cave" ? "#4d4945" : "#5d5650", undefined, !open && scene !== "cave");

  // the object, cut out large on the boards
  const th = thing ? THINGS[thing] : undefined;
  const [tx, ty] = [THING_AT[0] + sway, THING_AT[1]];
  if (th) {
    c.save();
    c.translate(tx, ty);
    c.scale(THING_K, THING_K * 0.9);
    c.save();
    c.shadowColor = "rgba(0,0,0,.5)";
    c.shadowBlur = 10;
    c.shadowOffsetY = 4;
    dsl(c, th.prop, { cut: { fill: "#f4ead6", w: 2.2 } });
    c.restore();
    dsl(c, th.prop, { lw: 0.6, sh: true });
    c.restore();
    const m = markers(th.prop);
    for (const [lx, ly, lr, rgb] of m.lights) lights.push({ x: tx + lx * THING_K, y: ty + ly * THING_K * 0.9, r: lr * THING_K * 0.8, rgb });
  }

  // the cast: hero and party on the left, the foe on the right (closer if things went badly)
  cast.party.forEach((d, i) => standee(F, d, 52 + i * 34 + sway, FLOOR_Y + 30 - i * 3, 1.5, 1, T, 0.9 + i, CREAM));
  standee(F, cast.hero, 104 + sway, FLOOR_Y + 22, 2.2, 1, T, 0, GOLD);
  if (cast.foe) standee(F, cast.foe, (cast.fail ? 300 : 322) + sway, FLOOR_Y + 26, 2, -1, T, 1.7, RED);
  lights.push({ x: 104 + sway, y: FLOOR_Y - 40, r: 170, rgb: "255,190,110" });

  proscenium(c, sway, open, seed + 3);
  c.restore();
  lighting(F, lights.map((l) => ({ ...l, x: W / 2 + (l.x - W / 2) * push, y: FLOOR_Y + (l.y - FLOOR_Y) * push })), 0.5);

  // flames and the object's live part, over the light
  c.save();
  c.translate(W / 2, FLOOR_Y);
  c.scale(push, push);
  c.translate(-W / 2, -FLOOR_Y);
  if (scene !== "cave" && !open) flame(F, 300 + sway * 0.3, 280, 7, 0.4);
  if (th) {
    markers(th.prop).flames.forEach(([fx, fy, fs], i) => flame(F, tx + fx * THING_K, ty + fy * THING_K * 0.9, fs * THING_K, i * 1.7));
    if (th.live) {
      c.save();
      c.translate(tx, ty);
      c.scale(THING_K, THING_K * 0.9);
      th.live(c, T);
      c.restore();
    }
  }
  c.restore();
  // the top of the frame stays dark for the narration
  c.fillStyle = "#0c080c";
  c.fillRect(0, 0, W, 150);
}
