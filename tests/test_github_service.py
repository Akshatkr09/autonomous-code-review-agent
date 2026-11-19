"""Unit tests for read-only GitHub Pull Request ingestion."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services.github_service import GitHubIntegrationError, GitHubService


class FakeContent:
    def __init__(self, content: str, *, size: int | None = None) -> None:
        self.decoded_content = content.encode("utf-8")
        self.size = len(self.decoded_content) if size is None else size


class FakeChangedFile:
    def __init__(
        self,
        filename: str,
        *,
        status: str = "modified",
        additions: int = 1,
        deletions: int = 0,
        changes: int = 1,
        patch: str = "@@ -1 +1 @@",
    ) -> None:
        self.filename = filename
        self.status = status
        self.additions = additions
        self.deletions = deletions
        self.changes = changes
        self.patch = patch


class FakeRepository:
    def __init__(self, full_name: str, files: dict[str, FakeContent] | None = None) -> None:
        self.full_name = full_name
        self.files = files or {}
        self.content_requests: list[tuple[str, str]] = []
        self.pull_request: Any = None

    def get_pull(self, number: int) -> Any:
        assert number == self.pull_request.number
        return self.pull_request

    def get_contents(self, path: str, *, ref: str) -> FakeContent:
        self.content_requests.append((path, ref))
        return self.files[path]


class FakeGitHubClient:
    def __init__(self, repository: FakeRepository) -> None:
        self.repository = repository

    def get_repo(self, full_name: str) -> FakeRepository:
        assert full_name == self.repository.full_name
        return self.repository


def make_fake_client(
    *,
    changed_files: list[FakeChangedFile] | None = None,
    python_files: dict[str, FakeContent] | None = None,
    state: str = "open",
) -> tuple[FakeGitHubClient, FakeRepository]:
    base_repo = FakeRepository("sample-owner/sample-repo")
    head_repo = FakeRepository("sample-owner/sample-repo", python_files)
    pull = SimpleNamespace(
        number=12,
        state=state,
        html_url="https://github.com/sample-owner/sample-repo/pull/12",
        title="Improve calculations",
        body="Refactor calculation helpers.",
        base=SimpleNamespace(ref="main", sha="base-sha-123"),
        head=SimpleNamespace(ref="feature/calculations", sha="head-sha-456", repo=head_repo),
        user=SimpleNamespace(login="sample-author"),
        get_files=lambda: iter(changed_files or []),
    )
    base_repo.pull_request = pull
    return FakeGitHubClient(base_repo), head_repo


def test_fetch_pull_request_returns_metadata_and_python_contents() -> None:
    changed = [
        FakeChangedFile("src/calc.py"),
        FakeChangedFile("README.md"),
        FakeChangedFile("src/old.py", status="removed"),
    ]
    client, head_repo = make_fake_client(
        changed_files=changed,
        python_files={"src/calc.py": FakeContent("def add(a, b):\n    return a + b\n")},
    )

    service = GitHubService("fake-token", github_client=client)
    result = service.fetch_pull_request("sample-owner/sample-repo", 12)

    assert result["pr_number"] == 12
    assert result["pr_title"] == "Improve calculations"
    assert result["base_branch"] == "main"
    assert result["head_branch"] == "feature/calculations"
    assert result["head_sha"] == "head-sha-456"
    assert result["author"] == "sample-author"
    assert result["code_contents"] == {
        "src/calc.py": "def add(a, b):\n    return a + b\n"
    }
    assert [item["filename"] for item in result["file_changes"]] == [
        "src/calc.py",
        "README.md",
        "src/old.py",
    ]
    assert head_repo.content_requests == [("src/calc.py", "head-sha-456")]


def test_fetch_rejects_closed_pull_request() -> None:
    client, _ = make_fake_client(state="closed")
    service = GitHubService("fake-token", github_client=client)

    with pytest.raises(GitHubIntegrationError, match="not open"):
        service.fetch_pull_request("sample-owner/sample-repo", 12)


def test_fetch_rejects_oversized_python_file() -> None:
    changed = [FakeChangedFile("large.py")]
    client, _ = make_fake_client(
        changed_files=changed,
        python_files={"large.py": FakeContent("x = 1", size=500)},
    )
    service = GitHubService("fake-token", github_client=client, max_file_bytes=100)

    with pytest.raises(GitHubIntegrationError, match="exceeds"):
        service.fetch_pull_request("sample-owner/sample-repo", 12)


def test_fetch_rejects_pr_with_no_supported_python_files() -> None:
    changed = [FakeChangedFile("README.md")]
    client, _ = make_fake_client(changed_files=changed)
    service = GitHubService("fake-token", github_client=client)

    with pytest.raises(GitHubIntegrationError, match="no supported"):
        service.fetch_pull_request("sample-owner/sample-repo", 12)


def test_service_requires_token_when_no_client_is_injected() -> None:
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        GitHubService("")


def test_repository_name_and_pr_number_are_validated() -> None:
    client, _ = make_fake_client()
    service = GitHubService("fake-token", github_client=client)

    with pytest.raises(ValueError, match="owner/repository"):
        service.fetch_pull_request("not-a-full-name", 12)
    with pytest.raises(ValueError, match="positive integer"):
        service.fetch_pull_request("sample-owner/sample-repo", 0)


def test_fetch_enforces_maximum_changed_file_count() -> None:
    changed = [FakeChangedFile(f"file_{index}.md") for index in range(3)]
    client, _ = make_fake_client(changed_files=changed)
    service = GitHubService("fake-token", github_client=client, max_files=2)

    with pytest.raises(GitHubIntegrationError, match="configured limit"):
        service.fetch_pull_request("sample-owner/sample-repo", 12)
