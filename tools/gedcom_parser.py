"""GEDCOM parser — wraps python-gedcom-2 to return normalized person dicts.

Exposes two public functions:
    parse_gedcom_file(path)  -> list[dict]
    parse_gedcom_text(text)  -> list[dict]

Each person dict has the shape:
    {
        "id":           "@I0@",                   # GEDCOM pointer
        "name":         "John Fitzgerald Kennedy",
        "first_name":   "John Fitzgerald",
        "surname":      "Kennedy",
        "sex":          "M" | "F" | None,
        "birth_date":   "29 MAY 1917" | None,     # raw GEDCOM date string
        "birth_place":  "Brookline, MA" | None,
        "death_date":   "22 NOV 1963" | None,
        "death_place":  "Dallas, TX" | None,
        "father_id":    "@I1@" | None,
        "mother_id":    "@I2@" | None,
        "spouse_ids":   ["@I5@", ...],
        "children_ids": ["@I10@", ...],
        "famc":         ["@F0@", ...],            # raw family-as-child pointers
        "fams":         ["@F10@", ...],           # raw family-as-spouse pointers
    }

Date parsing and impossibility checks live in tools/date_utils.py (Step 4) —
this module returns raw strings so downstream tools can normalize them.
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional

from python_gedcom_2.element.family import FamilyElement
from python_gedcom_2.element.individual import IndividualElement
from python_gedcom_2.parser import Parser


def parse_gedcom_file(path: str) -> list[dict]:
    """Parse a .ged file from disk into a list of person dicts."""
    parser = Parser()
    # strict=False tolerates common format deviations (the Kennedy file triggers them)
    parser.parse_file(path, False)
    return _extract_persons(parser)


def parse_gedcom_text(gedcom_text: str) -> list[dict]:
    """Parse GEDCOM content passed as a string (e.g. state['gedcom_text']).

    python-gedcom-2's Parser only exposes parse_file, so we round-trip through
    a temp file. This keeps the public API string-friendly for LangGraph state.
    """
    tf = tempfile.NamedTemporaryFile(
        mode="w", suffix=".ged", delete=False, encoding="utf-8"
    )
    try:
        tf.write(gedcom_text)
        tf.close()
        return parse_gedcom_file(tf.name)
    finally:
        os.unlink(tf.name)


def _extract_persons(parser: Parser) -> list[dict]:
    root_elements = parser.get_root_child_elements()

    individuals = [e for e in root_elements if isinstance(e, IndividualElement)]
    family_index = _build_family_index(
        [e for e in root_elements if isinstance(e, FamilyElement)]
    )

    return [_person_to_dict(ind, family_index) for ind in individuals]


def _build_family_index(family_elements: list[FamilyElement]) -> dict[str, dict]:
    """Map family pointer → {husband, wife, children} of GEDCOM pointers."""
    index: dict[str, dict] = {}
    for fam in family_elements:
        husband: Optional[str] = None
        wife: Optional[str] = None
        children: list[str] = []
        for child in fam.get_child_elements():
            tag = child.get_tag()
            value = (child.get_value() or "").strip()
            if tag == "HUSB":
                husband = value or None
            elif tag == "WIFE":
                wife = value or None
            elif tag == "CHIL" and value:
                children.append(value)
        index[fam.get_pointer()] = {
            "husband": husband,
            "wife": wife,
            "children": children,
        }
    return index


def _person_to_dict(
    ind: IndividualElement, family_index: dict[str, dict]
) -> dict:
    first, last = ind.get_name()
    full_name = " ".join(part for part in (first, last) if part).strip()

    birth_date, birth_place, _sources = ind.get_birth_data()
    death_date, death_place, _sources = ind.get_death_data()

    famc_pointers, fams_pointers = _collect_family_pointers(ind)

    father_id, mother_id = _resolve_parents(famc_pointers, family_index)
    spouse_ids, children_ids = _resolve_spouse_and_children(
        ind.get_pointer(), fams_pointers, family_index
    )

    return {
        "id": ind.get_pointer(),
        "name": full_name or None,
        "first_name": first or None,
        "surname": last or None,
        "sex": ind.get_gender() or None,
        "birth_date": birth_date or None,
        "birth_place": birth_place or None,
        "death_date": death_date or None,
        "death_place": death_place or None,
        "father_id": father_id,
        "mother_id": mother_id,
        "spouse_ids": spouse_ids,
        "children_ids": children_ids,
        "famc": famc_pointers,
        "fams": fams_pointers,
    }


def _collect_family_pointers(
    ind: IndividualElement,
) -> tuple[list[str], list[str]]:
    famc: list[str] = []
    fams: list[str] = []
    for child in ind.get_child_elements():
        tag = child.get_tag()
        value = (child.get_value() or "").strip()
        if not value:
            continue
        if tag == "FAMC":
            famc.append(value)
        elif tag == "FAMS":
            fams.append(value)
    return famc, fams


def _resolve_parents(
    famc_pointers: list[str], family_index: dict[str, dict]
) -> tuple[Optional[str], Optional[str]]:
    father_id: Optional[str] = None
    mother_id: Optional[str] = None
    for fc in famc_pointers:
        fam = family_index.get(fc)
        if not fam:
            continue
        father_id = father_id or fam["husband"]
        mother_id = mother_id or fam["wife"]
    return father_id, mother_id


def _resolve_spouse_and_children(
    person_pointer: str,
    fams_pointers: list[str],
    family_index: dict[str, dict],
) -> tuple[list[str], list[str]]:
    spouse_ids: list[str] = []
    children_ids: list[str] = []
    for fs in fams_pointers:
        fam = family_index.get(fs)
        if not fam:
            continue
        for role in ("husband", "wife"):
            partner = fam[role]
            if partner and partner != person_pointer and partner not in spouse_ids:
                spouse_ids.append(partner)
        for child_ptr in fam["children"]:
            if child_ptr not in children_ids:
                children_ids.append(child_ptr)
    return spouse_ids, children_ids
