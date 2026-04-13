"""Fuzzy name matching — thin wrappers around Jellyfish.

Used by the Record Scout to match candidate records against a target person
when surnames are misspelled, transliterated, or recorded inconsistently
across historical sources.

Three layers:
  1. Raw phonetic codes — Soundex, Metaphone — for coarse equivalence classes.
  2. Edit-distance similarity — Levenshtein ratio, Jaro-Winkler — for scored ranking.
  3. A composite `name_match_score` that blends all three into a single 0..1 score
     so the Scout can threshold candidates without tuning four dials.

Design notes:
  - All functions are string-in / number-or-bool-out. No state, no I/O.
  - Case-insensitive, whitespace-trimmed. Empty/None inputs return 0 or False.
  - `name_match_score` weights Jaro-Winkler highest because surnames benefit
    from prefix-sensitive matching (e.g. Kennedy vs Kenedy).
"""

from __future__ import annotations

from typing import Optional

import jellyfish


def _clean(s: Optional[str]) -> str:
    return (s or "").strip()


def soundex(name: Optional[str]) -> str:
    """Return the Soundex code (e.g. 'Kennedy' → 'K530'). Empty for empty input."""
    cleaned = _clean(name)
    if not cleaned:
        return ""
    return jellyfish.soundex(cleaned)


def metaphone(name: Optional[str]) -> str:
    """Return the Metaphone code (e.g. 'Kennedy' → 'KNT'). Empty for empty input."""
    cleaned = _clean(name)
    if not cleaned:
        return ""
    return jellyfish.metaphone(cleaned)


def phonetic_match(name_a: Optional[str], name_b: Optional[str]) -> bool:
    """True iff both names share Soundex OR Metaphone codes.

    Use this as a coarse filter before running more expensive comparisons.
    """
    a = _clean(name_a)
    b = _clean(name_b)
    if not a or not b:
        return False
    return soundex(a) == soundex(b) or metaphone(a) == metaphone(b)


def levenshtein_ratio(name_a: Optional[str], name_b: Optional[str]) -> float:
    """Normalized edit-distance similarity in [0, 1]. 1.0 = identical.

    Returns 0.0 for empty inputs.
    """
    a = _clean(name_a).lower()
    b = _clean(name_b).lower()
    if not a or not b:
        return 0.0
    distance = jellyfish.levenshtein_distance(a, b)
    longest = max(len(a), len(b))
    return 1.0 - (distance / longest)


def jaro_winkler(name_a: Optional[str], name_b: Optional[str]) -> float:
    """Jaro-Winkler similarity in [0, 1]. Favors common prefixes."""
    a = _clean(name_a).lower()
    b = _clean(name_b).lower()
    if not a or not b:
        return 0.0
    return jellyfish.jaro_winkler_similarity(a, b)


def name_match_score(name_a: Optional[str], name_b: Optional[str]) -> float:
    """Composite 0..1 score blending phonetic + edit-distance signals.

    Weights:
      - 0.50 Jaro-Winkler (prefix-sensitive, handles misspellings well)
      - 0.30 Levenshtein ratio (handles transpositions and edits)
      - 0.20 phonetic match bonus (0 or 1)

    Empty/None inputs → 0.0.
    """
    a = _clean(name_a)
    b = _clean(name_b)
    if not a or not b:
        return 0.0

    jw = jaro_winkler(a, b)
    lev = levenshtein_ratio(a, b)
    phon = 1.0 if phonetic_match(a, b) else 0.0
    return round(0.50 * jw + 0.30 * lev + 0.20 * phon, 4)


def rank_candidates(
    target: str,
    candidates: list[str],
    threshold: float = 0.70,
) -> list[tuple[str, float]]:
    """Score all candidates against a target; return only those >= threshold,
    sorted by score descending.

    Useful for Record Scout: pass in the target surname and the list of
    surnames it pulled from a search; take the top-N above threshold.
    """
    scored = [(c, name_match_score(target, c)) for c in candidates]
    filtered = [(c, s) for c, s in scored if s >= threshold]
    filtered.sort(key=lambda pair: pair[1], reverse=True)
    return filtered
