# M6 — Persistent Checkpoints and Human-in-the-Loop API

## What this milestone adds

- A long-lived `SqliteSaver` checkpointer backed by `data/review_checkpoints.sqlite`.
- A `ReviewRuntime` that owns the SQLite connection and compiled graph for the FastAPI application lifespan.
- `POST /api/webhooks/github` to validate an incoming PR event and start a review thread.
- `POST /api/reviews/{thread_id}/approve` to persist approval or rejection against the same thread.
- Rejection feedback resumes the graph through the conditional edge to `propose_refactor_node`; the revised proposal pauses again before `apply_changes_node`.
- `GET /api/reviews/{thread_id}` to inspect a persisted review summary.
- Optional GitHub webhook HMAC verification using `GITHUB_WEBHOOK_SECRET`.

## Run locally

```powershell
uvicorn app.main:app --reload
```

FastAPI Swagger UI: `http://127.0.0.1:8000/docs`

## Simulate a pull request webhook

```powershell
$payload = @{
  action = "opened"
  repository = @{ full_name = "OWNER/REPOSITORY" }
  pull_request = @{
    number = 1
    html_url = "https://github.com/OWNER/REPOSITORY/pull/1"
    base = @{ ref = "main" }
    head = @{ ref = "feature/example" }
  }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/webhooks/github" -ContentType "application/json" -Body $payload
```

The real webhook path uses the actual GitHub API and OpenAI model. For local integration tests, graph nodes are replaced with deterministic fakes, so tests do not spend API credits or modify repositories.

## Submit reviewer feedback

Use the `thread_id` returned by the webhook:

```powershell
$decision = @{
  approved = $false
  feedback = "Use list comprehensions instead of loops"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/reviews/THREAD_ID/approve" -ContentType "application/json" -Body $decision
```

The endpoint updates the saved checkpoint and resumes the graph. The revised proposal pauses again at the same write gate.

## Approve a proposal

```powershell
$decision = @{ approved = $true } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/reviews/THREAD_ID/approve" -ContentType "application/json" -Body $decision
```

In M6, approval is durably recorded and the graph remains positioned at `apply_changes_node`. The actual GitHub commit operation is intentionally completed in M7; this milestone does not claim that a repository write has happened.

## Checkpoint storage

The synchronous `SqliteSaver` is appropriate for this local, single-process assessment server. The SQLite connection is opened once when FastAPI starts and closed on shutdown. A review thread uses a stable `thread_id`, allowing the saved snapshot and pending node to be retrieved after the app restarts.

For multi-worker production deployment, use a production-grade shared checkpointer (for example, PostgreSQL) rather than sharing a local SQLite database across processes.

## Security

- Configure `GITHUB_WEBHOOK_SECRET` to verify `X-Hub-Signature-256` on real webhooks. When no secret is configured, signature validation is intentionally skipped for local mock requests.
- Keep `.env` out of Git.
- The approval endpoint accepts only validated JSON fields.
- Reviewer decisions are accepted only while the thread is paused at the approval gate.
- An approval is persisted but not treated as a completed commit until M7 executes the GitHub write node.
