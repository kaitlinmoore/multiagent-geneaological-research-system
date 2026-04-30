"""Generate a committable audit-replay demo from a public-data tree.

Runs Pass 1 (deterministic) and optionally Pass 2 (LLM full-pipeline on
top-N questionable relationships) on a chosen subtree, then saves the
combined audit result to `traces/demos/audit_<label>.json` so it can
be loaded from Streamlit's Audit tab in Replay mode without an API key.

Usage:
    python scripts/run_audit_demo.py \\
        --gedcom "data/Habsburg.ged" --encoding latin-1 \\
        --root "MARIA THERESIA von Österreich" --generations 3 \\
        --pass2 5 --label habsburg_maria_theresia
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(override=True)

from tools.gedcom_parser import parse_gedcom_text
from tools.subtree_extractor import extract_all_relationships, extract_subtree
from audit import pass1_audit, pass2_audit


def _find_person(persons: list[dict], name_query: str) -> tuple[dict | None, float]:
    """Pick the highest-scoring person by surname-gated fuzzy match."""
    from tools.fuzzy_match import name_match_score
    best, score = None, 0.0
    for p in persons:
        s = name_match_score(name_query, p.get("name") or "")
        if s > score:
            score, best = s, p
    return best, score


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--gedcom", required=True)
    p.add_argument("--encoding", default="utf-8")
    p.add_argument("--root", required=True, help="Root-person fuzzy name.")
    p.add_argument("--generations", type=int, default=3)
    p.add_argument("--pass2", type=int, default=0,
                   help="Run Pass 2 LLM audit on top-N questionable relationships. "
                        "0 = skip Pass 2 (Pass 1 only).")
    p.add_argument("--label", required=True)
    args = p.parse_args()

    gedcom_text = Path(args.gedcom).read_text(
        encoding=args.encoding, errors="replace"
    )
    print(f"Loading {args.gedcom} ({args.encoding}) ...")
    persons = parse_gedcom_text(gedcom_text)
    print(f"  parsed {len(persons)} persons")

    root, score = _find_person(persons, args.root)
    if not root:
        print(f"No match for root {args.root!r}")
        return 1
    print(f"Root: {root.get('name')!r} ({root.get('id')}) — match score {score:.2f}")

    print(f"Extracting {args.generations}-generation ancestor subtree...")
    subtree = extract_subtree(persons, root["id"], args.generations, "ancestors")
    relationships = extract_all_relationships(persons, root["id"], args.generations)
    print(f"  subtree: {len(subtree['persons'])} persons, {len(relationships)} relationships")

    print("Running Pass 1 (deterministic)...")
    t0 = time.time()
    pass1_results = pass1_audit(relationships)
    pass1_elapsed = time.time() - t0
    n_impossible = sum(1 for r in pass1_results if r["severity"] == "impossible")
    n_flagged = sum(1 for r in pass1_results if r["severity"] == "flagged")
    n_ok = sum(1 for r in pass1_results if r["severity"] == "ok")
    print(f"  done in {pass1_elapsed:.1f}s — "
          f"{n_impossible} impossible, {n_flagged} flagged, {n_ok} ok")

    pass2_results = None
    pass2_elapsed = None
    if args.pass2 > 0:
        problems = [r for r in pass1_results if r["severity"] != "ok"]
        if not problems:
            print("Pass 1 produced no problems; skipping Pass 2.")
        else:
            n = min(args.pass2, len(problems))
            print(f"Running Pass 2 on top-{n} of {len(problems)} questionable relationships...")
            t0 = time.time()
            pass2_results = pass2_audit(problems, gedcom_text, persons, max_deep=n)
            pass2_elapsed = time.time() - t0
            print(f"  done in {pass2_elapsed:.1f}s")

    # Build the saved-audit payload. Same shape Streamlit's session_state
    # uses (aud_results, aud_subtree, aud_root, aud_persons, aud_gens) plus
    # a small metadata header.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = {
        "audit_metadata": {
            "kind": "audit_replay",
            "timestamp": timestamp,
            "label": args.label,
            "gedcom_path": args.gedcom,
            "encoding": args.encoding,
            "generations": args.generations,
            "pass1_elapsed_sec": round(pass1_elapsed, 2),
            "pass2_elapsed_sec": round(pass2_elapsed, 2) if pass2_elapsed else None,
        },
        "root": root,
        "generations": args.generations,
        "subtree": subtree,
        "pass1_results": pass1_results,
        "pass2_results": pass2_results,
    }

    out_dir = _REPO_ROOT / "traces" / "demos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"audit_{timestamp}_{args.label}.json"
    out_path.write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
