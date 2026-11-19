"""Sandboxed Python linting tool backed by a restricted Docker container.

The submitted source is mounted read-only and is never imported or executed.
Flake8 and Black only parse and inspect the source inside the container.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from langchain_core.tools import tool

MAX_SOURCE_BYTES = 256_000
MAX_OUTPUT_CHARS = 12_000
DOCKER_TIMEOUT_SECONDS = 45
_EXIT_MARKER = re.compile(r"__LINTER_EXIT_CODES__ flake8=(\d+) black=(\d+)")


def _validate_filename(filename: str) -> PurePosixPath:
    """Accept a safe relative Python filename; reject traversal and shell syntax."""
    if not filename or len(filename) > 180:
        raise ValueError("filename must be a non-empty relative path of at most 180 characters")
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", filename):
        raise ValueError("filename may contain only letters, numbers, dots, underscores, slashes and hyphens")

    path = PurePosixPath(filename)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("filename must not be absolute or contain path traversal")
    if path.suffix.lower() not in {".py", ".pyi"}:
        raise ValueError("only .py and .pyi files can be linted")
    return path


def _error_result(filename: str, message: str, *, category: str = "execution_error") -> str:
    return json.dumps(
        {
            "filename": filename,
            "ok": False,
            "category": category,
            "flake8_exit_code": None,
            "black_exit_code": None,
            "output": message[:MAX_OUTPUT_CHARS],
        },
        ensure_ascii=False,
    )


def _run_docker_linter(code_string: str, filename: str) -> dict[str, Any]:
    """Write source to a temporary read-only mount and run Flake8 + Black."""
    relative_path = _validate_filename(filename)
    encoded = code_string.encode("utf-8")
    if len(encoded) > MAX_SOURCE_BYTES:
        raise ValueError(f"source exceeds the {MAX_SOURCE_BYTES}-byte limit")

    image = os.getenv("LINTER_DOCKER_IMAGE", "code-review-linter:latest")
    container_target = "/workspace/" + relative_path.as_posix()

    with tempfile.TemporaryDirectory(prefix="code-review-lint-") as temporary_dir:
        host_root = Path(temporary_dir)
        target_file = host_root.joinpath(*relative_path.parts)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(code_string, encoding="utf-8", newline="\n")

        # The container runs as an unprivileged user. The temporary workspace
        # must be traversable/readable by that UID, while remaining read-only
        # once mounted into the container.
        try:
            host_root.chmod(0o755)
            current = target_file.parent
            while current != host_root:
                current.chmod(0o755)
                current = current.parent
            target_file.chmod(0o644)
        except OSError:
            # Windows ACLs govern access there; chmod is best-effort.
            pass

        shell_script = (
            "set +e\n"
            "flake8 --format='%(path)s:%(row)d:%(col)d: %(code)s %(text)s' \"$TARGET\"\n"
            "flake8_status=$?\n"
            "black --check --diff \"$TARGET\"\n"
            "black_status=$?\n"
            "printf '\\n__LINTER_EXIT_CODES__ flake8=%s black=%s\\n' \"$flake8_status\" \"$black_status\"\n"
            "exit 0\n"
        )

        command = [
            "docker", "run", "--rm",
            "--network", "none",
            "--memory", "256m",
            "--cpus", "1",
            "--pids-limit", "64",
            "--ulimit", "nofile=64:64",
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true",
            "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=64m",
            "--user", "10001:10001",
            "--mount", f"type=bind,source={host_root.resolve()},target=/workspace,readonly",
            "--workdir", "/workspace",
            "--env", f"TARGET={container_target}",
            "--env", "HOME=/tmp",
            image,
            "sh", "-lc", shell_script,
        ]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=DOCKER_TIMEOUT_SECONDS,
                check=False,
            )
        except FileNotFoundError:
            return {
                "filename": filename,
                "ok": False,
                "category": "docker_unavailable",
                "flake8_exit_code": None,
                "black_exit_code": None,
                "output": "Docker CLI was not found. Install Docker Desktop, start it, and reopen the terminal.",
            }
        except subprocess.TimeoutExpired:
            return {
                "filename": filename,
                "ok": False,
                "category": "timeout",
                "flake8_exit_code": None,
                "black_exit_code": None,
                "output": f"Docker linting exceeded the {DOCKER_TIMEOUT_SECONDS}-second timeout.",
            }

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        combined_output = (stdout + ("\n" + stderr if stderr else "")).strip()
        marker = _EXIT_MARKER.search(stdout)

        if completed.returncode != 0 or marker is None:
            return {
                "filename": filename,
                "ok": False,
                "category": "docker_execution_error",
                "flake8_exit_code": None,
                "black_exit_code": None,
                "output": (
                    "Docker could not run the linter container. Build the image with "
                    "`docker build -t code-review-linter:latest -f sandbox/Dockerfile sandbox`. "
                    f"Details: {combined_output}"
                )[:MAX_OUTPUT_CHARS],
            }

        flake8_code, black_code = (int(marker.group(1)), int(marker.group(2)))
        return {
            "filename": filename,
            "ok": flake8_code == 0 and black_code == 0,
            "category": "lint_result",
            "flake8_exit_code": flake8_code,
            "black_exit_code": black_code,
            "output": combined_output[:MAX_OUTPUT_CHARS],
        }


@tool

def run_linter_tool(code_string: str, filename: str = "candidate.py") -> str:
    """Run Flake8 and Black checks on Python source inside a restricted Docker sandbox.

    The source is written to a temporary directory, mounted read-only, and
    inspected without being imported or executed. Returns a JSON string with
    per-tool exit codes, diagnostics, and an overall success flag.
    """
    try:
        result = _run_docker_linter(code_string, filename)
    except (UnicodeEncodeError, ValueError) as exc:
        return _error_result(filename, str(exc), category="invalid_input")
    return json.dumps(result, ensure_ascii=False)
