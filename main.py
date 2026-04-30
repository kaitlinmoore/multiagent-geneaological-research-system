import os
from dotenv import load_dotenv

# override=True so .env wins over any parent-process env vars. Some sandboxed
# execution environments (e.g. coding agents) pre-set ANTHROPIC_API_KEY to an
# empty string to block subprocess API calls, which silently breaks the LLM
# unless we explicitly let .env take precedence.
load_dotenv(override=True)

from graph import build_graph
from tools.trace_writer import save_trace

GEDCOM_PATH = "data/The Kennedy Family.ged"
DNA_CSV_PATH = "data/DNA_demo/John_Fitzgerald_Kennedy_synthetic_DNA.csv"  # synthetic, no PII
# DNA_CSV_PATH = "data/DNA/GEDMATH-JamesMoore.csv"  # real data — gitignored
TRACE_LABEL = "jfk_parents_with_synthetic_dna"


def main():
    graph = build_graph()

    with open(GEDCOM_PATH, "r", encoding="utf-8", errors="replace") as f:
        gedcom_text = f.read()

    dna_csv = None
    if DNA_CSV_PATH:
        try:
            with open(DNA_CSV_PATH, "r", encoding="utf-8-sig") as f:
                dna_csv = f.read()
        except UnicodeDecodeError:
            with open(DNA_CSV_PATH, "r", encoding="latin-1") as f:
                dna_csv = f.read()

    initial_state = {
        "query": "Who were the parents of John F. Kennedy?",
        "target_person": {"name": "John Fitzgerald Kennedy", "approx_birth": "1917", "location": "Brookline, MA"},
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

    result = graph.invoke(initial_state)

    print("=== Pipeline complete ===")
    print(f"status:            {result['status']}")
    print(f"revision_count:    {result['revision_count']}")
    print(f"retrieved_records: {len(result['retrieved_records'])}")
    print(f"profiles:          {len(result['profiles'])}")
    print(f"hypotheses:        {len(result['hypotheses'])}")
    print(f"critiques:         {len(result['critiques'])}")
    print(f"final_report:      {len(result['final_report'])} chars")
    dna = result.get("dna_analysis")
    if dna:
        print(f"dna_analysis:      {dna.get('total_matches', 0)} matches, {dna.get('aggregate_consistency', '?')}")

    trace_paths = save_trace(result, label=TRACE_LABEL)
    if trace_paths:
        print()
        print(f"trace JSON: {trace_paths['json_path']}")
        print(f"trace MD:   {trace_paths['md_path']}")


if __name__ == "__main__":
    main()
