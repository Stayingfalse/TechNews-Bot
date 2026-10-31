"""The Shout List: words viewers can shout to the hero in a comment ("A sly torch"). Only these
words count, so nothing free-form ever reaches the story, the screen or the AI writer. A word only
counts once MIN_SHOUTERS different people have shouted it (no single comment can be picked out, and
one person can't steer the story). docs/VOICES_STORY_PLAN.md §3.3.
"""
from __future__ import annotations

import re
import unicodedata

MIN_SHOUTERS = 3

WORDS = """
torch lantern candle fire flame spark smoke ash ember light dark shadow moon sun star stars dawn dusk night
rope chain hook net ladder bridge door gate key lock window wall tower stair stairs tunnel cave well pit
river stream pool water rain storm wind thunder lightning ice snow frost mist fog stone rock sand mud
sword shield axe bow arrow dagger spear hammer staff wand helmet armour armor cloak boots gloves ring amulet
crown coin gold silver jewel gem treasure chest box bag map book scroll letter note riddle rune runes
bread apple honey cheese wine water milk soup salt herbs mushroom berries
potion poison antidote bandage medicine
song sing music drum flute bell horn whistle shout whisper silence listen
run hide climb jump swim crawl sneak fight flee wait rest sleep pray dance laugh cry
look search follow push pull break open close burn freeze dig throw catch
wolf bear fox owl raven crow cat dog horse rat bat spider snake toad frog fish eagle hawk dragon
goblin troll ghost skeleton zombie witch wizard knight king queen elf dwarf giant imp ogre wraith
friend family home hope fear courage luck faith trust mercy honour honor truth lie secret promise
feather bone skull mirror mask clock candlestick bucket shovel pickaxe needle thread ribbon flower rose
tree root leaf moss thorn vine seed acorn mushroom garden forest field hill mountain valley
church altar bell crypt grave tomb chapel cross statue painting portrait
left right up down back forward
""".split()
WORDS = sorted(set(WORDS))
_STEM = {}
for w in WORDS:
    _STEM.setdefault(w, w)
    if not w.endswith("s"):
        _STEM.setdefault(w + "s", w)  # "torches" isn't caught, "ropes" is: good enough
_WORD = re.compile(r"[a-z]+")
# letters, ways and party words aren't shouts, even when they're on the list ("back" is, "join" isn't)
NOT_SHOUTS = {"a", "b", "c", "bold", "sly", "wise", "join", "leave"}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"@\w+|https?://\S+", " ", text)


def shout_of(text: str) -> str | None:
    """The first Shout List word in a comment, or None."""
    for w in _WORD.findall(_norm(text)):
        if w in NOT_SHOUTS:
            continue
        if w in _STEM:
            return _STEM[w]
    return None


def counted(shouts: dict[str, list[str]]) -> list[dict]:
    """{word: [shouters in comment order]} → the words with MIN_SHOUTERS or more, most shouted first
    (ties: the word reached first), each {"word", "n", "first": the first 3 shouters}."""
    out = [{"word": w, "n": len(who), "first": who[:3], "order": i} for i, (w, who) in enumerate(shouts.items())
           if len(who) >= MIN_SHOUTERS]
    out.sort(key=lambda r: (-r["n"], r["order"]))
    return [{k: r[k] for k in ("word", "n", "first")} for r in out]
