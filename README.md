# Autonomous Code Review & Refactoring Agent

A stateful code review and refactoring agent built with **LangGraph**, **LangChain**, the **GitHub API**, and **FastAPI**. It is designed to inspect Pull Request changes, run code-quality checks in an isolated environment, propose refactorings with an LLM, and require human approval before writing changes back to GitHub.

> **Status:** Initial project scaffold. Workflow nodes, API routes, GitHub operations, sandbox execution, and automated tests will be implemented and validated in subsequent milestones.

## Assessment objectives

The implementation will cover the three verification scenarios in the project brief:

1. **PR ingestion and HITL pause:** receive a GitHub PR webhook (or local mock event), fetch changed files, run lint checks, and pause before repository writes.
2. **Reviewer feedback loop:** record rejection feedback, regenerate the refactoring proposal, and pause again for review.
3. **Approval and write-back:** resume an approved review and commit the approved changes to the PR branch.

## Technology stack

- Python 3.11
- LangGraph and SQLite-backed checkpoint persistence
- LangChain and LangChain OpenAI integration
- GitHub API
- FastAPI and Uvicorn
- Docker for isolated code-quality execution
- Flake8 and Black
- Pytest and HTTPX

## Project layout

```text
app/
  api/        FastAPI routes and request handling
  config/     Typed application settings
  graph/      State schema, nodes, routing, and graph construction
  services/   GitHub API integration
  tools/      Custom linting and sandbox tools
tests/        Unit and integration tests
sandbox/      Temporary analysis workspace
data/         Local checkpoint database directory
```

## Local setup

### 1. Clone the repository

```bash
git clone https://github.com/Akshatkr09/autonomous-code-review-agent.git
cd autonomous-code-review-agent
```

### 2. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env` and provide your own credentials:

- `GITHUB_TOKEN`: token with access to the test repository. The completed workflow needs permission to read PRs and read/write repository contents.
- `OPENAI_API_KEY`: API key used by the configured LangChain chat model.
- `GITHUB_WEBHOOK_SECRET`: secret used to validate incoming GitHub webhook signatures.

Never commit `.env` or expose credentials in logs, source code, or screenshots.

### 5. Run tests

The test suite will be added during implementation. Once available, run:

```bash
pytest -q
```

## Security design goals

- Treat Pull Request code as untrusted input; never execute it directly on the host.
- Run analysis in an isolated sandbox with restricted permissions and resource limits.
- Disable network access for sandboxed code execution by default.
- Require explicit reviewer approval before any GitHub write operation.
- Verify webhook signatures with HMAC and protect secrets using environment configuration.

## API documentation

FastAPI will expose interactive OpenAPI documentation at `/docs` while the local server is running. An OpenAPI specification export will be included in the final submission.

## Evaluation and validation

The final test suite will verify graph routing, checkpoint/resume behavior, sandbox linting, and API integration for all three assessment scenarios. See the project brief for the detailed evaluation rubric and expected request flows.
