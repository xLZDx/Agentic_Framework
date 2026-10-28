# Agentic_Framework - conventions

`D:\Repo\AGENTS.md` is the authoritative workspace workflow. This file adds only repository specifics.

- Edit `core/` only; regenerate `deploy/` with `python tools/af_cli.py deploy`. Never edit `deploy/`.
- Core files carry no tool-specific syntax beyond the neutral agent frontmatter (name, description, tools, skills, maxTurns).
- Tools are Python stdlib only.
- Subagents cannot launch agents; the main session orchestrates. The PM-GPT approval is produced only by `af_cli.py pm-review`.
- Do not copy project-private content here. All committed text is English. Every commit carries `docs/changes/<id>.md` and a `core/LESSONS_LOG.md` entry.
