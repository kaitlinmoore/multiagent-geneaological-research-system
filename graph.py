from langgraph.graph import StateGraph, END
from state import GenealogyState
from agents.record_scout import record_scout_node
from agents.profile_synthesizer import profile_synthesizer_node
from agents.relationship_hypothesizer import relationship_hypothesizer_node
from agents.adversarial_critic import adversarial_critic_node
from agents.final_report_writer import final_report_writer_node

def should_revise(state: GenealogyState) -> str:
    """Routing function: send back to Hypothesizer or finalize."""
    if state["status"] == "needs_revision" and state["revision_count"] < 2:
        return "revise"
    return "finalize"

def build_graph():
    graph = StateGraph(GenealogyState)

    # Register nodes
    graph.add_node("record_scout", record_scout_node)
    graph.add_node("profile_synthesizer", profile_synthesizer_node)
    graph.add_node("relationship_hypothesizer", relationship_hypothesizer_node)
    graph.add_node("adversarial_critic", adversarial_critic_node)
    graph.add_node("final_report_writer", final_report_writer_node)

    # Sequential edges
    graph.set_entry_point("record_scout")
    graph.add_edge("record_scout", "profile_synthesizer")
    graph.add_edge("profile_synthesizer", "relationship_hypothesizer")
    graph.add_edge("relationship_hypothesizer", "adversarial_critic")

    # Conditional edge: the revision loop OR finalize through the report writer.
    graph.add_conditional_edges(
        "adversarial_critic",
        should_revise,
        {
            "revise": "relationship_hypothesizer",      # loop back to Hypothesizer
            "finalize": "final_report_writer",          # compose report, then END
        }
    )
    graph.add_edge("final_report_writer", END)

    return graph.compile()