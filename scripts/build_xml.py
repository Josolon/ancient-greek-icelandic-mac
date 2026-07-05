"""Builds the Apple Dictionary XML for the Ancient Greek -> Icelandic bridge
dictionary. Headwords and morphology come from ancient-greek-mac's LSJ/Morpheus
databases (data/lsj.db, data/morph.db); Icelandic glosses come from
data/lsj_is.db, produced by translate_definitions.py.

Adapted from ancient-greek-mac/scripts/build_xml.py -- see that project for
the original English-only version this is derived from.
"""
import sqlite3
import html
import os
import unicodedata
import json
from collections import defaultdict

LSJ_DB_PATH = 'data/lsj.db'
MORPH_DB_PATH = 'data/morph.db'
IS_DB_PATH = 'data/lsj_is.db'
OUTPUT_XML_PATH = 'src/GreekIcelandicDictionary.xml'

PRINCIPAL_PARTS_ORDER = [
    'Present Active', 'Present Middle', 'Present Passive',
    'Future Active',  'Future Middle',
    'Aorist Active',  'Aorist Middle',
    'Perfect Active',
    'Perfect Middle', 'Perfect Passive',
    'Aorist Passive',
]
PRINCIPAL_PARTS_PRIMARY = frozenset(PRINCIPAL_PARTS_ORDER)

# Standard Icelandic grammatical terms for case/number -- these are
# everyday Icelandic (taught in school), unlike aspect/voice terminology
# for Ancient Greek verbs, which has no settled Icelandic classicist
# convention; verb principal-part labels are therefore left in English.
CASE_LABELS_IS = {
    'nominative': 'Nefnifall', 'genitive': 'Eignarfall',
    'dative': 'Þágufall', 'accusative': 'Þolfall', 'vocative': 'Ávarpsfall',
}
NUMBER_LABELS_IS = {'singular': 'Eintala', 'dual': 'Tvítala', 'plural': 'Fleirtala'}


def sanitize_apple_key(text):
    if not text:
        return ""
    kw = text.strip()
    kw = unicodedata.normalize('NFC', kw)
    while kw and not unicodedata.category(kw[0]).startswith(('L', 'N')):
        kw = kw[1:]
    return kw


def build_dictionary():
    print("Starting Ancient Greek -> Icelandic Apple Dictionary XML generation...")

    for path in (LSJ_DB_PATH, MORPH_DB_PATH, IS_DB_PATH):
        if not os.path.exists(path):
            print(f"Error: {path} not found.")
            return

    lsj_conn = sqlite3.connect(LSJ_DB_PATH)
    morph_conn = sqlite3.connect(MORPH_DB_PATH)
    is_conn = sqlite3.connect(IS_DB_PATH)

    lsj_cursor = lsj_conn.cursor()
    morph_cursor = morph_conn.cursor()

    print("Loading Icelandic bridge glosses...")
    is_cursor = is_conn.cursor()
    is_cursor.execute("SELECT id, definitions_is, any_translated FROM definitions_is")
    is_by_id = {row[0]: (row[1], row[2]) for row in is_cursor.fetchall()}

    with open(OUTPUT_XML_PATH, 'w', encoding='utf-8') as xml:
        xml.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        xml.write('<d:dictionary xmlns="http://www.w3.org/1999/xhtml" xmlns:d="http://www.apple.com/DTDs/DictionaryService-1.0.rng">\n\n')

        print("Fetching LSJ entries...")
        lsj_cursor.execute("SELECT id, lemma, lemma_normalized, definitions FROM definitions")
        entries = lsj_cursor.fetchall()

        total_entries = len(entries)
        print(f"Found {total_entries} entries. Building structures...")

        for index, row in enumerate(entries):
            entry_id = f"lsj_{row[0]}"
            raw_lemma = row[1]
            raw_lemma_norm = row[2]
            raw_def_en = row[3]

            is_def_json, any_translated = is_by_id.get(row[0], (None, 0))

            safe_title = sanitize_apple_key(raw_lemma)
            if not safe_title:
                safe_title = "unknown"

            xml.write(f'    <d:entry id="{entry_id}" d:title="{html.escape(safe_title)}">\n')
            search_indices = {raw_lemma, raw_lemma_norm}

            morph_cursor.execute("""
                SELECT form, form_normalized, pos, tense, voice, mood, person, number, case_name, gender
                FROM morphology WHERE lemma = ?
            """, (raw_lemma,))
            morph_rows = morph_cursor.fetchall()

            is_verb = False
            is_noun_adj = False
            noun_grid = defaultdict(lambda: defaultdict(set))
            verb_principal_parts = defaultdict(set)
            generic_forms = defaultdict(list)

            for mr in morph_rows:
                raw_form = mr[0]
                raw_form_norm = mr[1]
                pos = mr[2]
                tense = mr[3]
                voice = mr[4]
                mood = mr[5]
                person = mr[6]
                number = mr[7]
                case_name = mr[8]

                search_indices.add(raw_form)
                search_indices.add(raw_form_norm)

                display_form = html.escape(raw_form)

                if pos == 'verb':
                    is_verb = True
                    if person == '1st' and number == 'singular' and mood == 'indicative':
                        label = f"{str(tense).capitalize()} {str(voice).capitalize()}".strip()
                        verb_principal_parts[label].add(display_form)

                elif pos in ('noun', 'adjective', 'article', 'pronoun'):
                    is_noun_adj = True
                    if case_name and number:
                        noun_grid[case_name][number].add(display_form)

                else:
                    parsing_elements = [str(item) for item in mr[2:] if item]
                    parsing_str = " ".join(parsing_elements)
                    if parsing_str and parsing_str not in generic_forms[display_form]:
                        generic_forms[display_form].append(parsing_str)

            valid_indices = set()
            for keyword in search_indices:
                clean_kw = sanitize_apple_key(keyword)
                if clean_kw:
                    valid_indices.add(clean_kw)

            for keyword in valid_indices:
                xml.write(f'        <d:index d:value="{html.escape(keyword)}"/>\n')

            def render_defs(raw_json):
                try:
                    if raw_json.startswith('[') and raw_json.endswith(']'):
                        return "; ".join(html.escape(d) for d in json.loads(raw_json))
                    return html.escape(raw_json)
                except (json.JSONDecodeError, AttributeError):
                    return html.escape(str(raw_json))

            clean_definition_en = render_defs(raw_def_en)

            xml.write(f'        <h1 class="entry-lemma">{html.escape(raw_lemma)}</h1>\n')
            xml.write(f'        <div class="definition">\n')
            if any_translated and is_def_json:
                clean_definition_is = render_defs(is_def_json)
                xml.write(f'            <p class="gloss-is"><b>ÍS:</b> {clean_definition_is}</p>\n')
            else:
                xml.write(f'            <p class="gloss-is gloss-missing">Engin trygg þýðing í orðasafninu.</p>\n')
            xml.write(f'            <p class="gloss-en"><b>EN (LSJ):</b> {clean_definition_en}</p>\n')
            xml.write(f'        </div>\n')

            if is_noun_adj and noun_grid:
                xml.write('        <div class="morph-section">\n')
                xml.write('            <p class="morph-label">Beygingar / Declension</p>\n')
                xml.write('            <table class="morphology-table">\n')
                xml.write('                <tr><th>Fall</th><th>Eintala</th><th>Tvítala</th><th>Fleirtala</th></tr>\n')

                for c in ['nominative', 'genitive', 'dative', 'accusative', 'vocative']:
                    if c in noun_grid:
                        sing = ", ".join(noun_grid[c].get('singular', ['—']))
                        dual = ", ".join(noun_grid[c].get('dual', ['—']))
                        plur = ", ".join(noun_grid[c].get('plural', ['—']))
                        label = CASE_LABELS_IS.get(c, c.capitalize())
                        xml.write(f'                <tr><td class="case-label">{label}</td><td>{sing}</td><td>{dual}</td><td>{plur}</td></tr>\n')

                xml.write('            </table>\n')
                xml.write('        </div>\n')

            elif is_verb and verb_principal_parts:
                primary_parts = {k: v for k, v in verb_principal_parts.items() if k in PRINCIPAL_PARTS_PRIMARY}
                secondary_parts = {k: v for k, v in verb_principal_parts.items() if k not in PRINCIPAL_PARTS_PRIMARY}
                xml.write('        <div class="morph-section">\n')
                xml.write('            <p class="morph-label">Sagnmyndir / Principal Parts</p>\n')
                xml.write('            <table class="morphology-table">\n')
                xml.write('                <tr><th>Tíð &amp; Mynd</th><th>Mynd (1. p. et. framsöguh.)</th></tr>\n')

                for label in PRINCIPAL_PARTS_ORDER:
                    if label in primary_parts:
                        xml.write(f'                <tr><td class="case-label">{label}</td><td>{", ".join(primary_parts[label])}</td></tr>\n')
                if secondary_parts:
                    xml.write('                <tr class="morph-secondary-header"><td colspan="2">Additional attested forms</td></tr>\n')
                    for label, forms in sorted(secondary_parts.items()):
                        xml.write(f'                <tr><td class="case-label">{label}</td><td>{", ".join(forms)}</td></tr>\n')

                xml.write('            </table>\n')
                xml.write('        </div>\n')

            elif generic_forms:
                xml.write('        <div class="morph-section">\n')
                xml.write('            <p class="morph-label">Myndir / Forms</p>\n')
                xml.write('            <table class="morphology-table">\n')
                for m_form, m_parsings in generic_forms.items():
                    parsing_display = ", ".join(html.escape(p) for p in m_parsings)
                    xml.write(f'                <tr><td class="case-label">{m_form}</td><td>{parsing_display}</td></tr>\n')
                xml.write('            </table>\n')
                xml.write('        </div>\n')

            xml.write('    </d:entry>\n\n')

            if (index + 1) % 5000 == 0:
                print(f"   ... Processed {index + 1} / {total_entries} entries")

        xml.write('</d:dictionary>\n')

    print(f"Success! XML built at {OUTPUT_XML_PATH}")

    lsj_conn.close()
    morph_conn.close()
    is_conn.close()


if __name__ == "__main__":
    build_dictionary()
