// Voice-over helpers: the script format sent to ElevenLabs v3 (one clip, segments separated by
// pauses, delivery tags in brackets), number words, and finding where each segment starts in the
// with-timestamps alignment (prototype: segs(), scriptText(), fromAlign()).

export type Seg = { key: string; spoken: string; text: string }; // text = spoken with delivery tags

export const SEP = "\n\n[long pause]\n\n";

const O1 = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"];
const TN = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"];
/** 0-999 in words: 17 → "seventeen", 45 → "forty-five". */
export const words = (n: number): string =>
  n < 20 ? O1[n] : n < 100 ? TN[(n / 10) | 0] + (n % 10 ? "-" + O1[n % 10] : "") : O1[(n / 100) | 0] + " hundred" + (n % 100 ? " " + words(n % 100) : "");
export const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

/** A segment: `tagged` is what the voice reads; `spoken` the same words without tags. */
export function line(key: string, tagged: string): Seg {
  return { key, text: tagged, spoken: tagged.replace(/\[[^\]]*\]\s*/g, "").replace(/\s+/g, " ").trim() };
}

export const scriptText = (segs: Seg[]) => segs.map((s) => s.text).join(SEP);
/** The daily story clip: paragraph breaks only (tags cost credits; the alignment finds the starts). */
export const dailyText = (segs: Seg[]) => segs.map((s) => s.text).join("\n\n");
export const scriptChars = (segs: Seg[]) => scriptText(segs).length;

export type Alignment = { characters: string[]; character_start_times_seconds: number[]; character_end_times_seconds: number[] };
export type Cues = Record<string, number>;

/** Where each segment starts in the clip, from the ElevenLabs alignment. Matches on letters and
 *  digits only, so punctuation, spacing and tag handling differences don't matter. */
export function cuesFromAlignment(al: Alignment, segs: Seg[]): Cues {
  const chars = al.characters.join("");
  // blank out [tags] (in case the alignment includes them), then keep letters/digits with their index
  const blanked = chars.replace(/\[[^\]]*\]/g, (m) => " ".repeat(m.length));
  const keep: number[] = [];
  let flat = "";
  for (let i = 0; i < blanked.length; i++) {
    const ch = blanked[i].toLowerCase();
    if (/[a-z0-9]/.test(ch)) {
      flat += ch;
      keep.push(i);
    }
  }
  const cues: Cues = {};
  let cur = 0;
  for (const s of segs) {
    const key = s.spoken.toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 16);
    const at = flat.indexOf(key, cur);
    if (at < 0) throw new Error(`voice alignment: could not find "${s.spoken.slice(0, 30)}"`);
    cues[s.key] = Math.round(al.character_start_times_seconds[keep[at]] * 100) / 100;
    cur = at + Math.max(1, Math.floor(s.spoken.replace(/[^a-z0-9]/gi, "").length * 0.9));
  }
  const ends = al.character_end_times_seconds;
  cues.end = Math.round(ends[ends.length - 1] * 100) / 100;
  return cues;
}
