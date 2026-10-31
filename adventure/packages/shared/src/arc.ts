// The weekly arc the routine writes, and every check it must pass before the server accepts it.
// One layer of nodes per day; each node's choices lead to nodes of the next day (paths may merge);
// `links` joins the arc to whatever came before (Episode 0's last vote, or the previous arc's last
// day). The server passes the context (dates, what to link from, the hero) to `validateArc`.
import { z } from "zod";
import { BI } from "../../engine/src/defs.ts";
import { type ClassKey, SKILLS, modifier, odds } from "../../engine/src/sheet.ts";
import { dailyText, line } from "../../engine/src/voice.ts";

const words = (max: number) => z.string().trim().min(2).refine((t) => t.split(/\s+/).length <= max, `at most ${max} words`);
const BANNED = /\b(fuck|shit|cunt|bitch|bastard|rape|nazi|gore|disembowel|decapitat|torture)\w*/i;
export const SCENES = Object.keys(BI.scenes) as [string, ...string[]];
export const FOES = Object.keys(BI.creatures).filter((k) => !["fighter", "rogue", "wizard"].includes(k)) as [string, ...string[]];
export const DCS = [5, 8, 10, 12, 13, 15, 18, 20] as const;
export const DAILY_CHARS = 280; // the most a day's narration may cost (voice credits); aim for ~220

const Choice = z.object({
  label: z.string().trim().min(2).max(32),
  recap: words(10),
  next: z.string().nullable(),
  breaks: z.enum(["speak", "eat"]).optional(),
});

export const Node = z.object({
  id: z.string().regex(/^[a-z0-9][a-z0-9-]{2,40}$/, "lowercase letters, digits and dashes"),
  day: z.number().int().min(0),
  scene: z.object({
    type: z.enum(SCENES), seed: z.number().int().min(1).max(99999),
    dir: z.enum(["N", "E", "S", "W"]).optional(), size: z.number().int().min(3).max(8).optional(), name: z.string().max(24).optional(),
  }),
  foe: z.enum(FOES).optional(),
  hook: z.tuple([z.string().trim().min(1).max(14), z.string().trim().min(1).max(14)]),
  story: words(20),
  check: z.object({
    skill: z.enum(Object.keys(SKILLS) as [string, ...string[]]),
    dc: z.number().int().refine((d) => (DCS as readonly number[]).includes(d), `one of ${DCS.join(", ")}`),
    mode: z.enum(["normal", "advantage", "disadvantage"]).optional(),
    harm: z.boolean().optional(),
    success: words(20), fail: words(20),
  }).optional(),
  after: words(20).optional(),
  rest: z.boolean().optional(),
  ask: words(5),
  choices: z.array(Choice).min(2).max(3),
  default: z.number().int().min(0).max(2),
  tone: z.object({ story: z.string().regex(/^\[[a-z ]{2,20}\]$/) }).optional(),
});
export type ArcNode = z.infer<typeof Node>;

export const Arc = z.object({
  id: z.string().regex(/^[a-z0-9-]{3,40}$/),
  title: z.string().max(60),
  start_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  days: z.number().int().min(1).max(8),
  links: z.record(z.string(), z.array(z.string()).min(2).max(3)),
  nodes: z.array(Node).min(1).max(24),
  notes: z.string().max(2000).optional(),
});
export type ArcT = z.infer<typeof Arc>;

export type ArcContext = {
  start_date: string; days: number;
  links_from: { id: string; choices: number }[];
  hero?: { cls: ClassKey; look: number } | null;
  known_ids?: string[]; // ids used by earlier arcs (must not be reused)
};

/** Every problem with one node on its own, as the AI writer's adapted node is checked before it
 *  plays: the same limits as in an arc (schema, words, teen-friendly, odds, narration length).
 *  `recap` is the line actually said before it. */
export function validateNode(raw: unknown, hero: { cls: ClassKey } | null, recap: string): { problems: string[]; node?: ArcNode } {
  const parsed = Node.safeParse(raw);
  if (!parsed.success) return { problems: parsed.error.issues.map((i) => `${i.path.join(".") || "node"}: ${i.message}`) };
  const n = parsed.data, p: string[] = [];
  if (!n.check && !n.after) p.push(`needs "after" (or a check with success/fail)`);
  if (n.check && n.after) p.push(`"after" is only for nodes without a check`);
  const text = [n.hook.join(" "), n.story, n.after, n.check?.success, n.check?.fail, n.ask, ...n.choices.flatMap((c) => [c.label, c.recap])].join(" ");
  if (BANNED.test(text)) p.push("keep it teen-friendly (no swearing or gore)");
  if (n.check && hero) {
    const pr = odds(modifier(hero.cls, n.check.skill), n.check.dc, n.check.mode || "normal");
    if (pr < 0.25 || pr > 0.9) p.push(`${Math.round(pr * 100)}% to succeed; keep checks between 25% and 90%`);
  }
  const longest = n.check ? (n.check.fail.length > n.check.success.length ? n.check.fail : n.check.success) : n.after || "";
  const chars = dailyText([line("hook", "[whispers] " + recap), line("story", "[tense] " + n.story), line("after", "[relieved] " + longest), line("ask", "[urgent] " + n.ask)]).length;
  if (chars > DAILY_CHARS) p.push(`about ${chars} characters of narration; keep it under ${DAILY_CHARS} (shorter story/outcomes)`);
  return { problems: p, node: p.length ? undefined : n };
}

/** Every problem with an arc, as readable lines; empty when it's good to book. */
export function validateArc(raw: unknown, ctx: ArcContext): { problems: string[]; arc?: ArcT } {
  const parsed = Arc.safeParse(raw);
  if (!parsed.success) return { problems: parsed.error.issues.map((i) => `${i.path.join(".") || "arc"}: ${i.message}`) };
  const arc = parsed.data, p: string[] = [];
  const byId = new Map(arc.nodes.map((n) => [n.id, n]));
  if (byId.size !== arc.nodes.length) p.push("node ids must be unique");
  for (const id of ctx.known_ids || []) if (byId.has(id)) p.push(`${id}: id already used by an earlier arc`);
  if (arc.start_date !== ctx.start_date) p.push(`start_date must be ${ctx.start_date}`);
  if (arc.days !== ctx.days) p.push(`days must be ${ctx.days} (${ctx.start_date} to the day before the next routine run)`);

  // links: exactly the expected predecessors, each choice to a day-0 node
  const want = new Map(ctx.links_from.map((l) => [l.id, l.choices]));
  for (const id of want.keys()) if (!arc.links[id]) p.push(`links: missing "${id}" (where the story is coming from)`);
  for (const [id, to] of Object.entries(arc.links)) {
    if (!want.has(id)) { p.push(`links: "${id}" isn't one of ${[...want.keys()].join(", ")}`); continue; }
    if (to.length !== want.get(id)) p.push(`links.${id}: needs ${want.get(id)} targets, one per choice`);
    to.forEach((t) => byId.get(t)?.day !== 0 && p.push(`links.${id}: "${t}" must be a day-0 node`));
  }

  for (let d = 0; d < arc.days; d++) {
    const n = arc.nodes.filter((x) => x.day === d).length;
    if (n < 1 || n > 3) p.push(`day ${d}: needs 1-3 nodes, has ${n}`);
  }
  const reached = new Set(Object.values(arc.links).flat());
  for (const n of arc.nodes) {
    const at = `${n.id}`;
    if (n.day >= arc.days) p.push(`${at}: day ${n.day} is past the arc's ${arc.days} days`);
    if (n.default >= n.choices.length) p.push(`${at}: default ${n.default} has no choice`);
    if (!n.check && !n.after) p.push(`${at}: needs "after" (or a check with success/fail)`);
    if (n.check && n.after) p.push(`${at}: "after" is only for nodes without a check`);
    if (n.rest && n.check) p.push(`${at}: a rest node has no check`);
    const text = [n.hook.join(" "), n.story, n.after, n.check?.success, n.check?.fail, n.ask, ...n.choices.flatMap((c) => [c.label, c.recap])].join(" ");
    if (BANNED.test(text)) p.push(`${at}: keep it teen-friendly (no swearing or gore)`);
    for (const [i, c] of n.choices.entries()) {
      if (n.day === arc.days - 1) {
        if (c.next !== null) p.push(`${at}.choices[${i}]: the last day's choices end the arc: next must be null`);
      } else if (!c.next || byId.get(c.next)?.day !== n.day + 1) p.push(`${at}.choices[${i}]: next must be a node on day ${n.day + 1}`);
      if (c.next) reached.add(c.next);
    }
    if (n.check && ctx.hero) {
      const pr = odds(modifier(ctx.hero.cls, n.check.skill), n.check.dc, n.check.mode || "normal");
      if (pr < 0.25 || pr > 0.9) p.push(`${at}: ${Math.round(pr * 100)}% to succeed for a ${ctx.hero.cls}; keep checks between 25% and 90%`);
    }
    // the day's narration, worst case (the longer outcome)
    const longest = n.check ? (n.check.fail.length > n.check.success.length ? n.check.fail : n.check.success) : n.after || "";
    const recap = "x".repeat(60); // the line for whichever choice led here (up to 10 words)
    const chars = dailyText([line("hook", "[whispers] " + recap), line("story", "[tense] " + n.story), line("after", "[relieved] " + longest), line("ask", "[urgent] " + n.ask)]).length;
    if (chars > DAILY_CHARS) p.push(`${at}: about ${chars} characters of narration; keep it under ${DAILY_CHARS} (shorter story/outcomes)`);
  }
  for (const n of arc.nodes) if (!reached.has(n.id)) p.push(`${n.id}: no choice or link leads here`);
  return { problems: p, arc };
}
