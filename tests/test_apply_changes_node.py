"""Tests for approval-gated GitHub write-back node."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.graph.nodes import apply_changes_node
from app.graph.state import create_initial_state


class FakeGitHubService:
    calls = []

    def __init__(self, *, token: str):
        assert token == "test-github-token"

    def commit_refactored_files(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "commit_sha": "approved-commit-sha",
            "commit_url": "https://github.com/sample-owner/sample-repo/commit/approved-commit-sha",
            "commit_branch": "feature/example",
            "commit_repository_full_name": "sample-owner/sample-repo",
        }

    def close(self):
        pass


def _state(approved: bool = True):
    state = create_initial_state(
        pr_url="https://github.com/sample-owner/sample-repo/pull/17",
        repository_full_name="sample-owner/sample-repo",
        pr_number=17,
        head_branch="feature/example",
    )
    state.update(
        {
            "head_sha": "reviewed-head-sha",
            "code_contents": {"src/calc.py": "def add(a,b):return a+b"},
            "refactored_code": {"src/calc.py": "def add(a, b):\n    return a + b\n"},
            "is_approved": approved,
            "review_attempt": 2,
        }
    )
    return state


def _patch(monkeypatch):
    FakeGitHubService.calls = []
    monkeypatch.setattr(
        "app.graph.nodes.get_settings",
        lambda: SimpleNamespace(github_token="test-github-token"),
    )
    monkeypatch.setattr("app.graph.nodes.GitHubService", FakeGitHubService)


def test_apply_node_commits_only_explicitly_approved_proposal(monkeypatch):
    _patch(monkeypatch)

    result = apply_changes_node(_state())

    assert result["commit_sha"] == "approved-commit-sha"
    assert result["review_status"] == "completed"
    assert result["commit_branch"] == "feature/example"
    assert result["history"][0]["event"] == "approved_changes_committed"
    assert len(FakeGitHubService.calls) == 1
    assert FakeGitHubService.calls[0]["expected_head_sha"] == "reviewed-head-sha"


def test_apply_node_refuses_unapproved_proposal(monkeypatch):
    _patch(monkeypatch)

    with pytest.raises(PermissionError, match="explicit reviewer approval"):
        apply_changes_node(_state(approved=False))
    assert FakeGitHubService.calls == []


def test_apply_node_requires_exact_original_file_set(monkeypatch):
    _patch(monkeypatch)
    state = _state()
    state["refactored_code"] = {"src/other.py": "x = 1\n"}

    with pytest.raises(ValueError, match="exactly the Python files"):
        apply_changes_node(state)
    assert FakeGitHubService.calls == []


def test_apply_node_requires_reviewed_head_sha(monkeypatch):
    _patch(monkeypatch)
    state = _state()
    state["head_sha"] = None

    with pytest.raises(ValueError, match="head SHA and branch"):
        apply_changes_node(state)
    assert FakeGitHubService.calls == []
