"""Shared Greek headword normalization for deduplicating spelling variants
that LSJ's TEI-XML parsing produced as separate rows for what is the same
word -- see build_xml.py and build_reverse_xml.py for where this is used.

_accent_key() strips ONLY the acute/grave/circumflex combining marks, never
breathing marks or capitalization, both of which are genuinely meaningful in
Greek: rough vs smooth breathing distinguishes real word pairs (hóros
"boundary" vs óros "mountain"), and capitalization distinguishes a proper
name (Hippos) from a common noun (hippos, "horse"). Merging across case is
only ever done by callers when they've independently confirmed there's no
semantic difference (e.g. build_xml.py only merges rows whose full
definitions text is byte-identical) -- accent-folding alone never justifies
crossing that line here.
"""
import unicodedata

# Combining accent marks (acute, grave, circumflex/perispomeni) to strip for
# dedup purposes.
_ACCENT_MARKS = {"́", "̀", "͂"}


def accent_key(word):
    """Grouping key that folds away pure accent-placement variants while
    preserving breathing marks and case."""
    decomposed = unicodedata.normalize("NFD", word)
    return "".join(ch for ch in decomposed if ch not in _ACCENT_MARKS)


def mark_count(word):
    """How many combining diacritics `word` carries -- used to prefer the
    fullest/most standard accentuation as a group's representative spelling."""
    return len(unicodedata.normalize("NFD", word)) - len(word)


def pick_representative(spellings):
    """Best single spelling to display for a group of variants: prefers a
    lowercase-starting form when any exists in the group (capitalization
    here is far more often an LSJ citation artifact than a real proper
    noun), then the most fully accented form, then alphabetical order for
    determinism."""
    spellings = list(spellings)
    has_lower = any(s[0].islower() for s in spellings if s)

    def sort_key(s):
        case_rank = 0 if (not has_lower or s[0].islower()) else 1
        return (case_rank, -mark_count(s), s)

    return sorted(spellings, key=sort_key)[0]


def dedup_accent_variants(words):
    """Collapse pure accent-placement variants in `words` to one
    representative each (breathing marks and case kept separate)."""
    groups = {}
    for word in words:
        groups.setdefault(accent_key(word), []).append(word)
    return [pick_representative(variants) for variants in groups.values()]
