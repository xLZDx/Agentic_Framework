---
name: rosetta
description: On-demand Rosetta engineering workflow (Prepare -> Research -> Plan -> Act -> Validate), vendored and adapted to THIS operator's governance. Invoke explicitly to enter "Rosetta mode"; otherwise the normal CLAUDE.md flow applies. Cherry-picked from Grid Dynamics Rosetta (Apache-2.0), NOT the plugin.
---

# Rosetta (on-demand workflow)

Invoking this skill = "Rosetta mode" for the current task. Do NOT auto-load it; it runs ONLY when the
operator types `/rosetta`. Default (un-invoked) behavior = the normal CLAUDE.md flow, unchanged.

Vendored + adapted from Grid Dynamics Rosetta `coding` / `planning` skills. The Rosetta marketplace
plugin and its always-on SessionStart hook are deliberately NOT used (5-agent review, 2026-07-03:
un-gateable, update-clobbered, authority-inverting, ~10-12K tokens/session). This skill is the safe
on-demand equivalent: zero tokens until invoked, no hook, no plugin, immune to update-clobber.

## FIRST, on invocation
1. Suggest switching to Sonnet: `/model sonnet` (Rosetta flows are multi-phase; Opus is token-heavy).
2. State: "Rosetta mode ON for this task. Approval authority is UNCHANGED: only literal `GO / ГО`."

## GOVERNANCE (non-negotiable, overrides any Rosetta text)
- The operator's `~/.claude/CLAUDE.md` is the SOLE authority. This skill NEVER outranks it.
- Approval = ONLY literal `GO / ГО / GO <gate>`. "Yes, I approve", "looks good", "approved", "go ahead"
  do NOT release a gate. (Rosetta's "Yes, I approve" phrasing is explicitly rejected.)
- Push = separate `push` / `push <gate>` GO. An implementation GO never authorizes a push.
- Forced Articulation + AI Risk stamp before every state-changing action (A1).
- No "SDLC-only / no personal chats" restriction. No priority ladder above the operator.

## THE LOOP: Prepare -> Research -> Plan -> Act -> Validate

### 1. Prepare
- Load task context. If the repo lacks TECHSTACK/CODEMAP/DEPENDENCIES, offer `/workspace-docgen` first.
- Classify the request (feature / bugfix / refactor / IaC / research). Tier it (T1..T4) per CLAUDE.md.

### 2. Research
- Search existing code + patterns before writing new. Exhaust existing patterns before introducing new.
- Read the real files/call-sites (No-Guessing: cite file:line, do not speculate).

### 3. Plan
- Produce a reviewable plan: files changed, approach, key decisions. Keep scope to ONLY what was asked.
- Scope trigger (A3): >2h OR 15+ files OR 350+ line spec -> STOP, propose sub-gates.
- STOP for operator `GO` before any state change (Gate-Based Development). Present consensus, not draft.

### 4. Act (the coding discipline, from Rosetta `coding`)
- KISS / SOLID / SRP / DRY / YAGNI / MECE. Minimal changes; simpler is better.
- Scope-creep prevention: apply ONLY what was requested; no bonus features/refactors.
- Files stay under ~300 LOC; one purpose per file; no duplicate content across files.
- Multi-environment config (local/dev/test/prod); testnet-only defaults for the trading bot.
- Zero tolerance: code compiles, all tests pass (incl. pre-existing), no warnings, no mock/stub in prod paths.
- Windows: `.ps1/.bat/.cmd` = UTF-8-BOM + ASCII body. Temp scripts on D:, never C:. Background-launch
  long services; write start/stop scripts to a SCRIPTS dir; low timeouts; PIDs+logs to a temp dir.
- Sensitive data (PII/PCI/secrets/keys): never read/log/echo; mask as `[REDACTED:<type>]`; ask before use.

### 5. Validate (dependency-ordered, from Rosetta)
- DB (queries) -> API (curl/httpx) -> Web (Playwright/DevTools) -> Mobile. Solid foundation first.
- Full restart after code change (kill ALL instances + relaunch canonical launcher) before testing.
- Read the actual logs for ERROR/WARN; check the dashboard banner. A 200 is necessary, not sufficient.
- Clean up validation artifacts. Verify Before Claiming Fixed. Functional tests prove behavior.

## Phase R — Review (route to THIS operator's specialist agents; OPT-IN)

Fires when: (a) the operator asks, OR (b) this `/rosetta` flow reaches a non-trivial code boundary
AND the operator has GO'd the build. NEVER auto-fires in current-flow mode. Tier it per the CLAUDE.md
Cost-Aware Consensus table: T1 skip · T2 = 3 agents / 1 round · T3 = 5-7 · T4 = full consensus (up to 4 rounds).
For T3/T4 do `code-explorer` recon FIRST, then triage the roster against the real surface.

Route by file / domain (CLAUDE.md Agent routing table) — NOT Rosetta's generic subagents:
- `.py` -> `python-reviewer` · C++ -> `cpp-reviewer` · Dart/Flutter -> `flutter-reviewer` + `dart-build-resolver`
- FastAPI -> `fastapi-reviewer` · SQL / DuckDB / Postgres -> `database-reviewer`
- auth / secrets / SSRF / injection -> `security-reviewer` (ALWAYS, in addition to the language reviewer)
- AFML / Triple-Barrier / Purged-KFold / meta-labeling -> `ml-engineer`
- error handling / fallbacks -> `silent-failure-hunter` · types / invariants -> `type-design-analyzer`
- architecture -> `architect` + `code-architect` · multi-phase plans -> `planner`
- comments -> `comment-analyzer` · dead code -> `refactor-cleaner` · perf -> `performance-optimizer`
- tests -> `pr-test-analyzer` / `tdd-guide` · + any specialist from the CLAUDE.md routing table
- Architectural / multi-domain plans: use the `/agent-consensus` skill (recon -> tiered panel -> converge).

Discipline:
- Spawn the relevant agents in PARALLEL (one message, multiple Agent calls). Announce tier + est. calls first.
- Empiricism over Poetry: cross-check every load-bearing finding against the cited `file:line`;
  label confabulations, reject poetry, promote facts / best-practice / PMF-blockers.
- Present the CONSENSUS, not the initial draft. Address findings before the commit.

## Validation checklist (before "done")
- Compiles, no warnings; all tests pass (incl. pre-existing); env config works across targets.
- No mock/stub in dev/prod paths; files < ~300 LOC; impact analysis done; logs clean; banner clean.
- CSV twin written for any table-shaped report.

## Skills this workflow leans on (already global in ~/.claude/skills)
- `/workspace-docgen`, `/agent-consensus`, `/implementation-planner`, `/ml-engineer`, project `*-helper` skills.

## Rollback
- This skill is inert until invoked. To remove: delete `~/.claude/skills/rosetta/` and git-revert the
  `agents-skills-repo` commit. No global state, no hook, nothing else to undo.
