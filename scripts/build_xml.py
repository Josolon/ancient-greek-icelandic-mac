"""Builds the Apple Dictionary XML for the Ancient Greek -> Icelandic bridge
dictionary. Headwords and morphology come from ancient-greek-mac's LSJ/Morpheus
databases (data/lsj.db, data/morph.db); Icelandic glosses come from
data/lsj_is.db, produced by translate_definitions.py.

Adapted from ancient-greek-mac/scripts/build_xml.py -- see that project for
the original English-only version this is derived from.

LSJ's TEI-XML parsing produced many rows in data/lsj.db that are pure
duplicates of each other under a different accent placement or
capitalization -- e.g. logos/logos/Logos/Logos, five rows, byte-identical
definitions text. This isn't homonyms sharing a spelling, it's the same
headword counted multiple times, and it made "Look Up" show the same entry
4-5 times in a row. Rows are grouped by (accent-folded, case-folded
spelling, exact definitions text) before writing entries -- merging across
case is normally unsafe (see greek_normalize.py), but is fine here because
the merge key requires the full definitions text to match exactly, which
rules out conflating a real proper-noun/common-noun pair (those would have
different definitions rows to begin with). Morphology is unioned across
every spelling variant in a group, since Morpheus is keyed by exact string
and different variants can carry different attested inflected forms.
"""
import sqlite3
import html
import os
import re
import unicodedata
import json
from collections import defaultdict

from greek_normalize import accent_key, pick_representative

LSJ_DB_PATH = 'data/lsj.db'
MORPH_DB_PATH = 'data/morph.db'
IS_DB_PATH = 'data/lsj_is.db'
NOUN_DECL_PATH = 'data/is_noun_declension.tsv'
VERB_FORMS_PATH = 'data/is_verb_forms.tsv'
ADJ_DECL_PATH = 'data/is_adj_declension.tsv'
ADJ_LEMMA_PATH = 'data/is_adj_form_lemma.tsv'
OUTPUT_XML_PATH = 'src/GreekIcelandicDictionary.xml'

PRINCIPAL_PARTS_ORDER = [
    ('present', 'active'), ('present', 'middle'), ('present', 'passive'),
    ('future', 'active'),  ('future', 'middle'),
    ('aorist', 'active'),  ('aorist', 'middle'),
    ('perfect', 'active'),
    ('perfect', 'middle'), ('perfect', 'passive'),
    ('aorist', 'passive'),
]
PRINCIPAL_PARTS_PRIMARY = frozenset(PRINCIPAL_PARTS_ORDER)

# Standard Icelandic grammatical terms, as supplied by the user (an
# Icelandic classicist) for tense/voice/mood, plus everyday Icelandic
# school terms for case/number/gender/part-of-speech.
CASE_LABELS_IS = {
    'nominative': 'Nefnifall', 'genitive': 'Eignarfall',
    'dative': 'Þágufall', 'accusative': 'Þolfall', 'vocative': 'Ávarpsfall',
}
NUMBER_LABELS_IS = {'singular': 'Eintala', 'dual': 'Tvítala', 'plural': 'Fleirtala'}
GENDER_LABELS_IS = {'masculine': 'Karlkyn', 'feminine': 'Kvenkyn', 'neuter': 'Hvorugkyn'}
TENSE_LABELS_IS = {
    'present': 'Nútíð', 'future': 'Framtíð', 'aorist': 'Þátíð',
    'perfect': 'Núliðin tíð', 'imperfect': 'Dvalarþátíð',
    'pluperfect': 'Þáliðin tíð', 'future perfect': 'Þáframtíð',
}
VOICE_LABELS_IS = {
    'active': 'Germynd', 'middle': 'Miðmynd', 'passive': 'Þolmynd',
    'middle/passive': 'Miðmynd/þolmynd',
}
MOOD_LABELS_IS = {
    'indicative': 'Framsöguháttur', 'subjunctive': 'Viðtengingarháttur',
    'optative': 'Óskháttur', 'imperative': 'Boðháttur',
    'infinitive': 'Nafnháttur', 'participle': 'Lýsingarháttur',
}
PERSON_LABELS_IS = {'1st': '1. persóna', '2nd': '2. persóna', '3rd': '3. persóna'}
POS_LABELS_IS = {
    'noun': 'Nafnorð', 'verb': 'Sagnorð', 'participle': 'Lýsingarháttur',
    'adv': 'Atviksorð', 'particle': 'Smáorð', 'conj': 'Samtenging',
    'prep': 'Forsetning', 'numeral': 'Töluorð',
}

# Word-category label shown right under the headword. Morpheus tags Greek
# adjectives, articles, and pronouns all as pos='noun' (see adjectival_entry
# in the main loop), so this needs the SAME multi-gender heuristic to tell
# "Lýsingarorð" apart from plain "Nafnorð" -- POS_LABELS_IS alone can't
# distinguish them. Priority order matters: is_verb wins over pos_kinds
# (Greek deponent-looking entries can carry a stray noun-tagged homonym
# row), adjectival_entry (multi-gender) wins over a bare 'noun' tag, and an
# explicit article/pronoun tag wins over the generic noun fallback.
_WORD_CATEGORY_POS_IS = {
    'article': 'Greinir', 'pronoun': 'Fornafn', 'adv': 'Atviksorð',
    'particle': 'Smáorð', 'conj': 'Samtenging', 'prep': 'Forsetning',
    'numeral': 'Töluorð',
}


# Case government for the ~20 most common Ancient Greek prepositions,
# hand-curated (standard reference-grammar content -- e.g. Smyth's Greek
# Grammar SS1685ff -- NOT derivable from morph.db, which doesn't tag
# case-government on preposition rows at all: a preposition itself doesn't
# inflect, so its object's case never gets attached back to the
# preposition's own lemma rows). Deliberately scoped to the well-established
# core set rather than all 49 attested lemmas in morph.db -- the rarer
# poetic/dialectal ones (νόσφι, ἄτερ, καταντικρύ, ...) are exactly where a
# hand-curated fact is most likely to be wrong without a grammar open next
# to it, so they're left unlabeled rather than guessed. Each entry is
# (greek_case_or_cases, one Icelandic preposition per Greek case, chosen
# for the CLOSEST matching sense -- Greek's single preposition often splits
# across senses that Icelandic itself case-marks differently, e.g. Greek
# ἐν "in" (dat) vs εἰς "into" (acc) mirrors Icelandic "í" itself governing
# þgf. for location vs þf. for motion-into). Spot-check before publishing;
# this reflects standard grammar-reference case government, not an
# independently re-verified table.
PREP_CASE_GOVERNANCE = {
    'ἀμφί':  [('genitive', 'um (viðvíkjandi)'), ('dative', 'við'), ('accusative', 'um, kringum')],
    'ἀνά':   [('accusative', 'upp eftir, um')],
    'ἀντί':  [('genitive', 'í stað, í staðinn fyrir')],
    'ἀπό':   [('genitive', 'frá')],
    'διά':   [('genitive', 'í gegnum'), ('accusative', 'vegna')],
    'εἰς':   [('accusative', 'í, til (hreyfing)')],
    'ἐς':    [('accusative', 'í, til (hreyfing)')],
    'ἐκ':    [('genitive', 'úr, frá')],
    'ἐξ':    [('genitive', 'úr, frá')],
    'ἐν':    [('dative', 'í, á (kyrrstaða)')],
    'ἐπί':   [('genitive', 'á, í tíð'), ('dative', 'við, á grundvelli'), ('accusative', 'að, upp á')],
    'κατά':  [('genitive', 'niður frá, gegn'), ('accusative', 'eftir, samkvæmt')],
    'μετά':  [('genitive', 'með'), ('accusative', 'eftir (tíma)')],
    'παρά':  [('genitive', 'frá'), ('dative', 'hjá'), ('accusative', 'til hliðar við, þvert á')],
    'περί':  [('genitive', 'um, viðvíkjandi'), ('accusative', 'um, kringum')],
    'πρό':   [('genitive', 'á undan, fyrir framan')],
    'πρός':  [('genitive', 'frá'), ('dative', 'hjá, auk'), ('accusative', 'til, gegn')],
    'σύν':   [('dative', 'með')],
    'ὑπέρ':  [('genitive', 'yfir, fyrir hönd'), ('accusative', 'yfir (mörk)')],
    'ὑπό':   [('genitive', 'af (gerandi þolmyndar)'), ('accusative', 'undir (hreyfing)')],
}


def _word_category_is(is_verb, adjectival_entry, pos_kinds):
    if is_verb:
        return 'Sagnorð'
    if adjectival_entry:
        return 'Lýsingarorð'
    for pos, label in _WORD_CATEGORY_POS_IS.items():
        if pos in pos_kinds:
            return label
    if 'noun' in pos_kinds:
        return 'Nafnorð'
    if 'participle' in pos_kinds:
        return 'Lýsingarháttur'
    return None


def _tense_voice_label(tense, voice):
    t = TENSE_LABELS_IS.get(str(tense).lower(), str(tense).capitalize())
    v = VOICE_LABELS_IS.get(str(voice).lower(), str(voice).capitalize())
    return f"{t} – {v}"


# Compact grammatical tags. Every inflected form carries TWO parallel
# parses: the classical/international one (the "Latin" markers, in the
# convention every classicist already reads -- "3. sg. coni. aor. med.")
# describing the GREEK form, shown above the Icelandic one describing the
# Icelandic rendering. Canonical order for both, per the user:
#   case. gender. person. number. mood. tense. voice.
# (case/gender for nominals, person for finite verbs -- mutually exclusive;
# mood BEFORE tense). Fields absent from a given form are omitted.
_CLASSICAL_ABBR = {
    'case': {'nominative': 'nom.', 'genitive': 'gen.', 'dative': 'dat.',
             'accusative': 'acc.', 'vocative': 'voc.'},
    'gender': {'masculine': 'masc.', 'feminine': 'fem.', 'neuter': 'neut.'},
    'person': {'1st': '1.', '2nd': '2.', '3rd': '3.'},
    'number': {'singular': 'sg.', 'plural': 'pl.', 'dual': 'du.'},
    'mood': {'indicative': 'ind.', 'subjunctive': 'coni.', 'optative': 'opt.',
             'imperative': 'imp.', 'infinitive': 'inf.', 'participle': 'part.'},
    'tense': {'present': 'praes.', 'future': 'fut.', 'aorist': 'aor.',
              'perfect': 'perf.', 'imperfect': 'imperf.', 'pluperfect': 'plqp.',
              'future perfect': 'futp.'},
    'voice': {'active': 'act.', 'middle': 'med.', 'passive': 'pass.',
              'middle/passive': 'medpass.'},
    'degree': {'comparative': 'comp.', 'superlative': 'superl.'},
}
_ICELANDIC_ABBR = {
    'case': {'nominative': 'nf.', 'genitive': 'ef.', 'dative': 'þgf.',
             'accusative': 'þf.', 'vocative': 'áf.'},
    'gender': {'masculine': 'kk.', 'feminine': 'kvk.', 'neuter': 'hk.'},
    'person': {'1st': '1. p.', '2nd': '2. p.', '3rd': '3. p.'},
    'number': {'singular': 'et.', 'plural': 'ft.', 'dual': 'tvít.'},
    'mood': {'indicative': 'frh.', 'subjunctive': 'vth.', 'optative': 'vth.',
             'imperative': 'bh.', 'infinitive': 'nh.', 'participle': 'lh.'},
    'tense': {'present': 'nt.', 'future': 'frt.', 'aorist': 'þt.',
              'perfect': 'nlt.', 'imperfect': 'dþt.', 'pluperfect': 'þlt.',
              'future perfect': 'þframt.'},
    'voice': {'active': 'gm.', 'middle': 'mm.', 'passive': 'þm.',
              'middle/passive': 'mm./þm.'},
    'degree': {'comparative': 'mst.', 'superlative': 'est.'},
}


_PN_PERSONS = frozenset(('1st', '2nd', '3rd'))
_PN_NUMBERS = frozenset(('singular', 'plural', 'dual'))


def _grammar_tag(scheme, case=None, gender=None, person=None, number=None,
                 mood=None, tense=None, voice=None, fuse_subj=False, degree=None):
    """One space-joined grammar tag in the given abbreviation `scheme`
    (_CLASSICAL_ABBR or _ICELANDIC_ABBR), canonical field order. When
    fuse_subj is set (the Icelandic parse only), a Greek subjunctive/
    optative collapses to Icelandic viðtengingarháttur with its mapped
    present/past marker (Greek doesn't distinguish tense within those
    moods the way the Icelandic target does) -- the classical parse keeps
    the real Greek mood+tense (coni./opt. + aor. etc.)."""
    def ab(cat, val):
        return scheme[cat].get(str(val).lower(), str(val).lower())
    parts = []
    if case:
        parts.append(ab('case', case))
    if gender:
        parts.append(ab('gender', gender))
    # Positive degree is the unmarked default (never labeled, same as an
    # unmarked active voice would be for a verb whose voice is obvious) --
    # only comparative/superlative are ever worth calling out.
    if degree in ('comparative', 'superlative'):
        parts.append(ab('degree', degree))
    if person:
        parts.append(ab('person', person))
    if number:
        parts.append(ab('number', number))
    ml = str(mood).lower() if mood else None
    if fuse_subj and ml in MOOD_TENSE_FUSION_IS:
        parts.append(ab('mood', 'subjunctive'))
        _, subj_tense = MOOD_TENSE_FUSION_IS[ml]
        parts.append(ab('tense', 'present' if subj_tense == 'pres' else 'aorist'))
    else:
        if ml:
            parts.append(ab('mood', ml))
        if tense:
            parts.append(ab('tense', tense))
    if voice:
        parts.append(ab('voice', voice))
    return ' '.join(parts)


def _dual_tag(**kw):
    """(classical_tag, icelandic_tag) for one form's parse. The Icelandic
    one fuses subjunctive/optative; the classical one doesn't."""
    classical = _grammar_tag(_CLASSICAL_ABBR, **kw)
    icelandic = _grammar_tag(_ICELANDIC_ABBR, fuse_subj=True, **kw)
    return classical, icelandic


def _tag_label_html(classical, icelandic):
    """Two stacked italic tag lines for a morphology-table row label:
    classical (Greek parse) above, Icelandic (rendering parse) below."""
    return (f'<i class="tag-cl">{html.escape(classical, quote=False)}</i>'
            f'<br/><i class="tag-is">{html.escape(icelandic, quote=False)}</i>')


# Greek subjunctive and optative don't map onto separate Icelandic moods --
# Icelandic only has one viðtengingarháttur, which itself splits into a
# present-stem and a past-stem form. Comparative-grammar convention (per an
# Icelandic classicist) collapses Greek's mood pair onto that split
# regardless of the Greek form's own stem/tense (aorist subjunctive and
# present subjunctive are both "non-past, non-indicative" in Greek's
# aspectual system, with no Icelandic equivalent distinction): Greek
# subjunctive -> Icelandic present subjunctive, Greek optative -> Icelandic
# past subjunctive. The value is the (display label, verb-slot tense) pair;
# person/number are filled in per form.
MOOD_TENSE_FUSION_IS = {
    'subjunctive': ('Viðtengingarháttur (nt.)', 'pres'),
    'optative': ('Viðtengingarháttur (þt.)', 'past'),
}

# Greek subjunctive/optative render as Icelandic viðtengingarháttur, which
# an Icelandic subordinator governs -- "(þótt) ég mennti" reads as a real
# subjunctive clause ("though I educate") rather than a bare stranded form.
_SUBJ_PREFIX = '(þótt) '

# Icelandic has no case that vocative maps to as a distinct inflected
# form (address forms just reuse the nominative) and no grammatical dual
# at all -- vocative is left blank, and Greek dual reuses the Icelandic
# plural verb form (marked in the pronoun, see PRONOUNS_IS).
#
# Subject pronouns, keyed by (Greek person, Greek number). Icelandic isn't
# pro-drop, so every rendering is a full "pronoun + verb" clause. Per the
# user (an Icelandic classicist): 3rd person shows all genders; plural adds
# the archaic true-plural pronoun in brackets (1st/2nd) or "(öll)" (3rd,
# which has no archaic contrast); dual -- which Icelandic lost -- reuses the
# plural verb form, marked "(tvö)" (modern við/þið themselves descend from
# the old duals, hence they carry the marker rather than a distinct word).
PRONOUNS_IS = {
    ('1st', 'singular'): 'ég',
    ('2nd', 'singular'): 'þú',
    ('3rd', 'singular'): 'hann/hún/það',
    ('1st', 'plural'): 'við [vér]',
    ('2nd', 'plural'): 'þið [þér]',
    ('3rd', 'plural'): 'þeir/þær/þau (öll)',
    ('1st', 'dual'): 'við (tvö)',
    ('2nd', 'dual'): 'þið (tvö)',
    ('3rd', 'dual'): 'þeir/þær/þau (tvö)',
}

# Oblique subject pronouns for impersonal verbs ("mig langar", "mér
# finnst"): the logical subject stands in the accusative (þf), dative
# (þgf), or genitive (ef), and the verb form itself stays 3rd-singular
# invariant (see below). Same person/number/gender scheme as PRONOUNS_IS,
# in the oblique case: 3rd person shows all genders, dual reuses the plural
# marked "(tvö)", and 1st/2nd plural carry the archaic oblique pronoun in
# brackets (oss/yður acc-dat, vor/yðar gen) exactly as the nominative
# scheme carries [vér]/[þér] -- both to mark plurality (vs the "(tvö)"
# dual) and for parallelism. Per the user (an Icelandic classicist).
OBLIQUE_PRONOUNS_IS = {
    'þf': {
        ('1st', 'singular'): 'mig',
        ('2nd', 'singular'): 'þig',
        ('3rd', 'singular'): 'hann/hana/það',
        ('1st', 'plural'): 'okkur [oss]',
        ('2nd', 'plural'): 'ykkur [yður]',
        ('3rd', 'plural'): 'þá/þær/þau (öll)',
        ('1st', 'dual'): 'okkur (tvö)',
        ('2nd', 'dual'): 'ykkur (tvö)',
        ('3rd', 'dual'): 'þá/þær/þau (tvö)',
    },
    'þgf': {
        ('1st', 'singular'): 'mér',
        ('2nd', 'singular'): 'þér',
        ('3rd', 'singular'): 'honum/henni/því',
        ('1st', 'plural'): 'okkur [oss]',
        ('2nd', 'plural'): 'ykkur [yður]',
        ('3rd', 'plural'): 'þeim (öll)',
        ('1st', 'dual'): 'okkur (tvö)',
        ('2nd', 'dual'): 'ykkur (tvö)',
        ('3rd', 'dual'): 'þeim (tvö)',
    },
    'ef': {
        ('1st', 'singular'): 'mín',
        ('2nd', 'singular'): 'þín',
        ('3rd', 'singular'): 'hans/hennar/þess',
        ('1st', 'plural'): 'okkar [vor]',
        ('2nd', 'plural'): 'ykkar [yðar]',
        ('3rd', 'plural'): 'þeirra (öll)',
        ('1st', 'dual'): 'okkar (tvö)',
        ('2nd', 'dual'): 'ykkar (tvö)',
        ('3rd', 'dual'): 'þeirra (tvö)',
    },
}
# Expletive-subject impersonals (weather verbs etc.): a fixed dummy "það".
_EXPLETIVE_SUBJECT = 'það'

# Greek dual has no Icelandic verb form of its own -> agree with the plural.
_AGREEMENT_NUMBER = {'singular': 'sg', 'plural': 'pl', 'dual': 'pl'}
# morph.db person string -> the digit BÍN slot keys use (gm_ind_pres_2sg).
_PERSON_DIGIT = {'1st': '1', '2nd': '2', '3rd': '3'}

# Auxiliary paradigms, hardcoded (vera/hafa/munu are closed-class; their
# forms are invariant across the language). Keyed by (person, agreement-
# number). BÍN-verified. hafa has two present-tense uses: as the finite
# perfect auxiliary it takes its own present ("ég hef leyst"), but after the
# modal "mun" (future perfect) it stays infinitival ("ég mun hafa leyst").
_AUX = {
    'vera_pres': {('1st', 'sg'): 'er', ('2nd', 'sg'): 'ert', ('3rd', 'sg'): 'er',
                  ('1st', 'pl'): 'erum', ('2nd', 'pl'): 'eruð', ('3rd', 'pl'): 'eru'},
    'vera_past': {('1st', 'sg'): 'var', ('2nd', 'sg'): 'varst', ('3rd', 'sg'): 'var',
                  ('1st', 'pl'): 'vorum', ('2nd', 'pl'): 'voruð', ('3rd', 'pl'): 'voru'},
    'munu_pres': {('1st', 'sg'): 'mun', ('2nd', 'sg'): 'munt', ('3rd', 'sg'): 'mun',
                  ('1st', 'pl'): 'munum', ('2nd', 'pl'): 'munuð', ('3rd', 'pl'): 'munu'},
    'hafa_pres': {('1st', 'sg'): 'hef', ('2nd', 'sg'): 'hefur', ('3rd', 'sg'): 'hefur',
                  ('1st', 'pl'): 'höfum', ('2nd', 'pl'): 'hafið', ('3rd', 'pl'): 'hafa'},
    'hafa_past': {('1st', 'sg'): 'hafði', ('2nd', 'sg'): 'hafðir', ('3rd', 'sg'): 'hafði',
                  ('1st', 'pl'): 'höfðum', ('2nd', 'pl'): 'höfðuð', ('3rd', 'pl'): 'höfðu'},
}
_AUX_HAFA_INF = 'hafa'


# Greek's three voices don't map 1:1 onto Icelandic's inflectional system:
# active -> germynd (the plain verb), middle -> miðmynd (the -st form, e.g.
# leysa -> leysast). Passive has no synthetic Icelandic counterpart at
# all -- þolmynd is a "vera" + gender/number-agreeing past-participle
# construction, handled separately (_passive_periphrasis) since it doesn't
# use verb_slots' finite gm_/mm_ paradigm at all, only the participle.
_VOICE_TO_BUCKET = {'active': 'gm', 'middle': 'mm'}

# Tenses where Greek's middle and passive voices are genuinely, formally
# identical -- present/imperfect/perfect/pluperfect share one set of
# endings for both, and so does the future perfect (πεπαιδεύσομαι serves
# both). Morpheus's voice='middle/passive' tag on these is a real statement
# about Greek's own morphology, and they all render via the ordinary
# miðmynd construction. The SAME tag on aorist/plain-future (where Greek
# middle and passive ARE formally distinct, e.g. λύσομαι vs λυθήσομαι)
# instead reflects genuine parser uncertainty between two different,
# non-interchangeable forms -- rendering either reading would be a
# coin-flip guess, so those render nothing.
_SYNCRETIC_MP_TENSES = {'present', 'imperfect', 'perfect', 'pluperfect', 'future perfect'}


def _passive_periphrasis(tense, mood, person, number, verb_slots):
    """Þolmynd (passive): "vera" + a gender/number-agreeing past
    participle -- no Icelandic voice has a synthetic passive, so this is
    always periphrastic. The subject's gender isn't known from the Greek
    form (every person-marked rendering in this dictionary is gender-
    neutral, "ég/þú/hann-hún-það"), so the participle shows all three
    gender forms slash-joined (menntaður/menntuð/menntað), same as the
    3rd-person pronoun itself already does (PRONOUNS_IS: "hann/hún/það") --
    showing only the masculine would silently disagree with a fem./neut.
    subject. Number still agrees with the subject (Greek dual -> plural,
    per _AGREEMENT_NUMBER). Icelandic's past passive doesn't separately
    mark Greek's aorist/imperfect aspect distinction, so both use "var" +
    participle. Only indicative is rendered -- no subjunctive passive
    pattern was specified."""
    if mood != 'indicative':
        return None
    pron = PRONOUNS_IS.get((person, number))
    agr = _AGREEMENT_NUMBER.get(number)
    if not pron or not agr:
        return None
    pn = (person, agr)
    ptcp_forms = [verb_slots.get(_PTCP_SLOT[(g, agr)])
                  for g in ('masculine', 'feminine', 'neuter')]
    if not all(ptcp_forms):
        return None
    ptcp = "/".join(ptcp_forms)
    if tense == 'present':
        return f"{pron} {_AUX['vera_pres'][pn]} {ptcp}"
    if tense in ('aorist', 'imperfect'):
        return f"{pron} {_AUX['vera_past'][pn]} {ptcp}"
    if tense == 'future':
        return f"{pron} {_AUX['munu_pres'][pn]} vera {ptcp}"
    if tense == 'perfect':
        return f"{pron} {_AUX['hafa_pres'][pn]} verið {ptcp}"
    if tense == 'pluperfect':
        return f"{pron} {_AUX['hafa_past'][pn]} verið {ptcp}"
    if tense == 'future perfect':
        return f"{pron} {_AUX['munu_pres'][pn]} hafa verið {ptcp}"
    return None


# Participle rendering machinery. A Greek participle is adjectival (case/
# gender/number) AND verbal (tense/voice), so the Icelandic renders as a
# participial phrase agreeing in gender/number: a "who could this be"
# pronoun hint in parens, then the phrase. The past participle (ptcp_*
# slots) and "orðinn" (verða's past participle) both agree in gender+number
# (nominative); Greek dual agrees with the plural.
_PTCP_SLOT = {
    ('masculine', 'sg'): 'ptcp_nom_sg', ('feminine', 'sg'): 'ptcp_kvk_sg',
    ('neuter', 'sg'): 'ptcp_hk_sg', ('masculine', 'pl'): 'ptcp_nom_pl',
    ('feminine', 'pl'): 'ptcp_kvk_pl', ('neuter', 'pl'): 'ptcp_hk_pl',
}
_ORDINN = {
    ('masculine', 'sg'): 'orðinn', ('feminine', 'sg'): 'orðin', ('neuter', 'sg'): 'orðið',
    ('masculine', 'pl'): 'orðnir', ('feminine', 'pl'): 'orðnar', ('neuter', 'pl'): 'orðin',
}
_PTCP_PRONOUN = {
    ('masculine', 'sg'): 'hann', ('feminine', 'sg'): 'hún', ('neuter', 'sg'): 'það',
    ('masculine', 'pl'): 'þeir', ('feminine', 'pl'): 'þær', ('neuter', 'pl'): 'þau',
}


def _participle_periphrasis(gender, number, tense, voice, is_word, verb_slots):
    """Icelandic rendering of a Greek participle (per the classicist's
    scheme): a gender/number pronoun hint plus a participial phrase.
    Present -> "verandi", future -> "ætlandi", aorist -> "hafandi",
    perfect -> "verandi"; the active takes an infinitive/supine, the
    middle its -st counterpart, the passive a "vera/verið"+participle, and
    the syncretic perfect middle/passive an "orðinn"+participle. Genuinely
    ambiguous voice/tense cells (aorist & future middle/passive, where
    Greek's middle and passive participles are formally different) render
    nothing rather than guess."""
    gl = str(gender).lower()
    agr = _AGREEMENT_NUMBER.get(number)
    if agr is None or (gl, agr) not in _PTCP_PRONOUN:
        return None
    tense = str(tense).lower()
    voice = str(voice).lower()

    pron_prefix = f"({_PTCP_PRONOUN[(gl, agr)]}/{'ég/þú' if agr == 'sg' else 'við/þið'})"
    ppp = verb_slots.get(_PTCP_SLOT[(gl, agr)])
    gm_inf = is_word
    mm_inf = verb_slots.get('mm_inf')
    gm_sup = verb_slots.get('gm_supine')
    mm_sup = verb_slots.get('mm_supine')
    ordinn = _ORDINN[(gl, agr)]

    phrase = None
    if tense == 'present':
        if voice == 'active':
            phrase = f"verandi að {gm_inf}" if gm_inf else None
        else:  # middle / passive / middle-passive all syncretic in present
            phrase = f"verandi að vera {ppp}" if ppp else None
    elif tense == 'future':
        if voice == 'active':
            phrase = f"ætlandi að {gm_inf}" if gm_inf else None
        elif voice == 'middle':
            phrase = f"ætlandi að {mm_inf}" if mm_inf else None
        elif voice == 'passive':
            phrase = f"ætlandi að vera {ppp}" if ppp else None
        # future middle/passive: distinct forms, ambiguous -> None
    elif tense == 'aorist':
        if voice == 'active':
            phrase = f"hafandi {gm_sup}" if gm_sup else None
        elif voice == 'middle':
            phrase = f"hafandi {mm_sup}" if mm_sup else None
        elif voice == 'passive':
            phrase = f"hafandi verið {ppp}" if ppp else None
        # aorist middle/passive: distinct forms, ambiguous -> None
    elif tense == 'perfect':
        if voice == 'active':
            phrase = f"verandi {ppp}" if ppp else None
        else:  # perfect middle/passive is syncretic in Greek
            phrase = f"verandi {ordinn} {ppp}" if ppp else None

    return f"{pron_prefix} {phrase}" if phrase else None


def _icelandic_periphrasis(tense, voice, mood, person, number, is_word, verb_slots):
    """The Icelandic rendering for one Greek verb form's full parsing
    (tense, voice, mood, person, number), as a complete pronoun+verb clause
    since Icelandic isn't pro-drop. Person/number pick the pronoun
    (PRONOUNS_IS) and select which cell of the BÍN-sourced paradigm
    (verb_slots) and auxiliary paradigm (_AUX) to use; Greek dual has no
    Icelandic verb form so it agrees with the plural (_AGREEMENT_NUMBER).

    Voice: active -> germynd (gm_ slots, germynd infinitive = is_word),
    middle -> miðmynd (mm_ slots, mm_inf infinitive), passive -> þolmynd
    (_passive_periphrasis, a separate "vera" + participle construction).
    middle/passive (Morpheus's tag for Greek's own genuinely syncretic
    present/imperfect/perfect/pluperfect/future-perfect voices) routes to
    the ordinary miðmynd construction (perfect → "ég hef leyst/menntast",
    the -st supine, not a distinct passive form); on aorist/plain-future,
    where the tag reflects genuine parser ambiguity between two formally
    different forms rather than true syncretism, it renders nothing.

    Mood: indicative renders the classicist's tense mapping (present
    "PRON X / PRON er að INF", future "PRON mun INF", aorist = simple past,
    imperfect "PRON var að INF", perfect "PRON hef SUPINE", pluperfect
    "PRON hafði SUPINE", future-perfect "PRON mun hafa SUPINE").
    Subjunctive/optative render Icelandic present/past viðtengingarháttur
    with the "(þótt)" subordinator (see MOOD_TENSE_FUSION_IS, _SUBJ_PREFIX).

    Returns None when voice has no Icelandic mapping, or the specific
    BÍN cell needed isn't attested, rather than fabricating a form.
    """
    tense = str(tense).lower()
    mood = str(mood).lower()
    voice_l = str(voice).lower()

    if voice_l == 'passive':
        return _passive_periphrasis(tense, mood, person, number, verb_slots)
    if voice_l == 'middle/passive':
        if tense not in _SYNCRETIC_MP_TENSES:
            return None
        return _icelandic_periphrasis(tense, 'middle', mood, person, number, is_word, verb_slots)

    bucket = _VOICE_TO_BUCKET.get(voice_l)
    if bucket is None:
        return None

    # Impersonal verbs (mig langar, mér finnst) take an oblique subject and
    # an invariant 3sg verb form -- a wholly different clause shape, handled
    # separately.
    subj_case = verb_slots.get(f'__subj_{bucket}')
    if subj_case:
        return _impersonal_periphrasis(tense, mood, person, number, bucket,
                                       subj_case, is_word, verb_slots)

    pron = PRONOUNS_IS.get((person, number))
    agr = _AGREEMENT_NUMBER.get(number)
    pdigit = _PERSON_DIGIT.get(person)
    if not pron or not agr or not pdigit:
        return None
    pn = (person, agr)

    def slot(mood_key, tense_key):
        # Slot keys number the person 1/2/3 (BÍN's tag digits), not the
        # morph.db strings 1st/2nd/3rd -- hence pdigit, not person.
        return verb_slots.get(f"{bucket}_{mood_key}_{tense_key}_{pdigit}{agr}")

    infinitive = is_word if bucket == 'gm' else verb_slots.get('mm_inf')
    supine = verb_slots.get(f'{bucket}_supine')

    if mood in MOOD_TENSE_FUSION_IS:
        _, subj_tense = MOOD_TENSE_FUSION_IS[mood]
        form = slot('subj', subj_tense)
        return f"{_SUBJ_PREFIX}{pron} {form}" if form else None

    if mood != 'indicative':
        return None

    if tense == 'present':
        pres = slot('ind', 'pres')
        if not pres:
            return None
        clause = f"{pron} {pres}"
        if infinitive:
            clause += f" / {pron} {_AUX['vera_pres'][pn]} að {infinitive}"
        return clause
    if tense == 'future':
        return f"{pron} {_AUX['munu_pres'][pn]} {infinitive}" if infinitive else None
    if tense == 'imperfect':
        return f"{pron} {_AUX['vera_past'][pn]} að {infinitive}" if infinitive else None
    if tense == 'aorist':
        past = slot('ind', 'past')
        return f"{pron} {past}" if past else None
    if tense == 'perfect':
        return f"{pron} {_AUX['hafa_pres'][pn]} {supine}" if supine else None
    if tense == 'pluperfect':
        return f"{pron} {_AUX['hafa_past'][pn]} {supine}" if supine else None
    if tense == 'future perfect':
        return f"{pron} {_AUX['munu_pres'][pn]} {_AUX_HAFA_INF} {supine}" if supine else None
    return None


# Impersonal verbs are always 3rd-singular, whatever the oblique subject's
# person/number -- so the verb form, and every auxiliary, is looked up at
# 3sg. And the progressive "vera að + infinitive" (which needs a nominative
# subject) is dropped: the simple synthetic form alone carries the present.
_IMPERSONAL_PN = ('3rd', 'sg')


def _impersonal_periphrasis(tense, mood, person, number, bucket, subj_case, is_word, verb_slots):
    """Icelandic rendering for an impersonal verb: an oblique-case subject
    pronoun (accusative "mig", dative "mér", genitive "mín", or the
    expletive "það") plus the invariant 3rd-singular verb form. The logical
    subject's person/number only chooses the oblique pronoun; the verb
    never agrees."""
    if subj_case == _EXPLETIVE_SUBJECT:
        pron = _EXPLETIVE_SUBJECT
    else:
        table = OBLIQUE_PRONOUNS_IS.get(subj_case)
        pron = table.get((person, number)) if table else None
    if not pron:
        return None

    pn = _IMPERSONAL_PN

    def slot(mood_key, tense_key):
        return verb_slots.get(f"{bucket}_{mood_key}_{tense_key}_3sg")

    infinitive = is_word if bucket == 'gm' else verb_slots.get('mm_inf')
    supine = verb_slots.get(f'{bucket}_supine')

    if mood in MOOD_TENSE_FUSION_IS:
        _, subj_tense = MOOD_TENSE_FUSION_IS[mood]
        form = slot('subj', subj_tense)
        return f"{_SUBJ_PREFIX}{pron} {form}" if form else None
    if mood != 'indicative':
        return None

    if tense == 'present':
        pres = slot('ind', 'pres')
        return f"{pron} {pres}" if pres else None
    if tense == 'future':
        return f"{pron} {_AUX['munu_pres'][pn]} {infinitive}" if infinitive else None
    # imperfect has no separate impersonal form (no progressive) -> the
    # plain past stands in for both it and the aorist.
    if tense in ('aorist', 'imperfect'):
        past = slot('ind', 'past')
        return f"{pron} {past}" if past else None
    if tense == 'perfect':
        return f"{pron} {_AUX['hafa_pres'][pn]} {supine}" if supine else None
    if tense == 'pluperfect':
        return f"{pron} {_AUX['hafa_past'][pn]} {supine}" if supine else None
    if tense == 'future perfect':
        return f"{pron} {_AUX['munu_pres'][pn]} {_AUX_HAFA_INF} {supine}" if supine else None
    return None


def _is_definite_suffix_form(indef, definite):
    """Format as 'indef(suffix)' when the definite form is a straightforward
    suffixed extension of the indefinite one -- the regular Icelandic
    pattern (hestur "hestur" + "inn" -> "hesturinn"). Falls back to showing
    both forms separated by " / " for the irregular minority where the
    definite form isn't a clean suffix (internal stem changes etc.),
    rather than fabricating a misleading parenthetical."""
    if not indef:
        return definite
    if not definite:
        return indef
    if definite.startswith(indef):
        suffix = definite[len(indef):]
        return f"{indef}({suffix})" if suffix else indef
    return f"{indef} / {definite}"


def _primary_gloss_word(gloss_is):
    """The first single-word token of the Icelandic gloss -- the word this
    dictionary inflects for the morphology tables. A multi-word phrase
    ("ala upp") is skipped in favor of the next word in the gloss, not
    treated as a dead end -- paideuo's gloss is "ala upp, mennta, kenna",
    and stopping at the first (multi-word) entry silently disabled
    morphology rendering for the whole entry even though "mennta" right
    next to it inflects fine. None only when NO word in the gloss is a
    single token."""
    if not gloss_is:
        return None
    for word in gloss_is.split(","):
        word = word.strip()
        if word and " " not in word:
            return word
    return None


def load_is_noun_declension():
    data = defaultdict(dict)
    if not os.path.exists(NOUN_DECL_PATH):
        return data
    with open(NOUN_DECL_PATH, encoding='utf-8') as f:
        for line in f:
            parts = line.rstrip('\n').split('\t')
            if len(parts) != 5:
                continue
            lemma, case_name, number, indef, definite = parts
            data[lemma][(case_name, number)] = (indef, definite)
    return data


def load_is_verb_forms():
    """Long-format data/is_verb_forms.tsv (lemma, slot, form) ->
    {lemma: {slot: form}}. Slots are keys like 'gm_ind_pres_2sg',
    'mm_supine', 'mm_inf' -- see build_is_morphology.py."""
    data = defaultdict(dict)
    if not os.path.exists(VERB_FORMS_PATH):
        return data
    with open(VERB_FORMS_PATH, encoding='utf-8') as f:
        for line in f:
            parts = line.rstrip('\n').split('\t')
            if len(parts) != 3:
                continue
            lemma, slot, form = parts
            data[lemma][slot] = form
    return data


def load_is_adj_declension():
    """data/is_adj_declension.tsv (lemma, degree, case, gender, number,
    form) -> {lemma: {(degree, case, gender, number): form}} -- strong
    declension in all three degrees (positive/comparative/superlative;
    see build_is_morphology.py's parse_adj_slot)."""
    data = defaultdict(dict)
    if not os.path.exists(ADJ_DECL_PATH):
        return data
    with open(ADJ_DECL_PATH, encoding='utf-8') as f:
        for line in f:
            parts = line.rstrip('\n').split('\t')
            if len(parts) != 6:
                continue
            lemma, degree, case_name, gender, number, form = parts
            data[lemma][(degree, case_name, gender, number)] = form
    return data


def load_is_adj_form_lemma():
    """data/is_adj_form_lemma.tsv (form, lemma) -> {form: lemma}. Maps an
    adjective gloss word that's an inflected form (gott) to its masculine
    citation lemma (góður)."""
    data = {}
    if not os.path.exists(ADJ_LEMMA_PATH):
        return data
    with open(ADJ_LEMMA_PATH, encoding='utf-8') as f:
        for line in f:
            parts = line.rstrip('\n').split('\t')
            if len(parts) == 2:
                data[parts[0]] = parts[1]
    return data


def sanitize_apple_key(text):
    if not text:
        return ""
    kw = text.strip()
    kw = unicodedata.normalize('NFC', kw)
    while kw and not unicodedata.category(kw[0]).startswith(('L', 'N')):
        kw = kw[1:]
    return kw


# Reconstructed-classical Greek pronunciation, each symbol anchored to an
# Icelandic word carrying the same sound -- Icelandic keeps phonemic vowel
# length, unaspirated/aspirated stop pairs, and a rolled r that English
# lacks, so it's a far more precise anchor for a reconstructed classical
# pronunciation than English examples are. The Icelandic-anchor column is
# exactly as the user wrote it, including spelling, since it records a
# specific personal pronunciation judgment that isn't ours to rephrase or
# "correct"; the IPA column is added for cross-reference. gg is omitted --
# same sound as "g before k,ch,g,m" above it, already covered there.
_PRONUNCIATION_VOWELS = [
    ("ᾰ", "/a/", "a í aska (stutt)"),
    ("ᾱ", "/aː/", "a í aka (langt)"),
    ("ᾳ", "/aːi/", "a-æ í ha-æ (ýkt langt a)"),
    ("αι", "/ai/", "æ í bækur"),
    ("αυ", "/au/", "á í hár"),
    ("āυ", "/aːu/", "a-á í ha-á (ýkt langt a)"),
    ("ε", "/e/", "e í e. pet (lokað, stutt)"),
    ("ει", "/eː/", "e í þ. Weg (lokað, langt)"),
    ("ει á undan sérhljóða", "/ej/", "eyj í eyja."),
    ("ευ", "/eu/", "e-ú / \"e-u\" (stutt lokað e yfir í stutt ú)"),
    ("η", "/ɛː/", "e í vegur (opið)"),
    ("ῃ", "/ɛːi/", "e-ey í le-eysa (ýkt langt opið e)"),
    ("ηυ", "/ɛːu/", "e-ú í \"le-úsa\" (langt opið e yfir í stutt ú)"),
    ("ῐ", "/i/", "í í ískra (stutt)"),
    ("ῑ", "/iː/", "ý í nýta (langt)"),
    ("ο", "/o/", "o í þ. Gott (lokað, stutt)"),
    ("οι", "/oi/", "<i>au</i> í haust (eða <i>og</i> í bogi)"),
    ("ου", "/uː/", "ú í núna (langt)"),
    ("υ", "/y/", "u í undra (stutt)"),
    ("ῡ", "/yː/", "u í muna (langt)"),
    ("υι", "/yi/", "ug í hugi"),
    ("ω", "/ɔː/", "o í nota"),
    ("ῳ", "/ɔːi/", "og í bogi (ýkt langt opið o)"),
    ("ωυ", "/ɔːu/", "ó í ól (langt)"),
]
_PRONUNCIATION_CONSONANTS = [
    ("῾", "/h/", "h í hestur"),
    ("β", "/b/", "b í e. bad"),
    ("ββ", "/bː/", "bb í fr. subboréal, ít. babbo"),
    ("γ", "/ɡ/", "g í fr. garçon (raddað)"),
    ("γ á undan κ, χ, γ, ξ, μ", "/ŋ/", "n í langur"),
    ("δ", "/d/", "d í fr. deux"),
    ("ζ", "/zd/", "<i>st</i> í staður (þó raddað: <i>zd</i>; sbr. e. wisdom)"),
    ("θ", "/tʰ/", "t í töf"),
    ("κ", "/k/", "g í gæti"),
    ("λ", "/l/", "l í sæla"),
    ("λλ", "/lː/", "ll í karamella"),
    ("μ", "/m/", "m í mæla"),
    ("μμ", "/mː/", "mm í gammur"),
    ("ν", "/n/", "n í næla"),
    ("ξ", "/ks/", "x í lax"),
    ("π", "/p/", "b í bera"),
    ("ππ", "/pː/", "bb í gabba"),
    ("ρ", "/r/", "r í vor (raddað)"),
    ("ῥ", "/r̥/", "hr í hringur (óraddað)"),
    ("ῤῥ", "/rr̥/", "<i>rhr</i> í vorhringur; lengt <i>rg</i> í margt"),
    ("σ/ς", "/s/", "s í sofa (óraddað)"),
    ("σ/ς á undan röddun (β, γ, δ, μ)", "/z/", "z í e. zone (raddað)"),
    ("σσ", "/sː/", "ss í hissa"),
    ("τ", "/t/", "d í döf"),
    ("ττ", "/tː/", "dd í saddur"),
    ("φ", "/pʰ/", "p í pera"),
    ("χ", "/kʰ/", "k í kæti"),
    ("ψ", "/ps/", "ps í taps(ins)"),
]

# The Icelandic-anchor column follows a "LETTER í WORD" convention --
# italicize only that leading letter (once, at the start of the string),
# not every "í" that appears later in a parenthetical aside (e.g. "...ha
# yfir í hæ", where that "í" is just the Icelandic preposition, not
# another anchor-letter demonstration).
_LEADING_ANCHOR_RE = re.compile(r'^(\S+) í ')


def _render_anchor_html(text):
    # A row that demonstrates more than one anchor letter (e.g. "au í
    # haust (eða og í bogi)") is pre-authored with its own <i> markup
    # rather than run through the single-leading-token auto-italicizer.
    if '<i>' in text:
        return text
    m = _LEADING_ANCHOR_RE.match(text)
    if not m:
        return html.escape(text, quote=False)
    lead = html.escape(m.group(1), quote=False)
    rest = html.escape(text[m.end():], quote=False)
    return f'<i>{lead}</i> í {rest}'


def write_pronunciation_guide_entry(xml):
    """A hand-authored reference entry (not derived from LSJ/BÍN) mapping
    reconstructed-classical Greek pronunciation onto Icelandic anchor
    words -- see _PRONUNCIATION_VOWELS/_PRONUNCIATION_CONSONANTS above."""
    entry_id = "pronunciation_guide"
    title = "Framburður forngrísku"
    xml.write(f'    <d:entry id="{entry_id}" d:title="{html.escape(title)}">\n')
    for keyword in (title, "framburður", "framburður forngrísku",
                    "íslenskur framburður forngrísku", "pronunciation",
                    "pronunciation guide", "frambur"):
        xml.write(f'        <d:index d:value="{html.escape(keyword)}"/>\n')
    xml.write(f'        <h1 class="entry-lemma">{html.escape(title)}</h1>\n')
    xml.write('        <p class="entry-preamble">Handbók fyrir íslenskumælandi</p>\n')
    xml.write('        <div class="definition">\n')
    xml.write(
        '            <p class="gloss-is">Attískur fimmtu aldar (f. Kr.) framburður. Gefin '
        'eru framburðardæmi á íslensku þar sem hægt er. Röddun skortir í íslensku en með '
        'þekkingu á ensku eða frönsku má framkalla hana. Þá eru stuttu e- og o-hljóðin '
        'frábrugðin þeim íslensku en aftur má leita til ensku eða þýsku.</p>\n')

    def _write_table(heading, rows):
        xml.write('            <div class="morph-section">\n')
        xml.write(f'                <p class="morph-label">{html.escape(heading)}</p>\n')
        xml.write('                <table class="morphology-table">\n')
        xml.write('                    <tr><th>Tákn</th><th>IPA</th>'
                   '<th>Íslensk hjálpardæmi</th></tr>\n')
        for symbol, ipa, anchor in rows:
            xml.write(
                f'                    <tr><td class="case-label">{html.escape(symbol, quote=False)}</td>'
                f'<td>{html.escape(ipa, quote=False)}</td>'
                f'<td>{_render_anchor_html(anchor)}</td></tr>\n')
        xml.write('                </table>\n')
        xml.write('            </div>\n')

    _write_table("Sérhljóð og tvíhljóð", _PRONUNCIATION_VOWELS)
    _write_table("Samhljóð", _PRONUNCIATION_CONSONANTS)
    xml.write('        </div>\n')
    xml.write('    </d:entry>\n\n')


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
    is_cursor.execute("SELECT id, gloss_is, shortdef_en FROM definitions_is")
    is_by_id = {row[0]: (row[1], row[2]) for row in is_cursor.fetchall()}

    print("Loading Icelandic noun declension / verb form / adjective tables (BÍN)...")
    noun_declension = load_is_noun_declension()
    verb_forms = load_is_verb_forms()
    adj_declension = load_is_adj_declension()
    adj_form_lemma = load_is_adj_form_lemma()

    with open(OUTPUT_XML_PATH, 'w', encoding='utf-8') as xml:
        xml.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        xml.write('<d:dictionary xmlns="http://www.w3.org/1999/xhtml" xmlns:d="http://www.apple.com/DTDs/DictionaryService-1.0.rng">\n\n')

        print("Fetching LSJ entries...")
        lsj_cursor.execute("SELECT id, lemma, lemma_normalized, definitions FROM definitions")
        rows = lsj_cursor.fetchall()
        print(f"Found {len(rows)} raw rows. Grouping accent/case duplicates...")

        groups = defaultdict(list)
        for rid, lemma, lemma_norm, defs in rows:
            groups[(accent_key(lemma).lower(), defs)].append((rid, lemma, lemma_norm))

        # LSJ's TEI source sometimes produces a corrupted duplicate headword
        # that is missing its word-initial breathing mark entirely -- e.g.
        # "άγαθός" (bare accented alpha) alongside the real "ἀγαθός" (smooth
        # breathing). Every Greek word-initial vowel must carry breathing
        # (smooth or rough), so a bare one is never a genuine spelling, just
        # noise -- confirmed here by BYTE-IDENTICAL definitions text against
        # the properly-breathed entry (an 11-way fan-out of ἀγαθός/ἄγαθος/
        # ἁγαθός/Ἀγαθός/άγαθός/... variants, all sharing the same 178-char
        # defs, was found this way). Drop the breathing-less duplicate when a
        # defs-identical, properly-breathed sibling exists; scoped strictly
        # to the WORD-INITIAL position, so it can never touch a legitimate
        # mid-word crasis coronis (which looks like a smooth-breathing sign
        # but marks vowel elision between two words, not a missing initial
        # breathing -- a real, meaningful mark this must not strip).
        def _missing_initial_breathing(lemma):
            # Must run on the ORIGINAL spelling, not an accent_key()-folded
            # one -- accent_key already NFD-decomposes, which splits a
            # precomposed breathing+letter character (e.g. "ἀ") into two
            # separate string elements, so lemma[0] alone would no longer
            # see the breathing mark.
            if not lemma:
                return False
            decomp = unicodedata.normalize("NFD", lemma)
            base = decomp[0]
            if base not in "αεηιουωΑΕΗΙΟΥΩ":
                return False
            # Only the breathing mark immediately following the initial
            # vowel counts -- not one anywhere in the word (which could be a
            # legitimate mid-word crasis coronis).
            return not (len(decomp) > 1 and decomp[1] in ("̓", "̔"))

        defs_to_keys = defaultdict(list)
        for key in groups:
            defs_to_keys[key[1]].append(key)
        for defs, keys in defs_to_keys.items():
            if len(keys) < 2:
                continue
            good = [k for k in keys if not _missing_initial_breathing(groups[k][0][1])]
            bad = [k for k in keys if _missing_initial_breathing(groups[k][0][1])]
            if good and bad:
                for bk in bad:
                    del groups[bk]

        entries = list(groups.items())

        total_entries = len(entries)
        print(f"Merged into {total_entries} entries "
              f"({len(rows) - total_entries} duplicate rows folded in). Building structures...")

        def pick_representative_lemma(members):
            """Prefer whichever spelling variant Morpheus (data/morph.db, an
            independent source) actually has inflected forms recorded under
            -- e.g. for the logos/logos/Logos/Logos group, only 'logos'
            (paroxytone) has any morph.db rows (18 of them); the other 4
            spellings have none. That's real evidence for which spelling is
            the standard citation form, unlike an alphabetical tie-break
            (which for this exact group would have picked the oxytone
            'logos' misaccentuation just because its accented vowel sorts
            earlier in Unicode). Falls back to accent/case-based selection
            when no variant has any morph.db attestation."""
            distinct = {m[1] for m in members}
            if len(distinct) > 1:
                counts = {}
                for lemma in distinct:
                    morph_cursor.execute("SELECT COUNT(*) FROM morphology WHERE lemma = ?", (lemma,))
                    counts[lemma] = morph_cursor.fetchone()[0]
                best_count = max(counts.values())
                if best_count > 0:
                    distinct = {l for l, c in counts.items() if c == best_count}
            return pick_representative(distinct)

        # Looking up an inflected Greek form (e.g. hesti -> hippoi) currently
        # just jumps straight to the lemma's full entry via the d:index
        # aliases below -- useful, but it doesn't say *which* form you
        # found. form_stub_candidates accumulates, across every lemma in
        # this pass, one small stub-entry candidate per distinct attested
        # spelling that differs from its lemma's own citation form: its
        # grammatical parsing (in Icelandic) plus the specific Icelandic
        # periphrasis/case-form already computed for that cell, if any.
        # Deliberately scoped to the same CURATED cells already rendered in
        # the declension/principal-parts tables (not all of morph.db's raw
        # attestations, which would be orders of magnitude larger). Emitted
        # as their own d:entry blocks after the main loop, since the same
        # spelling can be attested for more than one lemma (homonyms) and
        # needs merging into a single stub listing all of them.
        # raw_form -> list of (lemma_title, lemma_entry_id, classical_tag,
        # icelandic_tag, rendering). Accent-variant folding (below) picks one
        # canonical accented spelling per normalized form.
        form_stub_candidates = defaultdict(list)
        # normalized (accent-stripped) spelling -> the accented spelling
        # chosen to own its stub, so an unaccented lookup lands on the
        # accented form's own stub rather than the base lemma.
        form_norm_to_accented = {}

        def register_stub(raw_form, lemma_title, lemma_entry_id, tags, is_rendering):
            if not raw_form or raw_form == lemma_title:
                return
            classical_tag, icelandic_tag = tags
            form_stub_candidates[raw_form].append(
                (lemma_title, lemma_entry_id, classical_tag, icelandic_tag, is_rendering))
            # Remember which accented spelling to route the unaccented form
            # to; prefer a spelling that actually carries accents.
            norm = accent_key(raw_form)
            if norm and norm != raw_form:
                cur = form_norm_to_accented.get(norm)
                if cur is None or (cur == accent_key(cur) and raw_form != accent_key(raw_form)):
                    form_norm_to_accented[norm] = raw_form

        for index, ((_, raw_def_en), members) in enumerate(entries):
            representative_lemma = pick_representative_lemma(members)
            representative_id = next(rid for rid, lemma, _ in members if lemma == representative_lemma)
            entry_id = f"lsj_{representative_id}"

            gloss_is, shortdef_en = is_by_id.get(representative_id, (None, None))

            safe_title = sanitize_apple_key(representative_lemma)
            if not safe_title:
                safe_title = "unknown"

            xml.write(f'    <d:entry id="{entry_id}" d:title="{html.escape(safe_title)}">\n')
            search_indices = set()
            for _, lemma, lemma_norm in members:
                search_indices.add(lemma)
                search_indices.add(lemma_norm)

            morph_rows = []
            for _, lemma, _ in members:
                morph_cursor.execute("""
                    SELECT form, form_normalized, pos, tense, voice, mood, person, number, case_name, gender, degree
                    FROM morphology WHERE lemma = ?
                """, (lemma,))
                morph_rows.extend(morph_cursor.fetchall())

            is_verb = False
            is_noun_adj = False
            # Every distinct Morpheus `pos` value attested for this lemma,
            # for the word-category label (Nafnorð/Sagnorð/...) -- kept
            # separate from is_verb/is_noun_adj, which merge several pos
            # values (noun/adjective/article/pronoun) into one boolean.
            pos_kinds = set()
            # 4D noun/adjective grid, keyed (degree, case, gender, number)
            # -> forms. degree is 'positive' for every noun (Morpheus's
            # degree column is only ever populated for adjectives) and for
            # an adjective's own positive-degree forms; comparative/
            # superlative Greek forms get their own degree key so they
            # never collapse into the same cell (and same Icelandic
            # rendering) as the positive form.
            noun_grid = defaultdict(set)
            noun_grid_raw = defaultdict(set)
            noun_genders = set()
            adj_degrees = set()
            verb_principal_parts = defaultdict(set)
            verb_secondary_moods = defaultdict(set)
            # raw_form -> set of (tense, voice, mood, person, number) parsings,
            # for every finite (indicative/subjunctive/optative) verb form.
            # This is the basis for the per-inflected-form stub entries, which
            # (unlike the main-entry tables, which cite only the 1st singular)
            # cover every person/number the Greek verb actually attests.
            verb_finite_forms = defaultdict(set)
            # raw_form -> set of (case, gender, number, tense, voice) parsings.
            participle_forms = defaultdict(set)
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
                gender = mr[9]
                degree = str(mr[10]).lower() if mr[10] else 'positive'

                # Only the exact accented inflected form indexes the main
                # (lemma) entry directly -- NOT its accent-stripped
                # normalization. Every inflected form also gets its own stub
                # entry below, and the stub mechanism (form_norm_to_accented)
                # is what an unaccented search should resolve through, so it
                # lands on the accented form's OWN stub (e.g. an unaccented
                # search for "πεπαιδευμεναι" should reach the
                # "πεπαιδευμέναι" stub) rather than jumping straight to the
                # lemma, which claiming the unaccented spelling here would
                # cause.
                search_indices.add(raw_form)

                display_form = html.escape(raw_form, quote=False)

                if pos:
                    pos_kinds.add(str(pos).lower())

                if pos == 'verb':
                    is_verb = True
                    ml = str(mood).lower()
                    # Main-entry tables cite the 1st singular only (standard
                    # lexicographic convention): principal parts from the
                    # indicative, a separate mood block from subj/optative.
                    if person == '1st' and number == 'singular' and ml == 'indicative':
                        verb_principal_parts[(str(tense).lower(), str(voice).lower())].add(display_form)
                    elif person == '1st' and number == 'singular' and ml in MOOD_TENSE_FUSION_IS:
                        verb_secondary_moods[ml].add(display_form)
                    # Stubs, by contrast, cover every attested finite form
                    # (all persons/numbers) -- capture the full parsing here.
                    if ml in ('indicative',) or ml in MOOD_TENSE_FUSION_IS:
                        if person in _PN_PERSONS and number in _PN_NUMBERS:
                            verb_finite_forms[raw_form].add(
                                (str(tense).lower(), str(voice).lower(), ml, person, number))

                elif pos == 'participle':
                    # Participles inflect like adjectives (case/gender/number)
                    # AND carry verbal tense/voice -- rendered by their own
                    # hybrid scheme (_participle_periphrasis). Captured for
                    # stubs only (no main-entry participle table).
                    if case_name and number and gender:
                        participle_forms[raw_form].add(
                            (case_name, gender, number, str(tense).lower(), str(voice).lower()))

                elif pos in ('noun', 'adjective', 'article', 'pronoun'):
                    is_noun_adj = True
                    if case_name and number and gender:
                        # 4D grid [degree][case][gender][number]: a Greek
                        # noun has one gender, but a Greek adjective (also
                        # tagged 'noun' by Morpheus) spans all three, and
                        # the Icelandic gloss word -- if it's an adjective
                        # -- must agree per gender AND per degree (a
                        # comparative/superlative Greek form must never
                        # share a cell, or an Icelandic rendering, with the
                        # positive form of the same case/gender/number).
                        noun_grid[(degree, case_name, gender, number)].add(display_form)
                        noun_grid_raw[(degree, case_name, gender, number)].add(raw_form)
                        noun_genders.add(str(gender).lower())
                        if degree != 'positive':
                            adj_degrees.add(degree)

                else:
                    parsing_elements = []
                    if pos:
                        parsing_elements.append(POS_LABELS_IS.get(str(pos).lower(), str(pos).capitalize()))
                    if tense:
                        parsing_elements.append(TENSE_LABELS_IS.get(str(tense).lower(), str(tense).capitalize()))
                    if voice:
                        parsing_elements.append(VOICE_LABELS_IS.get(str(voice).lower(), str(voice).capitalize()))
                    if mood:
                        parsing_elements.append(MOOD_LABELS_IS.get(str(mood).lower(), str(mood).capitalize()))
                    if person:
                        parsing_elements.append(PERSON_LABELS_IS.get(person, str(person)))
                    if number:
                        parsing_elements.append(NUMBER_LABELS_IS.get(number, str(number).capitalize()))
                    if case_name:
                        parsing_elements.append(CASE_LABELS_IS.get(case_name, str(case_name).capitalize()))
                    if gender:
                        parsing_elements.append(GENDER_LABELS_IS.get(str(gender).lower(), str(gender).capitalize()))
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
                        return "; ".join(html.escape(d, quote=False) for d in json.loads(raw_json))
                    return html.escape(raw_json, quote=False)
                except (json.JSONDecodeError, AttributeError):
                    return html.escape(str(raw_json), quote=False)

            clean_definition_en = render_defs(raw_def_en)

            # Adjective glosses come out of the bridge in whatever gender the
            # English->Icelandic glossary happened to store ("good" -> "gott",
            # neuter), but an adjective's citation form is the masculine
            # nominative singular ("góður"), and that's what BÍN keys its
            # declension on -- so normalize each adjective gloss word to its
            # lemma. Only for a genuinely adjectival Greek entry (Morpheus
            # tags Greek adjectives as multi-gender 'noun's) and NEVER for a
            # word that's itself a verb lemma: "mennta" is a form of the
            # adjective "menntur" AND the verb "to educate", and a verb entry
            # (παιδεύω) means the verb -- normalizing it to "menntur" would
            # wrongly turn the whole entry adjectival.
            adjectival_entry = is_noun_adj and not is_verb and len(noun_genders) >= 2
            if gloss_is and adjectival_entry:
                def _norm_adj(w):
                    w = w.strip()
                    if " " in w or w in verb_forms:
                        return w
                    return adj_form_lemma.get(w, w)
                gloss_is = ", ".join(_norm_adj(w) for w in gloss_is.split(","))

            xml.write(f'        <h1 class="entry-lemma">{html.escape(representative_lemma, quote=False)}</h1>\n')
            word_category = _word_category_is(is_verb, adjectival_entry, pos_kinds)
            if word_category:
                xml.write(f'        <p class="entry-preamble">{html.escape(word_category)}</p>\n')
            xml.write(f'        <div class="definition">\n')
            if gloss_is:
                xml.write(f'            <p class="gloss-is"><b>ÍS:</b> {html.escape(gloss_is, quote=False)}</p>\n')
            else:
                xml.write(f'            <p class="gloss-is gloss-missing">Engin trygg þýðing í orðasafninu.</p>\n')
            # The concise English line mirrors what the Icelandic gloss was
            # built from (the curated shortdef); the full LSJ sense list is
            # demoted to a smaller reference block below it rather than
            # driving the entry.
            if shortdef_en:
                xml.write(f'            <p class="gloss-en"><b>EN (LSJ):</b> {html.escape(shortdef_en, quote=False)}</p>\n')
                if clean_definition_en != html.escape(shortdef_en, quote=False):
                    xml.write(f'            <p class="senses-ref">{clean_definition_en}</p>\n')
            else:
                xml.write(f'            <p class="gloss-en"><b>EN (LSJ):</b> {clean_definition_en}</p>\n')
            xml.write(f'        </div>\n')

            if 'prep' in pos_kinds and representative_lemma in PREP_CASE_GOVERNANCE:
                gov = PREP_CASE_GOVERNANCE[representative_lemma]
                gov_items = "; ".join(
                    f'{_CLASSICAL_ABBR["case"].get(case, case)} – {is_prep}'
                    for case, is_prep in gov)
                xml.write('        <div class="case-governance-header">'
                           f'Fallstjórn: {html.escape(gov_items, quote=False)}</div>\n')

            # The single Icelandic word this entry's morphology tables and
            # stubs inflect (first single-word gloss token, already
            # adjective-normalized), plus its BÍN data if we have it.
            is_word = _primary_gloss_word(gloss_is)
            is_decl = noun_declension.get(is_word) if is_word else None
            is_adj = adj_declension.get(is_word) if is_word else None
            is_verb_slots = verb_forms.get(is_word) if is_word else None

            def _nominal_rendering(case, gender, number, degree='positive'):
                """Icelandic inflected form for a (degree, case, gender,
                number) cell: an adjective declines per gender AND degree
                (positive/comparative/superlative -- a noun has no degree,
                always 'positive', and takes the definite-suffix format
                instead). Icelandic has no vocative case -- ávarpsfall is
                always identical to the nominative -- so a Greek vocative
                cell renders the nominative Icelandic form rather than
                nothing."""
                if case == 'vocative':
                    case = 'nominative'
                if is_adj:
                    return is_adj.get((degree, case, gender, number))
                if is_decl:
                    forms = is_decl.get((case, number))
                    return _is_definite_suffix_form(*forms) if forms else None
                return None

            # Icelandic (unlike Greek's synthetic -teros/-tatos suffixes)
            # marks comparative/superlative with a wholly different
            # declension paradigm (vitur/vitrari/vitrastur), so each
            # attested Greek degree gets its OWN table rather than being
            # folded into the positive-degree one.
            _DEGREE_HEADINGS = {
                'positive': 'Beygingar / Declension',
                'comparative': 'Miðstig / Comparative',
                'superlative': 'Efsta stig / Superlative',
            }

            def _render_declension_table(degree, table_gender):
                is_ref = is_adj or is_decl
                xml.write('        <div class="morph-section">\n')
                xml.write(f'            <p class="morph-label">{_DEGREE_HEADINGS[degree]}</p>\n')
                xml.write('            <table class="morphology-table">\n')
                xml.write('                <tr><th>Fall</th><th>Eintala</th><th>Tvítala</th><th>Fleirtala</th></tr>\n')

                any_row = False
                for c in ['nominative', 'genitive', 'dative', 'accusative', 'vocative']:
                    cells = []
                    any_form = False
                    for num in ('singular', 'dual', 'plural'):
                        key = (degree, c, table_gender, num)
                        gk = ", ".join(sorted(noun_grid.get(key, []))) or '—'
                        if noun_grid.get(key):
                            any_form = True
                        rend = _nominal_rendering(c, table_gender, num, degree)
                        if rend:
                            gk += f'<br/><span class="is-gloss-form">{html.escape(rend, quote=False)}</span>'
                        cells.append(gk)
                    if not any_form:
                        continue
                    any_row = True
                    label = CASE_LABELS_IS.get(c, c.capitalize())
                    xml.write(f'                <tr><td class="case-label">{label}</td>'
                              f'<td>{cells[0]}</td><td>{cells[1]}</td><td>{cells[2]}</td></tr>\n')

                xml.write('            </table>\n')
                if is_ref and degree == 'positive':
                    kind = 'lýsingarorð' if is_adj else 'orð'
                    xml.write(f'            <p class="morph-note">Íslenskt viðmiðunar{kind}: '
                              f'<b>{html.escape(is_word, quote=False)}</b> (skv. BÍN).</p>\n')
                xml.write('        </div>\n')
                return any_row

            if is_noun_adj and noun_grid:
                # The table cites one gender: an adjective its masculine
                # citation, a noun its own single gender. Stubs (below) still
                # cover every attested gender.
                table_gender = ('masculine' if is_adj
                                else (next(iter(noun_genders)) if len(noun_genders) == 1
                                      else 'masculine'))
                _render_declension_table('positive', table_gender)
                for degree in ('comparative', 'superlative'):
                    if degree in adj_degrees:
                        _render_declension_table(degree, table_gender)

                # Stubs for every attested (degree, case, gender, number) form.
                for (degree, c, g, num), raws in noun_grid_raw.items():
                    rend = _nominal_rendering(c, g, num, degree)
                    tags = _dual_tag(case=c, gender=g, number=num, degree=degree)
                    for raw_form in raws:
                        register_stub(raw_form, representative_lemma, entry_id, tags, rend)

            elif is_verb and (verb_principal_parts or verb_secondary_moods):
                # Main-entry tables cite the 1st singular (header says so);
                # the full person/number spread lives in the per-form stubs.
                def _peri_1sg(tense, voice, mood):
                    if not is_verb_slots:
                        return None
                    return _icelandic_periphrasis(tense, voice, mood, '1st', 'singular',
                                                  is_word, is_verb_slots)

                def _peri_cell(tense, voice, mood):
                    peri = _peri_1sg(tense, voice, mood)
                    return f'<br/><span class="is-gloss-form">{html.escape(peri, quote=False)}</span>' if peri else ""

                def _row(tense, mood, voice, forms):
                    # person/number omitted -- the header states "1. p. et."
                    cl, isl = _dual_tag(mood=mood, tense=tense, voice=voice)
                    cell = ", ".join(forms) + _peri_cell(tense, voice, mood)
                    xml.write(f'                <tr><td class="case-label">{_tag_label_html(cl, isl)}</td>'
                              f'<td>{cell}</td></tr>\n')

                primary_parts = {k: v for k, v in verb_principal_parts.items() if k in PRINCIPAL_PARTS_PRIMARY}
                secondary_parts = {k: v for k, v in verb_principal_parts.items() if k not in PRINCIPAL_PARTS_PRIMARY}
                xml.write('        <div class="morph-section">\n')
                xml.write('            <p class="morph-label">Kennimyndir / Principal Parts</p>\n')
                xml.write('            <table class="morphology-table">\n')
                xml.write('                <tr><th>Auðkenni</th><th>Mynd (1. p. et.)</th></tr>\n')

                for key in PRINCIPAL_PARTS_ORDER:
                    if key in primary_parts:
                        _row(key[0], 'indicative', key[1], primary_parts[key])
                if secondary_parts:
                    xml.write('                <tr class="morph-secondary-header"><td colspan="2">Aðrar mögulegar myndir / Additional attested forms</td></tr>\n')
                    for key, forms in sorted(secondary_parts.items(), key=lambda kv: _tense_voice_label(*kv[0])):
                        _row(key[0], 'indicative', key[1], forms)

                if verb_secondary_moods:
                    xml.write('                <tr class="morph-secondary-header"><td colspan="2">Háttur / Mood (1. p. et.)</td></tr>\n')
                    for mood_key, (_, _) in MOOD_TENSE_FUSION_IS.items():
                        if mood_key not in verb_secondary_moods:
                            continue
                        mood_form = _peri_1sg(None, 'active', mood_key)
                        cl, isl = _dual_tag(mood=mood_key, voice='active')
                        cell = ", ".join(sorted(verb_secondary_moods[mood_key]))
                        if mood_form:
                            cell += f'<br/><span class="is-gloss-form">{html.escape(mood_form, quote=False)}</span>'
                        xml.write(f'                <tr><td class="case-label">{_tag_label_html(cl, isl)}</td>'
                                  f'<td>{cell}</td></tr>\n')

                xml.write('            </table>\n')
                if is_verb_slots:
                    xml.write(f'            <p class="morph-note">Íslensk viðmiðunarsögn: <b>{html.escape(is_word, quote=False)}</b> (skv. BÍN).</p>\n')
                xml.write('        </div>\n')

            elif generic_forms:
                xml.write('        <div class="morph-section">\n')
                xml.write('            <p class="morph-label">Myndir / Forms</p>\n')
                xml.write('            <table class="morphology-table">\n')
                for m_form, m_parsings in generic_forms.items():
                    parsing_display = ", ".join(html.escape(p, quote=False) for p in m_parsings)
                    xml.write(f'                <tr><td class="case-label">{m_form}</td><td>{parsing_display}</td></tr>\n')
                xml.write('            </table>\n')
                xml.write('        </div>\n')

            # Per-inflected-form stubs for verbs: every attested finite form
            # (all persons/numbers), each with its own periphrasis.
            for raw_form, parsings in verb_finite_forms.items():
                for tense, voice, mood, person, number in parsings:
                    rendering = None
                    if is_verb_slots:
                        rendering = _icelandic_periphrasis(
                            tense, voice, mood, person, number, is_word, is_verb_slots)
                    tags = _dual_tag(person=person, number=number, mood=mood,
                                     tense=tense, voice=voice)
                    register_stub(raw_form, representative_lemma, entry_id, tags, rendering)

            # Participle stubs: adjectival case/gender/number + verbal
            # tense/voice, rendered by the participle scheme.
            for raw_form, parsings in participle_forms.items():
                for case_name, gender, number, tense, voice in parsings:
                    rendering = None
                    if is_verb_slots:
                        rendering = _participle_periphrasis(
                            gender, number, tense, voice, is_word, is_verb_slots)
                    tags = _dual_tag(case=case_name, gender=gender, number=number,
                                     mood='participle', tense=tense, voice=voice)
                    register_stub(raw_form, representative_lemma, entry_id, tags, rendering)

            xml.write('    </d:entry>\n\n')

            if (index + 1) % 5000 == 0:
                print(f"   ... Processed {index + 1} / {total_entries} entries")

        # An unaccented form should resolve to its accented analogue's own
        # stub -- so index each stub under its accent-stripped spelling too,
        # but ONLY where that stub owns the canonical accented spelling for
        # that normalized key (form_norm_to_accented), so "λειπωνται" lands
        # on the "λείπωνται" stub rather than the base lemma or an
        # accent-variant twin.
        print(f"Writing {len(form_stub_candidates)} inflected-form stub entries...")
        for i, (raw_form, parsings) in enumerate(sorted(form_stub_candidates.items())):
            safe_title = sanitize_apple_key(raw_form)
            if not safe_title:
                continue
            stub_id = f"lsjform_{i}"
            xml.write(f'    <d:entry id="{stub_id}" d:title="{html.escape(safe_title)}">\n')
            xml.write(f'        <d:index d:value="{html.escape(safe_title)}"/>\n')
            norm = accent_key(raw_form)
            if norm and norm != raw_form and form_norm_to_accented.get(norm) == raw_form:
                clean_norm = sanitize_apple_key(norm)
                if clean_norm and clean_norm != safe_title:
                    xml.write(f'        <d:index d:value="{html.escape(clean_norm)}"/>\n')
            xml.write(f'        <h1 class="entry-lemma">{html.escape(raw_form, quote=False)}</h1>\n')
            xml.write('        <div class="definition">\n')
            xml.write('            <p class="gloss-en"><i>Beygingarmynd / Inflected form</i></p>\n')
            # A form can be attested for more than one lemma (a real homonym
            # collision) or more than one cell of the SAME lemma (a syncretic
            # form) -- dedup on (lemma, icelandic-tag) so the stub doesn't
            # repeat an identical parsing line.
            seen = set()
            for lemma_title, lemma_entry_id, classical_tag, icelandic_tag, is_rendering in parsings:
                dedup_key = (lemma_entry_id, icelandic_tag)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                link = f'<a href="x-dictionary:r:{lemma_entry_id}">{html.escape(lemma_title, quote=False)}</a>'
                # Translation frontloaded; then the classical (Greek) parse
                # and the lemma link + Icelandic parse, italicised.
                cl = f'<i class="tag-cl">{html.escape(classical_tag, quote=False)}</i>' if classical_tag else ''
                isl = html.escape(icelandic_tag, quote=False)
                if is_rendering:
                    line = (f'<b>{html.escape(is_rendering, quote=False)}</b> '
                            f'<i>— af {link}, {isl}</i>')
                else:
                    line = f'<i>af {link}, {isl}</i>'
                if cl:
                    line = f'{cl}<br/>{line}'
                xml.write(f'            <p class="gloss-is">{line}</p>\n')
            xml.write('        </div>\n')
            xml.write('    </d:entry>\n\n')

            if (i + 1) % 20000 == 0:
                print(f"   ... {i + 1}/{len(form_stub_candidates)} stub entries")

        write_pronunciation_guide_entry(xml)

        xml.write('</d:dictionary>\n')

    print(f"Success! XML built at {OUTPUT_XML_PATH}")

    lsj_conn.close()
    morph_conn.close()
    is_conn.close()


if __name__ == "__main__":
    build_dictionary()
