// Small helpers shared by every drawing module (ported from the prototype's one-liners).

export type Ctx = CanvasRenderingContext2D;
export type Canvas = { width: number; height: number; getContext(kind: "2d"): Ctx };
export type MakeCanvas = (w: number, h: number) => Canvas;

/** Logical frame size: the prototype's coordinate system. Output is scaled up from this. */
export const W = 360;
export const H = 640;

export const INK = "#1d3b8b";
export const RED = "#c0392b";
export const GRN = "#1f8a4c";
/** Hand-lettering (prototype: system cursive fonts) and the hook's display face (prototype: Impact). */
export const FP = '"Patrick Hand"';
export const DISPLAY = "Anton";
export const font = (w: number | string, z: number) => `${w} ${z}px ${FP}`;

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
