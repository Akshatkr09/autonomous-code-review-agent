"""Tests for the LangGraph GitHub ingestion node using injected service behavior."""

from __future__ import annotations

from types import SimpleNamespace

from app.graph.nodes import fetch_pr_node
from app.graph.state import create_initial_state


def test_fetch_pr_node_maps_github_snapshot_into_graph_state(monkeypatch) -> None:
    snapshot = {
        "pr_url": "https://github.com/sample-owner/sample-repo/pull/12",
        "pr_title": "Improve calculations",
        "pr_body": "Refactor helpers.",
        "repository_full_name": "sample-owner/sample-repo",
        "pr_number": 12,
        "base_branch": "main",
        "head_branch": "feature/calculations",
        "base_sha": "base-sha",
        "head_sha": "head-sha",
        "head_repo_full_name": "sample-owner/sample-repo",
        "author": "sample-author",
        "file_changes": [{"filename": "src/calc.py", "status": "modified"}],
        "code_contents": {"src/calc.py": "def add(a, b):\n    return a + b\n"},
    }

    class FakeService:
        def __init__(self, *, token: str) -> None:
            assert token == "test-token"

        def fetch_pull_request(self, *, repository_full_name: str, pr_number: int):
            assert repository_full_name == "sample-owner/sample-repo"
            assert pr_number == 12
            return snapshot

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "app.graph.nodes.get_settings",
        lambda: SimpleNamespace(github_token="test-token"),
    )
    monkeypatch.setattr("app.graph.nodes.GitHubService", FakeService)

    state = create_initial_state(
        pr_url="https://github.com/sample-owner/sample-repo/pull/12",
        repository_full_name="sample-owner/sample-repo",
        pr_number=12,
    )
    result = fetch_pr_node(state)

    assert result["code_contents"] == snapshot["code_contents"]
    assert result["file_changes"] == snapshot["file_changes"]
    assert result["head_sha"] == "head-sha"
    assert result["review_status"] == "linting"
    assert result["history"][0]["event"] == "pull_request_fetched"


def test_fetch_pr_node_requires_configured_token(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.graph.nodes.get_settings",
        lambda: SimpleNamespace(github_token=""),
    )
    state = create_initial_state(
        pr_url="https://github.com/sample-owner/sample-repo/pull/12",
        repository_full_name="sample-owner/sample-repo",
        pr_number=12,
    )

    import pytest

    with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
        fetch_pr_node(state)
