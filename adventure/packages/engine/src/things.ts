// Story objects: the thing a scene is about (Ellen's ribbon, the dying candle-keeper, the bone
// stair…). The weekly routine names one per node (`focus`); the map draws its prop as the scene's
// landmark, the camera pushes in on it when the narrator says one of its `words`, and `live` animates
// it every frame (in the prop's own units: standing on (0, 0), up is −y). The side-on close-up draws
// the same prop and animation, bigger, on a paper-theatre stage.
import type { Part } from "./defs.ts";

type Ctx = CanvasRenderingContext2D;
export type Thing = {
  /** What it is, for the weekly routine. */
  about: string;
  /** Narration words the camera pushes in on (the first one said). */
  words: string[];
  prop: Part[];
  live?: (c: Ctx, T: number) => void;
  /** Where its live part sits, for the camera and the label (prop units). */
  eye: [number, number];
  /** The colour of its glow in a close-up ("r,g,b"). */
  glow?: string;
};

const wv = (T: number, k: number) => Math.sin(T * 3.1 + k) * 1.6 + Math.sin(T * 5.3 + k * 2) * 0.6;

/** A red silk bow whose tails lift in a draught; `hang` lets one tail spill over an edge. */
export function bow(c: Ctx, x: number, y: number, s: number, T: number, hang = 0) {
  c.save();
  c.translate(x, y);
  c.scale(s, s);
  const tail = (dir: number, len: number, k: number) => {
    c.beginPath();
    c.moveTo(0, 0);
    c.bezierCurveTo(dir * 4, 4 + wv(T, k), dir * 7 + wv(T, k + 1), 9 + hang, dir * 6 + wv(T, k + 2) * 1.5, len + hang);
    c.lineTo(dir * 9 + wv(T, k + 2) * 1.5, len - 2 + hang);
    c.bezierCurveTo(dir * 10 + wv(T, k + 1), 8 + hang, dir * 6, 3 + wv(T, k), 1.5 * dir, 0);
    c.closePath();
    c.fill();
    c.stroke();
  };
  c.lineWidth = 0.6;
  c.strokeStyle = "#4a0e0a";
  c.fillStyle = "#b3241b";
  tail(-1, 15, 0);
  c.fillStyle = "#c8302a";
  tail(1, 17, 1.7);
  for (const dir of [-1, 1]) {
    c.beginPath();
    c.moveTo(0, 0);
    c.bezierCurveTo(dir * 9, -9 + wv(T, dir) * 0.3, dir * 12, 2, 0, 1);
    c.closePath();
    c.fillStyle = dir < 0 ? "#c22b22" : "#d83a30";
    c.fill();
    c.stroke();
  }
  c.beginPath();
  c.ellipse(0, 0.5, 2.2, 2.6, 0, 0, 7);
  c.fillStyle = "#9c1d16";
  c.fill();
  c.stroke();
  c.strokeStyle = "rgba(255,200,190,.6)";
  c.lineWidth = 0.5;
  c.beginPath();
  c.moveTo(-8, -5);
  c.quadraticCurveTo(-5, -7, -2, -3);
  c.stroke();
  c.restore();
}

/** Glowing eyes that look about: the skull and the stair's watcher. */
function eyes(c: Ctx, x: number, y: number, T: number, gap = 2.6, r = 1.1) {
  const look = Math.sin(T * 0.9) * 0.8, a = 0.65 + 0.35 * Math.sin(T * 4);
  c.fillStyle = `rgba(230,60,40,${a})`;
  for (const d of [-gap, gap]) {
    c.beginPath();
    c.arc(x + d + look, y, r, 0, 7);
    c.fill();
  }
}

function motes(c: Ctx, T: number, x: number, y: number, w: number, h: number, rgb: string, n = 10, up = 1) {
  for (let i = 0; i < n; i++) {
    const ph = (T * 0.25 * up + i / n) % 1, a = Math.sin(ph * Math.PI);
    c.fillStyle = `rgba(${rgb},${0.7 * a})`;
    c.beginPath();
    c.arc(x + Math.sin(i * 2.7 + T * 0.7) * w, y - ph * h * up, 0.6 + (i % 2) * 0.5, 0, 7);
    c.fill();
  }
}

const stone = "#8a8478", lid = "#a49d8f", wax = "#efe6d0";

export const THINGS: Record<string, Thing> = {
  ribbon: {
    glow: "255,120,100",
    about: "a red ribbon of Ellen's lying on a stone tomb with two candles",
    words: ["ribbon", "tomb"],
    eye: [0, -18],
    prop: [["box", 0, 0, 50, 13, 22, stone], ["box", 0, -13, 54, 5, 25, lid], ["l", -20, -6, 20, -6, "#6e685d", 0.8],
      ["cyl", -22, -18, 1.8, 7, wax], ["flame", -22, -26, 3], ["cyl", 22, -18, 1.8, 7, wax], ["flame", 22, -26, 3],
      ["light", 0, -24, 90, "255,190,100"]],
    live: (c, T) => bow(c, 2, -18, 0.5, T, 2),
  },
  keeper: {
    glow: "255,190,110",
    about: "an old candle-keeper lying dying, a candle stub in his hand",
    words: ["candle-keeper", "keeper", "old man", "candle"],
    eye: [0, -8],
    prop: [
      // a straw pallet, the old man on it in a grey hooded robe, head to the right
      ["e", 0, 1, 34, 9, "#b89a5a"], ["l", -28, 2, 26, 4, "#8a6e3a", 0.8], ["l", -24, -2, 28, -1, "#8a6e3a", 0.8],
      ["p", [-26, 0, -20, -9, 10, -11, 18, -7, 18, 2, -24, 4], "#5a5468"], ["p", [-26, 0, -30, -3, -28, -7, -20, -9], "#4a4458"],
      ["p", [16, -9, 26, -14, 32, -8, 30, 1, 18, 2], "#4a4458"], ["e", 25, -6, 4.6, 4.2, "#e3c4a2"],
      ["p", [21, -4, 29, -4, 27, 4, 24, 6, 22, 2], "#e8e4dc"], ["d", 26.5, -7, 0.7, "#2a1d14"],
      ["p", [4, -10, 12, -12, 13, -9, 6, -7], "#5a5468"], ["c", 13, -11, 1.8, "#e3c4a2"],
      ["cyl", 13, -12, 1.4, 6, wax], ["flame", 13, -19, 2.6], ["light", 13, -19, 70, "255,180,90"]],
    live: (c, T) => {
      // his chest rises and falls; a thread of breath in the cold
      const br = Math.max(0, Math.sin(T * 1.4)) * 1.6;
      c.fillStyle = "#5a5468";
      c.strokeStyle = "#2a2433";
      c.lineWidth = 0.6;
      c.beginPath();
      c.moveTo(-8, -9);
      c.quadraticCurveTo(2, -13 - br, 12, -9);
      c.lineTo(12, -6);
      c.lineTo(-8, -6);
      c.closePath();
      c.fill();
      c.stroke();
      const ph = (T * 0.5) % 1;
      c.strokeStyle = `rgba(235,235,245,${0.5 * Math.sin(ph * Math.PI)})`;
      c.lineWidth = 1.1;
      c.beginPath();
      c.moveTo(30, -5);
      c.bezierCurveTo(34, -9 - ph * 6, 30, -13 - ph * 8, 35, -19 - ph * 10);
      c.stroke();
    },
  },
  bonestair: {
    glow: "230,210,170",
    about: "a spiral stair of stacked bones going down into the dark, a skull watching from the top",
    words: ["stair", "steps", "bones"],
    eye: [12, -16],
    prop: [["e", 0, -2, 26, 13, "#140e12"], ...Array.from({ length: 9 }, (_, i): Part => {
      const a = Math.PI * 0.9 + i * 0.42, r = 21 - i * 1.6;
      return ["box", Math.cos(a) * r, Math.sin(a) * r * 0.5 - 1, 10 - i * 0.4, 3 + (8 - i) * 0.6, 6, i % 2 ? "#e2d8bf" : "#d4c9ad"];
    }), ["cyl", 12, -6, 2.6, 7, "#cfc4a8"], ["sph", 12, -14, 4.6, "#efe8d6"]],
    live: (c, T) => {
      eyes(c, 12, -14.5, T, 1.6, 0.9);
      motes(c, T, 0, -2, 14, -10, "240,230,210", 8, -1);
    },
  },
  skull: {
    glow: "235,90,70",
    about: "a skull on a stone plinth whose eyes follow you",
    words: ["skull"],
    eye: [0, -26],
    prop: [["box", 0, 0, 16, 18, 12, "#8f897c"], ["box", 0, -18, 20, 3, 14, "#a59e90"], ["sph", 0, -27, 7, "#efe8d6"],
      ["r", -4, -22, 8, 3.5, "#e3dcc8"], ["light", 0, -27, 50, "230,80,60"]],
    live: (c, T) => {
      eyes(c, 0, -28, T, 2.6, 1.3);
      const j = Math.max(0, Math.sin(T * 2.2)) * 1.2; // the jaw clicks
      c.fillStyle = "#e3dcc8";
      c.strokeStyle = "#2a1d14";
      c.lineWidth = 0.6;
      c.fillRect(-4, -22 + j, 8, 3.5);
      c.strokeRect(-4, -22 + j, 8, 3.5);
    },
  },
  pool: {
    glow: "120,220,240",
    about: "a still pool that glows blue; a face (Ellen's) shows in it",
    words: ["pool", "water", "face", "reflection"],
    eye: [0, 0],
    prop: [["e", 0, 0, 30, 15, "#2f5f74"], ["e", -3, -2, 20, 9, "#4f8ea6"], ["light", 0, 0, 90, "90,200,230"]],
    live: (c, T) => {
      for (let i = 0; i < 3; i++) {
        const ph = (T * 0.35 + i / 3) % 1;
        c.strokeStyle = `rgba(215,240,250,${0.5 * (1 - ph)})`;
        c.lineWidth = 0.8;
        c.beginPath();
        c.ellipse(4, 2, 4 + ph * 22, 2 + ph * 10, 0, 0, 7);
        c.stroke();
      }
      const a = 0.35 + 0.3 * Math.sin(T * 0.8); // the face: there, and gone
      c.fillStyle = `rgba(235,225,215,${a})`;
      c.beginPath();
      c.ellipse(-3, -1, 6, 4.5, 0, 0, 7);
      c.fill();
      c.fillStyle = `rgba(40,60,80,${a})`;
      c.fillRect(-6, -2, 1.6, 1);
      c.fillRect(-1.5, -2, 1.6, 1);
      c.fillRect(-4, 1, 2.5, 0.8);
    },
  },
  irondoor: {
    glow: "210,200,190",
    about: "a heavy iron door, studded and locked, in a stone wall",
    words: ["iron door", "door"],
    eye: [0, -20],
    prop: [["box", 0, 0, 40, 40, 8, "#77747c"], ["p", [-13, -2, -13, -30, 13, -30, 13, -2], "#3a3640"], ["l", -13, -12, 13, -12, "#6b6772", 1.6],
      ["l", -13, -22, 13, -22, "#6b6772", 1.6], ["c", 7, -16, 1.8, "#b8b2a0"]],
    live: (c, T) => {
      const g = 0.5 + 0.5 * Math.sin(T * 2.4); // a glint on the lock, a rattle now and then
      c.fillStyle = `rgba(255,240,200,${0.7 * g})`;
      c.beginPath();
      c.arc(7.6, -16.6, 0.9, 0, 7);
      c.fill();
      motes(c, T, 0, -30, 12, -26, "220,210,190", 6, -1);
    },
  },
  greendoor: {
    glow: "140,240,140",
    about: "a door in the rock with green light and the smell of grass behind it: the way into Elfland",
    words: ["green door", "door", "green"],
    eye: [0, -18],
    prop: [["box", 0, 0, 44, 36, 10, "#6f6b64"], ["p", [-12, -1, -12, -22, 0, -30, 12, -22, 12, -1], "#3f8a4a"],
      ["l", -12, -1, -12, -22, "#2a5a30", 1], ["light", 0, -15, 110, "120,230,120"]],
    live: (c, T) => {
      const a = 0.35 + 0.25 * Math.sin(T * 1.6);
      const g = c.createRadialGradient(0, -14, 1, 0, -14, 22);
      g.addColorStop(0, `rgba(200,255,180,${a})`);
      g.addColorStop(1, "rgba(120,230,120,0)");
      c.fillStyle = g;
      c.fillRect(-24, -40, 48, 46);
      for (let i = 0; i < 4; i++) { // leaves drifting out
        const ph = (T * 0.3 + i / 4) % 1;
        c.fillStyle = `rgba(110,190,90,${Math.sin(ph * Math.PI)})`;
        c.beginPath();
        c.ellipse(-6 + i * 4 + Math.sin(T + i) * 6 + ph * 14, -18 + ph * 20, 2, 1, T + i, 0, 7);
        c.fill();
      }
    },
  },
  larder: {
    glow: "255,200,120",
    about: "a goblin larder: a rough table piled with bread, meat and apples",
    words: ["larder", "food", "table", "bread"],
    eye: [0, -16],
    prop: [["box", 0, 0, 46, 12, 20, "#6b4a2a"], ["sph", -12, -16, 5, "#c48a3f"], ["sph", -4, -17, 4.5, "#b0322a"], ["sph", 2, -15, 3.5, "#c43a2a"],
      ["e", 12, -16, 8, 4.5, "#9a4a3a"], ["cyl", -18, -12, 2.4, 5, "#7a5a32"]],
    live: (c, T) => {
      for (let i = 0; i < 4; i++) { // flies
        const a = T * (3 + i) + i * 1.7;
        c.fillStyle = "#1a1418";
        c.beginPath();
        c.arc(Math.cos(a) * (10 + i * 2), -24 + Math.sin(a * 1.3) * 4, 0.9, 0, 7);
        c.fill();
      }
    },
  },
  feast: {
    glow: "255,215,130",
    about: "a golden feast laid out in Elfland, warm and steaming: the food you must not eat",
    words: ["feast", "food", "table", "golden"],
    eye: [0, -16],
    prop: [["box", 0, 0, 56, 12, 22, "#8a5a2a"], ["e", 0, -13, 26, 7, "#f2e8d0"], ["e", -12, -15, 6, 3, "#e0b040"], ["e", 12, -15, 6, 3, "#e0b040"],
      ["sph", -12, -18, 3.5, "#c0702a"], ["sph", 12, -18, 3.5, "#a03a2a"], ["cyl", 0, -14, 2.4, 9, "#e0b040"], ["light", 0, -18, 90, "255,210,120"]],
    live: (c, T) => {
      c.strokeStyle = "rgba(245,240,230,.4)";
      c.lineWidth = 1;
      for (const x of [-12, 12]) { // steam
        const ph = (T * 0.4 + (x > 0 ? 0.5 : 0)) % 1;
        c.globalAlpha = Math.sin(ph * Math.PI);
        c.beginPath();
        c.moveTo(x, -21);
        c.bezierCurveTo(x - 3, -26 - ph * 4, x + 3, -30 - ph * 6, x, -36 - ph * 8);
        c.stroke();
      }
      c.globalAlpha = 1;
      motes(c, T, 0, -16, 22, 14, "255,225,140", 8);
    },
  },
  lamp: {
    glow: "255,245,200",
    about: "a great lamp hanging in a hall, shining with no flame at all",
    words: ["lamp", "light"],
    eye: [0, -40],
    prop: [["cyl", 0, 0, 3, 30, "#5a5560"], ["box", 0, -30, 16, 4, 10, "#7a7480"], ["sph", 0, -40, 8, "#fff6c8"], ["light", 0, -40, 140, "255,240,190"]],
    live: (c, T) => {
      const p = 1 + 0.08 * Math.sin(T * 1.2);
      for (let i = 0; i < 8; i++) { // rays turning slowly
        const a = T * 0.2 + (i / 8) * Math.PI * 2;
        c.strokeStyle = "rgba(255,245,200,.35)";
        c.lineWidth = 1.2;
        c.beginPath();
        c.moveTo(Math.cos(a) * 10, -40 + Math.sin(a) * 10);
        c.lineTo(Math.cos(a) * 20 * p, -40 + Math.sin(a) * 20 * p);
        c.stroke();
      }
    },
  },
  statues: {
    glow: "210,215,235",
    about: "two young men standing still as statues, grey as stone: Ellen's enchanted brothers",
    words: ["brothers", "statues", "statue"],
    eye: [0, -26],
    prop: [["box", -12, 0, 14, 4, 10, "#8f897c"], ["cyl", -12, -4, 5, 18, "#9e9a92"], ["sph", -12, -27, 5, "#aaa69e"],
      ["box", 12, 0, 14, 4, 10, "#8f897c"], ["cyl", 12, -4, 5, 18, "#9e9a92"], ["sph", 12, -27, 5, "#aaa69e"]],
    live: (c, T) => {
      motes(c, T, 0, -6, 20, 30, "230,230,240", 10);
      const blink = Math.sin(T * 0.7) > 0.96 ? 1 : 0; // once in a while, an eye opens
      if (blink) eyes(c, -12, -28, T, 1.4, 0.6);
    },
  },
  sword: {
    glow: "190,220,255",
    about: "a sword (or wand) that cuts enchantment, glowing in a cleft rock: Merlin's gift",
    words: ["sword", "blade", "wand"],
    eye: [0, -26],
    prop: [["p", [-22, 0, -17, -13, -4, -19, 10, -16, 21, 0], "#8f8a84"], ["p", [-4, -19, 10, -16, 21, 0, 4, -6], "#6f6a65"],
      ["p", [-1.6, -15, -1.6, -40, 0, -44, 1.6, -40, 1.6, -15], "#dfe6f0"], ["r", -7, -42, 14, 2.8, "#c09030"],
      ["r", -1, -52, 2, 10, "#6b4a2a"], ["c", 0, -53, 1.8, "#c09030"], ["light", 0, -30, 100, "190,220,255"]],
    live: (c, T) => {
      const y = -40 + ((T * 12) % 26); // a shine running down the blade
      const g = c.createLinearGradient(0, y - 4, 0, y + 4);
      g.addColorStop(0, "rgba(255,255,255,0)");
      g.addColorStop(0.5, "rgba(255,255,255,.9)");
      g.addColorStop(1, "rgba(255,255,255,0)");
      c.fillStyle = g;
      c.fillRect(-1, y - 4, 2.4, 8);
      motes(c, T, 0, -12, 10, 24, "200,225,255", 8);
    },
  },
};

export const THING_KEYS = Object.keys(THINGS) as [string, ...string[]];

/** The thing's word the narration says (its words in order of preference: "ribbon" before
 *  "tomb"), which line it's in, and how far into that line (0-1). */
export function focusWord(thing: string, lines: { key: string; text: string }[]): { key: string; word: string; at: number } | null {
  const t = THINGS[thing];
  if (!t) return null;
  for (const w of t.words) {
    const re = new RegExp(`\\b${w.replace(/[-\s]/g, "[-\\s]")}`);
    for (const l of lines) {
      const low = l.text.toLowerCase(), i = low.search(re);
      if (i >= 0) return { key: l.key, word: w, at: i / Math.max(1, low.length) };
    }
  }
  return null;
}
