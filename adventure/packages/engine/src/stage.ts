// The side-on close-up: the scene as a paper toy theatre. A backdrop for the scene type (the crypt
// wall, the cave's rock, the wood at night, the mountain at dusk), the focus object cut out large
// on the boards, the party and the foe as the same paper minis as on the map, and a front frame the
// whole thing is seen through. Each layer is a die-cut sheet (white edge, drop shadow, lit from
// above) and drifts at its own speed, so the stage has depth; light falls through it (a shaft from
// a grate, moonbeams, the dusk sun), water drips, mist creeps along the boards.
import type { Creature, Defs } from "./defs.ts";
import { type Frame, type Light, flame, lighting, standee } from "./draw.ts";
import { dsl, markers } from "./dsl.ts";
import { embers, fog, moodOf, motes, rays, shafts } from "./fx.ts";
import { prng } from "./prng.ts";
import { THINGS } from "./things.ts";
import { CREAM, GOLD, H, INK, RED, W, shade } from "./util.ts";

type Ctx = CanvasRenderingContext2D;
export type StageCast = { hero: Creature; party: Creature[]; foe?: Creature; fail: boolean };

/** Where the boards are, and where the object stands on them. */
export const FLOOR_Y = 476, THING_AT: [number, number] = [236, 480], THING_K = 3.7;

/** A sheet lit from above: lighter at its top edge, darker at the bottom. */
function lit(c: Ctx, y0: number, y1: number, col: string, top = 0.18, bottom = -0.35): CanvasGradient {
  const g = c.createLinearGradient(0, y0, 0, y1);
  g.addColorStop(0, shade(col, top));
  g.addColorStop(0.45, col);
  g.addColorStop(1, shade(col, bottom));
  return g;
}

/** A die-cut paper layer: white edge and drop shadow behind, then the printed face, then a thin
 *  highlight along its upper edges (the paper catching the light). */
function cut(c: Ctx, path: () => void, fill: string | CanvasGradient, shadow = 0.55, sheen = 0.22) {
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
  if (sheen > 0) {
    c.clip();
    c.translate(0, 2.2);
    path();
    c.strokeStyle = `rgba(255,248,230,${sheen})`;
    c.lineWidth = 2.2;
    c.stroke();
    c.translate(0, -2.2);
  }
  c.restore();
  c.save();
  path();
  c.strokeStyle = INK;
  c.lineWidth = 1.1;
  c.stroke();
  c.restore();
}

/** Bevelled stones, each lit from above, a few cracked or damp. */
function stones(c: Ctx, x0: number, y0: number, x1: number, y1: number, h: number, base: string, seed: number) {
  const rnd = prng(seed);
  for (let y = y0, row = 0; y < y1; y += h, row++) {
    let x = x0 - (row % 2) * 20;
    while (x < x1) {
      const w = 34 + rnd() * 26, col = shade(base, (rnd() - 0.5) * 0.18);
      c.fillStyle = lit(c, y, y + h, col, 0.14, -0.22);
      c.fillRect(x + 1, y + 1, w - 2, h - 2);
      c.fillStyle = "rgba(255,248,230,.18)";
      c.fillRect(x + 2, y + 1.5, w - 4, 1.4);
      c.fillStyle = "rgba(20,12,8,.28)";
      c.fillRect(x + 2, y + h - 2.6, w - 4, 1.4);
      c.strokeStyle = "rgba(42,29,20,.55)";
      c.lineWidth = 0.8;
      c.strokeRect(x + 1, y + 1, w - 2, h - 2);
      const r = rnd();
      if (r < 0.2) {
        c.beginPath();
        c.moveTo(x + w * 0.3, y + 3);
        c.lineTo(x + w * 0.45, y + h * 0.5);
        c.lineTo(x + w * 0.38, y + h - 3);
        c.stroke();
      } else if (r < 0.3) {
        const g = c.createRadialGradient(x + w / 2, y + h, 0, x + w / 2, y + h, w * 0.6);
        g.addColorStop(0, "rgba(70,90,50,.35)");
        g.addColorStop(1, "rgba(70,90,50,0)");
        c.fillStyle = g;
        c.fillRect(x, y, w, h);
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

const hsh = (n: number) => {
  const x = Math.sin(n * 91.7 + 13.1) * 43758.5453;
  return x - Math.floor(x);
};

function floor(c: Ctx, col: string, kind: "flags" | "rock" | "grass" | "scree") {
  cut(c, () => {
    c.beginPath();
    c.rect(-30, FLOOR_Y - 8, W + 60, H - FLOOR_Y + 40);
  }, lit(c, FLOOR_Y - 8, H, col, 0.12, -0.45), 0.4, 0.3);
  c.save();
  c.beginPath();
  c.rect(-30, FLOOR_Y - 8, W + 60, H - FLOOR_Y + 40);
  c.clip();
  if (kind === "flags") {
    c.strokeStyle = "rgba(42,29,20,.5)";
    c.lineWidth = 0.9;
    for (let i = -5; i < 12; i++) {
      c.beginPath();
      c.moveTo(40 * i + 20, FLOOR_Y - 8);
      c.lineTo(70 * i - 60, H + 30);
      c.stroke();
    }
    for (const y of [FLOOR_Y + 22, FLOOR_Y + 62, FLOOR_Y + 112]) {
      c.beginPath();
      c.moveTo(-30, y);
      c.lineTo(W + 30, y);
      c.stroke();
    }
  } else {
    for (let i = 0; i < 70; i++) {
      const x = hsh(i) * (W + 40) - 20, y = FLOOR_Y + hsh(i + 0.3) * (H - FLOOR_Y), s = 1 + hsh(i + 0.6) * 2.5;
      if (kind === "grass") {
        c.strokeStyle = `rgba(${90 + (hsh(i + 1) * 40) | 0},130,70,.55)`;
        c.lineWidth = 1;
        c.beginPath();
        c.moveTo(x, y);
        c.lineTo(x - s, y - s * 3);
        c.moveTo(x, y);
        c.lineTo(x + s, y - s * 2.6);
        c.stroke();
      } else {
        c.fillStyle = `rgba(${kind === "rock" ? "20,26,30" : "50,40,30"},.35)`;
        c.beginPath();
        c.ellipse(x, y, s * 1.6, s, 0, 0, 7);
        c.fill();
        c.fillStyle = "rgba(255,248,230,.12)";
        c.beginPath();
        c.ellipse(x - s * 0.3, y - s * 0.4, s * 0.9, s * 0.4, 0, 0, 7);
        c.fill();
      }
    }
  }
  c.restore();
}

/** A soft shadow on the boards under something standing there. */
function contact(c: Ctx, x: number, y: number, rx: number) {
  const g = c.createRadialGradient(x, y, 0, x, y, rx);
  g.addColorStop(0, "rgba(10,5,2,.55)");
  g.addColorStop(1, "rgba(10,5,2,0)");
  c.save();
  c.translate(x, y);
  c.scale(1, 0.22);
  c.translate(-x, -y);
  c.fillStyle = g;
  c.fillRect(x - rx, y - rx, rx * 2, rx * 2);
  c.restore();
}

// ---------------------------------------------------------------- backdrops (each returns its after-light pass)

type After = (F: Frame) => void;

function crypt(c: Ctx, sway: number, seed: number, lights: Light[]): After {
  c.save();
  c.translate(sway * 0.3, 0);
  cut(c, () => {
    c.beginPath();
    c.rect(-20, 176, W + 40, 320);
  }, "#7d756a", 0.3, 0);
  c.save();
  c.beginPath();
  c.rect(-20, 176, W + 40, 320);
  c.clip();
  stones(c, -20, 176, W + 40, 496, 22, "#8f877b", seed);
  c.restore();
  // a high grate, light falling through it
  cut(c, () => {
    c.beginPath();
    c.rect(150, 196, 54, 30);
  }, "#d9c9a0", 0.2, 0);
  c.fillStyle = "#2a2226";
  for (let i = 0; i < 5; i++) c.fillRect(154 + i * 11, 196, 3, 30);
  // a niche of skulls
  cut(c, () => {
    c.beginPath();
    c.moveTo(42, 330);
    c.lineTo(42, 270);
    c.arc(76, 270, 34, Math.PI, 0);
    c.lineTo(110, 330);
    c.closePath();
  }, lit(c, 236, 330, "#2a2226", 0.1, -0.4), 0.2, 0);
  for (let i = 0; i < 3; i++) {
    const x = 56 + i * 20, y = 314 - (i % 2) * 4;
    c.fillStyle = lit(c, y - 7, y + 7, "#e6dcc4", 0.2, -0.3);
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
  // a chain hanging from the dark
  c.strokeStyle = "#4a4650";
  c.lineWidth = 1.6;
  for (let i = 0; i < 9; i++) {
    c.beginPath();
    c.ellipse(268 + Math.sin(i * 0.4) * 1.5, 182 + i * 7, i % 2 ? 1.6 : 3, 4, 0, 0, 7);
    c.stroke();
  }
  // a torch in its bracket
  c.fillStyle = "#3e3a40";
  c.fillRect(296, 300, 8, 4);
  c.fillStyle = "#6b4524";
  c.fillRect(298, 284, 4, 18);
  lights.push({ x: 300 + sway * 0.3, y: 276, r: 120, rgb: "255,170,80" });
  lights.push({ x: 196, y: 420, r: 130, rgb: "235,225,200" });
  c.restore();
  return (F) => {
    shafts(F, 177 + sway * 0.3, 214, "235,228,205", 300, -0.22, 3, 1);
    flame(F, 300 + sway * 0.3, 280, 7, 0.4);
    embers(F, 300 + sway * 0.3, 280, 7, 3);
  };
}

function caveBack(c: Ctx, sway: number, seed: number, lights: Light[]): After {
  // a far opening, cold light beyond
  const far = c.createRadialGradient(250, 300, 4, 250, 300, 150);
  far.addColorStop(0, "rgba(140,210,220,.55)");
  far.addColorStop(1, "rgba(140,210,220,0)");
  c.fillStyle = far;
  c.fillRect(80, 150, 340, 330);
  c.save();
  c.translate(sway * 0.3, 0);
  cut(c, () => ragged(c, seed, -20, W + 20, 236, 22, 18, 500), lit(c, 210, 500, "#4f5a5c", 0.2, -0.4), 0.3);
  cut(c, () => ragged(c, seed + 1, -20, W + 20, 312, 16, 24, 500), lit(c, 290, 500, "#5f6966", 0.22, -0.4), 0.35);
  // stalactites from the roof, wet at the tips; water drips into the pools below
  const r = prng(seed + 2), tips: number[][] = [];
  for (let i = 0; i < 9; i++) {
    const x = 10 + i * 42 + r() * 20, h = 30 + r() * 60;
    cut(c, () => {
      c.beginPath();
      c.moveTo(x - 9, 150);
      c.lineTo(x + 9, 150);
      c.lineTo(x + 1, 150 + h);
      c.closePath();
    }, lit(c, 150, 150 + h, "#4a5154", 0.15, -0.3), 0.4);
    if (i % 3 === 1) tips.push([x + 1 + sway * 0.3, 150 + h]);
  }
  for (const [x, y] of [[40, 466], [318, 470], [70, 472]]) {
    c.fillStyle = "#ddd5c4";
    c.fillRect(x - 1, y - 8, 2, 8);
    c.fillStyle = "#3fb8a6";
    c.beginPath();
    c.ellipse(x, y - 8, 7, 4, 0, Math.PI, 0);
    c.fill();
    lights.push({ x: x + sway * 0.3, y: y - 10, r: 60, rgb: "90,230,210" });
  }
  lights.push({ x: 250, y: 300, r: 160, rgb: "150,210,225" });
  c.restore();
  return (F) => {
    const { T } = F;
    tips.forEach(([x, y], i) => {
      const per = 1.6 + i * 0.5, p = ((T + i * 0.7) % per) / per, land = FLOOR_Y + 14 + i * 6;
      const yy = y + p * p * (land - y) * 1.05;
      c.fillStyle = "rgba(200,240,250,.85)";
      if (yy < land) {
        c.beginPath();
        c.ellipse(x, yy, 1.2, 2.2, 0, 0, 7);
        c.fill();
      }
      // the pool it falls into, and its rings
      c.fillStyle = "rgba(120,190,210,.25)";
      c.beginPath();
      c.ellipse(x, land, 22, 4, 0, 0, 7);
      c.fill();
      const q = ((T + i * 0.7) % per) / per;
      if (q > 0.9 || q < 0.4) {
        const k = q > 0.9 ? (q - 0.9) * 2.5 : 0.25 + q * 1.9;
        c.strokeStyle = `rgba(210,245,255,${0.6 * (1 - k)})`;
        c.lineWidth = 0.8;
        c.beginPath();
        c.ellipse(x, land, 3 + k * 18, 0.8 + k * 3.4, 0, 0, 7);
        c.stroke();
      }
    });
  };
}

function wood(c: Ctx, sway: number, seed: number, lights: Light[], T: number): After {
  const sky = c.createLinearGradient(0, 150, 0, 480);
  sky.addColorStop(0, "#121a36");
  sky.addColorStop(1, "#3a3f5a");
  c.fillStyle = sky;
  c.fillRect(-20, 150, W + 40, 340);
  for (let i = 0; i < 40; i++) { // stars, twinkling
    const x = hsh(i) * W, y = 156 + hsh(i + 0.5) * 140, a = 0.35 + 0.5 * Math.abs(Math.sin(T * (1 + hsh(i + 2)) + i));
    c.fillStyle = `rgba(240,240,255,${a})`;
    c.fillRect(x, y, 1, 1);
  }
  const halo = c.createRadialGradient(270, 210, 18, 270, 210, 90);
  halo.addColorStop(0, "rgba(220,225,255,.35)");
  halo.addColorStop(1, "rgba(220,225,255,0)");
  c.fillStyle = halo;
  c.fillRect(180, 120, 180, 180);
  c.fillStyle = "#efe8cf";
  c.beginPath();
  c.arc(270, 210, 22, 0, 7);
  c.fill();
  c.fillStyle = "rgba(200,190,160,.35)";
  c.beginPath();
  c.arc(264, 204, 5, 0, 7);
  c.arc(277, 218, 3.5, 0, 7);
  c.fill();
  // a cloud drifting over the moon
  const cx = ((T * 6) % (W + 200)) - 100;
  c.fillStyle = "rgba(40,48,80,.75)";
  for (const [dx, dy, r] of [[0, 0, 18], [18, -6, 16], [36, 2, 14], [-16, 4, 12]]) {
    c.beginPath();
    c.ellipse(cx + dx, 214 + dy, r * 1.6, r * 0.7, 0, 0, 7);
    c.fill();
  }
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
      }, lit(c, y - h, y, col, 0.15, -0.35), 0.35);
    }
    c.restore();
  };
  trees(1, "#22392c", 470, 6, 0.3);
  // mist between the rows of trees
  const mist = c.createLinearGradient(0, 380, 0, 480);
  mist.addColorStop(0, "rgba(150,170,190,0)");
  mist.addColorStop(1, "rgba(150,170,190,.32)");
  c.fillStyle = mist;
  c.fillRect(-20, 380, W + 40, 100);
  trees(2, "#2d553a", 486, 4, 0.6);
  return (F) => {
    shafts(F, 262, 214, "210,220,255", 330, 0.42, 3, 0.9);
    for (let i = 0; i < 10; i++) { // fireflies, glowing
      const x = 30 + ((i * 47 + F.T * 9) % 300), y = 300 + Math.sin(F.T * 1.3 + i) * 40 + (i % 3) * 30;
      const a = 0.45 + 0.45 * Math.sin(F.T * 3 + i);
      const g = c.createRadialGradient(x, y, 0, x, y, 7);
      g.addColorStop(0, `rgba(230,255,150,${a})`);
      g.addColorStop(1, "rgba(230,255,150,0)");
      c.fillStyle = g;
      c.fillRect(x - 7, y - 7, 14, 14);
    }
  };
}

function peaks(c: Ctx, sway: number, seed: number, lights: Light[], T: number): After {
  const sky = c.createLinearGradient(0, 150, 0, 480);
  sky.addColorStop(0, "#2e2342");
  sky.addColorStop(0.55, "#a8604f");
  sky.addColorStop(1, "#f0b070");
  c.fillStyle = sky;
  c.fillRect(-20, 150, W + 40, 340);
  const sun = c.createRadialGradient(110, 420, 6, 110, 420, 170);
  sun.addColorStop(0, "rgba(255,225,160,.9)");
  sun.addColorStop(0.15, "rgba(255,200,140,.45)");
  sun.addColorStop(1, "rgba(255,170,120,0)");
  c.fillStyle = sun;
  c.fillRect(-60, 250, 340, 340);
  lights.push({ x: 110, y: 420, r: 280, rgb: "255,180,120" });
  // clouds drifting at two speeds
  for (let i = 0; i < 4; i++) {
    const x = ((hsh(i) * (W + 200) + T * (4 + i * 2)) % (W + 200)) - 100, y = 190 + i * 22;
    c.fillStyle = `rgba(${i < 2 ? "120,80,110" : "230,150,130"},.45)`;
    c.beginPath();
    c.ellipse(x, y, 60 + i * 10, 7 + i * 1.5, 0, 0, 7);
    c.fill();
  }
  c.save();
  c.translate(sway * 0.2, 0);
  const ridge = () => {
    c.beginPath();
    c.moveTo(-20, 470);
    c.lineTo(60, 250);
    c.lineTo(120, 330);
    c.lineTo(200, 210);
    c.lineTo(290, 320);
    c.lineTo(W + 20, 260);
    c.lineTo(W + 20, 470);
    c.closePath();
  };
  cut(c, ridge, lit(c, 210, 470, "#6e6a7a", 0.18, -0.35), 0.3);
  // snow on the peaks
  c.fillStyle = "rgba(245,240,250,.85)";
  for (const [x, y] of [[60, 250], [200, 210], [W + 20, 260]]) {
    c.beginPath();
    c.moveTo(x - 18, y + 30);
    c.lineTo(x, y);
    c.lineTo(x + 18, y + 30);
    c.lineTo(x + 8, y + 24);
    c.lineTo(x, y + 32);
    c.lineTo(x - 8, y + 24);
    c.closePath();
    c.fill();
  }
  c.restore();
  c.save();
  c.translate(sway * 0.5, 0);
  cut(c, () => ragged(c, seed, -20, W + 20, 400, 26, 30, 500), lit(c, 370, 500, "#8a8478", 0.2, -0.4), 0.4);
  c.restore();
  return (F) => {
    c.save();
    c.strokeStyle = "rgba(255,240,230,.35)";
    c.lineWidth = 0.8;
    for (let i = 0; i < 14; i++) { // wind
      const p = ((F.T * 0.9 + hsh(i)) % 1), x = -40 + p * (W + 80), y = 260 + hsh(i + 1) * 200;
      c.beginPath();
      c.moveTo(x, y);
      c.lineTo(x + 18 + hsh(i + 2) * 20, y - 2);
      c.stroke();
    }
    c.restore();
  };
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
    cut(c, shape, "#16201a", 0.7, 0);
    const r = prng(seed);
    for (let i = 0; i < 26; i++) {
      const a = (i / 26) * Math.PI, x = W / 2 - Math.cos(a) * (W / 2 - 10), y = 300 - Math.sin(a) * 120;
      c.fillStyle = i % 3 ? "#2d4a34" : "#3a5e40";
      c.beginPath();
      c.ellipse(x + (r() - 0.5) * 12, y + (r() - 0.5) * 12, 16, 8, a + r(), 0, 7);
      c.fill();
    }
  } else {
    cut(c, shape, "#3a3236", 0.7, 0);
    c.save();
    shape();
    c.clip();
    stones(c, -30, 150, W + 30, H + 20, 26, "#4a4146", seed);
    c.restore();
    // the arch's inner edge catches the light
    c.strokeStyle = "rgba(255,230,190,.25)";
    c.lineWidth = 2;
    c.beginPath();
    c.moveTo(W - 15, H);
    c.lineTo(W - 15, 300);
    c.bezierCurveTo(W - 15, 176, 15, 176, 15, 300);
    c.lineTo(15, H);
    c.stroke();
  }
  c.restore();
}

// ---------------------------------------------------------------- the stage

export function drawStage(F: Frame, scene: string, thing: string | undefined, defs: Defs, cast: StageCast, a: number) {
  const { c, T } = F;
  void defs;
  const sway = Math.sin(T * 0.5) * 3, seed = 7, mood = moodOf(scene);
  const push = 1 + 0.05 * a; // a slow dolly in while the beat plays
  const lights: Light[] = [];
  c.save();
  c.fillStyle = "#0c080c";
  c.fillRect(0, 0, W, H);
  c.translate(W / 2, FLOOR_Y);
  c.scale(push, push);
  c.translate(-W / 2, -FLOOR_Y);
  const open = scene === "forest" || scene === "mountain";
  const after = scene === "cave" ? caveBack(c, sway, seed, lights)
    : scene === "forest" ? wood(c, sway, seed, lights, T)
      : scene === "mountain" ? peaks(c, sway, seed, lights, T)
        : crypt(c, sway, seed, lights);
  floor(c, scene === "forest" ? "#3d4a2c" : scene === "mountain" ? "#7d6a52" : scene === "cave" ? "#454c4c" : "#5d5650",
    scene === "forest" ? "grass" : scene === "mountain" ? "scree" : scene === "cave" ? "rock" : "flags");

  // the object, cut out large on the boards, its glow behind it
  const th = thing ? THINGS[thing] : undefined;
  const [tx, ty] = [THING_AT[0] + sway, THING_AT[1]];
  if (th) {
    contact(c, tx + 6, ty + 2, 110);
    rays(F, tx + th.eye[0] * THING_K, ty + th.eye[1] * THING_K * 0.9, 120, th.glow || "255,214,150", 0.45);
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
  const shown = lights.map((l) => ({ ...l, x: W / 2 + (l.x - W / 2) * push, y: FLOOR_Y + (l.y - FLOOR_Y) * push }));
  lighting(F, shown, 0.48);

  // after the light: what glows or moves in it
  c.save();
  c.translate(W / 2, FLOOR_Y);
  c.scale(push, push);
  c.translate(-W / 2, -FLOOR_Y);
  after(F);
  if (th) {
    markers(th.prop).flames.forEach(([fx, fy, fs], i) => {
      flame(F, tx + fx * THING_K, ty + fy * THING_K * 0.9, fs * THING_K, i * 1.7);
      embers(F, tx + fx * THING_K, ty + fy * THING_K * 0.9, fs * THING_K, i + 5);
    });
    if (th.live) {
      c.save();
      c.translate(tx, ty);
      c.scale(THING_K, THING_K * 0.9);
      th.live(c, T);
      c.restore();
    }
  }
  c.restore();
  motes(F, mood, shown, 30);
  fog(F, { ...mood, fog: mood.fog || "190,180,170" }, FLOOR_Y - 30, FLOOR_Y + 70, 1.2);
  // the top of the frame stays dark for the narration
  const top = c.createLinearGradient(0, 130, 0, 160);
  top.addColorStop(0, "#0c080c");
  top.addColorStop(1, "rgba(12,8,12,0)");
  c.fillStyle = "#0c080c";
  c.fillRect(0, 0, W, 130);
  c.fillStyle = top;
  c.fillRect(0, 130, W, 30);
}
