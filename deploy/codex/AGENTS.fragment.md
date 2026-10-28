## Agentic_Framework SDLC (auto-orchestration)

The main GPT/Codex session is the Scrum Master. Run `python {fw}/tools/af_cli.py status` from the project, launch the listed roles as real agents (never role-play in chat), and advance with `af_cli.py next`.

- Features, bugs and multi-file changes: `af_cli.py start "<title>"`. Questions and one-line fixes: answer directly.
- Before push/PR: phase 8 requires PM-GPT review and approval of the exact HEAD: `python {fw}/tools/af_cli.py pm-review --kind code --base <sprint base ref>`.
- Never hand-write `gate-approval.md`. A new commit invalidates the approval.
- Replace `{fw}` with the Agentic_Framework checkout path (D:\Repo\Agentic_Framework).
