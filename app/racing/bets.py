"""Reading bets out of comments. One comment is one bet: a car and a stake.

Accepted: "4 250", "#4 £250", "250 on 4", "car 4 250", "4 for 250", "blue streak 300", "blue 300",
"all in on 3", "3 all", "1k on 2", and a car alone ("4", "custard!", "go hot pink"), which stakes
DEFAULT_STAKE. A car named on its own only counts in a short comment (or with "bet"/"back"/"on"),
so "hot pink was robbed lol" isn't a bet. Rejected: two cars in one comment, two stakes, a stake
under MIN_STAKE, or anything ambiguous like "5 4".
"""
from __future__ import annotations

import re
import unicodedata

from .sim import CARS

DEFAULT_STAKE = 100
MIN_STAKE = 10
ALL_IN = re.compile(r"\b(all[\s-]*in|all|everything|max)\b")
BET_WORDS = re.compile(r"\b(bet|bets|betting|back|backing|on|stake|put|for|go|come on|c'mon)\b")

# words that name each car: its name, its colour and a few nicknames
NAMES = {
    1: ["red rocket", "rocket", "red"],
    2: ["mean green", "green"],
    3: ["custard", "yellow"],
    4: ["blue streak", "streak", "blue"],
    5: ["hot pink", "pink", "magenta"],
    6: ["cyanara", "cyan", "sayonara"],
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"@[\w.]+|https?://\S+|#optout", " ", text)
    text = re.sub(r"\brace\s*#?\d+\b", " ", text)  # "race 15: 4 250" names the race, not a car
    return " ".join(text.split())


def _amount(tok: str) -> int | None:
    m = re.fullmatch(r"[£$§€]?(\d{1,3}(?:,\d{3})+|\d+)(k)?", tok)
    if not m:
        return None
    n = int(m.group(1).replace(",", ""))
    return n * 1000 if m.group(2) else n


def parse(text: str) -> dict | None:
    """{car, stake} (stake None = DEFAULT_STAKE, "all" = everything left), or None if it isn't a bet."""
    t = _norm(text)
    if not t:
        return None
    all_in = bool(ALL_IN.search(t))
    named: set[int] = set()
    rest = t
    for no, words in NAMES.items():
        for w in words:
            if re.search(rf"\b{w}\b", rest):
                named.add(no)
                rest = re.sub(rf"\b{w}\b", " ", rest)
    # explicit car markers: "#4", "car 4", "no 4", "number 4"
    marked = {int(x) for x in re.findall(r"(?:#|\bcar\s*|\bno\.?\s*|\bnumber\s*)([1-6])\b", rest)}
    rest = re.sub(r"(?:#|\bcar\s*|\bno\.?\s*|\bnumber\s*)[1-6]\b", " ", rest)
    toks = re.findall(r"[£$§€]?\d[\d,]*k?\b", rest)
    nums = [n for n in (_amount(x) for x in toks) if n is not None]
    small = [n for n in nums if 1 <= n <= 6 and not re.search(rf"[£$§€]{n}\b", rest)]
    big = [n for n in nums if n not in small]

    cars = named | marked
    if not cars:
        if len(small) == 1:
            cars = {small[0]}
            small = []
        elif len(small) > 1:
            return None  # "5 4": which is the car?
    elif small:
        big += small  # "#4 5" is a stake of 5 (too small, rejected below)
    if len(cars) != 1:
        return None
    car = cars.pop()
    if len(big) > 1:
        return None
    if big:
        if big[0] < MIN_STAKE:
            return None
        return {"car": car, "stake": big[0]}
    if all_in:
        return {"car": car, "stake": "all"}
    words = re.findall(r"[a-z']+", rest)
    if named and not marked and len(words) > 3 and not BET_WORDS.search(rest):
        return None  # chat that happens to mention a car
    if len(re.findall(r"[a-z']+", t)) > 8:
        return None
    return {"car": car, "stake": None}


def looks_like_bet(text: str) -> bool:
    """Not a valid bet, but probably meant as one (gets a "how to bet" reply): a number next to a
    car word or a bet word, or a lone number."""
    t = _norm(text)
    has_num = bool(re.search(r"\d", t))
    carish = any(re.search(rf"\b{w}\b", t) for ws in NAMES.values() for w in ws) or bool(re.search(r"#\d|\bcar\b", t))
    return has_num and (carish or bool(BET_WORDS.search(t)) or bool(re.fullmatch(r"[£$§€]?[\d,\s]+k?", t)))


def car_name(no: int) -> str:
    return CARS[no - 1]["name"]
