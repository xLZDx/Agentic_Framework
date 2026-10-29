# 0013 - bundle referenced skills, declare externals, installer check

Sprint: framework-maintenance

## What changed
- 11 generic skills referenced by the curated agents are now bundled in `core/skills` (a11y-contract, ci-release-contract, context-memory-hygiene, db-change-contract, git-worktree-ops, migration-safety, observability-contract, performance-testing, repo-recon, security-evidence-contract, ux-design-contract); 29 bundled skills in total.
- `html-report` and `financial-ml-contract` are declared in `external_skills` (they carry operator-specific content).
- `tools/af_install.py`: `install()` logs `EXTERNAL-SKILLS ok` or `EXTERNAL-SKILLS MISSING: ...` for external skills absent from the target home.
- `core/agents/reporting-analyst.md` reads `docs/sdlc/state.json` as the authority; `STATE.md`/`AF_STATE.md` is a generated view.
- Removed a private path from `workspace-docgen/SKILL.md` and a vendor attribution from `performance-testing/references/sql-perf-tuning-loop.md`.
- Tests: an unresolved agent skill reference now fails (`tests/test_curated.py`); new `tests/test_externals.py`.

## Why
GPT-PM round 7 (MAJOR AF-001, MINOR AF-002, AF-003): agents referenced 13 skills that a clean install would not have; the reporting agent read the wrong state file; the Markdown evidence summary was stale.

## Verification
- `functional-test-reviewer` ran the five affected files: 77 tests, 76 OK, 1 self-skip, 0 failures (`sub19.log`); the first run found two content bugs (vendor attribution, private path), fixed here.
- NOT_RUN: complete suite on this tree (operator rule), live PM Bridge, real home installs.
