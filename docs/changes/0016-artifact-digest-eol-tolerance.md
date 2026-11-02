# 0016 - artifact digests keep a reproducible, verified connection to the artifact

Sprint: framework-maintenance

## What changed
- `tools/af/pm_review.py`: new `_canonical_sha()` (CRLF/LF-normalised digest) and `_canonical_artifact_digests()`. `request()` now records `artifacts_canonical` next to the existing `artifacts` snapshot.
- `_artifact_matches()` replaces the previous strict `digest in blob-variants` test and is used by both approval validation and the request-time "artifacts are committed" check. A recorded digest is accepted when
  1. Git can reproduce it for the approved revision (blob or its LF/CRLF serialisations), or
  2. it hashes the artifact that is on disk **and** that artifact equals the committed blob of the revision under CRLF/LF normalisation (and equals the recorded canonical digest when the approval carries one).
  Any other digest is refused; nothing is accepted because of content equivalence alone.
- `tests/test_pm_review.py`: `test_artifact_digest_requires_reproducible_provenance` covers the reviewer's matrix — exact blob digest, LF/CRLF variant, legacy mixed-EOL checkout whose digest hashes the artifact, arbitrary digest refused, wrong canonical refused, changed artifact refused, missing artifact refused.

## Why
A Windows checkout can leave a tracked document with mixed line endings, so its working-copy digest is not reproducible from any Git blob of the revision. PDCC hit exactly this (`docs/sdlc/change-records/2026-10-30-src01-t09-fixture-certification-harness.md`): 44 recorded artifacts validated and this one aborted an otherwise valid approval chain.

An earlier revision of this fix compared the working copy with the blob and ignored the recorded digest; the PM review rejected that (MAJOR-01, request `993fd4c2-3bea-4214-88c4-1e4cc9864556`) because a corrupted digest would then be accepted as provenance. The current implementation keeps the digest binding: it must hash the artifact on disk or be reproducible from the revision itself.

## Verification
- Focused: `python -m unittest discover -s tests -p test_pm_review.py -k artifact_digest_requires` = 1 passed.
- Full affected-file rerun at `5568d16ce2daf0839c66ef38545346d270c878e2`: 57 tests, 57 passed, 0 failed, 0 errors, 0 skipped, `Ran 57 tests in 1132.227s`, `OK` (log `af-pm-review-5568d16-unittest.log`, sha256 68dd2e95a565e1c8a0ed42937065a1cdf24f7c219e8114752d0c6f1c47674935).
- NOT_RUN: complete framework suite, GitHub CI.
