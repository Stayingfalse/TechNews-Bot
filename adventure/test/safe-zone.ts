// Shared by the frame tests: every piece of text must sit inside the area the Reels / Shorts overlays leave clear.
export const SAFE = { x0: 16, x1: 307, y0: 73, y1: 480 };

export type TextBox = { t: string; x0: number; x1: number; y0: number; y1: number };

/** Wraps ctx.fillText to record each visible, non-blank string's box in logical units (device px / 3). */
export function recordText(ctx: CanvasRenderingContext2D, out: TextBox[]) {
  const fill = ctx.fillText.bind(ctx);
  ctx.fillText = (t: string, x: number, y: number) => {
    const m = ctx.measureText(t), tr = ctx.getTransform(), s = 3;
    const left = ctx.textAlign === "center" ? x - m.width / 2 : ctx.textAlign === "right" ? x - m.width : x;
    const pts = [[left, y - m.actualBoundingBoxAscent], [left + m.width, y + m.actualBoundingBoxDescent]].map(([px, py]) => tr.transformPoint({ x: px, y: py }));
    if (ctx.globalAlpha > 0.05 && t.trim()) out.push({ t, x0: Math.min(pts[0].x, pts[1].x) / s, x1: Math.max(pts[0].x, pts[1].x) / s, y0: Math.min(pts[0].y, pts[1].y) / s, y1: Math.max(pts[0].y, pts[1].y) / s });
    fill(t, x, y);
  };
}

/** The boxes outside SAFE (1 px slack), labelled for a readable failure. */
export function outside(boxes: TextBox[]): string[] {
  return [...new Set(boxes
    .filter((b) => b.x0 < SAFE.x0 - 1 || b.x1 > SAFE.x1 + 1 || b.y0 < SAFE.y0 - 1 || b.y1 > SAFE.y1 + 1)
    .map((b) => `${b.t} [${b.x0.toFixed(0)},${b.y0.toFixed(0)}–${b.x1.toFixed(0)},${b.y1.toFixed(0)}]`))];
}
