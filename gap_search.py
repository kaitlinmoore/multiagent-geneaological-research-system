"""Gap detection entry point — discovers and investigates missing relationships.

Usage:
    # Show gap summary for a GEDCOM file:
    ./.venv/Scripts/python.exe gap_search.py data/PII\ Trees/Moore\ Family\ Tree.ged

    # Run the pipeline on the top N gaps:
    ./.venv/Scripts/python.exe gap_search.py data/PII\ Trees/Moore\ Family\ Tree.ged --run 3

    # Only scan for fathers / mothers:
    ./.venv/Scripts/python.exe gap_search.py data/PII\ Trees/Moore\ Family\ Tree.ged --role father --run 5

    # Filter to gaps with a high-scoring candidate already in the tree:
    ./.venv/Scripts/python.exe gap_search.py data/PII\ Trees/Moore\ Family\ Tree.ged --min-score 0.75 --run 3

Pipeline integration:
    For each selected gap, gap_search builds a target_person dict with
    ``gap_mode: True``, ``child_id``, and ``missing_role``. The Record Scout
    detects gap_mode and calls find_parent_candidates instead of fuzzy-matching.
    The rest of the pipeline (Synthesizer, Hypothesizer, Critic, Report Writer)
    runs unchanged — it evaluates the parent candidates as hypotheses and
    produces the same traced, cited, escalation-checked output.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(override=True)

from graph import build_graph
from tools.gap_scanner import find_parent_candidates, find_research_candidates
from tools.gedcom_parser import parse_gedcom_file, parse_gedcom_text
from tools.trace_writer import save_trace


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    gedcom_path = Path(args.gedcom)

    if not gedcom_path.exists():
        print(f"error: file not found: {gedcom_path}")
        return 1

    # --- Parse ---
    print(f"parsing {gedcom_path.name} ...")
    persons = parse_gedcom_file(str(gedcom_path))
    print(f"  {len(persons)} persons")

    # --- Load text for pipeline (handle encoding) ---
    try:
        gedcom_text = gedcom_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        gedcom_text = gedcom_path.read_text(encoding="latin-1")

    # --- Find gaps ---
    candidates = find_research_candidates(persons, min_data_fields=args.min_fields)
    print(f"  {len(candidates)} gaps with >= {args.min_fields} data fields")

    # Filter by role if requested.
    if args.role:
        candidates = [
            c for c in candidates
            if c["missing_role"] == args.role
            or (args.role in ("father", "mother") and c["missing_role"] == "both")
        ]
        print(f"  {len(candidates)} after filtering to missing={args.role}")

    if not candidates:
        print("no gaps found matching criteria")
        return 0

    # --- Pre-score top candidates to find broken links ---
    print(f"\nscoring top parent candidates for each gap ...")
    scored_gaps: list[dict] = []
    t0 = time.time()
    for gap in candidates:
        child = gap["person"]
        roles = []
        if gap["missing_role"] in ("father", "both"):
            roles.append("father")
        if gap["missing_role"] in ("mother", "both"):
            roles.append("mother")

        for role in roles:
            top = find_parent_candidates(
                persons, child, role, max_results=1, use_geocoding=False
            )
            top_score = top[0]["composite_score"] if top else 0.0
            top_cand = top[0] if top else None
            scored_gaps.append({
                "gap": gap,
                "role": role,
                "top_score": top_score,
                "top_candidate": top_cand,
            })

    elapsed = time.time() - t0
    print(f"  scored {len(scored_gaps)} role-searches in {elapsed:.1f}s")

    # Filter by minimum score.
    if args.min_score > 0:
        scored_gaps = [sg for sg in scored_gaps if sg["top_score"] >= args.min_score]
        print(f"  {len(scored_gaps)} with top candidate >= {args.min_score}")

    # Sort by top_score descending (most promising first).
    scored_gaps.sort(key=lambda sg: sg["top_score"], reverse=True)

    # --- Summary ---
    print(f"\n{'='*60}")
    print(f"GAP SUMMARY: {len(scored_gaps)} actionable gaps")
    print(f"{'='*60}\n")
    show_n = min(20, len(scored_gaps))
    for i, sg in enumerate(scored_gaps[:show_n], 1):
        child = sg["gap"]["person"]
        tc = sg["top_candidate"]
        tc_name = tc["person"]["name"] if tc else "(none)"
        tc_score = f'{sg["top_score"]:.3f}'
        print(
            f"  {i:3}. [{sg['role']:<7}] {child['name']:<30} "
            f"top candidate: {tc_name:<30} score={tc_score}"
        )
    if len(scored_gaps) > show_n:
        print(f"  ... +{len(scored_gaps) - show_n} more")

    # --- Run pipeline on selected gaps ---
    if args.run is None or args.run == 0:
        print(f"\nuse --run N to run the pipeline on the top N gaps")
        return 0

    run_count = min(args.run, len(scored_gaps))
    print(f"\n{'='*60}")
    print(f"RUNNING PIPELINE ON TOP {run_count} GAPS")
    print(f"{'='*60}\n")

    graph = build_graph()
    results: list[dict] = []

    for i, sg in enumerate(scored_gaps[:run_count], 1):
        child = sg["gap"]["person"]
        role = sg["role"]
        child_name = child.get("name", "(unnamed)")
        child_id = child["id"]

        print(f"[{i}/{run_count}] {child_name} — missing {role}")

        initial_state = {
            "query": sg["gap"]["query"],
            "target_person": {
                "name": child_name,
                "approx_birth": child.get("birth_date"),
                "location": child.get("birth_place"),
                "gap_mode": True,
                "child_id": child_id,
                "missing_role": role,
            },
            "gedcom_text": gedcom_text,
            "gedcom_persons": [],
            "dna_csv": None,
            "retrieved_records": [],
            "profiles": [],
            "hypotheses": [],
            "critiques": [],
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
            print(f"  FAILED after {elapsed:.1f}s: {type(exc).__name__}: {exc}")
            continue

        # Save trace.
        safe_name = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in child_name
        )
        label = f"gap_{safe_name}_{role}"
        trace_paths = save_trace(result, label=label)

        # Summarize.
        critiques = result.get("critiques") or []
        verdicts = [c.get("verdict") for c in critiques]
        confs = [c.get("confidence_in_critique") for c in critiques]
        print(
            f"  {elapsed:.1f}s  status={result.get('status')}  "
            f"hypotheses={len(result.get('hypotheses') or [])}  "
            f"verdicts={verdicts}  confs={confs}"
        )
        if trace_paths:
            print(f"  trace: {trace_paths.get('md_path')}")

        results.append({
            "child": child_name,
            "role": role,
            "status": result.get("status"),
            "verdicts": verdicts,
            "confs": confs,
            "elapsed": round(elapsed, 1),
        })
        print()

    # Final summary table.
    print(f"{'='*60}")
    print(f"RESULTS: {run_count} gap investigations")
    print(f"{'='*60}")
    for r in results:
        print(
            f"  {r['child']:<30} {r['role']:<7}  "
            f"status={r['status']}  verdicts={r['verdicts']}  "
            f"confs={r['confs']}  {r['elapsed']}s"
        )

    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gap detection — discover and investigate missing relationships."
    )
    parser.add_argument(
        "gedcom",
        help="Path to the GEDCOM file to scan.",
    )
    parser.add_argument(
        "--run",
        type=int,
        default=None,
        help="Run the pipeline on the top N gaps. Default: summary only.",
    )
    parser.add_argument(
        "--role",
        choices=["father", "mother"],
        default=None,
        help="Only scan for this missing role. Default: both.",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Only show gaps whose top candidate scores above this threshold.",
    )
    parser.add_argument(
        "--min-fields",
        type=int,
        default=4,
        help="Minimum populated data fields for a gap to be investigable. Default: 4.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
