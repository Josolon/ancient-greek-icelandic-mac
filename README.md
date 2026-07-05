# Ancient Greek ↔ Icelandic Dictionary

Two `.dictionary` plugins for the native macOS Dictionary app and
system-wide "Look Up" feature, built from the **LSJ Ancient Greek lexicon**
(110,826 entries):

* **AncientGreekIcelandicDictionary** — Greek headword → Icelandic glossary
  (+ full English LSJ gloss for reference).
* **IcelandicGreekDictionary** — Icelandic headword → Ancient Greek word(s),
  a reverse index inverted from the forward glossary.

## How this works — read this before relying on a gloss

There is no existing Ancient Greek–Icelandic dictionary to build from, so
this project bridges two independent resources:

1. **LSJ** (Liddell–Scott–Jones), which glosses Ancient Greek headwords into
   short English definitions — reused from the companion
   [`ancient-greek-mac`](https://github.com/Josolon/ancient-greek-mac) project.
2. The **CLARIN IS-EN glossary**, a bilingual English↔Icelandic word list with
   per-pair confidence scores and method-evidence counts — reused from
   [`icelandic-english-dictionary-mac`](https://github.com/Josolon/icelandic-english-dictionary-mac).

This is deliberately built as **a glossary, not a dictionary**: the goal is
a list of trustworthy Icelandic word equivalents for each Greek headword,
not fluent Icelandic prose. `scripts/bridge_lookup.py` is precision-first —
it returns an Icelandic candidate only when the glossary gives real
evidence for it (checking translation score *and* how much independent
evidence backs that score — a hard evidence floor, not just a soft
down-weight, since a lone corpus-alignment artifact with a perfect score
can otherwise outrank a well-attested word with a lower one; filtering out
proper-noun/acronym outliers; and lemmatizing English inflected forms so
e.g. "eyes" inherits "eye"'s much better-attested translation instead of a
weak one-off alignment). When it isn't confident, it returns nothing rather
than guessing.

`scripts/translate_definitions.py` builds the glossary sense-by-sense: each
LSJ sense (e.g. *"king, chief"*) is split into short phrases, and each
phrase is translated independently. Two hard rules keep this from
regressing into pidgin:

1. **No word-by-word phrase reconstruction.** A phrase translates only if
   it's a single word, or an exact whole-phrase match already established
   in the glossary (a real idiom, like "run away" → "strjúka") — never a
   concatenation of separately-looked-up words. Each word in "a tyrant's
   dwelling" might translate fine in isolation, but "harðstjóri suður
   bústaður" isn't Icelandic; nobody chose that combination on purpose, so
   it's refused rather than emitted. This means a polysemous word's
   multi-word senses often don't get an Icelandic gloss at all — the
   glossary favors dropping a sense over fabricating one.
2. **LSJ's own apparatus is filtered out before translation is attempted.**
   LSJ's short-definition field also carries cross-references to other
   headwords, citation sigla, and page/chapter numbers (e.g. *"Ion. for
   πολύς... Ep."* or *"D.H. 6.17, Plu. Marc. 3, etc."*) — none of that is
   an actual English gloss, and translating it produces nonsense results
   like a citation abbreviation becoming a real Icelandic word. These are
   detected (Greek characters, digits, capitalized citation sigla) and
   skipped outright.

A phrase that can't be confidently translated is simply **omitted from the
Icelandic side**. If a sense has no confident translation at all, the
original English is kept so no information is silently dropped; the
compiled dictionary always shows the full English LSJ gloss beneath the
Icelandic glossary for reference and to catch dropped senses.

Coverage, from the current build:
- 17.5% of entries: every sense, every phrase, translated
- 52.1% of entries: at least a partial Icelandic glossary
- 47.9% of entries: no confident translation at all (English-only fallback)

Coverage is lower than an earlier version of this project, on purpose —
that version reconstructed multi-word phrases and let low-evidence
candidates through, which covered more entries but with real grammatical
and semantic garbage mixed in throughout (see git history if curious what
that looked like). This version trades coverage for not lying to you.

**Use the Icelandic side as a fast way to recognize a Greek word's rough
meaning, not as a citable definition.** The English LSJ gloss alongside it
is the authoritative source.

### The reverse direction (Icelandic → Greek) is coarser still

`scripts/build_reverse_xml.py` inverts the forward glossary: every
single-word Icelandic gloss becomes a headword pointing back to the Greek
word(s) that produced it (multi-word glosses aren't invertible onto one
headword, so only single words are indexed). Two things fall out of this
that are inherent to the data, not bugs:
- LSJ carries many diacritic/dialect spelling variants of what is
  linguistically "the same" Greek word as separate headwords, so a lookup
  like "hestur" returns a cluster of near-duplicate forms (ἵππος, ἱππος,
  Ἵππος, ...) rather than one clean entry.
- No morphology tables in this direction — the headword is Icelandic, not
  Greek, so Morpheus declension data doesn't apply (same scope decision as
  `icelandic-nordic-dictionary-mac`'s reverse bundles).

## ✨ Features

* **110k LSJ entries**, glossed into Icelandic where the bridge is confident.
* **9,611 Icelandic headwords** in the reverse index.
* **System Integration:** works natively with macOS "Look Up".
* **Morphology tables** (forward direction only): noun declensions and verb
  principal parts, reused directly from `ancient-greek-mac`'s Morpheus data.
  Case/number labels are shown in Icelandic (Nefnifall, Eignarfall,
  Þágufall, Þolfall, Ávarpsfall / Eintala, Tvítala, Fleirtala) since these
  are standard school-taught terms; verb tense/voice labels are left in
  English pending a settled Icelandic classicist convention — see
  Contributing.
* **Transparency:** the full English LSJ gloss is always shown alongside
  the Icelandic glossary, so nothing is silently hidden behind a
  translation guess.

## 📦 Installation (For End Users)

1. Download the latest release from the [Releases](https://github.com/Josolon/ancient-greek-icelandic-mac/releases) page.
2. Unzip to get `AncientGreekIcelandicDictionary.dictionary` and/or `IcelandicGreekDictionary.dictionary`.
3. Open Finder, press `Cmd+Shift+G`, navigate to `~/Library/Dictionaries/`.
4. Drag the `.dictionary` folder(s) there.
5. Open Dictionary.app → Settings → enable "Forngríska (LSJ) - Íslenska" and/or "Íslenska - Forngríska (LSJ, öfug leit)".

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
# 1. Build the Icelandic glossary from LSJ's English definitions (fast, ~1s)
python3 scripts/translate_definitions.py

# 2. Generate both Apple Dictionary XML sources
python3 scripts/build_xml.py            # forward: Greek -> Icelandic
python3 scripts/build_reverse_xml.py    # reverse: Icelandic -> Greek

# 3. Compile and install both bundles
cd src && make install
```

Note: Apple's `build_dict.sh` fetches `PropertyList-1.0.dtd` from apple.com
on every invocation; a transient network hiccup can abort a build mid-way
with an "unable to parse dict.plist" error (same issue documented in
`icelandic-nordic-dictionary-mac`). Just re-run `make install`.

## 📁 Project Structure

```
ancient-greek-icelandic-mac/
├── data/
│   ├── lsj.db                  # LSJ entries [gitignored, from ancient-greek-mac]
│   ├── morph.db                # Morpheus morphology [gitignored, from ancient-greek-mac]
│   ├── IS-EN_glossary.tsv      # EN<->IS bridge glossary [gitignored, from CLARIN]
│   └── lsj_is.db               # Generated Icelandic glossary [gitignored, regenerate]
├── scripts/
│   ├── bridge_lookup.py        # Precision-first EN->IS phrase/word lookup
│   ├── translate_definitions.py # Builds the Icelandic glossary sense-by-sense
│   ├── build_xml.py            # Forward direction: Greek -> Icelandic XML
│   └── build_reverse_xml.py    # Reverse direction: Icelandic -> Greek XML
├── src/
│   ├── GreekIcelandicDictionary.{xml,css,plist}      # forward bundle [xml gitignored]
│   ├── IcelandicGreekDictionary.{xml,plist}          # reverse bundle [xml gitignored]
│   ├── Makefile                # builds + installs both bundles
│   └── objects/                # Build artifacts [gitignored]
└── README.md
```

## 🤝 Contributing

* **Translation quality:** the biggest opportunity. `scripts/bridge_lookup.py`
  already lemmatizes English inflected forms and penalizes proper-noun/
  acronym outliers and self-referential candidates — extending that (better
  phrase segmentation, real POS tagging of LSJ senses instead of a POS-less
  guess) directly improves coverage and precision.
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
project's generated Icelandic glossary and reverse index, since they derive
from CC BY-SA LSJ text). See [LICENSE](LICENSE) for full details.
