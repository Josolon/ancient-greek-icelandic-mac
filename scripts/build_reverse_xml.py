"""Builds the reverse-direction Apple Dictionary XML: Icelandic headword ->
Ancient Greek word(s). Inverts data/lsj_is.db's forward glossary (Greek ->
Icelandic), the same way icelandic-nordic-dictionary-mac inverts ISLEX for
its x2is bundles.

Coarser than the forward direction by construction:
  1. Only single-word Icelandic glosses become reverse headwords -- a
     multi-word phrase like "konungur, yfirmaður" as a sense doesn't have
     one natural "headword" to invert on, so each comma-split single word
     is indexed separately (both "konungur" and "yfirmaður" point back to
     the Greek word that produced that sense).
  2. LSJ carries many pure ACCENT-placement variants of what is
     unambiguously the same Greek word as distinct headwords (e.g. hippos
     appearing with an acute, a grave, a circumflex, or no accent mark at
     all, purely as an artifact of the source text/edition). These are
     deduplicated below via _accent_key(), which strips only the
     acute/grave/circumflex combining marks -- NOT breathing marks or
     capitalization, both of which are meaningful in Greek (rough vs smooth
     breathing distinguishes real word pairs like hóros "boundary" vs
     óros "mountain"; capitalization distinguishes a proper name like
     Hippos from the common noun hippos "horse"). So "case/accent
     differences with no meaningful difference" are collapsed, but
     anything that could actually change the word is deliberately left
     alone, at the cost of leaving some genuine near-duplicates unmerged.
No morphology tables in this direction -- the headword is Icelandic, not
Greek, so Morpheus declension/principal-part data doesn't apply (same
scope decision as icelandic-nordic-dictionary-mac's x2is bundles).
"""
import html
import json
import os
import sqlite3
import unicodedata
from collections import defaultdict

IS_DB_PATH = "data/lsj_is.db"
OUTPUT_XML_PATH = "src/IcelandicGreekDictionary.xml"

# Combining accent marks (acute, grave, circumflex/perispomeni) to strip for
# dedup purposes. Deliberately excludes breathing marks (U+0313 smooth,
# U+0314 rough) and iota subscript (U+0345), which are never purely
# cosmetic in Greek.
_ACCENT_MARKS = {"́", "̀", "͂"}


def _accent_key(word):
    """Grouping key that folds away pure accent-placement variants while
    preserving breathing marks and case (both can be semantically real)."""
    decomposed = unicodedata.normalize("NFD", word)
    return "".join(ch for ch in decomposed if ch not in _ACCENT_MARKS)


def _dedup_greek_forms(lemmas):
    """Collapse accent-only spelling variants in `lemmas` to one
    representative each, preferring the fullest/most-accented spelling
    (more combining marks = more standard/complete accentuation), with a
    deterministic alphabetical tie-break."""
    groups = defaultdict(list)
    for lemma in lemmas:
        groups[_accent_key(lemma)].append(lemma)

    def mark_count(s):
        return len(unicodedata.normalize("NFD", s)) - len(s)

    representatives = []
    for variants in groups.values():
        best = sorted(variants, key=lambda s: (-mark_count(s), s))[0]
        representatives.append(best)
    return representatives


def sanitize_apple_key(text):
    if not text:
        return ""
    kw = text.strip()
    kw = unicodedata.normalize("NFC", kw)
    while kw and not unicodedata.category(kw[0]).startswith(("L", "N")):
        kw = kw[1:]
    return kw


def build_reverse_index():
    if not os.path.exists(IS_DB_PATH):
        print(f"Error: {IS_DB_PATH} not found -- run translate_definitions.py first.")
        return

    conn = sqlite3.connect(IS_DB_PATH)
    rows = conn.execute(
        "SELECT lemma, definitions_is FROM definitions_is WHERE any_translated = 1"
    ).fetchall()
    conn.close()

    print(f"Inverting {len(rows)} Greek entries with Icelandic glosses...")

    is_to_greek = defaultdict(set)
    for lemma, defs_json in rows:
        try:
            senses = json.loads(defs_json)
        except (json.JSONDecodeError, TypeError):
            continue
        for sense in senses:
            for word in sense.split(","):
                word = word.strip()
                if word and " " not in word:
                    is_to_greek[word.lower()].add(lemma)

    print(f"Built {len(is_to_greek)} Icelandic headwords.")

    with open(OUTPUT_XML_PATH, "w", encoding="utf-8") as xml:
        xml.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        xml.write('<d:dictionary xmlns="http://www.w3.org/1999/xhtml" xmlns:d="http://www.apple.com/DTDs/DictionaryService-1.0.rng">\n\n')

        for i, (is_word, greek_lemmas) in enumerate(sorted(is_to_greek.items())):
            entry_id = f"is2gk_{i}"
            safe_title = sanitize_apple_key(is_word)
            if not safe_title:
                continue

            xml.write(f'    <d:entry id="{entry_id}" d:title="{html.escape(safe_title)}">\n')
            xml.write(f'        <d:index d:value="{html.escape(safe_title)}"/>\n')

            deduped = _dedup_greek_forms(greek_lemmas)

            xml.write(f'        <h1 class="entry-lemma">{html.escape(is_word)}</h1>\n')
            xml.write('        <div class="definition">\n')
            xml.write('            <p class="gloss-en"><i>Forngrísk orð / Ancient Greek words:</i></p>\n')
            xml.write('            <p class="gloss-is">')
            xml.write(", ".join(f'<b class="gk-word">{html.escape(gk)}</b>' for gk in sorted(deduped)))
            xml.write('</p>\n')
            xml.write('        </div>\n')
            xml.write('    </d:entry>\n\n')

            if (i + 1) % 2000 == 0:
                print(f"   ... {i + 1}/{len(is_to_greek)}")

        xml.write('</d:dictionary>\n')

    print(f"Success! XML built at {OUTPUT_XML_PATH}")


if __name__ == "__main__":
    build_reverse_index()
