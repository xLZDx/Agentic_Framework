# 0011 - zero-pass evidence rejected, foreign STATE.md protected

Sprint: framework-maintenance

## What changed
- `tools/af/evidence.py`: every run must have `passed > 0` (skipped tests are not evidence); an empty `reviewers` list requires a non-blank `reviewers_waived_reason`; field types are checked strictly.
- `tools/af/core.py`: `state_view_name()` redirects the generated state view to `AF_STATE.md` when a `STATE.md` exists that does not carry the generated marker, so a project's own tracked file is never overwritten.
- `tools/af_cli.py` and `docs/changes/on-phase-context-2026-10-29.md`: `on` prints the canonical phase context (see that record).

## Why
- GPT-PM round 5 (MAJOR): a run with zero passing tests was accepted as evidence.
- The framework overwrote a tracked `docs/sdlc/STATE.md` in another project.

## Affected contracts
- `docs/sdlc/verify-evidence.json` schema (stricter), state view file name.

## Verification
- Tests by `functional-test-reviewer`: `tests/test_round5.py` (extended), `tests/test_stateview.py` (8 tests), `tests/test_on_context.py`.
- Full run `python -m unittest discover -s tests -v`: 338 tests, 337 OK, 1 skipped (self-skip when a real install exists), 0 failures.
- Not run: live PM Bridge dump mode, real schtasks, real home installs, real phase-8 push.
