"""DNA match file parser — normalizes GEDmatch and MyHeritage CSV formats.

Detects the platform from column headers and normalizes each match into
a common dict format so the DNA Analyst agent can process matches from
any supported platform identically.

Supported platforms:
    GEDmatch:    columns include 'Match Nomber', 'Autosomal Total cM', 'Gen'
    MyHeritage:  columns include 'Match Name', 'Shared cM', 'Estimated Relationship'

Public functions:
    parse_dna_file(file_path) -> dict
    parse_dna_text(text, filename_hint="") -> dict

Return format:
    {
        "platform":      "gedmatch" | "myheritage" | "unknown",
        "subject_name":  str | None,
        "matches":       list[dict],
        "total_count":   int,
    }

Each match dict:
    {
        "match_id":             str,
        "name":                 str,
        "shared_cM":            float,
        "largest_segment":      float | None,
        "num_segments":         int | None,
        "platform_prediction":  str | None,
        "source_platform":      str,
        "has_real_name":        bool,
    }
"""

from __future__ import annotations

import csv
import io
import os
import re
import tempfile
from pathlib import Path
from typing import Optional


def parse_dna_file(file_path: str) -> dict:
    """Parse a DNA match CSV file from disk."""
    path = Path(file_path)
    # Try utf-8-sig (handles BOM), fall back to latin-1.
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        return _empty_result("unknown")

    return parse_dna_text(text, filename_hint=path.name)


def parse_dna_text(text: str, filename_hint: str = "") -> dict:
    """Parse DNA match CSV content from a string (e.g. Streamlit upload)."""
    if not text or not text.strip():
        return _empty_result("unknown")

    # Normalize line endings and detect platform from header.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    reader = csv.DictReader(io.StringIO(text))
    headers = set(reader.fieldnames or [])

    if _is_gedmatch(headers):
        return _parse_gedmatch(reader, filename_hint)
    if _is_myheritage(headers):
        return _parse_myheritage(reader, filename_hint)

    return _empty_result("unknown")


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------


def _is_gedmatch(headers: set[str]) -> bool:
    return "Autosomal Total cM" in headers and "Match Nomber" in headers


def _is_myheritage(headers: set[str]) -> bool:
    # MyHeritage exports vary; check common column names.
    return (
        ("Match Name" in headers or "Name" in headers)
        and ("Shared cM" in headers or "Shared DNA" in headers)
    )


# ---------------------------------------------------------------------------
# GEDmatch parser
# ---------------------------------------------------------------------------


def _parse_gedmatch(reader: csv.DictReader, filename_hint: str) -> dict:
    matches: list[dict] = []
    for row_num, row in enumerate(reader, start=1):
        shared_cm = _parse_float(row.get("Autosomal Total cM"))
        if shared_cm is None:
            continue  # skip rows with empty/invalid cM

        largest_raw = row.get("Autosomal Largest") or ""
        largest_segment = _parse_float(_strip_qualifiers(largest_raw))

        gen_raw = (row.get("Gen") or "").strip()
        platform_prediction = f"Gen {gen_raw}" if gen_raw else None

        name = (row.get("Name/Alias") or "").strip()
        kit = (row.get("Kit") or "").strip()

        matches.append({
            "match_id": kit or f"gedmatch-{row_num}",
            "name": name or kit or f"Match #{row_num}",
            "shared_cM": shared_cm,
            "largest_segment": largest_segment,
            "num_segments": None,  # GEDmatch doesn't provide segment count
            "platform_prediction": platform_prediction,
            "source_platform": "gedmatch",
            "has_real_name": False,  # GEDmatch uses aliases
        })

    subject_name = _guess_subject_from_filename(filename_hint)

    return {
        "platform": "gedmatch",
        "subject_name": subject_name,
        "matches": matches,
        "total_count": len(matches),
    }


# ---------------------------------------------------------------------------
# MyHeritage parser
# ---------------------------------------------------------------------------


def _parse_myheritage(reader: csv.DictReader, filename_hint: str) -> dict:
    matches: list[dict] = []
    for row_num, row in enumerate(reader, start=1):
        # MyHeritage column names can vary slightly.
        shared_cm = _parse_float(
            row.get("Shared cM")
            or row.get("Shared DNA")
            or row.get("Total cM")
        )
        if shared_cm is None:
            continue

        largest_segment = _parse_float(
            row.get("Largest Segment")
            or row.get("Largest Segment (cM)")
        )
        num_segments = _parse_int(
            row.get("Shared Segments")
            or row.get("Number of Segments")
        )

        name = (
            row.get("Match Name")
            or row.get("Name")
            or ""
        ).strip()

        estimated_rel = (
            row.get("Estimated Relationship")
            or row.get("Estimated relationship")
            or ""
        ).strip()

        matches.append({
            "match_id": f"myheritage-{row_num}",
            "name": name or f"Match #{row_num}",
            "shared_cM": shared_cm,
            "largest_segment": largest_segment,
            "num_segments": num_segments,
            "platform_prediction": estimated_rel or None,
            "source_platform": "myheritage",
            "has_real_name": bool(name),
        })

    subject_name = _guess_subject_from_filename(filename_hint)

    return {
        "platform": "myheritage",
        "subject_name": subject_name,
        "matches": matches,
        "total_count": len(matches),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_float(value) -> Optional[float]:
    if value is None:
        return None
    cleaned = _strip_qualifiers(str(value))
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _strip_qualifiers(value: str) -> str:
    """Remove non-breaking spaces, 'Q' suffixes, commas, and whitespace
    from numeric values. GEDmatch uses '\xa0Q' after some cM values.
    """
    cleaned = value.replace("\xa0", " ").strip()
    cleaned = re.sub(r"[QqCc%]", "", cleaned)
    cleaned = cleaned.replace(",", "").strip()
    return cleaned


def _guess_subject_from_filename(filename: str) -> Optional[str]:
    """Try to extract the subject's name from the CSV filename."""
    name = Path(filename).stem
    # Common patterns: "GEDMATH-JamesMoore", "Jim_Moore_..._MyHeritage_Match_List"
    # Remove platform suffixes.
    for suffix in ("_MyHeritage_Match_List", "_Match_List", "_DNA"):
        name = name.replace(suffix, "")
    # Split on common delimiters.
    name = name.replace("-", " ").replace("_", " ")
    # Remove "GEDMATH" prefix.
    name = re.sub(r"^GEDMATH?\s*", "", name, flags=re.IGNORECASE)
    name = name.strip()
    return name if name else None


def _empty_result(platform: str) -> dict:
    return {
        "platform": platform,
        "subject_name": None,
        "matches": [],
        "total_count": 0,
    }
