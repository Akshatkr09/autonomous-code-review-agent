"""LangGraph node functions for the code-review workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, NoReturn

from app.config.settings import get_settings
from app.graph.state import ReviewState
from app.services.github_service import GitHubService


def _not_implemented(node_name: str) -> NoReturn:
    raise NotImplementedError(
        f"{node_name} is not implemented yet. It will be added in a later project milestone."
    )


def fetch_pr_node(state: ReviewState) -> dict[str, Any]:
    """Fetch PR metadata and changed Python files from GitHub.

    This node is read-only. It never creates branches, commits, or updates PRs.
    """
    settings = get_settings()
    if not settings.github_token:
        raise RuntimeError("GITHUB_TOKEN is not configured. Add it to your local .env file.")

    service = GitHubService(token=settings.github_token)
    try:
        snapshot = service.fetch_pull_request(
            repository_full_name=state["repository_full_name"],
            pr_number=state["pr_number"],
        )
    finally:
        service.close()

    history_entry = {
        "node": "fetch_pr_node",
        "event": "pull_request_fetched",
        "detail": (
            f"Fetched {len(snapshot['code_contents'])} Python source file(s) "
            f"from {snapshot['repository_full_name']}#{snapshot['pr_number']} "
            f"at head commit {snapshot['head_sha']}."
        ),
        "attempt": state.get("review_attempt", 0),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "pr_url": snapshot["pr_url"],
        "pr_title": snapshot["pr_title"],
        "pr_body": snapshot["pr_body"],
        "repository_full_name": snapshot["repository_full_name"],
        "pr_number": snapshot["pr_number"],
        "base_branch": snapshot["base_branch"],
        "head_branch": snapshot["head_branch"],
        "base_sha": snapshot["base_sha"],
        "head_sha": snapshot["head_sha"],
        "head_repo_full_name": snapshot["head_repo_full_name"],
        "author": snapshot["author"],
        "file_changes": snapshot["file_changes"],
        "code_contents": snapshot["code_contents"],
        "review_status": "linting",
        "error_message": None,
        "history": [history_entry],
    }


def lint_code_node(state: ReviewState) -> dict[str, Any]:
    """Run the custom linter against fetched files (sandbox milestone)."""
    _not_implemented("lint_code_node")


def propose_refactor_node(state: ReviewState) -> dict[str, Any]:
    """Generate a refactoring proposal using the configured LLM (LLM milestone)."""
    _not_implemented("propose_refactor_node")


def review_router_node(state: ReviewState) -> dict[str, Any]:
    """Record the current review routing decision for auditability."""
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
    """Write approved files to GitHub (write-back milestone)."""
    if state.get("is_approved") is not True:
        raise PermissionError("Refusing to write changes without explicit reviewer approval")
    _not_implemented("apply_changes_node")
