"""GitHub integration for Pull Request ingestion and approved write-back.

Read operations fetch PR metadata and Python source at the immutable head SHA.
Write operations create one Git-data commit containing all approved refactored
files and update the PR's head branch only after checking that it still points
to the SHA reviewed by the agent.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Mapping

from github import Auth, Github, GithubException, InputGitTreeElement


class GitHubIntegrationError(RuntimeError):
    """Raised when GitHub data cannot be retrieved or written safely."""


class GitHubWriteConflict(GitHubIntegrationError):
    """Raised when a PR branch changed since the agent reviewed it."""


class GitHubService:
    """Fetch Pull Requests and commit explicitly approved refactoring proposals.

    Args:
        token: Fine-grained GitHub PAT. It is never included in errors/logs.
        github_client: Optional injected PyGithub-compatible client for tests.
        max_files: Maximum number of changed files accepted for one review.
        max_file_bytes: Maximum size of an individual Python file to ingest.

    Only ``.py`` and ``.pyi`` source files are placed in ``code_contents``.
    Metadata for every changed file is retained in ``file_changes``.
    """

    PYTHON_SUFFIXES = {".py", ".pyi"}
    MAX_COMMIT_FILES = 30
    MAX_COMMIT_TOTAL_BYTES = 1_000_000

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

    @staticmethod
    def _validate_python_path(filename: str) -> None:
        if (
            not isinstance(filename, str)
            or not filename
            or len(filename) > 180
            or not re.fullmatch(r"[A-Za-z0-9_./-]+", filename)
        ):
            raise ValueError("Refactored filename is invalid")
        raw_parts = filename.split("/")
        path = PurePosixPath(filename)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in raw_parts):
            raise ValueError(f"Unsafe refactored filename: '{filename}'")
        if path.suffix.lower() not in {".py", ".pyi"}:
            raise ValueError(f"Only Python files can be committed: '{filename}'")

    def fetch_pull_request(self, repository_full_name: str, pr_number: int) -> dict[str, Any]:
        """Fetch PR metadata and changed Python files at the immutable head SHA."""
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
                file_status = changed_file.status
                change_metadata: dict[str, Any] = {
                    "filename": filename,
                    "status": file_status,
                    "additions": changed_file.additions,
                    "deletions": changed_file.deletions,
                    "changes": changed_file.changes,
                }
                patch = getattr(changed_file, "patch", None)
                if patch is not None:
                    change_metadata["patch"] = patch
                file_changes.append(change_metadata)

                suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                if suffix not in self.PYTHON_SUFFIXES or file_status == "removed":
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
                message = "GitHub denied this request. Check token permissions and API rate limits."
            else:
                message = f"GitHub API request failed (HTTP status: {status})."
            raise GitHubIntegrationError(message) from exc

    def commit_refactored_files(
        self,
        *,
        repository_full_name: str,
        pr_number: int,
        expected_head_sha: str,
        expected_head_branch: str,
        refactored_code: Mapping[str, str],
        commit_message: str,
    ) -> dict[str, str]:
        """Commit all approved Python files to the PR head branch in one commit.

        The operation fails closed unless the PR is still open and its head
        branch still points to the SHA that the agent originally reviewed.
        The GitHub reference update is non-force; if another commit wins a race
        after the final SHA check, GitHub rejects a non-fast-forward update.
        """
        self._validate_repository_name(repository_full_name)
        if pr_number < 1:
            raise ValueError("pr_number must be a positive integer")
        if not expected_head_sha or not expected_head_branch:
            raise ValueError("The reviewed PR head SHA and branch are required for write-back")
        if not commit_message.strip() or len(commit_message) > 200:
            raise ValueError("commit_message must contain 1 to 200 characters")
        if not refactored_code:
            raise ValueError("refactored_code must contain at least one file")
        if len(refactored_code) > self.MAX_COMMIT_FILES:
            raise ValueError(f"A commit may contain at most {self.MAX_COMMIT_FILES} files")

        total_bytes = 0
        normalized: dict[str, str] = {}
        for filename, source in refactored_code.items():
            self._validate_python_path(filename)
            if not isinstance(source, str):
                raise ValueError(f"Refactored source for '{filename}' must be text")
            source_bytes = len(source.encode("utf-8"))
            if source_bytes > self._max_file_bytes:
                raise ValueError(f"Refactored file '{filename}' exceeds the per-file size limit")
            total_bytes += source_bytes
            normalized[filename] = source
        if total_bytes > self.MAX_COMMIT_TOTAL_BYTES:
            raise ValueError("Combined refactored source exceeds the commit size limit")

        try:
            base_repo = self._client.get_repo(repository_full_name)
            pull = base_repo.get_pull(pr_number)
            if pull.state != "open":
                raise GitHubIntegrationError(
                    f"Refusing write-back: Pull Request #{pr_number} is not open."
                )
            if pull.head.sha != expected_head_sha:
                raise GitHubWriteConflict(
                    "The Pull Request head changed after review. Re-run the review before committing."
                )
            if pull.head.ref != expected_head_branch:
                raise GitHubWriteConflict(
                    "The Pull Request head branch no longer matches the reviewed branch."
                )

            head_repo = pull.head.repo
            if head_repo is None:
                raise GitHubIntegrationError(
                    "The Pull Request source repository is unavailable; its branch cannot be updated."
                )

            branch_ref = head_repo.get_git_ref(f"heads/{expected_head_branch}")
            if branch_ref.object.sha != expected_head_sha:
                raise GitHubWriteConflict(
                    "The source branch moved after review. Re-run the review before committing."
                )

            parent_commit = head_repo.get_git_commit(expected_head_sha)
            tree_elements = [
                InputGitTreeElement(
                    path=filename,
                    mode="100644",
                    type="blob",
                    content=source,
                )
                for filename, source in normalized.items()
            ]
            new_tree = head_repo.create_git_tree(tree_elements, parent_commit.tree)
            new_commit = head_repo.create_git_commit(
                commit_message,
                new_tree,
                [parent_commit],
            )

            # Re-check immediately before updating the ref. force=False also
            # prevents replacing a branch with a non-fast-forward commit.
            latest_ref = head_repo.get_git_ref(f"heads/{expected_head_branch}")
            if latest_ref.object.sha != expected_head_sha:
                raise GitHubWriteConflict(
                    "The source branch moved while the commit was being prepared. No branch update was made."
                )
            latest_ref.edit(new_commit.sha, force=False)

            return {
                "commit_sha": new_commit.sha,
                "commit_url": getattr(new_commit, "html_url", "") or "",
                "commit_branch": expected_head_branch,
                "commit_repository_full_name": head_repo.full_name,
            }

        except GithubException as exc:
            status = getattr(exc, "status", "unknown")
            if status in {409, 422}:
                raise GitHubWriteConflict(
                    "GitHub rejected the branch update because the branch changed or a repository rule blocked it."
                ) from exc
            if status == 401:
                message = "GitHub authentication failed during write-back. Check GITHUB_TOKEN."
            elif status == 403:
                message = (
                    "GitHub denied the commit. The token needs Contents: read and write access "
                    "to the PR source repository."
                )
            elif status == 404:
                message = "GitHub could not find the PR source repository or branch for write-back."
            else:
                message = f"GitHub write-back failed (HTTP status: {status})."
            raise GitHubIntegrationError(message) from exc
