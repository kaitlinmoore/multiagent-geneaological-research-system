"""Tiny driver to run the full pipeline against an arbitrary GEDCOM + DNA
combo and save the resulting trace into `traces/demos/`. Used to generate
committable, reproducible demo artifacts on public-data trees (Kennedy,
Queen, Habsburg) so graders can re-run them without any PII.

Usage:
    python scripts/run_demo.py \\
        --gedcom "data/Habsburg.ged" --encoding latin-1 \\
        --query "Who are the parents of Maria Theresia of Austria?" \\
        --name "MARIA THERESIA von Österreich" \\
        --birth "1717" --location "Vienna, Austria" \\
        --dna "data/DNA_demo/Maria_Theresia_synthetic_DNA.csv" \\
        --label "habsburg_maria_theresia_synthetic_dna"

If --dna is omitted, the run is run without DNA. The trace JSON + MD are
written to traces/demos/ via the standard trace_writer; this script just
moves them there so the gitignore allow-list keeps them committable.
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
    p.add_argument("--query", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--birth", default="")
    p.add_argument("--location", default="")
    p.add_argument("--dna", default=None)
    p.add_argument("--label", required=True)
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
