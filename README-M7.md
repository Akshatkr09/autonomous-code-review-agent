# M7 — GitHub write-back milestone

This milestone completes the approval-to-commit path.

## Files in this bundle

- `app/services/github_service.py` — adds safe, single-commit Git Data API write-back.
- `app/graph/nodes.py` — implements the approval-guarded `apply_changes_node`.
- `app/graph/state.py` — records commit SHA, URL, branch, and target repository.
- `app/graph/runtime.py` — resumes the graph after approval and verifies completion.
- `app/api/routes.py` — returns commit metadata and accurate completion messaging.
- `tests/test_github_writeback.py` — tests branch SHA validation and single-commit behavior with a fake GitHub client.
- `tests/test_apply_changes_node.py` — tests approval and exact-file-set guards.
- `tests/test_api.py` — updated to assert that an approved graph reaches `completed`.
- `docs/github-writeback-m7.md` — safeguards, permissions, and validation instructions.

## Install

Extract the archive into the repository root, preserving the folder structure. Allow the listed existing files to be replaced.

## Required GitHub permissions

For a PR from the assessment repository, the fine-grained PAT needs:

- Contents: Read and write
- Pull requests: Read-only
- Metadata: Read-only (automatically included)

For PRs opened from forks, the token also needs write access to the fork's source repository. The agent intentionally does not fall back to writing to the base repository.

## Test

```powershell
pytest -v tests/test_github_writeback.py tests/test_apply_changes_node.py tests/test_api.py tests/test_checkpointer.py
pytest -v
```

These tests use fake GitHub clients and do not make real commits. A real write-back smoke test must be done on a disposable Pull Request branch after the full suite passes.
