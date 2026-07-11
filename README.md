# Ancient Greek ↔ Icelandic Dictionary

> **⚠️ Work in progress — not ready for general use.** This is an early,
> honest-effort attempt at a hard problem (there is no existing
> Ancient Greek-Icelandic dictionary to build from), not a finished
> reference work. Please read the whole "How this works" section below
> before relying on anything it outputs. In short:
> - It's a **glossary of word-level equivalents**, not a dictionary of
>   fluent Icelandic definitions.
> - Coverage is partial by design: ~54% of entries get a concise Icelandic
>   gloss, and the rest fall back to English-only because nothing confident
>   was found.
> - Even where it does return an Icelandic word, it can be the **wrong
>   sense** of a polysemous headword (the independent resources this
>   bridges don't share any notion of "the same sense") — always cross-check
>   against the English LSJ gloss shown alongside it.
> - The reverse (Icelandic → Greek) direction is coarser still. Pure
>   accent-placement duplicates of the same Greek word are collapsed, but
>   breathing-mark and capitalization differences are kept apart on purpose
>   (both can be genuinely meaningful in Greek), so some near-duplicate
>   results remain.
>
> Contributions on translation quality, phrase segmentation, and citation
> filtering are very welcome — see Contributing below.

Two `.dictionary` plugins for the native macOS Dictionary app and
system-wide "Look Up" feature, built from the **LSJ Ancient Greek lexicon**
(110,826 raw entries, merged down to 49,828 dictionary entries — see
"Duplicate headwords" below):

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
3. A **Wiktionary supplement** (`data/wiktionary_en_is.tsv`): human-curated
   EN→IS pairs extracted from the Icelandic entries of English Wiktionary
   (via kaikki.org), merged into the candidate ranking as extra evidence —
   it rescues words the CLARIN glossary lacks and helps well-attested
   candidates outrank corpus-alignment artifacts.

This is deliberately built as **a glossary, not a dictionary**: for
παιδεύω the goal is *"ala upp, mennta, kenna"* — a handful of well-chosen
Icelandic words — not a word-by-word shadow of LSJ's full sense apparatus
(an earlier version produced *"lyfta; refsa, refsa; leiðrétta, aga; kenna;
mennta"* for that same entry: duplicated words, a mistranslation per
sense, and no sense of which meaning is primary).

The concise gloss is built **shortdef-first**: LSJ's curated one-line
definition per lemma (*"bring up, educate, teach"*) is translated —
phrase by phrase, deduplicated, capped at five words — and if it yields
anything, that IS the entry's Icelandic gloss. Only when the shortdef is
missing or yields nothing does the builder fall back to the full sense
list, and then only its first few senses (LSJ orders senses by primacy).
The full English sense apparatus is still shown in the entry, demoted to
a small reference block.

`scripts/bridge_lookup.py` is precision-first — it returns an Icelandic
candidate only when the sources give real evidence for it:
- a hard **evidence floor** (not just a soft down-weight), since a lone
  corpus-alignment artifact with a perfect score can otherwise outrank a
  well-attested word with a lower one, plus a gentle evidence bonus so
  near-ties break toward the better-attested candidate ("god": *guð*,
  48 hits, over *drottinn*, 22 hits);
- **part-of-speech constraints at two strengths**: the Greek headword's
  own POS (majority vote over its attested forms in `data/morph.db`) is a
  soft rerank hint, while LSJ's own grammar markers are a hard filter — a
  gloss written *"to bear"* is certainly a verb, so noun candidates like
  *bjarndýr* (the animal) are dropped outright and *bera* (carry) wins,
  no matter how lopsided the corpus scores are;
- a small curated **register table** for LSJ's most frequent gloss phrases
  where the modern-corpus ranking picks the wrong era's sense ("bring up"
  is rearing a child in a classical lexicon, not hoisting a thing);
- filtering of proper-noun/acronym/single-letter outliers, penalties for
  identity pairs (EN "ball" → IS "ball"), and lemmatization of English
  inflected forms so e.g. "eyes" inherits "eye"'s much better-attested
  translation.

When it isn't confident, it returns nothing rather than guessing. Two more
hard rules keep the output from regressing into pidgin:

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
Icelandic gloss**; the compiled dictionary always shows the English LSJ
shortdef and full sense list alongside, so nothing is silently hidden
behind a translation guess.

A shortdef that's just the first sense with an article glued on ("the
word" for λόγος, which has 63 senses spanning "speech", "account",
"reason", "ratio"...) is a lazy stub, not a real summary. When a terse
shortdef (≤2 phrases) sits next to a genuinely large sense inventory, the
builder additionally pulls from the *full* sense list — not just as a
fallback, but layered on top of the shortdef's words — and gets a larger
word budget (8 instead of 5): λόγος becomes *"tala, orð, málsháttur,
reikningur, útreikningur, líking, regla, fullyrðing"*. This widening is
deliberately narrow: it does NOT trigger just because an entry happens to
have many senses (most entries with no shortdef at all still use only the
first few senses — LSJ orders by primacy, and senses 10+ are
disproportionately rare/technical extensions that translate noisily in
isolation when yanked out of context).

Coverage, from the current build:
- 40.6% of entries: gloss built from LSJ's curated shortdef
- 13.7% of entries: gloss built from the first senses (no usable shortdef)
- 54.3% of entries: total with an Icelandic gloss
- 45.7% of entries: no confident translation at all (English-only fallback)

Coverage is lower than an earlier version of this project, on purpose —
that version reconstructed multi-word phrases and let low-evidence
candidates through, which covered more entries but with real grammatical
and semantic garbage mixed in throughout (see git history if curious what
that looked like). This version trades coverage for not lying to you.

**Use the Icelandic side as a fast way to recognize a Greek word's rough
meaning, not as a citable definition.** The English LSJ gloss alongside it
is the authoritative source.

### Duplicate headwords (accent/case variants of the same word)

LSJ's TEI-XML parsing produced many rows in `data/lsj.db` that are pure
duplicates of each other under a different accent placement or
capitalization — e.g. "logos" showed up as five separate rows (λόγος,
λογός, Λόγος, Λογός, Λογος) with byte-identical definitions text. That's
not five homonyms, it's one headword counted five times, and it made "Look
Up" show the same entry back-to-back repeatedly.

`scripts/build_xml.py` now groups rows by (accent-folded spelling, exact
definitions text) before writing entries — merging *across case* is
normally unsafe (capitalization can be the only thing distinguishing a
proper name from a common noun), but it's fine here specifically because
the merge key also requires the full definitions text to match exactly; a
genuine proper-noun/common-noun pair would have different definitions to
begin with and wouldn't merge. Morphology is unioned across every spelling
variant in a merged group, and the displayed headword is chosen by
checking which variant Morpheus (`data/morph.db`, an independent source)
actually has inflected forms recorded under — for the logos group, only
the correctly-accented "λόγος" had any (18 forms; the other four had zero),
which is a much better signal than an arbitrary alphabetical tie-break.
This merge alone cut 110,826 raw rows down to 49,828 actual entries.

### Icelandic morphology matched to Greek morphology

Beyond the gloss line, noun declension and verb principal-parts tables
render an Icelandic sub-line under each Greek form — the same word the
gloss uses, inflected to match. For ἵππος's dative singular ἵππῳ, the
table also shows *hesti(num)*: the indefinite form with the
definite-article suffix in parentheses. For λύω's principal parts —
every one a full 1st-person-singular sentence, since every captured
Greek form (the "1. p. et." in the table header) IS 1st singular and
Icelandic isn't pro-drop, so a bare "mun leysa" reads as an incomplete
fragment rather than a citation form: nútíð *"ég leysi / ég er að
leysa"*, framtíð *"ég mun leysa"*, þátíð (aorist) *"ég leysti"*, núliðin
tíð (perfect) *"ég hef leyst"*, þáliðin tíð (pluperfect) *"ég hafði
leyst"*, dvalarþátíð (imperfect) *"ég var að leysa"* — and Greek
subjunctive/optative forms (previously not shown at all — see below) get
a real BÍN-sourced Icelandic subjunctive form with the *(þótt)*
subordinator that governs it: *"(þótt) ég leysi"* labeled
viðtengingarháttur (nt.) for subjunctive, past-stem for optative, per the
classicist convention that Icelandic's single viðtengingarháttur splits
into a present-stem and past-stem form matching Greek's mood pair (Greek
doesn't distinguish tense within subjunctive/optative the way Icelandic
distinguishes present/past subjunctive, so this mapping ignores the
Greek form's own stem/tense and keys only on mood). The main-entry table
cites the 1st singular; the per-form stubs below carry every person and
number.

Getting the present tense right needed a real BÍN lookup, not the
infinitive: Icelandic present indicative genuinely differs by person
(leysa's infinitive is "leysa", but 1st singular present is "leysi", not
"leysa" — a naive `"ég " + infinitive` would have been wrong for most
verbs). Likewise the perfect uses hafa's own present tense, *"ég hef
leyst"*, not the infinitive *"ég hafa leyst"* (ungrammatical) — contrast
the future perfect *"ég mun hafa leyst"*, where hafa correctly stays
infinitival after the modal "mun". Every other auxiliary form (*var*,
*mun*, *hafði*) already happens to coincide between 1st and 3rd person
in Icelandic, so no extra lookup was needed for those.

This comes from BÍN (Beygingarlýsing íslensks nútímamáls / Database of
Modern Icelandic Inflection, CC BY-SA 4.0 — see CREDITS.md), not a
hand-built inflection engine: `scripts/build_is_morphology.py` extracts
declension tables for ~4,400 nouns and the **full finite paradigm**
(germynd + miðmynd × indicative + subjunctive × present + past × all three
persons × both numbers, plus supine and mediopassive infinitive) for
~1,230 verbs — every single-word Icelandic gloss this dictionary actually
produces — into `data/is_noun_declension.tsv` /
`data/is_verb_forms.tsv` (the latter in a long `lemma · slot · form`
format, ~59k rows). Only the case/number/verb-form combinations BÍN
actually has are shown; nothing is guessed. Two things are deliberately left blank rather than filled
with a guess:
- **Vocative** has no separate Icelandic case (address forms reuse the
  nominative), and **dual** doesn't exist in Icelandic at all — both
  columns stay empty on the Icelandic side.
- The definite-suffix parenthesis (`hesti(num)`) is only used when the
  definite form is a clean concatenation of the indefinite form plus a
  suffix; Icelandic's dative plural has an irregular assimilation
  (hest**um** + -num → hest**unum**, not hestum*num*), so that cell falls
  back to showing both forms in full (`hestum / hestunum`) instead of a
  parenthetical that would misstate the actual suffix.

Voice is modeled for all three Greek voices, plus Greek's own
present/imperfect/perfect/pluperfect middle-passive syncretism. Active →
germynd (the plain verb, e.g. λύω's perfect → *ég hef leyst*). Middle →
miðmynd, Icelandic's reflexive "-st" form (λύω's middle future λύσομαι →
*ég mun leysast*; middle aorist ἐλυσάμην → *ég leystist*) — BÍN doesn't
lemmatize "-st" verbs separately, "leysast" lives as MM-tagged rows inside
"leysa"'s own paradigm, so this is a real looked-up inflection, not
`is_word + "st"` string-glued. Passive → þolmynd, a genuinely periphrastic
"vera" + gender/number-agreeing past-participle construction with no
inflectional slot of its own (aorist ἐλύθην → *ég var leystur*; future
λυθήσομαι → *ég mun vera leystur*; perfect → *ég hef verið leystur*),
built from BÍN's participle paradigm (`LHÞT-SB-KK-*`), not guessed.

Greek's `middle/passive` tag (Morpheus's mark for a form it can't formally
distinguish) gets its own careful handling: on the genuinely syncretic
tenses — present, imperfect, perfect, pluperfect, and future perfect,
where Greek has one set of endings for both voices — it renders via the
ordinary miðmynd construction (λύομαι → *ég leysist*; perfect λέλυμαι →
*ég hef leyst*, the miðmynd supine). On aorist and plain future, where
Greek middle and passive are formally *different* forms and the ambiguous
tag reflects real parser uncertainty rather than syncretism, nothing is
rendered — picking either reading there would be a guess.

Every verb form's row (and stub) carries **two stacked grammatical tags**:
the classical/international parse of the Greek form in the abbreviations
every classicist reads (*ind. praes. act.*, *coni. aor. med.*) above the
Icelandic parse of the rendering (*frh. nt. gm.*, *vth. þt. mm.*) — they
diverge exactly where the mapping does (Greek *coni. aor.* → Icelandic
*vth. nt.*). Order for both is *[case. gender. person. number.] mood.
tense. voice.*

**Impersonal verbs** (oblique-subject / "quirky subject" verbs) are
handled specially. A verb like *dreyma* "dream" or *líka* "please" takes
its logical subject in an oblique case, not the nominative — *mig dreymir*
"I dream" (lit. "me dreams", accusative), *mér líkar* "I like" (dative) —
and the verb itself never agrees, staying 3rd-singular whatever the
subject. BÍN marks these with an `OP-{case}-…` tag prefix (`ÞF`
accusative, `ÞGF` dative, `EF` genitive, or `það` for weather-verb
expletives), so they're detected, not guessed: the oblique subject pronoun
carries the person/number (*mig/þig/hann·hana·það/okkur [oss]/…* accusative,
*mér/þér/honum·henni·því/…* dative) while the verb form is frozen at the
BÍN-sourced 3rd singular (*mig dreymir*, *þig dreymir*, *okkur [oss]
dreymir*; past *mig dreymdi*; subjunctive *(þótt) mig dreymi*). Only verbs
BÍN marks as unambiguously impersonal (in the relevant voice, with a
single subject case) get this treatment — a verb with any ordinary
personal paradigm (bera, draga, finna…) is left personal, since the
glossary almost always chose it for that sense. 24 pure impersonals are
primary glosses here; the `-st` experiencers (finnast, reynast, tapast)
aren't standalone BÍN lemmas and their base verbs carry a valid nominative
reading too, so they're deliberately left personal rather than
force-disambiguated.

### Inflected Greek forms get their own entry, linked back to the lemma

Looking up an inflected form (say ἵππῳ, ἵππος's dative singular) used to
just jump straight to ἵππος's full entry via a plain search-index alias —
useful, but with no indication of *which* form you'd actually found.
Every attested noun case-form and **every attested finite verb form —
all persons and numbers** — now gets a small standalone entry of its own:
the Icelandic rendering frontloaded (what the reader wants first, given
they already have the inflected form in hand), then — italicized — a
native Dictionary.app hyperlink back to the full lemma entry (the
`x-dictionary:r:` internal-reference scheme, resolved through Apple's own
reference-index build step) plus a single compact grammatical tag. Looking
up ἵππῳ shows:

> *dat. m. sg.*
> **hesti(num)** *— af* **ἵππος***, þgf. kk. et.*

and a verb form carries its full person/number rendering — παιδεύετε (2nd
plural present) →

> *2. pl. ind. praes. act.*
> **þið [þér] menntið / þið [þér] eruð að mennta** *— af* **παιδεύω***, 2. p. ft. frh. nt. gm.*

The tag is `[case. gender. person. number.] mood. tense. voice.`
(nt./frt./þt./nlt./dþt./þlt./þframt. for tense; frh./vth./nh./lh. for mood;
gm./mm./þm. for voice; kk./kvk./hk. for gender), with the classical parse
of the Greek form stacked above. The same format replaces the old verbose
row labels ("Nútíð – Germynd") in the main entry's declension/
principal-parts tables (headed **Kennimyndir**) too. The pronoun scheme (supplied by an
Icelandic classicist): 1sg *ég*, 2sg *þú*, 3sg *hann/hún/það*, 1pl *við
[vér]*, 2pl *þið [þér]*, 3pl *þeir/þær/þau (öll)*. Greek **dual** — which
Icelandic lost — reuses the plural verb form marked *(tvö)* (ἐπαιδευσάτην,
3rd dual → *þeir/þær/þau (tvö) menntuðu*); modern *við*/*þið* themselves
descend from the old duals, which is why they carry the marker rather than
a distinct word. A spelling attested for more than one Greek word (a
homonym collision) or more than one cell of the same word (a syncretic
form) merges into one stub listing every parsing, each with its own link.

Scoped to the finite paradigm (indicative + subjunctive/optative), noun/
adjective cases, and participles — not every raw Morpheus attestation
(infinitives etc. still resolve to the lemma via plain aliases). Stubs
total **~651k** on top of the 49,828 lemma entries; the compiled forward
bundle is ~660 MB. Looking up an *unaccented* inflected form (λειπωνται)
lands on its accented stub (λείπωνται), not the base lemma.

### Adjectives and participles

**Adjectives** decline for gender, so they're handled apart from nouns.
Morpheus tags Greek adjectives as multi-gender "nouns"; where the
Icelandic gloss is an adjective, it's normalized to its masculine citation
form (the bridge often stores the wrong gender — "good" → *gott* neuter,
normalized to *góður*) and then declined per the Greek form's own gender:
ἀγαθαί (fem nom pl) → **góðar**. BÍN's positive-strong paradigm supplies
the forms; the normalization is gated to genuinely adjectival entries so a
verb whose gloss word happens to also be an adjective form (mennta ↔ the
adjective menntur) is never mis-cast.

**Participles** are adjectival (case/gender/number) *and* verbal
(tense/voice), and render as a gender-agreeing participial phrase per an
Icelandic classicist's scheme: παιδεύων → *(hann/ég/þú) verandi að
mennta*; the perfect middle/passive masc pl → *(þeir/við/þið) verandi
orðnir menntaðir*; the aorist passive neut pl → *(þau/við/þið) hafandi
verið menntuð*. Present takes *verandi*, future *ætlandi*, aorist
*hafandi*, perfect *verandi*; the past participle agrees in gender/number
(menntaður/menntuð/menntað).

### Word category and preposition case government

Every entry shows its word category (Nafnorð/Sagnorð/Lýsingarorð/
Atviksorð/Fornafn/Greinir/Samtenging/Forsetning/Töluorð/Smáorð) right under
the headword, derived from the same part-of-speech signal already used to
decide how the entry renders. Note: this reflects Morpheus's own tagging,
which doesn't always match traditional school-grammar categories — e.g.
ἀλλά ("but") is tagged `adv` by Morpheus and so shows "Atviksorð", not
"Samtenging", even though most grammars call it a conjunction.

The ~20 most common prepositions also show their case government (Greek
case → closest-matching Icelandic preposition+case), hand-curated from
standard reference grammar since morphological analyzers don't tag
case-government on prepositions at all (a preposition doesn't itself
inflect). Scoped to the well-established core set only — rarer
poetic/dialectal prepositions are left unlabeled rather than guessed.

### The reverse direction (Icelandic → Greek) is coarser still

`scripts/build_reverse_xml.py` inverts the forward glossary: every word of
the concise gloss becomes a headword pointing back to the Greek word(s)
that produced it — including deliberate multiword units like "ala upp",
which are single glossary choices, not phrase fragments. Two things fall
out of this:
- Unlike the forward direction, entries here aren't grouped by matching
  definitions text (there isn't one definitions text per Icelandic
  headword to compare), so the safe cross-case merge above doesn't apply.
  `greek_normalize.dedup_accent_variants()` still folds pure accent-only
  duplicates (e.g. "hippos" with an acute, a grave, a circumflex, or no
  accent mark at all), but deliberately leaves breathing marks and
  capitalization alone, since both are genuinely meaningful in Greek
  (rough vs smooth breathing distinguishes real word pairs like
  "hóros"/boundary vs "óros"/mountain; capitalization distinguishes a
  proper name like Hippos from the common noun "hippos"/horse). So a
  lookup like "hestur" still returns a non-trivial cluster (ἵππος,
  ἱππικός, ἱππότης, Ἱππότης, Ἰππός, κόττος, ...) rather than one clean
  entry — the remaining spread is genuine distinct words/forms, not
  orthographic noise.
- No morphology tables in this direction — the headword is Icelandic, not
  Greek, so Morpheus declension data doesn't apply (same scope decision as
  `icelandic-nordic-dictionary-mac`'s reverse bundles).

## ✨ Features

* **110k LSJ entries**, glossed into Icelandic where the bridge is confident.
* **7,823 Icelandic headwords** in the reverse index.
* **System Integration:** works natively with macOS "Look Up".
* **Morphology tables** (forward direction only): noun declensions and verb
  principal parts, reused directly from `ancient-greek-mac`'s Morpheus data.
  Every label is in Icelandic: case/number for nouns (Nefnifall,
  Eignarfall, Þágufall, Þolfall, Ávarpsfall / Eintala, Tvítala, Fleirtala),
  and tense/voice/mood for verbs (Nútíð, Framtíð, Þátíð, Núliðin tíð,
  Dvalarþátíð, Þáliðin tíð, Þáframtíð / Germynd, Miðmynd, Þolmynd /
  Framsöguháttur, Viðtengingarháttur, Óskháttur, Boðháttur, Nafnháttur,
  Lýsingarháttur).
* **Icelandic-matched morphology:** noun/verb tables also show the
  Icelandic gloss word inflected to match each Greek form, as a full
  1st-person sentence (dative ἵππῳ → *hesti(num)*; λύω's perfect → *ég
  hef leyst*; middle voice → *leysast* forms), sourced from BÍN — see
  "Icelandic morphology matched to Greek morphology" above.
* **~651,000 inflected-form entries** (every noun/adjective case-form,
  every finite verb form in all persons/numbers, and every participle),
  each linking back to its lemma via Dictionary.app's native
  cross-reference hyperlinks — see "Inflected Greek forms get their own
  entry" above. The compiled forward bundle is ~660 MB as a result.
* **Transparency:** the English LSJ shortdef is always shown alongside the
  Icelandic gloss, with the full sense apparatus in a smaller reference
  block below it, so nothing is silently hidden behind a translation guess.

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
* `data/BIN_SHsnid.csv` (BÍN/DMII, "Sigrúnarsnið" CSV export, gitignored
  here) from CLARIN Iceland —
  https://repository.clarin.is/repository/xmlui/handle/20.500.12537/5

### Build steps

```bash
# 0. (Optional, only to regenerate data/wiktionary_en_is.tsv, which is
#    committed) Download the kaikki.org Wiktionary dump and extract pairs
curl -o data/kaikki-icelandic.jsonl \
    https://kaikki.org/dictionary/Icelandic/kaikki.org-dictionary-Icelandic.jsonl
python3 scripts/build_wiktionary_supplement.py

# 1. Build the Icelandic glossary from LSJ's English definitions (fast, ~2s)
python3 scripts/translate_definitions.py

# 2. (Optional, only to regenerate data/is_noun_declension.tsv and
#    data/is_verb_forms.tsv, which are committed) Extract Icelandic
#    morphology via the `islenska` package (BÍN data, nicer API than the
#    raw CSV) for every word this build's glossary actually produced --
#    must run AFTER step 1, since it reads data/lsj_is.db. Needs a venv:
#      python3 -m venv .venv && .venv/bin/pip install islenska
#      source .venv/bin/activate
python3 scripts/build_is_morphology.py

# 3. Generate both Apple Dictionary XML sources
python3 scripts/build_xml.py            # forward: Greek -> Icelandic
python3 scripts/build_reverse_xml.py    # reverse: Icelandic -> Greek

# 4. Compile and install both bundles
cd src && make install
```

Note: Apple's `build_dict.sh` validates plists against
`PropertyList-1.0.dtd` fetched from apple.com, whose served copy is
intermittently malformed and used to abort builds. `src/xml-catalog.xml`
(wired up via `XML_CATALOG_FILES` in the Makefile) now resolves that DTD
to the local system copy instead, so the build no longer touches the
network.

## 📁 Project Structure

```
ancient-greek-icelandic-mac/
├── data/
│   ├── lsj.db                  # LSJ entries + shortdefs [gitignored, from ancient-greek-mac]
│   ├── morph.db                # Morpheus morphology [gitignored, from ancient-greek-mac]
│   ├── IS-EN_glossary.tsv      # EN<->IS bridge glossary [gitignored, from CLARIN]
│   ├── wiktionary_en_is.tsv    # Curated EN->IS supplement [committed, from Wiktionary/kaikki.org]
│   ├── kaikki-icelandic.jsonl  # Raw Wiktionary dump [gitignored, redownload]
│   ├── BIN_SHsnid.csv          # Raw BÍN/DMII export [gitignored, from CLARIN]
│   ├── is_noun_declension.tsv  # Extracted Icelandic noun forms [committed, from BÍN]
│   ├── is_verb_forms.tsv       # Extracted Icelandic verb forms [committed, from BÍN]
│   └── lsj_is.db               # Generated Icelandic glossary [gitignored, regenerate]
├── scripts/
│   ├── bridge_lookup.py        # Precision-first EN->IS phrase/word lookup
│   ├── translate_definitions.py # Builds the concise Icelandic gloss per entry
│   ├── build_wiktionary_supplement.py # Extracts wiktionary_en_is.tsv from the kaikki dump
│   ├── build_is_morphology.py  # Extracts is_noun_declension.tsv / is_verb_forms.tsv from BÍN
│   ├── build_xml.py            # Forward direction: Greek -> Icelandic XML
│   └── build_reverse_xml.py    # Reverse direction: Icelandic -> Greek XML
├── src/
│   ├── GreekIcelandicDictionary.{xml,css,plist}      # forward bundle [xml gitignored]
│   ├── IcelandicGreekDictionary.{xml,plist}          # reverse bundle [xml gitignored]
│   ├── Makefile                # builds + installs both bundles
│   ├── xml-catalog.xml         # local DTD resolution (no network during build)
│   └── objects/                # Build artifacts [gitignored]
└── README.md
```

## 🤝 Contributing

* **Translation quality:** the biggest opportunity. The register table in
  `scripts/bridge_lookup.py` (`_CLASSICAL_OVERRIDES_*`) is deliberately
  small — if you spot a common LSJ gloss phrase that lands on the wrong
  Icelandic sense, adding a verified pair there is a one-line fix.
* **Coverage:** ~46% of entries still have no confident Icelandic gloss.
  Morphology coverage is narrower still: of the ~7,000 distinct single-word
  glosses this dictionary produces, BÍN has declension data for ~4,400 of
  the nouns and verb-form data for ~1,230 of the verbs (multi-word glosses
  like "ala upp" don't get a morphology table at all — see "Icelandic
  morphology matched to Greek morphology").
  Additional open EN→IS (or even direct Grc→IS) word lists that could be
  merged as supplements — the same way `data/wiktionary_en_is.tsv` was —
  are very welcome.
* **Weird/broken entries:** same caveat as `ancient-greek-mac` — 110k
  auto-generated entries will have edge cases.

**Not in scope:** LSJ headwords/definitions and morphology data themselves
are maintained upstream (Chicago Digital Classics / Perseids) — report
issues with the *source* English gloss there, not here.

## 📚 Data Sources

See [CREDITS.md](CREDITS.md) for full attribution.

* **LSJ Lexicon & Morphology:** same sources as `ancient-greek-mac`.
* **Bridge glossary:** CLARIN Iceland, English-Icelandic/Icelandic-English glossary 21.09.
* **Wiktionary supplement:** English Wiktionary via kaikki.org/wiktextract (CC BY-SA).
* **Icelandic morphology:** BÍN/DMII, CLARIN Iceland, compiled by Kristín Bjarnadóttir (CC BY-SA 4.0).

## 📄 License

Dual-license, same structure as `ancient-greek-mac`: code under MIT, data
under CC BY-SA 4.0 (LSJ) / CC BY 4.0 (glossary) / CC BY-SA 4.0 (this
project's generated Icelandic glossary and reverse index, since they derive
from CC BY-SA LSJ text). See [LICENSE](LICENSE) for full details.
