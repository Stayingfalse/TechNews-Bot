// The drawing language every item, prop and creature is written in (prototype: dsl()).
//   l x1 y1 x2 y2 [colour] [width]   line          d x y r [colour]       dot
//   t text x y size                  text          a x y r a0 a1          arc
//   c x y r [fill]                   circle        e x y rx ry [fill]     ellipse
//   r x y w h [fill]                 rectangle     p [x,y,…] [fill]       polygon
// Filled shapes get a left-lit shading pass (`sh`); `sil` draws only the solid silhouette, for
// cast shadows.
import type { Part } from "./defs.ts";
import { FP } from "./util.ts";

export type DslOpts = { sil?: boolean; ink?: string; lw?: number; sh?: boolean };

export function dsl(g: CanvasRenderingContext2D, parts: Part[], o: DslOpts): void {
  for (const p of parts) {
    const k = p[0] as string;
    const n = (i: number) => p[i] as number;
    let bb: number[] | undefined;
    let fi: string | undefined;
    g.beginPath();
    if (k === "l") {
      if (o.sil) continue;
      g.moveTo(n(1), n(2));
      g.lineTo(n(3), n(4));
      g.strokeStyle = (p[5] as string) || o.ink!;
      g.lineWidth = (p[6] as number) || o.lw!;
      g.stroke();
      continue;
    }
    if (k === "d") {
      if (o.sil) continue;
      g.arc(n(1), n(2), n(3), 0, 7);
      g.fillStyle = (p[4] as string) || o.ink!;
      g.fill();
      continue;
    }
    if (k === "t") {
      if (o.sil) continue;
      g.font = `${n(4)}px ${FP}`;
      g.textAlign = "center";
      g.fillStyle = o.ink!;
      g.fillText(p[1] as string, n(2), n(3));
      continue;
    }
    if (k === "a") {
      if (o.sil) continue;
      g.arc(n(1), n(2), n(3), n(4), n(5));
      g.strokeStyle = o.ink!;
      g.lineWidth = o.lw!;
      g.stroke();
      continue;
    }
    if (k === "c") {
      g.arc(n(1), n(2), n(3), 0, 7);
      bb = [n(1) - n(3), n(2) - n(3), n(3) * 2, n(3) * 2];
      fi = p[4] as string;
    } else if (k === "e") {
      g.ellipse(n(1), n(2), n(3), n(4), 0, 0, 7);
      bb = [n(1) - n(3), n(2) - n(4), n(3) * 2, n(4) * 2];
      fi = p[5] as string;
    } else if (k === "r") {
      g.rect(n(1), n(2), n(3), n(4));
      bb = [n(1), n(2), n(3), n(4)];
      fi = p[5] as string;
    } else if (k === "p") {
      const q = p[1] as number[];
      const xs = q.filter((_, i) => i % 2 === 0), ys = q.filter((_, i) => i % 2 === 1);
      for (let i = 0; i < q.length; i += 2) i ? g.lineTo(q[i], q[i + 1]) : g.moveTo(q[i], q[i + 1]);
      g.closePath();
      const x0 = Math.min(...xs), y0 = Math.min(...ys);
      bb = [x0, y0, Math.max(...xs) - x0, Math.max(...ys) - y0];
      fi = p[2] as string;
    } else continue;
    if (o.sil) {
      g.fillStyle = "rgba(20,20,45,.24)";
      g.fill();
      continue;
    }
    if (fi) {
      g.fillStyle = fi;
      g.fill();
      if (o.sh) {
        g.save();
        g.clip();
        const gr = g.createLinearGradient(bb[0], 0, bb[0] + bb[2], 0);
        gr.addColorStop(0, "rgba(255,255,255,.4)");
        gr.addColorStop(0.45, "rgba(255,255,255,0)");
        gr.addColorStop(1, "rgba(0,0,0,.38)");
        g.fillStyle = gr;
        g.fillRect(bb[0], bb[1], bb[2], bb[3]);
        const gv = g.createLinearGradient(0, bb[1], 0, bb[1] + bb[3]);
        gv.addColorStop(0, "rgba(255,255,255,.24)");
        gv.addColorStop(0.6, "rgba(255,255,255,0)");
        gv.addColorStop(1, "rgba(0,0,0,.24)");
        g.fillStyle = gv;
        g.fillRect(bb[0], bb[1], bb[2], bb[3]);
        g.restore();
      }
    }
    g.strokeStyle = o.ink!;
    g.lineWidth = o.lw!;
    g.stroke();
  }
}
