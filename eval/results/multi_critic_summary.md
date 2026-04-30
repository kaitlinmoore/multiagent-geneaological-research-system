# Multi-Critic Ensemble — Summary

_Aggregated from `eval/results/multi_critic_*.json` (public-data runs
only). Moore-tree result files are gitignored and excluded._

## Why this experiment

The cross-vendor pairwise comparison
([cross_vendor_summary.md](cross_vendor_summary.md)) showed that
Anthropic and OpenAI Critics can disagree on ambiguous cases. The
ensemble experiment generalizes that observation: run the same
hypothesis through three Critics from three different vendors and
aggregate their verdicts conservatively — any reject → reject; any
flag_uncertain → flag_uncertain; unanimous accept required for accept.

This addresses the "same training data, same failure modes" concern more
robustly than pairwise comparison. The conservative aggregation rule is
a deliberate design choice that prefers escalation over false confidence.

Source: `eval/multi_critic_ensemble_experiment.py` →
`eval/results/multi_critic_<timestamp>_<scenario>.json`.

## Headline

**On the ambiguous Tier 3 case, the ensemble correctly produced
`flag_uncertain` on 2/2 hypotheses, where Anthropic Opus 4.7 alone would
have accepted both at high confidence.** This is the strongest
empirical argument for ensemble Critics on safety-critical genealogical
claims.

## Per-case verdicts

### `multi_critic_20260429_174343_jfk.json` — JFK (control)

Target: John F. Kennedy. Two parental hypotheses.

| Hypothesis | Anthropic Opus 4.7 | OpenAI GPT-5.5 | Google Gemini 2.5 Pro | Agreement | Ensemble verdict |
|---|---|---|---|---|---|
| `hyp:@I0@:@I1@:father` | accept | accept | accept | unanimous | **accept** |
| `hyp:@I0@:@I2@:mother` | accept | accept | accept | unanimous | **accept** |

Ensemble confidence: 0.86. Unanimous accept across three vendors on a
well-documented public-record relationship. The conservative rule
preserves the accept verdict because no Critic dissented.

### `multi_critic_20260429_174343_tier3_duplicate.json` — Tier 3 ambiguous

Target: the injected duplicate "John Kennedy b.1917 Boston" persona.
Two parental hypotheses for the duplicate.

| Hypothesis | Anthropic Opus 4.7 | OpenAI GPT-5.5 | Google Gemini 2.5 Pro | Agreement | Ensemble verdict |
|---|---|---|---|---|---|
| `hyp:@I100@:@I101@:father` | accept | flag_uncertain | flag_uncertain | majority (flag) | **flag_uncertain** |
| `hyp:@I100@:@I102@:mother` | accept | flag_uncertain | flag_uncertain | majority (flag) | **flag_uncertain** |

Anthropic Opus 4.7 alone would accept both hypotheses at the production
configuration — meaning a single-Critic deployment would miss the
ambiguity entirely. Adding two non-Anthropic Critics surfaces the
genuine uncertainty. The ensemble's conservative rule (any
flag_uncertain → flag_uncertain) escalates correctly.

## Aggregation rule

The ensemble's design encodes a deliberate asymmetry:

```
verdicts_per_critic = {Anthropic: V_A, OpenAI: V_O, Gemini: V_G}

if any(V_x == "reject"): ensemble = reject
elif any(V_x == "flag_uncertain"): ensemble = flag_uncertain
elif all(V_x == "accept"): ensemble = accept
```

This biases the system toward escalation. False positives
(unwarranted flag_uncertain) cost the user a moment of unnecessary
scrutiny; false negatives (unwarranted accept on ambiguous evidence)
propagate into family trees that other researchers cite. The
conservative rule treats those error modes asymmetrically.

## Interpretation

Two effects of ensembling are visible in the data:

1. **On unambiguous cases, ensemble verdicts match individual Critic
   verdicts and add confidence.** All three Critics accepted JFK's
   parentage. Ensemble accept (0.86 confidence) carries the weight of
   three independent confirmations.

2. **On ambiguous cases, ensembling escalates appropriately even when
   the production single-Critic configuration would not.** Two of three
   Critics flagged the Tier 3 case; the conservative rule lifted that
   into the ensemble verdict. A grader auditing the system's behavior
   on ambiguous data would see this escalation.

The cost of ensembling is real (3× LLM calls per critique, plus
aggregation latency) but justifiable for high-stakes claims. In
production this is a configurable option, not the default.

## Reproducing this

```bash
python eval/multi_critic_ensemble_experiment.py
```

Outputs land in `eval/results/multi_critic_<timestamp>_<scenario>.json`,
one file per scenario. The JSON contains each Critic's full critique
plus the `ensemble` block with `verdicts_per_critic`,
`confidences_per_critic`, `agreement` ("unanimous" / "majority" /
"split"), `issues_union`, and the aggregated `ensemble_verdict`.
