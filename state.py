import operator
from typing import Annotated, TypedDict, Optional, List


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
    dna_analysis: Optional[dict]        # DNA Analyst output (match distribution, cross-refs)
    final_report: str

    # Control
    revision_count: int                 # Adversarial loop iterations (max 2)
    status: str                         # "running" | "needs_revision" | "complete"

    # trace_log uses operator.add as a reducer so parallel nodes (e.g.
    # profile_synthesizer + dna_analyst running concurrently after the
    # Record Scout) can each append entries without a concurrent-write
    # conflict. Each agent node returns ONLY its new entries; the reducer
    # concatenates them onto the accumulated log.
    trace_log: Annotated[List[str], operator.add]

    # Experiment toggle — optional. Set to "unfiltered" to skip the Critic
    # isolation filter (Condition B of the A/B experiment). Defaults to
    # "filtered" (Condition A) inside the Critic node when absent or None.
    isolation_mode: Optional[str]
