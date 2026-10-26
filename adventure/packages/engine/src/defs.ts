// Built-in content in the drawing DSL (see dsl.ts), as in the prototype. A weekly payload can add
// or override any of these; merge() combines them.

export type Part = (string | number | number[])[];
export type Creature = { r?: number; base?: string; float?: number; glow?: number; hop?: number; parts: Part[] };
export type Scene = {
  layout: "rooms" | "cave" | "trail";
  amp?: number;
  out: "hatch" | "open";
  dress: [string, number, "edge" | "floor" | "out"][];
  landmark: [string, string];
};
export type Defs = {
  scenes: Record<string, Scene>;
  items: Record<string, Part[]>;
  props: Record<string, Part[]>;
  creatures: Record<string, Creature>;
};
export type Style = { ink: string; paper: string; grid: string; tint: string };

export const STY: Record<string, Style> = {
  ink: { ink: "#1d3b8b", paper: "#f4efe0", grid: "110,160,210", tint: "#e6dfc6" },
  pencil: { ink: "#444", paper: "#efece4", grid: "150,150,150", tint: "#dcd8cc" },
  sepia: { ink: "#5a3a1a", paper: "#efe0bd", grid: "190,150,100", tint: "#dcc89c" },
  blueprint: { ink: "#e8f1ff", paper: "#1b3a6b", grid: "120,160,220", tint: "#12295a" },
};

export const BI: Defs = {
  scenes: {
    dungeon: { layout: "rooms", out: "hatch", dress: [["torch", 10, "edge"], ["pillar", 6, "floor"], ["bones", 4, "floor"], ["rubble", 6, "floor"], ["chest", 1, "floor"]], landmark: ["altar", "The Sunken Altar"] },
    cave: { layout: "cave", out: "hatch", dress: [["stalag", 12, "floor"], ["rubble", 6, "floor"], ["bones", 3, "floor"], ["mushroom", 6, "floor"]], landmark: ["pool", "The Glow Pool"] },
    mountain: { layout: "trail", amp: 60, out: "open", dress: [["peak", 10, "out"], ["tree", 8, "out"], ["rock", 8, "out"], ["bones", 5, "floor"]], landmark: ["door", "The Mountain Door"] },
    forest: { layout: "trail", amp: 85, out: "open", dress: [["tree", 34, "out"], ["stump", 5, "out"], ["rock", 4, "out"], ["flower", 10, "out"]], landmark: ["tent", "Hollow Camp"] },
  },
  items: {
    bones: [["l", -7, -4, 7, 4], ["l", -7, 4, 7, -4], ["c", 0, 0, 3]],
    rubble: [["p", [-6, 2, -3, -4, 2, -2, 5, 3]], ["c", 8, -3, 2], ["c", -9, 5, 1.5]],
    mushroom: [["c", 0, 0, 6], ["d", -2, -1, 1], ["d", 2, 1, 1]],
    stump: [["c", 0, 0, 7], ["c", 0, 0, 4], ["c", 0, 0, 1.5]],
    flower: [["c", 0, 0, 2], ["c", -4, 0, 2], ["c", 4, 0, 2], ["c", 0, -4, 2], ["c", 0, 4, 2]],
    pool: [["e", 0, 0, 30, 19], ["e", 0, 0, 19, 11], ["l", -8, -2, 0, 0], ["l", 2, 3, 10, 1]],
  },
  props: {
    tree: [["r", -3, -14, 6, 14, "#6b4a2a"], ["c", 0, -26, 11, "#4f8f4a"], ["c", -8, -19, 8, "#5da357"], ["c", 8, -19, 8, "#468a44"], ["c", 0, -34, 8, "#63ad5c"]],
    peak: [["p", [-30, 0, 0, -52, 30, 0], "#9a9a9a"], ["p", [0, -52, 30, 0, 8, 0, -4, -26], "#6e6e6e"], ["p", [-9, -38, 0, -52, 9, -38, 3, -33, -3, -35], "#f4f4f4"]],
    rock: [["p", [-12, 0, -10, -10, -2, -15, 9, -12, 13, 0], "#8d8d8d"], ["p", [-2, -15, 9, -12, 13, 0, 4, -3], "#6d6d6d"]],
    torch: [["r", -2, -18, 4, 18, "#6b4a2a"], ["p", [-5, -18, 0, -34, 5, -18], "#ff9a2e"], ["p", [-2.5, -18, 0, -27, 2.5, -18], "#ffe27a"]],
    pillar: [["r", -8, -34, 16, 34, "#bfb8a8"], ["e", 0, -34, 8, 3, "#d8d2c2"], ["r", -10, -4, 20, 4, "#9d968a"]],
    chest: [["r", -11, -10, 22, 10, "#8a5a2a"], ["p", [-11, -10, -9, -17, 9, -17, 11, -10], "#a06a30"], ["r", -2, -12, 4, 5, "#e8c35a"]],
    campfire: [["l", -9, 0, 9, -3, "#4a2f18", 4], ["l", -9, -3, 9, 0, "#4a2f18", 4], ["p", [-6, -3, 0, -22, 6, -3], "#ff7a1e"], ["p", [-3, -3, 0, -14, 3, -3], "#ffd45a"]],
    stalag: [["p", [-7, 0, 0, -24, 7, 0], "#a69f94"], ["p", [0, -24, 7, 0, 2, 0], "#7e776c"]],
    door: [["p", [-22, 0, -22, -26, -14, -40, 14, -40, 22, -26, 22, 0], "#6f6f7a"], ["p", [-12, 0, -12, -24, 0, -32, 12, -24, 12, 0], "#16161c"], ["e", 0, -34, 4, 4, "#8a8a96"]],
    altar: [["r", -20, -16, 40, 16, "#a8a190"], ["r", -24, -20, 48, 6, "#c4bdac"], ["c", 0, -28, 5, "#ffd23f"], ["l", 0, -34, 0, -22, "#ffd23f", 2]],
    tent: [["p", [-24, 0, -4, -30, 16, 0], "#c9b27a"], ["p", [-4, -30, 16, 0, 6, 0], "#a8924f"], ["p", [8, 0, 22, -22, 36, 0], "#b5a068"]],
  },
  creatures: {
    rogue: { r: 17, base: "#cfd9f5", parts: [["p", [-9, 0, -12, -18, 12, -18, 9, 0], "#3f5aa8"], ["e", 0, -27, 8, 9, "#f0c9a0"], ["p", [-11, -27, 0, -42, 11, -27, 6, -19, -6, -19], "#2a3d80"], ["d", -3, -26, 1.4], ["d", 3, -26, 1.4], ["l", 13, -12, 20, -30, "#dde", 2.6], ["l", 10, -14, 16, -14]] },
    wizard: { r: 17, base: "#e0d3f5", parts: [["p", [-12, 0, -8, -30, 8, -30, 12, 0], "#6a4fb0"], ["e", 0, -35, 7, 8, "#f0c9a0"], ["p", [-5, -32, 5, -32, 0, -20], "#eeeeee"], ["e", 0, -39, 14, 3.5, "#4a3590"], ["p", [-11, -39, 0, -64, 11, -39], "#4a3590"], ["l", 16, 0, 16, -48, "#8a5a1f", 2.6], ["c", 16, -52, 5, "#ffd23f"], ["d", -2.5, -35, 1.2], ["d", 2.5, -35, 1.2]] },
    fighter: { r: 18, base: "#e8d5c5", parts: [["p", [-11, 0, -13, -20, 13, -20, 11, 0], "#9aa3b5"], ["e", 0, -28, 8, 9, "#f0c9a0"], ["p", [-9, -30, -9, -40, 9, -40, 9, -30], "#7d8699"], ["l", 14, -8, 14, -34, "#dde", 3], ["l", 9, -14, 19, -14, "#8a5a1f", 2.6], ["d", -3, -28, 1.4], ["d", 3, -28, 1.4]] },
    goblin: { r: 16, base: "#d6e6c0", parts: [["e", 0, -12, 10, 12, "#7fb36a"], ["e", 0, -30, 10, 9, "#8fc47a"], ["p", [-9, -32, -21, -38, -9, -26], "#8fc47a"], ["p", [9, -32, 21, -38, 9, -26], "#8fc47a"], ["d", -4, -31, 1.8, "#c0392b"], ["d", 4, -31, 1.8, "#c0392b"], ["l", -4, -26, 4, -26], ["l", -14, -6, -22, -32, "#7a4a1a", 3.4], ["c", -22, -33, 4, "#7a4a1a"]] },
    skeleton: { r: 16, base: "#e8e2d0", parts: [["l", -3, -10, -4, 0, "#e8e2d0", 2.8], ["l", 3, -10, 4, 0, "#e8e2d0", 2.8], ["r", -1.2, -28, 2.4, 20, "#e8e2d0"], ["r", -8, -25, 16, 3, "#e8e2d0"], ["r", -7, -20, 14, 3, "#e8e2d0"], ["r", -6, -15, 12, 3, "#e8e2d0"], ["l", -8, -24, -13, -12, "#e8e2d0", 2.4], ["l", 8, -24, 13, -16, "#e8e2d0", 2.4], ["e", 0, -35, 8, 8, "#f1ecdc"], ["d", -3, -35, 2], ["d", 3, -35, 2], ["l", 13, -16, 13, -24, "#8a5a1f", 1.6], ["r", 10, -24, 6, 8, "#ffd45a"]] },
    wraith: { r: 16, float: 1, glow: 1, parts: [["p", [-14, 0, -10, -8, -15, -16, -12, -32, -8, -46, 0, -54, 8, -46, 12, -32, 15, -16, 10, -8, 14, 0, 5, -6, 0, 2, -5, -6], "#b9a3e8"], ["d", -4, -40, 2.4, "#ffffff"], ["d", 4, -40, 2.4, "#ffffff"], ["e", 0, -32, 3, 5, "#2a2050"]] },
    slime: { r: 17, hop: 1, base: "#d8f0e2", parts: [["e", 0, -10, 17, 11, "#7fd0a0"], ["e", -6, -15, 4, 2.5, "#d6ffe9"], ["d", -5, -11, 2], ["d", 5, -11, 2]] },
  },
};

export function merge(payload?: Partial<Defs> | null): Defs {
  const d: Defs = JSON.parse(JSON.stringify(BI));
  for (const k of ["scenes", "items", "props", "creatures"] as const) Object.assign(d[k], (payload && payload[k]) || {});
  return d;
}

/** A creature with some of its colours swapped: how a hero's "look" is made. */
export function recolor(cr: Creature, swap: Record<string, string>): Creature {
  const c = (v: unknown) => (typeof v === "string" && swap[v.toLowerCase()]) || v;
  return { ...cr, base: (cr.base && (c(cr.base) as string)) || cr.base, parts: cr.parts.map((p) => p.map(c) as Part) };
}
