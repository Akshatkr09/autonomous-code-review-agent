# Final Assessment Validation Guide

This guide maps the project to the three manual verification scenarios in the assessment brief. Run the application locally; public deployment is not required.

## Before testing

1. Use a disposable GitHub repository or a disposable Pull Request branch where the configured token has permission to write contents.
2. Put `GITHUB_TOKEN`, `OPENAI_API_KEY`, and (optionally for local simulation) `GITHUB_WEBHOOK_SECRET` in the local `.env` file. Never commit `.env`.
3. Start Docker Desktop and build the linter image:

   ```powershell
   docker build -t code-review-linter:latest -f sandbox/Dockerfile sandbox
   ```

4. Install project dependencies and start the app from the repository root:

   ```powershell
   pip install -r requirements.txt
   uvicorn main:app --reload
   ```

5. Open `http://127.0.0.1:8000/docs` to inspect the API. The machine-readable OpenAPI document is available at `http://127.0.0.1:8000/openapi.json`.

## Prepare a real test Pull Request

Create a feature branch in a repository where the PAT has Contents: read/write permission. Add or modify at least one `.py` file, push the branch, and open a PR against the repository's default branch. Do not use a production branch or a PR whose changes you do not want the agent to update.

The agent writes approved refactored files to the PR's head branch. It does not merge the PR.

## Test case 1 — Webhook PR ingestion, linting, and HITL pause

In a second PowerShell window, set the real repository owner/name and PR number:

```powershell
$ownerRepo = "YOUR_OWNER/YOUR_TEST_REPOSITORY"
$prNumber = 123
$payload = @{
  action = "opened"
  repository = @{
    full_name = $ownerRepo
    html_url = "https://github.com/$ownerRepo"
  }
  pull_request = @{
    number = $prNumber
    html_url = "https://github.com/$ownerRepo/pull/$prNumber"
    base = @{ ref = "main" }
    head = @{ ref = "YOUR_TEST_BRANCH" }
  }
} | ConvertTo-Json -Depth 8

$started = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/webhooks/github" `
  -ContentType "application/json" -Body $payload

$started | ConvertTo-Json -Depth 10
$threadId = $started.thread_id
```

Expected: HTTP 202, `accepted: true`, lint results, a refactoring proposal, `waiting_for_reviewer: true`, and `next_nodes` containing `apply_changes_node`. Execution is paused before repository writes.

## Test case 2 — Feedback input and refactoring proposal re-route

Submit a rejection against the returned thread ID:

```powershell
$rejection = @{
  approved = $false
  feedback = "Use list comprehensions instead of loops"
} | ConvertTo-Json

$revised = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/reviews/$threadId/approve" `
  -ContentType "application/json" -Body $rejection

$revised | ConvertTo-Json -Depth 10
```

Expected: the feedback is stored, the LLM proposal is regenerated, `review_attempt` increases, and the graph pauses again before `apply_changes_node` for a fresh decision.

## Test case 3 — Approval and Git commit write-back

Review the revised source and then approve it:

```powershell
$approval = @{ approved = $true } | ConvertTo-Json

$completed = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/reviews/$threadId/approve" `
  -ContentType "application/json" -Body $approval

$completed | ConvertTo-Json -Depth 10
```

Expected: `status: completed`, `approval_recorded: true`, a non-empty `commit_sha`, and the PR head branch/repository in the response. Confirm the new commit appears on the disposable PR branch in GitHub. The agent does not merge the PR.

## Inspect a review later

```powershell
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8000/api/reviews/$threadId" |
  ConvertTo-Json -Depth 10
```

## Automated verification

Run the full suite:

```powershell
pytest -v
```

The automated suite uses fakes for external GitHub/OpenAI operations. These tests verify routing, guards, and service behavior without writing to a real repository or consuming OpenAI API credits. The manual test above verifies the live integration against a disposable PR.

## Safety notes

- A successful approval writes to the PR source branch, not the base branch, and does not merge the PR.
- The write-back operation checks the PR head SHA and branch against the values captured during ingestion. If the branch moved, re-run the review rather than applying a stale proposal.
- For fork-based PRs, the token needs write access to the fork/source repository. The workflow fails closed if it cannot update that source branch.
- An empty `GITHUB_WEBHOOK_SECRET` permits local mock webhook calls. Configure a webhook secret and supply a valid `X-Hub-Signature-256` for real GitHub webhook delivery.
- The assessment app is intended for local demonstration. Before exposing it to a network, add reviewer authentication/authorization, request-size limits, operational logging/monitoring, and stricter deployment secret management.
