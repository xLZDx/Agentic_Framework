# Change 0002 - import agents and skills, /af toggle, push-gate fix, installer

What changed
- Imported 36 agents and 8 skills from the operator's agents-skills-repo into core/ (42 agents, 16 skills bundled). core/policies/autonomous-completion.md is a preference text, not an agent, and is not deployed.
- deploy.py: parses inline `tools: [..]` lists, ignores source-only keys, generates skill `af` (Claude, user-invoked only) and prompt `af.md` (Codex) from core/commands/af.md.
- af_cli.py: new `on` and `off` commands (off pauses: no injection, no push gate, state kept).
- hook.py: the push gate now tokenises the shell command (`is_push_command`) instead of matching the substring "push".
- tools/af_install.py: opt-in installer for ~/.claude and ~/.codex with dry-run, settings backup, idempotent hook merge, manifest-based uninstall.

Why: one framework for Claude and GPT with a switch, the operator's full roster inside it, and a push gate that does not block unrelated git commands (found by the first test run: 3 of 93 tests failed).

Affected contracts: framework.json bundled lists; deploy output layout (adds skills/af, prompts/af.md); CLI surface (on, off).

Also in this change: tools/af_autostart.py (Windows logon task and VS Code folder-open task that run deploy plus idempotent install and log to ~/.claude/af-autostart.log; never enables the framework in a project), and implementation-engineer added to the bundled agents (43) because phase 6 names it.

Verification state (agent functional-test-reviewer, python -m unittest discover -s tests -v, head = parent of this commit plus working tree): first run 93 tests, 90 passed, 3 failed on the old push regex. Extended suite after fixes: 161 tests, 161 OK, 0 failed, 0 skipped, 288 s.
NOT_RUN by design: real schtasks registration (argv only checked) and installation into the real ~/.claude and ~/.codex.
Known gap: installed files are LF while deploy/ files are CRLF on Windows (cosmetic, no test).

Not done in this commit: PM-GPT review of this repository.
