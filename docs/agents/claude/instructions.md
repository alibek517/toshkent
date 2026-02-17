# Instructions for Claude Agents

**Role**: Reviewer, Refactorer & Complex Logic Solver.

## Tasks
1.  **Review**: Check code in `main.py` for race conditions (especially with `asyncio`).
2.  **Refactor**: Suggest modularization. `main.py` is getting large (800+ lines); propose splitting it into `handlers/`, `core/`, `database/`.
3.  **Test**: Write complex test cases for the regex engine and `portal_app.py` logic.

## Context
- Use `docs/beads.md` to track the history of changes.
- If you find a bug, document it in `docs/known_issues.md` (create if missing).
