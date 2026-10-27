import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { type StorySpec, dailyText, planStory, resolveNode, scriptStory } from "../packages/engine/src/index.ts";
import { type ArcContext, type ArcNode, Story, validateArc } from "../packages/shared/src/index.ts";
import { assembleStory } from "../packages/renderer/src/assemble.ts";
import { loadFonts, mapFor, prepare } from "../packages/renderer/src/canvas.ts";

const ARC = JSON.parse(readFileSync(new URL("../examples/arc-s1w1.json", import.meta.url), "utf8"));
const CTX: ArcContext = { start_date: "2026-10-31", days: 4, links_from: [{ id: "episode0", choices: 3 }], hero: { cls: "rogue", look: 0 } };
const copy = () => structuredClone(ARC);
const node = (id: string) => ARC.nodes.find((n: ArcNode) => n.id === id) as ArcNode;
const hero = { cls: "rogue" as const, look: 0 };

describe("validateArc", () => {
  it("accepts the example arc", () => expect(validateArc(ARC, CTX).problems).toEqual([]));
  it("checks the dates against the schedule", () => {
    expect(validateArc(ARC, { ...CTX, start_date: "2026-11-01" }).problems).toContain("start_date must be 2026-11-01");
    expect(validateArc(ARC, { ...CTX, days: 7 }).problems.join()).toMatch(/days must be 7/);
  });
  it("needs a link from what came before", () => {
    const p = validateArc(ARC, { ...CTX, links_from: [{ id: "the-whisper", choices: 2 }] }).problems.join("\n");
    expect(p).toMatch(/missing "the-whisper"/);
    expect(p).toMatch(/"episode0" isn't one of/);
  });
  it("follows each day to the next and ends the last day", () => {
    const a = copy();
    a.nodes.find((n: ArcNode) => n.id === "bone-stair").choices[0].next = "the-whisper";
    a.nodes.find((n: ArcNode) => n.id === "the-whisper").choices[0].next = "gate-lock";
    const p = validateArc(a, CTX).problems.join("\n");
    expect(p).toMatch(/bone-stair.choices\[0\]: next must be a node on day 2/);
    expect(p).toMatch(/the-whisper.choices\[0\]: the last day's choices end the arc/);
  });
  it("finds nodes nothing leads to", () => {
    const a = copy();
    a.nodes.push({ ...structuredClone(node("glow-pool")), id: "lost-room" });
    expect(validateArc(a, CTX).problems).toContain("lost-room: no choice or link leads here");
  });
  it("keeps checks fair for the hero", () => {
    const a = copy();
    a.nodes.find((n: ArcNode) => n.id === "gate-force").check.dc = 20;
    expect(validateArc(a, CTX).problems.join()).toMatch(/gate-force: \d+% to succeed for a rogue/);
  });
  it("rejects swearing", () => {
    const a = copy();
    a.nodes[0].story = "The damn bastard gate will not budge at all.";
    expect(validateArc(a, CTX).problems.join()).toMatch(/gate-force: keep it teen-friendly/);
  });
  it("rejects long lines and unknown scenes", () => {
    const a = copy();
    a.nodes[1].scene.type = "moon";
    a.nodes[2].ask = "What do you want to do now then?";
    const p = validateArc(a, CTX).problems.join("\n");
    expect(p).toMatch(/nodes.1.scene.type/);
    expect(p).toMatch(/nodes.2.ask: at most 5 words/);
  });
  it("refuses ids an earlier arc used", () => {
    expect(validateArc(ARC, { ...CTX, known_ids: ["gate-lock"] }).problems).toContain("gate-lock: id already used by an earlier arc");
  });
});

describe("resolveNode", () => {
  const ctx = { ep: 1, hero, hearts: 3, dice: [15, 3] };
  it("adds the modifier and picks the outcome", () => {
    const s = resolveNode(node("gate-force"), ctx);
    expect(s.check!.roll.total).toBe(15 + s.check!.roll.mod);
    expect(s.check!.roll.ok).toBe(true);
    expect(s.after).toBe(node("gate-force").check!.success);
    expect(() => Story.parse(s)).not.toThrow();
  });
  it("natural 1 fails and 20 succeeds whatever the total", () => {
    expect(resolveNode(node("gate-force"), { ...ctx, dice: [1] }).check!.roll).toMatchObject({ ok: false, natural: 1 });
    const hard = { ...node("gate-force"), check: { ...node("gate-force").check!, dc: 20 } };
    expect(resolveNode(hard, { ...ctx, dice: [20] }).check!.roll).toMatchObject({ ok: true, natural: 20 });
  });
  it("advantage keeps the higher die, disadvantage the lower", () => {
    const n = node("gate-force");
    expect(resolveNode({ ...n, check: { ...n.check!, mode: "advantage" } }, ctx).check!.roll.kept).toBe(15);
    expect(resolveNode({ ...n, check: { ...n.check!, mode: "disadvantage" } }, ctx).check!.roll.kept).toBe(3);
  });
  it("a harmful failure costs a heart, and the last heart kills", () => {
    const n = { ...node("gate-force"), check: { ...node("gate-force").check!, harm: true } };
    expect(resolveNode(n, { ...ctx, dice: [2] }).hearts).toEqual({ before: 3, after: 2 });
    const last = resolveNode(n, { ...ctx, hearts: 1, dice: [2] });
    expect(last.dead).toBe(true);
    expect(scriptStory(last).tail).toBe("Rest well, hero.");
  });
  it("a rest heals one heart, up to three", () => {
    const n: ArcNode = { ...node("glow-pool"), check: undefined, after: "You rest by the glow.", rest: true };
    expect(resolveNode(n, { ...ctx, hearts: 2 }).hearts.after).toBe(3);
    expect(resolveNode(n, ctx).hearts.after).toBe(3);
  });
  it("says only the letters there are", () => {
    expect(scriptStory(resolveNode(node("gate-force"), ctx)).tail).toMatch(/^Comment A or B\./);
  });
});

describe("story episode", () => {
  const spec = resolveNode(node("gate-force"), { ep: 1, hero, hearts: 3, dice: [4], recap: { pick: 0, votes: [3, 1, 0], label: "Force the gate", line: "You chose to force the gate." } });

  it("assembles the voice with the check and roll between story and outcome", () => {
    const dir = mkdtempSync(join(tmpdir(), "story-test-"));
    const tone = (name: string, d: number) => {
      const f = join(dir, `${name}.mp3`);
      execFileSync("ffmpeg", ["-loglevel", "error", "-f", "lavfi", "-i", `sine=f=220:d=${d}`, "-ac", "1", f]);
      return f;
    };
    const text = dailyText(scriptStory(spec).daily).replace(/\[[a-z ]+\]\s*/g, "");
    const chars = [...text], per = 10 / chars.length;
    const align = { characters: chars, character_start_times_seconds: chars.map((_, i) => i * per), character_end_times_seconds: chars.map((_, i) => (i + 1) * per) };
    const v = assembleStory(spec, { daily: tone("daily", 10), align, check: tone("check", 2), roll: tone("roll", 2), tail: tone("tail", 3) });
    const c = v.cues as Record<string, number>;
    expect(c.hook).toBe(0);
    expect(c.story).toBeLessThan(c.check);
    expect(c.roll).toBeCloseTo(c.check + 2.35, 1);
    expect(c.after).toBeCloseTo(c.roll + 2.35 + 0.12, 1);
    expect(c.after).toBeLessThan(c.cta);
    expect(c.end).toBeCloseTo(10 + 2 + 2 + 3 + 3 * 0.35, 0);
  });

  it("plans and draws every second inside the safe zone", async () => {
    loadFonts();
    const r = await prepare({ spec, map: await mapFor(spec) });
    const plan = planStory(spec);
    expect(plan.dur).toBeGreaterThan(10);
    expect(plan.dur).toBeLessThanOrEqual(60);
    for (let t = 0; t < plan.dur; t += 1) expect(() => r.draw(t)).not.toThrow();
  });

  it("schema refuses a spec missing its choices", () => {
    const bad: Partial<StorySpec> = { ...spec, choices: [] };
    expect(() => Story.parse(bad)).toThrow();
  });
});
