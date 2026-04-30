"""Subtree extractor — traverses GEDCOM person dicts to extract a subtree.

Given a root person and a generation depth, walks parent or child links
to collect everyone in the subtree plus every relationship encountered.

Two public functions:

    extract_subtree(gedcom_persons, root_id, generations=3, direction="ancestors")
        Returns {"persons": list[dict], "relationships": list[dict],
                 "root": dict, "generations_reached": int}

    extract_all_relationships(gedcom_persons, root_id, generations=3)
        Convenience: returns a flat list of relationship dicts covering
        both ancestor and descendant directions (union, deduplicated).

Design: pure traversal over parser-output dicts. No I/O, no LLM, no network.
Handles missing links gracefully (stops that branch, never crashes).
"""

from __future__ import annotations

from typing import Optional


def extract_subtree(
    gedcom_persons: list[dict],
    root_id: str,
    generations: int = 3,
    direction: str = "ancestors",
) -> dict:
    """Extract a subtree rooted at ``root_id``.

    Args:
        gedcom_persons: full parsed person list from the GEDCOM parser.
        root_id: GEDCOM pointer of the starting person (e.g. "@I0@").
        generations: how many generations to traverse (1 = just parents/children).
        direction: "ancestors" (follow father_id/mother_id upward) or
                   "descendants" (follow children_ids downward).

    Returns:
        {
            "persons":             list[dict] — all person dicts in the subtree,
            "relationships":       list[dict] — every parent-child + spousal link,
            "root":                dict — the root person dict,
            "generations_reached": int — actual depth reached (may be < generations
                                         if branches terminate early),
        }
    """
    by_id = {p["id"]: p for p in gedcom_persons}
    root = by_id.get(root_id)
    if not root:
        return {
            "persons": [],
            "relationships": [],
            "root": None,
            "generations_reached": 0,
        }

    collected_ids: set[str] = set()
    relationships: list[dict] = []
    max_gen_reached = 0

    if direction == "ancestors":
        _walk_ancestors(root_id, 0, generations, by_id, collected_ids,
                        relationships)
    else:
        _walk_descendants(root_id, 0, generations, by_id, collected_ids,
                          relationships)

    if relationships:
        max_gen_reached = max(r["generation"] for r in relationships)

    persons = [by_id[pid] for pid in collected_ids if pid in by_id]

    # Deduplicate relationships (same pair can be reached via multiple paths
    # in endogamous trees).
    seen_rels: set[tuple] = set()
    unique_rels: list[dict] = []
    for rel in relationships:
        key = (rel["child_id"], rel["parent_id"], rel["role"])
        if key not in seen_rels:
            seen_rels.add(key)
            unique_rels.append(rel)

    return {
        "persons": persons,
        "relationships": unique_rels,
        "root": root,
        "generations_reached": max_gen_reached,
    }


def extract_all_relationships(
    gedcom_persons: list[dict],
    root_id: str,
    generations: int = 3,
) -> list[dict]:
    """Return every relationship in the subtree (ancestors + descendants).

    Each relationship dict:
        {
            "child_id":   str,
            "parent_id":  str,
            "role":       "father" | "mother",
            "generation": int (distance from root),
            "child":      dict (person dict),
            "parent":     dict (person dict),
        }
    """
    by_id = {p["id"]: p for p in gedcom_persons}

    # Collect from both directions.
    anc = extract_subtree(gedcom_persons, root_id, generations, "ancestors")
    desc = extract_subtree(gedcom_persons, root_id, generations, "descendants")

    # Merge and deduplicate.
    seen: set[tuple] = set()
    merged: list[dict] = []
    for rel in anc["relationships"] + desc["relationships"]:
        key = (rel["child_id"], rel["parent_id"], rel["role"])
        if key in seen:
            continue
        seen.add(key)

        child = by_id.get(rel["child_id"])
        parent = by_id.get(rel["parent_id"])
        if child and parent:
            merged.append({
                **rel,
                "child": child,
                "parent": parent,
            })

    return merged


# ---------------------------------------------------------------------------
# Tree traversal helpers
# ---------------------------------------------------------------------------


def _walk_ancestors(
    person_id: str,
    current_gen: int,
    max_gen: int,
    by_id: dict[str, dict],
    collected: set[str],
    relationships: list[dict],
) -> None:
    """Recursively walk up parent links, collecting persons and relationships."""
    person = by_id.get(person_id)
    if not person:
        return
    collected.add(person_id)

    if current_gen >= max_gen:
        return

    for role, parent_key in [("father", "father_id"), ("mother", "mother_id")]:
        parent_id = person.get(parent_key)
        if not parent_id or parent_id not in by_id:
            continue

        gen = current_gen + 1
        relationships.append({
            "child_id": person_id,
            "parent_id": parent_id,
            "role": role,
            "generation": gen,
        })
        collected.add(parent_id)

        # Also collect the parent's spouse (the other parent at this level).
        parent = by_id[parent_id]
        for spouse_id in parent.get("spouse_ids") or []:
            if spouse_id in by_id:
                collected.add(spouse_id)

        _walk_ancestors(parent_id, gen, max_gen, by_id, collected,
                        relationships)


def _walk_descendants(
    person_id: str,
    current_gen: int,
    max_gen: int,
    by_id: dict[str, dict],
    collected: set[str],
    relationships: list[dict],
) -> None:
    """Recursively walk down children links."""
    person = by_id.get(person_id)
    if not person:
        return
    collected.add(person_id)

    if current_gen >= max_gen:
        return

    for child_id in person.get("children_ids") or []:
        if child_id not in by_id:
            continue

        child = by_id[child_id]
        gen = current_gen + 1

        # Determine role: is this person the father or mother?
        role = "father"
        if person.get("sex") == "F":
            role = "mother"

        relationships.append({
            "child_id": child_id,
            "parent_id": person_id,
            "role": role,
            "generation": gen,
        })
        collected.add(child_id)

        # Collect spouses of the child.
        for spouse_id in child.get("spouse_ids") or []:
            if spouse_id in by_id:
                collected.add(spouse_id)

        _walk_descendants(child_id, gen, max_gen, by_id, collected,
                          relationships)
