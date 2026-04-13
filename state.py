from typing import TypedDict, Optional, List


class GenealogyState(TypedDict):
    # Input
    query: str                          # Research question (e.g., "Who were the parents of X?")
    target_person: dict                 # Name, approx dates, locations
    gedcom_text: str                    # Raw GEDCOM file contents
    gedcom_persons: List[dict]          # Persons parsed from GEDCOM
    dna_csv: Optional[str]              # Phase 3

    # Agent outputs
    retrieved_records: List[dict]       # Raw records from Record Scout
    profiles: List[dict]                # Consolidated person profiles from Synthesizer
    hypotheses: List[dict]              # Proposed relationships w/ evidence + confidence
    critiques: List[dict]               # Critic responses to hypotheses
    final_report: str

    # Control
    revision_count: int                 # Adversarial loop iterations (max 2)
    status: str                         # "running" | "needs_revision" | "complete"
    trace_log: List[str]                # Running log of agent actions

    # Experiment toggle — optional. Set to "unfiltered" to skip the Critic
    # isolation filter (Condition B of the A/B experiment). Defaults to
    # "filtered" (Condition A) inside the Critic node when absent or None.
    isolation_mode: Optional[str]
