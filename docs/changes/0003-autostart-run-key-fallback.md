# Change 0003 - autostart falls back to the per-user Run key

What changed: `tools/af_autostart.py register` tries the Windows Scheduled Task first; when `schtasks /SC ONLOGON` fails (it needs admin, observed "Access is denied" on this machine) it writes `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\AgenticFrameworkAutostart`. `unregister` and `status` handle both. tests/test_autostart.py covers the fallback with patched subprocess calls.

Why: the operator asked for the framework to start with Windows and VS Code without elevation.

Affected: tools/af_autostart.py, tests/test_autostart.py. Real machine state changed by running it: Run key present, VS Code task in D:\Repo\.vscode\tasks.json, framework installed in ~/.claude and ~/.codex (53 files written, 67 differing foreign files skipped, settings.json backup `settings.json.bak-af-20261028225744`).

Verification (agent functional-test-reviewer, `python -m unittest discover -s tests -v`): 165 tests, 164 OK, 0 failed, 1 skipped, 299 s. The skip is a guard that disables itself because the real home already has af-install-manifest.json. After the full run one assertion string in test_autostart.py was fixed (SyntaxWarning) and only that file was re-run: 19/19 OK.
NOT_RUN by design: real schtasks and registry operations inside tests. Known gap: LF installed vs CRLF deploy files (cosmetic).
Not done: PM-GPT review of this repository.
