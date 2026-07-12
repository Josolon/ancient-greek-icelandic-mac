"""Extract a compact Icelandic noun-declension / verb-form lookup from BÍN
(Beygingarlýsing íslensks nútímamáls / Database of Modern Icelandic
Inflection, CLARIN handle 20.500.12537/5, CC BY-SA 4.0, compiled by Kristín
Bjarnadóttir at the Árni Magnússon Institute for Icelandic Studies -- see
CREDITS.md), writing data/is_noun_declension.tsv and data/is_verb_forms.tsv.

Only extracts forms for words that actually occur as a first, single-word
Icelandic gloss somewhere in data/lsj_is.db -- BÍN itself covers ~300,000
lemmas, but the dictionary only ever needs to inflect the handful of
thousand words that are themselves glossary output. This keeps the derived
TSVs small and committed, same pattern as data/wiktionary_en_is.tsv.

Data source: the `islenska` PyPI package (Miðeind ehf., MIT-licensed wrapper
around the same BÍN dataset -- see CREDITS.md), NOT the raw Sigrúnarsnið CSV
dump. Run this script inside the project venv (`python3 -m venv .venv &&
.venv/bin/pip install islenska`, then `source .venv/bin/activate`) -- every
other script in this pipeline is stdlib-only and does NOT need the venv.
islenska.Bin exposes two lookups this script relies on:
  lookup_lemmas(w)  every entry whose CITATION LEMMA is exactly w
  lookup(w)         every entry whose INFLECTED FORM is exactly w (any lemma)
  lookup_id(id)     the full paradigm (every attested form) for one entry id
`.mark` on each returned entry is the same Sigrúnarsnið-style grammatical
tag string documented below (islenska wraps the identical underlying data,
it does not add register/frequency metadata that would help disambiguate
homographs -- see the MENNTUR_BLOCKLIST note further down).

Grammatical tags (`.mark`):
  Nouns (kk/kvk/hk):  NF/ÞF/ÞGF/EF (nom/acc/dat/gen) x ET/FT (sg/pl),
                      with a "gr" suffix for the definite-article form
                      (e.g. ÞGFETgr "hestinum" vs ÞGFET "hesti").
  Verbs (so):         the FULL finite paradigm the dictionary renders --
                      germynd (GM) and miðmynd (MM) x indicative (FH) and
                      subjunctive (VH) x present (NT) and past (ÞT) x all
                      three persons (1P/2P/3P) x both numbers (ET/FT) --
                      plus the supine (SAGNB) and the miðmynd infinitive
                      (MM-NH). Every attested Greek verb form gets its own
                      Icelandic rendering matching ITS person/number/mood
                      (not just a 1st-sg citation), so every cell of the
                      paradigm is needed: Icelandic inflects for person AND
                      number ("ég leysi", "þú leysir", "við leysum", ...),
                      none of it derivable by rule from the infinitive.

BÍN does NOT lemmatize Icelandic's mediopassive "-st" verb forms
separately (there is no standalone "leysast" lemma) -- they're MM- tagged
inflections inside the *same* paradigm as the active verb ("leysa" carries
both GM-* and MM-* rows). That maps directly onto Greek's active/middle
voice distinction: MM-NH ("leysast") is the miðmynd infinitive itself and
the MM-FH-*/MM-VH-* rows are its finite forms -- all looked up under the
one lemma "leysa", no separate "-st lemma" search needed.

BÍN's MM-SAGNB (miðmynd supine) column is frequently just a COPY of
GM-SAGNB rather than the genuine reflexive form -- e.g. leysa's MM-SAGNB is
recorded as "leyst", identical to GM-SAGNB, even though the real miðmynd
perfect is "ég hef leysts" (leyst + productive -st suffix, with the
double "stst" that produces simplifying to "sts"; see _fix_mm_supine).
Verbs with a genuinely distinct, lexicalized MM-SAGNB (mennta -> menntast,
yfirgefa -> yfirgefist) are trusted as-is; the synthesis only fires when
BÍN's two SAGNB columns are identical, which is the signal that BÍN didn't
bother recording a distinct entry.

Output format (data/is_verb_forms.tsv) is LONG -- one row per
(lemma, slot, form) -- because the paradigm is sparse and wide (up to ~50
cells/verb) and not every verb attests every cell. Slot keys:
  {gm,mm}_{ind,subj}_{pres,past}_{1,2,3}{sg,pl}   finite cells
  {gm,mm}_supine                                  supine
  mm_inf                                          miðmynd infinitive
  ptcp_{nom,kvk,hk}_{sg,pl}                       past-participle forms
  __subj_{gm,mm}                                  oblique-subject marker
(germynd infinitive is just the lemma, not stored).

Impersonal verbs (mig langar, mér finnst) get a __subj_{voice} row whose
value is the subject case (þf/þgf/ef/það); their finite cells are all the
3sg-collapsed form (they don't vary by the subject's person/number). See
parse_verb_tag and _choose_voice_slots. Only verbs that are impersonal in
BÍN with a single unambiguous case are marked -- a verb with any ordinary
personal paradigm is left personal, since the glossary picked it for that
sense.
"""
import sqlite3

try:
    from islenska import Bin
except ImportError as exc:
    raise SystemExit(
        "islenska is not installed in the current interpreter. Run this "
        "script inside the project venv:\n"
        "  python3 -m venv .venv && .venv/bin/pip install islenska\n"
        "  source .venv/bin/activate && python3 scripts/build_is_morphology.py"
    ) from exc

IS_DB_PATH = "data/lsj_is.db"
NOUN_OUT_PATH = "data/is_noun_declension.tsv"
VERB_OUT_PATH = "data/is_verb_forms.tsv"
ADJ_OUT_PATH = "data/is_adj_declension.tsv"
ADJ_LEMMA_OUT_PATH = "data/is_adj_form_lemma.tsv"

NOUN_CLASSES = {"kk", "kvk", "hk"}
VERB_CLASS = "so"
ADJ_CLASS = "lo"

# BÍN lists "menntur" (id 166123) as a positive-strong adjective lemma whose
# paradigm happens to overlap heavily with "mennta"'s own past-participle
# forms (menntaður, menntað, ...) -- but a native speaker confirms "menntur"
# is not a real word in this sense; the forms are participles of the verb
# "mennta", not an independent adjective. islenska carries the same BÍN data
# as the raw CSV (no register/frequency field distinguishes it -- checked
# via lookup_ksnid), so this is a hand-curated exclusion, not a data fix.
# Extend this set if other archaic/spurious BÍN "lo" lemmas turn up the same
# way -- see bin-morphology-recap.md.
ADJ_LEMMA_BLOCKLIST_IDS = {166123}  # menntur

# BÍN case tag -> the label keys already used in build_xml.py's
# CASE_LABELS_IS, so the two can be joined directly at render time.
CASES = {"NF": "nominative", "ÞF": "accusative", "ÞGF": "dative", "EF": "genitive"}
NUMBERS = {"ET": "singular", "FT": "plural"}
GENDERS = {"KK": "masculine", "KVK": "feminine", "HK": "neuter"}

# Adjective (lo) strong/indefinite declension, one tag prefix per degree:
# FSB (Frumstig Sterk beyging, positive), MST (Miðstig, comparative -- no
# strong/weak split in Icelandic), ESB (Efsta stig Sterk beyging,
# superlative). Strong is the citation paradigm in each degree -- the weak
# (FVB/EVB) forms are the "góði"/"besti" definite-context ones. Greek
# adjectives inflect for case/gender/number with no definiteness
# distinction, so the strong forms are the right target throughout.
# Morpheus tags each Greek adjective FORM with its own degree (positive/
# comparative/superlative, see data/morph.db's `degree` column) -- a
# comparative Greek form like sophoteros must render against MST, not
# FSB, or the dictionary shows the wrong Icelandic word entirely.
_ADJ_DEGREE_TAG_PREFIX = {"FSB": "positive", "MST": "comparative", "ESB": "superlative"}

# BÍN grammatical-tag component -> slot-key component. Finite verb tags in
# Sigrúnarsnið are "VOICE-MOOD-TENSE-PERSON-NUMBER" (e.g. GM-FH-NT-3P-ET);
# supine is "VOICE-SAGNB"; infinitive is "VOICE-NH".
_V_VOICE = {"GM": "gm", "MM": "mm"}
_V_MOOD = {"FH": "ind", "VH": "subj"}
_V_TENSE = {"NT": "pres", "ÞT": "past"}
_V_PERSON = {"1P": "1", "2P": "2", "3P": "3"}
_V_NUMBER = {"ET": "sg", "FT": "pl"}

# Impersonal ("ópersónuleg") verbs -- "mig langar", "mér finnst" -- carry
# their subject in an oblique case and take an OP-prefixed tag whose second
# component is that case: OP-ÞF-... (accusative subject), OP-ÞGF-...
# (dative), OP-EF-... (genitive), or OP-það-... (an expletive "það" dummy
# subject, weather verbs etc.). Their verb form is INVARIANT across the
# subject's person/number -- "langar" whatever the subject -- so all cells
# collapse onto the 3rd-singular form.
_V_SUBJ_CASE = {"ÞF": "þf", "ÞGF": "þgf", "EF": "ef", "það": "það"}


def parse_verb_tag(tag):
    """BÍN verb tag -> (slot_key, subj_case), or None for tags we don't
    render. subj_case is None for an ordinary personal form; for an
    impersonal (OP-) form it is 'þf'/'þgf'/'ef'/'það' and the slot_key is
    forced to the 3rd-singular cell (impersonal forms don't vary by the
    oblique subject's person/number)."""
    parts = tag.split("-")
    subj_case = None
    force_3sg = False
    if parts and parts[0] == "OP":
        if len(parts) < 3:
            return None
        subj_case = _V_SUBJ_CASE.get(parts[1])
        if subj_case is None:
            return None
        parts = parts[2:]
        force_3sg = True

    if len(parts) == 2:
        voice, kind = parts
        if voice in _V_VOICE and kind == "SAGNB":
            return (f"{_V_VOICE[voice]}_supine", subj_case)
        if voice == "MM" and kind == "NH":
            return ("mm_inf", subj_case)
        return None
    if len(parts) == 5:
        voice, mood, tense, person, number = parts
        if (voice in _V_VOICE and mood in _V_MOOD and tense in _V_TENSE
                and person in _V_PERSON and number in _V_NUMBER):
            pn = "3sg" if force_3sg else f"{_V_PERSON[person]}{_V_NUMBER[number]}"
            return (f"{_V_VOICE[voice]}_{_V_MOOD[mood]}_{_V_TENSE[tense]}_{pn}", subj_case)
    return None


# Past-participle forms (LHÞT-SB-KK-{case}{number}, e.g. "LHÞT-SB-KK-NFET"
# -> "leystur"), used to build the Icelandic þolmynd (vera/verða +
# participle) construction and the miðmynd/þolmynd-hybrid perfect ("hef
# leysts"). Voice-agnostic in BÍN (no GM-/MM- prefix): one participle
# paradigm per verb serves both constructions. Masculine strong (SB/KK) is
# used throughout as the citation gender/class, same convention as the rest
# of this dictionary's person-marked renderings (which don't specify
# gender for 1st/2nd person either). Nominative sg/pl agree the vera/verða
# construction with the subject's number; the genitive singular is used
# invariantly (not case-agreeing) as a fixed marker in the perfect hybrid,
# matching how the supine itself is invariant elsewhere in this table.
_PARTICIPLE_TAGS = {
    # Masculine nom sg/pl drive the passive "vera + participle" construction
    # (masc is the citation default, as elsewhere). All three genders'
    # nominative are needed for the Greek-participle rendering
    # (_participle_periphrasis), which agrees the Icelandic past participle
    # with the participle's own gender (menntaður kk / menntuð kvk /
    # menntað hk).
    "LHÞT-SB-KK-NFET": "ptcp_nom_sg",       # = ptcp_kk_sg
    "LHÞT-SB-KK-NFFT": "ptcp_nom_pl",       # = ptcp_kk_pl
    "LHÞT-SB-KVK-NFET": "ptcp_kvk_sg",
    "LHÞT-SB-KVK-NFFT": "ptcp_kvk_pl",
    "LHÞT-SB-HK-NFET": "ptcp_hk_sg",
    "LHÞT-SB-HK-NFFT": "ptcp_hk_pl",
}


def parse_adj_slot(tag):
    """BÍN strong-declension adjective tag (FSB/MST/ESB-{gender}-{case}
    {number}) -> (degree_name, case_name, gender_name, number_name), or
    None. Ignores weak (FVB/EVB) forms -- only the strong paradigm, the
    citation declension a Greek adjective form maps to, in each of the
    three degrees. A few MST cells carry an alternate spelling suffixed
    "2" (e.g. NFET2) -- skipped here (number lookup fails), same as any
    other unrecognized tag; the primary spelling is enough."""
    prefix, _, rest = tag.partition("-")
    degree = _ADJ_DEGREE_TAG_PREFIX.get(prefix)
    if degree is None or not rest:
        return None
    parts = rest.split("-")
    if len(parts) != 2:
        return None
    gender_code, cn = parts
    gender = GENDERS.get(gender_code)
    if not gender:
        return None
    case = number = None
    for cc, name in CASES.items():
        if cn.startswith(cc):
            case = name
            number = NUMBERS.get(cn[len(cc):])
            break
    if not case or not number:
        return None
    return (degree, case, gender, number)


def _target_words():
    """Every single-word token that appears as (part of) a gloss in
    data/lsj_is.db -- the only words this dictionary will ever need to
    inflect."""
    conn = sqlite3.connect(IS_DB_PATH)
    words = set()
    for (gloss,) in conn.execute("SELECT gloss_is FROM definitions_is WHERE gloss_is IS NOT NULL"):
        for word in gloss.split(","):
            word = word.strip()
            if word and " " not in word:
                words.add(word)
    conn.close()
    return words


def _choose_voice_slots(pers, op, opcases):
    """Decide, per voice (gm/mm), whether this verb is personal or
    impersonal, and return (slots, subj_cases). A voice is personal iff it
    has any ordinary finite form; then its personal slots are used and no
    oblique subject is recorded. Otherwise, if its impersonal (OP) forms
    point at exactly ONE oblique case, it's an impersonal verb in that case
    (its 3sg-collapsed OP forms become the slots); a voice attested only
    with the expletive 'það' subject is treated as impersonal-'það'.
    Anything ambiguous (two oblique cases, or no usable data) is dropped for
    that voice -- rendering it would be a guess.

    Deliberately conservative: a verb with BOTH a personal paradigm and OP
    forms (bera, draga, finna...) counts as personal, because the glossary
    almost always chose it for its ordinary sense, not the impersonal one --
    "ég ber" (I carry), not an impersonal reading."""
    out_slots, subj = {}, {}

    # Supine and the miðmynd infinitive are non-finite: they carry no
    # subject and so are tagged plainly even for impersonal verbs. Carry
    # them through from whichever source has them, and -- crucially -- do
    # NOT let them count as evidence that a voice is "personal" below.
    def is_finite(s):
        return "_ind_" in s or "_subj_" in s

    for src in (pers, op):
        for s, f in src.items():
            if not is_finite(s):
                out_slots.setdefault(s, f)

    for voice in ("gm", "mm"):
        finite_personal = {s: f for s, f in pers.items()
                           if is_finite(s) and s.split("_")[0] == voice}
        if finite_personal:
            out_slots.update(finite_personal)
            continue
        cases = opcases.get(voice, set())
        oblique = cases & {"þf", "þgf", "ef"}
        chosen = None
        if len(oblique) == 1:
            chosen = next(iter(oblique))
        elif not oblique and "það" in cases:
            chosen = "það"
        if chosen:
            subj[voice] = chosen
            out_slots.update({s: f for s, f in op.items()
                              if is_finite(s) and s.split("_")[0] == voice})
    return out_slots, subj


# Reflexive -st assimilation: when the base (germynd) supine already ends in
# "st" (leyst, hitt-, ...), appending the productive miðmynd -st suffix
# produces a "stst" cluster that Icelandic simplifies to "sts" (leyst+st ->
# leystst -> leysts). This is the ONLY assimilation this dictionary
# synthesizes -- anything else (yfirgefa's irregular -ið -> -ist) needs a
# genuinely distinct MM-SAGNB from BÍN, which is trusted as-is. See the
# module docstring and bin-morphology-recap.md.
def _fix_mm_supine(gm_supine, mm_supine):
    if mm_supine and mm_supine != gm_supine:
        return mm_supine
    if gm_supine and gm_supine.endswith("st"):
        return gm_supine + "s"
    return mm_supine


def main():
    targets = _target_words()
    print(f"Looking up {len(targets)} distinct single-word glosses in BÍN via islenska...")
    bindb = Bin()

    # headword -> id -> {(case, number): {"indef": form, "def": form}}
    noun_data = {}
    # Personal and impersonal (OP) verb forms are collected together per
    # entry (islenska's lookup_id already scopes to one lemma+id), then
    # reconciled per voice in _choose_voice_slots. verb_opcases records which
    # oblique subject case(s) each (verb, voice) was attested with.
    verb_personal = {}   # headword -> id -> {slot: form}  (includes OP forms)
    verb_op = {}         # headword -> id -> {slot: form}  (OP forms only, 3sg-collapsed)
    verb_opcases = {}    # headword -> id -> {voice: {case, ...}}
    # Adjectives: full positive-strong declension per lemma, PLUS a map from
    # any inflected form that is itself a gloss word back to its lemma. The
    # latter is what lets a gloss like "gott" (neuter nom sg) be normalized
    # to its citation lemma "góður" and then declined per the Greek form's
    # gender -- so adjectives are collected when the HEADWORD or the FORM is
    # a gloss word, not just the headword. ADJ_LEMMA_BLOCKLIST_IDS excludes
    # known-spurious lemmas (e.g. "menntur") from both directions.
    adj_data = {}        # headword -> id -> {(case, gender, number): form}
    adj_form_lemma = {}  # gloss-word form -> (lemma, id) (lowest non-blocklisted id wins)

    # Nouns and verbs: forward lookup only (headword must be the citation
    # lemma), same as the old CSV pass -- unchanged behavior.
    for headword in sorted(targets):
        _, cands = bindb.lookup_lemmas(headword)
        noun_ids = sorted({e.bin_id for e in cands if e.ofl in NOUN_CLASSES})
        if noun_ids:
            entry_id = noun_ids[0]
            for e in bindb.lookup_id(entry_id):
                if e.ord != headword:
                    continue
                tag = e.mark
                definite = tag.endswith("gr")
                base_tag = tag[:-2] if definite else tag
                for case_code, case_name in CASES.items():
                    if not base_tag.startswith(case_code):
                        continue
                    number_name = NUMBERS.get(base_tag[len(case_code):])
                    if not number_name:
                        continue
                    cell = noun_data.setdefault(headword, {}).setdefault(entry_id, {}) \
                        .setdefault((case_name, number_name), {})
                    cell["def" if definite else "indef"] = e.bmynd
                    break

        verb_ids = sorted({e.bin_id for e in cands if e.ofl == VERB_CLASS})
        if verb_ids:
            entry_id = verb_ids[0]
            pers_sink = verb_personal.setdefault(headword, {}).setdefault(entry_id, {})
            op_sink = verb_op.setdefault(headword, {}).setdefault(entry_id, {})
            opcases_sink = verb_opcases.setdefault(headword, {}).setdefault(entry_id, {})
            for e in bindb.lookup_id(entry_id):
                if e.ord != headword:
                    continue
                tag = e.mark
                if tag in _PARTICIPLE_TAGS:
                    pers_sink[_PARTICIPLE_TAGS[tag]] = e.bmynd
                    continue
                res = parse_verb_tag(tag)
                if not res:
                    continue
                slot_key, subj_case = res
                if subj_case is None:
                    pers_sink[slot_key] = e.bmynd
                else:
                    op_sink[slot_key] = e.bmynd
                    opcases_sink.setdefault(slot_key.split("_")[0], set()).add(subj_case)
            # Reflexive -st assimilation for verbs whose BÍN MM-SAGNB just
            # duplicates GM-SAGNB (see _fix_mm_supine).
            fixed = _fix_mm_supine(pers_sink.get("gm_supine"), pers_sink.get("mm_supine"))
            if fixed:
                pers_sink["mm_supine"] = fixed

    # Adjectives: forward (headword is the lemma) AND reverse (headword is
    # merely an attested FORM of some other adjective lemma, e.g. Greek
    # gloss "gott" is neuter nom sg of "góður"). Collect candidate
    # (lemma, id) pairs from both directions before choosing one id per
    # lemma, same two-pass shape as the old CSV loop.
    adj_lemma_candidates = set()  # {(lemma, id)}
    form_reverse = {}             # form -> [(lemma, id), ...] sorted by id

    for word in sorted(targets):
        _, fwd = bindb.lookup_lemmas(word)
        for e in fwd:
            if e.ofl == ADJ_CLASS and e.bin_id not in ADJ_LEMMA_BLOCKLIST_IDS:
                adj_lemma_candidates.add((e.ord, e.bin_id))

        _, rev = bindb.lookup(word)
        cands = sorted(
            {(e.ord, e.bin_id) for e in rev
             if e.ofl == ADJ_CLASS and e.ord != word
             and e.bin_id not in ADJ_LEMMA_BLOCKLIST_IDS},
            key=lambda p: p[1],
        )
        if cands:
            form_reverse[word] = cands[0]
            adj_lemma_candidates.add(cands[0])

    for form, (lemma, entry_id) in form_reverse.items():
        adj_form_lemma[form] = (lemma, entry_id)

    adj_ids_by_lemma = {}
    for lemma, entry_id in adj_lemma_candidates:
        adj_ids_by_lemma.setdefault(lemma, []).append(entry_id)

    for headword, ids in adj_ids_by_lemma.items():
        entry_id = min(ids)
        cells = adj_data.setdefault(headword, {}).setdefault(entry_id, {})
        for e in bindb.lookup_id(entry_id):
            if e.ord != headword:
                continue
            res = parse_adj_slot(e.mark)
            if res:
                cells[res] = e.bmynd

    # Collapse multiple homograph ids per headword (rare: e.g. a word
    # attested under two BÍN ids) by keeping the numerically lowest id --
    # BÍN ids are stable and low ids tend to be the long-established
    # entries. A glossary rendering only needs "a" correct declension, not
    # perfect homograph disambiguation the source Icelandic gloss word
    # itself doesn't carry.
    with open(NOUN_OUT_PATH, "w", encoding="utf-8") as out:
        for headword in sorted(noun_data):
            entry_id = min(noun_data[headword], key=int)
            cells = noun_data[headword][entry_id]
            for (case_name, number_name), forms in sorted(cells.items()):
                indef, definite = forms.get("indef", ""), forms.get("def", "")
                if not indef and not definite:
                    continue
                out.write(f"{headword}\t{case_name}\t{number_name}\t{indef}\t{definite}\n")

    verb_rows = 0
    impersonal_count = 0
    with open(VERB_OUT_PATH, "w", encoding="utf-8") as out:
        all_verbs = set(verb_personal) | set(verb_op)
        for headword in sorted(all_verbs):
            ids = set(verb_personal.get(headword, {})) | set(verb_op.get(headword, {}))
            entry_id = min(ids, key=int)
            pers = verb_personal.get(headword, {}).get(entry_id, {})
            op = verb_op.get(headword, {}).get(entry_id, {})
            opcases = verb_opcases.get(headword, {}).get(entry_id, {})
            slots, subj = _choose_voice_slots(pers, op, opcases)
            for slot in sorted(slots):
                out.write(f"{headword}\t{slot}\t{slots[slot]}\n")
                verb_rows += 1
            for voice in sorted(subj):
                out.write(f"{headword}\t__subj_{voice}\t{subj[voice]}\n")
                verb_rows += 1
                impersonal_count += 1

    adj_rows = 0
    with open(ADJ_OUT_PATH, "w", encoding="utf-8") as out:
        for headword in sorted(adj_data):
            entry_id = min(adj_data[headword], key=int)
            cells = adj_data[headword][entry_id]
            for (degree_name, case_name, gender_name, number_name) in sorted(cells):
                out.write(f"{headword}\t{degree_name}\t{case_name}\t{gender_name}\t{number_name}\t"
                          f"{cells[(degree_name, case_name, gender_name, number_name)]}\n")
                adj_rows += 1

    with open(ADJ_LEMMA_OUT_PATH, "w", encoding="utf-8") as out:
        for form in sorted(adj_form_lemma):
            out.write(f"{form}\t{adj_form_lemma[form][0]}\n")

    print(f"Wrote {len(noun_data)} nouns to {NOUN_OUT_PATH}")
    print(f"Wrote {verb_rows} verb-form rows for {len(all_verbs)} verbs "
          f"({impersonal_count} impersonal voice(s)) to {VERB_OUT_PATH}")
    print(f"Wrote {adj_rows} adjective-form rows for {len(adj_data)} adjectives to {ADJ_OUT_PATH}")
    print(f"Wrote {len(adj_form_lemma)} adjective form->lemma entries to {ADJ_LEMMA_OUT_PATH}")


if __name__ == "__main__":
    main()
