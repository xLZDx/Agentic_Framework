# Change 0008 - outcome of the fourth PM-GPT review round, backlog

Round 4 (range 4dcd4ba...b9b4fe1) confirmed the --force, effort, state-authority fixes and part of the base validation, and kept two MAJOR open: heading-only evidence preflight and mtime-based artifact freshness.
Decision: these are design limits of an internal gate, not regressions of the remediation, and this is the fourth fix round on that mechanism. They are recorded in core/BACKLOG.md instead of another fix round, pending the operator's choice. No code changed. The last approved head remains 4dcd4ba (approval PMG-20261028-4dcd4ba9); b9b4fe1 is NOT approved.
Verification: documentation only.
