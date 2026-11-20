# Autonomous Code Review & Refactoring Agent

A LangGraph-powered agent that reviews GitHub Pull Requests, runs Python lint checks in a restricted Docker container, proposes refactorings with an LLM, and commits approved changes to the Pull Request's source branch only after human approval.

**Assessment implementation:** Python · LangGraph · LangChain · GitHub API · FastAPI · Docker · SQLite · Pytest

## Workflow

1. `POST /api/webhooks/github` receives a Pull Request event and starts a LangGraph review thread.
2. `fetch_pr_node` retrieves Pull Request metadata and changed Python files from the PR head commit.
3. `lint_code_node` runs Flake8 and Black through the Docker-backed custom LangChain tool. PR source is inspected, not imported or executed.
4. `propose_refactor_node` asks the configured OpenAI chat model for complete replacement source files and validates the response schema and exact filename set.
5. LangGraph persists the review state in SQLite and pauses before `apply_changes_node`.
6. A reviewer rejects with feedback or approves through `POST /api/reviews/{thread_id}/approve`.
7. Rejection regenerates the proposal and pauses for a new decision. Approval resumes the graph and commits all approved files to the PR head branch in one Git commit.

The agent does **not** merge Pull Requests.

## Assessment deliverables

- Python application and automated tests in this repository.
- OpenAPI specification: generate `openapi.json` using the export command below.
- This README documents installation, configuration, execution, and tests.

The implementation maps to the assessment's three required validation scenarios: webhook ingestion/HITL pause, rejection/feedback regeneration, and approval/GitHub commit write-back. See [docs/assessment-validation.md](docs/assessment-validation.md) for reproducible steps.

## Requirements

- Python 3.11 or newer (the project has also been exercised locally on Python 3.14.6).
- Git.
- Docker Desktop with the Linux container engine running.
- GitHub account and a fine-grained Personal Access Token.
- OpenAI API key with API billing/model access configured.

## Local installation — Windows PowerShell

```powershell
git clone https://github.com/Akshatkr09/autonomous-code-review-agent.git
cd autonomous-code-review-agent
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and provide the credentials/configuration:

```dotenv
GITHUB_TOKEN=your_fine_grained_github_token
OPENAI_API_KEY=your_openai_api_key
GITHUB_WEBHOOK_SECRET=
OPENAI_MODEL=gpt-4o-mini
DATABASE_PATH=./data/review_checkpoints.sqlite
```

The token must have **Contents: read and write**, **Pull requests: read-only**, and **Metadata: read-only** access to the repository being tested. For a forked PR, write access is needed on the PR's source/fork repository too. Keep `.env` private; only `.env.example` belongs in Git.

## Build the Docker linter image

Start Docker Desktop and ensure the Linux engine is running:

```powershell
docker version
docker build -t code-review-linter:latest -f sandbox/Dockerfile sandbox
docker image inspect code-review-linter:latest
```

The linter container runs with no network, read-only root filesystem and source mount, dropped Linux capabilities, resource limits, and an unprivileged user. It runs Flake8 and Black checks; it does not execute the submitted Python program.

## Run the application

From the repository root, use the command specified in the assessment brief:

```powershell
uvicorn main:app --reload
```

API documentation: <http://127.0.0.1:8000/docs>
OpenAPI JSON endpoint: <http://127.0.0.1:8000/openapi.json>

## Export OpenAPI specification for submission

With dependencies installed, run:

```powershell
python scripts/export_openapi.py
```

This generates `openapi.json` at the repository root. Commit that generated file as part of the submission.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/webhooks/github` | Validate a PR event and start a review thread |
| POST | `/api/reviews/{thread_id}/approve` | Submit approval or rejection/feedback and resume the graph |
| GET | `/api/reviews/{thread_id}` | Retrieve the persisted review status and proposal/commit metadata |

When `GITHUB_WEBHOOK_SECRET` is configured, webhook requests must include a valid `X-Hub-Signature-256` header. For local assessment simulation, the secret may be left empty and a mock GitHub webhook payload can be posted. See the validation guide for full PowerShell examples.

## Run automated tests

```powershell
pytest -v
```

The tests use deterministic fake GitHub/LLM integrations and a temporary SQLite database for repeatable unit and API workflow verification. They do not create real GitHub commits or spend OpenAI API credits. Use a disposable PR for the live write-back demonstration described in the validation guide.

## Repository layout

```text
app/
  api/        FastAPI request schemas and endpoints
  config/     Typed environment settings
  graph/      LangGraph state, nodes, routing, runtime and checkpointer
  services/   GitHub and LLM integration services
  tools/      Docker-backed LangChain linting tool
sandbox/      Dockerfile for the restricted lint container
tests/        Unit, graph, persistence and API workflow tests
docs/         Architecture, security and assessment validation guides
scripts/      OpenAPI export utility
main.py       Uvicorn entry point required by the assessment
openapi.json  Generated OpenAPI specification (created by export command)
```

## Security and operational limitations

- Human approval is required before GitHub write-back. The write node also validates the exact reviewed PR head SHA and branch.
- A branch movement conflict stops write-back; rerun review against the new PR head.
- Webhook HMAC verification authenticates delivery, but the local assessment API does not implement reviewer user authentication/authorization. Do not expose it publicly as-is.
- Use a disposable Pull Request for live tests. GitHub write-back changes the PR source branch but does not merge the PR.
- GitHub and OpenAI API calls require valid credentials, network access, and applicable permissions/billing.
