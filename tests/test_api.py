"""API integration tests using real SQLite checkpoints and deterministic nodes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.graph.runtime import ReviewRuntime
from app.main import create_app


def _fake_fetch(state: dict) -> dict[str, Any]:
    return {
        "code_contents": {"sample.py": "def add(a,b):return a+b"},
        "pr_title": "Test PR",
        "head_sha": "reviewed-head-sha",
        "head_branch": "feature/example",
        "review_status": "linting",
    }


def _fake_lint(state: dict) -> dict[str, Any]:
    return {
        "lint_results": [{"filename": "sample.py", "ok": False}],
        "lint_errors": [{"file": "sample.py", "tool": "black", "message": "formatting"}],
        "review_status": "proposing",
    }


def _fake_propose(state: dict) -> dict[str, Any]:
    attempt = state.get("review_attempt", 0) + 1
    feedback = state.get("reviewer_feedback") or "initial proposal"
    return {
        "refactored_code": {"sample.py": f"# attempt {attempt}: {feedback}\ndef add(a, b):\n    return a + b\n"},
        "refactor_summary": f"Proposal attempt {attempt}",
        "review_attempt": attempt,
        "is_approved": None,
        "review_status": "awaiting_approval",
    }


def _fake_apply(state: dict) -> dict[str, Any]:
    assert state.get("is_approved") is True
    return {
        "commit_sha": "fake-commit",
        "commit_url": "https://github.com/sample-owner/sample-repo/commit/fake-commit",
        "commit_branch": "feature/example",
        "commit_repository_full_name": "sample-owner/sample-repo",
        "review_status": "completed",
    }


def _node_overrides():
    return {
        "fetch_pr_node": _fake_fetch,
        "lint_code_node": _fake_lint,
        "propose_refactor_node": _fake_propose,
        "apply_changes_node": _fake_apply,
    }


def _webhook_payload(action: str = "opened") -> dict:
    return {
        "action": action,
        "repository": {
            "full_name": "sample-owner/sample-repo",
            "html_url": "https://github.com/sample-owner/sample-repo",
        },
        "pull_request": {
            "number": 12,
            "html_url": "https://github.com/sample-owner/sample-repo/pull/12",
            "base": {"ref": "main", "sha": "base-sha"},
            "head": {"ref": "feature/example", "sha": "head-sha"},
        },
    }


def _client(database_path: Path) -> TestClient:
    app = create_app(
        runtime_factory=lambda: ReviewRuntime(
            database_path,
            node_overrides=_node_overrides(),
        )
    )
    return TestClient(app)


def test_webhook_starts_review_and_pauses_for_human(tmp_path: Path) -> None:
    with _client(tmp_path / "reviews.sqlite") as client:
        response = client.post("/api/webhooks/github", json=_webhook_payload())

        assert response.status_code == 202
        body = response.json()
        assert body["accepted"] is True
        assert body["ignored"] is False
        assert body["status"] == "awaiting_approval"
        assert body["waiting_for_reviewer"] is True
        assert body["review_attempt"] == 1
        assert body["next_nodes"] == ["apply_changes_node"]
        assert body["pr_number"] == 12


def test_rejection_feedback_regenerates_proposal_and_pauses_again(tmp_path: Path) -> None:
    with _client(tmp_path / "reviews.sqlite") as client:
        started = client.post("/api/webhooks/github", json=_webhook_payload()).json()
        thread_id = started["thread_id"]

        rejected = client.post(
            f"/api/reviews/{thread_id}/approve",
            json={"approved": False, "feedback": "Use list comprehensions instead of loops"},
        )

        assert rejected.status_code == 200
        body = rejected.json()
        assert body["status"] == "awaiting_approval"
        assert body["waiting_for_reviewer"] is True
        assert body["review_attempt"] == 2
        assert "Use list comprehensions" in body["refactored_code"]["sample.py"]


def test_approval_resumes_graph_and_completes_writeback(tmp_path: Path) -> None:
    with _client(tmp_path / "reviews.sqlite") as client:
        started = client.post("/api/webhooks/github", json=_webhook_payload()).json()
        thread_id = started["thread_id"]

        approved = client.post(
            f"/api/reviews/{thread_id}/approve",
            json={"approved": True},
        )

        assert approved.status_code == 200
        body = approved.json()
        assert body["status"] == "completed"
        assert body["approval_recorded"] is True
        assert body["next_nodes"] == []
        assert body["waiting_for_reviewer"] is False
        assert body["commit_sha"] == "fake-commit"
        assert body["commit_branch"] == "feature/example"
        assert "committed" in body["message"].lower()


def test_unsupported_webhook_action_is_ignored(tmp_path: Path) -> None:
    with _client(tmp_path / "reviews.sqlite") as client:
        response = client.post(
            "/api/webhooks/github",
            json=_webhook_payload(action="closed"),
        )
        assert response.status_code == 202
        assert response.json()["ignored"] is True


def test_unknown_review_thread_returns_404(tmp_path: Path) -> None:
    with _client(tmp_path / "reviews.sqlite") as client:
        response = client.get("/api/reviews/not-a-real-thread")
        assert response.status_code == 404
