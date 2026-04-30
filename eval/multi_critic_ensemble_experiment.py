"""Multi-Critic ensemble experiment.

Three Critics from three vendors evaluate the same hypotheses. Aggregates
their verdicts under a "conservative escalation" rule — accept only if all
three accept; any disagreement escalates to the most cautious verdict.

Critics:
    1. Anthropic Opus 4.7 (production)
    2. OpenAI GPT-5.5
    3. Google Gemini 2.5 Pro

The shared-seed methodology is identical to the cross-vendor 2-Critic
experiment: Scout + Synthesizer + Hypothesizer run once, then each Critic
evaluates the same hypotheses independently. Aggregation runs post-hoc on
the three critique outputs.

Aggregation rule (conservative escalation):
    If any critic says reject  -> ensemble = reject
    Else if any says flag_uncertain -> ensemble = flag_uncertain
    Else (all accept) -> ensemble = accept
    Confidence = min across critics
    Issues = union across critics

This rule prioritizes catching errors over efficiency. It's the right
default for a system whose stated goal is adversarial uncertainty surfacing.

Run:
    ./.venv/Scripts/python.exe eval/multi_critic_ensemble_experiment.py

Output:
    eval/results/multi_critic_{timestamp}_{scenario}.json
    traces/trace_..._multi_{condition}.{json,md} per critic per scenario
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
from agents.final_report_writer import final_report_writer_node
from agents.profile_synthesizer import profile_synthesizer_node
from agents.record_scout import record_scout_node
from agents.relationship_hypothesizer import relationship_hypothesizer_node
from agents.adversarial_critic import adversarial_critic_node
from tools.trace_writer import save_trace


_RESULTS_DIR = _REPO_ROOT / "eval" / "results"


_CRITICS = [
    {
        "name": "anthropic_opus_4_7",
        "vendor": "anthropic",
        "model": "claude-opus-4-7",
        "label": "Anthropic Opus 4.7",
    },
    {
        "name": "openai_gpt_5_5",
        "vendor": "openai",
        "model": "gpt-5.5",
        "label": "OpenAI GPT-5.5",
    },
    {
        "name": "google_gemini_2_5_pro",
        "vendor": "google",
        "model": "gemini-2.5-pro",
        "label": "Google Gemini 2.5 Pro",
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


# Verdict ordering for "most cautious" comparison.
# Higher value = more cautious / escalation-worthy.
_VERDICT_RANK = {
    "accept": 0,
    "flag_uncertain": 1,
    "reject": 2,
}


def aggregate_ensemble(critiques_per_critic: list[dict]) -> dict:
    """Apply the conservative escalation rule.

    Args:
        critiques_per_critic: list of dicts, each with 'critic_label' and
            'critique' keys for a single hypothesis.

    Returns:
        {
            "ensemble_verdict":    "accept" | "flag_uncertain" | "reject",
            "ensemble_confidence": float (min across critics),
            "issues_union":        list[str] (all unique issues),
            "agreement":           "unanimous" | "majority" | "split",
            "verdicts_per_critic": {label: verdict, ...},
            "confidences_per_critic": {label: confidence, ...},
        }
    """
    verdicts = [c["critique"].get("verdict") for c in critiques_per_critic]
    confidences = [
        c["critique"].get("confidence_in_critique") for c in critiques_per_critic
        if c["critique"].get("confidence_in_critique") is not None
    ]

    # Conservative escalation: max-rank verdict wins.
    valid_verdicts = [v for v in verdicts if v in _VERDICT_RANK]
    if valid_verdicts:
        ensemble_verdict = max(valid_verdicts, key=lambda v: _VERDICT_RANK[v])
    else:
        ensemble_verdict = "flag_uncertain"

    # Confidence: minimum across critics (most-cautious available signal).
    ensemble_confidence = min(confidences) if confidences else None

    # Issues: union, deduplicated by exact text match.
    seen: set[str] = set()
    issues_union: list[str] = []
    for c in critiques_per_critic:
        for issue in c["critique"].get("issues_found") or []:
            if issue not in seen:
                seen.add(issue)
                issues_union.append(issue)

    # Agreement classification.
    unique_verdicts = set(valid_verdicts)
    if len(unique_verdicts) == 1:
        agreement = "unanimous"
    elif len(valid_verdicts) > 0 and max(
        valid_verdicts.count(v) for v in unique_verdicts
    ) > len(valid_verdicts) / 2:
        agreement = "majority"
    else:
        agreement = "split"

    return {
        "ensemble_verdict": ensemble_verdict,
        "ensemble_confidence": ensemble_confidence,
        "issues_union": issues_union,
        "agreement": agreement,
        "verdicts_per_critic": {
            c["critic_label"]: c["critique"].get("verdict")
            for c in critiques_per_critic
        },
        "confidences_per_critic": {
            c["critic_label"]: c["critique"].get("confidence_in_critique")
            for c in critiques_per_critic
        },
    }


def run_scenario(scenario: dict, run_label: str) -> dict:
    print(f"\n{'='*70}")
    print(f"SCENARIO: {scenario['name']}  -  {scenario['query']}")
    print(f"{'='*70}")

    gedcom_text = scenario["gedcom"].read_text(encoding="utf-8", errors="replace")
    base_state = _initial_state(scenario["query"], scenario["target_person"], gedcom_text)

    # Shared seed: Scout + Synthesizer + Hypothesizer (all production models).
    print("Building shared seed (Scout + Synthesizer + Hypothesizer)...")
    t0 = time.time()
    seed = record_scout_node(base_state)
    seed_state = _merge(base_state, seed)
    seed = profile_synthesizer_node(seed_state)
    seed_state = _merge(seed_state, seed)
    seed = relationship_hypothesizer_node(seed_state)
    seed_state = _merge(seed_state, seed)
    t_seed = time.time() - t0
    print(
        f"  seed: {len(seed_state.get('hypotheses') or [])} hypotheses "
        f"in {t_seed:.1f}s"
    )

    if not seed_state.get("hypotheses"):
        print(f"  WARNING: no hypotheses — skipping")
        return {"scenario": scenario["name"], "skipped": True}

    # Run each Critic in turn.
    original_critic_llm = critic_module.llm
    critic_outputs: list[dict] = []

    try:
        for critic in _CRITICS:
            print(f"\nCritic: {critic['label']}")
            critic_module.llm = build_critic_llm(
                vendor=critic["vendor"], model=critic["model"]
            )
            state = copy.deepcopy(seed_state)
            t0 = time.time()
            try:
                critic_out = adversarial_critic_node(state)
                elapsed = time.time() - t0
                state = _merge(state, critic_out)
                state = _merge(state, final_report_writer_node(state))
                print(
                    f"  {critic['label']}: {len(state['critiques'])} critiques "
                    f"in {elapsed:.1f}s"
                )
                save_trace(
                    state,
                    label=f"{run_label}_{scenario['name']}_multi_{critic['name']}",
                )
                critic_outputs.append({
                    "critic": critic,
                    "critiques": state["critiques"],
                    "elapsed_sec": round(elapsed, 2),
                })
            except Exception as exc:
                elapsed = time.time() - t0
                print(f"  {critic['label']} FAILED in {elapsed:.1f}s: "
                      f"{type(exc).__name__}: {exc}")
                critic_outputs.append({
                    "critic": critic,
                    "critiques": [],
                    "elapsed_sec": round(elapsed, 2),
                    "error": f"{type(exc).__name__}: {exc}",
                })
    finally:
        critic_module.llm = original_critic_llm

    # Per-hypothesis ensemble aggregation.
    ensemble_per_hypothesis: list[dict] = []
    for hyp in seed_state["hypotheses"]:
        hid = hyp.get("hypothesis_id")
        per_critic = []
        for cout in critic_outputs:
            if cout.get("error"):
                continue
            critique = next(
                (c for c in cout["critiques"] if c.get("hypothesis_id") == hid),
                None,
            )
            if critique:
                per_critic.append({
                    "critic_label": cout["critic"]["label"],
                    "critique": critique,
                })
        ensemble = aggregate_ensemble(per_critic)
        ensemble_per_hypothesis.append({
            "hypothesis_id": hid,
            "proposed_relationship": hyp.get("proposed_relationship"),
            "subject_id": hyp.get("subject_id"),
            "related_id": hyp.get("related_id"),
            "ensemble": ensemble,
        })

    # Persist scenario result.
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = _RESULTS_DIR / f"multi_critic_{run_label}_{scenario['name']}.json"
    result_path.write_text(
        json.dumps(
            {
                "run_label": run_label,
                "scenario": scenario["name"],
                "query": scenario["query"],
                "target_person": scenario["target_person"],
                "seed": {
                    "hypothesis_count": len(seed_state["hypotheses"]),
                    "elapsed_sec": round(t_seed, 2),
                },
                "critics": [
                    {
                        "name": cout["critic"]["name"],
                        "label": cout["critic"]["label"],
                        "vendor": cout["critic"]["vendor"],
                        "model": cout["critic"]["model"],
                        "elapsed_sec": cout["elapsed_sec"],
                        "critiques": cout["critiques"],
                        **({"error": cout["error"]} if cout.get("error") else {}),
                    }
                    for cout in critic_outputs
                ],
                "ensemble_per_hypothesis": ensemble_per_hypothesis,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"  wrote {result_path}")

    # Print ensemble summary.
    try:
        print(f"\n--- {scenario['name']} ensemble ---")
        for entry in ensemble_per_hypothesis:
            ens = entry["ensemble"]
            hid = entry["hypothesis_id"].split(":")[-1]
            print(f"  [{hid}] ensemble: {ens['ensemble_verdict']:<14} "
                  f"min_conf={ens['ensemble_confidence']!s:<6} "
                  f"agreement={ens['agreement']}")
            for label, verdict in ens["verdicts_per_critic"].items():
                conf = ens["confidences_per_critic"].get(label)
                print(f"    {label:30s} {verdict!s:<14} conf={conf!s}")
    except UnicodeEncodeError as exc:
        print(f"  (print suppressed: {exc})")

    return {
        "scenario": scenario["name"],
        "ensemble_per_hypothesis": ensemble_per_hypothesis,
        "result_path": str(result_path),
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
    print(f"=== Multi-Critic Ensemble Experiment ({run_label}) ===")
    print(f"Critics: {' / '.join(c['label'] for c in _CRITICS)}")
    print(f"Aggregation: conservative escalation (any non-accept escalates)")

    summaries: list[dict] = []
    for scenario in _SCENARIOS:
        try:
            result = run_scenario(scenario, run_label)
            summaries.append(result)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            summaries.append({"scenario": scenario["name"], "error": str(exc)})

    print(f"\n{'='*70}")
    print(f"FINAL SUMMARY")
    print(f"{'='*70}")
    for s in summaries:
        if s.get("skipped") or s.get("error"):
            print(f"  {s['scenario']}: skipped/error")
            continue
        for entry in s["ensemble_per_hypothesis"]:
            ens = entry["ensemble"]
            hid = entry["hypothesis_id"].split(":")[-1]
            verdicts = list(ens["verdicts_per_critic"].values())
            print(f"  {s['scenario']:<20} [{hid}]  "
                  f"individual={verdicts}  "
                  f"ensemble={ens['ensemble_verdict']}  "
                  f"agreement={ens['agreement']}")


if __name__ == "__main__":
    main()
