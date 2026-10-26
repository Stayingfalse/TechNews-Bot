// The d20 (prototype: die(), finalRot() and the throw in frame()). The face it lands on is an
// input: the server rolls, the engine shows that roll.
import type { Frame } from "./draw.ts";
import { loop } from "./draw.ts";
import { FP, GRN, INK, RED, cl, lp, seg } from "./util.ts";

type V3 = [number, number, number];
type M3 = [V3, V3, V3];

const PHI = (1 + Math.sqrt(5)) / 2;
const V: V3[] = [];
const F: { v: [number, number, number]; n: V3; c: V3; num: number }[] = [];
for (const v of [[0, 1, PHI], [0, -1, PHI], [0, 1, -PHI], [0, -1, -PHI], [1, PHI, 0], [-1, PHI, 0], [1, -PHI, 0], [-1, -PHI, 0], [PHI, 0, 1], [-PHI, 0, 1], [PHI, 0, -1], [-PHI, 0, -1]]) {
  const l = Math.hypot(...v);
  V.push(v.map((c) => c / l) as V3);
}
const dist = (a: V3, b: V3) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]), EL = dist(V[0], V[1]);
for (let i = 0; i < 12; i++) for (let j = i + 1; j < 12; j++) for (let k = j + 1; k < 12; k++) {
  if ([dist(V[i], V[j]), dist(V[j], V[k]), dist(V[i], V[k])].every((d) => Math.abs(d - EL) < 0.02)) {
    const c = [0, 1, 2].map((a) => (V[i][a] + V[j][a] + V[k][a]) / 3) as V3, l = Math.hypot(...c);
    F.push({ v: [i, j, k], n: c.map((x) => x / l) as V3, c, num: 0 });
  }
}
{ // opposite faces sum to 21, as on a real d20
  const L = [17, 3, 13, 7, 16, 10, 6, 19, 1, 12];
  let p = 0;
  for (const f of F) {
    if (f.num) continue;
    const o = F.find((g) => g.n[0] * f.n[0] + g.n[1] * f.n[1] + g.n[2] * f.n[2] < -0.99)!;
    f.num = L[p];
    o.num = 21 - L[p];
    p++;
  }
}
export const FACES = F.map((f) => f.num);

const mm = (A: M3, B: M3): M3 => A.map((r) => [0, 1, 2].map((j) => r[0] * B[0][j] + r[1] * B[1][j] + r[2] * B[2][j])) as M3;
const mv = (A: M3, v: V3): V3 => A.map((r) => r[0] * v[0] + r[1] * v[1] + r[2] * v[2]) as V3;
function rot(a: V3, th: number): M3 {
  const l = Math.hypot(...a), [x, y, z] = a.map((c) => c / l), c = Math.cos(th), s = Math.sin(th), t = 1 - c;
  return [[t * x * x + c, t * x * y - s * z, t * x * z + s * y], [t * x * y + s * z, t * y * y + c, t * y * z - s * x], [t * x * z - s * y, t * y * z + s * x, t * z * z + c]];
}

/** The rotation that shows face N to the camera, upright. */
export function finalRot(N: number): M3 {
  const f = F.find((f) => f.num === N)!, n = f.n, ax: V3 = [n[1], -n[0], 0];
  const R = Math.hypot(ax[0], ax[1]) < 1e-6 ? (n[2] > 0 ? rot([0, 0, 1], 0) : rot([1, 0, 0], Math.PI)) : rot(ax, Math.acos(n[2]));
  const u = mv(R, [0, 1, 2].map((a) => V[f.v[0]][a] - f.c[a]) as V3);
  return mm(rot([0, 0, 1], Math.PI / 2 - Math.atan2(u[1], u[0])), R);
}

/** The face nearest the camera for a rotation (what a viewer reads). */
export function topFace(R: M3): number {
  let best = F[0], bz = -2;
  for (const f of F) {
    const z = mv(R, f.n)[2];
    if (z > bz) {
      bz = z;
      best = f;
    }
  }
  return best.num;
}

export function die(Fr: Frame, cx: number, cy: number, Rp: number, Rm: M3) {
  const { c } = Fr;
  const P = (v: V3) => {
    const r = mv(Rm, v), k = 520 / (520 - r[2] * Rp);
    return [cx + r[0] * Rp * k, cy - r[1] * Rp * k];
  };
  F.map((f) => ({ f, n: mv(Rm, f.n), c: mv(Rm, f.c) })).filter((o) => o.n[2] > 0.02).sort((a, b) => a.c[2] - b.c[2]).forEach(({ f, n }) => {
    const pts = f.v.map((i) => P(V[i])), sh = cl(0.5 + 0.5 * (n[0] * -0.35 + n[1] * 0.55 + n[2] * 0.75));
    c.fillStyle = `rgb(${lp(205, 255, sh) | 0},${lp(198, 252, sh) | 0},${lp(172, 238, sh) | 0})`;
    c.strokeStyle = INK;
    c.lineWidth = 2;
    c.lineJoin = "round";
    c.beginPath();
    pts.forEach((p, i) => (i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1])));
    c.closePath();
    c.fill();
    c.stroke();
    const u0 = mv(Rm, [0, 1, 2].map((a) => V[f.v[0]][a] - f.c[a]) as V3), ul = Math.hypot(...u0), u = u0.map((x) => x / ul);
    const r = [u[1] * n[2] - u[2] * n[1], u[2] * n[0] - u[0] * n[2], u[0] * n[1] - u[1] * n[0]], cp = P(f.c);
    c.save();
    c.transform(r[0], -r[1], -u[0], u[1], cp[0], cp[1]);
    c.font = `700 ${0.34 * Rp}px ${FP}`;
    c.textAlign = "center";
    c.textBaseline = "middle";
    c.fillStyle = INK;
    c.fillText(f.num + (f.num === 6 || f.num === 9 ? "." : ""), 0, 0);
    c.restore();
  });
}

const AX1: V3 = [0.62, 0.5, 0.6], AX2: V3 = [-0.3, 0.9, 0.3];
export const THROW = 2.7; // seconds from leaving the hand to landing
/** Bounce times (fractions of THROW) where the die touches the table: for the clatter sound. */
export const BOUNCES = [1 / 3.2, 2 / 3.2, 3 / 3.2, 1];

export type Throw = { t0: number; face: number; ok: boolean; until: number; to?: [number, number]; from?: [number, number] };

/** The throw: arcs in from the bottom right, tumbles, settles on `face`, wobbles, then gets circled. */
export function throwDie(Fr: Frame, th: Throw) {
  const { c, T } = Fr;
  const land = th.t0 + THROW;
  if (T <= th.t0 || T >= th.until) return;
  const [x0, y0] = th.from || [440, 620], [x1, y1] = th.to || [165, 345];
  const u = seg(T, th.t0, land), pe = 1 - (1 - u) * (1 - u), gx = lp(x0, x1, pe), gy = lp(y0, y1, pe);
  const h = 140 * Math.abs(Math.sin(u * Math.PI * 3.2)) * Math.pow(1 - u, 1.3) + 50 * Math.pow(1 - u, 3);
  let R = mm(rot(AX1, 15 * Math.pow(1 - u, 1.5)), mm(rot(AX2, 9 * (1 - u) * (1 - u)), finalRot(th.face)));
  if (T > land) R = mm(rot([1, 0.3, 0], Math.exp(-(T - land) * 4) * 0.22 * Math.sin((T - land) * 16)), R);
  c.fillStyle = `rgba(30,15,0,${0.35 * (1 - h / 260)})`;
  c.beginPath();
  c.ellipse(gx + h * 0.12 + 8, gy + 46, 46 * (1 - h / 450), 13, 0, 0, 7);
  c.fill();
  die(Fr, gx, gy - h, 54 * (1 + h / 600), R);
  if (T > land + 0.4) loop(Fr, gx, gy, 82, 80, seg(T, land + 0.4, land + 1.1), th.ok ? GRN : RED);
}
export { RED, GRN };
