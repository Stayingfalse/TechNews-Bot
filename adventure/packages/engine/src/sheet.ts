// Hero classes, skills and the odds of a check (SRD 5.2.1 rules: d20 + ability modifier, + the
// proficiency bonus on the class's skills, against a DC). House rule: a natural 20 always succeeds,
// a natural 1 always fails.

export type Ability = "str" | "dex" | "con" | "int" | "wis" | "cha";
export type ClassKey = "fighter" | "rogue" | "wizard";

export const SKILLS: Record<string, Ability> = {
  athletics: "str", acrobatics: "dex", sleight_of_hand: "dex", stealth: "dex",
  arcana: "int", history: "int", investigation: "int", nature: "int", religion: "int",
  animal_handling: "wis", insight: "wis", medicine: "wis", perception: "wis", survival: "wis",
  deception: "cha", intimidation: "cha", performance: "cha", persuasion: "cha",
};

export const skillName = (s: string) => s.split("_").map((w) => (w === "of" ? w : w[0].toUpperCase() + w.slice(1))).join(" ");

type ClassDef = { name: string; mods: Record<Ability, number>; skills: string[]; blurb: string; looks: { name: string; swap: Record<string, string> }[] };

// Level 1, standard array plus background bonuses (17/15/13/12/10/8 → +3/+2/+1/+1/0/−1).
export const CLASSES: Record<ClassKey, ClassDef> = {
  fighter: {
    name: "Fighter", mods: { str: 3, dex: 1, con: 2, int: -1, wis: 1, cha: 0 }, skills: ["athletics", "intimidation", "perception"],
    blurb: "Breaks doors. Takes hits.",
    looks: [
      { name: "Steel", swap: {} },
      { name: "Bronze", swap: { "#9aa3b5": "#b58a4a", "#7d8699": "#8f6a35", "#f0c9a0": "#c99a6b" } },
      { name: "Blackened", swap: { "#9aa3b5": "#4a4f5c", "#7d8699": "#2f333d", "#f0c9a0": "#8d5a3b" } },
    ],
  },
  rogue: {
    name: "Rogue", mods: { str: 0, dex: 3, con: 1, int: 1, wis: 1, cha: 2 }, skills: ["stealth", "sleight_of_hand", "acrobatics", "perception"],
    blurb: "Sneaks. Picks locks.",
    looks: [
      { name: "Midnight", swap: {} },
      { name: "Crimson", swap: { "#3f5aa8": "#a83f3f", "#2a3d80": "#802a2a", "#f0c9a0": "#c99a6b" } },
      { name: "Moss", swap: { "#3f5aa8": "#4f7a3a", "#2a3d80": "#3a5c2a", "#f0c9a0": "#8d5a3b" } },
    ],
  },
  wizard: {
    name: "Wizard", mods: { str: -1, dex: 2, con: 1, int: 3, wis: 1, cha: 0 }, skills: ["arcana", "history", "investigation", "insight"],
    blurb: "Reads runes. Casts spells.",
    looks: [
      { name: "Violet", swap: {} },
      { name: "Ember", swap: { "#6a4fb0": "#b0584f", "#4a3590": "#903a35", "#f0c9a0": "#c99a6b" } },
      { name: "Frost", swap: { "#6a4fb0": "#4f8fb0", "#4a3590": "#356f90", "#f0c9a0": "#8d5a3b" } },
    ],
  },
};
export const CLASS_ORDER: ClassKey[] = ["fighter", "rogue", "wizard"];
export const PROFICIENCY = 2;

export function modifier(cls: ClassKey, skill: string): number {
  const c = CLASSES[cls], ab = SKILLS[skill];
  if (!ab) throw new Error(`unknown skill ${skill}`);
  return c.mods[ab] + (c.skills.includes(skill) ? PROFICIENCY : 0);
}

export type Mode = "normal" | "advantage" | "disadvantage";

/** Probability that a check succeeds. */
export function odds(mod: number, dc: number, mode: Mode = "normal"): number {
  let ok = 0;
  for (let k = 1; k <= 20; k++) if (k === 20 || (k !== 1 && k + mod >= dc)) ok++;
  const p = ok / 20;
  return mode === "advantage" ? 1 - (1 - p) * (1 - p) : mode === "disadvantage" ? p * p : p;
}

export const pct = (p: number) => `${Math.round(p * 100)}%`;
export const signed = (n: number) => (n >= 0 ? `+${n}` : `${n}`);
