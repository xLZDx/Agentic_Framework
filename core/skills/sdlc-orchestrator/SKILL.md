---
name: sdlc-orchestrator
description: Drive a project through the SDLC from idea to release with a scrum-style virtual team. Use at project/sprint start, at every phase transition, and when asked for process status. The main session runs it; subagents cannot launch other agents.
---

# sdlc-orchestrator

## Apply when
A project or sprint needs to move through phases with the right specialist at each step. Works the same in Claude Code and in GPT/Codex sessions: the phase map and the state tool are shared.

## Method
1. Read the phase: `python <framework>/tools/af_cli.py status` (run from the project). The phase map is `core/orchestration/phase-map.json`; state lives in the project's `docs/sdlc/state.json` and `docs/sdlc/STATE.md`.
2. Launch ONLY the current phase's role agents as real agent runs (never role play in chat). Each role writes its artifact to `docs/sdlc/`.
3. When every exit artifact exists, run `af_cli.py next`. It refuses to advance while artifacts are missing and, at phase 8, while there is no valid PM-GPT approval for the exact HEAD.
4. Reviewer agents use only Sonnet 5.5 medium (Claude) or GPT-5.6 Luna low/medium (GPT). Opus is never automatic.

## Phases, roles, exit artifacts
| # | Phase | Role (agent) | Exit artifact |
|---|---|---|---|
| 1 | Discovery | `business-analyst` | requirements.md |
| 2 | Backlog | `product-owner` | backlog.md |
| 3 | Design | `architect` / `code-architect`, `ui-designer` | design.md |
| 4 | Docs + test plan | `technical-writer`, `functional-test-reviewer`, `e2e-runner` | test-plan.md |
| 5 | Doc review | relevant reviewers, then optional PM-GPT docs review | review-record.md |
| 6 | Build | `implementation-engineer` | all sprint code committed, change record per commit |
| 7 | Verify | test agents write+run per-epic tests, then specialists | verify-evidence.md |
| 8 | PM-GPT review and approve | PM-GPT via skill `pm-gpt-review` | gate-approval.md bound to HEAD |
| 9 | Accept + release | `product-owner`, `technical-writer` | acceptance.md |
| 10 | Report + retro | `reporting-analyst` | sprint-report.md |

## Rules
- Phase 6 runs no tests or checks. Phase 7 runs only test-agent-authored focused tests.
- `git push` and PR creation are blocked until phase 8 holds a PM-GPT APPROVE for the exact HEAD. A later commit invalidates it.
- Never write `gate-approval.md` by hand; only `af_cli.py pm-review` produces it from a correlated PM reply.
- Existing project: one review of current docs/code, one fix pass; do not rewrite settled documents.
- Project architecture and domain rules stay in that project; never import them from siblings.

## Required output
Current phase, artifacts present/missing, next role to launch, agents and models actually run.

## Do not
Skip a phase silently; let an implementer approve its own work; simulate roles in chat; self-approve the PM-GPT gate.

Roster: `references/team-roster.md`. Templates: `references/artifact-templates.md`.
