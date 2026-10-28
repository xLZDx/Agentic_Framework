# Change 0007 - remediation of the GPT-PM review of the root commit

Findings (verdict MAJOR on 20c0098, 4 MAJOR + 2 MINOR; all verified valid against the current code): incomplete evidence accepted; stale artifacts reused by a new sprint; `next --force` bypassed the phase-8 approval; review base not validated or bound to the result; per-agent effort dropped by deploy; leftover references to the excluded state store.

What changed
- tools/af/pm_review.py: `_preflight` (evidence contract, base resolution/ancestry/coverage, non-empty range); approval records base_sha, diff_sha256, evidence_sha256.
- tools/af_cli.py: `next --force` skips only missing artifacts, never the PM approval.
- tools/af/core.py: `new_sprint_state` stores started_epoch and start_head; artifacts count only if written after the sprint start.
- tools/af/deploy.py: per-agent effort override within policy (claude low/medium/high, codex low/medium).
- core/agents/reporting-analyst.md, core/skills/sdlc-metrics, core/skills/sprint-ceremonies: state authority text now points to docs/sdlc/state.json.
- tests: 38 new tests in tests/test_round4.py; 24 existing tests adapted.

Verification: full suite 243 tests, 242 OK, 1 self-skip (docs/sdlc/verify-evidence.md). NOT_RUN: real schtasks/registry, install into real homes, a phase-8 push through the pre-push hook, real PM Bridge in tests.
Note: the previous approval PMG-20261028-4dcd4ba9 applied to head 4dcd4ba and is invalidated by this commit.
