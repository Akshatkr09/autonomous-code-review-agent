"""HTTP endpoints for PR ingestion and human-in-the-loop review decisions."""

from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.schemas import GitHubWebhookPayload, ReviewDecisionRequest
from app.config.settings import get_settings
from app.graph.runtime import ReviewRuntime

router = APIRouter(prefix="/api", tags=["code-reviews"])
SUPPORTED_PULL_REQUEST_ACTIONS = {"opened", "reopened", "synchronize", "ready_for_review"}


def _verify_webhook_signature(secret: str, body: bytes, signature: str | None) -> None:
    """Verify GitHub's X-Hub-Signature-256 header when a secret is configured."""
    if not secret:
        return  # Local assessment simulation; configure a secret for real webhooks.
    if not signature or not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing or invalid GitHub webhook signature")

    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="GitHub webhook signature verification failed")


def _repository_full_name(payload: GitHubWebhookPayload) -> str:
    full_name = (payload.repository.full_name or "").strip()
    if full_name:
        return full_name

    html_url = payload.repository.html_url or ""
    parsed = urlparse(html_url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if parsed.scheme == "https" and parsed.netloc.lower() == "github.com" and len(parts) == 2:
        return f"{parts[0]}/{parts[1].removesuffix('.git')}"
    raise HTTPException(
        status_code=422,
        detail="Webhook must include repository.full_name or a valid GitHub repository URL",
    )


def _snapshot_response(thread_id: str, snapshot) -> dict:
    values = snapshot.values or {}
    return {
        "thread_id": thread_id,
        "status": values.get("review_status", "unknown"),
        "next_nodes": list(snapshot.next),
        "waiting_for_reviewer": (
            tuple(snapshot.next) == ("apply_changes_node",)
            and values.get("is_approved") is None
        ),
        "approval_recorded": values.get("is_approved"),
        "pr_url": values.get("pr_url"),
        "pr_title": values.get("pr_title", ""),
        "repository_full_name": values.get("repository_full_name"),
        "pr_number": values.get("pr_number"),
        "lint_results": values.get("lint_results", []),
        "lint_errors": values.get("lint_errors", []),
        "refactor_summary": values.get("refactor_summary", ""),
        "refactored_code": values.get("refactored_code", {}),
        "review_attempt": values.get("review_attempt", 0),
        "commit_sha": values.get("commit_sha"),
        "commit_url": values.get("commit_url"),
        "commit_branch": values.get("commit_branch"),
        "commit_repository_full_name": values.get("commit_repository_full_name"),
        "error_message": values.get("error_message"),
    }


def _runtime(request: Request) -> ReviewRuntime:
    runtime = getattr(request.app.state, "review_runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Review runtime is not available")
    return runtime


@router.post("/webhooks/github", status_code=status.HTTP_202_ACCEPTED)
async def receive_github_webhook(request: Request) -> dict:
    """Accept a PR event, start a LangGraph thread, and pause for human review."""
    body = await request.body()
    settings = get_settings()
    _verify_webhook_signature(
        settings.github_webhook_secret,
        body,
        request.headers.get("X-Hub-Signature-256"),
    )

    try:
        raw_payload = json.loads(body)
        payload = GitHubWebhookPayload.model_validate(raw_payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid GitHub Pull Request webhook payload") from exc

    if payload.action not in SUPPORTED_PULL_REQUEST_ACTIONS:
        return {
            "accepted": True,
            "ignored": True,
            "reason": f"Pull Request action '{payload.action}' is not processed",
        }

    repository_full_name = _repository_full_name(payload)
    pr_number = payload.pull_request.number
    pr_url = payload.pull_request.html_url or (
        f"https://github.com/{repository_full_name}/pull/{pr_number}"
    )
    thread_id = uuid4().hex

    try:
        snapshot = await run_in_threadpool(
            _runtime(request).start_review,
            thread_id=thread_id,
            pr_url=pr_url,
            repository_full_name=repository_full_name,
            pr_number=pr_number,
            base_branch=payload.pull_request.base.ref or "main",
            head_branch=payload.pull_request.head.ref or "",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="The review workflow could not process this Pull Request. Check server logs and integration configuration.",
        ) from exc

    response = _snapshot_response(thread_id, snapshot)
    response["accepted"] = True
    response["ignored"] = False
    return response


@router.post("/reviews/{thread_id}/approve")
def submit_review_decision(thread_id: str, decision: ReviewDecisionRequest, request: Request) -> dict:
    """Record a reviewer decision and resume the graph to its next checkpoint."""
    runtime = _runtime(request)
    try:
        snapshot = runtime.submit_decision(
            thread_id=thread_id,
            approved=decision.approved,
            feedback=decision.feedback,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        # Avoid exposing GitHub API details, code contents, or credentials.
        raise HTTPException(
            status_code=502,
            detail="The review decision was recorded, but workflow resumption failed. Check server logs and review status.",
        ) from exc

    response = _snapshot_response(thread_id, snapshot)
    if decision.approved:
        response["message"] = "Approved refactored files were committed to the Pull Request branch."
    else:
        response["message"] = "Feedback saved and a revised proposal has been generated."
    return response


@router.get("/reviews/{thread_id}")
def get_review_status(thread_id: str, request: Request) -> dict:
    """Retrieve the latest persisted review state for a thread."""
    try:
        snapshot = _runtime(request).get_review(thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Review thread not found")
    return _snapshot_response(thread_id, snapshot)
