// The procedural scene map (prototype: gen()): grid paper, carved floor with wall-relief shadow,
// stains, folds, warm light and upright 3D props. Baked once per request into a bitmap; frames only
// crop it. World space is 600×600; the bitmap is 600·K pixels square.
import { type Defs, STY } from "./defs.ts";
import { dsl } from "./dsl.ts";
import { prng, type Rnd } from "./prng.ts";
import { type Canvas, type MakeCanvas, FP, cl, lp } from "./util.ts";

export type MapRequest = {
  type: string; seed: number; dir?: "N" | "E" | "S" | "W"; size?: number; style?: string;
  accessories?: string[]; name?: string; stains?: number;
};
export type BakedMap = { cv: Canvas; k: number; tp: number[][]; len: number[] };

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

/** An upright prop: glow for fire, contact shadow, slanted silhouette shadow, then the shaded prop. */
export function prop(g: CanvasRenderingContext2D, df: Defs, name: string, x: number, y: number, sc: number) {
  const parts = df.props[name];
  g.save();
  g.translate(x, y);
  if (name === "torch" || name === "campfire") {
    const gr = g.createRadialGradient(0, -18 * sc, 2, 0, -18 * sc, 64 * sc);
    gr.addColorStop(0, "rgba(255,170,60,.4)");
    gr.addColorStop(1, "rgba(255,170,60,0)");
    g.fillStyle = gr;
    g.fillRect(-70 * sc, -90 * sc, 140 * sc, 140 * sc);
  }
  g.fillStyle = "rgba(30,15,0,.3)";
  g.beginPath();
  g.ellipse(0, 0, 14 * sc, 5 * sc, 0, 0, 7);
  g.fill();
  g.save();
  g.scale(sc, sc);
  g.transform(1, 0, -0.6, -0.3, 0, 0);
  dsl(g, parts, { sil: true });
  g.restore();
  g.save();
  g.scale(sc, sc * 0.9);
  dsl(g, parts, { ink: "#2a2418", lw: 1.6, sh: true });
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

  const M = make(SZ, SZ), g = M.getContext("2d");
  g.scale(k, k);
  g.fillStyle = sty.paper;
  g.fillRect(0, 0, 600, 600);
  g.lineWidth = 1;
  for (let i = 0; i <= 600; i += 20) {
    g.strokeStyle = `rgba(${sty.grid},${i % 100 ? 0.3 : 0.6})`;
    g.beginPath();
    g.moveTo(i, 0);
    g.lineTo(i, 600);
    g.moveTo(0, i);
    g.lineTo(600, i);
    g.stroke();
  }
  for (let i = 0; i < 5000; i++) {
    g.fillStyle = `rgba(120,90,50,${0.03 + rnd() * 0.05})`;
    g.fillRect(rnd() * 600, rnd() * 600, 0.8, 0.8);
  }
  const L = make(SZ, SZ), l = L.getContext("2d");
  l.setTransform(...TS);
  if (sd.out === "hatch") {
    l.fillStyle = sty.tint;
    l.fillRect(0, 0, 600, 600);
    l.strokeStyle = sty.ink;
    l.globalAlpha = 0.3;
    l.lineWidth = 1;
    for (let i = -600; i < 1200; i += 9) {
      l.beginPath();
      l.moveTo(i, -10);
      l.lineTo(i + 610, 600);
      l.stroke();
    }
    l.globalAlpha = 1;
  }
  l.strokeStyle = sty.ink;
  l.lineWidth = 9;
  l.lineJoin = "round";
  fl.forEach((p) => {
    pp(l, p);
    l.stroke();
  });
  l.globalCompositeOperation = "destination-out";
  fl.forEach((p) => {
    pp(l, p);
    l.fill();
  });
  g.save();
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.shadowColor = "rgba(30,15,0,.5)";
  g.shadowBlur = 26 * h;
  g.shadowOffsetX = 9 * h;
  g.shadowOffsetY = 13 * h;
  g.drawImage(L as unknown as CanvasImageSource, 0, 0);
  g.restore();

  const K = make(600, 600), kc = K.getContext("2d");
  kc.fillStyle = "#000";
  fl.forEach((p) => {
    pp(kc, p);
    kc.fill();
  });
  const D = kc.getImageData(0, 0, 600, 600).data;
  const inF = (x: number, y: number) => x >= 0 && y >= 0 && x < 600 && y < 600 && D[((y | 0) * 600 + (x | 0)) * 4 + 3] > 40;

  g.setTransform(...TS);
  const placed: number[][] = [LP], ups: [string, number, number, number][] = [];
  const put = (n: string, x: number, y: number, sc: number, r: number) => {
    g.save();
    g.translate(x, y);
    g.rotate(r);
    g.scale(sc, sc);
    dsl(g, df.items[n] || [], { ink: sty.ink, lw: 2.2 / sc });
    g.restore();
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
    if (df.props[n]) ups.push([n, ...tr([x, y]), sc]);
    else put(n, x, y, sc, n === "torch" ? 0 : rnd() * 6.28);
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
  const ns = rq.stains == null ? 2 : rq.stains;
  for (let i = 0; i < ns; i++) stain(g, rnd, 70 + rnd() * 460, 70 + rnd() * 460, i ? 26 + rnd() * 8 : 40 + rnd() * 14);
  for (const [a, b, c, d] of [[300, 0, 300, 600], [0, 300, 600, 300]]) {
    g.lineWidth = 1.4;
    g.strokeStyle = "rgba(60,40,10,.14)";
    g.beginPath();
    g.moveTo(a, b);
    g.lineTo(c, d);
    g.stroke();
    g.strokeStyle = "rgba(255,255,255,.4)";
    g.beginPath();
    g.moveTo(a + 1.4, b + 1.4);
    g.lineTo(c + 1.4, d + 1.4);
    g.stroke();
  }
  g.fillStyle = sty.ink;
  g.font = `15px ${FP}`;
  g.textAlign = "center";
  const lt = tr(LP), st = tr(path[0]);
  g.fillText(rq.name || sd.landmark[1], cl(lt[0], 80, 520), lt[1] > 540 ? lt[1] - 52 : cl(lt[1] + 38, 16, 584));
  g.font = `12px ${FP}`;
  g.fillText("ENTER ▸", cl(st[0], 40, 560), st[1] > 300 ? st[1] - 20 : st[1] + 26);
  ups.sort((a, b) => a[2] - b[2]).forEach(([n, x, y, sc]) => prop(g, df, n, x, y, sc));
  g.setTransform(1, 0, 0, 1, 0, 0);
  let lg = g.createRadialGradient(380 * h, 300 * h, 40 * h, 380 * h, 300 * h, 1000 * h);
  lg.addColorStop(0, "rgba(255,236,190,.26)");
  lg.addColorStop(1, "rgba(255,236,190,0)");
  g.fillStyle = lg;
  g.fillRect(0, 0, SZ, SZ);
  lg = g.createRadialGradient(600 * h, 600 * h, 420 * h, 600 * h, 600 * h, 900 * h);
  lg.addColorStop(0, "rgba(30,10,0,0)");
  lg.addColorStop(1, "rgba(30,10,0,.5)");
  g.fillStyle = lg;
  g.fillRect(0, 0, SZ, SZ);

  const tp = path.map(tr), len = [0];
  for (let i = 1; i < tp.length; i++) len.push(len[i - 1] + Math.hypot(tp[i][0] - tp[i - 1][0], tp[i][1] - tp[i - 1][1]));
  return { cv: M, k, tp, len };
}

/** A point a fraction f of the way along the map's path, and the direction of travel there. */
export function along(S: Pick<BakedMap, "tp" | "len">, f: number): [number, number, number] {
  const d = f * S.len[S.len.length - 1];
  let i = 1;
  while (i < S.len.length - 1 && S.len[i] < d) i++;
  const kk = (d - S.len[i - 1]) / Math.max(1e-6, S.len[i] - S.len[i - 1]);
  return [lp(S.tp[i - 1][0], S.tp[i][0], kk), lp(S.tp[i - 1][1], S.tp[i][1], kk), S.tp[i][0] - S.tp[i - 1][0]];
}
