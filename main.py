"""Uvicorn entry point required by the assessment brief.

Run from the repository root with:
    uvicorn main:app --reload
"""

from app.main import app

__all__ = ["app"]
