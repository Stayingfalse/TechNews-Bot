// A story episode: one node of the weekly arc, resolved by the server (the vote that led here, the
// real dice roll and its outcome, the hero's hearts). The prototype's frame(), in the new look:
//   hook → story (recap card, hero walks, foe follows) → check (card with odds, the die lands on the
//   rolled face) → aftermath → call to action (choices as wax seals and cards).
import { type BakedMap, along } from "./map.ts";
import { type Creature, type Defs, recolor } from "./defs.ts";
import {
  type Frame, type Light, big, dtxt, fade, fit, flame, heart, lighting, narr, parch, ribbon, seal, standee, star, txt,
} from "./draw.ts";
import { THROW, throwDie, BOUNCES } from "./dice.ts";
import { CLASSES, type ClassKey, type Mode, modifier, odds, pct, signed, skillName } from "./sheet.ts";
import { CREAM, GOLD, GRN, H, INK, RED, W, cl, ez, font, lp, seg } from "./util.ts";
import { type Cues, type Seg, cap, line, words } from "./voice.ts";
import { THINGS, focusWord } from "./things.ts";
import { drawStage } from "./stage.ts";

export type Roll = { dice: number[]; kept: number; mod: number; total: number; ok: boolean; p: number; natural?: 1 | 20 };

export type StorySpec = {
  kind: "story";
  ep: number;
  node: string;
  scene: { type: string; seed: number; dir?: "N" | "E" | "S" | "W"; size?: number; style?: string; name?: string };
  hero: { cls: ClassKey; look: number };
  foe?: string;
  hook: [string, string];
  recap?: { pick: number; votes: number[]; label: string; line: string } | null;
  story: string;
  check?: { skill: string; dc: number; mode: Mode; harm: boolean; roll: Roll; rally?: number } | null;
  after: string;
  hearts: { before: number; after: number };
  dead?: boolean;
  ask: string;
  choices: { label: string }[];
  default: number;
  tone?: { story?: string; after?: string };
  cues?: Cues;
  /** The party: companions the server drew, each with the viewer's handle to show (or none). */
  party?: Companion[];
  /** Credits shown on screen: the viewer the roll is credited to. */
  credits?: { rolledBy?: string | null; shouters?: string[] };
  /** What the comments added up to: how many voted, the word the Voices shouted (only when the
   *  story uses it). */
  voices?: { voters: number; shout?: { word: string; n: number } };
  /** Said before the recap line on a week's first episode: the story so far in a sentence or two
   *  (the arc's `previously`, written by the weekly routine). */
  previously?: string;
  /** The caption's "Story so far": a line for last week and one per recent episode, oldest first. */
  soFar?: string[];
  /** The story object the scene is about (things.ts): drawn as the landmark, pushed in on. */
  focus?: { thing: string; label?: string };
};

export type Companion = { name: string; cls: ClassKey; look: number; handle?: string | null };

export type StoryPlan = { dur: number; hook: [number, number]; story: [number, number]; check?: [number, number]; after: [number, number]; cta: number; throwAt?: number;
  /** When the narrator says the focus object's word: the camera pushes in on it. */
  focus?: number;
  /** The side-on close-up (the outcome, on a paper-theatre stage). */
  stage?: [number, number] };

const ASK_Y = 76, CARD_Y = 314, CARD_H = 46, CARD_GAP = 52, LEAD = 0.25;
const HERO_CTA: [number, number] = [W / 2 - 10, 250];
const est = (t: string) => t.trim().split(/\s+/).length / 2.6 + 1;

export function planStory(s: StorySpec): StoryPlan {
  const c = s.cues;
  if (c) {
    const story = c.story - LEAD, cta = c.cta - LEAD, after = c.after - LEAD;
    const p: StoryPlan = { dur: Math.max(c.end + 2, cta + 9), hook: [0, story], story: [story, s.check ? c.check - LEAD : after], after: [after, cta], cta };
    if (s.check) {
      p.check = [c.check - LEAD, after];
      p.throwAt = Math.max(p.check[0] + 1, c.roll - 0.35 - THROW);
    }
    return withFocus(s, p, c.focus);
  }
  let t = 3.4;
  const add = (l: number): [number, number] => [t, (t += l)];
  const story = add(Math.max(4, est(s.story)) + 2), check = s.check ? add(6.5) : undefined, after = add(Math.max(3.5, est(s.after)));
  const p: StoryPlan = { dur: t + 10, hook: [0, 3.4], story, check, after, cta: t };
  if (check) p.throwAt = check[0] + 1.6;
  return withFocus(s, p);
}

/** The push-in's moment: the voice's cue for the word, or where the word falls in its line. */
function withFocus(s: StorySpec, p: StoryPlan, cue?: number): StoryPlan {
  if (!s.focus) return p;
  const w = focusWord(s.focus.thing, [{ key: "story", text: s.story }, { key: "after", text: s.after }]);
  const win = w?.key === "after" ? p.after : p.story;
  const at = cue != null ? cue - LEAD : win[0] + 0.3 + (w ? w.at : 0) * (win[1] - win[0]) * 0.8;
  // not before yesterday's vote card has had its moment (it sits where the close-up goes)
  const stage: [number, number] | undefined = p.cta - p.after[0] > 2 ? [p.after[0] - 0.1, p.cta - 0.4] : undefined;
  return { ...p, focus: cl(at, p.story[0] + RECAP_S - 0.4, p.cta - 2.5), stage };
}

/** The close-up's zoom, and when it lets go: before the dice if there's a check, else before the question. */
export const FOCUS_Z = 2.5;
const RECAP_S = 2.6;
function focusAmount(T: number, P: StoryPlan): number {
  if (P.focus == null) return 0;
  let until = P.check && P.focus < P.check[0] ? P.check[0] - 0.3 : P.cta - 1.2;
  if (P.stage) until = Math.min(until, P.stage[0] - 0.5);
  return ez(seg(T, P.focus - 0.2, P.focus + 1)) * (1 - ez(seg(T, until, until + 0.9)));
}

export function storyHero(defs: Defs, h: StorySpec["hero"]): Creature {
  return recolor(defs.creatures[h.cls], CLASSES[h.cls].looks[h.look].swap);
}

// ---------------------------------------------------------------- voice

const letters = (n: number) => (n === 2 ? "A or B" : "A, B or C");

/** The daily clip (hook = recap line, story, aftermath, question) and the reusable lines between them. */
export function scriptStory(s: StorySpec): { daily: Seg[]; check?: string; roll?: string; tail: string } {
  const r = s.check?.roll, okTag = r ? (r.ok ? "[relieved]" : "[grimly]") : "[softly]";
  const afterLine = s.dead ? `${s.after} [grimly] And your hero falls.` : s.after;
  const daily = [
    ...(s.previously ? [line("previously", `[softly] ${s.previously}`)] : []),
    line("hook", `[whispers] ${s.recap?.line || s.hook.join(" ")}`),
    line("story", `${s.tone?.story || "[tense]"} ${s.story}`),
    line("after", `${s.tone?.after || okTag} ${afterLine}`),
    line("ask", s.dead ? "[softly] A new hero will take up the quest." : `[urgent] ${s.ask}`),
  ];
  const tail = s.dead ? "Rest well, hero." : `Comment ${s.choices.length === 2 ? "A or B" : "A, B, or C"}. Next episode, tomorrow at nine.`;
  if (!s.check || !r) return { daily, tail };
  const mode = s.check.mode === "advantage" ? " With advantage." : s.check.mode === "disadvantage" ? " With disadvantage." : "";
  const sign = r.mod >= 0 ? "plus" : "minus";
  const result = r.natural === 20 ? "Natural twenty! Success!" : r.natural === 1 ? "A natural one. Failure."
    : `${cap(words(r.kept))}, ${sign} ${words(Math.abs(r.mod))}. ${cap(words(r.total))}. ${r.ok ? "Success!" : "Failure."}`;
  return {
    daily,
    check: `${skillName(s.check.skill)} check. Difficulty ${words(s.check.dc)}.${mode}`,
    roll: result,
    tail,
  };
}

export const storyMusic = (s: StorySpec) => (s.scene.type === "forest" || s.scene.type === "mountain" ? "old_tower_inn.mp3" : "dungeon_ambience.ogg");

export function storySfx(s: StorySpec, P: StoryPlan): { t: number; file: string; gain: number }[] {
  if (!s.check || P.throwAt == null) return [];
  const files = ["dice-throw-1.ogg", "dice-throw-2.ogg", "dice-throw-3.ogg", "dice-throw-2.ogg"], gains = [1, 0.75, 0.5, 0.3];
  return [{ t: Math.max(0, P.throwAt - 1.3), file: "dice-shake-1.ogg", gain: 0.6 }, ...BOUNCES.map((b, i) => ({ t: P.throwAt! + b * THROW, file: files[i], gain: gains[i] }))];
}

const MUSIC_CREDITS: Record<string, string> = {
  "dungeon_ambience.ogg": "“Dungeon Ambience” by yd",
  "old_tower_inn.mp3": "“The Old Tower Inn” by RandomMind",
};

export function captionStory(s: StorySpec): string {
  const head = `Episode ${s.ep}: ${s.hook.join(" ").replace(/\s+/g, " ").toLowerCase().replace(/^./, (m) => m.toUpperCase())} ⚔️`;
  const ask = s.dead ? "Your hero has fallen. A new hero rises next." : `${s.ask} Comment ${letters(s.choices.length)} by 8am 👇 No votes? We go with ${"ABC"[s.default]}.`;
  const soFar = s.soFar?.length ? [`📜 Story so far\n${s.soFar.join("\n")}`] : [];
  return [head, ask, ...soFar, "#dungeoncrawl #ttrpg #chooseyourownadventure #fantasy #tabletopgames",
    `Music: ${MUSIC_CREDITS[storyMusic(s)]} (CC0). Dice sounds: Kenney (CC0). Includes material from the SRD 5.2.1 by Wizards of the Coast LLC (CC BY 4.0).`].join("\n\n");
}

export function commentStory(s: StorySpec): string {
  if (s.dead) return "Rest well, hero. A new hero rises next.";
  return `${s.choices.map((o, i) => `${"ABC"[i]}) ${o.label}`).join(" · ")}\nComment your letter by 8am. No votes? We go with ${"ABC"[s.default]}.`
    + `\nShout a word to the hero (torch, rope, wolf…). Comment "join" to join the party.`;
}

// ---------------------------------------------------------------- drawing

export type SceneStory = { defs: Defs; map: BakedMap };

export function drawStory(F: Frame, s: StorySpec, S: SceneStory, P: StoryPlan) {
  const { c, T } = F;
  const hero = storyHero(S.defs, s.hero), foe = s.foe ? S.defs.creatures[s.foe] : undefined;
  const fail = !!s.check && !s.check.roll.ok, land = P.throwAt != null ? P.throwAt + THROW : Infinity;
  c.fillStyle = "#000";
  c.fillRect(0, 0, W, H);
  c.save();
  const HE = P.hook[1];
  const shake = T < HE ? ((HE - T) / HE) * 4 : fail && T > land && T < land + 0.4 ? (land + 0.4 - T) * 9 : 0;
  c.translate(Math.sin(T * 70) * shake, Math.cos(T * 83) * shake);

  // the walk: in during the story, on during the aftermath; with a focus object, up to it
  const lm = s.focus && S.map.lp && THINGS[s.focus.thing] ? S.map.lp : null;
  const total = S.map.len[S.map.len.length - 1] || 1, near = lm ? Math.max(0.5, 1 - 62 / total) : 0;
  let p: number;
  if (lm && P.focus != null) p = lp(0.05, near, ez(seg(T, P.story[0], Math.max(P.story[0] + 1.5, P.focus + 0.8))));
  else {
    p = lp(0.05, s.check ? 0.4 : 0.55, ez(seg(T, P.story[0], P.story[1])));
    p = lp(p, 0.8, ez(seg(T, P.after[0], P.after[1])));
  }
  const hp = along(S.map, p), face = hp[2] >= 0 ? 1 : -1;
  const fz = lm ? focusAmount(T, P) : 0;
  let z = lp(lp(1.5, 1.25, ez(seg(T, P.cta - 1.5, P.cta + 0.5))), FOCUS_Z, fz);
  let tx = lp(hp[0] + Math.sin(T * 0.8) * 3, lm ? lm[0] : 0, fz), ty = lp(hp[1] + Math.cos(T * 0.6) * 3, lm ? lm[1] + 34 : 0, fz);
  // the question: the camera pulls back to show where each choice leads, pinned on the map
  const pins = s.dead ? null : pinSpots(s, S, lm);
  const pv = pins ? ez(seg(T, P.cta - 0.8, P.cta + 0.4)) : 0;
  if (pins && pv > 0) {
    const xs = [hp[0], ...pins.map((q) => q.x)], ys = [hp[1], ...pins.map((q) => q.y)];
    const bw = Math.max(...xs) - Math.min(...xs) + 40, bh = Math.max(...ys) - Math.min(...ys) + 60;
    const zp = cl(Math.min(230 / bw, 220 / bh), 1.05, 1.6);
    const bx = (Math.max(...xs) + Math.min(...xs)) / 2, by = (Math.max(...ys) + Math.min(...ys)) / 2;
    z = lp(z, zp, pv);
    tx = lp(tx, bx + (W / 2 - PIN_BOX[0]) / zp, pv);
    ty = lp(ty, by + (H / 2 - PIN_BOX[1]) / zp, pv);
  }
  const vw = W / z, vh = H / z;
  // for the pins the camera may look past the map's top edge (the landmark is often near it)
  const over = 90 * Math.max(pv, lm && lm[1] < 120 ? fz : 0);
  const cx = cl(tx, vw / 2, 600 - vw / 2), cy = cl(ty, vh / 2 - over, 600 - vh / 2);
  const vx = cx - vw / 2, vy = cy - vh / 2, sx = (m: number) => (m - vx) * z, sy = (m: number) => (m - vy) * z;
  const onStage = !!(lm && P.stage && T >= P.stage[0] && T < P.stage[1]);
  if (!onStage) c.drawImage(S.map.cv as unknown as CanvasImageSource, vx * S.map.k, vy * S.map.k, vw * S.map.k, vh * S.map.k, 0, 0, W, H);

  const out = pins ? 0 : ez(seg(T, P.cta - 0.8, P.cta + 0.2));
  const toks: { d: Creature; x: number; y: number; ph: number; a: number; rim: string; sc?: number; tag?: string | null }[] = [];
  if (out < 1) toks.push({ d: hero, x: hp[0], y: hp[1], ph: 0, a: 1 - out, rim: GOLD });
  // the party: viewers' companions walk behind the hero, each with its viewer's handle
  const crew = T > HE ? s.party || [] : [];
  crew.forEach((m, i) => {
    const cp = along(S.map, Math.max(0, p - 0.04 * (i + 1)));
    const a = seg(T, HE, HE + 0.6 + i * 0.15) * (1 - out);
    if (a > 0) toks.push({ d: storyHero(S.defs, { cls: m.cls, look: m.look }), x: cp[0], y: cp[1], ph: 0.9 + i, a, rim: CREAM, sc: 0.68, tag: m.handle });
  });
  if (foe && T > P.story[0]) {
    let gap = 0.14;
    if (s.check) gap = lp(0.14, fail ? 0.045 : 0.1, ez(seg(T, land, land + 0.7)));
    gap = lp(gap, fail ? 0.07 : 0.2, ez(seg(T, P.after[0], P.after[1])));
    const fp = along(S.map, Math.max(0, p - gap)), fa = seg(T, P.story[0], P.story[0] + 1) * (1 - out);
    if (fa > 0) toks.push({ d: foe, x: fp[0], y: fp[1], ph: 1.7, a: fa, rim: RED });
  }
  if (!onStage) toks.sort((a, b) => a.y - b.y).forEach((o) => {
    c.globalAlpha = o.a;
    standee(F, o.d, sx(o.x), sy(o.y), z * 0.95 * (o.sc || 1), face, T, o.ph, o.rim);
    c.globalAlpha = 1;
  });
  if (out > 0) {
    c.fillStyle = `rgba(14,9,18,${0.3 * out})`;
    c.fillRect(0, 0, W, H);
    c.globalAlpha = out;
    standee(F, hero, HERO_CTA[0], HERO_CTA[1], 1.6, 1, T, 0);
    c.globalAlpha = 1;
  }
  const lights: Light[] = [];
  for (const l of S.map.lights) {
    const X = sx(l.x), Y = sy(l.y), r = l.r * z;
    if (X > -r && X < W + r && Y > -r && Y < H + r) lights.push({ x: X, y: Y, r, rgb: l.rgb });
  }
  lights.push({ x: lp(sx(hp[0]), HERO_CTA[0], out), y: lp(sy(hp[1]), HERO_CTA[1], out) - 18, r: 125, rgb: "255,190,110" });
  if (onStage) {
    drawStage(F, s.scene.type, s.focus!.thing, S.defs, {
      hero, party: (s.party || []).map((m) => storyHero(S.defs, { cls: m.cls, look: m.look })), foe, fail,
    }, seg(T, P.stage![0], P.stage![1]));
  } else {
    lighting(F, lights, 0.52);
    S.map.flames.forEach((f, i) => {
      const X = sx(f.x), Y = sy(f.y);
      if (X > -20 && X < W + 20 && Y > -20 && Y < H + 20) flame(F, X, Y, f.s * z * 0.95, i * 1.9);
    });
    if (lm) focusThing(F, s, sx(lm[0]), sy(lm[1]), z, fz);
  }
  // in and out of the stage: a quick dip to black
  if (lm && P.stage) {
    const dip = Math.max(0, 1 - Math.abs(T - P.stage[0]) / 0.25, 1 - Math.abs(T - P.stage[1]) / 0.25);
    if (dip > 0) {
      c.fillStyle = `rgba(8,5,8,${dip})`;
      c.fillRect(-20, -20, W + 40, H + 40);
    }
  }

  // the companions' handle tags, over the lighting so they stay readable
  if (!onStage) toks.forEach((o) => {
    if (!o.tag) return;
    c.globalAlpha = o.a;
    const X = sx(o.x), Y = sy(o.y) + 14;
    c.font = font(700, 9);
    const w = Math.min(90, c.measureText(`@${o.tag}`).width + 12);
    parch(F, X - w / 2, Y, w, 15);
    fit(F, `@${o.tag}`, X, Y + 11, 9, w - 8, INK, "center", 700);
    c.globalAlpha = 1;
  });

  // HUD: episode and hearts
  if (T > HE && T < P.cta) {
    parch(F, 16, ASK_Y, 104, 26);
    dtxt(F, `EPISODE ${s.ep}`, 68, ASK_Y + 17, 11);
    const lost = s.hearts.before - s.hearts.after, broke = lost > 0 ? ez(seg(T, land + 0.3, land + 0.9)) : 0;
    for (let i = 0; i < 3; i++) {
      const alive = i < s.hearts.after || (i < s.hearts.before && broke < 1);
      heart(F, 140 + i * 24, ASK_Y + 13, 8, i >= s.hearts.after && i < s.hearts.before ? broke : alive ? 0 : 1);
    }
    voteTag(F, s);
  }

  // story, with yesterday's vote on a card first
  // in a close-up the card drops to the bottom like a subtitle, and the object's word is in red
  const sub = (t: number) => (lm && focusAmount(t, P) > 0.5 ? -470 : 112);
  const hi = s.focus ? focusWord(s.focus.thing, [{ key: "story", text: s.story }, { key: "after", text: s.after }])?.word : undefined;
  narr(F, s.story, P.story[0] + 0.1, P.story[1], sub(Math.max(T, P.story[0] + 0.5)), hi);
  if (s.recap) recapCard(F, s, [P.story[0], Math.min(P.story[0] + (lm ? RECAP_S : 3.6), P.story[1])]);
  if (s.voices?.shout) shoutCard(F, s, [P.story[0] + 0.5, Math.min(P.story[0] + 4.2, P.story[1])]);
  narr(F, s.after, P.after[0] + 0.1, P.after[1], sub(T), hi);

  if (s.check && P.check) checkBeat(F, s, P, sx(hp[0]), sy(hp[1]));
  if (fail && T > land && T < land + 0.8) {
    c.fillStyle = `rgba(200,0,0,${0.35 * (1 - seg(T, land, land + 0.8))})`;
    c.fillRect(-20, -20, W + 40, H + 40);
  }

  cta(F, s, P, pins && { pins: pins.map((q) => ({ ...q, x: sx(q.x), y: sy(q.y) })), hero: [sx(hp[0]), sy(hp[1])], z, open: S.defs.scenes[s.scene.type]?.out === "open" });
  if (T < HE + 0.1) hook(F, s, hero, foe, HE);
  c.restore();
  c.fillStyle = "rgba(128,128,128,.4)";
  c.fillRect(0, H - 4, W, 4);
  c.fillStyle = GOLD;
  c.fillRect(0, H - 4, (W * T) / P.dur, 4);
}

// The opening: complete in its first frame (the one that decides whether people stay), and it puts
// today's choice up front, as the call to action only comes at the end and most viewers leave sooner.
function hook(F: Frame, s: StorySpec, hero: Creature, foe: Creature | undefined, HE: number) {
  const { c, T } = F;
  const a = T < HE - 0.4 ? 1 : (HE + 0.1 - T) / 0.5;
  c.fillStyle = `rgba(14,9,18,${0.72 * a})`;
  c.fillRect(-20, -20, W + 40, H + 40);
  const hv = c.createRadialGradient(170, 220, 20, 170, 220, 240);
  hv.addColorStop(0, `rgba(255,170,80,${0.24 * a})`);
  hv.addColorStop(1, "rgba(255,170,80,0)");
  c.fillStyle = hv;
  c.fillRect(0, 0, W, H);
  c.globalAlpha = a;
  dtxt(F, `EPISODE ${s.ep} · YOU DECIDE THE STORY`, W / 2 - 10, 96, 12, GOLD);
  standee(F, foe || hero, 170, 226, 2.5, 1, T, 0, foe ? RED : GOLD);
  big(F, s.hook[0].toUpperCase(), 170, 312, 40, CREAM, -1, -0.5);  // already settled at frame 0
  big(F, s.hook[1].toUpperCase(), 170, 360, 44, GOLD, -1, -0.5);
  if (!s.dead && s.choices.length) {
    dtxt(F, "TODAY YOU DECIDE", 170, 394, 11, GOLD);
    fit(F, s.ask, 170, 416, 18, W - 100, CREAM, "center", 700);
    s.choices.forEach((o, i) => {
      const y = 442 + i * 25;
      c.fillStyle = "rgba(20,12,16,.78)";
      c.beginPath();
      c.roundRect(30, y - 11, W - 100, 22, 5);
      c.fill();
      seal(F, 44, y, 9, "ABC"[i]);
      fit(F, o.label, 60, y + 5, 13, W - 140, CREAM, "left", 600);
    });
    const crew = (s.party || []).length;
    fit(F, `+ SHOUT A WORD  ·  JOIN THE PARTY${crew ? ` (${crew})` : ""}`, 170, 442 + s.choices.length * 25 + 4, 10, W - 100, GOLD, "center", 700);
  }
  c.globalAlpha = 1;
}

/** During the story: a small reminder that viewers pick what happens next. */
function voteTag(F: Frame, s: StorySpec) {
  if (s.dead || !s.choices.length) return;
  parch(F, 200, ASK_Y, 106, 26);
  fit(F, `YOU PICK NEXT: ${"ABC".slice(0, s.choices.length).split("").join(" · ")}`, 253, ASK_Y + 17, 10, 94, INK, "center", 700);
}

/** "@a, @b, @c and 11 others cried: TORCH": the word the Voices shouted, which today's story uses. */
function shoutCard(F: Frame, s: StorySpec, [a0, a1]: [number, number]) {
  const { c, T } = F;
  const a = fade(T, a0, a1), sh = s.voices!.shout!;
  if (a <= 0) return;
  const names = (s.credits?.shouters || []).map((h) => `@${h}`), others = Math.max(0, sh.n - names.length);
  const who = names.length ? `${names.join(", ")}${others ? ` and ${others} other${others === 1 ? "" : "s"}` : ""}` : `${sh.n} voices`;
  const y = 392;
  c.save();
  c.globalAlpha = a;
  parch(F, 16, y, W - 76, 62);
  fit(F, `${who} cried:`, 158, y + 22, 12, W - 100, INK, "center", 600);
  fit(F, sh.word.toUpperCase(), 158, y + 49, 22, W - 100, RED, "center", 900);
  c.restore();
}

function recapCard(F: Frame, s: StorySpec, [a0, a1]: [number, number]) {
  const { c, T } = F;
  const v = s.recap!.votes, tot = v.reduce((x, y) => x + y, 0), i = s.recap!.pick;
  const a = fade(T, a0, a1);
  if (a <= 0) return;
  const y = 290;
  c.save();
  c.globalAlpha = a;
  parch(F, 16, y, W - 76, 92);
  dtxt(F, tot ? "YESTERDAY'S VOTE" : "NO VOTES YESTERDAY", 158, y + 22, 11);
  txt(F, tot ? `${v[i]} of ${tot} of you chose` : "so we took the default:", 158, y + 45, 15, INK, "center", 600);
  fit(F, `[${"ABC"[i]}] ${s.recap!.label.toUpperCase()}`, 158, y + 70, 15, W - 100, RED);
  c.restore();
}

/** The focus object's live part (the ribbon's tails, the old man's breath), at map scale, and its
 *  label once the camera is in close. */
function focusThing(F: Frame, s: StorySpec, X: number, Y: number, z: number, fz: number) {
  const { c, T } = F, th = THINGS[s.focus!.thing], sc = z * 1.6;
  if (X < -80 || X > W + 80 || Y < -80 || Y > H + 120) return;
  if (th.live) {
    c.save();
    c.translate(X, Y);
    c.scale(sc, sc * 0.9);
    th.live(c, T);
    c.restore();
  }
  const label = s.focus!.label;
  if (label && fz > 0.6) {
    c.save();
    c.globalAlpha = ez((fz - 0.6) / 0.4);
    c.font = font(700, 10);
    const w = Math.min(150, c.measureText(label.toUpperCase()).width + 16);
    const lx = cl(X - w / 2, 18, 305 - w), ly = cl(Y + th.eye[1] * sc * 0.9 - 40, 112, 380);
    parch(F, lx, ly, w, 20);
    fit(F, label.toUpperCase(), lx + w / 2, ly + 14, 10, w - 10, RED, "center", 700);
    c.restore();
  }
}

function checkBeat(F: Frame, s: StorySpec, P: StoryPlan, hx: number, hy: number) {
  const { T } = F;
  const ck = s.check!, r = ck.roll, land = P.throwAt! + THROW, end = s.focus && P.stage ? P.stage[0] : P.after[1];
  const mode = ck.mode === "advantage" ? " · ADV" : ck.mode === "disadvantage" ? " · DIS" : "";
  if (T > P.check![0] + 0.1 && T < land + 0.2) {
    parch(F, 30, 200, W - 86, 40);
    const rallied = ck.rally ? ` · +${ck.rally} RALLY` : "";
    fit(F, `${skillName(ck.skill).toUpperCase()} · DC ${ck.dc} · ${pct(r.p)}${mode}${rallied}`, 152, 226, 17, W - 130, RED, "center", 900);
  }
  const by = s.credits?.rolledBy, voters = s.voices?.voters || 0;
  if ((by || ck.rally) && T > P.check![0] + 0.3 && T < end) {
    const bits = [ck.rally ? `${voters} VOICES` : "", by ? `ROLLED BY @${by}` : ""].filter(Boolean);
    parch(F, 50, 244, W - 126, 22);
    fit(F, bits.join(" · "), 152, 259, 10, W - 140, INK, "center", 700);
  }
  if (T > land + 0.2 && T < end) {
    parch(F, 30, 200, W - 86, 40, r.ok ? "#d3e2bf" : "#e9c0b2");
    const label = r.natural === 20 ? "NATURAL 20!" : r.natural === 1 ? "NATURAL 1" : `${r.kept} ${signed(r.mod)} = ${r.total}`;
    fit(F, `${label} · ${r.ok ? "SUCCESS" : "FAIL"}`, 152, 228, 20, W - 110, r.ok ? GRN : RED, "center", 900);
  }
  throwDie(F, { t0: P.throwAt!, face: r.kept, ok: r.ok, until: P.after[0] + 1.5 });
  if (r.ok && T > land + 0.5 && T < P.after[0] + 1.5) star(F, hx, hy - 78, 16, ez(seg(T, land + 0.5, land + 1)) * (1 + 0.08 * Math.sin(T * 12)));
}

type Pin = { x: number; y: number; kind: "focus" | "exit" };
/** Where the pins sit on screen: the middle of the space between the question and the bottom bar. */
const PIN_BOX: [number, number] = [160, 290];

/** Each choice's place on the map (map units): the focus object if the choice names it, else the
 *  map's exits, left to right. Null when the map hasn't enough exits (the cards are used instead). */
function pinSpots(s: StorySpec, S: SceneStory, lm: number[] | null): Pin[] | null {
  const ex = [...(S.map.exits || [])].sort((a, b) => a[0] - b[0]), out: Pin[] = [];
  const thing = s.focus && THINGS[s.focus.thing];
  for (const ch of s.choices) {
    if (lm && thing && !out.some((o) => o.kind === "focus") && focusWord(s.focus!.thing, [{ key: "l", text: ch.label }])) {
      out.push({ x: lm[0], y: lm[1] - 8, kind: "focus" });
      continue;
    }
    const e = ex.shift();
    if (!e) return null;
    out.push({ x: e[0], y: e[1], kind: "exit" });
  }
  return out;
}

/** An opening in the wall (or a signpost outdoors) where a choice leads. */
function exitMark(F: Frame, x: number, y: number, z: number, open: boolean, a: number) {
  const { c } = F, k = cl(z * 0.9, 0.9, 2);
  c.save();
  c.globalAlpha = a;
  c.translate(x, y);
  c.scale(k, k);
  c.lineWidth = 1.4;
  c.strokeStyle = INK;
  if (open) {
    c.fillStyle = "#7a5a32";
    c.fillRect(-1.2, -16, 2.4, 16);
    c.beginPath();
    c.moveTo(-9, -15);
    c.lineTo(8, -15);
    c.lineTo(11, -12);
    c.lineTo(8, -9);
    c.lineTo(-9, -9);
    c.closePath();
    c.fillStyle = "#b08a58";
    c.fill();
    c.stroke();
  } else {
    c.beginPath();
    c.moveTo(-7, 2);
    c.lineTo(-7, -8);
    c.arc(0, -8, 7, Math.PI, 0);
    c.lineTo(7, 2);
    c.closePath();
    c.fillStyle = "#16121a";
    c.fill();
    c.stroke();
  }
  c.restore();
}

function cta(F: Frame, s: StorySpec, P: StoryPlan, map?: { pins: Pin[]; hero: number[]; z: number; open: boolean } | null) {
  const { c, T } = F;
  const t = T - P.cta;
  if (t <= 0) return;
  const q = ez(seg(t, 0.3, 0.8)), pu = 1 + 0.04 * Math.sin(T * 6);
  if (map) pinned(F, s, t, map);
  c.save();
  c.translate(W / 2 - 10, ASK_Y + 28);
  c.scale(q * pu, q * pu);
  ribbon(F, 0, 0, 226, 44, s.dead ? "YOUR HERO HAS FALLEN" : s.ask.toUpperCase());
  c.restore();
  if (map) return;
  if (s.dead) {
    if (t > 1.2) {
      parch(F, 30, CARD_Y, W - 86, 60);
      fit(F, "A new hero will take up the quest.", 152, CARD_Y + 36, 16, W - 110, INK, "center", 700);
    }
    return;
  }
  const [hx, hy] = HERO_CTA, PO = [[-100, -55], [0, -110], [100, -55]];
  s.choices.forEach((_, i) => {
    const a = ez(seg(t, 0.8 + i * 0.2, 1.3 + i * 0.2)), x = cl(hx + PO[i][0], 40, 280), y = cl(hy + PO[i][1], 150, 250) + Math.sin(T * 5 + i) * 2;
    c.save();
    c.globalAlpha = a;
    c.setLineDash([5, 5]);
    c.strokeStyle = "rgba(243,228,194,.85)";
    c.lineWidth = 2;
    c.beginPath();
    c.moveTo(hx, hy - 40);
    c.lineTo(x, y);
    c.stroke();
    c.setLineDash([]);
    seal(F, x, y, 14, "ABC"[i]);
    c.restore();
  });
  if (t > 1.4) {
    c.save();
    c.globalAlpha = ez(seg(t, 1.4, 1.8));
    c.fillStyle = "rgba(20,12,16,.88)";
    c.beginPath();
    c.roundRect(16, CARD_Y - 36, W - 76, 31, 6);
    c.fill();
    fit(F, `COMMENT ${letters(s.choices.length).toUpperCase()} BY 8AM · NEXT EPISODE AT 9AM`, W / 2 - 22, CARD_Y - 22, 11, W - 92, GOLD, "center", 700);
    fit(F, `+ a word to shout · JOIN the party · no votes? ${"ABC"[s.default]}`, W / 2 - 22, CARD_Y - 9, 11, W - 92, CREAM, "center", 500);
    c.restore();
  }
  s.choices.forEach((o, i) => {
    const a = ez(seg(t, 1.6 + i * 0.25, 2.3 + i * 0.25)), x = 16 + (1 - a) * 400, y = CARD_Y + i * CARD_GAP;
    c.save();
    c.globalAlpha = a;
    parch(F, x, y, W - 76, CARD_H, i === s.default ? "#f5e6b8" : undefined);
    seal(F, x + 24, y + CARD_H / 2, 13, "ABC"[i]);
    c.font = font(700, 16);
    fit(F, o.label, x + 46, y + 29, 16, W - 150, INK, "left", 700);
    c.restore();
  });
}

/** The question on the map: a dashed ink path from the hero to each choice's place, a wax seal
 *  there and its label beside it, then how to vote along the bottom. */
function pinned(F: Frame, s: StorySpec, t: number, m: { pins: Pin[]; hero: number[]; z: number; open: boolean }) {
  const { c, T } = F, [hx, hy] = m.hero;
  const at = m.pins.map((p) => ({ ...p, sx: cl(p.x, 34, 290), sy: cl(p.y - 16, 150, 410) }));
  // paths and openings first, then the labels, then the seals on top of everything
  at.forEach((p, i) => {
    const a = ez(seg(t, 0.5 + i * 0.3, 1.1 + i * 0.3));
    if (a <= 0) return;
    if (p.kind === "exit") exitMark(F, p.x, p.y, m.z, m.open, a);
    c.save();
    c.globalAlpha = a;
    c.setLineDash([5, 5]);
    c.lineDashOffset = -T * 14;
    c.strokeStyle = "rgba(155,44,30,.9)";
    c.lineWidth = 2.4;
    c.lineCap = "round";
    const mx = (hx + p.x) / 2 + (p.x < hx ? -20 : 20), my = Math.min(hy, p.y) - 20;
    c.beginPath();
    c.moveTo(hx, hy - 6);
    c.quadraticCurveTo(mx, my, p.x, p.y - 4);
    c.stroke();
    c.restore();
  });
  at.forEach((p, i) => {
    const a = ez(seg(t, 0.8 + i * 0.3, 1.3 + i * 0.3));
    if (a <= 0) return;
    c.save();
    c.globalAlpha = a;
    c.font = font(700, 12);
    const label = s.choices[i].label, w = Math.min(150, c.measureText(label).width + 18);
    // away from the hero, unless there's no room on that side
    let right = Math.abs(p.x - hx) < 20 ? p.sx < 160 : p.x > hx;
    if (right && p.sx + 18 + w > 305) right = false;
    else if (!right && p.sx - 18 - w < 18) right = true;
    let lx = cl(right ? p.sx + 18 : p.sx - 18 - w, 18, 305 - w), ly = cl(p.sy - 11, 140, 404);
    if (lx < hx + 22 && lx + w > hx - 22 && ly < hy + 12 && ly + 22 > hy - 56) {
      // it would sit on the hero: above or below the seal instead
      lx = cl(p.sx - w / 2, 18, 305 - w);
      ly = cl(p.sy < hy - 20 ? p.sy - 42 : p.sy + 20, 140, 404);
    }
    parch(F, lx, ly, w, 22, i === s.default ? "#f5e6b8" : undefined);
    fit(F, label, lx + w / 2, ly + 15, 12, w - 10, INK, "center", 700);
    c.restore();
  });
  at.forEach((p, i) => {
    const a = ez(seg(t, 0.5 + i * 0.3, 1.1 + i * 0.3));
    if (a <= 0) return;
    const pu = 1 + 0.06 * Math.sin(T * 5 + i);
    c.save();
    c.globalAlpha = a;
    c.translate(p.sx, p.sy);
    c.scale(pu * a, pu * a);
    seal(F, 0, 0, 14, "ABC"[i]);
    c.restore();
  });
  if (t > 1.4) {
    c.save();
    c.globalAlpha = ez(seg(t, 1.4, 1.8));
    c.fillStyle = "rgba(20,12,16,.88)";
    c.beginPath();
    c.roundRect(16, 438, W - 76, 31, 6);
    c.fill();
    fit(F, `COMMENT ${letters(s.choices.length).toUpperCase()} BY 8AM · NEXT EPISODE AT 9AM`, W / 2 - 22, 452, 11, W - 92, GOLD, "center", 700);
    fit(F, `+ a word to shout · JOIN the party · no votes? ${"ABC"[s.default]}`, W / 2 - 22, 465, 11, W - 92, CREAM, "center", 500);
    c.restore();
  }
}

// ---------------------------------------------------------------- resolving a node (rules in one place)

export type ArcNode = {
  id: string; day: number;
  scene: StorySpec["scene"]; foe?: string;
  hook: [string, string]; story: string;
  check?: { skill: string; dc: number; mode?: Mode; harm?: boolean; success: string; fail: string } | null;
  after?: string; rest?: boolean;
  ask: string;
  choices: { label: string; recap: string; next: string | null; breaks?: "speak" | "eat" }[];
  default: number;
  tone?: { story?: string };
  focus?: { thing: string; label?: string };
};

/** Turn a node into a renderable spec: the roll (from the server's dice), its outcome, the hearts. */
export function resolveNode(n: ArcNode, ctx: {
  ep: number; hero: { cls: ClassKey; look: number }; hearts: number; dice: number[];
  recap?: { pick: number; votes: number[]; label: string; line: string } | null;
  rally?: number;
}): StorySpec {
  let check: StorySpec["check"] = null, after = n.after || "", hearts = ctx.hearts;
  if (n.rest) hearts = Math.min(3, hearts + 1);
  if (n.check) {
    // the Voices: Rally (turnout) adds to the roll
    const skill = n.check.skill, rally = Math.max(0, ctx.rally || 0);
    const mode = n.check.mode || "normal", mod = modifier(ctx.hero.cls, skill) + rally;
    const d = mode === "normal" ? [ctx.dice[0]] : [ctx.dice[0], ctx.dice[1]];
    const kept = mode === "advantage" ? Math.max(...d) : mode === "disadvantage" ? Math.min(...d) : d[0];
    const natural = kept === 20 ? 20 : kept === 1 ? 1 : undefined;
    const ok = kept === 20 || (kept !== 1 && kept + mod >= n.check.dc);
    check = { skill, dc: n.check.dc, mode, harm: !!n.check.harm, roll: { dice: d, kept, mod, total: kept + mod, ok, p: odds(mod, n.check.dc, mode), natural } };
    if (rally) check.rally = rally;
    after = ok ? n.check.success : n.check.fail;
    if (!ok && n.check.harm) hearts -= 1;
  }
  return {
    kind: "story", ep: ctx.ep, node: n.id, scene: n.scene, hero: ctx.hero, foe: n.foe, hook: n.hook,
    recap: ctx.recap || null, story: n.story, check, after, hearts: { before: ctx.hearts, after: Math.max(0, hearts) },
    dead: hearts <= 0, ask: n.ask, choices: n.choices.map((c) => ({ label: c.label })), default: n.default,
    tone: n.tone,
    ...(n.focus ? { focus: n.focus } : {}),
  };
}
export { CLASSES };
