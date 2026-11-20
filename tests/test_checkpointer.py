"""Persistence tests for SQLite-backed LangGraph review threads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.graph.runtime import ReviewRuntime


def _fake_fetch(state: dict) -> dict[str, Any]:
    return {"code_contents": {"sample.py": "x = 1\n"}, "review_status": "linting"}


def _fake_lint(state: dict) -> dict[str, Any]:
    return {"lint_results": [], "lint_errors": [], "review_status": "proposing"}


def _fake_propose(state: dict) -> dict[str, Any]:
    return {
        "refactored_code": {"sample.py": "x = 1\n"},
        "refactor_summary": "No change required",
        "review_attempt": state.get("review_attempt", 0) + 1,
        "is_approved": None,
        "review_status": "awaiting_approval",
    }


def _overrides():
    return {
        "fetch_pr_node": _fake_fetch,
        "lint_code_node": _fake_lint,
        "propose_refactor_node": _fake_propose,
    }


def test_sqlite_checkpoint_survives_runtime_restart(tmp_path: Path) -> None:
    database = tmp_path / "persistent.sqlite"
    thread_id = "persistent-thread-123"

    first_runtime = ReviewRuntime(database, node_overrides=_overrides())
    first_runtime.start()
    first_runtime.start_review(
        thread_id=thread_id,
        pr_url="https://github.com/sample-owner/sample-repo/pull/12",
        repository_full_name="sample-owner/sample-repo",
        pr_number=12,
        base_branch="main",
        head_branch="feature/example",
    )
    first_runtime.close()

    second_runtime = ReviewRuntime(database, node_overrides=_overrides())
    second_runtime.start()
    try:
        snapshot = second_runtime.get_review(thread_id)
        assert snapshot is not None
        assert snapshot.values["review_status"] == "awaiting_approval"
        assert snapshot.values["review_attempt"] == 1
        assert snapshot.next == ("apply_changes_node",)
    finally:
        second_runtime.close()
