"""Shared state definition for one Pull Request review thread."""

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
    """Shared state for the assessment's code-review workflow."""

    # Required by the project brief.
    pr_url: str
    code_contents: dict[str, str]
    lint_errors: list[dict[str, Any]]
    refactored_code: dict[str, str]
    is_approved: bool | None
    reviewer_feedback: str | None
    history: Annotated[list[ReviewHistoryEntry], operator.add]

    # GitHub identity and PR ingestion metadata.
    repository_full_name: str
    pr_number: int
    pr_title: str
    pr_body: str
    base_branch: str
    head_branch: str
    base_sha: str | None
    head_sha: str | None
    head_repo_full_name: str
    author: str
    file_changes: list[dict[str, Any]]

    # Workflow metadata.
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
    """Create and validate the complete initial state for a review thread."""
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
        "pr_title": "",
        "pr_body": "",
        "base_branch": base_branch,
        "head_branch": head_branch,
        "base_sha": None,
        "head_sha": None,
        "head_repo_full_name": repository_full_name,
        "author": "unknown",
        "file_changes": [],
        "review_status": "queued",
        "review_attempt": 0,
        "commit_sha": None,
        "error_message": None,
    }
