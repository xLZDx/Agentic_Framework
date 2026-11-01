---
project: Agentic_Framework
as_of: 2026-11-01
active_sprint: S4
scope: single_sprint
approved_sprints: S4
operator_approved: true
---
# Agentic_Framework - project plan

## Roadmap
| Sprint | Title | Status | Goal |
|---|---|---|---|
| S1 | Initial framework and PM-GPT gate | ACCEPTED | Neutral core/ plus generated deploy/, 10-phase map, mechanical PM-GPT review gate (20c0098..4dcd4ba, round 3 APPROVE). |
| S2 | Review remediation and backlog closure | ACCEPTED | Structured evidence, sprint-bound artifacts, input hash binding (2d6743d..5ee25f9, change 0009-0011). |
| S3 | Curated agents and opt-in push gate | ACCEPTED | Curated agent bodies, bundled skills, push gate made opt-in (2c18fd6..5e54167, changes 0012-0014). |
| S4 | Open backlog and PM review recovery | ACTIVE | Derived from core/BACKLOG.md open items and the 2026-10-30 recovery report. |

## Sprint S1 - Initial framework and PM-GPT gate
Goal: Tool-agnostic scrum-team framework with a HEAD-bound PM-GPT approval gate.

| Task | Title | Acceptance | Status | Evidence | Owner | Depends | Commit |
|---|---|---|---|---|---|---|---|
| S1-T01 | Core and deploy layers | core/ rendered to deploy/claude and deploy/codex | ACCEPTED | DECISION_LOG 2026-10-28 | assistant | | 20c0098 |
| S1-T02 | Agent/skill import and /af toggle | agents and skills imported, on/off toggle | ACCEPTED | DECISION_LOG: 161 tests OK | assistant | S1-T01 | dc12906 |
| S1-T03 | Gate remediation rounds 1-3 | PM-GPT round 3 APPROVE on 4dcd4ba | ACCEPTED | DECISION_LOG approval PMG-20261028-4dcd4ba9 | assistant | S1-T02 | 4dcd4ba |

## Sprint S2 - Review remediation and backlog closure
Goal: Close findings from PM-GPT rounds 4-6.

| Task | Title | Acceptance | Status | Evidence | Owner | Depends | Commit |
|---|---|---|---|---|---|---|---|
| S2-T01 | Structured verify evidence, artifact provenance, review input binding | BACKLOG Closed items 1-3 | ACCEPTED | BACKLOG closed 2026-10-29; 323 tests, 322 OK | assistant | | 2d6743d |
| S2-T02 | Zero-pass evidence rejected, foreign STATE.md protected | round 6 MINOR only, corrected | ACCEPTED | DECISION_LOG 2026-10-29 | assistant | S2-T01 | 75ee95b |

## Sprint S3 - Curated agents and opt-in push gate
Goal: Curated agents, bundled skills, push block opt-in.

| Task | Title | Acceptance | Status | Evidence | Owner | Depends | Commit |
|---|---|---|---|---|---|---|---|
| S3-T01 | Curated agent bodies and engineer skills | 25 agents replaced; affected tests 41/41 | ACCEPTED | DECISION_LOG change 0012 | assistant | | 2c18fd6 |
| S3-T02 | Bundle referenced skills, declare external | unresolved refs fail a test | ACCEPTED | DECISION_LOG change 0013 | assistant | S3-T01 | 645f620 |
| S3-T03 | Push/PR block opt-in | 392 tests, 391 OK, 1 skipped | ACCEPTED | DECISION_LOG change 0014 | assistant | | 5e54167 |

## Sprint S4 - Open backlog and PM review recovery
Goal: Derived from open backlog items and recent commits; close remaining open work.

| Task | Title | Acceptance | Status | Evidence | Owner | Depends | Commit |
|---|---|---|---|---|---|---|---|
| S4-T01 | pm-review --recover-request-id | CLI forwards recovery id; valid correlated reply records approval; uncorrelated records none | PARTIAL | reports/2026-10-30-pm-review-request-recovery.md: focused test PASS; local commit only, no GPT-PM approval or push recorded | assistant | | 8a044ee |
| S4-T02 | status prints exact artifact requirements | af_cli.py status lists file names, Sprint stamping line, location (BACKLOG open 1) | NOT_STARTED | BACKLOG open item 1 | assistant | | |
| S4-T03 | Live PM Bridge exercise | review.js dump-only with live review; phase-8 push via pre-push hook with genuine approval (BACKLOG open 2) | NOT_STARTED | BACKLOG open item 2 | assistant | S4-T01 | |
| S4-T04 | Bundle or declare 13 unbundled skills | no dangling skill references on a clean machine (BACKLOG open 4) | NOT_STARTED | BACKLOG open item 4; round 8 follow-up in DECISION_LOG not evidenced as closed | assistant | | |
| S4-T05 | Normalize EOL of installed vs deploy files | installed and deploy/ line endings consistent (BACKLOG open 3, cosmetic) | NOT_STARTED | BACKLOG open item 3 | assistant | | |
