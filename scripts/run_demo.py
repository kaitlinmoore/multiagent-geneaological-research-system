"""Tiny driver to run the full pipeline against an arbitrary GEDCOM and
save the resulting trace into `traces/demos/`. Used to generate
committable, reproducible demo artifacts on public-data trees (Kennedy,
Queen, Habsburg) so graders can re-run them without any PII.

Two modes: query (default) and gap.

Query mode example (with optional DNA):
    python scripts/run_demo.py \\
        --gedcom "data/Habsburg.ged" --encoding latin-1 \\
        --query "Who are the parents of Maria Theresia of Austria?" \\
        --name "MARIA THERESIA von Österreich" \\
        --birth "1717" --location "Vienna, Austria" \\
        --dna "data/DNA_demo/Maria_Theresia_synthetic_DNA.csv" \\
        --label "habsburg_maria_theresia_synthetic_dna"

Gap mode example (no query / target — picks the top candidate from
find_research_candidates):
    python scripts/run_demo.py --gap \\
        --gedcom "data/The Kennedy Family.ged" --encoding utf-8 \\
        --label "kennedy_gap_demo"

The trace JSON + MD are written by the standard trace_writer; this script
just moves them into traces/demos/ so the gitignore allow-list keeps
them committable.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(override=True)

from graph import build_graph
from tools.trace_writer import save_trace


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--gedcom", required=True)
    p.add_argument("--encoding", default="utf-8")
    p.add_argument("--query", default=None,
                   help="Required for query mode; ignored in gap mode.")
    p.add_argument("--name", default=None,
                   help="Required for query mode; ignored in gap mode.")
    p.add_argument("--birth", default="")
    p.add_argument("--location", default="")
    p.add_argument("--dna", default=None)
    p.add_argument("--label", required=True)
    p.add_argument("--gap", action="store_true",
                   help="Gap-mode: pick the top candidate from "
                        "find_research_candidates and run the pipeline on it.")
    p.add_argument("--gap-pick", type=int, default=0,
                   help="In gap mode, which ranked candidate to investigate "
                        "(0=top, 1=second, …).")
    args = p.parse_args()

    gedcom_text = Path(args.gedcom).read_text(encoding=args.encoding, errors="replace")
    dna_csv = None
    if args.dna:
        for enc in ("utf-8-sig", "latin-1"):
            try:
                dna_csv = Path(args.dna).read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue

    if args.gap:
        # Gap mode: scan deterministically, pick a candidate, build the
        # gap-mode initial_state matching gap_search.py's pattern.
        from tools.gap_scanner import find_research_candidates
        from tools.gedcom_parser import parse_gedcom_text

        persons = parse_gedcom_text(gedcom_text)
        candidates = find_research_candidates(persons)
        if not candidates:
            print("No gap candidates found in GEDCOM "
                  "(try lowering min_data_fields).")
            return 1
        if args.gap_pick >= len(candidates):
            print(f"--gap-pick {args.gap_pick} out of range "
                  f"({len(candidates)} candidates).")
            return 1
        cand = candidates[args.gap_pick]
        person = cand["person"]
        # If missing both, default to investigating the father first.
        role = cand["missing_role"]
        if role == "both":
            role = "father"

        print(f"Gap mode picked: {person.get('name')!r} "
              f"(missing {cand['missing_role']}, "
              f"investigating {role}, "
              f"{cand['data_fields']} data fields)")

        initial_state = {
            "query": cand["query"],
            "target_person": {
                "name": person.get("name") or "(unknown)",
                "approx_birth": person.get("birth_date"),
                "location": person.get("birth_place"),
                "gap_mode": True,
                "child_id": person["id"],
                "missing_role": role,
            },
            "gedcom_text": gedcom_text,
            "gedcom_persons": [],
            "dna_csv": dna_csv,
            "retrieved_records": [],
            "profiles": [],
            "hypotheses": [],
            "critiques": [],
            "dna_analysis": None,
            "final_report": "",
            "revision_count": 0,
            "status": "running",
            "trace_log": [],
        }
    else:
        # Query mode (original behavior).
        if not args.query or not args.name:
            print("--query and --name are required in query mode.")
            return 2

        initial_state = {
            "query": args.query,
            "target_person": {
                "name": args.name,
                "approx_birth": args.birth,
                "location": args.location,
            },
            "gedcom_text": gedcom_text,
            "gedcom_persons": [],
            "dna_csv": dna_csv,
            "retrieved_records": [],
            "profiles": [],
            "hypotheses": [],
            "critiques": [],
            "dna_analysis": None,
            "final_report": "",
            "revision_count": 0,
            "status": "running",
            "trace_log": [],
        }

    graph = build_graph()
    final_state = graph.invoke(initial_state)

    print(f"=== {args.label} complete ===")
    print(f"  status:            {final_state.get('status')}")
    print(f"  revisions:         {final_state.get('revision_count')}")
    print(f"  retrieved_records: {len(final_state.get('retrieved_records') or [])}")
    print(f"  profiles:          {len(final_state.get('profiles') or [])}")
    print(f"  hypotheses:        {len(final_state.get('hypotheses') or [])}")
    print(f"  critiques:         {len(final_state.get('critiques') or [])}")
    dna = final_state.get("dna_analysis")
    if dna:
        print(
            f"  dna:               {dna.get('total_matches', 0)} matches, "
            f"subject={dna.get('subject_gedcom_id')} "
            f"({dna.get('subject_match_score')})"
        )

    paths = save_trace(final_state, label=args.label)
    if not paths:
        print("(trace save failed)")
        return 1

    demos_dir = _REPO_ROOT / "traces" / "demos"
    demos_dir.mkdir(parents=True, exist_ok=True)
    moved = []
    for k in ("json_path", "md_path"):
        src = Path(paths[k]) if paths.get(k) else None
        if not src or not src.exists():
            continue
        dst = demos_dir / src.name
        shutil.move(str(src), str(dst))
        moved.append(str(dst))
    for m in moved:
        print(f"  -> {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
