"""Unit tests for structured LLM refactoring and output validation."""

from __future__ import annotations

import pytest

from app.services.refactor_service import RefactorService, RefactorServiceError


class FakeStructuredModel:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return self.result


def _service(result):
    model = FakeStructuredModel(result)
    return RefactorService(model=model), model


def test_service_returns_exact_complete_file_mapping():
    service, model = _service(
        {
            "summary": "Applied formatting and simplified the calculation.",
            "files": [
                {"filename": "src/math_ops.py", "code": "def add(a, b):\n    return a + b\n"}
            ],
        }
    )

    result = service.generate_refactor(
        code_contents={"src/math_ops.py": "def add(a,b):return a+b"},
        lint_errors=[{"file": "src/math_ops.py", "tool": "black", "message": "formatting"}],
        reviewer_feedback="Use a descriptive variable name",
        review_attempt=1,
    )

    assert result["refactored_code"]["src/math_ops.py"].startswith("def add")
    assert "Applied formatting" in result["refactor_summary"]
    assert len(model.calls) == 1
    assert "Use a descriptive variable name" in model.calls[0][1].content


def test_service_rejects_missing_files():
    service, _ = _service({"summary": "Changed one file", "files": []})

    with pytest.raises(RefactorServiceError, match="schema"):
        service.generate_refactor(code_contents={"a.py": "x = 1\n"})


def test_service_rejects_unexpected_filename():
    service, _ = _service(
        {
            "summary": "Changed a file",
            "files": [{"filename": "other.py", "code": "x = 1\n"}],
        }
    )

    with pytest.raises(RefactorServiceError, match="exactly the supplied files"):
        service.generate_refactor(code_contents={"a.py": "x = 1\n"})


def test_service_rejects_duplicate_filename():
    service, _ = _service(
        {
            "summary": "Duplicate result",
            "files": [
                {"filename": "a.py", "code": "x = 1\n"},
                {"filename": "a.py", "code": "x = 2\n"},
            ],
        }
    )

    with pytest.raises(RefactorServiceError, match="duplicate filenames"):
        service.generate_refactor(code_contents={"a.py": "x = 1\n"})


def test_service_rejects_non_python_and_path_traversal():
    service, _ = _service({"summary": "unused", "files": [{"filename": "a.py", "code": "x=1"}]})

    with pytest.raises(ValueError, match="Only Python"):
        service.generate_refactor(code_contents={"README.md": "hello"})
    with pytest.raises(ValueError, match="Unsafe"):
        service.generate_refactor(code_contents={"../a.py": "x = 1"})


def test_service_requires_api_key_for_real_model():
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        RefactorService(api_key="")
