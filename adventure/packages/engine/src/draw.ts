// Frame-level drawing pieces from the prototype: paper cards, text, the hook title, typed narration,
// hand-drawn loop and star, and the standee token. Everything works in the 360×640 logical space;
// `dpr` scales the things canvas doesn't transform (shadow blur and offsets).
import type { Creature } from "./defs.ts";
import { dsl } from "./dsl.ts";
import { type Canvas, type Ctx, CREAM, DISPLAY, GOLD, H, INK, RED, W, cl, dfont, ez, font, lp, seg, shade, wrap } from "./util.ts";

/** One frame being drawn. `paper` is a grain texture for cards; `dark` a scratch canvas for the lighting. */
export type Frame = { c: Ctx; dpr: number; T: number; paper?: Canvas; dark?: Canvas };

/** A torn parchment card: grain, darkened edges, a fine ink border and a soft drop shadow. */
export function parch(F: Frame, x: number, y: number, w: number, h: number, hl?: string) {
  const { c, dpr } = F;
  const j = (k: number) => Math.sin(x * 3.1 + y * 1.7 + k * 9.3) * 1.2 + Math.sin(k * 4.7 + w) * 0.6;
  const edge = () => {
    c.beginPath();
    const nx = Math.max(3, Math.round(w / 14)), ny = Math.max(2, Math.round(h / 14));
    let k = 0;
    for (let i = 0; i <= nx; i++) c.lineTo(x + (w * i) / nx + j(k++), y + j(k++));
    for (let i = 1; i <= ny; i++) c.lineTo(x + w + j(k++), y + (h * i) / ny + j(k++));
    for (let i = nx - 1; i >= 0; i--) c.lineTo(x + (w * i) / nx + j(k++), y + h + j(k++));
    for (let i = ny - 1; i > 0; i--) c.lineTo(x + j(k++), y + (h * i) / ny + j(k++));
    c.closePath();
  };
  const base = hl || "#efe0bd";
  c.save();
  c.shadowColor = "rgba(20,10,0,.55)";
  c.shadowBlur = 10 * dpr;
  c.shadowOffsetX = 2 * dpr;
  c.shadowOffsetY = 5 * dpr;
  edge();
  const gr = c.createLinearGradient(x, y, x + w * 0.3, y + h);
  gr.addColorStop(0, shade(base, 0.25));
  gr.addColorStop(1, base);
  c.fillStyle = gr;
  c.fill();
  c.shadowColor = "transparent";
  c.clip();
  if (F.paper) {
    c.globalAlpha = 0.9;
    c.drawImage(F.paper as unknown as CanvasImageSource, (x * 7) % 200, (y * 5) % 200, w * 3, h * 3, x, y, w, h);
    c.globalAlpha = 1;
  }
  // scorched rim
  c.lineWidth = 7;
  c.strokeStyle = "rgba(120,70,20,.22)";
  edge();
  c.stroke();
  c.restore();
  c.save();
  c.lineWidth = 1.2;
  c.strokeStyle = "rgba(42,29,20,.8)";
  edge();
  c.stroke();
  c.restore();
}

/** A wax seal with a letter pressed into it. */
export function seal(F: Frame, x: number, y: number, r: number, letter: string, col = "#a3291d") {
  const { c, dpr } = F;
  c.save();
  c.shadowColor = "rgba(20,5,0,.5)";
  c.shadowBlur = 4 * dpr;
  c.shadowOffsetY = 2 * dpr;
  c.beginPath();
  for (let i = 0; i <= 28; i++) {
    const a = (i / 28) * Math.PI * 2, rr = r * (1 + 0.07 * Math.sin(i * 2.7 + x) + 0.05 * Math.sin(i * 5.3 + y));
    c.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr);
  }
  c.closePath();
  const gr = c.createRadialGradient(x - r * 0.35, y - r * 0.4, r * 0.1, x, y, r * 1.1);
  gr.addColorStop(0, shade(col, 0.35));
  gr.addColorStop(0.55, col);
  gr.addColorStop(1, shade(col, -0.45));
  c.fillStyle = gr;
  c.fill();
  c.restore();
  c.save();
  c.lineWidth = r * 0.12;
  c.strokeStyle = shade(col, -0.35);
  c.beginPath();
  c.arc(x, y, r * 0.72, 0, 7);
  c.stroke();
  c.font = dfont(900, r * 1.05);
  c.textAlign = "center";
  c.textBaseline = "middle";
  c.fillStyle = shade(col, -0.55);
  c.fillText(letter, x + r * 0.05, y + r * 0.1);
  c.fillStyle = shade(col, 0.55);
  c.fillText(letter, x - r * 0.03, y + r * 0.02);
  c.restore();
}

/** A red ribbon banner with folded tails. */
export function ribbon(F: Frame, cx: number, cy: number, w: number, h: number, text: string) {
  const { c, dpr } = F;
  const x0 = cx - w / 2, x1 = cx + w / 2, t = h * 0.75;
  c.save();
  c.shadowColor = "rgba(20,5,0,.5)";
  c.shadowBlur = 8 * dpr;
  c.shadowOffsetY = 4 * dpr;
  for (const side of [-1, 1]) {
    const xe = side < 0 ? x0 : x1, xo = xe + side * t;
    c.fillStyle = shade("#8e241a", -0.25);
    c.beginPath();
    c.moveTo(xe - side * 6, cy - h / 2 + 7);
    c.lineTo(xo, cy - h / 2 + 7);
    c.lineTo(xo - side * 8, cy + 7);
    c.lineTo(xo, cy + h / 2 + 7);
    c.lineTo(xe - side * 6, cy + h / 2 + 7);
    c.closePath();
    c.fill();
  }
  c.restore();
  const gr = c.createLinearGradient(0, cy - h / 2, 0, cy + h / 2);
  gr.addColorStop(0, "#b8392a");
  gr.addColorStop(0.5, "#9b2c1e");
  gr.addColorStop(1, "#7a2016");
  c.fillStyle = gr;
  c.beginPath();
  c.moveTo(x0, cy - h / 2);
  c.quadraticCurveTo(cx, cy - h / 2 - 4, x1, cy - h / 2);
  c.lineTo(x1, cy + h / 2);
  c.quadraticCurveTo(cx, cy + h / 2 - 4, x0, cy + h / 2);
  c.closePath();
  c.fill();
  c.strokeStyle = GOLD;
  c.lineWidth = 1.2;
  c.stroke();
  c.save();
  c.font = dfont(900, h * 0.48);
  const m = c.measureText(text).width, sc = Math.min(1, (w - 24) / m);
  c.translate(cx, cy + h * 0.17);
  c.scale(sc, sc);
  c.textAlign = "center";
  c.fillStyle = "rgba(40,5,0,.6)";
  c.fillText(text, 0, 1.5);
  c.fillStyle = CREAM;
  c.fillText(text, 0, 0);
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

/** Text in the display face (Cinzel). */
export function dtxt(F: Frame, t: string, x: number, y: number, z: number, col = INK, al: CanvasTextAlign = "center", w: number | string = 700) {
  const { c } = F;
  c.font = dfont(w, z);
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
  const { c, T, dpr } = F;
  if (T < a0) return;
  const sc = lp(2.6, 1, ez(seg(T, a0, a1)));
  c.save();
  c.translate(x, y);
  c.scale(sc, sc);
  c.font = dfont(900, z);
  c.textAlign = "center";
  const m = c.measureText(t).width;
  if (m > W - 40) c.scale((W - 40) / m, (W - 40) / m);
  c.shadowColor = "rgba(0,0,0,.7)";
  c.shadowBlur = 12 * dpr;
  c.lineWidth = 5;
  c.lineJoin = "round";
  c.strokeStyle = "#1a0f08";
  c.strokeText(t, 0, 0);
  c.shadowColor = "transparent";
  const gr = c.createLinearGradient(0, -z * 0.8, 0, 0);
  gr.addColorStop(0, shade(col, 0.35));
  gr.addColorStop(1, col);
  c.fillStyle = gr;
  c.fillText(t, 0, 0);
  c.restore();
}

/** Narration card that types itself out between a and b. */
export function narr(F: Frame, t: string | undefined, a: number, b: number, y = 112) {
  const { c, T } = F;
  if (!t || T < a || T > b) return;
  c.font = font(500, 16);
  const shown = t.slice(0, Math.floor(((T - a + 0.1) * t.length) / Math.max(1, (b - a) * 0.55)));
  const all = wrap(c, t, W - 108), ls = wrap(c, shown, W - 108);
  parch(F, 16, y, W - 76, Math.max(all.length * 20 + 18, 40));
  c.font = font(500, 16);
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
const RED_HEART = "#b8322a";

const ELV = (52 * Math.PI) / 180;

/** A paper miniature: a printed figure with a die-cut white edge, slotted into a dark round base
 *  whose rim colour marks the side (gold for the hero, red for foes). */
export function standee(F: Frame, d: Creature, x: number, y: number, sc: number, face: number, t: number, ph: number, rim = GOLD) {
  const { c, dpr } = F;
  const r = (d.r || 17) * sc, ry = Math.sin(ELV), hs = 0.45 + 0.55 * Math.cos(ELV), th = r * 0.3 * Math.cos(ELV) + 2, fl = d.float;
  const bob = fl ? (Math.sin(t * 2 + ph) * 3 + 9) * sc : Math.abs(Math.sin(t * 3 + ph)) * (d.hop ? 5 : 1.5) * sc;
  const sx = face * sc * (0.9 + 0.1 * Math.cos(t * 1.3 + ph)), sy = sc * hs * (d.hop ? 1 + 0.07 * Math.sin(t * 6 + ph) : 1);
  c.save();
  c.translate(x, y);
  c.lineJoin = "round";
  // soft ground shadow, thrown down and to the right
  const gs = c.createRadialGradient(r * 0.35, th + r * 0.2, 0, r * 0.35, th + r * 0.2, r * 1.5);
  gs.addColorStop(0, "rgba(15,8,0,.5)");
  gs.addColorStop(1, "rgba(15,8,0,0)");
  c.fillStyle = gs;
  c.save();
  c.scale(1, ry);
  c.beginPath();
  c.arc(r * 0.35, (th + r * 0.2) / ry, r * 1.5, 0, 7);
  c.fill();
  c.restore();
  if (!fl) {
    // the base: dark side band, coloured rim, dark top
    const sg = c.createLinearGradient(-r, 0, r, 0);
    sg.addColorStop(0, "#4a413b");
    sg.addColorStop(0.35, "#2e2824");
    sg.addColorStop(1, "#141110");
    c.fillStyle = sg;
    c.beginPath();
    c.moveTo(r, 0);
    c.lineTo(r, th);
    c.ellipse(0, th, r, r * ry, 0, 0, Math.PI);
    c.lineTo(-r, 0);
    c.closePath();
    c.fill();
    const tg = c.createRadialGradient(-r * 0.3, -r * ry * 0.4, 1, 0, 0, r);
    tg.addColorStop(0, "#5a524b");
    tg.addColorStop(1, "#24201d");
    c.fillStyle = tg;
    c.beginPath();
    c.ellipse(0, 0, r, r * ry, 0, 0, 7);
    c.fill();
    c.strokeStyle = rim;
    c.lineWidth = Math.max(1.4, r * 0.09);
    c.beginPath();
    c.ellipse(0, 0, r * 0.94, r * ry * 0.94, 0, 0, 7);
    c.stroke();
    c.strokeStyle = "rgba(255,255,255,.18)";
    c.lineWidth = 1;
    c.beginPath();
    c.ellipse(0, 0, r * 0.82, r * ry * 0.82, 0, Math.PI * 1.05, Math.PI * 1.7);
    c.stroke();
  } else {
    c.strokeStyle = rim;
    c.globalAlpha = 0.5;
    c.lineWidth = 1.2;
    c.beginPath();
    c.ellipse(0, r * 0.3, r * 0.8, r * 0.8 * ry * 0.45, 0, 0, 7);
    c.stroke();
    c.globalAlpha = 1;
  }
  // faint cast shadow of the figure
  c.save();
  c.globalAlpha = 0.6;
  c.scale(sx, sc);
  c.transform(1, 0, 0.7, -0.3 * ry, 0, 0);
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
  const cw = 3.4 / sc;
  // die-cut paper: card thickness, then the white edge, then the print
  c.save();
  c.translate(0.9 / sc, 0.5 / sc);
  dsl(c, d.parts, { cut: { fill: "#a89a80", w: cw } });
  c.restore();
  dsl(c, d.parts, { cut: { fill: "#f6efdf", w: cw } });
  dsl(c, d.parts, { ink: "#1e1712", lw: 1.5 / sc, sh: true });
  c.restore();
  void dpr;
}

export type Light = { x: number; y: number; r: number; rgb: string };

/** Darkness with pools of light, then additive warmth where it's lit. Needs `F.dark`. */
export function lighting(F: Frame, lights: Light[], ambient = 0.6) {
  const { c, T } = F;
  if (!F.dark) return;
  const d = F.dark.getContext("2d"), s = F.dark.width / W;
  d.setTransform(s, 0, 0, s, 0, 0);
  d.globalCompositeOperation = "source-over";
  d.clearRect(0, 0, W, H);
  d.fillStyle = `rgba(20,11,10,${ambient})`;
  d.fillRect(0, 0, W, H);
  d.globalCompositeOperation = "destination-out";
  lights.forEach((l, i) => {
    const r = l.r * (1 + 0.05 * Math.sin(T * 11 + i * 2.3) + 0.03 * Math.sin(T * 23 + i));
    const g = d.createRadialGradient(l.x, l.y, r * 0.1, l.x, l.y, r);
    g.addColorStop(0, "rgba(0,0,0,1)");
    g.addColorStop(0.5, "rgba(0,0,0,.7)");
    g.addColorStop(1, "rgba(0,0,0,0)");
    d.fillStyle = g;
    d.fillRect(l.x - r, l.y - r, r * 2, r * 2);
  });
  c.drawImage(F.dark as unknown as CanvasImageSource, 0, 0, W, H);
  c.save();
  c.globalCompositeOperation = "lighter";
  lights.forEach((l, i) => {
    const r = l.r * 0.7, a = 0.16 + 0.04 * Math.sin(T * 9 + i * 1.7);
    const g = c.createRadialGradient(l.x, l.y, 0, l.x, l.y, r);
    g.addColorStop(0, `rgba(${l.rgb},${a})`);
    g.addColorStop(1, `rgba(${l.rgb},0)`);
    c.fillStyle = g;
    c.fillRect(l.x - r, l.y - r, r * 2, r * 2);
  });
  c.restore();
}

/** A live flame: layered teardrops that flicker and sway. */
export function flame(F: Frame, x: number, y: number, s: number, ph: number) {
  const { c, T } = F;
  const k = 1 + 0.14 * Math.sin(T * 13 + ph) + 0.07 * Math.sin(T * 29 + ph * 2), sway = Math.sin(T * 7 + ph) * s * 0.18;
  const drop = (q: number, col: string) => {
    const w = s * q, top = y - s * 1.9 * q * k;
    c.beginPath();
    c.moveTo(x + sway * q, top);
    c.bezierCurveTo(x + w * 0.9, y - w * 0.7, x + w * 0.75, y + w * 0.45, x, y + w * 0.5);
    c.bezierCurveTo(x - w * 0.75, y + w * 0.45, x - w * 0.9, y - w * 0.7, x + sway * q, top);
    c.fillStyle = col;
    c.fill();
  };
  c.save();
  c.globalCompositeOperation = "lighter";
  const g = c.createRadialGradient(x, y - s * 0.6, 0, x, y - s * 0.6, s * 3.2);
  g.addColorStop(0, "rgba(255,150,50,.35)");
  g.addColorStop(1, "rgba(255,150,50,0)");
  c.fillStyle = g;
  c.fillRect(x - s * 3.2, y - s * 3.8, s * 6.4, s * 6.4);
  c.restore();
  drop(1, "rgba(235,80,20,.95)");
  drop(0.7, "#ffa62b");
  drop(0.42, "#fff1b8");
}

export const fade = (T: number, a: number, b: number, inn = 0.4, out = 0.4) => ez(seg(T, a, a + inn)) * (1 - seg(T, b - out, b));
export { cl };
