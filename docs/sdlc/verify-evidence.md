# Verify evidence - Agentic_Framework

Machine-readable evidence: `docs/sdlc/verify-evidence.json` (validated by tools/af/evidence.py before a review is sent).

## Test evidence
Tested head 75ee95ba2996c5fbda483042d53f5b9304467575: `python -m unittest discover -s tests -v` = 338 tests, 337 OK, 0 failed, 0 errors, 1 self-skip (guard that skips when the real home already has an install manifest), 1129 s, run by the functional-test-reviewer agent on exactly this tree.

## History of the review
- Round 1 (head 9befa56): MAJOR x3, MINOR x2 - remediated (change 0005).
- Round 2 (7728951): MAJOR x2 - remediated (change 0006).
- Round 3 (4dcd4ba): APPROVE.
- Root commit 20c0098 reviewed separately: MAJOR x4, MINOR x2 - remediated (change 0007).
- Round 5 (5ee25f9): MAJOR - zero-pass runs accepted as evidence; remediated (change 0011).
- Round 6 (28b6830): MINOR - stale Markdown summary only; corrected in the following commit.
- Round 4 (b9b4fe1): MAJOR x2 left open (heading-only evidence, mtime freshness) plus input-hash correspondence - closed by this change set (change 0009): structured evidence, sprint-bound artifacts with digests, pre-computed prompt hash comparison.

## NOT_RUN
See the not_run list in verify-evidence.json (real PM Bridge dump mode, real schtasks/registry, installs into real homes, phase-8 push through the pre-push hook with a genuine approval, mutation checks).

## Known gaps
- Approval files are guarded by tooling and digests, not cryptography.
- Text-based push detection is best effort; the git pre-push hook is the boundary.
- `status` does not yet print the exact artifact requirements (backlog item 1).

## Curated agents change (change 0012, remediation of round 7)
- Earlier complete run `full15.log`: 355 tests, 9 failures (7 outdated expectations, 2 forbidden wording); all fixed.
- Focused re-run after those fixes: `test_curated`, `test_deploy`, `test_deploy_imported` = 41/41 (`sub17.log`); after round 7 remediation five affected files = 77 tests, 76 OK, 1 self-skip (`sub19.log`).
- Round 7 remediation (unresolved skill references, reporting-analyst state authority, installer warning) is covered by the focused run recorded in `verify-evidence.json`, which stays authoritative.
- NOT_RUN: complete suite on the final tree (operator rule: no complete re-runs after small fixes).
