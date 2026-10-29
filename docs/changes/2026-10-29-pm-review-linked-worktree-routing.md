# PM review routing from linked worktrees

- Added `pm-review --review-cwd` to route PM Bridge through the registered primary checkout while reviewing a candidate in a linked worktree.
- AF refuses the route unless candidate and routing checkout resolve to the same Git common directory.
- The review command now passes the candidate's exact HEAD to `review.js`, so routing and diff identity remain separate and explicit.
- Focused verification: `functional-test-reviewer` ran `python -m unittest discover -s tests -p test_pm_review.py` at pre-commit worktree HEAD `164d300e487c2165b7b355e0e9322b0e31acdfd3`; 29 tests passed, exit 0. ResourceWarning traces from `tools/af/core.py:98` were present without test failures.
