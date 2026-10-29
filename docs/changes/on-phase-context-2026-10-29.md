# Print phase instructions on activation

## Problem and acceptance

The `on` command printed activation confirmation only. The command contract asks the
caller to launch roles from an injected phase line, but that line was emitted only by
the Claude hook, leaving other CLI clients without the requested instructions.

Both new and resumed activation must print the existing canonical phase context,
including the phase, roles, skills and missing artifacts, without advancing phases
or requesting approval. Failed activation must retain its existing refusal behavior.

## Change

`tools/af_cli.py:cmd_on` calls the existing `af.hook.context_line` after successful
state creation or resumption. No phase rules or push-gate rules are changed.
This is a targeted CLI repair; generated deploy files are not edited.

## Provenance and verification

Pre-existing modifications to tools/af/core.py, tools/af/evidence.py,
tests/test_round5.py and untracked stateview/review artifacts belong to the
baseline; this change does not claim or stage them. No commit or push is included.
## Functional verification

Acceptance mapping:

- Fresh activation prints the canonical phase context and creates phase 1 state: covered by
  `test_fresh_on_prints_canonical_phase_context`.
- Resume prints context while retaining paused sprint phase and mode: covered by
  `test_resume_prints_context_for_retained_phase_and_mode`.
- Explicit mode is applied before context output: covered by
  `test_explicit_mode_prints_context_after_applying_mode`.
- Refusal prints no context and neither creates nor activates state: covered by
  `test_refused_fresh_activation_prints_no_context_and_creates_no_state` and
  `test_refused_resume_prints_no_context_and_preserves_paused_state`.
- Activation does not advance phase or request PM approval: covered by
  `test_on_does_not_advance_phase_or_request_pm_approval`.

Focused command at HEAD `5ee25f96cfe9fe26c4ec98dd0e0673b661926350`:

```text
python -m unittest discover -s tests -p test_on_context.py -v
Ran 6 tests in 18.445s
OK
```

All six functional tests passed. An initial import-style invocation,
`python -m unittest tests.test_on_context -v`, was not a test result: it errored with
`ModuleNotFoundError: No module named 'afhelpers'`. The focused discovery command above
is the successful run. This functional run exercised CLI behavior with disposable
temporary Git repositories; it did not execute the broader suite or ERP runtime.

## End-to-end verification

The actual e2e-runner agent separately ran the CLI as subprocesses in a disposable
repository: `on --mode soft --title "Verification Sprint"`, `off`, then `on`.
Both activations printed canonical phase context. Sprint ID `14d37638470b`, phase 1
and soft mode were retained after resumption; the pre-push hook existed. The shell
exercise returned exit code 0. Temporary repository:
`D:\Temp\af-cli-on-2ea21c1ac92440cb89638b8567371772`.

The same agent ran `python D:/Repo/Agentic_Framework/tools/af_cli.py on` from
`D:\Repo\ERP_MCP`, at ERP HEAD `9454d904d60d371920608088cb326b688895f0cf`.
It returned exit code 0 with this output:

```text
Installed D:\Repo\ERP_MCP\.git\hooks\pre-push
Framework ON: resumed at phase 1 (hard) in D:\Repo\ERP_MCP
[Agentic_Framework SDLC] sprint 'Sprint' (id beea27520b33; every phase artifact must contain the line `Sprint: <id>`) phase 1 Discovery. Missing exit artifacts: requirements.md. Launch as real agents: business-analyst. Skills: requirements-elicitation. Advance with af_cli.py next; never self-approve phase 8.
```

Activation rewrites state timestamps and the framework-owned hook; the identity
and phase are retained. No phase advancement or PM review was requested.
The main session launched the actual business-analyst role for a bounded read-only
phase-1 handoff; that agent confirmed state and supplied requirement candidates.
It did not implement ERP features or create requirements.md. Full ERP Phase 2
delivery is outside this CLI-repair acceptance scope.

## Independent review and limits

After functional and end-to-end verification, a separate code-reviewer agent
reviewed the scoped CLI diff and nearest contracts read-only. Verdict: no
BLOCKER or MAJOR findings. It inspected code and inherited test evidence without
rerunning tests. Executing roles were functional-test-reviewer, e2e-runner,
business-analyst and code-reviewer, using the configured gpt-6-luna role profiles
with low reasoning effort.

The framework revision remained `5ee25f96cfe9fe26c4ec98dd0e0673b661926350`;
verification covered the working-tree patch, not a new committed revision.
No full framework suite, production write, push, PR or PM approval was performed.
The missing ERP requirements artifact remains future phase work; it is not an
activation defect. No remaining acceptance item for this bounded repair is open.
