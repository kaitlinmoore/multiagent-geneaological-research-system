"""Generate Tier 3 trap GEDCOMs by modifying the Kennedy family file.

Tier 3 cases need real-tree context to be realistic, so these are produced
as derived copies of data/The Kennedy Family.ged with fictional records
injected. The original file is never modified; this script reads it and
writes new .ged files alongside the rest of the trap cases.

Run once after any change to the source or to this script:

    ./.venv/Scripts/python.exe eval/trap_cases/build_tier3_traps.py

Both outputs are checked into git so evaluation is reproducible without
re-running this script.

Traps produced:
  tier3_kennedy_duplicate_john.ged   — injects a fictional "John Kennedy"
                                       born 1917 in Boston with plausible
                                       but different parents. A query for
                                       "John Kennedy born 1917 Boston"
                                       matches both the real JFK and the
                                       injected duplicate. Ground truth:
                                       genuinely ambiguous — no single-
                                       candidate answer is defensible from
                                       the tree alone.
  tier3_kennedy_ambiguous_joseph.ged — injects a fictional "Joseph Patrick
                                       Kennedy" whose birth year overlaps
                                       with the real Joseph Sr (b.1888).
                                       Different middle/none, different
                                       birthplace. Tests whether the system
                                       can distinguish near-name-collisions.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE_GED = REPO_ROOT / "data" / "The Kennedy Family.ged"
OUT_DIR = REPO_ROOT / "eval" / "trap_cases"


# ---------------------------------------------------------------------------
# Injected records — each a self-contained block of GEDCOM lines to insert
# before the 0 TRLR terminator. Uses pointer ids in the @I100@+ / @F100@+
# range to avoid collision with the real tree (which uses @I0@–@I69@).
# ---------------------------------------------------------------------------


_DUPLICATE_JOHN_BLOCK = """\
0 @I100@ INDI
1 NAME John /Kennedy/
1 SEX M
1 BIRT
2 DATE 15 JUL 1917
2 PLAC Boston, Massachusetts
1 DEAT
2 DATE 3 SEP 1975
2 PLAC Worcester, Massachusetts
1 FAMC @F100@
0 @I101@ INDI
1 NAME Daniel /Kennedy/
1 SEX M
1 BIRT
2 DATE 20 OCT 1880
2 PLAC Boston, Massachusetts
1 DEAT
2 DATE 11 FEB 1951
2 PLAC Boston, Massachusetts
1 FAMS @F100@
0 @I102@ INDI
1 NAME Margaret /O'Shea/
1 SEX F
1 BIRT
2 DATE 2 MAR 1884
2 PLAC Boston, Massachusetts
1 DEAT
2 DATE 19 AUG 1960
2 PLAC Boston, Massachusetts
1 FAMS @F100@
0 @F100@ FAM
1 HUSB @I101@
1 WIFE @I102@
1 CHIL @I100@
"""


_AMBIGUOUS_JOSEPH_BLOCK = """\
0 @I110@ INDI
1 NAME Joseph Patrick /Kennedy/
1 SEX M
1 BIRT
2 DATE 22 NOV 1886
2 PLAC Lowell, Massachusetts
1 DEAT
2 DATE 5 JUL 1955
2 PLAC Lowell, Massachusetts
1 FAMC @F110@
0 @I111@ INDI
1 NAME Thomas /Kennedy/
1 SEX M
1 BIRT
2 DATE 8 APR 1855
2 PLAC Lowell, Massachusetts
1 DEAT
2 DATE 30 JAN 1925
2 PLAC Lowell, Massachusetts
1 FAMS @F110@
0 @I112@ INDI
1 NAME Catherine /Dolan/
1 SEX F
1 BIRT
2 DATE 17 SEP 1858
2 PLAC Lowell, Massachusetts
1 DEAT
2 DATE 14 MAY 1930
2 PLAC Lowell, Massachusetts
1 FAMS @F110@
0 @F110@ FAM
1 HUSB @I111@
1 WIFE @I112@
1 CHIL @I110@
"""


def _inject_before_trailer(source_text: str, block: str) -> str:
    """Insert ``block`` just before the ``0 TRLR`` terminator line."""
    marker = "0 TRLR"
    idx = source_text.rfind(marker)
    if idx == -1:
        raise ValueError("Source GEDCOM has no 0 TRLR line")
    return source_text[:idx] + block + source_text[idx:]


def _build_with_note(original: str, note_lines: list[str], block: str) -> str:
    """Append a NOTE to HEAD explaining the modification, then inject block."""
    # Insert NOTE right after the CHAR UTF-8 line of the HEAD section if present.
    lines = original.splitlines(keepends=True)
    char_idx = next(
        (i for i, line in enumerate(lines) if line.strip() == "1 CHAR UTF-8"),
        None,
    )
    note_block_lines: list[str] = []
    first = True
    for note_line in note_lines:
        tag = "NOTE" if first else "CONT"
        note_block_lines.append(f"1 {tag} {note_line}\n" if first
                                else f"2 {tag} {note_line}\n")
        first = False
    if char_idx is not None:
        lines[char_idx + 1:char_idx + 1] = note_block_lines
    modified = "".join(lines)
    return _inject_before_trailer(modified, block)


def main() -> None:
    if not SOURCE_GED.exists():
        raise SystemExit(f"source not found: {SOURCE_GED}")
    original = SOURCE_GED.read_text(encoding="utf-8", errors="replace")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Trap A: injected duplicate John Kennedy
    out_a = OUT_DIR / "tier3_kennedy_duplicate_john.ged"
    content_a = _build_with_note(
        original,
        note_lines=[
            "Tier 3 ambiguity trap: derived from data/The Kennedy Family.ged",
            "with fictional John Kennedy (@I100@) injected — same first name,",
            "same surname, same birth year (1917), same birthplace (Boston,",
            "Massachusetts) as the real JFK (@I0@). A query for 'John Kennedy",
            "born 1917 Boston' cannot be disambiguated from the tree alone.",
            "Expected system behavior: flag_uncertain, Critic self-confidence",
            "should be LOW (not an overconfident accept or reject).",
        ],
        block=_DUPLICATE_JOHN_BLOCK,
    )
    out_a.write_text(content_a, encoding="utf-8")
    print(f"wrote {out_a}")

    # Trap B: ambiguous Joseph Patrick Kennedy
    out_b = OUT_DIR / "tier3_kennedy_ambiguous_joseph.ged"
    content_b = _build_with_note(
        original,
        note_lines=[
            "Tier 3 ambiguity trap: derived from data/The Kennedy Family.ged",
            "with fictional Joseph Patrick Kennedy (@I110@) injected —",
            "identical name to the real Joseph Sr (@I1@, b.1888 Boston),",
            "birth year off by 2 (1886), birthplace Lowell, Massachusetts",
            "instead of Boston. A query for 'Joseph Patrick Kennedy born",
            "c. 1888 Massachusetts' produces two near-equally-scoring",
            "candidates. Expected: flag_uncertain with LOW Critic confidence;",
            "a system that confidently accepts either is overconfident.",
        ],
        block=_AMBIGUOUS_JOSEPH_BLOCK,
    )
    out_b.write_text(content_b, encoding="utf-8")
    print(f"wrote {out_b}")


if __name__ == "__main__":
    main()
