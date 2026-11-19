"""Conditional routing functions for the review graph."""

from __future__ import annotations

from app.graph.state import ReviewState


def route_after_review_decision(state: ReviewState) -> str:
    """Route rejected proposals back to refactoring; otherwise reach the HITL gate.

    A missing decision (`None`) means a newly generated proposal is ready for
    human review. The graph then advances to `apply_changes_node`, where the
    compile-time interrupt stops execution before any repository write.
    """
    return "regenerate" if state.get("is_approved") is False else "apply"
