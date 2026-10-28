# Change 0001 - initial framework

What: new repository with a neutral core (6 roles, 8 skills, phase map), a stdlib CLI (state, phase gating, PM-GPT review, Claude hook, git pre-push gate, deploy) and generated deploy/claude and deploy/codex.
Why: one SDLC orchestration usable from Claude and GPT/Codex, with a mechanical PM-GPT review and approve step (phase 8) bound to the exact HEAD.
Contracts: phase-map.json (phases, push gate, PM review config); approval files under docs/sdlc/.pm-review and gate-approval.md.
Decisions: see core/DECISION_LOG.md. Out of scope: Virtual_scrum_team sandbox/QA runner and AEVE.
Verification: functional tests are authored and run by the functional-test-reviewer agent; results are recorded in the follow-up commit. At this commit tests are NOT_RUN.
