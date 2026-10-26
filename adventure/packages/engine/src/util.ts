// Small helpers shared by every drawing module (ported from the prototype's one-liners).

export type Ctx = CanvasRenderingContext2D;
export type Canvas = { width: number; height: number; getContext(kind: "2d"): Ctx };
export type MakeCanvas = (w: number, h: number) => Canvas;

/** Logical frame size: the prototype's coordinate system. Output is scaled up from this. */
export const W = 360;
export const H = 640;

// The look: iron-gall ink on old parchment, rubricated in red, with gilt highlights.
export const INK = "#2a1d14";
export const RED = "#9b2c1e";
export const GRN = "#2f6e3f";
export const GOLD = "#d4a440";
export const CREAM = "#f3e4c2";
export const NIGHT = "#140e18";
/** Body text (narration, cards) and the display face (titles, banners, dice numbers). */
export const FP = "Alegreya";
export const DISPLAY = "Cinzel";
export const font = (w: number | string, z: number) => `${w} ${z}px ${FP}`;
export const dfont = (w: number | string, z: number) => `${w} ${z}px ${DISPLAY}`;

/** A colour moved towards white (k > 0) or black (k < 0). */
export function shade(hex: string, k: number): string {
  let h = hex.replace("#", "");
  if (h.length === 3) h = h.split("").map((x) => x + x).join("");
  const n = parseInt(h, 16), t = k > 0 ? 255 : 0, a = Math.abs(k);
  const ch = (v: number) => Math.round(v + (t - v) * a);
  return `rgb(${ch((n >> 16) & 255)},${ch((n >> 8) & 255)},${ch(n & 255)})`;
}

export const cl = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const seg = (t: number, a: number, b: number) => cl((t - a) / (b - a));
export const ez = (x: number) => (x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2);
export const lp = (a: number, b: number, k: number) => a + (b - a) * k;

export function wrap(c: Ctx, t: string, w: number): string[] {
  const o: string[] = [];
  let l = "";
  for (const x of t.split(" ")) {
    const n = l ? l + " " + x : x;
    if (c.measureText(n).width > w && l) {
      o.push(l);
      l = x;
    } else l = n;
  }
  o.push(l);
  return o;
}
