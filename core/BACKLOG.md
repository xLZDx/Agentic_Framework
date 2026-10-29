# Backlog

## Closed (2026-10-29, change 0009)
1. Structured verification evidence: `docs/sdlc/verify-evidence.json` is validated by `tools/af/evidence.py` before any code review is sent (runs, counts, red runs, not_run reasons, open blocker/major, tested head ancestry and code-after-tested-head).
2. Artifact provenance: every sprint has a `sprint_id`; phase artifacts must contain it; legacy states need an explicit `af_cli.py migrate`; artifact digests are stored at each transition and re-checked by `verify`.
3. Review input binding: `pm-review` pre-computes the exact review.js prompt (dump-only mode) and rejects a result whose `reviewInputHash` differs.

## Open
1. `af_cli.py status` should print the exact artifact requirements (file names, the `Sprint: <id>` stamping line, where to write them) so an agent does not read the framework source and trigger permission prompts (operator report, Codex session of 2026-10-29).
2. Not exercised against the real PM Bridge: review.js dump-only mode with a live review; a phase-8 push through the pre-push hook with a genuine approval.
3. Installed files are LF while deploy/ files are CRLF on Windows (cosmetic).
