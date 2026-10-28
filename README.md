# Agentic_Framework

A tool-agnostic virtual scrum team. One neutral `core/` (roles, skills, phase map) is rendered into
`deploy/claude/` and `deploy/codex/`, so the same SDLC orchestration runs in Claude Code and in
GPT/Codex sessions. The layering is modelled on the Agentic Studio / AI Dev Kit
("core" tool-agnostic layer + generated "deploy" layer); the process comes from the Virtual Scrum
Team orchestration (10 phases, one role per responsibility, written artifacts per phase).

Out of scope: the Virtual_scrum_team sandbox/QA runner (`tools/vst`, `tools/qa`) and the AEVE gate.

## The PM-GPT review and approve step

Phase 8 is a mechanical gate. `tools/af_cli.py pm-review --kind code --base <ref>` sends the exact
committed range plus `verify-evidence.md` to the GPT-PM through PM Bridge `review.js --final`, accepts
only a correlated, concluding `APPROVE`, and writes `gate-approval.md` and `.pm-review/approval.json`
bound to the reviewed HEAD. `git push`, `gh pr create` and `gh pr merge` are denied until the
approval matches the current HEAD (Claude hook, and a git `pre-push` hook for GPT/Codex and humans).
A new commit invalidates the approval. Phase 5 can run the same review with `--kind docs`.

Limits: the approval files are guarded by tooling and convention, not by cryptography; an actor with
file access could forge them. The gate protects against accidents and self-approval by agents that
follow the rules.

## Phases

1 Discovery, 2 Backlog, 3 Design, 4 Docs and test plan, 5 Doc review, 6 Build, 7 Verify,
8 PM-GPT review and approve, 9 Accept and release, 10 Report and retro. Map: `core/orchestration/phase-map.json`.

## Use

```
python tools/af_cli.py deploy                       # regenerate deploy/ from core/
python tools/af_cli.py --project <repo> start "Sprint 1"
python tools/af_cli.py --project <repo> status
python tools/af_cli.py --project <repo> next
python tools/af_cli.py --project <repo> pm-review --kind code --base origin/main
python tools/af_cli.py --project <repo> install-githook
```

Install (manual, opt-in): copy `deploy/claude/agents` and `skills` into `~/.claude/`, merge
`deploy/claude/settings.hooks.json` into `~/.claude/settings.json` (replace `{fw}` with this
checkout path), append `deploy/claude/CLAUDE.fragment.md` to the routing text. For GPT/Codex copy
`deploy/codex/agents` to `~/.codex/agents`, `skills` to `~/.codex/skills`, and append
`deploy/codex/AGENTS.fragment.md` to `AGENTS.md`.

## Models

Claude agents: alias `sonnet`, effort `medium`; Opus never automatic. Codex agents: `gpt-6-luna`.
Reviewers: Sonnet 5.5 medium or GPT-5.6 Luna low/medium only.

## Layout

| Path | Content |
|---|---|
| `core/agents`, `core/skills` | Neutral role and skill sources |
| `core/orchestration/phase-map.json` | Phases, roles, exit artifacts, push gate, PM review config |
| `core/framework.json` | Bundled vs external roles/skills, per-target model policy |
| `tools/af/`, `tools/af_cli.py` | State, gating, PM review, hook, deploy |
| `deploy/` | Generated; never edit by hand |
| `docs/changes/` | One change record per commit |
