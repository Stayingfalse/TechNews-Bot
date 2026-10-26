// Procedural paper: layered value noise (mottling), fibres and foxing, tiled under the map and the
// cards. Built once from a seed with canvas operations only.
import { prng } from "./prng.ts";
import type { Canvas, MakeCanvas } from "./util.ts";

/** A square grain texture (transparent, drawn over a paper colour). `size` in pixels; detail scales with it. */
export function paperTexture(make: MakeCanvas, seed: number, size = 512): Canvas {
  const rnd = prng(seed * 31 + 5);
  const T = make(size, size), g = T.getContext("2d");
  // mottling: random cells stretched with smoothing; several octaves, drawn 3×3 so it tiles
  for (const [cells, alpha] of [[4, 0.16], [12, 0.12], [40, 0.08], [128, 0.06]] as const) {
    const N = make(cells, cells), n = N.getContext("2d");
    for (let y = 0; y < cells; y++) for (let x = 0; x < cells; x++) {
      const v = rnd();
      n.fillStyle = v < 0.5 ? `rgba(90,60,25,${(0.5 - v) * 2})` : `rgba(255,250,235,${(v - 0.5) * 2})`;
      n.fillRect(x, y, 1, 1);
    }
    g.globalAlpha = alpha;
    g.imageSmoothingEnabled = true;
    g.drawImage(N as unknown as CanvasImageSource, 0, 0, cells, cells, 0, 0, size, size);
  }
  const k = size / 512, area = k * k;
  g.globalAlpha = 1;
  // fibres
  for (let i = 0; i < 900 * area; i++) {
    const x = rnd() * size, y = rnd() * size, a = rnd() * 6.28, l = (3 + rnd() * 9) * Math.pow(k, 0.3), bend = (rnd() - 0.5) * 4 * Math.pow(k, 0.3);
    g.strokeStyle = rnd() < 0.5 ? `rgba(110,80,40,${0.025 + rnd() * 0.05})` : `rgba(255,252,240,${0.05 + rnd() * 0.08})`;
    g.lineWidth = (0.5 + rnd() * 0.5) * Math.pow(k, 0.3);
    g.beginPath();
    g.moveTo(x, y);
    g.quadraticCurveTo(x + Math.cos(a) * l / 2 - Math.sin(a) * bend, y + Math.sin(a) * l / 2 + Math.cos(a) * bend, x + Math.cos(a) * l, y + Math.sin(a) * l);
    g.stroke();
  }
  // foxing
  for (let i = 0; i < 26 * k; i++) {
    const x = rnd() * size, y = rnd() * size, r = (1 + rnd() * 5) * Math.sqrt(k);
    const gr = g.createRadialGradient(x, y, 0, x, y, r);
    gr.addColorStop(0, `rgba(120,70,25,${0.12 + rnd() * 0.15})`);
    gr.addColorStop(1, "rgba(120,70,25,0)");
    g.fillStyle = gr;
    g.fillRect(x - r, y - r, r * 2, r * 2);
  }
  return T;
}
