"""Validated request models for GitHub webhooks and human review decisions."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GitHubRepositoryRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    full_name: str | None = None
    html_url: str | None = None


class GitHubBranchRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ref: str = ""
    sha: str | None = None


class GitHubPullRequestRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    number: int = Field(gt=0)
    html_url: str | None = None
    base: GitHubBranchRef = Field(default_factory=GitHubBranchRef)
    head: GitHubBranchRef = Field(default_factory=GitHubBranchRef)


class GitHubWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: str = "opened"
    repository: GitHubRepositoryRef
    pull_request: GitHubPullRequestRef


class ReviewDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    feedback: str | None = Field(default=None, max_length=4000)
