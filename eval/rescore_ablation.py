"""Re-score the most recent ablation run against updated keyword tables.

Saves API spend by re-evaluating already-collected baseline responses
when scoring criteria change. Reads the most recent
eval/results/ablation_*.json, re-applies _evaluate_baseline_case() with
whatever the current scoring code says, and re-emits the per-tier
summary + ablation_summary.md.

Run this if you tweak the keyword lists or tier scoring rules.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from eval.single_agent_baseline import (
    _MANIFEST_PATH, _RESULTS_DIR,
    _evaluate_baseline_case, _build_summary_md, _load_full_pipeline_baseline,
)


def main() -> int:
    if not _RESULTS_DIR.exists():
        print(f"no results dir at {_RESULTS_DIR}")
        return 2
    # Prefer the original (non-rescored) JSON files; if a previous rescore
    # left a *_rescored.json sibling, ignore those to avoid the cascading
    # double-suffix problem (ablation_X_rescored_rescored_rescored.json).
    runs = sorted(
        [p for p in _RESULTS_DIR.glob("ablation_*.json") if "_rescored" not in p.stem],
        reverse=True,
    )
    if not runs:
        print("no ablation_*.json files to rescore")
        return 2
    latest = runs[0]
    print(f"rescoring {latest.name}")

    data = json.loads(latest.read_text(encoding="utf-8"))
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    tiers = manifest.get("tiers") or {}

    by_file = {}
    for tier_name, spec in tiers.items():
        for case in spec.get("cases") or []:
            by_file[case["file"]] = (tier_name, spec, case)

    rescored = []
    for r in data.get("results") or []:
        info = by_file.get(r.get("file"))
        if not info:
            rescored.append(r)
            continue
        tier_name, spec, case = info
        response = r.get("response") or {}
        eval_result = _evaluate_baseline_case(case, tier_name, spec, response)
        new_r = dict(r)
        new_r["passed"] = eval_result["passed"]
        new_r["partial"] = eval_result.get("partial", False)
        new_r["reason"] = eval_result["reason"]
        rescored.append(new_r)

    # Print summary
    print()
    by_tier = {}
    for r in rescored:
        by_tier.setdefault(r["tier"], []).append(r)
    for t in ("tier1", "tier2", "tier3"):
        rs = by_tier.get(t, [])
        full = sum(1 for r in rs if r["passed"] and not r.get("partial"))
        partial = sum(1 for r in rs if r["passed"] and r.get("partial"))
        print(f"  {t}: {full}/{len(rs)} full pass, {partial}/{len(rs)} partial")
        for r in rs:
            ok = "PASS" if r["passed"] and not r.get("partial") else (
                "partial" if r["passed"] and r.get("partial") else "FAIL"
            )
            print(f"    {ok}  {r['file']}  verdict={r.get('verdict')} conf={r.get('confidence')}")

    # Re-emit summary md + the JSON with updated scoring
    full_baseline = _load_full_pipeline_baseline()
    md_path = _RESULTS_DIR / "ablation_summary.md"
    md_path.write_text(
        _build_summary_md(rescored, full_baseline, data.get("run_label") or "rescored"),
        encoding="utf-8",
    )
    json_path = latest.with_name(latest.stem + "_rescored.json")
    data["results"] = rescored
    total = len(rescored)
    passed = sum(1 for r in rescored if r["passed"] and not r.get("partial"))
    partial = sum(1 for r in rescored if r["passed"] and r.get("partial"))
    data["summary"]["passed_full"] = passed
    data["summary"]["passed_partial"] = partial
    json_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {md_path}")
    print(f"wrote {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
