# Ancient Greek → Icelandic Dictionary

A `.dictionary` plugin for the native macOS Dictionary app and system-wide
"Look Up" feature, glossing the **LSJ Ancient Greek lexicon** (110,826
entries) into Icelandic.

## How translation works — read this before relying on a gloss

There is no existing Ancient Greek–Icelandic dictionary to build from, so
this project bridges two independent resources:

1. **LSJ** (Liddell–Scott–Jones), which glosses Ancient Greek headwords into
   short English definitions — reused from the companion
   [`ancient-greek-mac`](https://github.com/Josolon/ancient-greek-mac) project.
2. The **CLARIN IS-EN glossary**, a bilingual English↔Icelandic word list with
   confidence scores per translation pair — reused from
   [`icelandic-english-dictionary-mac`](https://github.com/Josolon/icelandic-english-dictionary-mac).

`scripts/translate_definitions.py` takes each LSJ English gloss (e.g. *"not
to be injured, inviolable"*), splits it into phrases, and translates each
phrase by looking it up whole first, then falling back to word-by-word
substitution using the best-scored Icelandic candidate for each English
word (`scripts/bridge_lookup.py`).

**This is gloss-substitution, not fluent translation.** No LLM and no human
translator touched the Icelandic text — it's mechanical word/phrase
substitution through a bilingual word list. Expect:
- Correct simple entries: *ἵππος* → "hestur"
- Word-order and inflection issues: Icelandic isn't just re-ordered English,
  so multi-word glosses often read like pidgin ("einn kvörtun af hinn skjár"
  for "a complaint of the eyes" — "skjár" is a mistranslation of "eyes" via
  an ambiguous glossary entry, not "auga/augu").
- Missing words: if the glossary has no entry for an English word, it's left
  untranslated in place.

Every entry whose Icelandic gloss required an English fallback word is
flagged internally (`fully_translated = 0` in `data/lsj_is.db`), and the
compiled dictionary shows the original English LSJ gloss underneath the
Icelandic one in those cases, so you can sanity-check it. About 60% of
entries translate with no fallback words needed.

**Use this as a first-pass aid for recognizing a Greek word's rough meaning,
not as a citable Icelandic definition.** Improving translation quality (better
phrase segmentation, sense disambiguation, POS-aware lookup) is the most
valuable kind of contribution here.

## ✨ Features

* **110k LSJ entries**, bridge-glossed into Icelandic.
* **System Integration:** works natively with macOS "Look Up".
* **Morphology tables:** noun declensions and verb principal parts, reused
  directly from `ancient-greek-mac`'s Morpheus data. Case/number labels are
  shown in Icelandic (Nefnifall, Eignarfall, Þágufall, Þolfall, Ávarpsfall /
  Eintala, Tvítala, Fleirtala) since these are standard school-taught terms;
  verb tense/voice labels are left in English pending a settled Icelandic
  classicist convention — see Contributing.
* **Transparency:** low-confidence glosses show the original English LSJ
  definition alongside the Icelandic bridge translation.

## 📦 Installation (For End Users)

1. Download the latest release from the [Releases](https://github.com/Josolon/ancient-greek-icelandic-mac/releases) page.
2. Unzip to get `AncientGreekIcelandicDictionary.dictionary`.
3. Open Finder, press `Cmd+Shift+G`, navigate to `~/Library/Dictionaries/`.
4. Drag the `.dictionary` folder there.
5. Open Dictionary.app → Settings → enable "Forngríska (LSJ) - Íslenska".

## 🛠️ Building from Source

### Prerequisites
* Python 3.x
* [Dictionary Development Kit](https://developer.apple.com/download/all/) (Apple's "Additional Tools for Xcode")
* The `data/lsj.db` / `data/morph.db` SQLite databases from
  [`ancient-greek-mac`](https://github.com/Josolon/ancient-greek-mac) (gitignored here, copy them over)
* `data/IS-EN_glossary.tsv` from CLARIN Iceland (gitignored here) —
  https://repository.clarin.is/repository/xmlui/handle/20.500.12537/144

### Build steps

```bash
# 1. Gloss-translate LSJ's English definitions into Icelandic (fast, ~1s)
python3 scripts/translate_definitions.py

# 2. Generate the Apple Dictionary XML (a few seconds, ~200MB output)
python3 scripts/build_xml.py

# 3. Compile and install
cd src && make install
```

## 📁 Project Structure

```
ancient-greek-icelandic-mac/
├── data/
│   ├── lsj.db                  # LSJ entries [gitignored, from ancient-greek-mac]
│   ├── morph.db                # Morpheus morphology [gitignored, from ancient-greek-mac]
│   ├── IS-EN_glossary.tsv      # EN<->IS bridge glossary [gitignored, from CLARIN]
│   └── lsj_is.db               # Generated Icelandic glosses [gitignored, regenerate]
├── scripts/
│   ├── bridge_lookup.py        # EN->IS phrase/word lookup against the glossary
│   ├── translate_definitions.py # Runs every LSJ gloss through the bridge
│   └── build_xml.py            # Generates the Apple Dictionary XML
├── src/
│   ├── GreekIcelandicDictionary.xml   # Generated [gitignored]
│   ├── GreekIcelandicDictionary.css
│   ├── GreekIcelandicDictionary.plist
│   ├── Makefile
│   └── objects/                # Build artifacts [gitignored]
└── README.md
```

## 🤝 Contributing

* **Translation quality:** the biggest opportunity. Better phrase
  segmentation, POS-aware sense disambiguation, or filtering out
  proper-noun/acronym outliers from the glossary (see `_OVERRIDES` in
  `scripts/bridge_lookup.py` for the pattern already used to fix the worst
  offenders like "it" → "upplýsingatækni") all directly improve output.
* **Icelandic classical-grammar terminology:** if you know the standard
  Icelandic terms for Greek verb tense/voice/mood (as taught in Icelandic
  classics courses, if such a convention exists), replacing the English
  labels in `scripts/build_xml.py` would be valuable.
* **Weird/broken entries:** same caveat as `ancient-greek-mac` — 110k
  auto-generated entries will have edge cases.

**Not in scope:** LSJ headwords/definitions and morphology data themselves
are maintained upstream (Chicago Digital Classics / Perseids) — report
issues with the *source* English gloss there, not here.

## 📚 Data Sources

See [CREDITS.md](CREDITS.md) for full attribution.

* **LSJ Lexicon & Morphology:** same sources as `ancient-greek-mac`.
* **Bridge glossary:** CLARIN Iceland, English-Icelandic/Icelandic-English glossary 21.09.

## 📄 License

Dual-license, same structure as `ancient-greek-mac`: code under MIT, data
under CC BY-SA 4.0 (LSJ) / CC BY 4.0 (glossary) / CC BY-SA 4.0 (this
project's generated Icelandic glosses, since they derive from CC BY-SA
LSJ text). See [LICENSE](LICENSE) for full details.
