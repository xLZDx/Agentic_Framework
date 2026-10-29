# PM-GPT code review request
Project root: D:\Repo\Agentic_Framework
Reviewed range: cf73562...4f5fa0e6404c61648a00c670fb6b91153b283a88
Exact HEAD under review: 4f5fa0e6404c61648a00c670fb6b91153b283a88
Reply format: first line `VERDICT: APPROVE|MINOR|MAJOR|BLOCKER`, then one finding per line as `SEVERITY | basis | claim | evidence | required change`.
Approve only if the exact head is safe to push. Verify claims against the diff.

## Evidence file: verify-evidence.json (sha256 b806343f5126734e8aafcc65493b9e607ed3795af2e6926ca153b626dbdb8015)
{
  "tested_head": "2c18fd6f80b2a000176ddf2f6978b4ff9627ad4b",
  "runs": [
    {
      "command": "python -m unittest -v test_curated test_deploy test_deploy_imported (cwd tests)",
      "total": 41,
      "passed": 41,
      "failed": 0,
      "errors": 0,
      "skipped": 0,
      "log": "sub17.log (3 s)"
    }
  ],
  "not_run": [
    {
      "item": "complete suite on the final tree",
      "reason": "last complete run full15.log (355 tests) had 9 failures, 7 outdated expectations and 2 forbidden-wording hits, all fixed; per operator instruction only the three affected test files were re-run, the other files were not re-run after the fixes"
    },
    {
      "item": "real PM Bridge review.js dump-only mode with a live review",
      "reason": "tests use a fake review.js; the real one was only exercised manually (two identical prompt dumps)"
    },
    {
      "item": "real schtasks and registry operations",
      "reason": "tests assert argv only; no real system state is changed by tests"
    },
    {
      "item": "install into the real ~/.claude and ~/.codex from tests",
      "reason": "tests use temp homes; NeverTouchesRealHomes self-skips because a real install exists"
    },
    {
      "item": "phase-8 git push through the pre-push hook with a genuine approval",
      "reason": "covered only by gate_decision and fake-approval tests"
    },
    {
      "item": "mutation checks",
      "reason": "not run by operator policy"
    }
  ],
  "findings": {
    "open_blocker": 0,
    "open_major": 0
  },
  "reviewers": [
    {
      "role": "functional-test-reviewer",
      "model": "sonnet",
      "effort": "medium",
      "verdict": "affected files 41/41 green after fixes; full15 failures all fixed; no open product bugs"
    }
  ]
}


## Evidence file: verify-evidence.md (sha256 745af71b727f80617400f308e6f04d8cec1731bf43058981d992486b78cec091)
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
