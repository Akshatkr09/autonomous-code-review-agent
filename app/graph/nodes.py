"""LangGraph node functions.

The review router is implemented in this milestone. External-effect nodes are
explicit stubs and will be completed in their dedicated milestones; raising
NotImplementedError is intentional so an incomplete integration cannot appear
successful or silently write to GitHub.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, NoReturn

from app.graph.state import ReviewState


def _not_implemented(node_name: str) -> NoReturn:
    raise NotImplementedError(
        f"{node_name} is not implemented yet. It will be added in a later project milestone."
    )


def fetch_pr_node(state: ReviewState) -> dict[str, Any]:
    """Fetch PR metadata and changed file contents from GitHub (next milestone)."""
    _not_implemented("fetch_pr_node")


def lint_code_node(state: ReviewState) -> dict[str, Any]:
    """Run the custom linter against fetched files (sandbox milestone)."""
    _not_implemented("lint_code_node")


def propose_refactor_node(state: ReviewState) -> dict[str, Any]:
    """Generate a refactoring proposal using the configured LLM (LLM milestone)."""
    _not_implemented("propose_refactor_node")


def review_router_node(state: ReviewState) -> dict[str, Any]:
    """Record the current review routing decision for auditability.

    `is_approved is None` means the first proposal is ready and must be shown
    to a human. `False` means the human rejected it and the proposal node must
    run again with reviewer_feedback. `True` permits the write node to run.
    The graph's interrupt-before gate pauses execution before that write.
    """
    if state.get("is_approved") is False:
        status = "changes_requested"
        event = "review_rejected"
    elif state.get("is_approved") is True:
        status = "approved"
        event = "review_approved"
    else:
        status = "awaiting_approval"
        event = "proposal_ready_for_review"

    entry = {
        "node": "review_router_node",
        "event": event,
        "detail": state.get("reviewer_feedback") or "",
        "attempt": state.get("review_attempt", 0),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return {"review_status": status, "history": [entry]}



def apply_changes_node(state: ReviewState) -> dict[str, Any]:
    """Write approved files to GitHub (GitHub write milestone).

    The approval guard is deliberately present now, before the write operation
    is implemented, so an accidental route can never become an unauthorized
    repository write later.
    """
    if state.get("is_approved") is not True:
        raise PermissionError("Refusing to write changes without explicit reviewer approval")
    _not_implemented("apply_changes_node")
