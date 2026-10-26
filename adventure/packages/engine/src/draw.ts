// Frame-level drawing pieces from the prototype: paper cards, text, the hook title, typed narration,
// hand-drawn loop and star, and the standee token. Everything works in the 360×640 logical space;
// `dpr` scales the things canvas doesn't transform (shadow blur and offsets).
import type { Creature } from "./defs.ts";
import { dsl } from "./dsl.ts";
import { type Ctx, DISPLAY, H, INK, W, cl, ez, font, lp, seg, wrap } from "./util.ts";

export type Frame = { c: Ctx; dpr: number; T: number };

export function parch(F: Frame, x: number, y: number, w: number, h: number, hl?: string, tape = true) {
  const { c, dpr } = F;
  c.save();
  c.shadowColor = "rgba(30,15,0,.45)";
  c.shadowBlur = 9 * dpr;
  c.shadowOffsetX = 3 * dpr;
  c.shadowOffsetY = 5 * dpr;
  c.fillStyle = hl || "#fbf6e4";
  c.strokeStyle = INK;
  c.lineWidth = 2.2;
  const j = (k: number) => Math.sin(x * 3.1 + y * 1.7 + k * 9.3) * 2;
  c.beginPath();
  c.moveTo(x + j(1), y + j(2));
  c.lineTo(x + w / 2 + j(3), y + j(4));
  c.lineTo(x + w + j(5), y + j(6));
  c.lineTo(x + w + j(7), y + h / 2 + j(8));
  c.lineTo(x + w + j(9), y + h + j(10));
  c.lineTo(x + w / 2 + j(11), y + h + j(12));
  c.lineTo(x + j(13), y + h + j(14));
  c.lineTo(x + j(15), y + h / 2 + j(16));
  c.closePath();
  c.fill();
  c.shadowColor = "transparent";
  c.stroke();
  if (tape) {
    c.fillStyle = "rgba(255,226,120,.55)";
    c.save();
    c.translate(x + w - 26, y - 3);
    c.rotate(0.35);
    c.fillRect(-14, -5, 28, 10);
    c.restore();
  }
  c.restore();
}

export function txt(F: Frame, t: string, x: number, y: number, z: number, col = INK, al: CanvasTextAlign = "center", w: number | string = 700) {
  const { c } = F;
  c.font = font(w, z);
  c.textAlign = al;
  c.textBaseline = "alphabetic";
  c.fillStyle = col;
  c.fillText(t, x, y);
}

/** Text shrunk to fit a width. */
export function fit(F: Frame, t: string, x: number, y: number, z: number, maxW: number, col = INK, al: CanvasTextAlign = "center", w: number | string = 700) {
  F.c.font = font(w, z);
  const m = F.c.measureText(t).width;
  txt(F, t, x, y, m > maxW ? (z * maxW) / m : z, col, al, w);
}

/** The hook title: slams in from 2.6× scale. */
export function big(F: Frame, t: string, x: number, y: number, z: number, col: string, a0: number, a1: number) {
  const { c, T } = F;
  if (T < a0) return;
  const sc = lp(2.6, 1, ez(seg(T, a0, a1)));
  c.save();
  c.translate(x, y);
  c.scale(sc, sc);
  c.font = `${z}px ${DISPLAY}`;
  c.textAlign = "center";
  const m = c.measureText(t).width;
  if (m > W - 40) c.scale((W - 40) / m, (W - 40) / m);
  c.lineWidth = 7;
  c.lineJoin = "round";
  c.strokeStyle = "#000";
  c.strokeText(t, 0, 0);
  c.fillStyle = col;
  c.fillText(t, 0, 0);
  c.restore();
}

/** Narration card that types itself out between a and b. */
export function narr(F: Frame, t: string | undefined, a: number, b: number, y = 112) {
  const { c, T } = F;
  if (!t || T < a || T > b) return;
  c.font = font(600, 15);
  const shown = t.slice(0, Math.floor(((T - a + 0.1) * t.length) / Math.max(1, (b - a) * 0.55)));
  const all = wrap(c, t, W - 108), ls = wrap(c, shown, W - 108);
  parch(F, 16, y, W - 76, Math.max(all.length * 20 + 18, 40));
  c.font = font(600, 15);
  c.fillStyle = INK;
  c.textAlign = "left";
  ls.forEach((l, i) => c.fillText(l, 30, y + 24 + i * 20));
}

export function loop(F: Frame, cx: number, cy: number, rx: number, ry: number, p: number, col: string) {
  const { c } = F;
  c.strokeStyle = col;
  c.lineWidth = 3;
  c.lineCap = "round";
  c.beginPath();
  for (let a = 0; a <= 6.6 * p; a += 0.1) {
    const x = cx + Math.cos(a - 1.57) * (rx + Math.sin(a * 3) * 3 + a * 0.6), y = cy + Math.sin(a - 1.57) * (ry + Math.cos(a * 2) * 3 + a * 0.6);
    a ? c.lineTo(x, y) : c.moveTo(x, y);
  }
  c.stroke();
}

export function star(F: Frame, x: number, y: number, r: number, sc: number) {
  const { c } = F;
  c.save();
  c.translate(x, y);
  c.scale(sc, sc);
  c.beginPath();
  for (let i = 0; i < 10; i++) {
    const q = (i * Math.PI) / 5 - Math.PI / 2, rr = i % 2 ? r * 0.45 : r;
    c.lineTo(Math.cos(q) * rr, Math.sin(q) * rr);
  }
  c.closePath();
  c.fillStyle = "#ffd23f";
  c.strokeStyle = INK;
  c.lineWidth = 2.2;
  c.fill();
  c.stroke();
  c.restore();
}

/** A hand-drawn heart; `broken` 0..1 cracks it in two and greys it out. */
export function heart(F: Frame, x: number, y: number, r: number, broken = 0) {
  const { c } = F;
  const shape = () => {
    c.beginPath();
    c.moveTo(0, r * 0.9);
    c.bezierCurveTo(-r * 1.35, 0, -r * 0.95, -r * 1.05, 0, -r * 0.35);
    c.bezierCurveTo(r * 0.95, -r * 1.05, r * 1.35, 0, 0, r * 0.9);
    c.closePath();
  };
  for (const side of [-1, 1]) {
    c.save();
    c.translate(x + side * broken * r * 0.35, y + broken * r * 0.15);
    c.rotate(side * broken * 0.3);
    c.beginPath();
    // each half is clipped along a zigzag crack down the middle
    c.moveTo(0, -r * 1.2);
    [[0.15, -0.4], [-0.12, -0.05], [0.12, 0.3], [0, 1]].forEach(([dx, dy]) => c.lineTo(dx * r, dy * r));
    c.lineTo(side * r * 2, r * 1.2);
    c.lineTo(side * r * 2, -r * 1.2);
    c.closePath();
    c.clip();
    shape();
    c.fillStyle = broken > 0.5 ? "#5d6169" : RED_HEART;
    c.fill();
    c.strokeStyle = INK;
    c.lineWidth = 2.2;
    c.stroke();
    c.fillStyle = "rgba(255,255,255,.45)";
    c.beginPath();
    c.ellipse(-r * 0.45, -r * 0.35, r * 0.18, r * 0.12, -0.6, 0, 7);
    c.fill();
    c.restore();
  }
}
const RED_HEART = "#d64541";

const ELV = (52 * Math.PI) / 180;

/** A token: bevelled base, cast and contact shadows, and the shaded upright figure. */
export function standee(F: Frame, d: Creature, x: number, y: number, sc: number, face: number, t: number, ph: number) {
  const { c, dpr } = F;
  const r = (d.r || 17) * sc, ry = Math.sin(ELV), hs = 0.45 + 0.55 * Math.cos(ELV), th = r * 0.3 * Math.cos(ELV) + 2, fl = d.float;
  const bob = fl ? (Math.sin(t * 2 + ph) * 3 + 9) * sc : Math.abs(Math.sin(t * 3 + ph)) * (d.hop ? 5 : 1.5) * sc;
  const sx = face * sc * (0.9 + 0.1 * Math.cos(t * 1.3 + ph)), sy = sc * hs * (d.hop ? 1 + 0.07 * Math.sin(t * 6 + ph) : 1);
  c.save();
  c.translate(x, y);
  c.lineJoin = "round";
  if (fl) {
    c.fillStyle = "rgba(20,10,0,.25)";
    c.beginPath();
    c.ellipse(0, r * 0.3, r * 0.9 * (1 - bob / 120), r * 0.9 * ry * 0.45, 0, 0, 7);
    c.fill();
  } else {
    c.save();
    c.shadowColor = "rgba(20,10,0,.55)";
    c.shadowBlur = r * 0.5 * dpr;
    c.shadowOffsetX = r * 0.35 * dpr;
    c.shadowOffsetY = (th + r * 0.25) * dpr;
    c.fillStyle = "#6e6140";
    c.beginPath();
    c.ellipse(0, th, r, r * ry, 0, 0, 7);
    c.fill();
    c.restore();
    const sg = c.createLinearGradient(-r, 0, r, 0);
    sg.addColorStop(0, "#c2b384");
    sg.addColorStop(0.6, "#8a7a55");
    sg.addColorStop(1, "#4f452b");
    c.fillStyle = sg;
    c.strokeStyle = "#1b2146";
    c.lineWidth = 2;
    c.beginPath();
    c.moveTo(r, 0);
    c.lineTo(r, th);
    c.ellipse(0, th, r, r * ry, 0, 0, Math.PI);
    c.lineTo(-r, 0);
    c.closePath();
    c.fill();
    c.stroke();
    const gr = c.createRadialGradient(-r * 0.3, -r * ry * 0.3, 2, 0, 0, r);
    gr.addColorStop(0, "#fff");
    gr.addColorStop(1, d.base || "#d9c99a");
    c.fillStyle = gr;
    c.beginPath();
    c.ellipse(0, 0, r, r * ry, 0, 0, 7);
    c.fill();
    c.stroke();
    c.strokeStyle = "rgba(255,255,255,.6)";
    c.lineWidth = 1.4;
    c.beginPath();
    c.ellipse(0, 0, r * 0.82, r * ry * 0.82, 0, 0, 7);
    c.stroke();
    c.strokeStyle = "rgba(0,0,0,.18)";
    c.beginPath();
    c.ellipse(0.6, 0.6, r * 0.78, r * ry * 0.78, 0, 0, 7);
    c.stroke();
  }
  c.fillStyle = "rgba(20,10,0,.28)";
  c.beginPath();
  c.ellipse(0, 1, r * 0.55, r * ry * 0.3, 0, 0, 7);
  c.fill();
  c.save();
  c.scale(sx, sc);
  c.transform(1, 0, -0.6, -0.35 * ry, 0, 0);
  dsl(c, d.parts, { sil: true });
  c.restore();
  c.translate(0, -bob);
  if (d.glow) {
    const q = c.createRadialGradient(0, -26 * sc * hs, 2, 0, -26 * sc * hs, 44 * sc);
    q.addColorStop(0, "rgba(185,163,232,.45)");
    q.addColorStop(1, "rgba(185,163,232,0)");
    c.fillStyle = q;
    c.fillRect(-50 * sc, -80 * sc, 100 * sc, 100 * sc);
  }
  c.scale(sx, sy);
  dsl(c, d.parts, { ink: "#1b2146", lw: 1.8 / sc, sh: true });
  c.restore();
}

/** The warm flickering light over everything (prototype: end of frame()). */
export function flicker(F: Frame) {
  const { c, T } = F;
  const fk = 0.1 + 0.03 * Math.sin(T * 9) + 0.02 * Math.sin(T * 23), lg = c.createRadialGradient(70, 110, 10, 70, 110, 540);
  lg.addColorStop(0, `rgba(255,215,140,${fk + 0.1})`);
  lg.addColorStop(1, "rgba(255,215,140,0)");
  c.fillStyle = lg;
  c.fillRect(0, 0, W, H);
}

export const fade = (T: number, a: number, b: number, inn = 0.4, out = 0.4) => ez(seg(T, a, a + inn)) * (1 - seg(T, b - out, b));
export { cl };
