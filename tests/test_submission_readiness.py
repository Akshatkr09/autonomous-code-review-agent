"""Submission checks for the documented application entry point and OpenAPI."""

from __future__ import annotations

from fastapi import FastAPI

from app.main import app as application


def test_assessment_uvicorn_entrypoint_exports_fastapi_app() -> None:
    # The assessment's prescribed command is `uvicorn main:app --reload`.
    from main import app as entrypoint_app

    assert isinstance(entrypoint_app, FastAPI)
    assert entrypoint_app is application


def test_openapi_contains_required_assessment_endpoints() -> None:
    specification = application.openapi()
    paths = specification["paths"]

    assert "/api/webhooks/github" in paths
    assert "post" in paths["/api/webhooks/github"]
    assert "/api/reviews/{thread_id}/approve" in paths
    assert "post" in paths["/api/reviews/{thread_id}/approve"]
    assert "/api/reviews/{thread_id}" in paths
    assert "get" in paths["/api/reviews/{thread_id}"]


def test_openapi_has_title_and_version() -> None:
    specification = application.openapi()

    assert specification["info"]["title"] == "Autonomous Code Review & Refactoring Agent"
    assert specification["info"]["version"]
