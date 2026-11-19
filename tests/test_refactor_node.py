"""Tests for the LangGraph LLM refactoring node."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.graph.nodes import propose_refactor_node
from app.graph.state import create_initial_state


class FakeRefactorService:
    def __init__(self, *, api_key: str, model_name: str):
        assert api_key == "test-openai-key"
        assert model_name == "test-model"

    def generate_refactor(self, **kwargs):
        assert kwargs["code_contents"] == {"src/calc.py": "def add(a,b):return a+b"}
        assert kwargs["reviewer_feedback"] == "Use spaces around operators"
        assert kwargs["review_attempt"] == 1
        return {
            "refactored_code": {"src/calc.py": "def add(a, b):\n    return a + b\n"},
            "refactor_summary": "Applied the requested formatting changes.",
        }


def _state():
    state = create_initial_state(
        pr_url="https://github.com/example/demo/pull/9",
        repository_full_name="example/demo",
        pr_number=9,
    )
    state["code_contents"] = {"src/calc.py": "def add(a,b):return a+b"}
    state["lint_errors"] = [{"file": "src/calc.py", "tool": "black", "message": "formatting"}]
    state["reviewer_feedback"] = "Use spaces around operators"
    state["review_attempt"] = 1
    state["is_approved"] = False
    return state


def test_refactor_node_uses_feedback_and_requires_fresh_approval(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.get_settings",
        lambda: SimpleNamespace(openai_api_key="test-openai-key", openai_model="test-model"),
    )
    monkeypatch.setattr("app.graph.nodes.RefactorService", FakeRefactorService)

    result = propose_refactor_node(_state())

    assert result["refactored_code"]["src/calc.py"] == "def add(a, b):\n    return a + b\n"
    assert result["refactor_summary"] == "Applied the requested formatting changes."
    assert result["review_attempt"] == 2
    assert result["is_approved"] is None
    assert result["review_status"] == "awaiting_approval"
    assert result["history"][0]["event"] == "refactor_proposed"


def test_refactor_node_requires_openai_api_key(monkeypatch):
    monkeypatch.setattr(
        "app.graph.nodes.get_settings",
        lambda: SimpleNamespace(openai_api_key="", openai_model="test-model"),
    )
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        propose_refactor_node(_state())


def test_refactor_node_rejects_empty_code(monkeypatch):
    state = _state()
    state["code_contents"] = {}
    with pytest.raises(ValueError, match="No Python source files"):
        propose_refactor_node(state)
