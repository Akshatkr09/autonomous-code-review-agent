# M7 — Approved GitHub write-back

## Overview

M7 connects the existing human approval checkpoint to a real GitHub commit. The graph's `apply_changes_node` now writes the full refactored Python files to the Pull Request's **head branch**, not the base branch.

## Write-back safeguards

Before creating or updating a branch, the service:

1. Requires `is_approved is True` in the graph state.
2. Requires the proposal to contain exactly the same filenames that were fetched from the PR.
3. Accepts only safe relative `.py` and `.pyi` paths and limits file count and content size.
4. Confirms the Pull Request is still open.
5. Confirms the PR head SHA and branch still match the SHA and branch captured during review.
6. Confirms the source branch ref still points to that reviewed SHA.
7. Builds one Git tree and one commit containing all approved source files.
8. Re-reads the branch ref and updates it with `force=False`; a competing non-fast-forward update is rejected by GitHub.

A PR originating from a fork is written to the fork's head repository. The token must therefore have Contents: read and write permission on that source repository. If the source repository is unavailable or the token lacks write access, the workflow fails rather than silently writing to the base repository.

## Approval lifecycle

`POST /api/reviews/{thread_id}/approve` now resumes the checkpointed graph after an approval. The request returns `completed` only after `apply_changes_node` receives a successful GitHub commit result and the commit SHA is saved in the checkpoint.

A rejection still records the feedback, re-enters `propose_refactor_node`, resets the approval decision, and pauses for a new decision.

## API response fields

After a successful approval, the response includes:

- `status`: `completed`
- `approval_recorded`: `true`
- `commit_sha`
- `commit_url`
- `commit_branch`
- `commit_repository_full_name`

## Local validation

Run the complete test suite:

```powershell
pytest -v
```

The GitHub write-back unit tests use a fake PyGithub client, so they do not create real commits. Run the assessment's real write-back verification only against a disposable test Pull Request and a token with Contents: read and write permission on the PR head repository.

## Important operational note

The review API is intended for local assessment use. Before exposing it to a network, add reviewer authentication/authorization, enforce webhook secrets, configure request-size limits, and use an appropriately scoped GitHub App or fine-grained token. A webhook secret authenticates GitHub delivery; it does not authenticate human reviewers.
