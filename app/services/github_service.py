"""Read-only GitHub integration for Pull Request ingestion.

This service deliberately performs no repository writes. It retrieves PR
metadata, changed-file metadata, and the current Python source for the PR head
commit. GitHub write operations belong to the later approval/write-back stage.
"""

from __future__ import annotations

import re
from typing import Any

from github import Auth, Github, GithubException


class GitHubIntegrationError(RuntimeError):
    """Raised when GitHub data cannot be retrieved safely."""


class GitHubService:
    """Fetch Pull Request metadata and Python source using PyGithub.

    Args:
        token: GitHub fine-grained PAT. It is never included in errors/logs.
        github_client: Optional injected PyGithub-compatible client for tests.
        max_files: Maximum number of changed files accepted for one review.
        max_file_bytes: Maximum size of an individual Python file to ingest.

    Only ``.py`` and ``.pyi`` source files are placed in ``code_contents``.
    Metadata for every changed file is retained in ``file_changes`` so later
    nodes can explain which files were ignored by the Python-only linter.
    """

    PYTHON_SUFFIXES = {".py", ".pyi"}

    def __init__(
        self,
        token: str,
        *,
        github_client: Any | None = None,
        max_files: int = 30,
        max_file_bytes: int = 256_000,
    ) -> None:
        if github_client is None and not token.strip():
            raise ValueError("GITHUB_TOKEN is required for GitHub API access")
        if max_files < 1:
            raise ValueError("max_files must be at least 1")
        if max_file_bytes < 1:
            raise ValueError("max_file_bytes must be at least 1")

        self._owns_client = github_client is None
        self._client = github_client or Github(
            auth=Auth.Token(token),
            timeout=20,
            per_page=100,
        )
        self._max_files = max_files
        self._max_file_bytes = max_file_bytes

    def close(self) -> None:
        """Close the underlying HTTP session when this service owns it."""
        if self._owns_client:
            self._client.close()

    @staticmethod
    def _validate_repository_name(repository_full_name: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository_full_name):
            raise ValueError("repository_full_name must use the 'owner/repository' format")

    def fetch_pull_request(self, repository_full_name: str, pr_number: int) -> dict[str, Any]:
        """Fetch PR metadata and changed Python files at the immutable head SHA.

        The source repository is taken from ``pull.head.repo`` when available,
        which supports PRs opened from a fork. File contents are read at the
        PR's head commit SHA to avoid branch movement during ingestion.
        """
        self._validate_repository_name(repository_full_name)
        if pr_number < 1:
            raise ValueError("pr_number must be a positive integer")

        try:
            base_repo = self._client.get_repo(repository_full_name)
            pull = base_repo.get_pull(pr_number)

            if pull.state != "open":
                raise GitHubIntegrationError(
                    f"Pull Request #{pr_number} is not open (state: {pull.state})."
                )

            head_sha = pull.head.sha
            head_repo = pull.head.repo or base_repo
            file_changes: list[dict[str, Any]] = []
            code_contents: dict[str, str] = {}

            for changed_file in pull.get_files():
                if len(file_changes) >= self._max_files:
                    raise GitHubIntegrationError(
                        f"Pull Request exceeds the configured limit of {self._max_files} changed files."
                    )

                filename = changed_file.filename
                status = changed_file.status
                change_metadata: dict[str, Any] = {
                    "filename": filename,
                    "status": status,
                    "additions": changed_file.additions,
                    "deletions": changed_file.deletions,
                    "changes": changed_file.changes,
                }
                patch = getattr(changed_file, "patch", None)
                if patch is not None:
                    change_metadata["patch"] = patch
                file_changes.append(change_metadata)

                # The current linter in this assessment is Python-specific.
                # Keep other changed-file metadata, but do not send non-Python
                # or deleted files to the Python linter/refactoring node.
                suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                if suffix not in self.PYTHON_SUFFIXES or status == "removed":
                    continue

                content_file = head_repo.get_contents(filename, ref=head_sha)
                if isinstance(content_file, list):
                    raise GitHubIntegrationError(
                        f"GitHub returned a directory instead of a file for '{filename}'."
                    )

                file_size = getattr(content_file, "size", 0)
                if file_size > self._max_file_bytes:
                    raise GitHubIntegrationError(
                        f"Python file '{filename}' exceeds the {self._max_file_bytes}-byte ingestion limit."
                    )

                try:
                    source = content_file.decoded_content.decode("utf-8")
                except (AttributeError, UnicodeDecodeError) as exc:
                    raise GitHubIntegrationError(
                        f"Python file '{filename}' could not be decoded as UTF-8."
                    ) from exc

                code_contents[filename] = source

            if not code_contents:
                raise GitHubIntegrationError(
                    "The Pull Request contains no supported, non-deleted Python files (.py or .pyi)."
                )

            head_repository = pull.head.repo
            return {
                "pr_url": pull.html_url,
                "pr_title": pull.title or "",
                "pr_body": pull.body or "",
                "repository_full_name": base_repo.full_name,
                "pr_number": pull.number,
                "base_branch": pull.base.ref,
                "head_branch": pull.head.ref,
                "base_sha": pull.base.sha,
                "head_sha": head_sha,
                "head_repo_full_name": (
                    head_repository.full_name if head_repository is not None else base_repo.full_name
                ),
                "author": pull.user.login if pull.user else "unknown",
                "file_changes": file_changes,
                "code_contents": code_contents,
            }

        except GithubException as exc:
            status = getattr(exc, "status", "unknown")
            if status == 404:
                message = (
                    "GitHub could not find the repository, Pull Request, or PR-head file. "
                    "Check the repository name, PR number, and token access."
                )
            elif status == 401:
                message = "GitHub authentication failed. Check GITHUB_TOKEN."
            elif status == 403:
                message = (
                    "GitHub denied this request. Check token permissions and API rate limits."
                )
            else:
                message = f"GitHub API request failed (HTTP status: {status})."
            raise GitHubIntegrationError(message) from exc
