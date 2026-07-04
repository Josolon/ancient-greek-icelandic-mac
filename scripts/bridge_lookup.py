"""English -> Icelandic bridge lookup, built from the CLARIN IS-EN glossary
(data/IS-EN_glossary.tsv, CC BY 4.0). Used to gloss-translate LSJ's English
short definitions into Icelandic one phrase/word at a time (word substitution,
not fluent machine translation) -- see README for why this approach was
chosen over LLM translation.

TSV columns (1-indexed per data/IS-EN_glossary.READ.ME):
  1 Icelandic  2 English  3 IS POS  4 EN POS  5 unit-type
  6-11 method counts (embeddings/MT/pivot/parallel/comparable/synthetic)
  12 IS/EN score   13 EN/IS score
"""
import csv
import os
import re
from functools import lru_cache

GLOSSARY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "IS-EN_glossary.tsv")

_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:'[A-Za-z]+)?")

_en_to_is = None  # english phrase (lowercase) -> list of (icelandic, score) sorted desc

# The glossary's top-scored candidate for common closed-class words is often an
# acronym/proper-noun outlier picked up from its source corpora (e.g. "it" ->
# "upplýsingatækni" i.e. the IT acronym, "a" -> "A" the letter grade, "word" ->
# "Word" the Microsoft product). These words are frequent enough in LSJ glosses
# that leaving them to the raw ranking visibly hurts output quality, so they're
# hand-pinned here and checked before the glossary lookup.
_OVERRIDES = {
    "a": "einn", "an": "einn", "the": "hinn", "it": "það", "is": "er",
    "are": "eru", "was": "var", "were": "voru", "be": "vera", "been": "verið",
    "of": "af", "to": "til", "in": "í", "on": "á", "at": "á", "by": "af",
    "with": "með", "or": "eða", "and": "og", "not": "ekki", "no": "nei",
    "one": "einn", "this": "þessi", "that": "sá", "as": "sem", "for": "fyrir",
    "word": "orð", "if": "ef", "than": "en", "also": "einnig", "from": "frá",
}


def _load():
    global _en_to_is
    if _en_to_is is not None:
        return _en_to_is

    merged = {}
    with open(GLOSSARY_PATH, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) < 13:
                continue
            icelandic, english = row[0].strip(), row[1].strip()
            if not icelandic or not english:
                continue
            try:
                score = float(row[12])
            except ValueError:
                score = 0.0
            key = english.lower()
            bucket = merged.setdefault(key, {})
            if icelandic not in bucket or score > bucket[icelandic]:
                bucket[icelandic] = score

    _en_to_is = {
        key: sorted(cands.items(), key=lambda kv: kv[1], reverse=True)
        for key, cands in merged.items()
    }
    return _en_to_is


@lru_cache(maxsize=200_000)
def translate_word(word):
    """Best single Icelandic candidate for one English word, or None."""
    lower = word.lower()
    if lower in _OVERRIDES:
        return _OVERRIDES[lower]
    table = _load()
    hits = table.get(lower)
    return hits[0][0] if hits else None


@lru_cache(maxsize=100_000)
def translate_phrase(phrase):
    """Try a whole phrase first (multiword glossary entries), else
    fall back to word-by-word substitution. Returns (icelandic_text, fully_translated)."""
    table = _load()
    key = phrase.lower().strip()
    hits = table.get(key)
    if hits:
        return hits[0][0], True

    words = _WORD_RE.findall(phrase)
    if not words:
        return phrase, False

    out = []
    all_found = True
    for w in words:
        translated = translate_word(w)
        if translated is None:
            all_found = False
            out.append(w)
        else:
            out.append(translated)
    return " ".join(out), all_found


if __name__ == "__main__":
    for sample in ["not to be injured, inviolable", "ah!", "one, first", "horse", "run away"]:
        for phrase in sample.split(","):
            phrase = phrase.strip()
            print(f"{phrase!r} -> {translate_phrase(phrase)}")
