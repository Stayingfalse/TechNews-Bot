# Season 1: Childe Rowland

The weekly routine writes from this file. It is served as `season_bible` by `GET /adventure/state`.
It is our own retelling of a public-domain tale ("Childe Rowland", Joseph Jacobs, *English Fairy
Tales*, 1890). Rules and monsters come from the SRD 5.2.1 (CC BY 4.0). Don't copy text from
anywhere: write everything fresh.

## The premise (what viewers already know from Episode 0)

- The hero's little sister **Ellen** ran round the old church *widdershins* (against the sun) on a
  dare, and vanished.
- Under the church is a sealed crypt. It is the only way after her. Episode 0 ended at its gate:
  force it, pick the lock, or search for another way.
- The viewers made the hero in Episode 0: a **fighter**, **rogue** or **wizard** (`state.hero`).
  They also chose the foe they fear most (`state.fear`: skeleton, goblin or wraith). That foe is
  the season's recurring menace, the King's servant who keeps turning up.
- The hero has 3 hearts. A failed check marked `harm` costs one. At 0 the hero dies, for good.

## Where it is going

Ellen was taken by the **King of Elfland**. He keeps her in the Dark Tower, inside a green hill
ringed with terraces, in a hall lit by a great lamp with no flame. Her two older brothers went
after her long ago and never came back; they're in the Tower too, enchanted, as still as statues.

**The two rules.** Anyone who goes into Elfland must speak to no one who speaks to them there,
and eat or drink nothing, however hungry, until they're out again. Break either and you start to
belong to Elfland. These rules are the heart of the season:

- The rules are first given in **week 1**, carved over the crypt's inner door or spoken by a dying
  candle-keeper (put it in the first arc's day-0 or day-1 text). After that every viewer knows
  them, so tempting choices are a real test, not a trick.
- Merlin (week 2) explains *why* they matter, and what breaking them costs.
- Every arc should offer **one or two** choices that break a rule (`"breaks": "speak"` or
  `"breaks": "eat"`). Make them tempting: the food is warm, the voice knows your name, the stranger
  is crying, the water is clear and you're so thirsty. Never make the rule-breaking choice the
  default.
- Broken rules are remembered (`state.rules_broken`). Later arcs should notice: the voices know the
  hero now, a shadow follows. In the finale each broken rule gives **disadvantage** on one of the
  final checks.

## The weeks

Arcs end on Tuesdays. The first arc is short (Saturday to Tuesday); after that each arc runs
Wednesday to Tuesday (7 days). Use the scene named here for most nodes, and vary `seed` per node
so every day has a fresh map.

| Week | Days | Site | Scene | What happens |
|---|---|---|---|---|
| 1 | Sat 31 Oct to Tue 3 Nov | **The crypt** under the church | `dungeon` (`cave` for flooded parts) | Get through the gate and down. The bone stair or the weeping cave, then a red ribbon of Ellen's. Then the two rules are seen, and a voice that knows the hero's name tests them. It ends at a door that opens onto a path that shouldn't be under a church. |
| 2 | Wed 4 to Tue 10 Nov | **Merlin's cave** | `cave` | The path leads to a seer's cave. Reach Merlin through his tests (riddles, a guardian, a flooded passage). He explains the rules and why the brothers failed, and gives one gift: a sword or wand that cuts enchantment, used once in the finale. |
| 3 | Wed 11 to Tue 17 Nov | **The fey wood** | `forest` | The horse-herd and the cow-herd both speak to the hero; both know the road. Asking them for the road without answering their questions is the puzzle. Goblins and will-o'-wisps. |
| 4 | Wed 18 to Tue 24 Nov | **The hen-wife and the green hill** | `mountain` | A kindly old woman offers food, warmth and the way. The climb up the terraced hill. Walk round it widdershins three times: "Open, door!" |
| 5 | Wed 25 Nov to Tue 1 Dec | **Inside the hill** | `dungeon` | The halls of Elfland, golden and wrong. The feast the hero must not touch. The brothers, standing still as statues. |
| 6 | Wed 2 to Tue 8 Dec | **The Dark Tower** | `dungeon` | The King of Elfland. Free Ellen and the brothers, or fall trying. Broken rules come due. |

If the hero dies, the story pauses until a new hero's Episode 0 runs. The new hero picks up the
quest where the last one fell (their sibling, their oath).

## The cast

- **Ellen**: brave, reckless, eleven. Seen in glimpses: a ribbon, a reflection, a laugh down a
  corridor. Never speaks to the hero until the end (she knows the rules too).
- **The King of Elfland**: never seen until week 6, only felt. Polite, ancient, pleased with
  himself. His servants say "the King would like you to stay".
- **Merlin**: old, dry, tired of heroes who don't listen.
- **The foe the viewers chose** (`state.fear`): the King's servant. Use it once or twice an arc,
  never every day.
- Other foes: `skeleton` (the crypt's dead), `goblin` (Elfland's scavengers), `wraith` (voices of
  the lost), `slime` (deep wet places).

## Tone

Teen and up: a dark fairy tale. Scary, eerie and sometimes sad, with real danger and real loss.
- No gore described, no torture, nothing sexual, no swearing.
- No real religions or real-world groups as villains. The church is just an old building.
- Write for the ear: short sentences, concrete things (cold iron, wet stone, a ribbon), one strong
  image per line. Second person, present tense ("You kneel at the lock.").
- Every day ends on a question the viewer wants to answer.

## Dice and danger

- Checks use the hero's sheet: `vocab.skills.<skill>.success_pct_by_dc` gives the exact odds for
  this hero at every DC. Keep every check between 25% and 90% (the server refuses others). The
  sweet spot is 45-75%.
- Give the hero's own skills (`vocab.hero.proficient`) chances to shine, but test their weak spots
  too. A wizard forced to climb is a good story.
- `harm: true` on about one check in three, and not two days running. A failure always moves the
  story on: a worse room, a lost item, a foe now awake. Never a dead end.
- A rest node (`"rest": true`, no check, an `after` line) restores a heart. Give one about once a
  week, more if `state.hearts` is low.
- `advantage` when the choice that led here was clever (sneaking with the torch out), and
  `disadvantage` when it was reckless or a rule was broken.
