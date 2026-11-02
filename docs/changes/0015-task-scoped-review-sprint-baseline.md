# 0015 - task-scoped review can root at the committed sprint baseline

Sprint: framework-maintenance

## What changed
- `tools/af/pm_review.py`: task-scoped reviews no longer require a prior official approval at `--task-base`. When no approval covers that base, the review may root at the configured sprint baseline only if `_trusted_sprint_start()` resolves the sprint start HEAD from `docs/sdlc/state.json` **as committed at the candidate HEAD** and it matches both the working state and `--base` (`base_anchor = sprint-base`). Incremental reviews keep the previous behavior (`base_anchor = approval`).
- `tools/af/pm_review.py`: `request()` now refuses a code review whose acceptance artifacts (`verify-evidence.json`, phase artifacts, `state.json` when present) are not present in the committed HEAD, so a reviewed head always carries its own evidence.
- `tools/af/pm_review.py`: `verify()` and approval-chain validation re-check the trusted sprint baseline for task-scoped approvals, so a forged or edited `state.json` cannot re-anchor a chain.
- `tests/test_pm_review.py`: scoped-review cases extended (sprint-base root without prior approval, refusal for caller-controlled tracking refs, conflicting candidate history, linked-worktree prior approval, exact task scope).
- `docs/sdlc/verify-evidence.json` and `docs/sdlc/verify-evidence.md`: exact-HEAD evidence for candidate `e8b3baaeb853b292c74331d06070b2f93c0b8f19`.
- `docs/sdlc/gate-approval.md` and `docs/sdlc/.pm-review/approval.json`: the tool-written `PMG-20261102-9c21daff` receipt that was produced after commit `9c21daff` and was still uncommitted.

## Why
Task-scoped reviews could only chain from an existing official approval, so the first task of a sprint could not be reviewed against its own diff when the sprint had no approval yet, and a hand-edited or synthetic task-acceptance record could redirect the review range. Rooting the chain at the committed sprint baseline keeps the exact task diff visible to GPT-PM while binding the anchor to committed project state.

## Verification
- Round-2 exact HEAD `6c139cea179d6290cf27ca6546ccde33a65c32b6`: `python -m unittest discover -s tests -p test_pm_review.py -v` = 56 tests, 56 passed, 0 failed, 0 errors, 0 skipped, `Ran 56 tests in 836.660s`, `OK` (log `af-pm-review-6c139ce-unittest.log`, sha256 `A95ED03D4A7CF0BFD746715D3E219DAD7B393E895B4DADDFD321C726A242DBED`).
- `functional-test-reviewer` exact-HEAD rerun on the clean candidate worktree: `python -m unittest discover -s tests -p test_pm_review.py -v` = 54 tests, 54 passed, 0 failed, 0 errors, 0 skipped, `Ran 54 tests in 939.462s`, `OK` (log `af-pm-review-e8b3baa-unittest.log`, sha256 `4AD6AEA751FEBFD46FC0759CB5CD3D4233EA67D75311054E6DF0479E97F6F944`). The earlier interrupted attempt produced no result and is not claimed.
- Source/test diff identity: `git diff 9c21daff9d6b3d330dc95b7bab9c69045b627ddd e8b3baaeb853b292c74331d06070b2f93c0b8f19 -- tools/af/pm_review.py tests/test_pm_review.py`, 25,655 bytes, sha256 `d0c25afe48ea12dd25e36d96241538729589b04c15e600790250771bec1564b3`.
- Read-only `python-reviewer` and `security-reviewer` passes on that diff: no actionable finding.
- NOT_RUN: complete framework suite on this tree, GitHub CI, push (pending the official `af_cli.py pm-review` approval bound to this HEAD).


## Round 2 hardening (PM review MAJOR-01, request `82014858-e5aa-47bc-8004-853225d65b86`)
- Finding: the baseline came from the mutable `docs/sdlc/state.json` at the candidate HEAD, so a later commit could redefine `start_head` and shrink a first-task review range.
- Fix: `_trusted_sprint_start()` now resolves the sprint via `_sprint_creation()` — the earliest commit that introduced the sprint id into the committed `state.json` (`git log --reverse -S<sprint_id> <head> -- docs/sdlc/state.json`). The declared `start_head` must equal the creation record's `start_head`, that baseline must be an ancestor of the creation commit, and the creation commit must be an ancestor of the reviewed HEAD. `_state_at()` reads the committed state at any revision.
- Regression tests: `test_task_scoped_root_refuses_redefined_sprint_start` (baseline rewritten and committed, then used as `--base`: refused) and `test_task_scoped_root_refuses_baseline_absent_from_creation_record` (baseline declared only after sprint creation: refused).
