# 0017 - bound the evidence section of the review packet

Sprint: framework-maintenance

## What changed
- `tools/af/pm_review.py`: `build_packet()` now caps the embedded evidence files at `MAX_EVIDENCE_CHARS_PER_FILE` (12,000) and `MAX_EVIDENCE_CHARS_TOTAL` (80,000) characters. Each file still carries its full `sha256`, and a truncated file carries an explicit marker with the omitted character count and its absolute path. The diff and the task/base/head metadata are never truncated.
- `tests/test_pm_review.py`: `test_packet_bounds_evidence_and_keeps_digests`.

## Why
The PM transport converts a payload above roughly 114k characters into a `Pasted text` attachment. In this environment the reviewer cannot read that attachment, so a 357k-character PDCC packet produced "файл недоступен" instead of a verdict and blocked the review. Bounding the evidence keeps the request inline (14,288 characters in the reproduced PDCC case) while keeping the reviewed delta, the exact head and every evidence digest intact.

## Limits
- Truncation is visible, so a reviewer can demand the full file; the marker names the path and the digest.
- The diff itself is never truncated, so code acceptance is unaffected.
- NOT_RUN: complete framework suite, GitHub CI.

## Round 2 (PM MAJOR-01, request 71c4b513-f761-408b-b334-9dbeba398392)
- Metadata is no longer inside the content budget: every existing evidence file always emits its name, sha256, original character count and an explicit status: FULL | TRUNCATED | OMITTED line. Only the embedded body consumes the 11,000-character content budget, so budget exhaustion can no longer hide an evidence source.
- Tests: 	est_packet_bounds_evidence_and_keeps_digests, 	est_packet_keeps_evidence_identity_when_budget_is_exhausted (backlog and design names, digests and OMITTED status retained after the budget is spent), 	est_packet_does_not_invent_metadata_for_missing_evidence.
