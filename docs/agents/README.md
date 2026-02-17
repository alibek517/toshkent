# Agent Instructions: General

This project involves multiple AI agents working in tandem. 
**ALL AGENTS MUST USE `bd` CLI to manage context.**

## Roles
- **Gemini**: Primary code generator and architect.
- **Antigravity**: Implementation and execution engine (You are here).
- **Claude**: Expert reviewer and complex logic debugger.

## Communication Protocol
1.  **Context**: Before starting work, run `bd list` to see active tasks.
2.  **Handover**: If you stop partway, create a new task with `bd create`.
3.  **Documentation**: Update `docs/architecture/` if you change core logic.

---

### Specific Instructions
See subfolders:
- [Gemini](./gemini/instructions.md)
- [Antigravity](./antigravity/instructions.md)
- [Claude](./claude/instructions.md)
