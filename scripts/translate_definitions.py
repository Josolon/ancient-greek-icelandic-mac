"""Gloss-translate every LSJ short definition (data/lsj.db, table `definitions`)
into Icelandic via the EN->IS glossary bridge (scripts/bridge_lookup.py),
writing results into data/lsj_is.db.

Each definition is a JSON list of English sense-strings, e.g.
  ["not to be injured, inviolable"]
We split each sense on ';' and ',' into phrases, translate each phrase
(whole-phrase lookup first, then word-by-word), and rejoin with the same
punctuation. A definition is flagged `fully_translated=0` if any phrase in
it needed an English fallback word, so low-confidence entries can be
inspected/regenerated later without redoing the whole run.
"""
import json
import re
import sqlite3
import time

from bridge_lookup import translate_phrase

LSJ_DB_PATH = "data/lsj.db"
OUT_DB_PATH = "data/lsj_is.db"

_SPLIT_RE = re.compile(r"\s*([,;])\s*")


def translate_sense(sense_text):
    """Translate one sense string, preserving its comma/semicolon structure."""
    parts = _SPLIT_RE.split(sense_text)
    out = []
    fully = True
    for part in parts:
        if part in (",", ";"):
            out.append(part + " ")
            continue
        if not part.strip():
            continue
        translated, ok = translate_phrase(part.strip())
        fully = fully and ok
        out.append(translated)
    return "".join(out).strip(), fully


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
            definitions_is TEXT NOT NULL,
            fully_translated INTEGER NOT NULL
        )"""
    )
    out.execute("CREATE INDEX idx_def_is_lemma ON definitions_is(lemma)")

    rows = lsj.execute("SELECT id, lemma, lemma_normalized, definitions FROM definitions").fetchall()
    total = len(rows)
    print(f"Translating {total} LSJ entries via EN->IS glossary bridge...")

    start = time.time()
    buffer = []
    fully_count = 0
    for i, (rid, lemma, lemma_norm, defs_json) in enumerate(rows):
        try:
            senses = json.loads(defs_json)
        except (json.JSONDecodeError, TypeError):
            senses = [defs_json]

        is_senses = []
        entry_fully = True
        for sense in senses:
            is_text, ok = translate_sense(sense)
            is_senses.append(is_text)
            entry_fully = entry_fully and ok
        fully_count += 1 if entry_fully else 0

        buffer.append((rid, lemma, lemma_norm, defs_json, json.dumps(is_senses, ensure_ascii=False), int(entry_fully)))

        if len(buffer) >= 5000:
            out.executemany("INSERT INTO definitions_is VALUES (?,?,?,?,?,?)", buffer)
            out.commit()
            buffer.clear()
            elapsed = time.time() - start
            print(f"  ... {i + 1}/{total} ({elapsed:.0f}s elapsed)")

    if buffer:
        out.executemany("INSERT INTO definitions_is VALUES (?,?,?,?,?,?)", buffer)
        out.commit()

    print(f"Done in {time.time() - start:.0f}s. Fully translated (no English fallback words): "
          f"{fully_count}/{total} ({100 * fully_count / total:.1f}%)")

    lsj.close()
    out.close()


if __name__ == "__main__":
    main()
