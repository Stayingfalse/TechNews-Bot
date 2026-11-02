// Atmosphere: what makes a frame feel lit and alive rather than drawn. A colour grade per scene
// (warm candlelight in the crypt, cold teal in the caves, moonlight in the wood, dusk on the
// mountain), a vignette, a moving film grain made from the paper texture, dust drifting in the
// pools of light, embers over flames, fog, light shafts, and the iris wipe between map and stage.
// All of it is a function of time and position only: the same frame always comes out the same.
import type { Frame, Light } from "./draw.ts";
import { H, W, cl, ez, seg } from "./util.ts";

type Ctx = CanvasRenderingContext2D;
export type Mood = { shade: string; key: string; mote: string; fog?: string; grain: number };

export const MOODS: Record<string, Mood> = {
  dungeon: { shade: "34,22,58", key: "255,184,104", mote: "255,222,170", grain: 0.16 },
  cave: { shade: "8,40,58", key: "130,224,214", mote: "205,240,255", fog: "150,185,195", grain: 0.16 },
  forest: { shade: "18,36,70", key: "205,230,185", mote: "230,255,160", fog: "165,195,190", grain: 0.14 },
  mountain: { shade: "58,28,78", key: "255,176,128", mote: "255,232,205", fog: "225,205,215", grain: 0.14 },
};
export const moodOf = (scene: string): Mood => MOODS[scene] || MOODS.dungeon;

/** A cheap deterministic hash in [0, 1). */
const h = (n: number) => {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};

/** Colour grade: the key light's warmth in the middle, the mood's shade in the corners, a little
 *  contrast (soft light), then the vignette. `k` scales it (0 = off). */
export function grade(F: Frame, m: Mood, k = 1, cx = W / 2, cy = H * 0.46) {
  const { c } = F;
  if (k <= 0) return;
  c.save();
  c.globalCompositeOperation = "soft-light";
  const g = c.createRadialGradient(cx, cy, 30, cx, cy, H * 0.75);
  g.addColorStop(0, `rgba(${m.key},${0.5 * k})`);
  g.addColorStop(0.5, `rgba(${m.key},${0.12 * k})`);
  g.addColorStop(1, `rgba(${m.shade},${0.95 * k})`);
  c.fillStyle = g;
  c.fillRect(0, 0, W, H);
  c.globalCompositeOperation = "source-over";
  // the mood's shade pooled in the dark (multiply keeps the lit middle clean)
  c.globalCompositeOperation = "multiply";
  const t = c.createRadialGradient(cx, cy, H * 0.12, cx, cy, H * 0.6);
  t.addColorStop(0, "rgba(255,255,255,0)");
  t.addColorStop(1, `rgba(${m.shade},${0.35 * k})`);
  c.fillStyle = t;
  c.fillRect(0, 0, W, H);
  c.globalCompositeOperation = "source-over";
  const v = c.createRadialGradient(cx, cy, H * 0.22, cx, cy, H * 0.7);
  v.addColorStop(0, "rgba(6,3,8,0)");
  v.addColorStop(1, `rgba(6,3,8,${0.7 * k})`);
  c.fillStyle = v;
  c.fillRect(0, 0, W, H);
  c.restore();
}

/** Film grain from the paper texture, shifted every frame (12 a second, like old film). */
export function grain(F: Frame, m: Mood) {
  const { c, T, paper } = F;
  if (!paper) return;
  const f = Math.floor(T * 12), ox = h(f) * 180, oy = h(f + 0.5) * 180, s = 200;
  c.save();
  c.globalCompositeOperation = "overlay";
  c.globalAlpha = m.grain;
  for (let y = -oy; y < H; y += s) for (let x = -ox; x < W; x += s) c.drawImage(paper as unknown as CanvasImageSource, x, y, s, s);
  c.restore();
}

/** Dust drifting in each pool of light (a few motes per light, nearest lights first). */
export function motes(F: Frame, m: Mood, lights: Light[], max = 36) {
  const { c, T } = F;
  c.save();
  c.globalCompositeOperation = "lighter";
  let n = 0;
  lights.forEach((l, li) => {
    for (let i = 0; i < 4 && n < max; i++, n++) {
      const k = li * 7.3 + i, life = 5 + h(k) * 4, ph = ((T + h(k + 1) * life) % life) / life;
      const x = l.x + (h(k + 2) - 0.5) * l.r * 1.1 + Math.sin(T * 0.7 + k) * 6, y = l.y + (h(k + 3) - 0.4) * l.r * 0.9 - ph * 26;
      const a = Math.sin(ph * Math.PI) * (0.35 + h(k + 4) * 0.4);
      c.fillStyle = `rgba(${m.mote},${a})`;
      c.beginPath();
      c.arc(x, y, 0.5 + h(k + 5) * 0.9, 0, 7);
      c.fill();
    }
  });
  c.restore();
}

/** Sparks rising off a flame. */
export function embers(F: Frame, x: number, y: number, s: number, ph: number) {
  const { c, T } = F;
  c.save();
  c.globalCompositeOperation = "lighter";
  for (let i = 0; i < 3; i++) {
    const k = ph * 13 + i, life = 1.4 + h(k) * 1.2, p = ((T + h(k + 1) * life) % life) / life;
    const ex = x + Math.sin(T * 3 + k) * s * 0.6 + (h(k + 2) - 0.5) * s, ey = y - s * 1.5 - p * s * 7;
    c.fillStyle = `rgba(255,${150 + (h(k + 3) * 80) | 0},70,${(1 - p) * 0.85})`;
    c.beginPath();
    c.arc(ex, ey, 0.5 + (1 - p) * 0.6, 0, 7);
    c.fill();
  }
  c.restore();
}

/** Slow banks of fog drifting sideways between y0 and y1. */
export function fog(F: Frame, m: Mood, y0: number, y1: number, a = 1) {
  const { c, T } = F;
  if (!m.fog || a <= 0) return;
  c.save();
  c.globalCompositeOperation = "screen";
  for (let i = 0; i < 6; i++) {
    const sp = 4 + h(i) * 6, x = ((h(i + 1) * (W + 240) + T * sp) % (W + 240)) - 120, y = y0 + h(i + 2) * (y1 - y0);
    const rx = 90 + h(i + 3) * 80, ry = 18 + h(i + 4) * 22;
    const g = c.createRadialGradient(x, y, 0, x, y, rx);
    g.addColorStop(0, `rgba(${m.fog},${0.13 * a})`);
    g.addColorStop(1, `rgba(${m.fog},0)`);
    c.fillStyle = g;
    c.save();
    c.translate(x, y);
    c.scale(1, ry / rx);
    c.translate(-x, -y);
    c.fillRect(x - rx, y - rx, rx * 2, rx * 2);
    c.restore();
  }
  c.restore();
}

/** Beams of light falling from (x, y) at an angle, slowly breathing. */
export function shafts(F: Frame, x: number, y: number, rgb: string, len = 420, angle = 0.35, n = 3, a = 1) {
  const { c, T } = F;
  c.save();
  c.globalCompositeOperation = "lighter";
  c.translate(x, y);
  c.rotate(angle);
  for (let i = 0; i < n; i++) {
    const w0 = 6 + i * 5, w1 = 40 + i * 26 + Math.sin(T * 0.6 + i) * 8, off = (i - (n - 1) / 2) * 14;
    const g = c.createLinearGradient(0, 0, 0, len);
    const al = (0.07 + 0.03 * Math.sin(T * 0.8 + i * 2)) * a;
    g.addColorStop(0, `rgba(${rgb},${al})`);
    g.addColorStop(1, `rgba(${rgb},0)`);
    c.fillStyle = g;
    c.beginPath();
    c.moveTo(off - w0, 0);
    c.lineTo(off + w0, 0);
    c.lineTo(off + w1, len);
    c.lineTo(off - w1, len);
    c.closePath();
    c.fill();
  }
  c.restore();
}

/** A slowly turning crown of rays round something precious (the close-up's object). */
export function rays(F: Frame, x: number, y: number, r: number, rgb: string, a: number) {
  const { c, T } = F;
  if (a <= 0) return;
  c.save();
  c.globalCompositeOperation = "lighter";
  const g = c.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, `rgba(${rgb},${0.28 * a})`);
  g.addColorStop(1, `rgba(${rgb},0)`);
  c.fillStyle = g;
  c.fillRect(x - r, y - r, r * 2, r * 2);
  c.translate(x, y);
  c.rotate(T * 0.12);
  for (let i = 0; i < 10; i++) {
    const rr = r * (0.75 + 0.25 * Math.sin(T * 1.3 + i * 1.9));
    c.rotate((Math.PI * 2) / 10);
    const gr = c.createLinearGradient(0, 0, rr, 0);
    gr.addColorStop(0, `rgba(${rgb},${0.16 * a})`);
    gr.addColorStop(1, `rgba(${rgb},0)`);
    c.fillStyle = gr;
    c.beginPath();
    c.moveTo(0, -2);
    c.lineTo(rr, -9);
    c.lineTo(rr, 9);
    c.lineTo(0, 2);
    c.closePath();
    c.fill();
  }
  c.restore();
}

/** An iris wipe: black everywhere outside a circle of radius `r` round (x, y), with an inky edge. */
export function iris(F: Frame, x: number, y: number, r: number) {
  const { c } = F;
  if (r > H * 1.3) return;
  c.save();
  c.beginPath();
  c.rect(-40, -40, W + 80, H + 80);
  c.arc(x, y, Math.max(0.1, r), 0, Math.PI * 2, true);
  c.fillStyle = "#08050a";
  c.fill("evenodd");
  if (r > 2) {
    const g = c.createRadialGradient(x, y, r * 0.82, x, y, r);
    g.addColorStop(0, "rgba(8,5,10,0)");
    g.addColorStop(1, "rgba(8,5,10,.85)");
    c.fillStyle = g;
    c.beginPath();
    c.arc(x, y, r, 0, 7);
    c.fill();
  }
  c.restore();
}

/** How far the iris is open at time T for a cut at `at` (closing before it, opening after). */
export function irisR(T: number, at: number, dur = 0.38): number | null {
  const d = Math.abs(T - at);
  if (d > dur) return null;
  return ez(cl(d / dur, 0, 1)) * H * 1.3;
}

export { seg };
