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
  check?: { skill: string; dc: number; mode: Mode; harm: boolean; roll: Roll } | null;
  after: string;
  hearts: { before: number; after: number };
  dead?: boolean;
  ask: string;
  choices: { label: string }[];
  default: number;
  tone?: { story?: string; after?: string };
  cues?: Cues;
};

export type StoryPlan = { dur: number; hook: [number, number]; story: [number, number]; check?: [number, number]; after: [number, number]; cta: number; throwAt?: number };

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
    return p;
  }
  let t = 3.4;
  const add = (l: number): [number, number] => [t, (t += l)];
  const story = add(Math.max(4, est(s.story)) + 2), check = s.check ? add(6.5) : undefined, after = add(Math.max(3.5, est(s.after)));
  const p: StoryPlan = { dur: t + 10, hook: [0, 3.4], story, check, after, cta: t };
  if (check) p.throwAt = check[0] + 1.6;
  return p;
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
  return [head, ask, "#dungeoncrawl #ttrpg #chooseyourownadventure #fantasy #tabletopgames",
    `Music: ${MUSIC_CREDITS[storyMusic(s)]} (CC0). Dice sounds: Kenney (CC0). Includes material from the SRD 5.2.1 by Wizards of the Coast LLC (CC BY 4.0).`].join("\n\n");
}

export function commentStory(s: StorySpec): string {
  if (s.dead) return "Rest well, hero. A new hero rises next.";
  return `${s.choices.map((o, i) => `${"ABC"[i]}) ${o.label}`).join(" · ")}\nComment your letter by 8am. No votes? We go with ${"ABC"[s.default]}.`;
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

  // the walk: in during the story, on during the aftermath
  let p = lp(0.05, s.check ? 0.4 : 0.55, ez(seg(T, P.story[0], P.story[1])));
  p = lp(p, 0.8, ez(seg(T, P.after[0], P.after[1])));
  const hp = along(S.map, p), face = hp[2] >= 0 ? 1 : -1;
  const z = lp(1.5, 1.25, ez(seg(T, P.cta - 1.5, P.cta + 0.5))), vw = W / z, vh = H / z;
  const cx = cl(hp[0] + Math.sin(T * 0.8) * 3, vw / 2, 600 - vw / 2), cy = cl(hp[1] + Math.cos(T * 0.6) * 3, vh / 2, 600 - vh / 2);
  const vx = cx - vw / 2, vy = cy - vh / 2, sx = (m: number) => (m - vx) * z, sy = (m: number) => (m - vy) * z;
  c.drawImage(S.map.cv as unknown as CanvasImageSource, vx * S.map.k, vy * S.map.k, vw * S.map.k, vh * S.map.k, 0, 0, W, H);

  const out = ez(seg(T, P.cta - 0.8, P.cta + 0.2));
  const toks: { d: Creature; x: number; y: number; ph: number; a: number; rim: string }[] = [];
  if (out < 1) toks.push({ d: hero, x: hp[0], y: hp[1], ph: 0, a: 1 - out, rim: GOLD });
  if (foe && T > P.story[0]) {
    let gap = 0.14;
    if (s.check) gap = lp(0.14, fail ? 0.045 : 0.1, ez(seg(T, land, land + 0.7)));
    gap = lp(gap, fail ? 0.07 : 0.2, ez(seg(T, P.after[0], P.after[1])));
    const fp = along(S.map, Math.max(0, p - gap)), fa = seg(T, P.story[0], P.story[0] + 1) * (1 - out);
    if (fa > 0) toks.push({ d: foe, x: fp[0], y: fp[1], ph: 1.7, a: fa, rim: RED });
  }
  toks.sort((a, b) => a.y - b.y).forEach((o) => {
    c.globalAlpha = o.a;
    standee(F, o.d, sx(o.x), sy(o.y), z * 0.95, face, T, o.ph, o.rim);
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
  lighting(F, lights, 0.52);
  S.map.flames.forEach((f, i) => {
    const X = sx(f.x), Y = sy(f.y);
    if (X > -20 && X < W + 20 && Y > -20 && Y < H + 20) flame(F, X, Y, f.s * z * 0.95, i * 1.9);
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
  }

  // story, with yesterday's vote on a card first
  narr(F, s.story, P.story[0] + 0.1, P.story[1], 112);
  if (s.recap) recapCard(F, s, [P.story[0], Math.min(P.story[0] + 3.6, P.story[1])]);
  narr(F, s.after, P.after[0] + 0.1, P.after[1], 112);

  if (s.check && P.check) checkBeat(F, s, P, sx(hp[0]), sy(hp[1]));
  if (fail && T > land && T < land + 0.8) {
    c.fillStyle = `rgba(200,0,0,${0.35 * (1 - seg(T, land, land + 0.8))})`;
    c.fillRect(-20, -20, W + 40, H + 40);
  }

  cta(F, s, P);
  if (T < HE + 0.1) hook(F, s, hero, foe, HE);
  c.restore();
  c.fillStyle = "rgba(128,128,128,.4)";
  c.fillRect(0, H - 4, W, 4);
  c.fillStyle = GOLD;
  c.fillRect(0, H - 4, (W * T) / P.dur, 4);
}

function hook(F: Frame, s: StorySpec, hero: Creature, foe: Creature | undefined, HE: number) {
  const { c, T } = F;
  const a = T < HE - 0.4 ? 1 : (HE + 0.1 - T) / 0.5;
  c.fillStyle = `rgba(14,9,18,${0.86 * a})`;
  c.fillRect(-20, -20, W + 40, H + 40);
  const hv = c.createRadialGradient(180, 300, 20, 180, 300, 260);
  hv.addColorStop(0, `rgba(255,170,80,${0.22 * a})`);
  hv.addColorStop(1, "rgba(255,170,80,0)");
  c.fillStyle = hv;
  c.fillRect(0, 0, W, H);
  c.globalAlpha = a;
  standee(F, foe || hero, 170, 300, 3.1, 1, T, 0, foe ? RED : GOLD);
  dtxt(F, `EPISODE ${s.ep} · YOU DECIDE THE STORY`, W / 2 - 10, 96, 12, GOLD);
  big(F, s.hook[0].toUpperCase(), 170, 386, 44, CREAM, 0.1, 0.4);
  big(F, s.hook[1].toUpperCase(), 170, 440, 48, GOLD, 0.5, 0.8);
  c.globalAlpha = 1;
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

function checkBeat(F: Frame, s: StorySpec, P: StoryPlan, hx: number, hy: number) {
  const { T } = F;
  const ck = s.check!, r = ck.roll, land = P.throwAt! + THROW;
  const mode = ck.mode === "advantage" ? " · ADV" : ck.mode === "disadvantage" ? " · DIS" : "";
  if (T > P.check![0] + 0.1 && T < land + 0.2) {
    parch(F, 30, 200, W - 86, 40);
    fit(F, `${skillName(ck.skill).toUpperCase()} · DC ${ck.dc} · ${pct(r.p)}${mode}`, 152, 226, 17, W - 110, RED, "center", 900);
  }
  if (T > land + 0.2 && T < P.after[1]) {
    parch(F, 30, 200, W - 86, 40, r.ok ? "#d3e2bf" : "#e9c0b2");
    const label = r.natural === 20 ? "NATURAL 20!" : r.natural === 1 ? "NATURAL 1" : `${r.kept} ${signed(r.mod)} = ${r.total}`;
    fit(F, `${label} · ${r.ok ? "SUCCESS" : "FAIL"}`, 152, 228, 20, W - 110, r.ok ? GRN : RED, "center", 900);
  }
  throwDie(F, { t0: P.throwAt!, face: r.kept, ok: r.ok, until: P.after[0] + 1.5 });
  if (r.ok && T > land + 0.5 && T < P.after[0] + 1.5) star(F, hx, hy - 78, 16, ez(seg(T, land + 0.5, land + 1)) * (1 + 0.08 * Math.sin(T * 12)));
}

function cta(F: Frame, s: StorySpec, P: StoryPlan) {
  const { c, T } = F;
  const t = T - P.cta;
  if (t <= 0) return;
  const q = ez(seg(t, 0.3, 0.8)), pu = 1 + 0.04 * Math.sin(T * 6);
  c.save();
  c.translate(W / 2 - 10, ASK_Y + 28);
  c.scale(q * pu, q * pu);
  ribbon(F, 0, 0, 226, 44, s.dead ? "YOUR HERO HAS FALLEN" : s.ask.toUpperCase());
  c.restore();
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
    fit(F, `No votes? We go with ${"ABC"[s.default]}.`, W / 2 - 22, CARD_Y - 9, 11, W - 92, CREAM, "center", 500);
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
};

/** Turn a node into a renderable spec: the roll (from the server's dice), its outcome, the hearts. */
export function resolveNode(n: ArcNode, ctx: {
  ep: number; hero: { cls: ClassKey; look: number }; hearts: number; dice: number[];
  recap?: { pick: number; votes: number[]; label: string; line: string } | null;
}): StorySpec {
  let check: StorySpec["check"] = null, after = n.after || "", hearts = ctx.hearts;
  if (n.rest) hearts = Math.min(3, hearts + 1);
  if (n.check) {
    const mode = n.check.mode || "normal", mod = modifier(ctx.hero.cls, n.check.skill);
    const d = mode === "normal" ? [ctx.dice[0]] : [ctx.dice[0], ctx.dice[1]];
    const kept = mode === "advantage" ? Math.max(...d) : mode === "disadvantage" ? Math.min(...d) : d[0];
    const natural = kept === 20 ? 20 : kept === 1 ? 1 : undefined;
    const ok = kept === 20 || (kept !== 1 && kept + mod >= n.check.dc);
    check = { skill: n.check.skill, dc: n.check.dc, mode, harm: !!n.check.harm, roll: { dice: d, kept, mod, total: kept + mod, ok, p: odds(mod, n.check.dc, mode), natural } };
    after = ok ? n.check.success : n.check.fail;
    if (!ok && n.check.harm) hearts -= 1;
  }
  return {
    kind: "story", ep: ctx.ep, node: n.id, scene: n.scene, hero: ctx.hero, foe: n.foe, hook: n.hook,
    recap: ctx.recap || null, story: n.story, check, after, hearts: { before: ctx.hearts, after: Math.max(0, hearts) },
    dead: hearts <= 0, ask: n.ask, choices: n.choices.map((c) => ({ label: c.label })), default: n.default,
    tone: n.tone,
  };
}
export { CLASSES };
