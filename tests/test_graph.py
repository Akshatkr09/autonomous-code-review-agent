"""Tests for the LangGraph state contract, routing, and approval interrupt."""

from __future__ import annotations

from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.graph.nodes import apply_changes_node
from app.graph.routing import route_after_review_decision
from app.graph.state import ReviewState, create_initial_state
from app.graph.workflow import build_review_graph


@pytest.fixture
def initial_state() -> ReviewState:
    return create_initial_state(
        pr_url="https://github.com/example/demo/pull/7",
        repository_full_name="example/demo",
        pr_number=7,
        base_branch="main",
        head_branch="feature/example",
    )


def test_initial_state_contains_assessment_keys(initial_state: ReviewState) -> None:
    expected = {
        "pr_url",
        "code_contents",
        "lint_errors",
        "refactored_code",
        "is_approved",
        "reviewer_feedback",
        "history",
    }
    assert expected.issubset(initial_state.keys())
    assert initial_state["is_approved"] is None
    assert initial_state["history"] == []
    assert initial_state["review_status"] == "queued"


def test_initial_state_validates_pr_identity() -> None:
    with pytest.raises(ValueError, match="pr_url"):
        create_initial_state(pr_url="", repository_full_name="example/demo", pr_number=1)
    with pytest.raises(ValueError, match="owner/repository"):
        create_initial_state(pr_url="https://github.com/example/demo/pull/1", repository_full_name="demo", pr_number=1)
    with pytest.raises(ValueError, match="positive integer"):
        create_initial_state(pr_url="https://github.com/example/demo/pull/0", repository_full_name="example/demo", pr_number=0)


def test_review_router_routes_pending_and_approved_to_apply() -> None:
    assert route_after_review_decision({"is_approved": None}) == "apply"
    assert route_after_review_decision({"is_approved": True}) == "apply"


def test_review_router_routes_rejection_back_to_refactor() -> None:
    assert route_after_review_decision({"is_approved": False}) == "regenerate"


def test_apply_node_refuses_unapproved_write() -> None:
    with pytest.raises(PermissionError, match="explicit reviewer approval"):
        apply_changes_node({"is_approved": False})


def _fake_fetch(state: ReviewState) -> dict[str, Any]:
    return {"code_contents": {"sample.py": "def add(a, b): return a+b"}, "review_status": "linting"}


def _fake_lint(state: ReviewState) -> dict[str, Any]:
    return {"lint_errors": [{"file": "sample.py", "message": "formatting issue"}], "review_status": "proposing"}


def _fake_propose(state: ReviewState) -> dict[str, Any]:
    feedback = state.get("reviewer_feedback") or "initial proposal"
    attempt = state.get("review_attempt", 0) + 1
    return {
        "refactored_code": {"sample.py": f"# proposal {attempt}; context: {feedback}"},
        "review_attempt": attempt,
        # A fresh proposal must wait for a fresh human decision.
        "is_approved": None,
        "review_status": "awaiting_approval",
    }


def _fake_apply(state: ReviewState) -> dict[str, Any]:
    assert state.get("is_approved") is True
    return {"commit_sha": "test-commit-sha", "review_status": "completed"}


def _test_graph() -> Any:
    return build_review_graph(
        checkpointer=InMemorySaver(),
        node_overrides={
            "fetch_pr_node": _fake_fetch,
            "lint_code_node": _fake_lint,
            "propose_refactor_node": _fake_propose,
            "apply_changes_node": _fake_apply,
        },
    )


def test_graph_pauses_before_write_and_resumes_after_feedback(initial_state: ReviewState) -> None:
    graph = _test_graph()
    config = {"configurable": {"thread_id": "test-review-7"}}

    # First run reaches the write node but is interrupted before it executes.
    graph.invoke(initial_state, config)
    paused = graph.get_state(config)
    assert paused.next == ("apply_changes_node",)
    assert paused.values["review_status"] == "awaiting_approval"
    assert paused.values["commit_sha"] is None
    assert paused.values["review_attempt"] == 1

    # Simulate the approval endpoint recording a rejection at the router node.
    graph.update_state(
        config,
        {
            "is_approved": False,
            "reviewer_feedback": "Use a clearer function name",
            "review_status": "changes_requested",
        },
        as_node="review_router_node",
    )
    graph.invoke(None, config)

    # The rejected proposal is regenerated and the graph pauses for review again.
    paused_again = graph.get_state(config)
    assert paused_again.next == ("apply_changes_node",)
    assert paused_again.values["review_attempt"] == 2
    assert "Use a clearer function name" in paused_again.values["refactored_code"]["sample.py"]
    assert paused_again.values["commit_sha"] is None

    # Approval is recorded against the same thread; only now may the write run.
    graph.update_state(
        config,
        {"is_approved": True, "review_status": "approved"},
        as_node="review_router_node",
    )
    final_state = graph.invoke(None, config)

    assert final_state["commit_sha"] == "test-commit-sha"
    assert final_state["review_status"] == "completed"
