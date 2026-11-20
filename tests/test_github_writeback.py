"""Unit tests for safe, single-commit GitHub PR write-back."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services.github_service import (
    GitHubService,
    GitHubIntegrationError,
    GitHubWriteConflict,
)


class FakeRef:
    def __init__(self, sha: str) -> None:
        self.object = SimpleNamespace(sha=sha)
        self.updated_to: str | None = None

    def edit(self, sha: str, *, force: bool = False) -> None:
        assert force is False
        self.updated_to = sha
        self.object.sha = sha


class FakeHeadRepository:
    full_name = "sample-owner/sample-repo"

    def __init__(self, sha: str = "reviewed-head-sha") -> None:
        self.ref = FakeRef(sha)
        self.tree = SimpleNamespace(sha="base-tree-sha")
        self.parent = SimpleNamespace(tree=self.tree, sha=sha)
        self.tree_elements = None
        self.commit_message = None
        self.commit = SimpleNamespace(sha="new-commit-sha", html_url="https://github.com/sample-owner/sample-repo/commit/new-commit-sha")

    def get_git_ref(self, ref: str) -> FakeRef:
        assert ref == "heads/feature/fix-calculation"
        return self.ref

    def get_git_commit(self, sha: str) -> Any:
        assert sha == "reviewed-head-sha"
        return self.parent

    def create_git_tree(self, elements, base_tree):
        self.tree_elements = elements
        assert base_tree is self.tree
        return SimpleNamespace(sha="new-tree-sha")

    def create_git_commit(self, message, tree, parents):
        self.commit_message = message
        assert tree.sha == "new-tree-sha"
        assert parents == [self.parent]
        return self.commit


class FakeBaseRepository:
    full_name = "sample-owner/sample-repo"

    def __init__(self, pull) -> None:
        self.pull = pull

    def get_pull(self, number: int):
        assert number == 17
        return self.pull


class FakeClient:
    def __init__(self, base_repo) -> None:
        self.base_repo = base_repo

    def get_repo(self, full_name: str):
        assert full_name == "sample-owner/sample-repo"
        return self.base_repo


def make_service(*, head_sha: str = "reviewed-head-sha", state: str = "open"):
    head_repo = FakeHeadRepository(head_sha)
    pull = SimpleNamespace(
        state=state,
        head=SimpleNamespace(
            sha="reviewed-head-sha",
            ref="feature/fix-calculation",
            repo=head_repo,
        ),
    )
    client = FakeClient(FakeBaseRepository(pull))
    return GitHubService("test-token", github_client=client), head_repo


def _commit(service: GitHubService):
    return service.commit_refactored_files(
        repository_full_name="sample-owner/sample-repo",
        pr_number=17,
        expected_head_sha="reviewed-head-sha",
        expected_head_branch="feature/fix-calculation",
        refactored_code={
            "src/calc.py": "def add(a, b):\n    return a + b\n",
            "src/helpers.py": "def identity(value):\n    return value\n",
        },
        commit_message="chore: apply approved refactoring for PR #17",
    )


def test_commit_writes_all_refactored_files_in_one_commit() -> None:
    service, head_repo = make_service()

    result = _commit(service)

    assert result["commit_sha"] == "new-commit-sha"
    assert result["commit_branch"] == "feature/fix-calculation"
    assert result["commit_repository_full_name"] == "sample-owner/sample-repo"
    assert result["commit_url"].endswith("new-commit-sha")
    assert len(head_repo.tree_elements) == 2
    assert head_repo.ref.updated_to == "new-commit-sha"


def test_commit_rejects_closed_pull_request() -> None:
    head_repo = FakeHeadRepository()
    pull = SimpleNamespace(
        state="closed",
        head=SimpleNamespace(sha="reviewed-head-sha", ref="feature/fix-calculation", repo=head_repo),
    )
    service = GitHubService("test-token", github_client=FakeClient(FakeBaseRepository(pull)))

    with pytest.raises(GitHubIntegrationError, match="not open"):
        _commit(service)


def test_commit_rejects_pull_request_head_changed_since_review() -> None:
    head_repo = FakeHeadRepository()
    pull = SimpleNamespace(
        state="open",
        head=SimpleNamespace(sha="newer-head-sha", ref="feature/fix-calculation", repo=head_repo),
    )
    service = GitHubService("test-token", github_client=FakeClient(FakeBaseRepository(pull)))

    with pytest.raises(GitHubWriteConflict, match="head changed"):
        _commit(service)


def test_commit_rejects_branch_reference_changed_since_review() -> None:
    service, head_repo = make_service(head_sha="newer-head-sha")

    with pytest.raises(GitHubWriteConflict, match="source branch moved"):
        _commit(service)
    assert head_repo.ref.updated_to is None


def test_commit_rejects_path_traversal() -> None:
    service, _ = make_service()
    with pytest.raises(ValueError, match="Unsafe refactored filename"):
        service.commit_refactored_files(
            repository_full_name="sample-owner/sample-repo",
            pr_number=17,
            expected_head_sha="reviewed-head-sha",
            expected_head_branch="feature/fix-calculation",
            refactored_code={"../outside.py": "print('unsafe')"},
            commit_message="test unsafe path",
        )


def test_commit_rejects_non_python_file() -> None:
    service, _ = make_service()
    with pytest.raises(ValueError, match="Only Python files"):
        service.commit_refactored_files(
            repository_full_name="sample-owner/sample-repo",
            pr_number=17,
            expected_head_sha="reviewed-head-sha",
            expected_head_branch="feature/fix-calculation",
            refactored_code={"README.md": "unsafe"},
            commit_message="test non-python file",
        )
