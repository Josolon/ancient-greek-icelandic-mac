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
    English words, and by merging case variants of the same Icelandic word
    ("Stöð"/"stöð") into one pooled-evidence candidate in the first place --
    they aren't two competing translations, they're the same word counted
    twice under different capitalization.
  - "it" -> "upplýsingatækni": acronym expansions. Handled by _OVERRIDES.
  - "shade" -> "hansagardína" (a curtain brand, score 1.0 on 3 hits) beating
    "skuggi" (score 0.14 but 22 hits): a single high score with almost no
    supporting evidence isn't more trustworthy than a lower score with lots
    of it. Fixed by MIN_EVIDENCE, a hard floor applied before ranking, not
    just a soft down-weight.
  - "a tyrant's dwelling" -> "harðstjóri suður bústaður": concatenating
    separately-looked-up words to cover a multi-word phrase produces
    ungrammatical Icelandic even when each word is individually a valid
    translation. Fixed by removing word-by-word reconstruction entirely --
    translate_glossary_phrase() only ever returns a single looked-up word or
    an exact whole-phrase glossary match, never a synthesized combination.

TSV columns (1-indexed per data/IS-EN_glossary.READ.ME):
  1 Icelandic  2 English  3 IS POS  4 EN POS  5 unit-type
  6-11 method hit-counts (embeddings/MT/pivot/parallel/comparable/synthetic)
  12 IS->EN score   13 EN->IS score
"""
import csv
import math
import os
import re
from functools import lru_cache

GLOSSARY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "IS-EN_glossary.tsv")
WIKTIONARY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "wiktionary_en_is.tsv")

# Weights for merging the Wiktionary supplement (data/wiktionary_en_is.tsv,
# built by build_wiktionary_supplement.py) into the candidate table. A
# Wiktionary pair is one human editor's deliberate judgment, which is worth
# more than a handful of corpus-alignment hits but shouldn't steamroll a
# strong corpus consensus: existing candidates get their evidence topped up
# (helping real words outrank artifacts via the evidence sweetener in
# _ranked), and pairs the CLARIN glossary lacks entirely enter as new
# candidates with a modest score -- enough to win when nothing better
# exists, not enough to beat a well-scored corpus candidate.
WIKTIONARY_EVIDENCE = 8
WIKTIONARY_NEW_SCORE = 0.22

WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]+(?:[-'][A-Za-zÀ-ÖØ-öø-ÿ]+)*")

# Hand-pinned translations for closed-class words whose glossary ranking is
# dominated by acronym/proper-noun outliers. Only consulted for words the
# segmenter actually allows through (mostly single-word senses).
_OVERRIDES = {
    "one": "einn", "first": "fyrstur", "word": "orð", "not": "ekki",
    "no": "enginn", "yes": "já", "it": "það", "this": "þessi", "that": "sá",
}

# Curated translations for LSJ's most common gloss phrases where the
# glossary's corpus-derived ranking picks the wrong *register*: the corpus
# is modern Icelandic (news, software, Wikipedia), so "bring up" ranks
# lyfta (hoist a thing) far above ala upp (rear a child), and "bear" ranks
# bjarndýr (the animal) above bera (carry) -- but in a classical lexicon
# these phrases almost always carry the older sense. Keyed by the phrase
# as it appears after leading-article stripping, lowercase. Keep these
# tables small and only for phrases verified to mistranslate; the POS
# filter below handles the ordinary noun/verb collisions.
#
# _ANY entries are multiword phrasal verbs -- unambiguous in any POS
# reading, safe to pin unconditionally. _VERB entries are single words
# that are only traps in their *verb* reading ("bear"/"stay" as nouns
# really are bjarndýr-the-animal / a prop), so they apply only when the
# caller has established verbness (LSJ's "to X" marker or the headword's
# morphology).
_CLASSICAL_OVERRIDES_ANY = {
    "bring up": "ala upp",
    "lift up": "lyfta",
    "stir up": "æsa",
    "cry aloud": "hrópa",
    "look at": "horfa á",
    "take up": "taka upp",
    "set upon": "ráðast á",
    "run away": "flýja",
    "put on": "klæðast",
    "fall upon": "ráðast á",
    "go through": "fara í gegnum",
    "bring forth": "fæða",
    "cut off": "höggva af",
    "drive away": "reka burt",
    "carry off": "ræna",
    "call upon": "ákalla",
    "set free": "frelsa",
    # Single word, technically a noun/verb homograph in general English
    # ("a count" = an earl), but not a genuine trap here: checked against
    # every LSJ headword that glosses as bare "count" (22, all counting/
    # reckoning verbs like ἀριθμέω, λογίζομαι, ψηφίζω) and none needed the
    # nobility sense -- "greifi" was outranking "telja" whenever no POS
    # hint happened to be available (e.g. λέγω, whose morph.db lemma entry
    # is suppletive and carries no attestations under this headword at
    # all, so there's no morphology signal to hint from).
    "count": "telja",
    # "hinsegin" scores highest for "different" (0.220, 8 hits) over
    # well-attested "ólíkur" (0.118, 38 hits) -- a corpus artifact, and in
    # contemporary Icelandic "hinsegin" primarily means "queer/LGBTQ+",
    # not "of another kind"; jarring and confusing as a classics gloss.
    "different": "ólíkur",
}
_CLASSICAL_OVERRIDES_VERB = {
    "bear": "bera",
    "stay": "vera kyrr",
}

_PLURAL_IRREGULAR = {
    "eyes": "eye", "feet": "foot", "teeth": "tooth", "men": "man",
    "women": "woman", "children": "child", "mice": "mouse", "geese": "goose",
    "oxen": "ox", "wolves": "wolf", "lives": "life", "knives": "knife",
    "leaves": "leaf", "halves": "half", "wives": "wife", "loaves": "loaf",
    "calves": "calf", "hooves": "hoof", "thieves": "thief", "sheaves": "sheaf",
}

# (english_lower, icelandic_lower) pairs to drop outright from the
# Wiktionary supplement -- a real dictionary sense, but one so narrow it
# does more harm than good as a default translation in a classical
# lexicon. "rödd" (score 0.22, evidence 8) means "part" only in the
# choral/musical sense ("fjögurra radda kór", a four-part choir), a sense
# that essentially never occurs in an LSJ shortdef -- yet without this
# exclusion it outranks well-attested "hluti" (0.116, 40 hits) for bare
# "part", and leaks (via lemmatization) into "parted"/"parts" too. Caught
# via moira ("a part, portion; fate") glossing as "rödd, skammtur, örlög",
# wrongly including the voice/singing word instead of "hluti".
_WIKTIONARY_EXCLUDE_PAIRS = {
    ("part", "rödd"),
}

_table = None  # english lowercase -> {icelandic_lower: {"score","evidence","en_pos","is_pos","surface","_casing"}}


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
            # Dedup key is case-insensitive: "Stöð" and "stöð" for "channel"
            # are the same word, not two different candidates that happen
            # to compete for the top slot -- pool their evidence instead of
            # letting a capitalized Wikipedia-title row silently outrank the
            # ordinary word it's actually the same as.
            dedup_key = icelandic.lower()
            cand = bucket.get(dedup_key)
            if cand is None:
                bucket[dedup_key] = {
                    "score": score, "evidence": evidence,
                    "en_pos": en_pos, "is_pos": is_pos,
                    "surface": icelandic, "_casing": {icelandic: evidence},
                }
            else:
                # Duplicate rows exist with different POS tagging and/or
                # casing; merge: sum evidence, keep max score, the more
                # informative POS, and recompute which casing to surface.
                cand["score"] = max(cand["score"], score)
                cand["evidence"] += evidence
                cand["_casing"][icelandic] = cand["_casing"].get(icelandic, 0) + evidence
                for key, val in (("en_pos", en_pos), ("is_pos", is_pos)):
                    if cand[key] in ("NULL", "", "Proper noun") and val not in ("NULL", ""):
                        cand[key] = val
                # Prefer whichever casing has more evidence behind it; break
                # ties toward lowercase (capitalization in this glossary is
                # far more often a citation/title artifact than a genuine
                # proper noun).
                cand["surface"] = max(
                    cand["_casing"].items(),
                    key=lambda kv: (kv[1], kv[0].islower()),
                )[0]

    if os.path.exists(WIKTIONARY_PATH):
        with open(WIKTIONARY_PATH, encoding="utf-8") as f:
            for row in csv.reader(f, delimiter="\t"):
                if len(row) != 3:
                    continue
                english, icelandic, en_pos = row
                if (english.lower(), icelandic.lower()) in _WIKTIONARY_EXCLUDE_PAIRS:
                    continue
                bucket = _table.setdefault(english, {})
                cand = bucket.get(icelandic.lower())
                if cand is not None:
                    cand["evidence"] += WIKTIONARY_EVIDENCE
                    if cand["en_pos"] in ("NULL", "", "Proper noun"):
                        cand["en_pos"] = en_pos
                else:
                    bucket[icelandic.lower()] = {
                        "score": WIKTIONARY_NEW_SCORE,
                        "evidence": WIKTIONARY_EVIDENCE,
                        "en_pos": en_pos, "is_pos": "",
                        "surface": icelandic, "_casing": {icelandic: WIKTIONARY_EVIDENCE},
                    }
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


# A candidate needs at least this many independent method-hits to be
# considered at all, regardless of its score. Without this floor, a lone
# corpus-alignment artifact with score 1.0 (e.g. "shade" -> "hansagardína",
# 3 hits) beats a well-attested real translation with a lower score but far
# more evidence ("shade" -> "skuggi", 22 hits, score 0.14) -- damping the
# score alone isn't enough to fix that, evidence has to gate first.
MIN_EVIDENCE = 5


def _ranked(en_word, cands, en_pos_hint=None, min_evidence=MIN_EVIDENCE,
            en_pos_require=None):
    """Rank a candidate dict by adjusted quality, best first. Candidates
    below min_evidence are dropped outright, not just down-weighted.
    Returns (surface_form, candidate_dict) pairs -- `cands` is keyed by the
    case-insensitive dedup key, not the display spelling; the display
    spelling lives in candidate_dict["surface"].

    en_pos_hint is a soft rerank (boost/penalty); en_pos_require is a hard
    filter for when the POS is *certain* (e.g. LSJ's "to X" infinitive
    marker): candidates whose explicit glossary POS conflicts with it are
    dropped entirely, because no score multiplier can rescue "to bear" from
    bjarndýr (the animal, score 0.6) when bera (carry, score 0.09) is the
    right answer -- the corpus evidence is 6x against us and only grammar
    knows better. Candidates with no POS tag survive the filter (half the
    glossary is untagged; dropping those would gut coverage), and the
    filter only engages at all if at least one candidate explicitly
    matches, so a word with only conflicting tags degrades to the soft
    ranking instead of returning nothing."""
    en_lower_word = en_word[0].islower() if en_word else True
    qualified = [
        c for c in cands.values()
        if c["evidence"] >= min_evidence
        # Single ASCII letters are corpus-alignment junk (abbreviations:
        # "north" -> "n"), never real translations. Genuine one-letter
        # Icelandic words (á "river", í) all carry an accent, so the
        # ASCII check keeps them.
        and not (len(c["surface"]) == 1 and c["surface"].isascii())
    ]
    if en_pos_require and any(c["en_pos"] == en_pos_require for c in qualified):
        qualified = [
            c for c in qualified
            if c["en_pos"] == en_pos_require or c["en_pos"] in ("NULL", "")
        ]
    if not qualified:
        return []
    has_lowercase = any(c["surface"][0].islower() for c in qualified)

    def quality(c):
        icelandic = c["surface"]
        # Evidence gently sweetens the score so near-ties break toward the
        # better-attested candidate: "god" scores drottinn 0.257 (22 hits)
        # vs gud 0.254 (48 hits), and only evidence knows gud is the word.
        q = c["score"] * (1 + 0.1 * math.log10(max(c["evidence"], 1)))
        if en_lower_word and icelandic[0].isupper() and has_lowercase:
            q *= 0.15
        if en_lower_word and c["en_pos"] == "Proper noun":
            q *= 0.3
        # Identity pairs (EN "ball" -> IS "ball", a dance) are usually a
        # loanword or corpus artifact wearing a perfect score; a genuine
        # cognate translation still wins when nothing else qualifies,
        # since the penalty only matters relative to competitors.
        if icelandic.lower() == en_word.lower():
            q *= 0.1
        if en_pos_hint:
            if c["en_pos"] == en_pos_hint:
                q *= 1.4
            elif c["en_pos"] not in ("NULL", ""):
                q *= 0.7
        return q

    return [(c["surface"], c) for c in sorted(qualified, key=quality, reverse=True)]


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
def top_candidates(word, en_pos_hint=None, n=2, en_pos_require=None):
    """Up to n Icelandic candidates for one English word, best first.
    Returns a list of (icelandic, is_pos) tuples; empty if nothing trustworthy."""
    lower = word.lower()
    if lower in _OVERRIDES:
        return [(_OVERRIDES[lower], "")]

    cands, _ = _candidates_for(word)
    if not cands:
        return []
    ranked = _ranked(word, cands, en_pos_hint, en_pos_require=en_pos_require)
    out = []
    best_score = None
    for icelandic, c in ranked:
        if best_score is None:
            best_score = c["score"]
            out.append((icelandic, c["is_pos"]))
        elif c["score"] >= 0.18 and c["score"] >= 0.3 * best_score and icelandic.lower() != out[0][0].lower():
            out.append((icelandic, c["is_pos"]))
        if len(out) >= n:
            break
    return out


@lru_cache(maxsize=200_000)
def phrase_match(phrase, en_pos_hint=None, en_pos_require=None):
    """Whole-phrase glossary match only (no word-by-word reconstruction).
    These are real editorial multiword entries (idioms like "run away" ->
    "strjúka"), so they get a lower evidence bar than single-word lookups --
    but still a bar, to keep out one-off corpus-alignment noise."""
    table = _load()
    key = " ".join(phrase.lower().split())
    cands = table.get(key)
    if not cands:
        return None
    ranked = _ranked(phrase, cands, en_pos_hint, min_evidence=2,
                     en_pos_require=en_pos_require)
    if not ranked:
        return None
    return ranked[0][0]


_LEADING_ARTICLE_RE = re.compile(r"^(to|an?|the)\s+", re.IGNORECASE)


@lru_cache(maxsize=200_000)
def translate_glossary_phrase(phrase, en_pos_hint=None):
    """Precision-first translation of one short gloss phrase for a glossary
    (not a sentence). Returns Icelandic text, or None if we don't have
    confident enough evidence -- callers should keep the English original in
    that case rather than force a translation.

    Deliberately narrow: after stripping a leading "to/a/an/the" (LSJ
    infinitive/article glosses), this only succeeds for (a) an exact
    whole-phrase glossary match, or (b) a single remaining word. It does
    NOT reconstruct multi-word phrases by concatenating separately-looked-up
    words -- e.g. "retiring" -> "hörfa" (withdraw) and "part" -> "hluti" are
    each individually defensible, but "hörfa hluti" is not grammatical
    Icelandic and nobody chose that combination on purpose. A polysemous
    Greek word's other multi-word senses just don't get an Icelandic gloss
    for that particular sense -- see README.

    The stripped article isn't just noise, it's grammar: LSJ writes verbs
    as "to bear" and nouns as "a city"/"the word", so the article pins the
    phrase's POS with certainty and becomes a hard candidate filter
    (en_pos_require in _ranked) -- stronger than en_pos_hint, which is a
    statistical guess from the headword's morphology.
    """
    stripped_full = phrase.strip()
    m = _LEADING_ARTICLE_RE.match(stripped_full)
    en_pos_require = None
    if m:
        article = m.group(1).lower()
        en_pos_require = "Verb" if article == "to" else "Noun"
        # An explicit article outranks the statistical hint; drop the hint
        # when they disagree so the boost doesn't fight the filter.
        if en_pos_hint and en_pos_hint != en_pos_require:
            en_pos_hint = None
    elif en_pos_hint:
        # No article marker, but the headword's own morphology gives a POS
        # hint -- promote it from a soft rerank to a hard filter too, same
        # as the article case. A soft 1.4x/0.7x nudge isn't always enough:
        # koinos ("common", an adjective) has an en_pos_hint of "Adjective",
        # but its LSJ sense "general" ranks the noun "hershöfðingi" (a
        # military commander, score 0.439/50 hits) so far above the correct
        # adjective "almennur" (score 0.139/39 hits) that the soft penalty
        # can't close the gap -- 0.439*0.7 still beats 0.139*1.4. _ranked's
        # filter is a safe no-op when nothing matches the required POS (see
        # "profane" below), so this can't zero out a translation that has
        # no same-POS alternative -- it only kicks in when a better-POS
        # candidate actually exists to prefer instead.
        en_pos_require = en_pos_hint
    stripped = _LEADING_ARTICLE_RE.sub("", stripped_full)
    if not stripped:
        return None

    key = " ".join(stripped.lower().split())
    classical = _CLASSICAL_OVERRIDES_ANY.get(key)
    if classical is None and "Verb" in (en_pos_require, en_pos_hint):
        classical = _CLASSICAL_OVERRIDES_VERB.get(key)
    if classical:
        return classical

    tokens = WORD_RE.findall(stripped)
    if len(tokens) == 1:
        # Single remaining word: always go through top_candidates, which
        # applies the full MIN_EVIDENCE bar. phrase_match's lower bar exists
        # for genuine multiword idioms and would let noise back in here
        # (e.g. "shade" matching the same weakly-attested table entry that
        # top_candidates would correctly reject).
        cands = top_candidates(tokens[0], en_pos_hint, n=1,
                               en_pos_require=en_pos_require)
        return cands[0][0] if cands else None

    if len(tokens) > 1:
        return phrase_match(stripped, en_pos_hint,
                            en_pos_require=en_pos_require)

    return None


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
