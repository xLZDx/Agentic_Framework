# Change 0005 - remediation of the first PM-GPT review

Findings (GPT-PM verdict MAJOR on head 9befa56): push-gate bypass through wrappers and nested shells; installer overwrote or deleted user-edited files; stale hook path after moving the checkout; IndexError on bare `gh pr`; tracked bytecode.

What changed
- tools/af/hook.py: quote-aware tokeniser, wrapper and nested-shell handling, safe `gh` parsing. Text detection is best effort by design.
- tools/af_cli.py: `on` installs the git pre-push hook (the authoritative boundary for Claude, Codex and humans).
- tools/af_install.py: sha256 manifest, edited files kept (MODIFIED/KEPT), legacy manifest migration, stale framework hooks replaced with exactly one per event, uninstall keeps the manifest while kept files remain.
- tools/af/__pycache__ removed from the index.
- tests/test_hardening.py (28 tests) plus updates to test_af_install.py; docs/sdlc/verify-evidence.md updated for the verification round.

Verification: see docs/sdlc/verify-evidence.md (full suite 192 tests, 190 OK, 1 stale test fixed, 1 self-skip; then 66 tests in the three affected files, 65 OK, 1 self-skip). NOT_RUN: real schtasks/registry, install into the real homes, a phase-8 push through the pre-push hook.
Next: verification round with GPT-PM on this head; separate review of the root commit 20c0098.
