# PM-GPT code review request
Project root: D:\Repo\Agentic_Framework
Reviewed range: 7728951...4dcd4ba9453c483b3c364900621ee7ffa5c1eef9
Exact HEAD under review: 4dcd4ba9453c483b3c364900621ee7ffa5c1eef9
Reply format: first line `VERDICT: APPROVE|MINOR|MAJOR|BLOCKER`, then one finding per line as `SEVERITY | basis | claim | evidence | required change`.
Approve only if the exact head is safe to push. Verify claims against the diff.

## Evidence file: verify-evidence.md
# Verify evidence - Agentic_Framework (first PM-GPT review)

Scope: the whole repository as pushed to origin/master (commits 20c0098, dc12906, 1689530). The reviewed diff range is 20c0098...HEAD (167 files; mostly imported agents/skills, generated deploy/, tests, installer, autostart, push-gate fix). The root commit 20c0098 (initial tools/af core, pm_review.py, hook.py, phase map, skills) is outside that range because git cannot diff against an empty base with `...`; it is reviewed separately with `review.js --commit 20c0098`.

## Test evidence (author: functional-test-reviewer agent, MEASURED)
- Command: `python -m unittest discover -s tests -v` from D:\Repo\Agentic_Framework.
- Run 1: 93 tests, 90 OK, 3 failed (push gate matched the word "push" in any git command) - fixed by tokenised `is_push_command`.
- Run 2: 161 tests, 160 OK, 1 failed (phase 6 role implementation-engineer not bundled) - fixed.
- Run 3: 161/161 OK. Run 4 (after autostart Run-key fallback): 165 tests, 164 OK, 0 failed, 1 self-skip (guard that disables itself when the real home already has the install manifest). 299 s.

## Remediation round (verification of the first PM-GPT review, MAJOR x3 + MINOR x2)
Reviewed range for this round: 9befa56...HEAD. Fixes: (1) push detection tokenises with quote awareness, handles wrappers (env/command/sudo/timeout/...), nested shells (sh -c, cmd /c, pwsh -Command), subshells and backticks; `gh pr` no longer raises; `/af on` installs the git pre-push hook as the authoritative boundary. (2) installer manifest records sha256 per file; user-edited files are never refreshed or removed (MODIFIED/KEPT); uninstall keeps the manifest for kept files. (3) stale framework hooks (moved checkout) are replaced, exactly one per event, unrelated hooks preserved. (4) bytecode no longer tracked.
Evidence (agent functional-test-reviewer, MEASURED): full suite 192 tests = 190 OK, 1 stale test of the old installer behaviour (fixed to assert the new behaviour), 1 self-skip, 697 s. Afterwards test_af_install + test_hardening + test_autostart: 66 tests, 65 OK, 0 failed, 1 self-skip, 188 s (includes the new uninstall-keeps-manifest test). The full suite was not re-run after the last one-line uninstall fix; the three affected files were.
Real-push coverage: against a local bare remote, `git push`, `env git push` and `sh -c 'git push'` are blocked at phase 1 by the pre-push hook and allowed after `off`.
Known limitation: push-command text detection is best-effort; the pre-push hook is the boundary. A push at phase 8+ with a valid approval through the pre-push hook is covered only by gate_decision tests.

## Remediation round 2 (GPT-PM round 2: 2 MAJOR, previous 5 findings confirmed fixed)
Reviewed range: 7728951...HEAD. Fixes: (1) hard mode `start`/`on`/`mode hard` install the git pre-push gate first and refuse activation when a foreign pre-push hook prevents it; soft mode only warns. (2) installer does not record a pre-existing byte-identical file as owned unless it was in the previous manifest, so uninstall never deletes it.
Evidence (agent functional-test-reviewer, MEASURED): full suite `python -m unittest discover -s tests -v`: 205 tests, 204 OK, 0 failed, 0 errors, 1 self-skip, 582 s. 13 tests added in tests/test_hardening.py (8 pre-push contract, 4 identical-foreign-file installer, 1 stale-hook rewrite).

## NOT_RUN
- Real `schtasks`/registry operations inside tests (argv-level checks only).
- No test installs into the real ~/.claude or ~/.codex.
- PM Bridge real `review.js` is never called by tests (fake script used).
- Mutation checks: not run by operator policy.

## Known gaps
- Approval files are guarded by tooling, not cryptography.
- Installed files are LF while deploy/ files are CRLF on Windows (cosmetic).
- Imported agents and skills (36 + 8) are copied unchanged from the operator's agents-skills-repo; they are not reviewed here beyond deploy-format validity.

## Reviewer consensus
No separate specialist reviewer round was run for this repository; the independent evidence is the test agent's findings above.
