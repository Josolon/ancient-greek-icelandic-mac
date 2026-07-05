"""Gloss-translate every LSJ short definition (data/lsj.db, table `definitions`)
into an Icelandic glossary via the EN->IS bridge (scripts/bridge_lookup.py),
writing results into data/lsj_is.db.

This is a glossary, not a dictionary: each LSJ sense (e.g. "king, chief") is
split on ','/';' into short candidate phrases, and each phrase is translated
independently through translate_glossary_phrase(), which refuses to guess --
it returns None rather than pidgin when it lacks confident evidence. Phrases
that translate become the Icelandic gloss for that sense; phrases that don't
are simply omitted from the Icelandic side (not force-translated word by
word). If NONE of a sense's phrases translate, the original English sense
is kept as-is so no information is silently lost.
"""
import json
import re
import sqlite3
import time

from bridge_lookup import translate_glossary_phrase

LSJ_DB_PATH = "data/lsj.db"
OUT_DB_PATH = "data/lsj_is.db"

_SPLIT_RE = re.compile(r"\s*[,;]\s*")


def translate_sense(sense_text):
    """Returns (icelandic_or_none, any_translated, all_translated) for one
    LSJ sense string."""
    phrases = [p for p in _SPLIT_RE.split(sense_text) if p.strip()]
    if not phrases:
        return None, False, False

    translated = []
    hits = 0
    for phrase in phrases:
        is_text = translate_glossary_phrase(phrase)
        if is_text:
            translated.append(is_text)
            hits += 1

    if hits == 0:
        return None, False, False
    return ", ".join(translated), True, hits == len(phrases)


def main():
    lsj = sqlite3.connect(LSJ_DB_PATH)
    out = sqlite3.connect(OUT_DB_PATH)
    out.execute("DROP TABLE IF EXISTS definitions_is")
    out.execute(
        """CREATE TABLE definitions_is (
            id INTEGER PRIMARY KEY,
            lemma TEXT NOT NULL,
            lemma_normalized TEXT NOT NULL,
            definitions_en TEXT NOT NULL,
            definitions_is TEXT,
            fully_translated INTEGER NOT NULL,
            any_translated INTEGER NOT NULL
        )"""
    )
    out.execute("CREATE INDEX idx_def_is_lemma ON definitions_is(lemma)")

    rows = lsj.execute("SELECT id, lemma, lemma_normalized, definitions FROM definitions").fetchall()
    total = len(rows)
    print(f"Building Icelandic glossary for {total} LSJ entries...")

    start = time.time()
    buffer = []
    fully_count = 0
    any_count = 0
    none_count = 0
    for i, (rid, lemma, lemma_norm, defs_json) in enumerate(rows):
        try:
            senses = json.loads(defs_json)
        except (json.JSONDecodeError, TypeError):
            senses = [defs_json]

        is_senses = []
        entry_fully = True
        entry_any = False
        for sense in senses:
            is_text, any_ok, all_ok = translate_sense(sense)
            entry_fully = entry_fully and all_ok
            entry_any = entry_any or any_ok
            if is_text:
                is_senses.append(is_text)

        if entry_any:
            any_count += 1
        else:
            none_count += 1
        if entry_fully and entry_any:
            fully_count += 1

        is_json = json.dumps(is_senses, ensure_ascii=False) if is_senses else None
        buffer.append((rid, lemma, lemma_norm, defs_json, is_json, int(entry_fully and entry_any), int(entry_any)))

        if len(buffer) >= 5000:
            out.executemany("INSERT INTO definitions_is VALUES (?,?,?,?,?,?,?)", buffer)
            out.commit()
            buffer.clear()
            elapsed = time.time() - start
            print(f"  ... {i + 1}/{total} ({elapsed:.0f}s elapsed)")

    if buffer:
        out.executemany("INSERT INTO definitions_is VALUES (?,?,?,?,?,?,?)", buffer)
        out.commit()

    print(f"Done in {time.time() - start:.0f}s.")
    print(f"  Fully translated (every sense, every phrase): {fully_count}/{total} ({100*fully_count/total:.1f}%)")
    print(f"  At least partially translated: {any_count}/{total} ({100*any_count/total:.1f}%)")
    print(f"  No confident translation at all (English only): {none_count}/{total} ({100*none_count/total:.1f}%)")

    lsj.close()
    out.close()


if __name__ == "__main__":
    main()
