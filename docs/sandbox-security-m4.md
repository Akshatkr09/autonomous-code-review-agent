# M4 — Custom Python Linter and Docker Sandbox

## What this milestone implements

- A custom LangChain tool named `run_linter_tool`, declared with `@tool`.
- Static checks using Flake8 and Black.
- A Docker image containing the analysis tools.
- A LangGraph `lint_code_node` that checks each Python file fetched from a PR and records results in graph state.
- Unit tests for linter outcomes, unsafe paths, source-size limits, Docker failures, and graph-state mapping.

## Build the linter image

Run this command from the repository root while Docker Desktop is running:

```powershell
docker build -t code-review-linter:latest -f sandbox/Dockerfile sandbox
```

Confirm the image exists:

```powershell
docker image inspect code-review-linter:latest
```

The container includes Flake8 and Black. The image is based on Python 3.11 so the analysis runtime is separate from the host Python installation.

## Sandbox restrictions

Every lint operation runs in a disposable container with:

- Network disabled (`--network none`).
- Read-only source mount and read-only container root filesystem.
- Unprivileged UID/GID 10001.
- All Linux capabilities dropped and `no-new-privileges` enabled.
- 256 MB memory limit, one CPU, 64 process limit, and a 45-second host timeout.
- A small temporary filesystem for tool caches.

The submitted source is never imported or executed. Flake8 and Black parse and inspect it as source text. This is a safer and narrower operation than running arbitrary PR code.

## Local tests

```powershell
pytest -v tests/test_linter.py tests/test_linter_node.py tests/test_github_service.py tests/test_github_node.py tests/test_graph.py
```

The unit tests mock the Docker CLI; they do not require a running Docker daemon. To validate the real container path, build the image and run the smoke check below.

## Direct smoke check

From the repository root, with the virtual environment active:

```powershell
python -c "from app.tools.linter import run_linter_tool; print(run_linter_tool.invoke({'code_string': 'def add(a, b):\n    return a + b\n', 'filename': 'sample.py'}))"
```

Expected result: JSON with `category` set to `lint_result`, `ok` set to `true`, and both exit codes set to `0`.

## Troubleshooting

- **Docker CLI not found:** ensure Docker Desktop is installed, running, and the terminal was reopened after installation.
- **Image not found / container startup error:** run the `docker build` command above.
- **Docker daemon unavailable:** start Docker Desktop and wait until its engine is ready.
- **Permission denied mounting the workspace:** ensure Docker Desktop file sharing allows access to the project drive.

## Security boundary

This sandbox is designed for static linting and formatting only. It is not a general-purpose untrusted-code execution environment. Do not add commands that run PR scripts, tests, package installation, or arbitrary shell content in this container. A broader execution sandbox would require additional isolation and threat modelling.
