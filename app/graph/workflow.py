"""Construction of the stateful LangGraph review workflow."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    apply_changes_node,
    fetch_pr_node,
    lint_code_node,
    propose_refactor_node,
    review_router_node,
)
from app.graph.routing import route_after_review_decision
from app.graph.state import ReviewState


NodeFunction = Callable[[ReviewState], dict[str, Any]]

_DEFAULT_NODES: dict[str, NodeFunction] = {
    "fetch_pr_node": fetch_pr_node,
    "lint_code_node": lint_code_node,
    "propose_refactor_node": propose_refactor_node,
    "review_router_node": review_router_node,
    "apply_changes_node": apply_changes_node,
}


def build_review_graph(
    *,
    checkpointer: Any,
    node_overrides: Mapping[str, NodeFunction] | None = None,
):
    """Build and compile the review graph with a persistent checkpointer.

    `node_overrides` is a deliberate dependency-injection seam. It lets tests
    exercise real LangGraph routing, checkpoint, and interrupt behavior using
    deterministic fake integrations, without making real GitHub or LLM calls.
    Production code will use the real node functions.

    The graph pauses immediately before `apply_changes_node`, as required by
    the assessment. Resumption and reviewer feedback are applied to the same
    thread using its `thread_id` in the graph config.
    """
    if checkpointer is None:
        raise ValueError("A checkpointer is required for the human-approval workflow")

    nodes = dict(_DEFAULT_NODES)
    if node_overrides:
        unknown = set(node_overrides) - set(nodes)
        if unknown:
            raise ValueError(f"Unknown node override(s): {', '.join(sorted(unknown))}")
        nodes.update(node_overrides)

    builder = StateGraph(ReviewState)
    for name, node in nodes.items():
        builder.add_node(name, node)

    builder.add_edge(START, "fetch_pr_node")
    builder.add_edge("fetch_pr_node", "lint_code_node")
    builder.add_edge("lint_code_node", "propose_refactor_node")
    builder.add_edge("propose_refactor_node", "review_router_node")
    builder.add_conditional_edges(
        "review_router_node",
        route_after_review_decision,
        {
            "regenerate": "propose_refactor_node",
            "apply": "apply_changes_node",
        },
    )
    builder.add_edge("apply_changes_node", END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["apply_changes_node"],
    )
