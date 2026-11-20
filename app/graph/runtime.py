"""Runtime manager for the checkpointed LangGraph review workflow."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable, Mapping

from langgraph.checkpoint.sqlite import SqliteSaver

from app.graph.state import ReviewState, create_initial_state
from app.graph.workflow import build_review_graph


class ReviewRuntime:
    """Own the SQLite connection and compiled review graph for one app process."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        node_overrides: Mapping[str, Callable[[ReviewState], dict[str, Any]]] | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.node_overrides = node_overrides
        self._connection: sqlite3.Connection | None = None
        self._checkpointer: SqliteSaver | None = None
        self.graph: Any | None = None

    def start(self) -> None:
        """Open the persistent checkpointer and compile the graph once."""
        if self.graph is not None:
            return

        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            str(self.database_path),
            check_same_thread=False,
        )
        self._checkpointer = SqliteSaver(self._connection)
        self._checkpointer.setup()
        self.graph = build_review_graph(
            checkpointer=self._checkpointer,
            node_overrides=self.node_overrides,
        )

    def close(self) -> None:
        """Close the SQLite connection during application shutdown."""
        self.graph = None
        self._checkpointer = None
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _require_graph(self) -> Any:
        if self.graph is None:
            raise RuntimeError("ReviewRuntime has not been started")
        return self.graph

    @staticmethod
    def _config(thread_id: str) -> dict[str, dict[str, str]]:
        if not thread_id or not thread_id.strip():
            raise ValueError("thread_id must not be empty")
        return {"configurable": {"thread_id": thread_id}}

    def start_review(
        self,
        *,
        thread_id: str,
        pr_url: str,
        repository_full_name: str,
        pr_number: int,
        base_branch: str = "main",
        head_branch: str = "",
    ) -> Any:
        """Run a new review until it reaches the pre-write human approval gate."""
        graph = self._require_graph()
        config = self._config(thread_id)
        initial_state = create_initial_state(
            pr_url=pr_url,
            repository_full_name=repository_full_name,
            pr_number=pr_number,
            base_branch=base_branch,
            head_branch=head_branch,
        )
        graph.invoke(initial_state, config)
        snapshot = graph.get_state(config)
        if not snapshot.values:
            raise RuntimeError("Graph completed without storing a review state")
        return snapshot

    def get_review(self, thread_id: str) -> Any | None:
        """Return a persisted state snapshot, or None for an unknown thread."""
        graph = self._require_graph()
        snapshot = graph.get_state(self._config(thread_id))
        if not snapshot.values:
            return None
        return snapshot

    def submit_decision(
        self,
        *,
        thread_id: str,
        approved: bool,
        feedback: str | None = None,
    ) -> Any:
        """Persist a human decision and resume the graph to its next safe point.

        Rejection resumes proposal generation and pauses again before writes.
        Approval resumes apply_changes_node; the graph only completes after the
        GitHub service confirms that the approved commit was pushed.
        """
        graph = self._require_graph()
        config = self._config(thread_id)
        snapshot = self.get_review(thread_id)
        if snapshot is None:
            raise LookupError(f"Review thread '{thread_id}' was not found")

        if tuple(snapshot.next) != ("apply_changes_node",):
            raise ValueError("This review is not currently waiting at the approval checkpoint")

        values = snapshot.values
        existing_decision = values.get("is_approved")
        # If the graph previously failed while trying to apply an approved
        # proposal, allow the same approval request to retry that pending node.
        if existing_decision is True and approved is True and values.get("review_status") == "approved":
            graph.invoke(None, config)
            updated = graph.get_state(config)
            if updated.values.get("review_status") != "completed":
                raise RuntimeError("Approved write-back did not complete")
            return updated
        if existing_decision is not None:
            raise ValueError("A decision has already been recorded for this proposal")

        clean_feedback = (feedback or "").strip()
        if not approved and not clean_feedback:
            clean_feedback = "No additional feedback provided; please review and improve the proposal."

        from datetime import datetime, timezone

        history_entry = {
            "node": "human_review",
            "event": "review_approved" if approved else "review_rejected",
            "detail": clean_feedback,
            "attempt": values.get("review_attempt", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        graph.update_state(
            config,
            {
                "is_approved": approved,
                "reviewer_feedback": clean_feedback if not approved else (feedback or "").strip(),
                "review_status": "approved" if approved else "changes_requested",
                "history": [history_entry],
            },
            as_node="review_router_node",
        )

        graph.invoke(None, config)
        updated = graph.get_state(config)

        if approved:
            if updated.values.get("review_status") != "completed":
                raise RuntimeError("Approval was recorded but GitHub write-back did not complete")
            return updated

        if tuple(updated.next) != ("apply_changes_node",):
            raise RuntimeError("Rejected review did not return to the approval checkpoint")
        return updated
