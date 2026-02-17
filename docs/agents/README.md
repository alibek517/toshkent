# Agent Instructions: General

This project involves multiple AI agents working in tandem. 
**ALL AGENTS MUST READ `docs/beads.md` FIRST to understand the current state.**

## Roles
- **Gemini**: Primary code generator and architect.
- **Antigravity**: Implementation and execution engine (You are here).
- **Claude**: Expert reviewer and complex logic debugger.

## Communication Protocol
1.  **Context**: Before starting work, check `docs/beads.md`.
2.  **Handover**: If you stop partway, write a "Pending" bead.
3.  **Documentation**: Update `docs/architecture/` if you change core logic.

---

### Specific Instructions
See subfolders:
- [Gemini](./gemini/instructions.md)
- [Antigravity](./antigravity/instructions.md)
- [Claude](./claude/instructions.md)
