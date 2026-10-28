# Backlog

## Open from GPT-PM review round 4 (head b9b4fe1, verdict MAJOR, 2 MAJOR)
1. Structured verification evidence. `verify-evidence.md` is checked only for the headings "## Test evidence" and "## NOT_RUN"; the reviewer wants a machine-readable contract (test status, required-check coverage, NOT_RUN dispositions, blocking-finding status) validated before PM Bridge is called. The PM reviewer stays responsible for judging sufficiency.
2. Artifact provenance. Freshness is the file mtime against `started_epoch`; the reviewer wants artifacts bound to a sprint id plus HEAD or content digest, verified at each phase transition, and explicit migration of legacy states (today a state without `started_epoch` keeps the existence-only check).
3. Verify that the recorded `diff_sha256`/`evidence_sha256` correspond to the input PM Bridge actually reviewed (`reviewInputHash`).
