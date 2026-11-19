# M3 — GitHub Pull Request ingestion

## Scope

M3 implements **read-only** GitHub integration. It retrieves Pull Request metadata, changed-file metadata, and the Python source files at the PR head commit. It does not create branches, post comments, or write/commit code.

## Required token permissions

For the private or public assessment repository, use a fine-grained PAT scoped only to the test repository:

- Pull requests: Read-only
- Contents: Read-only for M3

The later approval/write-back milestone will require Contents: Read and write. Do not grant broader permissions than needed. Keep the token in `.env` as `GITHUB_TOKEN`; never commit `.env`.

## Ingestion behavior

- The service validates the `owner/repository` identifier and positive PR number.
- Only open PRs are accepted.
- Source content is retrieved at the immutable PR head commit SHA, not a moving branch name.
- For PRs from forks, the head repository is used when GitHub supplies it.
- Metadata is retained for every changed file.
- `.py` and `.pyi` files are loaded into `code_contents`; non-Python and deleted files remain in `file_changes` but are not sent to the Python linter.
- The default safety limits are 30 changed files and 256,000 bytes per Python file.
- GitHub API failures are converted to `GitHubIntegrationError` without exposing the PAT.

## Tests

Run the service and graph-node tests without making real GitHub API requests:

```powershell
pytest -v tests/test_github_service.py tests/test_github_node.py
```

The tests use fake PyGithub-compatible objects and verify metadata extraction, immutable SHA-based file retrieval, filtering, limits, validation, and mapping into LangGraph state.

## Manual smoke test

Once a test PR exists in the configured repository and `.env` contains a PAT with the permissions above, the GitHub service can be exercised by the FastAPI webhook once the API milestone is complete. No public deployment is required; local API requests are sufficient for the assessment's stated verification flow.
