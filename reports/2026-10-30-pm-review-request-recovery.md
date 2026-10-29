# PM review correlated-reply recovery

## Scope

Add an explicit `--recover-request-id` option to `af_cli.py pm-review`. It forwards a durable
PM Bridge request identifier to the existing review command so an interrupted caller can retrieve
the correlated reply without creating a duplicate review. The normal AF review validation remains
responsible for correlation, verdict parsing, input hash checks, and writing approval artifacts.

## Change

- `tools/af_cli.py` accepts the optional recovery identifier and passes it to the review client.
- `tools/af/pm_review.py` carries the identifier to `review.js` only when supplied.
- `tests/test_pm_review.py` covers the CLI forwarding path, a valid correlated recovery that records
  approval and verifies, and an uncorrelated reply that records no approval.

## Verification evidence

The authorized `functional-test-reviewer` ran this focused test against the implementation:

```text
python tests/test_pm_review.py Request.test_cli_pm_review_recovery_forwards_id_and_records_only_valid_correlated_approval
```

Result: PASS, 1 test, exit code 0 (28.973 seconds). No full suite, CI, or GitHub Actions run is
claimed by this record.

## Delivery state

- Owner: Codex.
- Local commit: to be recorded in the commit that includes this change record.
- Push: not performed. The operator explicitly prohibited CI; a normal push is withheld until the
  repository's push-trigger behavior can be established without starting CI.
- Existing modifications to `docs/sdlc/.pm-review/approval.json` and
  `docs/sdlc/gate-approval.md`, plus unrelated untracked worktree/review artifacts, are excluded
  from this change.

## Acceptance

The implementation is accepted for local task completion when the CLI forwards the exact recovery
ID, a correlated valid reply follows the existing approval path, and an uncorrelated reply cannot
create approval files. The focused test above covers these conditions. This change does not itself
grant an approval or change the required exact-head review contract.
