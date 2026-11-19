"""Tests for LangGraph linter-node state updates."""

from __future__ import annotations

import json

from app.graph.nodes import lint_code_node
from app.graph.state import create_initial_state


class FakeLinterTool:
    def __init__(self, response: dict):
        self.response = response
        self.calls = []

    def invoke(self, payload: dict) -> str:
        self.calls.append(payload)
        return json.dumps(self.response)


def test_lint_node_maps_clean_lint_results_to_state(monkeypatch) -> None:
    fake_tool = FakeLinterTool(
        {
            "filename": "src/math_ops.py",
            "ok": True,
            "category": "lint_result",
            "flake8_exit_code": 0,
            "black_exit_code": 0,
            "output": "All checks passed.",
        }
    )
    monkeypatch.setattr("app.graph.nodes.run_linter_tool", fake_tool)

    state = create_initial_state(
        pr_url="https://github.com/example/demo/pull/4",
        repository_full_name="example/demo",
        pr_number=4,
    )
    state["code_contents"] = {"src/math_ops.py": "def add(a, b):\n    return a + b\n"}

    result = lint_code_node(state)

    assert result["lint_errors"] == []
    assert result["lint_results"][0]["ok"] is True
    assert result["review_status"] == "proposing"
    assert fake_tool.calls[0]["filename"] == "src/math_ops.py"
    assert result["history"][0]["event"] == "linting_completed"


def test_lint_node_collects_flake8_and_black_issues(monkeypatch) -> None:
    fake_tool = FakeLinterTool(
        {
            "filename": "bad.py",
            "ok": False,
            "category": "lint_result",
            "flake8_exit_code": 1,
            "black_exit_code": 1,
            "output": "formatting and lint issues",
        }
    )
    monkeypatch.setattr("app.graph.nodes.run_linter_tool", fake_tool)

    state = create_initial_state(
        pr_url="https://github.com/example/demo/pull/5",
        repository_full_name="example/demo",
        pr_number=5,
    )
    state["code_contents"] = {"bad.py": "x=1"}

    result = lint_code_node(state)

    assert len(result["lint_errors"]) == 2
    assert {item["tool"] for item in result["lint_errors"]} == {"flake8", "black"}


def test_lint_node_fails_closed_when_docker_tool_does_not_run(monkeypatch) -> None:
    fake_tool = FakeLinterTool(
        {
            "filename": "bad.py",
            "ok": False,
            "category": "docker_unavailable",
            "output": "Docker CLI was not found.",
        }
    )
    monkeypatch.setattr("app.graph.nodes.run_linter_tool", fake_tool)

    state = create_initial_state(
        pr_url="https://github.com/example/demo/pull/6",
        repository_full_name="example/demo",
        pr_number=6,
    )
    state["code_contents"] = {"bad.py": "x=1"}

    import pytest

    with pytest.raises(RuntimeError, match="Docker CLI was not found"):
        lint_code_node(state)
