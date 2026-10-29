# 0012 - curated agent bodies, backend/frontend engineer skills

Sprint: framework-maintenance

## What changed
- `core/agents/*.md`: 25 agents now carry the operator's installed curated versions (bodies plus frontmatter `skills`, `maxTurns`, `effort`); `deploy/` regenerated. Codex effort is derived per agent (`low` or `medium`).
- New bundled skills `backend-engineer` and `frontend-engineer` (`core/skills/`, registered in `core/framework.json`), self-contained and independent of any team workspace or corporate connector.
- Tests updated by `functional-test-reviewer`: derived effort expectations, skill count, new `tests/test_curated.py` (skill registration, forbidden foreign tokens, skill references).

## Why
- Operator decision: take the installed curated agents as the base. Installed Claude and Codex copies had diverged from `core/`, so Codex kept using the older versions.
- Operator decision: import only ADK pieces independent of corporate systems. Review of the 26 ADK skills: only these two engineer skills and three UX/guide skills are connector-free, and the UX/guide ones depend on Agentic Studio internals, so they were not imported.

## Affected contracts
- Deployed agent files under `deploy/claude/agents` and `deploy/codex/agents`; bundled skill list.

## Verification
- Complete run `full15.log`: 355 tests, 9 failures (7 outdated expectations, fixed; 2 were my "Agentic Studio" wording in the new skill descriptions, fixed).
- After fixes only the affected files were run, per operator instruction: `test_curated`, `test_deploy`, `test_deploy_imported` = 41 tests, 41 OK (`sub17.log`). Other files were not re-run after the fixes.
- Known gap: 13 skills named in agent frontmatter are not bundled (a11y-contract, ci-release-contract, context-memory-hygiene, db-change-contract, financial-ml-contract, git-worktree-ops, html-report, migration-safety, observability-contract, performance-testing, repo-recon, security-evidence-contract, ux-design-contract); they exist in the operator's global setup only (see `core/BACKLOG.md`).
