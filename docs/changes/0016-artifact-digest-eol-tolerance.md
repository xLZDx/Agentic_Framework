# 0016 - artifact digests tolerate the line-ending form of the record

Sprint: framework-maintenance

## What changed
- `tools/af/pm_review.py`: new `_artifact_matches()` replaces the strict `digest in git-blob-variants` test when validating a recorded approval. A digest that matches a committed blob variant is accepted as before; otherwise the artifact is accepted only when its current content equals the committed blob at that revision after CRLF/LF normalisation.
- `tests/test_pm_review.py`: `test_artifact_digest_tolerates_line_endings_only_when_blob_matches` — mixed-EOL record tolerated while the artifact equals the blob, refused as soon as the artifact changes.

## Why
A Windows checkout can leave a tracked document with mixed line endings. Its working-copy digest is then not reproducible from any Git blob of the same revision, so an otherwise valid approval chain becomes unverifiable and every later scoped review is refused. Observed on `docs/sdlc/change-records/2026-10-30-src01-t09-fixture-certification-harness.md` in PDCC: 44 recorded artifacts validated, this one aborted the chain.

The fallback does not weaken the binding: `pm-review` only runs on a clean tracked tree, so at approval time the artifact was exactly the committed blob of that revision. The comparison therefore still proves "the artifact is the one this head approved"; only the serialisation form of the recorded hash is tolerated.

## Verification
- Focused: `python -m unittest discover -s tests -p test_pm_review.py -k artifact_digest_tolerates` = 1 passed, 0 failed.
- Full affected-file rerun at `ca0825c4a1f1ce6ba14ffa70b2edf232c6379047`: 57 tests, 57 passed, 0 failed, 0 errors, 0 skipped, `Ran 57 tests in 1022.986s`, `OK` (log `af-pm-review-ca0825c-unittest.log`, sha256 `F8FEA3C79DBE26906831733CB7FC042D793D779C84B8E6CE697A677282D18CE4`).
- NOT_RUN: complete framework suite, GitHub CI.
