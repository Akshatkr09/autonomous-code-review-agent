"""Unit tests for the Docker-backed LangChain linter tool."""

from __future__ import annotations

import json
import subprocess

import pytest

from app.tools import linter


def _completed(stdout: str, *, returncode: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess(args=["docker"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_linter_tool_parses_successful_flake8_and_black_results(monkeypatch) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return _completed("All checks passed.\n__LINTER_EXIT_CODES__ flake8=0 black=0\n")

    monkeypatch.setattr(linter.subprocess, "run", fake_run)

    result = json.loads(
        linter.run_linter_tool.func("def add(a, b):\n    return a + b\n", "src/add.py")
    )

    assert result["ok"] is True
    assert result["flake8_exit_code"] == 0
    assert result["black_exit_code"] == 0
    assert len(calls) == 1
    command = calls[0][0]
    assert "--network" in command and "none" in command
    assert "--read-only" in command
    assert "--cap-drop" in command and "ALL" in command
    assert "--memory" in command and "256m" in command
    assert "--pids-limit" in command and "64" in command
    assert "--mount" in command
    assert any("readonly" in argument for argument in command if argument.startswith("type=bind"))


def test_linter_tool_reports_style_and_lint_failures(monkeypatch) -> None:
    output = "sample.py:1:1: E302 expected 2 blank lines\nwould reformat /workspace/sample.py\n"
    monkeypatch.setattr(
        linter.subprocess,
        "run",
        lambda *args, **kwargs: _completed(
            output + "__LINTER_EXIT_CODES__ flake8=1 black=1\n"
        ),
    )

    result = json.loads(linter.run_linter_tool.func("x=1\n", "sample.py"))

    assert result["ok"] is False
    assert result["flake8_exit_code"] == 1
    assert result["black_exit_code"] == 1
    assert "E302" in result["output"]


@pytest.mark.parametrize("filename", ["../escape.py", "/absolute.py", "folder/../../escape.py", "notes.txt", "bad name.py"])
def test_linter_tool_rejects_unsafe_or_unsupported_filename(filename: str) -> None:
    result = json.loads(linter.run_linter_tool.func("x = 1", filename))
    assert result["ok"] is False
    assert result["category"] == "invalid_input"


def test_linter_tool_rejects_oversized_source() -> None:
    result = json.loads(
        linter.run_linter_tool.func("x" * (linter.MAX_SOURCE_BYTES + 1), "large.py")
    )
    assert result["ok"] is False
    assert result["category"] == "invalid_input"
    assert "exceeds" in result["output"]


def test_linter_tool_handles_missing_docker_cli(monkeypatch) -> None:
    def missing_docker(*args, **kwargs):
        raise FileNotFoundError("docker not found")

    monkeypatch.setattr(linter.subprocess, "run", missing_docker)

    result = json.loads(linter.run_linter_tool.func("x = 1\n", "sample.py"))
    assert result["ok"] is False
    assert result["category"] == "docker_unavailable"
