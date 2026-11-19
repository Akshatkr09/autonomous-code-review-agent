# M5 — LLM-powered refactoring

## Purpose

M5 implements the `propose_refactor_node` using LangChain's `ChatOpenAI` integration. The model receives the fetched Python source, lint diagnostics, and any reviewer feedback, then returns complete replacement source for the exact same set of files.

## Design decisions

- Uses `ChatOpenAI` with temperature 0 and Pydantic structured output.
- Does not give the model tools or execution access.
- Treats source code, comments, PR descriptions, and reviewer feedback as untrusted data rather than instructions.
- Validates that each supplied filename is returned exactly once. Missing, duplicate, or unexpected files are rejected.
- Enforces a 25-file and 200 KB combined-source limit before sending content to the model.
- Stores the proposal summary and full replacement contents in LangGraph state.
- Increments `review_attempt` and resets `is_approved` to `None` so every new proposal requires a fresh human decision.
- Does not write to GitHub. Repository writes remain isolated to the later approved write-back milestone.

## Configuration

Add a valid OpenAI API key to the local `.env` file:

```env
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-4o-mini
```

The API key is not required for unit tests because those tests inject a deterministic fake model/service. Real API requests are billable and require API access/billing on the OpenAI Platform.

## Tests

Run the M5 tests:

```powershell
pytest -v tests/test_refactor_service.py tests/test_refactor_node.py
```

Run the complete suite:

```powershell
pytest -v
```

The tests do not call the real OpenAI API and do not consume API credits.

## Manual smoke test

After configuring `OPENAI_API_KEY`, test the service against a small, non-sensitive Python snippet. Do not use private or production source code for an initial API smoke test. The resulting proposal should be reviewed and linted before any repository write is considered.
