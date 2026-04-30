"""GEDCOM date normalization + Tier 1 deterministic impossibility checks.

Design contract:
  - The impossibility check functions accept RAW GEDCOM date strings directly
    (exactly what tools.gedcom_parser returns). No preprocessing required.
  - Normalization (`normalize_gedcom_date`) and rule checks share internals so
    the Adversarial Critic can call either layer without glue code.
  - Rule checks are deterministic Tier 1 detectors — they MUST run BEFORE any
    LLM reasoning in the Critic.

Supported GEDCOM date forms:
  Exact:        "29 MAY 1917", "MAY 1917", "1917"
  Qualified:    "ABT 1917", "CAL 1920", "EST 1850", "BEF 1920", "AFT 1850"
  Interval:     "BET 1850 AND 1860", "FROM 1850 TO 1860"

Normalized output shape:
  {
    "raw":       original string (unchanged),
    "qualifier": one of None | "ABT" | "CAL" | "EST" | "BEF" | "AFT" | "BET" | "FROM",
    "earliest":  datetime.date | None   # earliest possible instant
    "latest":    datetime.date | None   # latest possible instant
    "point":     datetime.date | None   # central estimate, or None for open-ended
    "parseable": bool
  }

`earliest` and `latest` are the uncertainty envelope. Rule checks compare
envelopes, so qualified dates propagate uncertainty correctly: an ABT date
that happens to straddle a boundary returns "insufficient_data", not "impossible".

Rule check return shape:
  {
    "check":   canonical check name,
    "verdict": "impossible" | "ok" | "insufficient_data",
    "reason":  short human-readable explanation (Critic can cite directly),
  }
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from dateutil.parser import ParserError
from dateutil.parser import parse as dateutil_parse
from dateutil.relativedelta import relativedelta


# ---------------------------------------------------------------------------
# Constants — biological / physical floors used by rule checks.
# ---------------------------------------------------------------------------

# Uncertainty envelopes applied to qualifiers that don't specify bounds.
# Conservative: wider envelopes → fewer false "impossible" verdicts.
_ABOUT_YEARS = 5      # ABT, CAL — ±5 years
_ESTIMATE_YEARS = 10  # EST — ±10 years

# Biological floors for parenting / marriage.
_MIN_MOTHER_AGE = 12      # earliest plausible maternal age
_MIN_FATHER_AGE = 12      # earliest plausible paternal age
_MAX_MOTHER_AGE = 55      # oldest plausible maternal age (upper floor, soft)
_MAX_FATHER_AGE = 85      # oldest plausible paternal age (rare, soft)
_MIN_MARRIAGE_AGE = 12    # below this = impossible marriage
_MAX_HUMAN_LIFESPAN = 120 # above this = impossible lifespan

# Approximate human gestation — used for "parent died before conception" checks.
_GESTATION_DAYS = 280


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


@dataclass
class NormalizedDate:
    raw: str
    qualifier: Optional[str]
    earliest: Optional[date]
    latest: Optional[date]
    point: Optional[date]
    parseable: bool

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "qualifier": self.qualifier,
            "earliest": self.earliest,
            "latest": self.latest,
            "point": self.point,
            "parseable": self.parseable,
        }


_UNPARSEABLE = NormalizedDate(
    raw="",
    qualifier=None,
    earliest=None,
    latest=None,
    point=None,
    parseable=False,
)


def normalize_gedcom_date(raw: Optional[str]) -> dict:
    """Normalize a raw GEDCOM date string to an uncertainty envelope dict.

    Always returns a dict with the full shape — None / unparseable inputs
    produce ``parseable=False`` with envelope fields set to None so callers
    can safely branch on ``parseable``.
    """
    if raw is None:
        return _UNPARSEABLE.to_dict() | {"raw": ""}

    text = raw.strip().upper()
    if not text:
        return _UNPARSEABLE.to_dict() | {"raw": raw}

    try:
        normalized = _parse_qualified(text, raw)
    except (ParserError, ValueError):
        normalized = NormalizedDate(
            raw=raw,
            qualifier=None,
            earliest=None,
            latest=None,
            point=None,
            parseable=False,
        )
    return normalized.to_dict()


def _parse_qualified(text: str, original: str) -> NormalizedDate:
    # Interval forms: BET X AND Y, FROM X TO Y
    bet_match = re.match(r"^BET\s+(.+?)\s+AND\s+(.+)$", text)
    if bet_match:
        start = _parse_date_value(bet_match.group(1))
        end = _parse_date_value(bet_match.group(2))
        return NormalizedDate(
            raw=original,
            qualifier="BET",
            earliest=start[0],
            latest=end[1],
            point=_midpoint(start[0], end[1]),
            parseable=True,
        )

    from_match = re.match(r"^FROM\s+(.+?)\s+TO\s+(.+)$", text)
    if from_match:
        start = _parse_date_value(from_match.group(1))
        end = _parse_date_value(from_match.group(2))
        return NormalizedDate(
            raw=original,
            qualifier="FROM",
            earliest=start[0],
            latest=end[1],
            point=_midpoint(start[0], end[1]),
            parseable=True,
        )

    from_only = re.match(r"^FROM\s+(.+)$", text)
    if from_only:
        start = _parse_date_value(from_only.group(1))
        return NormalizedDate(
            raw=original,
            qualifier="FROM",
            earliest=start[0],
            latest=None,
            point=start[0],
            parseable=True,
        )

    # Simple qualifiers: ABT, CAL, EST, BEF, AFT
    qual_match = re.match(r"^(ABT|ABOUT|CAL|EST|BEF|BEFORE|AFT|AFTER)\s+(.+)$", text)
    if qual_match:
        qualifier_raw = qual_match.group(1)
        earliest_raw, latest_raw = _parse_date_value(qual_match.group(2))
        qualifier = _canonicalize_qualifier(qualifier_raw)
        earliest, latest = _apply_qualifier(qualifier, earliest_raw, latest_raw)
        point = _midpoint(earliest_raw, latest_raw)
        return NormalizedDate(
            raw=original,
            qualifier=qualifier,
            earliest=earliest,
            latest=latest,
            point=point,
            parseable=True,
        )

    # Unqualified — exact / month-year / year-only
    earliest, latest = _parse_date_value(text)
    return NormalizedDate(
        raw=original,
        qualifier=None,
        earliest=earliest,
        latest=latest,
        point=_midpoint(earliest, latest),
        parseable=earliest is not None,
    )


def _canonicalize_qualifier(raw: str) -> str:
    """Map GEDCOM qualifier aliases to canonical three-letter forms."""
    mapping = {
        "ABOUT": "ABT",
        "BEFORE": "BEF",
        "AFTER": "AFT",
    }
    return mapping.get(raw, raw)


def _parse_date_value(value: str) -> tuple[Optional[date], Optional[date]]:
    """Parse a single unqualified GEDCOM date value into (earliest, latest).

    Year-only → Jan 1 – Dec 31 of that year.
    Month-year → 1st – last day of that month.
    Full date → same date twice.
    """
    text = value.strip()
    if not text:
        return (None, None)

    # Year-only: "1917"
    if re.fullmatch(r"\d{1,4}", text):
        year = int(text)
        return (date(year, 1, 1), date(year, 12, 31))

    # Month-year: "MAY 1917"
    month_year_match = re.fullmatch(r"([A-Z]{3,9})\s+(\d{1,4})", text)
    if month_year_match:
        parsed = dateutil_parse(text, default=datetime(1, 1, 1))
        year, month = parsed.year, parsed.month
        earliest = date(year, month, 1)
        latest = _end_of_month(year, month)
        return (earliest, latest)

    # Full date ("29 MAY 1917" or "1917-05-29" etc.) — let dateutil resolve.
    parsed = dateutil_parse(text, default=datetime(1, 1, 1))
    exact = parsed.date()
    return (exact, exact)


def _apply_qualifier(
    qualifier: str,
    earliest: Optional[date],
    latest: Optional[date],
) -> tuple[Optional[date], Optional[date]]:
    if qualifier == "ABT" or qualifier == "CAL":
        e = earliest - relativedelta(years=_ABOUT_YEARS) if earliest else None
        l = latest + relativedelta(years=_ABOUT_YEARS) if latest else None
        return (e, l)
    if qualifier == "EST":
        e = earliest - relativedelta(years=_ESTIMATE_YEARS) if earliest else None
        l = latest + relativedelta(years=_ESTIMATE_YEARS) if latest else None
        return (e, l)
    if qualifier == "BEF":
        # "BEF 1920" → strictly before start of that envelope
        l = earliest - relativedelta(days=1) if earliest else None
        return (None, l)
    if qualifier == "AFT":
        # "AFT 1850" → strictly after end of that envelope
        e = latest + relativedelta(days=1) if latest else None
        return (e, None)
    return (earliest, latest)


def _end_of_month(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - relativedelta(days=1)


def _midpoint(
    earliest: Optional[date], latest: Optional[date]
) -> Optional[date]:
    if earliest is None and latest is None:
        return None
    if earliest is None:
        return latest
    if latest is None:
        return earliest
    delta_days = (latest - earliest).days // 2
    return earliest + relativedelta(days=delta_days)


def get_year(raw: Optional[str]) -> Optional[int]:
    """Convenience: return the central-estimate year for a raw GEDCOM date."""
    normalized = normalize_gedcom_date(raw)
    if normalized["point"]:
        return normalized["point"].year
    return None


# ---------------------------------------------------------------------------
# Deterministic Tier 1 rule checks.
# All accept raw GEDCOM date strings; all return a check result dict.
# ---------------------------------------------------------------------------


def _result(check: str, verdict: str, reason: str) -> dict:
    return {"check": check, "verdict": verdict, "reason": reason}


def check_death_before_birth(birth_raw: Optional[str], death_raw: Optional[str]) -> dict:
    """Death cannot precede birth."""
    check = "death_before_birth"
    birth = normalize_gedcom_date(birth_raw)
    death = normalize_gedcom_date(death_raw)
    if not birth["parseable"] or not death["parseable"]:
        return _result(check, "insufficient_data", "missing or unparseable date")

    # Compare the tightest possible envelope: if the latest possible death is
    # still before the earliest possible birth, death strictly precedes birth.
    if death["latest"] and birth["earliest"] and death["latest"] < birth["earliest"]:
        return _result(
            check,
            "impossible",
            f"latest possible death {death['latest']} is before earliest possible birth {birth['earliest']}",
        )
    return _result(check, "ok", "death is not before birth")


def check_implausible_lifespan(
    birth_raw: Optional[str],
    death_raw: Optional[str],
    max_years: int = _MAX_HUMAN_LIFESPAN,
) -> dict:
    """Lifespan cannot exceed documented human maximum."""
    check = "implausible_lifespan"
    birth = normalize_gedcom_date(birth_raw)
    death = normalize_gedcom_date(death_raw)
    if not birth["parseable"] or not death["parseable"]:
        return _result(check, "insufficient_data", "missing or unparseable date")

    # Smallest possible lifespan: death.earliest - birth.latest.
    # If even that exceeds max_years, it's impossible.
    if death["earliest"] and birth["latest"]:
        minimum_years = relativedelta(death["earliest"], birth["latest"]).years
        if minimum_years > max_years:
            return _result(
                check,
                "impossible",
                f"minimum lifespan {minimum_years}y exceeds max {max_years}y",
            )
    return _result(check, "ok", f"lifespan within {max_years} years")


def check_parent_younger_than_child(
    parent_birth_raw: Optional[str],
    child_birth_raw: Optional[str],
) -> dict:
    """Parent cannot be born after their child."""
    check = "parent_younger_than_child"
    parent = normalize_gedcom_date(parent_birth_raw)
    child = normalize_gedcom_date(child_birth_raw)
    if not parent["parseable"] or not child["parseable"]:
        return _result(check, "insufficient_data", "missing or unparseable date")

    if parent["earliest"] and child["latest"] and parent["earliest"] > child["latest"]:
        return _result(
            check,
            "impossible",
            f"parent earliest birth {parent['earliest']} is after child latest birth {child['latest']}",
        )
    return _result(check, "ok", "parent is not younger than child")


def check_parent_too_young_at_birth(
    parent_birth_raw: Optional[str],
    child_birth_raw: Optional[str],
    min_age: int = _MIN_MOTHER_AGE,
) -> dict:
    """Parent's minimum plausible age at child's birth must meet biological floor."""
    check = "parent_too_young_at_birth"
    parent = normalize_gedcom_date(parent_birth_raw)
    child = normalize_gedcom_date(child_birth_raw)
    if not parent["parseable"] or not child["parseable"]:
        return _result(check, "insufficient_data", "missing or unparseable date")

    # Minimum plausible age = earliest child birth - latest parent birth.
    if parent["latest"] and child["earliest"]:
        age = relativedelta(child["earliest"], parent["latest"]).years
        if age < min_age:
            return _result(
                check,
                "impossible",
                f"parent would have been at most {age}y at child's birth (min {min_age}y)",
            )
    return _result(check, "ok", f"parent age plausible (>= {min_age})")


def check_parent_died_before_conception(
    parent_death_raw: Optional[str],
    child_birth_raw: Optional[str],
    parent_sex: Optional[str] = None,
) -> dict:
    """Father must be alive ~9mo before birth; mother must be alive at birth.

    If ``parent_sex`` is unknown, apply the father rule (looser) to avoid
    false positives on ambiguous records.
    """
    check = "parent_died_before_conception"
    death = normalize_gedcom_date(parent_death_raw)
    birth = normalize_gedcom_date(child_birth_raw)
    if not death["parseable"] or not birth["parseable"]:
        return _result(check, "insufficient_data", "missing or unparseable date")

    # Mother: must be alive at child's earliest birth. Father: alive ~9mo before.
    if parent_sex == "F":
        latest_allowed_death = birth["earliest"]
        rule = "mother alive at birth"
    else:
        latest_allowed_death = (
            birth["earliest"] - relativedelta(days=_GESTATION_DAYS)
            if birth["earliest"]
            else None
        )
        rule = "father alive ~9mo before birth"

    if death["latest"] and latest_allowed_death and death["latest"] < latest_allowed_death:
        return _result(
            check,
            "impossible",
            f"{rule}: latest death {death['latest']} precedes required {latest_allowed_death}",
        )
    return _result(check, "ok", f"{rule} holds")


def check_marriage_under_age(
    person_birth_raw: Optional[str],
    marriage_raw: Optional[str],
    min_age: int = _MIN_MARRIAGE_AGE,
) -> dict:
    """Marriage before biological floor is impossible."""
    check = "marriage_under_age"
    birth = normalize_gedcom_date(person_birth_raw)
    marriage = normalize_gedcom_date(marriage_raw)
    if not birth["parseable"] or not marriage["parseable"]:
        return _result(check, "insufficient_data", "missing or unparseable date")

    if marriage["latest"] and birth["latest"]:
        max_age = relativedelta(marriage["latest"], birth["latest"]).years
        if max_age < min_age:
            return _result(
                check,
                "impossible",
                f"person would have been at most {max_age}y at marriage (min {min_age}y)",
            )
    return _result(check, "ok", f"marriage age plausible (>= {min_age})")


def run_all_tier1_checks(
    person: dict,
    father: Optional[dict] = None,
    mother: Optional[dict] = None,
) -> list[dict]:
    """Convenience: run every Tier 1 check that applies to a person dict.

    Accepts parser-output dicts (keys: birth_date, death_date, sex, ...) and
    any available parent dicts. Returns a flat list of check results with
    'impossible' verdicts first so the Critic can short-circuit on hard failures.
    """
    results: list[dict] = []
    birth = person.get("birth_date")
    death = person.get("death_date")

    results.append(check_death_before_birth(birth, death))
    results.append(check_implausible_lifespan(birth, death))

    for parent, role in ((father, "father"), (mother, "mother")):
        if not parent:
            continue
        parent_birth = parent.get("birth_date")
        parent_death = parent.get("death_date")
        parent_sex = parent.get("sex") or ("F" if role == "mother" else "M")
        results.append(
            {
                **check_parent_younger_than_child(parent_birth, birth),
                "role": role,
            }
        )
        results.append(
            {
                **check_parent_too_young_at_birth(parent_birth, birth),
                "role": role,
            }
        )
        results.append(
            {
                **check_parent_died_before_conception(parent_death, birth, parent_sex),
                "role": role,
            }
        )

    # Sort impossible first, insufficient_data last.
    priority = {"impossible": 0, "ok": 1, "insufficient_data": 2}
    results.sort(key=lambda r: priority.get(r["verdict"], 3))
    return results
