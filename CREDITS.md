# Credits

This project builds an Ancient Greek -> Icelandic dictionary by bridging two
independent resources: an English lexicon of Ancient Greek, and a bilingual
English-Icelandic glossary. No direct Ancient Greek-Icelandic dictionary
exists, so every gloss here is a **word/phrase-substitution bridge
translation**, not idiomatic Icelandic prose written by a lexicographer or
translated by a language model. See "How translation works" in README.md.

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

## Tooling

Bridge-translation and Apple Dictionary build pipeline in this repository:
Jónatan Sólon. Adapted from the build pipeline of `ancient-greek-mac`.

## License Reminder

Always keep this CREDITS.md and the per-source attribution intact when
sharing anything derived from this repository. The compiled `.dictionary`
bundle is a derivative of CC BY-SA (LSJ) and CC BY (glossary) sources -- see
LICENSE for how those terms combine.
