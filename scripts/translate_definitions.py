"""Build the concise Icelandic gloss for every LSJ entry (data/lsj.db) via
the EN->IS bridge (scripts/bridge_lookup.py), writing results into
data/lsj_is.db.

This is a GLOSSARY, not a dictionary: the goal for e.g. paideuo is
"mennta, kenna, ala upp" -- a handful of well-chosen Icelandic words --
not a word-by-word shadow of LSJ's full sense apparatus ("lyfta; refsa,
refsa; leidrétta, aga; kenna; mennta"), which reads as soup: duplicated
words, one mistranslation per sense, and no sense of which meaning is
primary.

So the gloss is built shortdef-first: lsj.db's `shortdefs` table carries a
curated one-line definition per lemma ("bring up, educate, teach"), and
translating THAT -- with the headword's own part of speech from morph.db
as a bridge hint -- produces exactly the concise gloss we want. Only when
the shortdef is missing or yields nothing does the builder fall back to
the full sense list, and then only its FIRST few senses (LSJ orders senses
by primacy), capped, deduplicated, never one entry per sense.

Individual phrases go through translate_glossary_phrase(), which refuses
to guess -- it returns None rather than pidgin when it lacks confident
evidence. Untranslatable phrases are simply omitted; if nothing at all
translates, the entry gets no Icelandic gloss and the dictionary shows the
English shortdef alone.

Before any of that, _is_lsj_apparatus() filters out phrases that were never
real English glosses to begin with: LSJ's short-definition field also
carries cross-references to other headwords, citation sigla, and Latin,
e.g. "πουλύς, πουλύ,
Ion. for πολύς, ... Ep., but not in Ion. Prose." A
naive translator sees "for" and abbreviation tokens and can end up emitting
something like "v" as if it were a real gloss. These get skipped outright.
"""
import json
import re
import sqlite3
import time
from collections import Counter

from bridge_lookup import translate_glossary_phrase
from greek_normalize import accent_key

LSJ_DB_PATH = "data/lsj.db"
MORPH_DB_PATH = "data/morph.db"
OUT_DB_PATH = "data/lsj_is.db"

# Morpheus (data/morph.db) tags every attested form of a headword with its
# own part of speech; the glossary (data/IS-EN_glossary.tsv) tags every
# English word with its own, different, part-of-speech vocabulary. This maps
# the former onto the latter so bridge_lookup's en_pos_hint reranking (a
# soft boost/penalty, not a filter -- see bridge_lookup.py) can prefer
# glossary candidates whose POS matches the Greek headword's actual word
# class. Left out on purpose: 'particle' (too semantically diffuse to map to
# any single English POS) and the ~2% of rows with no pos at all.
GREEK_POS_TO_EN_POS = {
    "noun": "Noun",
    "adjective": "Adjective",  # synthesized from degree-marked 'noun' rows, see _load_pos_by_norm_lemma
    "verb": "Verb",
    "participle": "Adjective",  # participles gloss adjectivally in LSJ
    "adv": "Adverb",
    "prep": "Preposition",
    "conj": "Conjunction",
    "numeral": "Numeral",
}

_SPLIT_RE = re.compile(r"\s*[,;]\s*")

_GREEK_RE = re.compile(r"[Ͱ-Ͽἀ-῿]")
_APPARATUS_RE = re.compile(
    r"\b(cf|sq|v|q\.v|etc|Ion|Ep|Dor|Att|Hom|Hsch|Poet|Trag|Com)\.|"
    r"\bsee\b|\bcf\b|pr\.n\.|[\[\]]",
    re.IGNORECASE,
)
# Author-abbreviation sigla (e.g. "Plu." for Plutarch, "D.H." for Dionysius
# of Halicarnassus) are effectively unbounded across LSJ's citation
# apparatus -- rather than enumerate them, a capitalized 1-4 letter token
# immediately followed by a period is itself a strong citation signature
# that basically never occurs in a real English gloss.
_CITATION_SIGLUM_RE = re.compile(r"\b[A-Z][a-zA-Z]{0,3}\.")


def _is_lsj_apparatus(phrase):
    """True if `phrase` is LSJ editorial apparatus (cross-reference,
    citation, dialect note) rather than an actual English gloss."""
    if _GREEK_RE.search(phrase):
        return True
    if _APPARATUS_RE.search(phrase):
        return True
    if _CITATION_SIGLUM_RE.search(phrase):
        return True
    if any(ch.isdigit() for ch in phrase):
        return True
    letters = re.sub(r"[^A-Za-z]", "", phrase)
    if len(letters) <= 2:
        return True
    return False


_pos_by_norm_lemma = None  # accent_key(lemma).lower() -> Counter({pos: count})


def _load_pos_by_norm_lemma(morph_conn):
    """Precompute POS-vote counts per ACCENT-FOLDED lemma from morph.db, one
    full scan up front rather than a query per headword. This has to be
    accent-folded, not an exact-string lookup: LSJ's raw rows carry many
    pure accent/case duplicates of the same headword (see build_xml.py's
    docstring -- logos/logos/Logos/Logos etc.), and Morpheus independently
    attests forms under only ONE of those spellings. An exact-match lookup
    against morph.db silently returns "no opinion" for every duplicate
    spelling Morpheus didn't happen to pick, which is most of them -- e.g.
    lego (legw) had 8 accent/case variants in lsj.db, and an exact-match
    hint lookup missed the one morph.db actually has data for, wrongly
    leaving 'count' (the verb) to be translated with no POS hint at all
    and losing to 'greifi' ("Count", the noble title).

    Morpheus's pos tag has no separate 'adjective' value -- Greek
    adjectives are tagged 'noun' right alongside real nouns (e.g. koinos
    "common" has 142 pos='noun' rows, same as anthropos "human"). Left
    uncorrected, every adjectival headword gets an en_pos_hint of "Noun",
    which then BOOSTS wrong noun candidates and PENALIZES the correct
    adjective ones -- backwards. But comparison degree
    (comparative/superlative) is structurally impossible for a true noun
    and only ever attested on adjectives/adverbs, so a lemma with ANY
    degree-marked rows is reclassified as an adjective outright: koinos
    has 87 degree-marked rows (comparative/superlative) out of 147 total;
    anthropos has zero."""
    global _pos_by_norm_lemma
    _pos_by_norm_lemma = {}
    has_degree = set()
    rows = morph_conn.execute(
        "SELECT lemma, pos, degree, COUNT(*) FROM morphology "
        "WHERE pos IS NOT NULL AND pos != '' GROUP BY lemma, pos, degree"
    ).fetchall()
    for lemma, pos, degree, count in rows:
        key = accent_key(lemma).lower()
        if degree:
            has_degree.add(key)
        _pos_by_norm_lemma.setdefault(key, Counter())[pos] += count
    for key in has_degree:
        counts = _pos_by_norm_lemma[key]
        if counts.get("noun"):
            counts["adjective"] = counts.pop("noun")


def _headword_pos_hint(lemma):
    """Majority-vote part of speech for `lemma` across its attested forms in
    data/morph.db (accent-folded -- see _load_pos_by_norm_lemma), mapped
    onto the glossary's English-POS vocabulary. None if morph.db has no
    opinion for any spelling variant, or the winning tag isn't in
    GREEK_POS_TO_EN_POS -- callers then fall back to no hint."""
    counts = _pos_by_norm_lemma.get(accent_key(lemma).lower())
    if not counts:
        return None
    return GREEK_POS_TO_EN_POS.get(counts.most_common(1)[0][0])


# A gloss is a handful of words, not a sense inventory. Five is already
# generous; most entries land at 1-3.
GLOSS_MAX_WORDS = 5
# When falling back to the full sense list, only the first few senses are
# considered -- LSJ orders senses by primacy, and sense 7 of a polysemous
# verb is exactly the "dictionary soup" this builder exists to avoid.
FALLBACK_SENSES = 3

# LSJ's shortdef is sometimes just the *first* sense with an article glued
# on ("the word" for a headword with 63 senses spanning "speech", "account",
# "reason", "ratio", "narrative"...) -- a lazy stub, not a real summary. A
# terse shortdef (<=2 phrases) next to a large sense inventory is the
# signature of that: real breadth hiding behind a one-word placeholder.
# When both conditions hold, the fuller sense list is consulted *in
# addition to* the shortdef, not just as a fallback when it fails, and the
# gloss gets more room (one word cannot represent a headword where "word",
# "reason", and "ratio" are all genuinely distinct senses, not synonyms of
# each other).
POLYSEMY_SENSE_THRESHOLD = 8
POLYSEMY_GLOSS_MAX_WORDS = 8


def _add_gloss_words(text, en_pos_hint, seen, out, max_words):
    """Translate each comma/semicolon-separated phrase of `text`, appending
    Icelandic results to `out`, case-insensitively deduplicated via `seen`
    (LSJ loves near-synonym pairs like "chastise, punish" that both land on
    refsa -- one refsa is a gloss, two is noise)."""
    for phrase in _SPLIT_RE.split(text):
        if len(out) >= max_words:
            return
        if not phrase.strip() or _is_lsj_apparatus(phrase):
            continue
        is_text = translate_glossary_phrase(phrase, en_pos_hint)
        if is_text and is_text.lower() not in seen:
            seen.add(is_text.lower())
            out.append(is_text)


# Manually curated gloss overlays for specific headwords, keyed by
# lemma_normalized (so they apply across all accent/case spelling variants
# of the same word) -- supplied by an Icelandic classicist where the
# automatic bridge structurally can't find the intended word. bridge_lookup
# only ever sees English intermediary text, so a word like "tala" -- which
# alone spans "word/speech" AND "number/reckoning", mirroring λόγος's core
# duality, and is cognate with λέγω's "speak"/"count" duality below -- has
# no path to surface from ranking English gloss phrases individually,
# no matter how the ranking is tuned. Prepended (highest priority) to the
# automatic gloss, deduplicated against it, capped at the same word limit.
LEMMA_GLOSS_OVERRIDES = {
    # orð is λόγος's basic sense and must lead; tala (which alone spans
    # "word/speech" AND "number/reckoning") follows as the next most
    # representative, ahead of the automatic senses.
    "λογος": ["orð", "tala"],
    "λεγω": ["tala", "telja"],
}

# Same idea as LEMMA_GLOSS_OVERRIDES, but keyed by the EXACT accented lemma
# (breathing + accent + case), not the accent-folded lemma_normalized. Some
# accent-folds collide across genuinely unrelated words -- "αλλα" folds
# ἀλλά ("but", the adversative conjunction), ἄλλα (neuter plural of ἄλλος,
# "other things"), and the proper noun Ἀλλᾶ all onto one normalized key, so
# an override keyed by lemma_norm would wrongly overwrite all three. Use
# this map whenever the intended word isn't the sole occupant of its fold.
EXACT_LEMMA_GLOSS_OVERRIDES = {
    "ἀλλά": ["en", "heldur"],
    "τοι": ["þér má vera ljóst"],
    "ἀγαθόω": ["gera gott"],
}


def _apply_lemma_overrides(lemma_norm, out, max_words, lemma=None):
    additions = EXACT_LEMMA_GLOSS_OVERRIDES.get(lemma) or LEMMA_GLOSS_OVERRIDES.get(lemma_norm)
    if not additions:
        return out
    # The override words lead, in their given order, even when one of them
    # is also present in the automatic gloss (else a word like "orð", which
    # the shortdef already found, would be deduped out of the prepend and
    # leave "tala" wrongly in front).
    ordered = list(additions)
    seen = {w.lower() for w in ordered}
    for w in out:
        if w.lower() not in seen:
            ordered.append(w)
            seen.add(w.lower())
    return ordered[:max_words]


def build_gloss(lemma_norm, shortdef, senses, en_pos_hint, lemma=None):
    """The concise Icelandic gloss for one entry. Shortdef-first: if the
    curated one-liner yields anything, that IS the gloss's core, and the
    sense list is only additionally consulted when the shortdef looks like
    it's underselling a genuinely polysemous headword (see
    POLYSEMY_SENSE_THRESHOLD). Returns (gloss_text_or_None, source)."""
    seen, out = set(), []
    source = None
    max_words = GLOSS_MAX_WORDS

    shortdef_phrases = [p for p in _SPLIT_RE.split(shortdef) if p.strip()] if shortdef else []
    if shortdef_phrases:
        _add_gloss_words(shortdef, en_pos_hint, seen, out, max_words)
        if out:
            source = "shortdef"

    # Widening into the FULL sense list (beyond the standard 3-sense
    # fallback cap) is only justified when a shortdef existed but was
    # narrow relative to a genuinely large sense inventory -- e.g. λόγος's
    # shortdef is just "the word" (1 phrase) despite 63 senses spanning
    # "reason", "ratio", "narrative"... When there's NO shortdef at all, a
    # large sense count does NOT justify widening: LSJ orders senses by
    # primacy, and senses past the first few are disproportionately rare/
    # technical extensions that translate noisily in isolation (checked:
    # widening a no-shortdef entry like Κοινός, 35 senses, pulled in
    # "hershöfðingi" (a military rank) from an obscure sense far down the
    # list). No-shortdef entries stick to the safer FALLBACK_SENSES cap.
    underselling = len(shortdef_phrases) <= 2 and len(senses) >= POLYSEMY_SENSE_THRESHOLD
    if shortdef_phrases and underselling:
        max_words = POLYSEMY_GLOSS_MAX_WORDS
        before = len(out)
        for sense in senses:
            if len(out) >= max_words:
                break
            _add_gloss_words(sense, en_pos_hint, seen, out, max_words)
        if len(out) > before:
            source = "shortdef+senses"
    elif not out:
        for sense in senses[:FALLBACK_SENSES]:
            _add_gloss_words(sense, en_pos_hint, seen, out, max_words)
        if out:
            source = "senses"

    out = _apply_lemma_overrides(lemma_norm, out, max_words, lemma=lemma)
    if not out:
        return None, None
    return ", ".join(out), (source or "override")


def main():
    lsj = sqlite3.connect(LSJ_DB_PATH)
    morph = sqlite3.connect(MORPH_DB_PATH)
    print("Loading POS votes from morph.db...")
    _load_pos_by_norm_lemma(morph)
    out = sqlite3.connect(OUT_DB_PATH)
    out.execute("DROP TABLE IF EXISTS definitions_is")
    out.execute(
        """CREATE TABLE definitions_is (
            id INTEGER PRIMARY KEY,
            lemma TEXT NOT NULL,
            lemma_normalized TEXT NOT NULL,
            definitions_en TEXT NOT NULL,
            shortdef_en TEXT,
            gloss_is TEXT,
            gloss_source TEXT,
            any_translated INTEGER NOT NULL
        )"""
    )
    out.execute("CREATE INDEX idx_def_is_lemma ON definitions_is(lemma)")

    # Curated one-line definitions, keyed by exact lemma spelling. A
    # normalized-spelling fallback is only trusted when every shortdef row
    # sharing that normalized key agrees -- two lemmas that differ only in
    # accents/breathing can be genuinely different words, and giving one
    # the other's shortdef would be a silent mis-gloss.
    print("Loading shortdefs...")
    sd_by_lemma = {}
    sd_by_norm = {}
    for lemma, norm, sd in lsj.execute("SELECT lemma, lemma_normalized, definition FROM shortdefs"):
        sd_by_lemma[lemma] = sd
        if norm in sd_by_norm and sd_by_norm[norm] != sd:
            sd_by_norm[norm] = None  # conflicting -- unusable
        elif norm not in sd_by_norm:
            sd_by_norm[norm] = sd

    rows = lsj.execute("SELECT id, lemma, lemma_normalized, definitions FROM definitions").fetchall()
    total = len(rows)
    print(f"Building Icelandic glossary for {total} LSJ entries...")

    start = time.time()
    buffer = []
    from_shortdef = 0
    from_senses = 0
    none_count = 0
    for i, (rid, lemma, lemma_norm, defs_json) in enumerate(rows):
        try:
            senses = json.loads(defs_json)
        except (json.JSONDecodeError, TypeError):
            senses = [defs_json]

        shortdef = sd_by_lemma.get(lemma) or sd_by_norm.get(lemma_norm)
        en_pos_hint = _headword_pos_hint(lemma)
        gloss, source = build_gloss(lemma_norm, shortdef, senses, en_pos_hint, lemma=lemma)

        if source in ("shortdef", "shortdef+senses"):
            from_shortdef += 1
        elif source is not None:
            from_senses += 1
        else:
            none_count += 1

        buffer.append((rid, lemma, lemma_norm, defs_json, shortdef, gloss, source, int(gloss is not None)))

        if len(buffer) >= 5000:
            out.executemany("INSERT INTO definitions_is VALUES (?,?,?,?,?,?,?,?)", buffer)
            out.commit()
            buffer.clear()
            elapsed = time.time() - start
            print(f"  ... {i + 1}/{total} ({elapsed:.0f}s elapsed)")

    if buffer:
        out.executemany("INSERT INTO definitions_is VALUES (?,?,?,?,?,?,?,?)", buffer)
        out.commit()

    translated = from_shortdef + from_senses
    print(f"Done in {time.time() - start:.0f}s.")
    print(f"  Gloss from shortdef: {from_shortdef}/{total} ({100*from_shortdef/total:.1f}%)")
    print(f"  Gloss from first senses (no usable shortdef): {from_senses}/{total} ({100*from_senses/total:.1f}%)")
    print(f"  Total with Icelandic gloss: {translated}/{total} ({100*translated/total:.1f}%)")
    print(f"  English only: {none_count}/{total} ({100*none_count/total:.1f}%)")

    lsj.close()
    morph.close()
    out.close()


if __name__ == "__main__":
    main()
