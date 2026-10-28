"""Claude Code hook: phase context injection and the PM-GPT push gate.

Events: SessionStart, UserPromptSubmit (inject current phase), PreToolUse/Bash (deny push and PR
commands until phase 8 holds a valid PM-GPT approval for the exact HEAD). Inert in projects without
docs/sdlc/state.json or with mode "soft"; fails open on any internal error. GPT/Codex sessions get
the same gate from the git pre-push hook (see `af_cli.py install-githook`).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from . import core, pm_review

PUSH_RE = re.compile(r"\bgit\b[^;&|\n]*\bpush\b|\bgh\s+pr\s+(create|merge)\b")


def _project(cwd: str) -> Path | None:
    try:
        return core.git_root(Path(cwd))
    except Exception:
        return None


def gate_decision(project: Path, command: str) -> str | None:
    """Return a denial reason, or None when the command is allowed."""
    state = core.read_state(project)
    if not state or state.get("mode") != "hard" or state.get("paused"):
        return None
    if not PUSH_RE.search(command):
        return None
    cfg = core.load_phase_map()["push_gate"]
    if state["phase"] < cfg["unlock_phase"]:
        return (f"SDLC phase is {state['phase']}; push/PR unlock at phase {cfg['unlock_phase']} "
                "after a PM-GPT APPROVE. Continue the phase flow (af_cli.py status).")
    ok, why = pm_review.verify(project, "code")
    if not ok:
        return f"PM-GPT approval gate: {why}. Run af_cli.py pm-review --kind code --base <ref>."
    return None


def context_line(project: Path) -> str | None:
    state = core.read_state(project)
    if not state or state.get("paused"):
        return None
    n = state["phase"]
    p = core.phase_def(n)
    miss = core.missing_artifacts(project, n)
    roles = ", ".join(p["roles"]) or "PM-GPT via skill pm-gpt-review"
    return (f"[Agentic_Framework SDLC] sprint '{state.get('title', '')}' phase {n} {p['name']}. "
            f"Missing exit artifacts: {', '.join(miss) or 'none'}. Launch as real agents: {roles}. "
            f"Skills: {', '.join(p['skills'])}. Advance with af_cli.py next; never self-approve phase 8.")


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
        project = _project(event.get("cwd") or ".")
        if project is None:
            return 0
        name = event.get("hook_event_name")
        if name == "PreToolUse" and event.get("tool_name") == "Bash":
            reason = gate_decision(project, (event.get("tool_input") or {}).get("command", ""))
            if reason:
                print(json.dumps({"hookSpecificOutput": {
                    "hookEventName": "PreToolUse", "permissionDecision": "deny",
                    "permissionDecisionReason": reason}}))
        elif name in ("SessionStart", "UserPromptSubmit"):
            line = context_line(project)
            if line:
                print(json.dumps({"hookSpecificOutput": {"hookEventName": name, "additionalContext": line}}))
    except Exception as exc:  # fail open: a broken hook must not block work
        print(f"af hook error (ignored): {exc}", file=sys.stderr)
    return 0
