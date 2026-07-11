"""Extract a compact EN->IS supplement glossary from the kaikki.org
Wiktionary dump (data/kaikki-icelandic.jsonl, https://kaikki.org/dictionary/Icelandic/,
CC BY-SA -- see CREDITS.md), writing data/wiktionary_en_is.tsv.

Each Icelandic entry in English Wiktionary carries English glosses
("mennta" -> "to educate"); reversing those pairs gives an EN->IS lexicon
that is *human-curated* -- unlike the CLARIN glossary's corpus-derived
scores, nobody's machine-translation alignment decided these, an editor
did. bridge_lookup.py merges this file into its candidate table as
supplementary evidence: it can rescue words the CLARIN glossary lacks
entirely, and its votes help well-attested-but-low-scored candidates
outrank corpus artifacts.

Precision guardrails, same philosophy as the rest of the pipeline:
  - only concise glosses become pairs (a gloss that is a definitional
    sentence, "The first letter of the Icelandic alphabet...", is not a
    translation equivalent and is dropped);
  - inflected-form and alternative-spelling senses (form-of/alt-of) are
    skipped -- they gloss the lemma, not the form;
  - proper names, characters, affixes are skipped.

Run after downloading the dump:
    curl -o data/kaikki-icelandic.jsonl \
        https://kaikki.org/dictionary/Icelandic/kaikki.org-dictionary-Icelandic.jsonl
    python3 scripts/build_wiktionary_supplement.py
"""
import json
import re

IN_PATH = "data/kaikki-icelandic.jsonl"
OUT_PATH = "data/wiktionary_en_is.tsv"

# kaikki pos -> the CLARIN glossary's EN-POS vocabulary, so bridge_lookup's
# POS hint/filter machinery applies to supplement rows exactly as it does
# to CLARIN rows.
POS_MAP = {
    "noun": "Noun",
    "verb": "Verb",
    "adj": "Adjective",
    "adv": "Adverb",
    "prep": "Preposition",
    "conj": "Conjunction",
    "num": "Numeral",
    "pron": "Pronoun",
    "intj": "Interjection",
}

_SKIP_SENSE_TAGS = {
    "form-of", "alt-of", "obsolete", "misspelling", "abbreviation",
    "initialism", "acronym",
}

_PAREN_RE = re.compile(r"\([^)]*\)")
# Strip the same leading articles bridge_lookup strips before lookup, so
# supplement keys match its post-strip queries ("beard", not "a beard").
_LEADING_ARTICLE_RE = re.compile(r"^(to|an?|the)\s+", re.IGNORECASE)


def clean_gloss(gloss):
    """One concise translation-equivalent from a Wiktionary gloss, or None.
    Wiktionary glosses range from a bare equivalent ("discipline") to a
    full definitional sentence; only the former reverses into a valid
    EN->IS pair."""
    g = _PAREN_RE.sub("", gloss).strip().rstrip(".")
    if not g or g[0].isupper():  # sentence-style definition, not an equivalent
        return None
    g = _LEADING_ARTICLE_RE.sub("", g).strip()
    if not g or "[" in g or "]" in g:
        return None
    # A translation equivalent is at most a few words; anything longer is
    # a definition in disguise.
    if len(g.split()) > 3:
        return None
    if any(ch in g for ch in ";:,\"”“"):
        return None
    # Ordinals ("0th" -> "0."), affixes ("-dom"), abbreviations: not words.
    if any(ch.isdigit() for ch in g) or g.startswith("-") or "." in g:
        return None
    return g


def main():
    pairs = set()
    with open(IN_PATH, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            pos_en = POS_MAP.get(d.get("pos"))
            if pos_en is None:
                continue
            word = d.get("word", "").strip()
            # Inflection tables sometimes leak multiword or empty headwords
            if not word or word[0].isupper():
                continue
            if any(ch.isdigit() for ch in word) or word.startswith("-") or "." in word:
                continue
            for sense in d.get("senses", []):
                tags = set(sense.get("tags", []))
                if tags & _SKIP_SENSE_TAGS or "form_of" in sense or "alt_of" in sense:
                    continue
                for gloss in sense.get("glosses", [])[:1]:
                    en = clean_gloss(gloss)
                    if en:
                        pairs.add((en.lower(), word, pos_en))

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for en, is_word, pos_en in sorted(pairs):
            out.write(f"{en}\t{is_word}\t{pos_en}\n")

    print(f"Wrote {len(pairs)} EN->IS pairs to {OUT_PATH}")


if __name__ == "__main__":
    main()
