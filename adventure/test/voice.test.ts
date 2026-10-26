import { describe, expect, it } from "vitest";
import { type Episode0Spec, THROW, cuesFromAlignment, line, plan0, script0, scriptText, sfx0, words } from "../packages/engine/src/index.ts";
import { Episode0 } from "../packages/shared/src/index.ts";

/** An alignment as ElevenLabs returns it: one entry per character, tags included, 60 ms a letter. */
function fakeAlignment(text: string) {
  const characters: string[] = [], st: number[] = [], en: number[] = [];
  let t = 0.1;
  for (const ch of text) {
    characters.push(ch);
    st.push(t);
    t += 0.06;
    en.push(t);
  }
  return { characters, character_start_times_seconds: st, character_end_times_seconds: en };
}

describe("voice", () => {
  it("spells numbers", () => {
    expect([words(12), words(18), words(70), words(45), words(100)]).toEqual(["twelve", "eighteen", "seventy", "forty-five", "one hundred"]);
  });

  it("strips delivery tags from what is spoken", () => {
    expect(line("x", "[whispers] You decide [long pause] the story.").spoken).toBe("You decide the story.");
  });

  it("finds every segment in the alignment, in order", () => {
    const spec = Episode0.parse({ kind: "episode0", part: 1 }) as Episode0Spec;
    const segs = script0(spec), text = scriptText(segs);
    const cues = cuesFromAlignment(fakeAlignment(text), segs);
    const keys = segs.map((s) => s.key);
    expect(Object.keys(cues)).toEqual([...keys, "end"]);
    for (let i = 1; i < keys.length; i++) expect(cues[keys[i]]).toBeGreaterThan(cues[keys[i - 1]]);
    // the hook's first word starts after its tag
    expect(cues.hook).toBeCloseTo(0.1 + "[whispers] ".length * 0.06, 2);
  });

  it("times the video from the voice and lands the die before the roll is read", () => {
    const spec = Episode0.parse({ kind: "episode0", part: 1 }) as Episode0Spec;
    const segs = script0(spec);
    spec.cues = cuesFromAlignment(fakeAlignment(scriptText(segs)), segs);
    const P = plan0(spec);
    expect(P.beats[0][0]).toBeCloseTo(spec.cues.b0 - 0.25);
    expect(P.cta).toBeCloseTo(spec.cues.cta - 0.25);
    expect(P.dur).toBeGreaterThanOrEqual(spec.cues.end + 2);
    expect(P.throwAt! + THROW).toBeLessThan(spec.cues.roll);
    const sfx = sfx0(spec, P);
    expect(sfx.length).toBe(5);
    expect(sfx[sfx.length - 1].t).toBeCloseTo(P.throwAt! + THROW);
  });

  it("speaks the recap without numbers, and admits when nobody voted", () => {
    const voted = Episode0.parse({ kind: "episode0", part: 2, fear: "wraith", recap: { pick: 2, votes: [3, 2, 7] } }) as Episode0Spec;
    const none = Episode0.parse({ kind: "episode0", part: 2, fear: "skeleton", recap: { pick: 0, votes: [0, 0, 0] } }) as Episode0Spec;
    expect(script0(voted)[1].spoken).toBe("Most of you fear wraiths. Noted.");
    expect(script0(none)[1].spoken).toMatch(/^No votes yet/);
    expect(script0(voted)[1].spoken).not.toMatch(/\d/);
  });

  it("keeps each part's script short (voice credits)", () => {
    const specs = [
      { kind: "episode0", part: 1 },
      { kind: "episode0", part: 2, fear: "wraith", recap: { pick: 2, votes: [3, 2, 7] } },
      { kind: "episode0", part: 3, hero: { cls: "wizard", look: 0 }, recap: { pick: 2, votes: [1, 1, 4] } },
      { kind: "episode0", part: 4, hero: { cls: "fighter", look: 2 }, recap: { pick: 2, votes: [0, 0, 0] } },
    ].map((s) => Episode0.parse(s) as Episode0Spec);
    const chars = specs.map((s) => scriptText(script0(s)).length);
    expect(Math.max(...chars)).toBeLessThan(700);
    expect(chars.reduce((a, b) => a + b, 0)).toBeLessThan(2000);
  });
});
