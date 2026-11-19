"""Shared state definition for one Pull Request review thread.

Keep the state data-oriented: store source files, diagnostics, proposed files,
review decisions, and an audit trail. Build prompts inside nodes rather than
persisting prompt strings in the graph state.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


ReviewStatus = Literal[
    "queued",
    "fetching",
    "linting",
    "proposing",
    "awaiting_approval",
    "changes_requested",
    "approved",
    "completed",
    "failed",
]


class ReviewHistoryEntry(TypedDict, total=False):
    """One auditable event in a review thread."""

    node: str
    event: str
    detail: str
    attempt: int
    timestamp: str


class ReviewState(TypedDict):
    """The shared state for the assessment's code-review workflow.

    The first seven fields are the keys explicitly requested in the brief.
    Additional fields hold GitHub identifiers and execution metadata needed by
    the implementation.
    """

    # Required by the assessment brief.
    pr_url: str
    code_contents: dict[str, str]
    lint_errors: list[dict[str, Any]]
    refactored_code: dict[str, str]
    is_approved: bool | None
    reviewer_feedback: str | None
    history: Annotated[list[ReviewHistoryEntry], operator.add]

    # Additional workflow metadata.
    repository_full_name: str
    pr_number: int
    base_branch: str
    head_branch: str
    review_status: ReviewStatus
    review_attempt: int
    commit_sha: str | None
    error_message: str | None


def create_initial_state(
    *,
    pr_url: str,
    repository_full_name: str,
    pr_number: int,
    base_branch: str = "main",
    head_branch: str = "",
) -> ReviewState:
    """Create a complete, predictable initial state for a new review thread."""
    if not pr_url.strip():
        raise ValueError("pr_url must not be empty")
    if not repository_full_name.strip() or "/" not in repository_full_name:
        raise ValueError("repository_full_name must use the 'owner/repository' format")
    if pr_number < 1:
        raise ValueError("pr_number must be a positive integer")

    return {
        "pr_url": pr_url,
        "code_contents": {},
        "lint_errors": [],
        "refactored_code": {},
        "is_approved": None,
        "reviewer_feedback": None,
        "history": [],
        "repository_full_name": repository_full_name,
        "pr_number": pr_number,
        "base_branch": base_branch,
        "head_branch": head_branch,
        "review_status": "queued",
        "review_attempt": 0,
        "commit_sha": None,
        "error_message": None,
    }
