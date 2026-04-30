"""Subtree audit — flags weak evidence across generations of a family tree.

Two-pass design for speed:
    Pass 1 (fast, no LLM): deterministic date checks + geographic plausibility
        on every relationship in the subtree. Seconds even for hundreds of links.
    Pass 2 (slow, optional, LLM): runs the full pipeline on the top N most
        questionable relationships from Pass 1.

Usage:
    # Deterministic-only audit, 3 generations up from James Joseph Moore:
    ./.venv/Scripts/python.exe audit.py "data/PII Trees/Moore Family Tree.ged" \\
        --name "James Joseph Moore" --generations 3

    # Add deep LLM audit on top 5 questionable links:
    ./.venv/Scripts/python.exe audit.py "data/PII Trees/Moore Family Tree.ged" \\
        --name "James Joseph Moore" --generations 3 --deep 5

    # Use a GEDCOM pointer directly:
    ./.venv/Scripts/python.exe audit.py "data/The Kennedy Family.ged" \\
        --id "@I0@" --generations 3
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(override=True)

from tools.date_utils import (
    check_death_before_birth,
    check_implausible_lifespan,
    check_parent_died_before_conception,
    check_parent_too_young_at_birth,
    check_parent_younger_than_child,
    get_year,
    run_all_tier1_checks,
)
from tools.fuzzy_match import name_match_score
from tools.gedcom_parser import parse_gedcom_file
from tools.geo_utils import check_geographic_plausibility
from tools.subtree_extractor import extract_all_relationships, extract_subtree
from tools.trace_writer import save_trace


# ---------------------------------------------------------------------------
# Pass 1: fast deterministic audit
# ---------------------------------------------------------------------------


def pass1_audit(relationships: list[dict]) -> list[dict]:
    """Run deterministic checks on every relationship. No LLM, no network
    (geo uses token overlap, not live geocoding)."""
    results: list[dict] = []

    for rel in relationships:
        child = rel["child"]
        parent = rel["parent"]
        role = rel["role"]
        generation = rel["generation"]

        # Tier 1 date checks.
        father = parent if role == "father" else None
        mother = parent if role == "mother" else None
        tier1 = run_all_tier1_checks(child, father=father, mother=mother)
        impossibles = [r for r in tier1 if r["verdict"] == "impossible"]

        # Geographic check (token-based, no geocoding).
        child_place = child.get("birth_place") or ""
        parent_place = parent.get("birth_place") or ""
        geo = None
        if child_place and parent_place:
            geo = check_geographic_plausibility(child_place, parent_place)

        # Age gap.
        child_year = get_year(child.get("birth_date"))
        parent_year = get_year(parent.get("birth_date"))
        age_gap = (child_year - parent_year) if child_year and parent_year else None

        # Classify severity.
        if impossibles:
            severity = "impossible"
        elif geo and geo.get("verdict") in ("flag_moderate", "flag_strong"):
            severity = "flagged"
        elif age_gap is not None and (age_gap < 15 or age_gap > 55):
            severity = "flagged"
        else:
            severity = "ok"

        issues: list[str] = []
        for imp in impossibles:
            role_tag = f" [{imp.get('role')}]" if imp.get("role") else ""
            issues.append(f"[IMPOSSIBLE]{role_tag} {imp['check']}: {imp['reason']}")
        if geo and geo.get("verdict") in ("flag_moderate", "flag_strong"):
            issues.append(f"[GEO {geo['verdict'].upper()}] {geo['reason']}")
        if age_gap is not None:
            if age_gap < 15:
                issues.append(f"[AGE] parent-child age gap {age_gap}y is below 15y floor")
            elif age_gap > 55:
                issues.append(f"[AGE] parent-child age gap {age_gap}y exceeds 55y — unusual")

        results.append({
            "child_id": child["id"],
            "child_name": child.get("name"),
            "parent_id": parent["id"],
            "parent_name": parent.get("name"),
            "role": role,
            "generation": generation,
            "severity": severity,
            "age_gap": age_gap,
            "geo_verdict": geo.get("verdict") if geo else None,
            "geo_distance_km": geo.get("distance_km") if geo else None,
            "issues": issues,
            "tier1_results": tier1,
        })

    # Sort: impossible first, then flagged, then ok. Within each, by generation.
    severity_order = {"impossible": 0, "flagged": 1, "ok": 2}
    results.sort(key=lambda r: (severity_order.get(r["severity"], 3), r["generation"]))
    return results


# ---------------------------------------------------------------------------
# Pass 2: deep LLM audit on top-N questionable relationships
# ---------------------------------------------------------------------------


def pass2_audit(
    questionable: list[dict],
    gedcom_text: str,
    gedcom_persons: list[dict],
    max_deep: int = 5,
) -> list[dict]:
    """Run the full pipeline on the most questionable relationships."""
    from graph import build_graph

    graph = build_graph()
    deep_results: list[dict] = []

    for i, rel in enumerate(questionable[:max_deep], 1):
        child_name = rel["child_name"] or "(unnamed)"
        parent_name = rel["parent_name"] or "(unnamed)"
        role = rel["role"]

        print(f"  [{i}/{min(max_deep, len(questionable))}] "
              f"{child_name} <- {role} -> {parent_name} ... ", end="", flush=True)

        query = f"Is {parent_name} the {role} of {child_name}?"
        child_person = next(
            (p for p in gedcom_persons if p["id"] == rel["child_id"]), None
        )

        initial_state = {
            "query": query,
            "target_person": {
                "name": child_name,
                "approx_birth": child_person.get("birth_date") if child_person else None,
                "location": child_person.get("birth_place") if child_person else None,
            },
            "gedcom_text": gedcom_text,
            "gedcom_persons": [],
            "dna_csv": None,
            "retrieved_records": [],
            "profiles": [],
            "hypotheses": [],
            "critiques": [],
            "dna_analysis": None,
            "final_report": "",
            "revision_count": 0,
            "status": "running",
            "trace_log": [],
            "isolation_mode": None,
        }

        t0 = time.time()
        try:
            result = graph.invoke(initial_state)
            elapsed = time.time() - t0
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"FAILED ({elapsed:.0f}s)")
            deep_results.append({**rel, "deep_verdict": "error", "deep_conf": None,
                                 "deep_elapsed": round(elapsed, 1)})
            continue

        critiques = result.get("critiques") or []
        verdicts = [c.get("verdict") for c in critiques]
        confs = [c.get("confidence_in_critique") for c in critiques]
        print(f"verdicts={verdicts} confs={confs} ({elapsed:.0f}s)")

        deep_results.append({
            **rel,
            "deep_verdicts": verdicts,
            "deep_confs": confs,
            "deep_elapsed": round(elapsed, 1),
            "deep_issues": [
                issue
                for c in critiques
                for issue in (c.get("issues_found") or [])
            ],
        })

    return deep_results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(
    root_person: dict,
    generations: int,
    subtree_info: dict,
    pass1_results: list[dict],
    pass2_results: list[dict] | None,
) -> str:
    lines: list[str] = []
    lines.append("# Subtree Audit Report")
    lines.append("")
    lines.append(f"**Root:** {root_person.get('name')} (`{root_person.get('id')}`)")
    lines.append(f"**Generations:** {generations}")
    lines.append(f"**Persons in subtree:** {len(subtree_info.get('persons', []))}")
    lines.append(f"**Relationships audited:** {len(pass1_results)}")
    lines.append("")

    # Summary counts.
    impossible = sum(1 for r in pass1_results if r["severity"] == "impossible")
    flagged = sum(1 for r in pass1_results if r["severity"] == "flagged")
    ok = sum(1 for r in pass1_results if r["severity"] == "ok")
    lines.append("## Summary")
    lines.append("")
    if impossible:
        lines.append(f"- **{impossible} IMPOSSIBLE** — deterministic rule failures")
    if flagged:
        lines.append(f"- **{flagged} FLAGGED** — suspicious but not rule-breaking")
    lines.append(f"- **{ok} OK** — passed all deterministic checks")
    lines.append("")

    # Pass 1 details — impossible and flagged only.
    problem_results = [r for r in pass1_results if r["severity"] != "ok"]
    if problem_results:
        lines.append("## Relationships Requiring Attention")
        lines.append("")
        for r in problem_results:
            marker = "IMPOSSIBLE" if r["severity"] == "impossible" else "FLAGGED"
            lines.append(
                f"### {marker}: {r['child_name']} <- {r['role']} "
                f"-> {r['parent_name']}"
            )
            lines.append(
                f"Generation {r['generation']} | "
                f"Age gap: {r['age_gap']}y | "
                f"Geo: {r['geo_verdict'] or 'n/a'}"
                + (f" ({r['geo_distance_km']}km)" if r.get("geo_distance_km") else "")
            )
            lines.append("")
            for issue in r["issues"]:
                lines.append(f"- {issue}")
            lines.append("")
    else:
        lines.append("## No Issues Found")
        lines.append("")
        lines.append(
            "All relationships passed deterministic checks. Consider running "
            "`--deep N` for LLM-based evidence evaluation on the weakest links."
        )
        lines.append("")

    # Pass 1 full table (all relationships).
    lines.append("## Full Audit Table")
    lines.append("")
    lines.append(
        "| Gen | Severity | Child | Role | Parent | Age Gap | Geo | Issues |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in pass1_results:
        issues_short = "; ".join(r["issues"])[:80] if r["issues"] else "-"
        geo_str = r["geo_verdict"] or "-"
        age_str = f"{r['age_gap']}y" if r["age_gap"] is not None else "-"
        lines.append(
            f"| {r['generation']} | {r['severity']} | {r['child_name']} "
            f"| {r['role']} | {r['parent_name']} | {age_str} | {geo_str} "
            f"| {issues_short} |"
        )
    lines.append("")

    # Pass 2 deep results.
    if pass2_results:
        lines.append("## Deep Audit (LLM-based)")
        lines.append("")
        for dr in pass2_results:
            lines.append(
                f"### {dr['child_name']} <- {dr['role']} -> {dr['parent_name']}"
            )
            verdicts = dr.get("deep_verdicts") or [dr.get("deep_verdict", "?")]
            confs = dr.get("deep_confs") or []
            lines.append(
                f"Verdicts: {verdicts} | Confidence: {confs} | "
                f"Time: {dr.get('deep_elapsed', '?')}s"
            )
            lines.append("")
            for issue in dr.get("deep_issues") or []:
                lines.append(f"- {issue[:150]}")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Person lookup
# ---------------------------------------------------------------------------


def find_person_by_name(
    gedcom_persons: list[dict], name_query: str
) -> dict | None:
    """Find the best-matching person by fuzzy name search."""
    best = None
    best_score = 0.0
    for p in gedcom_persons:
        pname = p.get("name") or ""
        if not pname:
            continue
        score = name_match_score(name_query, pname)
        if score > best_score:
            best_score = score
            best = p
    if best and best_score >= 0.60:
        return best
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    gedcom_path = Path(args.gedcom)

    if not gedcom_path.exists():
        print(f"error: file not found: {gedcom_path}")
        return 1

    # Parse GEDCOM.
    print(f"parsing {gedcom_path.name} ...")
    persons = parse_gedcom_file(str(gedcom_path))
    print(f"  {len(persons)} persons")

    # Find root person.
    if args.id:
        by_id = {p["id"]: p for p in persons}
        root = by_id.get(args.id)
        if not root:
            print(f"error: person {args.id} not found in GEDCOM")
            return 1
    elif args.name:
        root = find_person_by_name(persons, args.name)
        if not root:
            print(f"error: no person matching '{args.name}' found (threshold 0.60)")
            return 1
    else:
        print("error: specify --name or --id")
        return 1

    print(f"root: {root.get('name')} ({root['id']})")
    print(f"  birth: {root.get('birth_date')} in {root.get('birth_place')}")
    print()

    # Extract subtree.
    subtree = extract_subtree(persons, root["id"], args.generations, "ancestors")
    relationships = extract_all_relationships(persons, root["id"], args.generations)
    print(
        f"subtree: {len(subtree['persons'])} persons, "
        f"{len(relationships)} relationships, "
        f"{subtree['generations_reached']} generations reached"
    )
    print()

    # Pass 1: deterministic audit.
    print("=== PASS 1: deterministic checks ===")
    t0 = time.time()
    pass1 = pass1_audit(relationships)
    elapsed1 = time.time() - t0

    impossible = sum(1 for r in pass1 if r["severity"] == "impossible")
    flagged = sum(1 for r in pass1 if r["severity"] == "flagged")
    ok = sum(1 for r in pass1 if r["severity"] == "ok")
    print(
        f"  {len(pass1)} relationships checked in {elapsed1:.1f}s: "
        f"{impossible} impossible, {flagged} flagged, {ok} ok"
    )
    print()

    # Show problems.
    problems = [r for r in pass1 if r["severity"] != "ok"]
    if problems:
        print(f"  relationships requiring attention ({len(problems)}):")
        for r in problems:
            marker = "!!!" if r["severity"] == "impossible" else " ! "
            age = f"{r['age_gap']}y" if r["age_gap"] is not None else "?"
            print(
                f"  {marker} gen {r['generation']} "
                f"{r['child_name']:<30} <- {r['role']:<7} "
                f"-> {r['parent_name']:<30} age_gap={age:<5} "
                f"geo={r['geo_verdict'] or '-'}"
            )
            for issue in r["issues"]:
                print(f"        {issue}")
        print()
    else:
        print("  no issues found in deterministic pass")
        print()

    # Pass 2: deep LLM audit (optional).
    pass2 = None
    if args.deep and args.deep > 0 and problems:
        print(f"=== PASS 2: deep LLM audit on top {args.deep} ===")

        # Load GEDCOM text for the pipeline.
        try:
            gedcom_text = gedcom_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            gedcom_text = gedcom_path.read_text(encoding="latin-1")

        pass2 = pass2_audit(problems, gedcom_text, persons, max_deep=args.deep)
        print()

    # Generate report.
    report = generate_report(root, args.generations, subtree, pass1, pass2)

    # Save to traces/.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(
        c if c.isalnum() or c in "-_" else "_"
        for c in (root.get("name") or "unknown")
    )
    report_path = Path("traces") / f"audit_{timestamp}_{safe_name}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"audit report: {report_path}")

    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Subtree audit — flag weak evidence across generations."
    )
    parser.add_argument("gedcom", help="Path to the GEDCOM file.")
    parser.add_argument("--name", help="Root person name (fuzzy search).")
    parser.add_argument("--id", help="Root person GEDCOM pointer (e.g. @I0@).")
    parser.add_argument(
        "--generations", type=int, default=3,
        help="Number of generations to traverse (default: 3)."
    )
    parser.add_argument(
        "--deep", type=int, default=0,
        help="Run full LLM pipeline on top N questionable relationships (default: 0 = skip)."
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
