// Episode 0: the launch series that teaches the format before the story starts. Four short videos,
// one a day, each ending in an easy vote with a stated default, so it works with no comments at all:
//   1 How it works  → warm-up vote: which monster scares you most (sets season 1's first foe)
//   2 Pick a hero   → class
//   3 Pick a look   → palette variant of that class
//   4 The quest     → the first real choice, with odds from the new hero's sheet
// Fixed templates: their voice-over is recorded once into the stock library.
import { type BakedMap, along } from "./map.ts";
import { type Creature, type Defs, recolor } from "./defs.ts";
import { type Frame, big, fade, fit, flicker, heart, narr, parch, standee, star, txt } from "./draw.ts";
import { THROW, throwDie } from "./dice.ts";
import { CLASSES, CLASS_ORDER, type ClassKey, modifier, odds, pct, signed, skillName } from "./sheet.ts";
import { GRN, H, INK, RED, W, cl, ez, font, lp, seg } from "./util.ts";

export type Foe = "skeleton" | "goblin" | "wraith";
export const FEARS: { foe: Foe; label: string; pick: string }[] = [
  { foe: "skeleton", label: "Rattling skeletons", pick: "skeletons" },
  { foe: "goblin", label: "Sneaky goblins", pick: "goblins" },
  { foe: "wraith", label: "Shrieking wraiths", pick: "wraiths" },
];
export const FIRST_CHOICES = [
  { label: "Force the rusted gate", skill: "athletics", dc: 12 },
  { label: "Pick the old lock", skill: "sleight_of_hand", dc: 12 },
  { label: "Search for another way", skill: "perception", dc: 10 },
];

export type Episode0Spec = {
  kind: "episode0";
  part: 1 | 2 | 3 | 4;
  seed: number;
  /** The previous part's vote: which option won and the counts (all zero = nobody voted). */
  recap?: { pick: number; votes: [number, number, number] } | null;
  fear: Foe;
  hero?: { cls: ClassKey; look: number };
  /** Part 1's demonstration roll. */
  demo: { roll: number; skill: string; dc: number };
};

type Option = { label: string; sub?: string };
type Plan = { dur: number; hook: [number, number]; beats: [number, number][]; cta: number; throwAt?: number };

const ASK_Y = 76, CARD_Y = 314, CARD_H = 46, CARD_GAP = 52, LINEUP_Y = 300, LINEUP_CTA_Y = 240;
const COLS = [64, 160, 256];
const HERO_CTA: [number, number] = [W / 2 - 10, 250];

export function plan0(s: Episode0Spec): Plan {
  // hook, then beats, then the call to action (10 s, room to read the cards and comment)
  const lens: Record<number, number[]> = { 1: [6.6, 7, 9.5, 4.5], 2: [4.4, 10.5, 6.5], 3: [4.4, 8.5], 4: [4.4, 7, 6.5, 6] };
  const hook = 3.4;
  let t = hook;
  const beats: [number, number][] = lens[s.part].map((l) => [t, (t += l)]);
  const p: Plan = { dur: t + 10, hook: [0, hook], beats, cta: t };
  if (s.part === 1) p.throwAt = beats[2][0] + 2.3;
  return p;
}

export function heroCreature(defs: Defs, hero?: { cls: ClassKey; look: number }): Creature {
  const cls = hero?.cls || "rogue";
  return recolor(defs.creatures[cls], CLASSES[cls].looks[hero?.look || 0].swap);
}

/** The default when nobody votes, and the options, for a part's call to action. */
export function ctaOf(s: Episode0Spec): { ask: string; options: Option[]; dflt: number; next: string } {
  if (s.part === 1) return { ask: "What scares you most?", options: FEARS.map((f) => ({ label: f.label })), dflt: 0, next: "Part 2" };
  if (s.part === 2) {
    return {
      ask: "Who goes in?", dflt: 1, next: "Part 3",
      options: CLASS_ORDER.map((k) => ({ label: CLASSES[k].name, sub: `${skillName(CLASSES[k].skills[0])} ${signed(modifier(k, CLASSES[k].skills[0]))}` })),
    };
  }
  const cls = s.hero!.cls;
  if (s.part === 3) return { ask: "Pick their look", options: CLASSES[cls].looks.map((l) => ({ label: l.name })), dflt: 0, next: "Part 4" };
  const ps = FIRST_CHOICES.map((c) => odds(modifier(cls, c.skill), c.dc));
  return {
    ask: "The crypt gate is shut", next: "Episode 1",
    dflt: ps.indexOf(Math.max(...ps)),
    options: FIRST_CHOICES.map((c, i) => ({ label: c.label, sub: `${skillName(c.skill)} · ${pct(ps[i])}` })),
  };
}

/** What the previous vote decided, as shown in the recap card. */
function recapOf(s: Episode0Spec): { label: string } | null {
  if (!s.recap) return null;
  const i = s.recap.pick;
  if (s.part === 2) return { label: FEARS[i].label };
  if (s.part === 3) return { label: CLASSES[CLASS_ORDER[i]].name };
  if (s.part === 4) return { label: CLASSES[s.hero!.cls].looks[i].name };
  return null;
}

const NARR: Record<number, string[]> = {
  1: [
    "Every day at 9am, a new episode. One hero. One dungeon. And you call the shots.",
    "Each episode ends with a choice. Comment A, B or C. The most votes decides what happens next.",
    "The dice are real. Your hero's skills set the odds, and we always show them.",
    "No votes? The story takes the default path. It never stops.",
  ],
  2: [
    "", // recap beat
    "Three heroes. Each one is good at different things, and that changes your odds.",
    "Every hero has 3 hearts. Lose them all and your hero dies. For good.",
  ],
  3: ["", "Pick how your hero looks. If they fall, a new hero takes up the quest."],
  4: [
    "",
    "Your sister Ellen ran round the old church widdershins, on a dare... and vanished.",
    "Below the church lies a sealed crypt. It's the only way after her.",
    "",
  ],
};

export type Scene0 = { defs: Defs; map: BakedMap };

export function drawEpisode0(F: Frame, s: Episode0Spec, S: Scene0, P: Plan) {
  const { c } = F, T = F.T;
  const hero = heroCreature(S.defs, s.part >= 3 ? s.hero : undefined);
  const lineupMode = s.part === 2 || s.part === 3;
  const [b1, b2, b3, b4] = P.beats;
  c.fillStyle = "#000";
  c.fillRect(0, 0, W, H);
  c.save();
  const HE = P.hook[1];
  const shake = T < HE ? ((HE - T) / HE) * 4 : 0;
  c.translate(Math.sin(T * 70) * shake, Math.cos(T * 83) * shake);

  // --- the map, with the camera on the hero
  let p = 0.05;
  if (s.part === 1) p = lp(0.04, 0.3, ez(seg(T, b1[0], b3[1])));
  if (s.part === 4) p = lp(0.0, 0.07, ez(seg(T, b2[0], b3[0])));
  if (lineupMode) p = 0.45;
  const hp = along(S.map, p), face = hp[2] >= 0 ? 1 : -1;
  const z = lp(1.5, 1.25, ez(seg(T, P.cta - 1.5, P.cta + 0.5))), vw = W / z, vh = H / z;
  const cx = cl(hp[0] + Math.sin(T * 0.8) * 3, vw / 2, 600 - vw / 2), cy = cl(hp[1] + Math.cos(T * 0.6) * 3 - (T > P.cta - 1 ? 40 : 0), vh / 2, 600 - vh / 2);
  const vx = cx - vw / 2, vy = cy - vh / 2, sx = (m: number) => (m - vx) * z, sy = (m: number) => (m - vy) * z;
  const k = S.map.k;
  c.drawImage(S.map.cv as unknown as CanvasImageSource, vx * k, vy * k, vw * k, vh * k, 0, 0, W, H);

  // in the call to action the hero steps out of the map to sit above the cards
  const out = lineupMode ? 1 : ez(seg(T, P.cta - 0.8, P.cta + 0.2));
  if (!lineupMode && out < 1) {
    c.globalAlpha = 1 - out;
    standee(F, hero, sx(hp[0]), sy(hp[1]), z * 0.95, face, T, 0);
    c.globalAlpha = 1;
  }
  if (out > 0) {
    c.fillStyle = `rgba(13,20,40,${0.55 * out})`;
    c.fillRect(0, 0, W, H);
  }
  if (!lineupMode && out > 0) {
    c.globalAlpha = out;
    standee(F, hero, HERO_CTA[0], HERO_CTA[1], 1.6, 1, T, 0);
    c.globalAlpha = 1;
  }
  flicker(F);

  // --- part tag
  if (T > HE && T < P.cta) {
    parch(F, 16, ASK_Y, 150, 26, undefined, false);
    txt(F, `EPISODE 0 · PART ${s.part} OF 4`, 91, ASK_Y + 18, 11);
  }

  // --- beats
  NARR[s.part].forEach((t, i) => t && narr(F, t, P.beats[i][0] + 0.1, P.beats[i][1], 112));

  if (s.part === 1) part1(F, s, P, sx(hp[0]), sy(hp[1]));
  if (lineupMode) lineup(F, s, S, P);
  if (s.part === 4) part4(F, s, P);
  const rc = recapOf(s);
  if (rc && s.part > 1) recapCard(F, s, rc.label, P.beats[0]);

  // --- call to action
  cta(F, s, P, lineupMode ? null : HERO_CTA);

  // --- hook
  if (T < HE + 0.1) hook(F, s, S, hero, HE);
  c.restore();
  c.fillStyle = "rgba(128,128,128,.4)";
  c.fillRect(0, H - 4, W, 4);
  c.fillStyle = RED;
  c.fillRect(0, H - 4, (W * T) / P.dur, 4);
}

function hook(F: Frame, s: Episode0Spec, S: Scene0, hero: Creature, HE: number) {
  const { c, T } = F;
  const a = T < HE - 0.4 ? 1 : (HE + 0.1 - T) / 0.5;
  c.fillStyle = `rgba(13,20,40,${0.9 * a})`;
  c.fillRect(-20, -20, W + 40, H + 40);
  c.globalAlpha = a;
  standee(F, s.part === 1 ? S.defs.creatures.skeleton : hero, 180, 300, 3.1, 1, T, 0);
  txt(F, "EPISODE 0 · YOU DECIDE THE STORY", W / 2, 96, 13, "#ffe680");
  const lines: [string, string, string] =
    s.part === 1 ? ["YOU DECIDE", "THE STORY", "A dungeon crawl run by your comments."]
      : s.part === 2 ? ["PICK", "YOUR HERO", "Who goes into the dark?"]
        : s.part === 3 ? ["PICK", "A LOOK", `Your ${CLASSES[s.hero!.cls].name.toLowerCase()} needs a face.`]
          : ["MEET YOUR", CLASSES[s.hero!.cls].name.toUpperCase(), "The quest starts now."];
  big(F, lines[0], 180, 386, 50, "#fff", 0.1, 0.4);
  big(F, lines[1], 180, 442, 54, "#ffd23f", 0.5, 0.8);
  if (T > 1.4) txt(F, lines[2], W / 2, 474, 17, "#fff", "center", 600);
  c.globalAlpha = 1;
}

function recapCard(F: Frame, s: Episode0Spec, label: string, [a0, a1]: [number, number]) {
  const { c, T } = F;
  const v = s.recap!.votes, tot = v.reduce((x, y) => x + y, 0), i = s.recap!.pick;
  const a = fade(T, a0, a1);
  if (a <= 0) return;
  const y = lp(-40, 112, a);
  c.save();
  c.globalAlpha = a;
  parch(F, 16, y, W - 76, 96);
  txt(F, tot ? "YESTERDAY'S VOTE" : "NO VOTES YESTERDAY", 158, y + 22, 12);
  txt(F, tot ? `${v[i]} of ${tot} of you chose` : "so we took the default:", 158, y + 45, 15, INK, "center", 600);
  fit(F, `[${"ABC"[i]}] ${label.toUpperCase()}`, 158, y + 72, 16, W - 100, RED);
  c.restore();
}

function part1(F: Frame, s: Episode0Spec, P: Plan, hx: number, hy: number) {
  const { c, T } = F;
  const [, b2, b3] = P.beats;
  // demo pins: what a choice looks like
  const pa = fade(T, b2[0] + 0.6, b2[1]);
  if (pa > 0) {
    const PO = [[-95, -65], [0, -118], [95, -65]];
    PO.forEach(([dx, dy], i) => {
      const a = pa * ez(seg(T, b2[0] + 0.6 + i * 0.3, b2[0] + 1.1 + i * 0.3)), x = cl(hx + dx, 40, 290), y = cl(hy + dy, 190, 420) + Math.sin(T * 5 + i) * 2;
      c.save();
      c.globalAlpha = a;
      c.setLineDash([6, 6]);
      c.strokeStyle = INK;
      c.lineWidth = 2.2;
      c.beginPath();
      c.moveTo(hx, hy - 30);
      c.lineTo(x, y);
      c.stroke();
      c.setLineDash([]);
      c.fillStyle = "#ffe680";
      c.beginPath();
      c.arc(x, y, 15, 0, 7);
      c.fill();
      c.stroke();
      txt(F, "ABC"[i], x, y + 6, 16, INK, "center", 900);
      c.restore();
    });
  }
  // the dice demonstration
  const t0 = P.throwAt!, land = t0 + THROW, mod = modifier("rogue", s.demo.skill), ok = s.demo.roll === 20 || (s.demo.roll !== 1 && s.demo.roll + mod >= s.demo.dc);
  if (T > b3[0] + 0.8 && T < land + 0.2) {
    parch(F, 30, 200, W - 72, 40);
    fit(F, `${skillName(s.demo.skill).toUpperCase()} · DC ${s.demo.dc} · ${pct(odds(mod, s.demo.dc))}`, (W - 12) / 2, 226, 17, W - 100, RED, "center", 900);
  }
  if (T > land + 0.2 && T < b3[1]) {
    parch(F, 30, 200, W - 72, 40, ok ? "#d9f2e0" : "#ffd9d4");
    fit(F, `${s.demo.roll} ${signed(mod)} = ${s.demo.roll + mod} · ${ok ? "SUCCESS" : "FAIL"}`, (W - 12) / 2, 228, 20, W - 100, ok ? GRN : RED, "center", 900);
  }
  throwDie(F, { t0, face: s.demo.roll, ok, until: b3[1] + 0.2 });
  if (ok && T > land + 0.5 && T < b3[1]) star(F, hx, hy - 78, 16, ez(seg(T, land + 0.5, land + 1)) * (1 + 0.08 * Math.sin(T * 12)));
}

function lineup(F: Frame, s: Episode0Spec, S: Scene0, P: Plan) {
  const { c, T } = F;
  const [, b1, b2] = P.beats;
  const toCta = ez(seg(T, P.cta - 0.6, P.cta + 0.4));
  const y = lp(LINEUP_Y, LINEUP_CTA_Y, toCta), sc = lp(2.0, 1.5, toCta);
  const who: Creature[] = s.part === 2 ? CLASS_ORDER.map((k) => S.defs.creatures[k])
    : CLASSES[s.hero!.cls].looks.map((l) => recolor(S.defs.creatures[s.hero!.cls], l.swap));
  const dim = s.part === 2 ? fade(T, b2[0], b2[1], 0.3, 0.3) : 0;
  who.forEach((d, i) => {
    const a = ez(seg(T, b1[0] + 0.3 + i * 0.6, b1[0] + 0.8 + i * 0.6));
    if (a <= 0) return;
    c.save();
    c.globalAlpha = a * (1 - dim * 0.75);
    standee(F, d, COLS[i], y + (1 - a) * 30, sc, 1, T, i * 1.7);
    c.restore();
    // name plates while the lineup is introduced
    const pa = a * (1 - toCta) * (1 - dim);
    if (pa > 0.01) {
      c.save();
      c.globalAlpha = pa;
      parch(F, COLS[i] - 46, y + 40, 92, s.part === 2 ? 70 : 36, undefined, false);
      if (s.part === 2) {
        const k = CLASS_ORDER[i], cd = CLASSES[k], best = cd.skills[0];
        fit(F, cd.name, COLS[i], y + 60, 17, 84);
        fit(F, `${skillName(best)} ${signed(modifier(k, best))}`, COLS[i], y + 78, 12, 84, RED);
        fit(F, cd.blurb, COLS[i], y + 96, 11, 84, INK, "center", 600);
      } else {
        fit(F, CLASSES[s.hero!.cls].looks[i].name, COLS[i], y + 63, 16, 84);
      }
      c.restore();
    }
    // the letter above each, in the call to action
    if (T > P.cta) {
      const la = ez(seg(T, P.cta + 0.6 + i * 0.2, P.cta + 1.1 + i * 0.2)), ly = y - 92 * sc / 2 - 14 + Math.sin(T * 5 + i) * 2;
      c.save();
      c.globalAlpha = la;
      c.fillStyle = "#ffe680";
      c.strokeStyle = INK;
      c.lineWidth = 2.2;
      c.beginPath();
      c.arc(COLS[i], ly, 15, 0, 7);
      c.fill();
      c.stroke();
      txt(F, "ABC"[i], COLS[i], ly + 6, 16, INK, "center", 900);
      c.restore();
    }
  });
  // hearts
  if (s.part === 2 && dim > 0) {
    c.save();
    c.globalAlpha = dim;
    for (let i = 0; i < 3; i++) heart(F, 120 + i * 60, 300, 22, i === 2 ? ez(seg(T, b2[0] + 3.2, b2[0] + 3.8)) : 0);
    txt(F, "3 HEARTS", W / 2 - 10, 356, 22, "#ffe680", "center", 900);
    c.restore();
  }
}

function part4(F: Frame, s: Episode0Spec, P: Plan) {
  const { c, T } = F;
  const b4 = P.beats[3];
  const a = fade(T, b4[0], b4[1]);
  if (a <= 0) return;
  const cls = s.hero!.cls, cd = CLASSES[cls];
  const rows = [...new Set([...FIRST_CHOICES.map((x) => x.skill), ...cd.skills])].slice(0, 5);
  c.save();
  c.globalAlpha = a;
  parch(F, 16, 112, W - 76, 70 + rows.length * 22);
  fit(F, `YOUR ${cd.name.toUpperCase()} · ${cd.looks[s.hero!.look].name.toUpperCase()}`, 30, 138, 16, W - 110, INK, "left", 900);
  for (let i = 0; i < 3; i++) heart(F, 40 + i * 30, 160, 10);
  rows.forEach((k, i) => {
    const m = modifier(cls, k);
    txt(F, skillName(k), 30, 198 + i * 22, 15, INK, "left", 600);
    txt(F, signed(m), W - 72, 198 + i * 22, 15, m >= 4 ? GRN : m <= 0 ? RED : INK, "right", 900);
  });
  c.restore();
}

function cta(F: Frame, s: Episode0Spec, P: Plan, pinFrom: [number, number] | null) {
  const { c, T } = F;
  const t = T - P.cta;
  if (t <= 0) return;
  const C = ctaOf(s);
  const q = ez(seg(t, 0.3, 0.8)), pu = 1 + 0.04 * Math.sin(T * 6);
  c.save();
  c.translate(W / 2 - 10, ASK_Y + 28);
  c.scale(q * pu, q * pu);
  parch(F, -142, -26, 284, 52, "#ffe680");
  fit(F, C.ask.toUpperCase(), 0, 9, 24, 260, INK, "center", 900);
  c.restore();
  if (pinFrom) {
    const [hx, hy] = pinFrom, PO = [[-100, -55], [0, -110], [100, -55]];
    C.options.forEach((_, i) => {
      const a = ez(seg(t, 0.8 + i * 0.2, 1.3 + i * 0.2)), x = cl(hx + PO[i][0], 40, 280), y = cl(hy + PO[i][1], 150, 250) + Math.sin(T * 5 + i) * 2;
      c.save();
      c.globalAlpha = a;
      c.setLineDash([6, 6]);
      c.strokeStyle = INK;
      c.lineWidth = 2.2;
      c.beginPath();
      c.moveTo(hx, hy - 40);
      c.lineTo(x, y);
      c.stroke();
      c.setLineDash([]);
      c.fillStyle = "#ffe680";
      c.beginPath();
      c.arc(x, y, 15, 0, 7);
      c.fill();
      c.stroke();
      txt(F, "ABC"[i], x, y + 6, 16, INK, "center", 900);
      c.restore();
    });
  }
  if (t > 1.4) {
    c.save();
    c.globalAlpha = ez(seg(t, 1.4, 1.8));
    c.fillStyle = "rgba(13,20,40,.85)";
    c.beginPath();
    c.roundRect(16, CARD_Y - 36, W - 76, 31, 6);
    c.fill();
    fit(F, `COMMENT A, B OR C BY 8AM · ${C.next.toUpperCase()} AT 9AM`, W / 2 - 22, CARD_Y - 22, 11, W - 92, "#ffd23f", "center", 900);
    fit(F, `No votes? We go with ${"ABC"[C.dflt]}.`, W / 2 - 22, CARD_Y - 9, 11, W - 92, "#fff", "center", 600);
    c.restore();
  }
  C.options.forEach((o, i) => {
    const a = ez(seg(t, 1.6 + i * 0.25, 2.3 + i * 0.25)), x = 16 + (1 - a) * 400, y = CARD_Y + i * CARD_GAP;
    c.save();
    c.globalAlpha = a;
    parch(F, x, y, W - 76, CARD_H, i === C.dflt ? "#fff3c4" : undefined, false);
    txt(F, `[${"ABC"[i]}]`, x + 12, y + 30, 17, INK, "left");
    c.font = font(600, 15);
    const lw = o.sub ? 150 : W - 140;
    fit(F, o.label, x + 50, y + (o.sub ? 24 : 30), 15, lw, INK, "left", 600);
    if (o.sub) fit(F, o.sub, x + 50, y + 41, 11, lw, RED, "left", 700);
    c.restore();
  });
}
