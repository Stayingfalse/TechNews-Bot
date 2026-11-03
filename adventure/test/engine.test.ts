import { createHash } from "node:crypto";
import { createCanvas } from "@napi-rs/canvas";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  CLASSES, CLASS_ORDER, FACES, H, W, bake, ctaOf, finalRot, merge, modifier, odds, plan0, prng, topFace,
} from "../packages/engine/src/index.ts";
import { Episode0 } from "../packages/shared/src/index.ts";
import { EPISODE0_MAP, loadFonts, makeCanvas, prepare } from "../packages/renderer/src/canvas.ts";
import type { Episode0Spec } from "../packages/engine/src/index.ts";
import { type TextBox, outside, recordText } from "./safe-zone.ts";

const pixels = (cv: unknown) => {
  const c = cv as ReturnType<typeof createCanvas>;
  return createHash("sha256").update(c.getContext("2d").getImageData(0, 0, c.width, c.height).data).digest("hex");
};

describe("prng", () => {
  it("is the prototype's Park-Miller sequence", () => {
    // episode_hybrid.html: s=((seed*7919+13)%2147483647)||7; rnd=()=>(s=(s*16807)%2147483647)/2147483647
    let s = (12 * 7919 + 13) % 2147483647;
    const ref = Array.from({ length: 5 }, () => (s = (s * 16807) % 2147483647) / 2147483647);
    const r = prng(12);
    expect(Array.from({ length: 5 }, r)).toEqual(ref);
  });
});

describe("map", () => {
  loadFonts();
  it("same request, same pixels", () => {
    const a = bake({ ...EPISODE0_MAP, seed: 7 }, merge(), makeCanvas, 1);
    const b = bake({ ...EPISODE0_MAP, seed: 7 }, merge(), makeCanvas, 1);
    expect(pixels(a.cv)).toBe(pixels(b.cv));
    expect(a.tp).toEqual(b.tp);
  });
  it("different seeds differ", () => {
    const a = bake({ ...EPISODE0_MAP, seed: 7 }, merge(), makeCanvas, 1);
    const b = bake({ ...EPISODE0_MAP, seed: 8 }, merge(), makeCanvas, 1);
    expect(a.tp).not.toEqual(b.tp);
  });
  it.each(["dungeon", "cave", "forest", "mountain"])("%s bakes in every direction with its path inside the map", (type) => {
    for (const dir of ["N", "E", "S", "W"] as const) {
      const m = bake({ type, seed: 3, dir }, merge(), makeCanvas, 1);
      expect(m.tp.length).toBeGreaterThan(2);
      for (const [x, y] of m.tp) {
        expect(x).toBeGreaterThanOrEqual(0);
        expect(x).toBeLessThanOrEqual(600);
        expect(y).toBeGreaterThanOrEqual(0);
        expect(y).toBeLessThanOrEqual(600);
      }
    }
  });
});

describe("d20", () => {
  it("has the 20 faces once each, opposite faces summing to 21", () => {
    expect([...FACES].sort((a, b) => a - b)).toEqual(Array.from({ length: 20 }, (_, i) => i + 1));
  });
  it.each(Array.from({ length: 20 }, (_, i) => i + 1))("lands showing %i", (n) => {
    expect(topFace(finalRot(n))).toBe(n);
  });
});

describe("odds", () => {
  it("matches counting the faces, with the natural 20/1 house rule", () => {
    expect(odds(0, 11)).toBeCloseTo(0.5);
    expect(odds(5, 12)).toBeCloseTo(0.7); // 7..20 succeed
    expect(odds(10, 5)).toBeCloseTo(0.95); // a 1 still fails
    expect(odds(-5, 30)).toBeCloseTo(0.05); // a 20 still succeeds
    expect(odds(0, 11, "advantage")).toBeCloseTo(0.75);
    expect(odds(0, 11, "disadvantage")).toBeCloseTo(0.25);
  });
  it("agrees with simulated rolls", () => {
    const r = prng(99), mod = 3, dc = 15, n = 200_000;
    let ok = 0;
    for (let i = 0; i < n; i++) {
      const d = 1 + Math.floor(r() * 20);
      if (d === 20 || (d !== 1 && d + mod >= dc)) ok++;
    }
    expect(Math.abs(ok / n - odds(mod, dc))).toBeLessThan(0.005);
  });
  it("gives each class its best skill at +5", () => {
    for (const k of CLASS_ORDER) expect(modifier(k, CLASSES[k].skills[0])).toBe(5);
  });
});

describe("episode 0 spec", () => {
  it("fills defaults for part 1", () => {
    const s = Episode0.parse({ kind: "episode0", part: 1 });
    expect(s.fear).toBe("skeleton");
    expect(s.demo.roll).toBe(13);
  });
  it("rejects a recap that disagrees with what it decided", () => {
    expect(() => Episode0.parse({ kind: "episode0", part: 3, hero: { cls: "wizard", look: 0 }, recap: { pick: 1, votes: [0, 0, 0] } })).toThrow(/hero.cls/);
  });
  it("rejects a recap pick that didn't win", () => {
    expect(() => Episode0.parse({ kind: "episode0", part: 2, fear: "skeleton", recap: { pick: 0, votes: [1, 5, 0] } })).toThrow(/most-voted/);
  });
  it("defaults part 4 to the hero's best odds", () => {
    const s = Episode0.parse({ kind: "episode0", part: 4, hero: { cls: "fighter", look: 0 }, recap: { pick: 0, votes: [0, 0, 0] } }) as Episode0Spec;
    expect(ctaOf(s).dflt).toBe(0); // fighter: force the gate
  });
});

describe("episode 0 frames", () => {
  afterEach(() => vi.restoreAllMocks());
  const specs: Episode0Spec[] = [
    Episode0.parse({ kind: "episode0", part: 1 }) as Episode0Spec,
    Episode0.parse({ kind: "episode0", part: 2, fear: "wraith", recap: { pick: 2, votes: [3, 2, 7] } }) as Episode0Spec,
    Episode0.parse({ kind: "episode0", part: 3, fear: "wraith", hero: { cls: "wizard", look: 0 }, recap: { pick: 2, votes: [1, 1, 4] } }) as Episode0Spec,
    Episode0.parse({ kind: "episode0", part: 4, fear: "goblin", hero: { cls: "fighter", look: 2 }, recap: { pick: 2, votes: [0, 0, 0] } }) as Episode0Spec,
  ];
  const map = (async () => {
    const { bakedMap } = await import("../packages/renderer/src/canvas.ts");
    return bakedMap(12);
  })();

  it.each(specs.map((s) => [s.part, s] as const))("part %i keeps all text in the safe zone", async (_, spec) => {
    const r = await prepare({ spec, map: await map });
    const P = plan0(spec), seen: TextBox[] = [];
    recordText(r.ctx as unknown as CanvasRenderingContext2D, seen);
    const times = [...P.beats.map(([a, b]) => (a + b) / 2), P.cta + 3, P.dur - 0.1];
    for (const t of times) r.draw(t);
    expect(seen.length).toBeGreaterThan(5);
    expect(outside(seen)).toEqual([]);
  });

  it("draws the same frame twice identically and never calls Math.random", async () => {
    vi.spyOn(Math, "random").mockImplementation(() => {
      throw new Error("Math.random in the engine");
    });
    const r = await prepare({ spec: specs[0], map: await map });
    r.draw(21.3);
    const a = pixels(r.canvas);
    r.draw(5);
    r.draw(21.3);
    expect(pixels(r.canvas)).toBe(a);
  });

  it("fits the 60 s limit", () => {
    for (const s of specs) expect(plan0(s).dur).toBeLessThanOrEqual(60);
    expect(W / H).toBeCloseTo(9 / 16);
  });
});
