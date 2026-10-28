# PM-GPT code review request
Project root: D:\Repo\Agentic_Framework
Reviewed range: 20c0098...9befa5682e1aab84f131f058c910b4f83d3df713
Exact HEAD under review: 9befa5682e1aab84f131f058c910b4f83d3df713
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
