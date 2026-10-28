# Change 0006 - remediation of the second PM-GPT review

Findings (GPT-PM verdict MAJOR on head 7728951; the five round-1 findings were confirmed fixed): (1) `/af on` reported success while the authoritative git pre-push gate was absent when a foreign pre-push hook existed; (2) the installer recorded a pre-existing identical foreign file as framework-owned, so uninstall would delete it.

What changed
- tools/af_cli.py: `_require_gate`; hard-mode `start`, `on` (new and resumed) and `mode hard` install the gate first and refuse activation otherwise (exit 1, state untouched, hint to chain the hook or use --mode soft). Soft mode only warns.
- tools/af_install.py: an identical pre-existing file is recorded as owned only if it was in the previous manifest.
- tests/test_hardening.py: 13 new tests (pre-push contract, identical-foreign-file installer).

Verification: full suite 205 tests, 204 OK, 1 self-skip (see docs/sdlc/verify-evidence.md). NOT_RUN: real schtasks/registry, install into the real homes, a phase-8 push through the pre-push hook.
