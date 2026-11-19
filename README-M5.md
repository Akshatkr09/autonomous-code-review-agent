# M5 implementation notes — LLM refactoring

This milestone connects `propose_refactor_node` to a dedicated `RefactorService` using LangChain `ChatOpenAI` structured output.

## Files in this bundle

- `app/services/refactor_service.py` — model integration, structured schema and strict source-file validation.
- `app/graph/nodes.py` — updated proposal node; preserves existing GitHub and sandbox nodes.
- `app/graph/state.py` — adds `refactor_summary` to review state.
- `tests/test_refactor_service.py` — isolated service tests using a fake structured model.
- `tests/test_refactor_node.py` — graph node tests with a fake service.
- `docs/llm-refactoring-m5.md` — design, configuration and testing notes.

## Install

Extract the bundle into the repository root, preserving folders and allowing the two existing graph files to be replaced.

No new Python dependency is required; `langchain-openai`, `langchain-core`, and Pydantic are already in `requirements.txt`.

Add to local `.env`:

```env
OPENAI_API_KEY=your_api_key
OPENAI_MODEL=gpt-4o-mini
```

## Verify

```powershell
pytest -v tests/test_refactor_service.py tests/test_refactor_node.py
pytest -v
```

The tests use fake model responses and do not call OpenAI.

## Commit after tests pass

```powershell
git add app/graph/nodes.py app/graph/state.py app/services/refactor_service.py tests/test_refactor_service.py tests/test_refactor_node.py docs/llm-refactoring-m5.md README-M5.md
git commit -m "feat: add LLM-powered refactoring proposals"
git push origin main
```
