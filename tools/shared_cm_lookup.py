"""Shared cM Project lookup table — predicts relationships from shared DNA.

Embeds the Shared cM Project data (thednageek.com/the-shared-cm-project)
as a static lookup table. Given a shared cM value, returns all possible
relationships sorted by probability, with each relationship's typical
range and the cM value's position within that range.

Two public functions:

    lookup_relationships(shared_cM) -> list[dict]
        Returns all relationships whose range includes the given cM value,
        ranked by how close the value is to the relationship's typical average.

    is_consistent(shared_cM, claimed_relationship) -> dict
        Checks whether a cM value is consistent with a specific claimed
        relationship type. Returns a structured result with in_range bool,
        expected range, and deviation description.

Design: pure functions over static data. No I/O, no network, no LLM.
"""

from __future__ import annotations

import math
from typing import Optional


# ---------------------------------------------------------------------------
# Shared cM Project reference data
# ---------------------------------------------------------------------------
# Each entry: (relationship, typical_cM, min_cM, max_cM)
# Ranges from the Shared cM Project, DNA Painter, and ISOGG wiki.

_RELATIONSHIP_TABLE: list[tuple[str, float, float, float]] = [
    ("Parent/Child",            3400,  3330, 3720),
    ("Full Sibling",            2550,  2200, 3200),
    ("Grandparent/Grandchild",  1750,  1150, 2250),
    ("Half Sibling",            1750,  1150, 2250),
    ("Aunt/Uncle",              1750,  1150, 2250),
    ("Great-Grandparent",        850,   550, 1150),
    ("1st Cousin",               850,   550, 1150),
    ("Half Aunt/Uncle",          850,   550, 1150),
    ("Great-Great-Grandparent",  425,   230,  640),
    ("1st Cousin 1x Removed",    425,   230,  640),
    ("Half 1st Cousin",          425,   230,  640),
    ("Great-Aunt/Uncle",         425,   230,  640),
    ("2nd Cousin",               212,    40,  400),
    ("2nd Cousin 1x Removed",    106,    20,  240),
    ("Half 2nd Cousin",          106,    20,  240),
    ("3rd Cousin",                53,    15,  160),
    ("3rd Cousin 1x Removed",     35,     0,  100),
    ("4th Cousin",                27,     6,   65),
    ("4th Cousin 1x Removed",     18,     0,   45),
    ("5th Cousin",                13,     0,   30),
    ("5th Cousin 1x Removed",      8,     0,   20),
    ("6th Cousin",                 5,     0,   15),
]

# Canonical relationship names for matching claimed relationships from
# platforms or GEDCOM path descriptions.
_CANONICAL_ALIASES: dict[str, str] = {
    "parent": "Parent/Child",
    "child": "Parent/Child",
    "parent/child": "Parent/Child",
    "father": "Parent/Child",
    "mother": "Parent/Child",
    "son": "Parent/Child",
    "daughter": "Parent/Child",
    "father of": "Parent/Child",
    "mother of": "Parent/Child",
    "son of": "Parent/Child",
    "daughter of": "Parent/Child",
    "parent of": "Parent/Child",
    "child of": "Parent/Child",
    "biological father": "Parent/Child",
    "biological mother": "Parent/Child",
    "biological parent": "Parent/Child",
    "sibling of": "Full Sibling",
    "brother of": "Full Sibling",
    "sister of": "Full Sibling",
    "grandfather": "Grandparent/Grandchild",
    "grandmother": "Grandparent/Grandchild",
    "grandparent of": "Grandparent/Grandchild",
    "grandchild of": "Grandparent/Grandchild",
    "grandfather of": "Grandparent/Grandchild",
    "grandmother of": "Grandparent/Grandchild",
    "grandson": "Grandparent/Grandchild",
    "granddaughter": "Grandparent/Grandchild",
    "aunt of": "Aunt/Uncle",
    "uncle of": "Aunt/Uncle",
    "niece of": "Aunt/Uncle",
    "nephew of": "Aunt/Uncle",
    "sibling": "Full Sibling",
    "full sibling": "Full Sibling",
    "brother": "Full Sibling",
    "sister": "Full Sibling",
    "grandparent": "Grandparent/Grandchild",
    "grandchild": "Grandparent/Grandchild",
    "half sibling": "Half Sibling",
    "half-sibling": "Half Sibling",
    "half brother": "Half Sibling",
    "half sister": "Half Sibling",
    "aunt": "Aunt/Uncle",
    "uncle": "Aunt/Uncle",
    "aunt/uncle": "Aunt/Uncle",
    "niece": "Aunt/Uncle",
    "nephew": "Aunt/Uncle",
    "1st cousin": "1st Cousin",
    "first cousin": "1st Cousin",
    "1c": "1st Cousin",
    "great-grandparent": "Great-Grandparent",
    "great grandparent": "Great-Grandparent",
    "half aunt": "Half Aunt/Uncle",
    "half uncle": "Half Aunt/Uncle",
    "1st cousin once removed": "1st Cousin 1x Removed",
    "1c1r": "1st Cousin 1x Removed",
    "1st cousin 1x removed": "1st Cousin 1x Removed",
    "half 1st cousin": "Half 1st Cousin",
    "half first cousin": "Half 1st Cousin",
    "2nd cousin": "2nd Cousin",
    "second cousin": "2nd Cousin",
    "2c": "2nd Cousin",
    "2nd cousin once removed": "2nd Cousin 1x Removed",
    "2c1r": "2nd Cousin 1x Removed",
    "3rd cousin": "3rd Cousin",
    "third cousin": "3rd Cousin",
    "3c": "3rd Cousin",
    "4th cousin": "4th Cousin",
    "fourth cousin": "4th Cousin",
    "4c": "4th Cousin",
    "5th cousin": "5th Cousin",
    "fifth cousin": "5th Cousin",
    "5c": "5th Cousin",
    # MyHeritage extended predictions
    "4th cousin's son": "4th Cousin 1x Removed",
    "4th cousin's daughter": "4th Cousin 1x Removed",
    "5th cousin's son": "5th Cousin 1x Removed",
    "5th cousin's daughter": "5th Cousin 1x Removed",
    "3rd cousin's son": "3rd Cousin 1x Removed",
    "3rd cousin's daughter": "3rd Cousin 1x Removed",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def lookup_relationships(shared_cM: float) -> list[dict]:
    """Return all possible relationships for a given shared cM value.

    Results are sorted by probability (how close the cM value is to the
    relationship's typical average, normalized by range width). Each result:

        {
            "relationship":   str,
            "probability":    float (0..1, relative — not a true probability),
            "typical_range":  [min, max],
            "typical_cM":     float,
            "position":       str ("within range" | "at edge" | "outside range"),
        }
    """
    if shared_cM <= 0:
        return []

    candidates: list[dict] = []
    for rel, typical, lo, hi in _RELATIONSHIP_TABLE:
        if shared_cM < lo - (hi - lo) * 0.1:
            continue  # too far below range
        if shared_cM > hi + (hi - lo) * 0.1:
            continue  # too far above range

        in_range = lo <= shared_cM <= hi
        distance = abs(shared_cM - typical)
        range_width = max(hi - lo, 1)
        # Score: inverse distance normalized by range width. Higher = better fit.
        raw_score = max(0.0, 1.0 - distance / range_width)

        if in_range:
            position = "within range"
        elif abs(shared_cM - lo) < range_width * 0.1 or abs(shared_cM - hi) < range_width * 0.1:
            position = "at edge"
            raw_score *= 0.5  # penalize edge cases
        else:
            position = "outside range"
            raw_score *= 0.2

        candidates.append({
            "relationship": rel,
            "raw_score": raw_score,
            "typical_range": [lo, hi],
            "typical_cM": typical,
            "position": position,
        })

    if not candidates:
        return []

    # Normalize scores to sum to 1.0 (relative probabilities).
    total = sum(c["raw_score"] for c in candidates) or 1.0
    for c in candidates:
        c["probability"] = round(c["raw_score"] / total, 3)
        del c["raw_score"]

    candidates.sort(key=lambda c: c["probability"], reverse=True)
    return candidates


def is_consistent(
    shared_cM: float,
    claimed_relationship: str,
) -> dict:
    """Check whether a cM value is consistent with a claimed relationship.

    Returns:
        {
            "consistent":      bool — True if cM is within the expected range
                               or within 10% of the range edges,
            "in_range":        bool — True if cM is strictly within [min, max],
            "expected_range":  [min, max] | None,
            "typical_cM":      float | None,
            "deviation":       str — human-readable description,
            "claimed":         str — the canonical relationship name matched,
        }
    """
    canonical = _resolve_relationship(claimed_relationship)
    if canonical is None:
        return {
            "consistent": False,
            "in_range": False,
            "expected_range": None,
            "typical_cM": None,
            "deviation": f"unknown relationship type: '{claimed_relationship}'",
            "claimed": claimed_relationship,
        }

    entry = next(
        (r for r in _RELATIONSHIP_TABLE if r[0] == canonical), None
    )
    if entry is None:
        return {
            "consistent": False,
            "in_range": False,
            "expected_range": None,
            "typical_cM": None,
            "deviation": f"no range data for '{canonical}'",
            "claimed": canonical,
        }

    _, typical, lo, hi = entry
    in_range = lo <= shared_cM <= hi
    margin = (hi - lo) * 0.10
    consistent = (lo - margin) <= shared_cM <= (hi + margin)

    if in_range:
        deviation = f"within expected range [{lo}-{hi}] (typical {typical})"
    elif shared_cM < lo:
        deviation = f"{lo - shared_cM:.1f} cM below minimum {lo} (typical {typical})"
    else:
        deviation = f"{shared_cM - hi:.1f} cM above maximum {hi} (typical {typical})"

    return {
        "consistent": consistent,
        "in_range": in_range,
        "expected_range": [lo, hi],
        "typical_cM": typical,
        "deviation": deviation,
        "claimed": canonical,
    }


def _resolve_relationship(claimed: str) -> Optional[str]:
    """Map a free-text relationship claim to a canonical table entry."""
    normalized = claimed.strip().lower()
    if normalized in _CANONICAL_ALIASES:
        return _CANONICAL_ALIASES[normalized]
    # Try direct match against table entries (case-insensitive).
    for rel, _, _, _ in _RELATIONSHIP_TABLE:
        if rel.lower() == normalized:
            return rel
    return None
