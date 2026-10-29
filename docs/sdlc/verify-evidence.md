# Verify evidence - Agentic_Framework

Machine-readable evidence: `docs/sdlc/verify-evidence.json` (validated by tools/af/evidence.py before a review is sent).

## Test evidence
Tested head 2d6743dc6e0db7f9967a3c2b526a4884f088a4b3: `python -m unittest discover -s tests -v` = 323 tests, 322 OK, 0 failed, 0 errors, 1 self-skip (guard that skips when the real home already has an install manifest), 799 s, run by the functional-test-reviewer agent on exactly this tree.

## History of the review
- Round 1 (head 9befa56): MAJOR x3, MINOR x2 - remediated (change 0005).
- Round 2 (7728951): MAJOR x2 - remediated (change 0006).
- Round 3 (4dcd4ba): APPROVE.
- Root commit 20c0098 reviewed separately: MAJOR x4, MINOR x2 - remediated (change 0007).
- Round 4 (b9b4fe1): MAJOR x2 left open (heading-only evidence, mtime freshness) plus input-hash correspondence - closed by this change set (change 0009): structured evidence, sprint-bound artifacts with digests, pre-computed prompt hash comparison.

## NOT_RUN
See the not_run list in verify-evidence.json (real PM Bridge dump mode, real schtasks/registry, installs into real homes, phase-8 push through the pre-push hook with a genuine approval, mutation checks).

## Known gaps
- Approval files are guarded by tooling and digests, not cryptography.
- Text-based push detection is best effort; the git pre-push hook is the boundary.
- `status` does not yet print the exact artifact requirements (backlog item 1).
