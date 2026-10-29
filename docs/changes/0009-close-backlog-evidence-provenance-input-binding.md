# Change 0009 - close the review backlog

Closes the three items opened by GPT-PM round 4 (see core/BACKLOG.md).

What changed
- tools/af/evidence.py (new): structured verification evidence validation. Rejects red or empty runs, contradictory counts, missing not_run reasons, open blocker/major findings, a tested head that is not an ancestor, and code changed after the tested head (only docs/ and the three core logs may change).
- tools/af/core.py, tools/af_cli.py, tools/af/hook.py: sprint_id; artifacts must contain it; `migrate` for legacy states; artifact digests in history; sprint id shown by status and the hook context line; friendly error outside a git repository.
- tools/af/pm_review.py: evidence and artifact preflight; pre-computed review.js prompt and `reviewInputHash` comparison; byte-exact (LF, raw bytes) packet and prompt handling; approval records expected_input_hash, diff digests, evidence digest, sprint id and artifact digests; verify() fails when an artifact changed after approval; gate-approval.md carries `Sprint: <id>`.
- tools/af/deploy.py: Codex prompt no longer carries a literal `$ARGUMENTS` line.
- tests: tests/test_round5.py, tests/test_nongit.py, adapted existing tests.

Verification (agent functional-test-reviewer, `python -m unittest discover -s tests -v`, tree identical to this commit): 323 tests, 322 OK, 0 failed, 0 errors, 1 self-skip, 799 s. Three product bugs found by the agent during the work (approval file lacked the sprint stamp so phase 8 could never advance; null evidence fields accepted; CRLF would break the prompt hash on Windows) were fixed before this run.
NOT_RUN: real PM Bridge review.js dump mode, real schtasks/registry, installs into real homes, a phase-8 push through the pre-push hook with a genuine approval.
Also done outside the repository (operator-approved): user TEMP/TMP moved to C:\Users\koros\AppData\Local\Temp (rollback values in ~/.claude/af-temp-env-backup.json) and allow rules for the framework CLI added to ~/.codex/rules/default.rules to stop Codex permission prompts.
