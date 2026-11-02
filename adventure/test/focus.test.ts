// Story objects: the push-in on the focus object, the side-on stage, and the choices pinned on the map.
import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { type ArcNode, type StorySpec, THINGS, THING_KEYS, bake, focusWord, merge, planStory, resolveNode, wordTime } from "../packages/engine/src/index.ts";
import { type ArcContext, validateArc, validateNode } from "../packages/shared/src/index.ts";
import { loadFonts, makeCanvas, mapFor, prepare } from "../packages/renderer/src/canvas.ts";

const ARC = JSON.parse(readFileSync(new URL("../examples/arc-s1w1.json", import.meta.url), "utf8"));
const CTX: ArcContext = { start_date: "2026-10-31", days: 4, links_from: [{ id: "episode0", choices: 3 }], hero: { cls: "rogue", look: 0 } };
const hero = { cls: "rogue" as const, look: 0 };
const ribbonNode = (): ArcNode => ({ ...structuredClone(ARC.nodes.find((n: ArcNode) => n.id === "ribbon-hall")), focus: { thing: "ribbon", label: "Ellen's ribbon" } });
const spec = (n: ArcNode, scene?: Partial<StorySpec["scene"]>): StorySpec => {
  const s = resolveNode(n, { ep: 3, hero, hearts: 3, dice: [12], recap: { pick: 0, votes: [3, 1], label: "Follow the red thread", line: "You follow the red thread." } });
  return { ...s, scene: { ...s.scene, ...scene }, party: [{ name: "Alder", cls: "wizard", look: 0, handle: "amy" }] };
};

describe("story objects", () => {
  it("each one names words to push in on, and its prop and animation draw", () => {
    const cv = makeCanvas(200, 200), c = cv.getContext("2d") as unknown as CanvasRenderingContext2D;
    for (const k of THING_KEYS) {
      const t = THINGS[k];
      expect(t.words.length, k).toBeGreaterThan(0);
      expect(t.about.length, k).toBeGreaterThan(10);
      expect(() => t.live?.(c, 1.3)).not.toThrow();
    }
  });
  it("pushes in on the preferred word, wherever it's said", () => {
    expect(focusWord("ribbon", [{ key: "story", text: "On a tomb lid lies a red ribbon." }])).toMatchObject({ key: "story", word: "ribbon" });
    expect(focusWord("keeper", [{ key: "story", text: "A candle-keeper lies dying." }])).toMatchObject({ word: "candle-keeper" });
    expect(focusWord("ribbon", [{ key: "story", text: "Dark." }, { key: "after", text: "The tomb is cold." }])).toMatchObject({ key: "after", word: "tomb" });
    expect(focusWord("ribbon", [{ key: "story", text: "Nothing here." }])).toBeNull();
  });
  it("an arc's node may name one, and must then say it", () => {
    const a = structuredClone(ARC);
    a.nodes = a.nodes.map((n: ArcNode) => (n.id === "ribbon-hall" ? ribbonNode() : n));
    expect(validateArc(a, CTX).problems).toEqual([]);
    a.nodes = a.nodes.map((n: ArcNode) => (n.id === "ribbon-hall" ? { ...n, focus: { thing: "skull" } } : n));
    expect(validateArc(a, CTX).problems.join()).toMatch(/focus "skull": say one of "skull"/);
    a.nodes = a.nodes.map((n: ArcNode) => (n.id === "ribbon-hall" ? { ...n, focus: { thing: "teapot" } } : n));
    expect(validateArc(a, CTX).problems.join()).toMatch(/focus/);
    // the AI writer can't drop the word either
    expect(validateNode({ ...ribbonNode(), story: "A cold stone room." , after: "Nothing stirs."}, hero, "x").problems.join()).toMatch(/say one of/);
  });
  it("the spec carries it, and the plan times the push-in and the stage", () => {
    const s = spec(ribbonNode());
    expect(s.focus).toEqual({ thing: "ribbon", label: "Ellen's ribbon" });
    const P = planStory(s);
    expect(P.focus).toBeGreaterThan(P.story[0]);
    expect(P.focus).toBeLessThan(P.cta);
    expect(P.stage![0]).toBeLessThan(P.after[0]);
    expect(P.stage![1]).toBeLessThan(P.cta);
    expect(planStory({ ...s, focus: undefined }).focus).toBeUndefined();
    // with the voice, the push-in follows the word's cue
    expect(planStory({ ...s, cues: { hook: 0, story: 3, after: 9, cta: 14, end: 16, focus: 5.5 } }).focus).toBeCloseTo(5.25, 2);
  });
});

describe("the voice", () => {
  it("finds when a word is said, after a given moment", () => {
    const text = "A ribbon. Then the ribbon again.", chars = [...text];
    const al = { characters: chars, character_start_times_seconds: chars.map((_, i) => i * 0.1), character_end_times_seconds: chars.map((_, i) => i * 0.1 + 0.1) };
    expect(wordTime(al, "ribbon")).toBeCloseTo(0.2, 5);
    expect(wordTime(al, "ribbon", 1)).toBeCloseTo(1.9, 5);
    expect(wordTime(al, "candle-keeper")).toBeNull();
  });
});

describe("maps", () => {
  it.each(["dungeon", "cave", "forest", "mountain"])("%s: the object stands as the landmark, with exits to pin choices on", (type) => {
    const m = bake({ type, seed: 33, landmark: "ribbon" }, merge(), makeCanvas, 1);
    expect(m.lp).toHaveLength(2);
    expect(m.exits!.length).toBeGreaterThanOrEqual(1);
    for (const e of m.exits!) expect(Math.hypot(e[0] - m.lp![0], e[1] - m.lp![1])).toBeGreaterThan(40);
  });
});

// text must stay where the Reels / Shorts overlays leave it clear
const SAFE = { x0: 16, x1: 307, y0: 73, y1: 480 };
function recordText(ctx: CanvasRenderingContext2D, out: { t: string; x0: number; x1: number; y0: number; y1: number }[]) {
  const fill = ctx.fillText.bind(ctx);
  ctx.fillText = (t: string, x: number, y: number) => {
    const m = ctx.measureText(t), tr = ctx.getTransform(), s = 3;
    const left = ctx.textAlign === "center" ? x - m.width / 2 : ctx.textAlign === "right" ? x - m.width : x;
    const pts = [[left, y - m.actualBoundingBoxAscent], [left + m.width, y + m.actualBoundingBoxDescent]].map(([px, py]) => tr.transformPoint({ x: px, y: py }));
    if (ctx.globalAlpha > 0.05 && t.trim()) out.push({ t, x0: Math.min(pts[0].x, pts[1].x) / s, x1: Math.max(pts[0].x, pts[1].x) / s, y0: Math.min(pts[0].y, pts[1].y) / s, y1: Math.max(pts[0].y, pts[1].y) / s });
    fill(t, x, y);
  };
}

describe("frames", () => {
  it.each([["dungeon", 33], ["cave", 7], ["forest", 41], ["mountain", 42]] as const)(
    "%s: push-in, stage and pins draw every half second, text in the safe zone, no Math.random", async (type, seed) => {
      loadFonts();
      const s = spec(ribbonNode(), { type, seed });
      const r = await prepare({ spec: s, map: await mapFor(s) });
      const P = planStory(s), seen: { t: string; x0: number; x1: number; y0: number; y1: number }[] = [];
      recordText(r.ctx as unknown as CanvasRenderingContext2D, seen);
      const rnd = vi.spyOn(Math, "random").mockImplementation(() => {
        throw new Error("Math.random in the engine");
      });
      for (let t = P.hook[1] + 0.2; t < P.dur; t += 0.5) r.draw(t);
      rnd.mockRestore();
      expect(seen.some((b) => b.t.includes("ELLEN'S RIBBON"))).toBe(true); // the label in the close-up
      expect(seen.some((b) => b.t === "Pocket the ribbon")).toBe(true); // the pinned choice
      // (viewers' @handles ride under their minis wherever they walk, so they aren't held to the zone)
      const outside = seen.filter((b) => !b.t.startsWith("@")).filter((b) => b.x0 < SAFE.x0 - 1 || b.x1 > SAFE.x1 + 1 || b.y0 < SAFE.y0 - 1 || b.y1 > SAFE.y1 + 1);
      expect([...new Set(outside.map((b) => `${b.t} [${b.x0.toFixed(0)},${b.y0.toFixed(0)}–${b.x1.toFixed(0)},${b.y1.toFixed(0)}]`))]).toEqual([]);
    }, 120_000);
});
