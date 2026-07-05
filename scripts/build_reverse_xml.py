"""Builds the reverse-direction Apple Dictionary XML: Icelandic headword ->
Ancient Greek word(s). Inverts data/lsj_is.db's forward glossary (Greek ->
Icelandic), the same way icelandic-nordic-dictionary-mac inverts ISLEX for
its x2is bundles.

Coarser than the forward direction by construction, for two reasons that
are inherent to inverting a gloss-substitution bridge rather than a bug:
  1. Only single-word Icelandic glosses become reverse headwords -- a
     multi-word phrase like "konungur, yfirmaður" as a sense doesn't have
     one natural "headword" to invert on, so each comma-split single word
     is indexed separately (both "konungur" and "yfirmaður" point back to
     the Greek word that produced that sense).
  2. LSJ carries many diacritic/dialect spelling variants of what is
     linguistically "the same" Greek word as distinct headwords (e.g.
     several accentuation variants of hippos), all of which end up under
     the same Icelandic entry. This is a real property of the LSJ dataset,
     not something to silently collapse here.
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

            xml.write(f'        <h1 class="entry-lemma">{html.escape(is_word)}</h1>\n')
            xml.write('        <div class="definition">\n')
            xml.write('            <p class="gloss-en"><i>Forngrísk orð / Ancient Greek words:</i></p>\n')
            xml.write('            <p class="gloss-is">')
            xml.write(", ".join(f'<b class="gk-word">{html.escape(gk)}</b>' for gk in sorted(greek_lemmas)))
            xml.write('</p>\n')
            xml.write('        </div>\n')
            xml.write('    </d:entry>\n\n')

            if (i + 1) % 2000 == 0:
                print(f"   ... {i + 1}/{len(is_to_greek)}")

        xml.write('</d:dictionary>\n')

    print(f"Success! XML built at {OUTPUT_XML_PATH}")


if __name__ == "__main__":
    build_reverse_index()
