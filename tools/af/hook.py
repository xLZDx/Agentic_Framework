"""Claude Code hook: phase context injection and the PM-GPT push gate.

Events: SessionStart, UserPromptSubmit (inject current phase), PreToolUse/Bash (deny push and PR
commands until phase 8 holds a valid PM-GPT approval for the exact HEAD). Inert in projects without
docs/sdlc/state.json or with mode "soft"; fails open on any internal error. GPT/Codex sessions get
the same gate from the git pre-push hook (see `af_cli.py install-githook`).
"""
from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

from . import core, pm_review

SEGMENT_RE = re.compile(r"&&|\|\||[;|&\n]")
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}


def is_push_command(command: str) -> bool:
    """True when any shell segment runs `git push`, `gh pr create` or `gh pr merge`."""
    for seg in SEGMENT_RE.split(command):
        seg = seg.replace(chr(92), "/")  # Windows paths: shlex would otherwise eat the backslashes
        try:
            toks = shlex.split(seg, posix=True)
        except ValueError:
            toks = seg.split()
        while toks and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", toks[0]):
            toks = toks[1:]
        if not toks:
            continue
        exe = re.split(r"[\\/]", toks[0])[-1].lower().removesuffix(".exe")
        if exe == "gh" and toks[1:3] and toks[1] == "pr" and toks[2] in ("create", "merge"):
            return True
        if exe != "git":
            continue
        i = 1
        while i < len(toks) and toks[i].startswith("-"):
            i += 2 if toks[i] in GIT_OPTS_WITH_VALUE else 1
        if i < len(toks) and toks[i] == "push":
            return True
    return False


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
    if not is_push_command(command):
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
