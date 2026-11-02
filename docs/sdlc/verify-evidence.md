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

## Task-scoped PM review routing (2026-11-02)
- Code candidate: `9f27fcd4745aff7310679d948ddd8eca8ff7e674`; test command: `python -m unittest discover -s tests -p test_pm_review.py`; exact-HEAD result: 46 passed, 0 failed, 0 errors, 0 skipped.
- The run emitted repeated `ResourceWarning` messages from `tools/af/core.py:98` for fixture `docs/sdlc` files; the run still exited 0.
- Earlier runs on the same focused set exposed two fixture failures. The fixtures created phase artifacts without committing them, so historical approval validation correctly refused artifact hashes absent from the reviewed HEAD. The fixtures now commit their baseline artifacts and exercise a prior approved HEAD before the task-scoped approval.
- Final Python review: no remaining findings. The reviewer runtime did not expose its model ID or reasoning effort.
- Test-role runtime did not expose its model ID or reasoning effort; no model or effort is inferred here.
- `CI`: `NOT_RUN` because the operator prohibited CI. A Python reviewer accidentally invoked `git diff --check`; it emitted no output and made no changes.

## Task-scoped review provenance remediation (2026-11-02)
- GPT-PM review of the earlier task-scoped route returned `MAJOR` at `6caf6fdf65e19208e394da30d0f1d2b3325c2aef`: committed `task_acceptance_records` were caller-controlled and could not prove predecessor acceptance.
- Remediation commit: `69d2d32c4d47c7cb181b005ab89893f527e34b61`. The route no longer treats those records as authority. Task identifiers are labels; task-scoped review requires a valid official PM approval at the exact task base and verifies the full approval chain through current HEAD.
- Internal review: Python reviewer reported no concrete findings. Security reviewer confirmed task labels and task-head records are not acceptance proof and the exact-base official approval remains the trust anchor.
- Focused test command: `python -m unittest discover -s tests -p test_pm_review.py`; final result: 49 passed, 0 failed, 0 errors, 0 skipped, 350.678s; exit 0; run by `functional-test-reviewer`.
- The test ran with repository HEAD `6caf6fdf65e19208e394da30d0f1d2b3325c2aef` and working diff SHA-256 `c788f0b444a99d53796e50e7006395fdcc7da525645088ba30b1b51bbce421fe`. That exact patch SHA matched the committed diff `6caf6fdf65e19208e394da30d0f1d2b3325c2aef..69d2d32c4d47c7cb181b005ab89893f527e34b61`.
- The first run on a preceding test-fixture revision produced 48 passed / 1 failed because the test omitted exact task-head metadata and hit an earlier refusal. The fixture was corrected; the final run above passed. Repeated `ResourceWarning`s from `tools/af/core.py:98` remained non-fatal.
- The initial GPT-PM retry at HEAD `69d2d32c4d47c7cb181b005ab89893f527e34b61` was refused before dispatch because this evidence file still referenced the prior tested head; evidence is now updated. No new GPT-PM decision has been received yet.
- `CI`: `NOT_RUN`; operator prohibited CI.

## Curated agents change (change 0012, remediation of round 7)
- Earlier complete run `full15.log`: 355 tests, 9 failures (7 outdated expectations, 2 forbidden wording); all fixed.
- Focused re-run after those fixes: `test_curated`, `test_deploy`, `test_deploy_imported` = 41/41 (`sub17.log`); after round 7 remediation five affected files = 77 tests, 76 OK, 1 self-skip (`sub19.log`).
- Round 7 remediation (unresolved skill references, reporting-analyst state authority, installer warning) is covered by the focused run recorded in `verify-evidence.json`, which stays authoritative.
- NOT_RUN: complete suite on the final tree (operator rule: no complete re-runs after small fixes).


## PM review routing change (change 0015, candidate head e8b3baa)
- Scope: `tools/af/pm_review.py` and `tests/test_pm_review.py`. A task-scoped review may now root at the committed sprint baseline when that base equals the sprint start HEAD recorded in the committed `docs/sdlc/state.json` and no prior approval exists; incremental reviews keep anchoring at the exact HEAD of the validated prior approval.
- Diff identity: `git --no-pager diff 9c21daff9d6b3d330dc95b7bab9c69045b627ddd e8b3baaeb853b292c74331d06070b2f93c0b8f19 -- tools/af/pm_review.py tests/test_pm_review.py` = 25,655 bytes, sha256 `d0c25afe48ea12dd25e36d96241538729589b04c15e600790250771bec1564b3`, reproduced in this session.
- Exact-HEAD functional evidence: `python -m unittest discover -s tests -p test_pm_review.py -v` in the clean candidate worktree at `e8b3baaeb853b292c74331d06070b2f93c0b8f19`: Ran 54 tests in 939.462 s, `OK` (54 passed, 0 failed, 0 errors, 0 skipped). Log `C:\Users\koros\AppData\Local\Temp\af-pm-review-e8b3baa-unittest.log`, sha256 `4AD6AEA751FEBFD46FC0759CB5CD3D4233EA67D75311054E6DF0479E97F6F944`; only non-fatal `ResourceWarning` from `tools/af/core.py:98`. This was the single authorized exact-HEAD rerun; the earlier interrupted attempt produced no result and stays `NOT_VERIFIED`; the earlier role run at parent `9c21daf` plus the identical diff (54/54) is historical, not exact-HEAD evidence.
- Read-only `python-reviewer` and `security-reviewer` passes on the same diff found no actionable finding.
- Prior approval `PMG-20261102-9c21daff` is bound to head `9c21daff9d6b3d330dc95b7bab9c69045b627ddd` only; it does not approve `e8b3baa`. The official PM review at the candidate head is requested separately through `af_cli.py pm-review`.
- NOT_RUN: complete framework suite on this tree, GitHub CI, push (pending the official PM review bound to this HEAD).
