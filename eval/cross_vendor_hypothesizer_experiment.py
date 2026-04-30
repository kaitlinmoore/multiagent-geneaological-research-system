"""Cross-vendor Hypothesizer experiment — asymmetric capability pairing.

Question: when a weaker primary reasoner (Hypothesizer) is paired with a
stronger adversarial Critic, does the cross-vendor design degrade gracefully?
Specifically:
  - Does the weak Hypothesizer produce noticeably weaker hypotheses?
  - Does the strong Critic catch the weakness, or does it accept anyway?
  - Does verdict alignment between weak-cross and production differ?

Design (extends the cross-vendor Critic experiment):
    Shared:    Scout + Synthesizer output (same retrieved_records + profile).
    Condition A (production):     Anthropic Sonnet 4.6 Hypothesizer + Anthropic Opus 4.7 Critic
    Condition B (asymmetric cross): OpenAI GPT-4o-mini Hypothesizer + Anthropic Opus 4.7 Critic

The Synthesizer stays Anthropic because we're isolating the Hypothesizer
variable; varying both at once would muddle the comparison.

Run:
    ./.venv/Scripts/python.exe eval/cross_vendor_hypothesizer_experiment.py

Output:
    eval/results/cross_vendor_hypo_{timestamp}_{scenario}.json
    traces/trace_..._hypo_{condition}.{json,md}  per condition per scenario
"""

from __future__ import annotations

import copy
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

from agents.adversarial_critic import build_critic_llm
import agents.adversarial_critic as critic_module
from agents.relationship_hypothesizer import build_hypothesizer_llm
import agents.relationship_hypothesizer as hypo_module
from agents.final_report_writer import final_report_writer_node
from agents.profile_synthesizer import profile_synthesizer_node
from agents.record_scout import record_scout_node
from agents.relationship_hypothesizer import relationship_hypothesizer_node
from agents.adversarial_critic import adversarial_critic_node
from tools.trace_writer import save_trace


_RESULTS_DIR = _REPO_ROOT / "eval" / "results"


_CONDITIONS = [
    {
        "name": "production_sonnet_hypo_opus_critic",
        "hypo_vendor": "anthropic",
        "hypo_model": "claude-sonnet-4-6",
        "critic_vendor": "anthropic",
        "critic_model": "claude-opus-4-7",
        "label": "Production (Sonnet 4.6 + Opus 4.7)",
    },
    {
        "name": "weak_cross_gpt4omini_hypo_opus_critic",
        "hypo_vendor": "openai",
        "hypo_model": "gpt-4o-mini",
        "critic_vendor": "anthropic",
        "critic_model": "claude-opus-4-7",
        "label": "Weak-cross (GPT-4o-mini Hypo + Opus 4.7 Critic)",
    },
]


_SCENARIOS = [
    {
        "name": "jfk",
        "gedcom": _REPO_ROOT / "data" / "The Kennedy Family.ged",
        "query": "Who were the parents of John F. Kennedy?",
        "target_person": {
            "name": "John F. Kennedy",
            "approx_birth": "1917",
            "location": "Brookline, MA",
        },
    },
    {
        "name": "tier3_duplicate",
        "gedcom": _REPO_ROOT / "eval" / "trap_cases" / "tier3_kennedy_duplicate_john.ged",
        "query": "Who are the parents of John Kennedy born 1917 in Boston?",
        "target_person": {
            "name": "John Kennedy",
            "approx_birth": "1917",
            "location": "Boston, Massachusetts",
        },
    },
    {
        "name": "moore_gap",
        "gedcom": _REPO_ROOT / "data" / "PII Trees" / "Moore Family Tree.ged",
        "query": "Who is the father of Sally Jane Smith born 1945 in Philadelphia?",
        "target_person": {
            "name": "Sally Jane Smith",
            "approx_birth": "25 Jul 1945",
            "location": "Philadelphia, Pennsylvania, USA",
            "gap_mode": True,
            "child_id": "@I372015397163@",
            "missing_role": "father",
        },
    },
]


def run_scenario(scenario: dict, run_label: str) -> dict:
    print(f"\n{'='*70}")
    print(f"SCENARIO: {scenario['name']}  —  {scenario['query']}")
    print(f"{'='*70}")

    gedcom_text = scenario["gedcom"].read_text(encoding="utf-8", errors="replace")
    base_state = _initial_state(scenario["query"], scenario["target_person"], gedcom_text)

    # Shared seed: Scout + Synthesizer (Hypothesizer comes per-condition).
    print("Building shared seed (Scout + Synthesizer)...")
    t0 = time.time()
    seed = record_scout_node(base_state)
    seed_state = _merge(base_state, seed)
    seed = profile_synthesizer_node(seed_state)
    seed_state = _merge(seed_state, seed)
    t_seed = time.time() - t0
    print(f"  seed: {len(seed_state.get('profiles') or [])} profiles, "
          f"{len(seed_state.get('retrieved_records') or [])} records "
          f"in {t_seed:.1f}s")

    if not seed_state.get("profiles"):
        print(f"  WARNING: no profile produced — skipping scenario")
        return {"scenario": scenario["name"], "skipped": True}

    # Save originals, restore in finally.
    original_hypo_llm = hypo_module.llm
    original_critic_llm = critic_module.llm

    condition_outputs: list[dict] = []

    try:
        for cond in _CONDITIONS:
            print(f"\nCondition: {cond['label']}")
            # Swap LLMs.
            hypo_module.llm = build_hypothesizer_llm(
                vendor=cond["hypo_vendor"], model=cond["hypo_model"]
            )
            critic_module.llm = build_critic_llm(
                vendor=cond["critic_vendor"], model=cond["critic_model"]
            )

            state = copy.deepcopy(seed_state)

            # Run Hypothesizer.
            t0 = time.time()
            hypo_out = relationship_hypothesizer_node(state)
            t_hypo = time.time() - t0
            state = _merge(state, hypo_out)
            print(f"  Hypothesizer: {len(state.get('hypotheses') or [])} hypotheses "
                  f"in {t_hypo:.1f}s")

            if not state.get("hypotheses"):
                print(f"  WARNING: no hypotheses generated — skipping critique")
                condition_outputs.append({
                    "condition": cond,
                    "hypotheses": [],
                    "critiques": [],
                    "elapsed_hypo_sec": round(t_hypo, 2),
                    "elapsed_critic_sec": 0.0,
                })
                continue

            # Run Critic.
            t0 = time.time()
            critic_out = adversarial_critic_node(state)
            t_critic = time.time() - t0
            state = _merge(state, critic_out)
            state = _merge(state, final_report_writer_node(state))
            print(f"  Critic: {len(state['critiques'])} critiques in {t_critic:.1f}s")

            save_trace(
                state,
                label=f"{run_label}_{scenario['name']}_{cond['name']}",
            )

            condition_outputs.append({
                "condition": cond,
                "hypotheses": state["hypotheses"],
                "critiques": state["critiques"],
                "elapsed_hypo_sec": round(t_hypo, 2),
                "elapsed_critic_sec": round(t_critic, 2),
            })
    finally:
        hypo_module.llm = original_hypo_llm
        critic_module.llm = original_critic_llm

    # Per-scenario comparison. Write JSON FIRST so a print failure can't lose data.
    comparison = _compare_conditions(condition_outputs)

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = _RESULTS_DIR / f"cross_vendor_hypo_{run_label}_{scenario['name']}.json"
    result_path.write_text(
        json.dumps(
            {
                "run_label": run_label,
                "scenario": scenario["name"],
                "query": scenario["query"],
                "target_person": scenario["target_person"],
                "seed": {
                    "profiles": len(seed_state.get("profiles") or []),
                    "retrieved_records": len(seed_state.get("retrieved_records") or []),
                    "elapsed_sec": round(t_seed, 2),
                },
                "conditions": [
                    {
                        "name": c["condition"]["name"],
                        "label": c["condition"]["label"],
                        "hypo_vendor": c["condition"]["hypo_vendor"],
                        "hypo_model": c["condition"]["hypo_model"],
                        "critic_vendor": c["condition"]["critic_vendor"],
                        "critic_model": c["condition"]["critic_model"],
                        "elapsed_hypo_sec": c["elapsed_hypo_sec"],
                        "elapsed_critic_sec": c["elapsed_critic_sec"],
                        "hypotheses": c["hypotheses"],
                        "critiques": c["critiques"],
                    }
                    for c in condition_outputs
                ],
                "comparison": comparison,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"  wrote {result_path}")

    # Print comparison AFTER JSON save so a print failure can't lose data.
    try:
        print(f"\n--- {scenario['name']} comparison ---")
        for entry in comparison["per_relationship"]:
            print(f"  {entry['relationship']}")
            for cond_label, stats in entry["per_condition"].items():
                print(
                    f"    {cond_label[:50]:50s} "
                    f"hypo_conf={stats['hyp_confidence']!s:<6} "
                    f"verdict={stats['critic_verdict']!s:<14} "
                    f"critic_conf={stats['critic_confidence']!s}"
                )
    except UnicodeEncodeError as exc:
        print(f"  (comparison print suppressed due to encoding: {exc})")

    return {
        "scenario": scenario["name"],
        "comparison": comparison,
        "result_path": str(result_path),
    }


def _compare_conditions(condition_outputs) -> dict:
    """Side-by-side comparison aligning hypotheses by (subject_id, related_id, role)
    since the Hypothesizer differs across conditions but should target the same
    relationships when given the same profile."""
    # Build per-condition map from relationship signature → (hypothesis, critique).
    per_cond: dict[str, dict[tuple, tuple]] = {}
    for cond_out in condition_outputs:
        label = cond_out["condition"]["label"]
        critiques_by_id = {c.get("hypothesis_id"): c for c in cond_out["critiques"]}
        sig_map: dict[tuple, tuple] = {}
        for hyp in cond_out["hypotheses"]:
            sig = (
                hyp.get("subject_id"),
                hyp.get("related_id"),
                hyp.get("proposed_relationship", "").split()[0].lower() if hyp.get("proposed_relationship") else "",
            )
            critique = critiques_by_id.get(hyp.get("hypothesis_id"))
            sig_map[sig] = (hyp, critique)
        per_cond[label] = sig_map

    # Union of all signatures across conditions.
    all_sigs = set()
    for sig_map in per_cond.values():
        all_sigs.update(sig_map.keys())

    per_relationship: list[dict] = []
    for sig in sorted(all_sigs):
        rel_str = f"{sig[2]} of {sig[0]} -> {sig[1]}"
        entry: dict = {"relationship": rel_str, "per_condition": {}}
        for cond_label, sig_map in per_cond.items():
            hyp, critique = sig_map.get(sig, (None, None))
            entry["per_condition"][cond_label] = {
                "hyp_present": hyp is not None,
                "hyp_confidence": (hyp or {}).get("confidence_score") if hyp else None,
                "hyp_evidence_count": len((hyp or {}).get("evidence_chain") or []),
                "hyp_weaknesses_count": len((hyp or {}).get("stated_weaknesses") or []),
                "critic_verdict": (critique or {}).get("verdict"),
                "critic_confidence": (critique or {}).get("confidence_in_critique"),
                "critic_issues_count": len((critique or {}).get("issues_found") or []),
            }
        per_relationship.append(entry)

    # Aggregate.
    verdict_flips = 0
    hypo_present_in_all = 0
    for entry in per_relationship:
        verdicts = {
            stats["critic_verdict"] for stats in entry["per_condition"].values()
            if stats["critic_verdict"] is not None
        }
        if len(verdicts) > 1:
            verdict_flips += 1
        if all(stats["hyp_present"] for stats in entry["per_condition"].values()):
            hypo_present_in_all += 1

    return {
        "per_relationship": per_relationship,
        "aggregate": {
            "total_relationships": len(per_relationship),
            "verdict_flips": verdict_flips,
            "hypothesis_present_in_all_conditions": hypo_present_in_all,
        },
    }


def _initial_state(query, target, gedcom_text) -> dict:
    return {
        "query": query,
        "target_person": target,
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


def _merge(state: dict, delta: dict) -> dict:
    out = dict(state)
    for k, v in delta.items():
        if k == "trace_log" and isinstance(v, list):
            out["trace_log"] = list(out.get("trace_log") or []) + v
        else:
            out[k] = v
    return out


def main() -> None:
    run_label = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"=== Cross-vendor Hypothesizer experiment ({run_label}) ===")
    print(f"Conditions:")
    for c in _CONDITIONS:
        print(f"  {c['label']}")
    print(f"Scenarios: {[s['name'] for s in _SCENARIOS]}")

    summaries: list[dict] = []
    for scenario in _SCENARIOS:
        try:
            result = run_scenario(scenario, run_label)
            summaries.append(result)
        except Exception as exc:
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            summaries.append({"scenario": scenario["name"], "error": str(exc)})

    # Final cross-scenario summary.
    print(f"\n{'='*70}")
    print(f"FINAL SUMMARY")
    print(f"{'='*70}")
    for s in summaries:
        if s.get("skipped") or s.get("error"):
            print(f"  {s['scenario']}: skipped/error")
            continue
        agg = s["comparison"]["aggregate"]
        print(
            f"  {s['scenario']:<20} "
            f"{agg['total_relationships']} relationships, "
            f"{agg['verdict_flips']} verdict flips, "
            f"{agg['hypothesis_present_in_all_conditions']} present in both conditions"
        )


if __name__ == "__main__":
    main()
