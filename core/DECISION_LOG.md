# Decision log (append-only)

## 2026-10-28 - Initial framework
- Architecture: neutral `core/` rendered to `deploy/claude` and `deploy/codex` (pattern from the Agentic Studio / AI Dev Kit archive). Config is JSON (stdlib only), not YAML.
- Scope taken from Virtual_scrum_team: orchestration only (roles, skills, 10-phase map). Sandbox/QA runner and AEVE excluded by operator instruction.
- Phase 8 became "PM-GPT review and approve": mechanical, HEAD-bound, shared by Claude and GPT/Codex through PM Bridge `review.js`.
- Global installation (`~/.claude`, `~/.codex`, settings hooks) is opt-in and not performed by this change.
