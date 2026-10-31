// Input schemas. The renderer validates every spec against these before drawing anything.
import { z } from "zod";
import type { Episode0Spec } from "../../engine/src/episode0.ts";
import type { StorySpec } from "../../engine/src/story.ts";

const votes = z.tuple([z.number().int().min(0), z.number().int().min(0), z.number().int().min(0)]);

export const Episode0 = z.object({
  kind: z.literal("episode0"),
  part: z.union([z.literal(1), z.literal(2), z.literal(3), z.literal(4)]),
  seed: z.number().int().positive().default(12),
  recap: z.object({ pick: z.number().int().min(0).max(2), votes }).nullable().default(null),
  fear: z.enum(["skeleton", "goblin", "wraith"]).default("skeleton"),
  hero: z.object({ cls: z.enum(["fighter", "rogue", "wizard"]), look: z.number().int().min(0).max(2) }).optional(),
  demo: z.object({ roll: z.number().int().min(1).max(20), skill: z.string(), dc: z.number().int().min(5).max(30) })
    .default({ roll: 13, skill: "stealth", dc: 12 }),
  cues: z.record(z.string(), z.number().min(0)).optional(),
}).superRefine((s, ctx) => {
  const need = (ok: boolean, message: string) => ok || ctx.addIssue({ code: "custom", message });
  if (s.part >= 3) need(!!s.hero, `part ${s.part} needs "hero"`);
  if (s.part >= 2) need(!!s.recap, `part ${s.part} needs "recap" (the previous part's vote)`);
  if (s.recap) {
    const v = s.recap.votes, top = Math.max(...v);
    need(top === 0 || v[s.recap.pick] === top, "recap.pick must be one of the most-voted options");
    // the recap must agree with what it decided
    if (s.part === 2) need(["skeleton", "goblin", "wraith"][s.recap.pick] === s.fear, "part 2: recap.pick must match fear");
    if (s.part === 3 && s.hero) need(["fighter", "rogue", "wizard"][s.recap.pick] === s.hero.cls, "part 3: recap.pick must match hero.cls");
    if (s.part === 4 && s.hero) need(s.recap.pick === s.hero.look, "part 4: recap.pick must match hero.look");
  }
});

export type Episode0Input = z.input<typeof Episode0>;

export function parseEpisode0(raw: unknown): Episode0Spec {
  return Episode0.parse(raw) as Episode0Spec;
}

// A story episode, as the server resolves it from an arc node (engine/story.ts resolveNode).
const Roll = z.object({ dice: z.array(z.number().int().min(1).max(20)).min(1).max(2), kept: z.number().int(), mod: z.number().int(),
  total: z.number().int(), ok: z.boolean(), p: z.number(), natural: z.union([z.literal(1), z.literal(20)]).optional() });
export const Story = z.object({
  kind: z.literal("story"), ep: z.number().int().min(1), node: z.string(),
  scene: z.object({ type: z.string(), seed: z.number().int(), dir: z.enum(["N", "E", "S", "W"]).optional(), size: z.number().int().optional(),
    style: z.string().optional(), name: z.string().optional() }),
  hero: z.object({ cls: z.enum(["fighter", "rogue", "wizard"]), look: z.number().int().min(0).max(2) }),
  foe: z.string().optional(),
  hook: z.tuple([z.string(), z.string()]),
  recap: z.object({ pick: z.number().int(), votes: z.array(z.number().int()), label: z.string(), line: z.string() }).nullable().optional(),
  story: z.string(),
  check: z.object({ skill: z.string(), dc: z.number().int(), mode: z.enum(["normal", "advantage", "disadvantage"]), harm: z.boolean(), roll: Roll,
    way: z.enum(["bold", "sly", "wise"]).optional(), rally: z.number().int().min(0).max(5).optional() }).nullable().optional(),
  after: z.string(),
  hearts: z.object({ before: z.number().int(), after: z.number().int() }),
  dead: z.boolean().optional(),
  ask: z.string(),
  choices: z.array(z.object({ label: z.string() })).min(1).max(3),
  default: z.number().int(),
  tone: z.object({ story: z.string().optional(), after: z.string().optional() }).optional(),
  cues: z.record(z.string(), z.number().min(0)).optional(),
  party: z.array(z.object({ name: z.string().max(16), cls: z.enum(["fighter", "rogue", "wizard"]), look: z.number().int().min(0).max(2),
    handle: z.string().max(30).nullable().optional() })).max(6).optional(),
  credits: z.object({ rolledBy: z.string().max(30).nullable().optional() }).optional(),
  voices: z.object({ ways: z.array(z.number().int().min(0)).length(3), way: z.enum(["bold", "sly", "wise"]).nullable().optional(),
    voters: z.number().int().min(0) }).optional(),
});

export type AnySpec = Episode0Spec | StorySpec;
export function parseSpec(raw: unknown): AnySpec {
  const kind = (raw as { kind?: string })?.kind;
  return kind === "story" ? (Story.parse(raw) as StorySpec) : parseEpisode0(raw);
}
export * from "./arc.ts";
