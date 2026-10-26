// The drawing language every item, prop and creature is written in (prototype: dsl()).
// Flat shapes:
//   l x1 y1 x2 y2 [colour] [width]   line          d x y r [colour]        dot
//   t text x y size                  text          a x y r a0 a1           arc
//   c x y r [fill]                   circle        e x y rx ry [fill]      ellipse
//   r x y w h [fill]                 rectangle     p [x,y,…] [fill]        polygon
// Solids, seen from above at the table's angle, standing on (x, y), up is −y:
//   cyl x y r h fill                 cylinder      box x y w h d fill      block (front + top face)
//   cone x y r h fill                cone          sph x y r fill          sphere
//   dome x y r fill                  half sphere
// Markers (not drawn here): flame x y size (an animated flame + light), light x y radius colour.
//
// Modes: shaded (`sh`, the left-lit pass on flat shapes), `sil` (solid shadow silhouette) and
// `cut` (the white die-cut paper edge around a mini).
import type { Part } from "./defs.ts";
import { FP, shade } from "./util.ts";

export type DslOpts = { sil?: boolean; ink?: string; lw?: number; sh?: boolean; cut?: { fill: string; w: number } };

const RY = 0.45; // ellipse squash for round tops and bases at the table's viewing angle
const isSolid = (k: string) => k === "cyl" || k === "box" || k === "cone" || k === "sph" || k === "dome";

/** The outline of a solid, as a path. */
function solidPath(g: CanvasRenderingContext2D, p: Part) {
  const k = p[0] as string, n = (i: number) => p[i] as number, x = n(1), y = n(2);
  g.beginPath();
  if (k === "cyl") {
    const r = n(3), h = n(4);
    g.moveTo(x - r, y - h);
    g.lineTo(x - r, y);
    g.ellipse(x, y, r, r * RY, 0, Math.PI, 0, true);
    g.lineTo(x + r, y - h);
    g.ellipse(x, y - h, r, r * RY, 0, 0, Math.PI, true);
  } else if (k === "box") {
    const w = n(3), h = n(4), d = n(5) * 0.5;
    g.rect(x - w / 2, y - h - d, w, h + d);
  } else if (k === "cone") {
    const r = n(3), h = n(4);
    g.moveTo(x, y - h);
    g.lineTo(x + r, y);
    g.ellipse(x, y, r, r * RY, 0, 0, Math.PI, false);
  } else if (k === "sph") {
    g.arc(x, y, n(3), 0, 7);
  } else if (k === "dome") {
    const r = n(3);
    g.moveTo(x - r, y);
    g.ellipse(x, y, r, r * 0.8, 0, Math.PI, 0, false);
    g.ellipse(x, y, r, r * RY * 0.6, 0, 0, Math.PI, false);
  }
  g.closePath();
}

function drawSolid(g: CanvasRenderingContext2D, p: Part, lw: number) {
  const k = p[0] as string, n = (i: number) => p[i] as number, x = n(1), y = n(2);
  const fill = p[k === "box" ? 6 : k === "sph" || k === "dome" ? 4 : 5] as string;
  const edge = shade(fill, -0.6);
  g.lineJoin = "round";
  g.lineWidth = lw;
  g.strokeStyle = edge;
  if (k === "cyl" || k === "cone") {
    const r = n(3);
    const gr = g.createLinearGradient(x - r, 0, x + r, 0);
    gr.addColorStop(0, shade(fill, -0.25));
    gr.addColorStop(0.28, shade(fill, 0.3));
    gr.addColorStop(0.55, fill);
    gr.addColorStop(1, shade(fill, -0.55));
    solidPath(g, p);
    g.fillStyle = gr;
    g.fill();
    g.stroke();
    if (k === "cyl") {
      const h = n(4);
      g.beginPath();
      g.ellipse(x, y - h, r, r * RY, 0, 0, 7);
      const tg = g.createLinearGradient(x - r, y - h - r * RY, x + r, y - h + r * RY);
      tg.addColorStop(0, shade(fill, 0.45));
      tg.addColorStop(1, shade(fill, 0.1));
      g.fillStyle = tg;
      g.fill();
      g.stroke();
    }
  } else if (k === "box") {
    const w = n(3), h = n(4), d = n(5) * 0.5;
    const fg = g.createLinearGradient(0, y - h, 0, y);
    fg.addColorStop(0, fill);
    fg.addColorStop(1, shade(fill, -0.35));
    g.fillStyle = fg;
    g.fillRect(x - w / 2, y - h, w, h);
    const sg = g.createLinearGradient(x - w / 2, 0, x + w / 2, 0);
    sg.addColorStop(0, "rgba(255,255,255,.12)");
    sg.addColorStop(1, "rgba(0,0,0,.22)");
    g.fillStyle = sg;
    g.fillRect(x - w / 2, y - h, w, h);
    g.fillStyle = shade(fill, 0.32);
    g.fillRect(x - w / 2, y - h - d, w, d);
    g.beginPath();
    g.rect(x - w / 2, y - h - d, w, h + d);
    g.moveTo(x - w / 2, y - h);
    g.lineTo(x + w / 2, y - h);
    g.stroke();
  } else {
    const r = n(3);
    const gr = g.createRadialGradient(x - r * 0.35, y - r * 0.45, r * 0.08, x, y, r * 1.05);
    gr.addColorStop(0, shade(fill, 0.5));
    gr.addColorStop(0.45, fill);
    gr.addColorStop(1, shade(fill, -0.5));
    solidPath(g, p);
    g.fillStyle = gr;
    g.fill();
    g.stroke();
  }
}

export function dsl(g: CanvasRenderingContext2D, parts: Part[], o: DslOpts): void {
  for (const p of parts) {
    const k = p[0] as string;
    const n = (i: number) => p[i] as number;
    if (k === "flame" || k === "light") continue;
    if (o.cut) {
      // die-cut edge: every shape as solid paper, outlines thickened
      g.fillStyle = g.strokeStyle = o.cut.fill;
      g.lineJoin = g.lineCap = "round";
      if (isSolid(k)) {
        solidPath(g, p);
        g.lineWidth = o.cut.w;
        g.fill();
        g.stroke();
        continue;
      }
      g.beginPath();
      if (k === "l") {
        g.moveTo(n(1), n(2));
        g.lineTo(n(3), n(4));
        g.lineWidth = ((p[6] as number) || o.lw || 1) + o.cut.w;
        g.stroke();
        continue;
      }
      if (k === "d") g.arc(n(1), n(2), n(3) + o.cut.w / 2, 0, 7);
      else if (k === "c") g.arc(n(1), n(2), n(3), 0, 7);
      else if (k === "e") g.ellipse(n(1), n(2), n(3), n(4), 0, 0, 7);
      else if (k === "r") g.rect(n(1), n(2), n(3), n(4));
      else if (k === "p") {
        const q = p[1] as number[];
        for (let i = 0; i < q.length; i += 2) i ? g.lineTo(q[i], q[i + 1]) : g.moveTo(q[i], q[i + 1]);
        g.closePath();
      } else continue;
      g.lineWidth = o.cut.w;
      g.fill();
      g.stroke();
      continue;
    }
    if (isSolid(k)) {
      if (o.sil) {
        solidPath(g, p);
        g.fillStyle = "rgba(20,20,45,.24)";
        g.fill();
      } else drawSolid(g, p, o.lw || 1.2);
      continue;
    }
    let bb: number[] | undefined;
    let fi: string | undefined;
    g.beginPath();
    if (k === "l") {
      if (o.sil) continue;
      g.moveTo(n(1), n(2));
      g.lineTo(n(3), n(4));
      g.strokeStyle = (p[5] as string) || o.ink!;
      g.lineWidth = (p[6] as number) || o.lw!;
      g.lineCap = "round";
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
    g.strokeStyle = o.ink || (fi ? shade(fi, -0.6) : "#000");
    g.lineWidth = o.lw!;
    g.stroke();
  }
}

/** Where a part list wants flames and lights, in its own coordinates. */
export function markers(parts: Part[]): { flames: [number, number, number][]; lights: [number, number, number, string][] } {
  const flames: [number, number, number][] = [], lights: [number, number, number, string][] = [];
  for (const p of parts) {
    if (p[0] === "flame") flames.push([p[1] as number, p[2] as number, p[3] as number]);
    if (p[0] === "light") lights.push([p[1] as number, p[2] as number, p[3] as number, p[4] as string]);
  }
  return { flames, lights };
}
