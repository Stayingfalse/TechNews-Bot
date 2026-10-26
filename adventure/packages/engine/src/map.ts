// The procedural scene map (prototype: gen()): grid paper, carved floor with wall-relief shadow,
// stains, folds, warm light and upright 3D props. Baked once per request into a bitmap; frames only
// crop it. World space is 600×600; the bitmap is 600·K pixels square.
import { type Defs, STY } from "./defs.ts";
import { dsl, markers } from "./dsl.ts";
import { prng, type Rnd } from "./prng.ts";
import { paperTexture } from "./tex.ts";
import { type Canvas, type MakeCanvas, DISPLAY, cl, lp } from "./util.ts";

export type MapRequest = {
  type: string; seed: number; dir?: "N" | "E" | "S" | "W"; size?: number; style?: string;
  accessories?: string[]; name?: string; stains?: number;
};
/** A light the frame lighting opens up (map coordinates); `rgb` is "r,g,b". Flames are drawn live. */
export type MapLight = { x: number; y: number; r: number; rgb: string };
export type MapFlame = { x: number; y: number; s: number };
export type BakedMap = { cv: Canvas; k: number; tp: number[][]; len: number[]; lights: MapLight[]; flames: MapFlame[] };

type Pt = [number, number];

function stain(g: CanvasRenderingContext2D, rnd: Rnd, x: number, y: number, r: number) {
  g.save();
  const gr = g.createRadialGradient(x, y, r * 0.2, x, y, r);
  gr.addColorStop(0, "rgba(110,70,25,.10)");
  gr.addColorStop(0.85, "rgba(110,70,25,.17)");
  gr.addColorStop(1, "rgba(110,70,25,0)");
  g.fillStyle = gr;
  g.beginPath();
  g.arc(x, y, r, 0, 7);
  g.fill();
  g.strokeStyle = "rgba(95,58,20,.34)";
  g.lineWidth = 2.5;
  g.beginPath();
  for (let a = 0; a <= 6.4; a += 0.15) {
    const rr = r * (0.86 + 0.06 * Math.sin(a * 3 + x) + 0.04 * Math.sin(a * 7)), X = x + Math.cos(a) * rr, Y = y + Math.sin(a) * rr;
    a ? g.lineTo(X, Y) : g.moveTo(X, Y);
  }
  g.stroke();
  g.lineWidth = 1;
  g.strokeStyle = "rgba(95,58,20,.2)";
  g.beginPath();
  g.arc(x + 3, y + 2, r * 0.74, 0.3, 4.6);
  g.stroke();
  for (let i = 0; i < 8; i++) {
    g.fillStyle = "rgba(95,58,20,.3)";
    g.beginPath();
    g.arc(x + (rnd() - 0.5) * r * 2.6, y + (rnd() - 0.5) * r * 2.6, rnd() * 3 + 1, 0, 7);
    g.fill();
  }
  g.restore();
}

/** An upright prop: soft contact shadow, a faint cast silhouette, then the shaded solid. */
export function prop(g: CanvasRenderingContext2D, df: Defs, name: string, x: number, y: number, sc: number) {
  const parts = df.props[name];
  const xs = parts.flatMap((p) => (typeof p[1] === "number" ? [p[1] as number] : []));
  const foot = Math.max(8, (Math.max(...xs) - Math.min(...xs)) / 2 + 6) * sc;
  g.save();
  g.translate(x, y);
  const sh = g.createRadialGradient(foot * 0.35, foot * 0.12, 0, foot * 0.35, foot * 0.12, foot * 1.2);
  sh.addColorStop(0, "rgba(25,12,0,.42)");
  sh.addColorStop(0.6, "rgba(25,12,0,.18)");
  sh.addColorStop(1, "rgba(25,12,0,0)");
  g.fillStyle = sh;
  g.save();
  g.scale(1, 0.45);
  g.beginPath();
  g.arc(foot * 0.35, foot * 0.12 / 0.45, foot * 1.2, 0, 7);
  g.fill();
  g.restore();
  g.save();
  g.globalAlpha = 0.55;
  g.scale(sc, sc);
  g.transform(1, 0, 0.75, -0.32, 0, 0);
  dsl(g, parts, { sil: true });
  g.restore();
  g.save();
  g.scale(sc, sc * 0.9);
  dsl(g, parts, { lw: 1.1, sh: true });
  g.restore();
  g.restore();
}

export function bake(rq: MapRequest, df: Defs, make: MakeCanvas, k = 4.5): BakedMap {
  const rnd = prng(rq.seed);
  const sty = STY[rq.style || "ink"] || STY.ink, sd = df.scenes[rq.type] || df.scenes.dungeon;
  const R = cl(rq.size || 5, 3, 8), dir = rq.dir || "N", dens = R / 5;
  const SZ = Math.round(600 * k), h = k / 2; // h: the prototype's device-pixel constants were for k = 2
  const fl: Pt[][] = [], path: Pt[] = [], cs: number[][] = [];
  let LP: Pt;
  const rectP = (x: number, y: number, w: number, hh: number): Pt[] => {
    const a: Pt[] = [[x, y], [x + w, y], [x + w, y + hh], [x, y + hh]], o: Pt[] = [];
    a.forEach((p, i) => {
      const q = a[(i + 1) % 4], n = Math.max(1, (Math.hypot(q[0] - p[0], q[1] - p[1]) / 18) | 0);
      for (let j = 0; j < n; j++) o.push([lp(p[0], q[0], j / n) + (rnd() - 0.5) * 2, lp(p[1], q[1], j / n) + (rnd() - 0.5) * 2]);
    });
    return o;
  };
  const ellP = (x: number, y: number, rx: number, ry: number, j: number): Pt[] =>
    Array.from({ length: 24 }, (_, i) => [x + Math.cos((i / 24) * 6.283) * (rx + (rnd() - 0.5) * j), y + Math.sin((i / 24) * 6.283) * (ry + (rnd() - 0.5) * j)]);
  const pp = (g: CanvasRenderingContext2D, p: Pt[]) => {
    g.beginPath();
    p.forEach((q, i) => (i ? g.lineTo(q[0], q[1]) : g.moveTo(q[0], q[1])));
    g.closePath();
  };

  if (sd.layout === "rooms") {
    for (let i = 0; i < R; i++) {
      const sp = 430 / (R - 1), w = 70 + rnd() * 110;
      cs.push([cl(300 + (rnd() - 0.5) * 220, w / 2 + 20, 580 - w / 2), lp(520, 95, i / (R - 1)), w, Math.min(sp - 34, 45 + rnd() * 50), rnd() < 0.3 ? 1 : 0]);
    }
    path.push([cs[0][0], 590]);
    fl.push(rectP(cs[0][0] - 13, cs[0][1], 26, 600 - cs[0][1]));
    cs.forEach(([cx, cy, w, hh, rd], i) => {
      fl.push(rd ? ellP(cx, cy, w / 2, hh / 2, 3) : rectP(cx - w / 2, cy - hh / 2, w, hh));
      path.push([cx, cy]);
      if (i < R - 1) {
        const [nx, ny] = cs[i + 1], m = (cy + ny) / 2;
        fl.push(rectP(cx - 13, m, 26, cy - m), rectP(Math.min(cx, nx) - 13, m - 13, Math.abs(nx - cx) + 26, 26), rectP(nx - 13, ny, 26, m - ny));
        path.push([cx, m], [nx, m]);
      }
    });
    LP = path[path.length - 1];
  } else if (sd.layout === "cave") {
    const ph = rnd() * 6;
    for (let i = 0; i < R; i++) {
      const cx = 300 + Math.sin(ph + i * 1.2) * 110, cy = lp(520, 100, i / (R - 1)), r = 38 + rnd() * 38;
      fl.push(ellP(cx, cy, r, r, 10));
      if (i) {
        const [px, py] = cs[i - 1], n = Math.ceil(Math.hypot(cx - px, cy - py) / 16);
        for (let j = 0; j <= n; j++) fl.push(ellP(lp(px, cx, j / n), lp(py, cy, j / n), 18, 18, 4));
      }
      cs.push([cx, cy]);
      path.push([cx, cy]);
    }
    path.unshift([cs[0][0], 590]);
    fl.push(ellP(cs[0][0], 582, 20, 20, 4));
    LP = [cs[R - 1][0], cs[R - 1][1]];
  } else {
    const amp = sd.amp || 60, ph = rnd() * 6, fr = 55 + rnd() * 40, pts: Pt[] = [];
    for (let y = 600; y >= 70; y -= 14) pts.push([300 + Math.sin(y / fr + ph) * amp, y]);
    const e = pts.map((_, i) => {
      const q = pts[Math.min(i + 1, pts.length - 1)], r = pts[Math.max(i - 1, 0)], dx = q[0] - r[0], dy = q[1] - r[1], l = Math.hypot(dx, dy) || 1;
      return [(-dy / l) * 22, (dx / l) * 22];
    });
    fl.push([...pts.map((p, i): Pt => [p[0] + e[i][0], p[1] + e[i][1]]), ...pts.map((p, i): Pt => [p[0] - e[i][0], p[1] - e[i][1]]).reverse()]);
    pts.forEach((p, i) => i % 3 === 0 && path.push(p));
    LP = [pts[pts.length - 1][0], 52];
  }

  const Tm = ({ N: [1, 0, 0, 1, 0, 0], E: [0, 1, -1, 0, 600, 0], S: [-1, 0, 0, -1, 600, 600], W: [0, -1, 1, 0, 0, 600] } as const)[dir];
  const tr = (q: number[]): Pt => [Tm[0] * q[0] + Tm[2] * q[1] + Tm[4], Tm[1] * q[0] + Tm[3] * q[1] + Tm[5]];
  const TS = Tm.map((v) => v * k) as [number, number, number, number, number, number];

  const hatch = sd.out === "hatch";
  const M = make(SZ, SZ), g = M.getContext("2d");
  // paper
  g.fillStyle = sty.paper;
  g.fillRect(0, 0, SZ, SZ);
  g.drawImage(paperTexture(make, rq.seed, SZ) as unknown as CanvasImageSource, 0, 0);
  g.scale(k, k);
  const grid = (alpha: number) => {
    g.lineWidth = 0.6;
    for (let i = 0; i <= 600; i += 20) {
      g.strokeStyle = `rgba(${sty.grid},${i % 100 ? alpha : alpha * 1.8})`;
      g.beginPath();
      g.moveTo(i, 0);
      g.lineTo(i, 600);
      g.moveTo(0, i);
      g.lineTo(600, i);
      g.stroke();
    }
  };
  grid(0.07);
  // floors: a light wash and a firmer grid (in the rotated frame, like the walls)
  g.save();
  g.setTransform(...TS);
  g.beginPath();
  fl.forEach((p) => p.forEach((q, i) => (i ? g.lineTo(q[0], q[1]) : g.moveTo(q[0], q[1]))));
  g.clip("nonzero");
  g.fillStyle = sd.path || sty.wash;
  g.fillRect(-10, -10, 620, 620);
  g.setTransform(k, 0, 0, k, 0, 0);
  grid(0.22);
  g.restore();

  // masks (unrotated world space): the floor, and a band just outside it
  const K = make(600, 600), kc = K.getContext("2d");
  kc.fillStyle = "#000";
  fl.forEach((p) => {
    pp(kc, p);
    kc.fill();
  });
  const D = kc.getImageData(0, 0, 600, 600).data;
  const inF = (x: number, y: number) => x >= 0 && y >= 0 && x < 600 && y < 600 && D[((y | 0) * 600 + (x | 0)) * 4 + 3] > 40;
  const NB = make(600, 600), nb = NB.getContext("2d");
  nb.strokeStyle = "#000";
  nb.lineJoin = "round";
  nb.lineWidth = hatch ? 34 : 24;
  fl.forEach((p) => {
    pp(nb, p);
    nb.stroke();
  });
  const DN = nb.getImageData(0, 0, 600, 600).data;
  const near = (x: number, y: number) => x >= 0 && y >= 0 && x < 600 && y < 600 && DN[((y | 0) * 600 + (x | 0)) * 4 + 3] > 40;

  // walls: ink line, hatching tufts outside (old-school dungeon maps) or grass stipple outdoors
  const rh = prng(rq.seed * 13 + 7);
  const L = make(SZ, SZ), l = L.getContext("2d");
  l.setTransform(...TS);
  l.strokeStyle = sty.ink;
  l.lineCap = "round";
  if (hatch) {
    l.fillStyle = sty.rock;
    l.fillRect(0, 0, 600, 600);
    for (let i = 0; i < 9000; i++) {
      const x = rh() * 600, y = rh() * 600;
      if (inF(x, y) || !near(x, y)) continue;
      const a = rh() * Math.PI, n = 3 + ((rh() * 3) | 0), len = 4 + rh() * 4, gap = 1.5;
      const ux = Math.cos(a), uy = Math.sin(a);
      l.globalAlpha = 0.5 + rh() * 0.4;
      l.lineWidth = 0.45 + rh() * 0.35;
      l.beginPath();
      for (let j = 0; j < n; j++) {
        const o = (j - (n - 1) / 2) * gap, cx = x - uy * o, cy = y + ux * o, h = len * (0.75 + rh() * 0.25) / 2;
        l.moveTo(cx - ux * h, cy - uy * h);
        l.lineTo(cx + ux * h, cy + uy * h);
      }
      l.stroke();
    }
    l.globalAlpha = 1;
  } else {
    if (sd.ground) {
      l.fillStyle = sd.ground;
      l.fillRect(0, 0, 600, 600);
    }
    for (let i = 0; i < 1800; i++) {
      const x = rh() * 600, y = rh() * 600;
      if (inF(x, y) || !near(x, y)) continue;
      l.globalAlpha = 0.35 + rh() * 0.4;
      l.lineWidth = 0.7;
      l.beginPath();
      l.moveTo(x - 2, y);
      l.lineTo(x - 0.5, y - 3 - rh() * 2);
      l.moveTo(x + 2, y);
      l.lineTo(x + 0.5, y - 3 - rh() * 2);
      l.stroke();
    }
    l.globalAlpha = 1;
  }
  l.lineWidth = hatch ? 6 : 3.5;
  l.lineJoin = "round";
  fl.forEach((p) => {
    pp(l, p);
    l.stroke();
  });
  l.globalCompositeOperation = "destination-out";
  l.fillStyle = "#000";
  fl.forEach((p) => {
    pp(l, p);
    l.fill();
  });
  g.save();
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.shadowColor = "rgba(40,22,5,.7)";
  g.shadowBlur = 16 * h;
  g.shadowOffsetX = 5 * h;
  g.shadowOffsetY = 8 * h;
  g.drawImage(L as unknown as CanvasImageSource, 0, 0);
  g.restore();

  g.setTransform(...TS);
  const placed: number[][] = [LP], ups: [string, number, number, number][] = [];
  const lights: MapLight[] = [], flames: MapFlame[] = [];
  const put = (n: string, x: number, y: number, sc: number, r: number) => {
    const parts = df.items[n] || [];
    g.save();
    g.translate(x, y);
    g.rotate(r);
    g.scale(sc, sc);
    dsl(g, parts, { lw: 0.9 / sc, sh: true });
    g.restore();
    const [mx, my] = tr([x, y]);
    for (const [, , lr, rgb] of markers(parts).lights) lights.push({ x: mx, y: my, r: lr * sc, rgb });
  };
  const spot = (w: string): Pt | null => {
    for (let i = 0; i < 70; i++) {
      const x = 20 + rnd() * 560, y = 40 + rnd() * 520, f = inF(x, y);
      if (placed.some((p) => Math.hypot(p[0] - x, p[1] - y) < 26)) continue;
      if ((w === "floor" && f && inF(x + 9, y) && inF(x - 9, y)) ||
        (w === "out" && !f && path.every((p) => Math.hypot(p[0] - x, p[1] - y) > 58)) ||
        (w === "edge" && f && (!inF(x + 16, y) || !inF(x - 16, y) || !inF(x, y + 16) || !inF(x, y - 16)))) {
        placed.push([x, y]);
        return [x, y];
      }
    }
    return null;
  };
  const drop = (n: string, x: number, y: number, sc: number) => {
    if (df.props[n]) {
      const [mx, my] = tr([x, y]);
      ups.push([n, mx, my, sc]);
      const m = markers(df.props[n]);
      for (const [fx, fy, fs] of m.flames) flames.push({ x: mx + fx * sc, y: my + fy * sc * 0.9, s: fs * sc });
      for (const [lx, ly, lr, rgb] of m.lights) lights.push({ x: mx + lx * sc, y: my + ly * sc * 0.9, r: lr * sc, rgb });
    } else put(n, x, y, sc, n === "torch" ? 0 : rnd() * 6.28);
  };
  drop(sd.landmark[0], LP[0], LP[1], 1.6);
  const extra = (rq.accessories || []).map((a): [string, number, string] => [a, 1 + ((rnd() * 2) | 0), "floor"]);
  for (const [n, c, w] of [...sd.dress, ...extra]) {
    for (let i = 0, m = Math.max(1, Math.round(c * dens)); i < m; i++) {
      const p = spot(w);
      if (p) drop(n, p[0], p[1], 0.95 + rnd() * 0.5);
    }
  }
  g.setTransform(k, 0, 0, k, 0, 0);
  const ns = rq.stains == null ? 1 : rq.stains;
  for (let i = 0; i < ns; i++) stain(g, rnd, 70 + rnd() * 460, 70 + rnd() * 460, i ? 26 + rnd() * 8 : 40 + rnd() * 14);
  // folds: a soft valley with a lit edge
  for (const [a, b, c, d] of [[300, 0, 300, 600], [0, 300, 600, 300]]) {
    const vert = a === c, gr = vert ? g.createLinearGradient(a - 6, 0, a + 6, 0) : g.createLinearGradient(0, b - 6, 0, b + 6);
    gr.addColorStop(0, "rgba(60,35,10,0)");
    gr.addColorStop(0.45, "rgba(60,35,10,.12)");
    gr.addColorStop(0.55, "rgba(255,250,235,.25)");
    gr.addColorStop(1, "rgba(255,250,235,0)");
    g.fillStyle = gr;
    if (vert) g.fillRect(a - 6, 0, 12, 600);
    else g.fillRect(0, b - 6, 600, 12);
  }
  g.fillStyle = sty.ink;
  g.font = `700 13px ${DISPLAY}`;
  g.textAlign = "center";
  const lt = tr(LP), st = tr(path[0]);
  g.fillText(rq.name || sd.landmark[1], cl(lt[0], 80, 520), lt[1] > 540 ? lt[1] - 52 : cl(lt[1] + 38, 16, 584));
  g.font = `700 10px ${DISPLAY}`;
  g.fillText("ENTER »", cl(st[0], 40, 560), st[1] > 300 ? st[1] - 20 : st[1] + 26);
  ups.sort((a, b) => a[2] - b[2]).forEach(([n, x, y, sc]) => prop(g, df, n, x, y, sc));
  g.setTransform(1, 0, 0, 1, 0, 0);
  // age: darker towards the sheet's edges
  const vg = g.createRadialGradient(SZ / 2, SZ / 2, SZ * 0.35, SZ / 2, SZ / 2, SZ * 0.75);
  vg.addColorStop(0, "rgba(70,40,10,0)");
  vg.addColorStop(1, "rgba(70,40,10,.28)");
  g.fillStyle = vg;
  g.fillRect(0, 0, SZ, SZ);

  const tp = path.map(tr), len = [0];
  for (let i = 1; i < tp.length; i++) len.push(len[i - 1] + Math.hypot(tp[i][0] - tp[i - 1][0], tp[i][1] - tp[i - 1][1]));
  return { cv: M, k, tp, len, lights, flames };
}

/** A point a fraction f of the way along the map's path, and the direction of travel there. */
export function along(S: Pick<BakedMap, "tp" | "len">, f: number): [number, number, number] {
  const d = f * S.len[S.len.length - 1];
  let i = 1;
  while (i < S.len.length - 1 && S.len[i] < d) i++;
  const kk = (d - S.len[i - 1]) / Math.max(1e-6, S.len[i] - S.len[i - 1]);
  return [lp(S.tp[i - 1][0], S.tp[i][0], kk), lp(S.tp[i - 1][1], S.tp[i][1], kk), S.tp[i][0] - S.tp[i - 1][0]];
}
