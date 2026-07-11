# Credits

This project builds an Ancient Greek <-> Icelandic dictionary (both
directions) by bridging two independent resources: an English lexicon of
Ancient Greek, and a bilingual English-Icelandic glossary. No direct Ancient
Greek-Icelandic dictionary exists, so every gloss here is a **precision-first
word/phrase-substitution bridge translation** -- a glossary of confident
equivalents, not idiomatic Icelandic prose written by a lexicographer or
translated by a language model. The reverse (Icelandic -> Greek) direction is
inverted from the same generated glossary. See "How this works" in
README.md.

## Ancient Greek Lexicon (LSJ)

Liddell-Scott-Jones (LSJ) Ancient Greek lexicon, via the Chicago Digital
Classics / Perseus Digital Library TEI-XML edition.
License: CC BY-SA 4.0.
Same source data as the companion [`ancient-greek-mac`](https://github.com/Josolon/ancient-greek-mac)
project -- see that repo for full sourcing detail.

## Morphology

Ancient Greek inflectional morphology (noun declensions, verb principal
parts) from Morpheus, via the Perseids project. Same source as
`ancient-greek-mac`.

## English-Icelandic Bridge Glossary

English-Icelandic/Icelandic-English glossary 21.09.
Compiled by Steinþór Steingrímsson, Luke James Obrien, Finnur Ágúst
Ingimundarson, Árni Davíð Magnússon, Þórdís Dröfn Andrésdóttir, and Inga
Guðrún Eiríksdóttir -- The Árni Magnússon Institute for Icelandic Studies /
Reykjavik University, via CLARIN Iceland.
License: CC BY 4.0.
https://repository.clarin.is/repository/xmlui/handle/20.500.12537/144

This is the same glossary used (in the opposite lookup direction) by the
companion [`icelandic-english-dictionary-mac`](https://github.com/Josolon/icelandic-english-dictionary-mac)
project.

## Wiktionary Supplement

Supplementary English -> Icelandic pairs (`data/wiktionary_en_is.tsv`)
extracted from the Icelandic entries of the English Wiktionary, via the
[kaikki.org](https://kaikki.org/dictionary/Icelandic/) machine-readable
dictionaries built with [wiktextract](https://github.com/tatuylonen/wiktextract):
Tatu Ylonen, *Wiktextract: Wiktionary as Machine-Readable Structured
Data*, Proceedings of the 13th Conference on Language Resources and
Evaluation (LREC), pp. 1317-1325, Marseille, 20-25 June 2022.
Wiktionary content license: Creative Commons CC BY-SA and GFDL (dual).
https://en.wiktionary.org/

## Icelandic Morphology (BÍN)

Beygingarlýsing íslensks nútímamáls (BÍN) / Database of Modern Icelandic
Inflection (DMII), "Sigrúnarsnið" CSV export.
Compiled by Kristín Bjarnadóttir -- The Árni Magnússon Institute for
Icelandic Studies, via CLARIN Iceland.
License: CC BY-SA 4.0.
https://repository.clarin.is/repository/xmlui/handle/20.500.12537/5
https://bin.arnastofnun.is/

Used to render an Icelandic-inflected form (declension for nouns, tense/
mood periphrasis for verbs) alongside each Greek morphological form in the
forward dictionary's declension and principal-parts tables -- see "How
this works" in README.md. Only extracted for the small set of Icelandic
words this dictionary's own generated glossary actually produces
(`data/is_noun_declension.tsv`, `data/is_verb_forms.tsv`), not the full
~300,000-lemma database.

## Tooling

Bridge-translation and Apple Dictionary build pipeline in this repository:
Jónatan Sólon. Adapted from the build pipeline of `ancient-greek-mac`.

## License Reminder

Always keep this CREDITS.md and the per-source attribution intact when
sharing anything derived from this repository. The compiled `.dictionary`
bundle is a derivative of CC BY-SA (LSJ), CC BY (glossary), CC BY-SA
(Wiktionary), and CC BY-SA (BÍN) sources -- see LICENSE for how those
terms combine.
