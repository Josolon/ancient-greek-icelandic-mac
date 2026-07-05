"""English -> Icelandic bridge lookup over the CLARIN IS-EN glossary
(data/IS-EN_glossary.tsv, CC BY 4.0), used to gloss-translate LSJ's English
short definitions into Icelandic.

Precision-first design: this module's job is to return an Icelandic
candidate only when the glossary gives real evidence for it, and None
otherwise -- the caller keeps the English text visible for anything we
decline to translate. That is the opposite of the first version of this
script, which translated everything and produced pidgin.

Junk signatures observed in the glossary and filtered here:
  - "eyes" -> "skjár": an inflected English form whose sole candidate came
    from corpus alignment, while the lemma ("eye" -> "auga") has an order of
    magnitude more evidence. Fixed by lemmatizing and preferring the lemma's
    candidates when the surface form's are weak.
  - "channel" -> "Stöð", "word" -> "Word": proper-noun/product-name rows
    (Wikipedia titles) outranking the real word. Fixed by penalizing
    capitalized candidates and EN-POS "Proper noun" rows for lowercase
    English words.
  - "it" -> "upplýsingatækni": acronym expansions. Handled by _OVERRIDES.

TSV columns (1-indexed per data/IS-EN_glossary.READ.ME):
  1 Icelandic  2 English  3 IS POS  4 EN POS  5 unit-type
  6-11 method hit-counts (embeddings/MT/pivot/parallel/comparable/synthetic)
  12 IS->EN score   13 EN->IS score
"""
import csv
import os
import re
from functools import lru_cache

GLOSSARY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "IS-EN_glossary.tsv")

WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:[-'][A-Za-zÀ-ÖØ-öø-ÿ]+)*")

# Hand-pinned translations for closed-class words whose glossary ranking is
# dominated by acronym/proper-noun outliers. Only consulted for words the
# segmenter actually allows through (mostly single-word senses).
_OVERRIDES = {
    "one": "einn", "first": "fyrstur", "word": "orð", "not": "ekki",
    "no": "enginn", "yes": "já", "it": "það", "this": "þessi", "that": "sá",
}

# Words that block the word-by-word fallback: a piece containing any of
# these (beyond a stripped leading article) needs real syntax to translate,
# so we keep it in English rather than emit pidgin.
FUNCTION_WORDS = frozenset("""
    a an the of to in on at by with without for from as into upon among
    is are was were be been being am do does did have has had
    who whom whose which what that this these those it its he she his her
    they them their one's oneself himself herself itself themselves
    and or nor but if than then so such not no any all each other another
    up down out off over under between before after against through
    can could shall should will would may might must
    's i.e e.g etc esp
""".split())

_PLURAL_IRREGULAR = {
    "eyes": "eye", "feet": "foot", "teeth": "tooth", "men": "man",
    "women": "woman", "children": "child", "mice": "mouse", "geese": "goose",
    "oxen": "ox", "wolves": "wolf", "lives": "life", "knives": "knife",
    "leaves": "leaf", "halves": "half", "wives": "wife", "loaves": "loaf",
    "calves": "calf", "hooves": "hoof", "thieves": "thief", "sheaves": "sheaf",
}

_table = None  # english lowercase -> {icelandic: {"score","evidence","en_pos","is_pos"}}


def _load():
    global _table
    if _table is not None:
        return _table

    _table = {}
    with open(GLOSSARY_PATH, encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="\t"):
            if len(row) < 13:
                continue
            icelandic, english = row[0].strip(), row[1].strip()
            if not icelandic or not english:
                continue
            try:
                score = float(row[12])  # EN -> IS direction
            except ValueError:
                score = 0.0
            try:
                evidence = sum(int(x) for x in row[5:11])
            except ValueError:
                evidence = 0
            is_pos, en_pos = row[2].strip(), row[3].strip()

            bucket = _table.setdefault(english.lower(), {})
            cand = bucket.get(icelandic)
            if cand is None:
                bucket[icelandic] = {
                    "score": score, "evidence": evidence,
                    "en_pos": en_pos, "is_pos": is_pos,
                }
            else:
                # Duplicate (en, is) rows exist with different POS tagging;
                # merge: sum evidence, keep max score and the more informative POS.
                cand["score"] = max(cand["score"], score)
                cand["evidence"] += evidence
                for key, val in (("en_pos", en_pos), ("is_pos", is_pos)):
                    if cand[key] in ("NULL", "", "Proper noun") and val not in ("NULL", ""):
                        cand[key] = val
    return _table


def _lemma_variants(word):
    """Cheap English lemmatizer: yields possible lemma forms, best-guess first."""
    lower = word.lower()
    if lower in _PLURAL_IRREGULAR:
        yield _PLURAL_IRREGULAR[lower]
        return
    if len(lower) > 3 and lower.endswith("ies"):
        yield lower[:-3] + "y"
    elif len(lower) > 4 and lower.endswith(("ches", "shes", "sses", "xes", "zes")):
        yield lower[:-2]
    elif len(lower) > 3 and lower.endswith("s") and not lower.endswith(("ss", "us", "is")):
        yield lower[:-1]
    if len(lower) > 4 and lower.endswith("ied"):
        yield lower[:-3] + "y"
    elif len(lower) > 4 and lower.endswith("ed"):
        yield lower[:-2]
        yield lower[:-1]  # loved -> love
    if len(lower) > 5 and lower.endswith("ing"):
        yield lower[:-3]
        yield lower[:-3] + "e"  # loving -> love


def _ranked(en_word, cands, en_pos_hint=None):
    """Rank a candidate dict by adjusted quality, best first."""
    en_lower_word = en_word[0].islower() if en_word else True
    has_lowercase = any(ic[0].islower() for ic in cands)

    def quality(item):
        icelandic, c = item
        q = c["score"]
        # Evidence damping: score 1.0 on 3 method-hits is far weaker than
        # score 0.35 on 40 hits. Saturates around 12 hits.
        q *= min(1.0, 0.25 + c["evidence"] / 12.0)
        if en_lower_word and icelandic[0].isupper() and has_lowercase:
            q *= 0.15
        if en_lower_word and c["en_pos"] == "Proper noun":
            q *= 0.3
        if icelandic.lower() == en_word.lower():
            q *= 0.2
        if en_pos_hint:
            if c["en_pos"] == en_pos_hint:
                q *= 1.4
            elif c["en_pos"] not in ("NULL", ""):
                q *= 0.7
        return q

    return sorted(cands.items(), key=quality, reverse=True)


def _candidates_for(word):
    """Candidates for a surface form, falling back to its lemma when the
    surface form's evidence is weak (the eyes->skjár fix). Returns (dict, form_used)."""
    table = _load()
    lower = word.lower()
    exact = table.get(lower, {})
    exact_strength = max((c["evidence"] for c in exact.values()), default=0)

    if exact_strength >= 10:
        return exact, lower

    for lemma in _lemma_variants(word):
        lemma_cands = table.get(lemma)
        if not lemma_cands:
            continue
        lemma_strength = max(c["evidence"] for c in lemma_cands.values())
        if lemma_strength >= max(2 * exact_strength, 4):
            return lemma_cands, lemma
    return exact, lower


@lru_cache(maxsize=200_000)
def top_candidates(word, en_pos_hint=None, n=2, min_quality_evidence=2):
    """Up to n Icelandic candidates for one English word, best first.
    Returns a list of (icelandic, is_pos) tuples; empty if nothing trustworthy."""
    lower = word.lower()
    if lower in _OVERRIDES:
        return [(_OVERRIDES[lower], "")]

    cands, _ = _candidates_for(word)
    if not cands:
        return []
    ranked = _ranked(word, cands, en_pos_hint)
    out = []
    best_score = None
    for icelandic, c in ranked:
        if c["evidence"] < min_quality_evidence:
            continue
        if best_score is None:
            best_score = c["score"]
            out.append((icelandic, c["is_pos"]))
        elif c["score"] >= 0.18 and c["score"] >= 0.3 * best_score and icelandic.lower() != out[0][0].lower():
            out.append((icelandic, c["is_pos"]))
        if len(out) >= n:
            break
    return out


@lru_cache(maxsize=200_000)
def phrase_match(phrase, en_pos_hint=None):
    """Whole-phrase glossary match only (no word-by-word). Returns the best
    Icelandic equivalent or None."""
    table = _load()
    key = " ".join(phrase.lower().split())
    cands = table.get(key)
    if not cands:
        return None
    ranked = _ranked(phrase, cands, en_pos_hint)
    icelandic, c = ranked[0]
    if c["evidence"] < 1:
        return None
    return icelandic


_LEADING_ARTICLE_RE = re.compile(r"^(to|an?|the)\s+", re.IGNORECASE)


@lru_cache(maxsize=200_000)
def translate_glossary_phrase(phrase, en_pos_hint=None):
    """Precision-first translation of one short gloss phrase for a glossary
    (not a sentence). Returns Icelandic text, or None if we don't have
    confident enough evidence -- callers should keep the English original in
    that case rather than force a translation.

    Strategy: strip a single leading "to/a/an/the" (LSJ infinitive/article
    glosses), try a whole-phrase glossary match, then allow word-by-word
    substitution ONLY for short phrases (<=3 tokens) built entirely from
    content words (plus "and"/"or") -- phrases needing real function-word
    grammar are refused rather than turned into pidgin.
    """
    stripped = _LEADING_ARTICLE_RE.sub("", phrase.strip())
    if not stripped:
        return None

    direct = phrase_match(stripped, en_pos_hint)
    if direct:
        return direct

    tokens = WORD_RE.findall(stripped)
    if not tokens or len(tokens) > 3:
        return None
    if any(t.lower() in FUNCTION_WORDS and t.lower() not in ("and", "or") for t in tokens):
        return None

    out = []
    for t in tokens:
        low = t.lower()
        if low == "and":
            out.append("og")
            continue
        if low == "or":
            out.append("eða")
            continue
        cands = top_candidates(t, en_pos_hint, n=1)
        if not cands:
            return None
        out.append(cands[0][0])
    return " ".join(out)


if __name__ == "__main__":
    tests = [
        ("eyes", None), ("eye", None), ("channel", None), ("word", None),
        ("horse", None), ("love", "Verb"), ("love", "Noun"), ("war", None),
        ("inviolable", None), ("wren", None), ("brave", None),
    ]
    for w, hint in tests:
        print(f"{w!r} (hint={hint}): {top_candidates(w, hint)}")
    for p in ("run away", "sea-fish", "regard with affection"):
        print(f"phrase {p!r}: {phrase_match(p)}")
