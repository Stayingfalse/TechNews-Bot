// The prototype's Park-Miller generator, kept exactly (same seeding, same sequence) so a seed gives
// the same map here as in episode_hybrid.html. The engine never uses Math.random.

export type Rnd = () => number;

export function prng(seed: number): Rnd {
  let s = ((seed || 1) * 7919 + 13) % 2147483647 || 7;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}
