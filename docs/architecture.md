# Milestone 2 notes — LangGraph state and workflow skeleton

## Implemented

- Assessment state keys: `pr_url`, `code_contents`, `lint_errors`, `refactored_code`, `is_approved`, `reviewer_feedback`, and `history`.
- Additional repository metadata, review status, attempt counter, commit SHA, and error field.
- Append-only state reducer for the audit history.
- State validation helper for incoming PR identity.
- LangGraph node topology and conditional routing for rejection feedback.
- Mandatory checkpointer and `interrupt_before=["apply_changes_node"]`.
- Dependency injection for graph nodes so tests can exercise true LangGraph behavior without real external API calls.
- Explicit approval guard in the eventual GitHub write node.

## Intentionally not implemented yet

The GitHub fetch, lint/sandbox, LLM refactor, and GitHub write node functions raise `NotImplementedError`. These integrations are delivered in later milestones; tests substitute deterministic fakes while validating the graph's real routing/checkpoint behavior.

## Test

```bash
pytest -q tests/test_graph.py
```

## Feedback loop contract for the future FastAPI endpoint

When the graph is paused before `apply_changes_node`, the approval endpoint will update the same `thread_id` with the reviewer decision and call `update_state(..., as_node="review_router_node")`. It then resumes with `invoke(None, config)`. A rejection routes to `propose_refactor_node`; a new proposal clears `is_approved` back to `None` and returns to the approval interrupt. An approval routes to the guarded write node.
