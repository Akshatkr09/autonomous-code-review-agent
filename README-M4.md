# M4 integration notes

1. Copy the contents of this bundle into the repository root, preserving paths.
2. Build the linter image:

   ```powershell
   docker build -t code-review-linter:latest -f sandbox/Dockerfile sandbox
   ```

3. Run the focused test suite:

   ```powershell
   pytest -v tests/test_linter.py tests/test_linter_node.py tests/test_github_service.py tests/test_github_node.py tests/test_graph.py
   ```

4. Run the direct Docker smoke check from `docs/sandbox-security-m4.md`.
5. Review `git status --short`, then commit the M4 changes only after tests pass.

This milestone intentionally does not implement LLM refactoring or GitHub write-back. Those remain separate milestones, and the approval gate must remain in front of all write operations.
