# Decision log (append-only)

## 2026-10-28 - Initial framework
- Architecture: neutral `core/` rendered to `deploy/claude` and `deploy/codex` (pattern from the Agentic Studio / AI Dev Kit archive). Config is JSON (stdlib only), not YAML.
- Scope taken from Virtual_scrum_team: orchestration only (roles, skills, 10-phase map). Sandbox/QA runner and AEVE excluded by operator instruction.
- Phase 8 became "PM-GPT review and approve": mechanical, HEAD-bound, shared by Claude and GPT/Codex through PM Bridge `review.js`.
- Global installation (`~/.claude`, `~/.codex`, settings hooks) is opt-in and not performed by this change.

## 2026-10-28 - Import of the operator's agents and skills, /af toggle, push-gate fix
- Imported all 36 agents and 8 non-empty skills from the operator's agents-skills-repo into core/ (three skill folders there were empty and were skipped). `autonomous-completion.md` has no agent frontmatter, so it lives in core/policies/ and is not deployed as an agent.
- All bundled roles are now in framework.json `bundled_agents`/`bundled_skills`; the deploy parser accepts inline `tools: [..]` lists and drops source-only keys (tier, token_budget_*); the target decides model and effort.
- Toggle: `af_cli.py on|off` (off = paused: no phase injection, no push gate, state kept). Exposed as skill `/af` for Claude (user-invoked only) and prompt `/prompts:af` for Codex, both generated from core/commands/af.md.
- Evidence: the functional-test-reviewer run (93 tests, 90 passed) found that the push-gate regex blocked any git command containing the word push. Replaced by a tokenising `is_push_command` check.
- Evidence: full suite 161 tests, 161 OK after fixing a missing bundled role (implementation-engineer, phase 6) and Windows backslash git paths in the push gate.
- Autostart fallback: schtasks ONLOGON returned "Access is denied" without admin, so register falls back to the per-user HKCU Run key (no elevation). Verified by 165-test run (164 OK, 1 self-skip).
- Autostart (operator request): tools/af_autostart.py registers a Windows logon task and a VS Code folder-open task that only sync the installed copy; enabling the framework in a project stays `/af on`.
- Global installation stays opt-in: tools/af_install.py (dry-run, backups, manifest for exact uninstall). The operator chose to install only this framework, not the ADK installer.
