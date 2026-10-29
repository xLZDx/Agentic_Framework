# 0014 - push/PR block is opt-in

Sprint: framework-maintenance

## What changed
- `tools/af/hook.py`: new `gate_enabled()`; `gate_decision()` returns None while the gate is disabled. Enable with `push_gate.enabled: true` in `core/orchestration/phase-map.json` or `AF_PUSH_GATE=on`.
- `tools/af_cli.py`: `_require_gate()` does not install the git pre-push hook and never fails activation while the gate is disabled. `install-githook` and `gate-check` remain available explicitly.
- `core/orchestration/phase-map.json`: `push_gate.enabled` is `false` (deploy regenerated).
- Tests: `tests/afhelpers.py` enables the gate for the existing gate tests; new `tests/test_gate_default.py` (17 tests) covers the default-off behavior and the opt-in path.

## Why
Operator decision: the GPT-PM review is the only approval needed; the framework's own push/PR block is a secondary blocker and is off by default. The PM-GPT review step, `pm-review`, and the phase flow are unchanged.

## Verification
- `functional-test-reviewer` ran 18 affected files: 392 tests, 391 OK, 1 self-skip, 0 failures (`sub20.log`).
- NOT_RUN: complete suite (operator rule), live PM Bridge, real home installs.
