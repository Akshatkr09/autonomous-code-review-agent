"""LangGraph node functions for the code-review workflow."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, NoReturn

from app.config.settings import get_settings
from app.graph.state import ReviewState
from app.services.github_service import GitHubService
from app.services.refactor_service import RefactorService
from app.tools.linter import run_linter_tool


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
    """Run Flake8 and Black for every fetched Python file via the Docker tool."""
    code_contents = state.get("code_contents") or {}
    if not code_contents:
        raise ValueError("No Python source files are available to lint.")

    lint_results: list[dict[str, Any]] = []
    lint_errors: list[dict[str, Any]] = []

    for filename, source in code_contents.items():
        raw_result = run_linter_tool.invoke(
            {"code_string": source, "filename": filename}
        )
        try:
            result = json.loads(raw_result)
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Linter returned an invalid result for {filename}.") from exc

        if result.get("category") != "lint_result":
            raise RuntimeError(
                f"Linter infrastructure failed for {filename}: {result.get('output', 'Unknown error')}"
            )

        lint_results.append(result)
        if result.get("flake8_exit_code"):
            lint_errors.append(
                {
                    "file": filename,
                    "tool": "flake8",
                    "message": result.get("output", "Flake8 reported issues."),
                }
            )
        if result.get("black_exit_code"):
            lint_errors.append(
                {
                    "file": filename,
                    "tool": "black",
                    "message": result.get("output", "Black reported formatting differences."),
                }
            )

    history_entry = {
        "node": "lint_code_node",
        "event": "linting_completed",
        "detail": (
            f"Checked {len(lint_results)} Python file(s); "
            f"{len(lint_errors)} linter check(s) reported issues."
        ),
        "attempt": state.get("review_attempt", 0),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "lint_results": lint_results,
        "lint_errors": lint_errors,
        "review_status": "proposing",
        "history": [history_entry],
    }


def propose_refactor_node(state: ReviewState) -> dict[str, Any]:
    """Generate a complete, feedback-aware refactoring proposal using the LLM."""
    code_contents = state.get("code_contents") or {}
    if not code_contents:
        raise ValueError("No Python source files are available to refactor.")

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Add it to your local .env file."
        )

    service = RefactorService(
        api_key=settings.openai_api_key,
        model_name=settings.openai_model,
    )
    proposal = service.generate_refactor(
        code_contents=code_contents,
        lint_errors=state.get("lint_errors") or [],
        reviewer_feedback=state.get("reviewer_feedback"),
        review_attempt=state.get("review_attempt", 0),
    )

    attempt = state.get("review_attempt", 0) + 1
    history_entry = {
        "node": "propose_refactor_node",
        "event": "refactor_proposed",
        "detail": proposal["refactor_summary"],
        "attempt": attempt,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "refactored_code": proposal["refactored_code"],
        "refactor_summary": proposal["refactor_summary"],
        "review_attempt": attempt,
        "is_approved": None,
        "review_status": "awaiting_approval",
        "error_message": None,
        "history": [history_entry],
    }


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
    """Commit the approved proposal to the exact PR head branch reviewed by the agent."""
    if state.get("is_approved") is not True:
        raise PermissionError("Refusing to write changes without explicit reviewer approval")

    original_files = state.get("code_contents") or {}
    proposed_files = state.get("refactored_code") or {}
    if not original_files:
        raise ValueError("No original source files are recorded for this review")
    if not proposed_files:
        raise ValueError("No approved refactored files are available to commit")
    if set(proposed_files) != set(original_files):
        raise ValueError(
            "Approved proposal must contain exactly the Python files fetched from the Pull Request"
        )

    head_sha = state.get("head_sha")
    head_branch = state.get("head_branch")
    if not head_sha or not head_branch:
        raise ValueError("The reviewed Pull Request head SHA and branch are missing")

    settings = get_settings()
    if not settings.github_token:
        raise RuntimeError("GITHUB_TOKEN is not configured. Add it to your local .env file.")

    service = GitHubService(token=settings.github_token)
    try:
        commit_result = service.commit_refactored_files(
            repository_full_name=state["repository_full_name"],
            pr_number=state["pr_number"],
            expected_head_sha=head_sha,
            expected_head_branch=head_branch,
            refactored_code=proposed_files,
            commit_message=(
                f"chore: apply approved refactoring for PR #{state['pr_number']}"
            ),
        )
    finally:
        service.close()

    history_entry = {
        "node": "apply_changes_node",
        "event": "approved_changes_committed",
        "detail": (
            f"Committed {len(proposed_files)} approved Python file(s) to "
            f"{commit_result['commit_repository_full_name']}:{commit_result['commit_branch']} "
            f"({commit_result['commit_sha']})."
        ),
        "attempt": state.get("review_attempt", 0),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "commit_sha": commit_result["commit_sha"],
        "commit_url": commit_result.get("commit_url", ""),
        "commit_branch": commit_result["commit_branch"],
        "commit_repository_full_name": commit_result["commit_repository_full_name"],
        "review_status": "completed",
        "error_message": None,
        "history": [history_entry],
    }
