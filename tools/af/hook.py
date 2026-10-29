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

SEGMENT_RE = re.compile(r"&&|\|\||[;|&\n()`]")
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
WRAPPERS = {"env", "command", "exec", "nice", "nohup", "time", "sudo", "builtin", "stdbuf", "timeout",
            "then", "do", "else", "!", "{"}
POSIX_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
MAX_DEPTH = 4


def _exe(tok: str) -> str:
    return re.split(r"[\\/]", tok)[-1].lower().removesuffix(".exe")


def _segments(command: str) -> list[list[str]]:
    """Tokenise honouring quotes, then split into command segments on shell operators."""
    text = command.replace(chr(92), "/").replace("`", " ; ").replace(chr(10), " ; ")
    try:
        lex = shlex.shlex(text, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:
        toks = []
        for seg in SEGMENT_RE.split(text):
            toks += seg.split() + [";"]
    segs: list[list[str]] = [[]]
    for tok in toks:
        if tok and set(tok) <= set("();<>|&"):
            segs.append([])
        else:
            segs[-1].append(tok)
    return [s for s in segs if s]


def _nested_payload(exe: str, toks: list[str]) -> str | None:
    """Command string handed to a nested shell (`sh -c '...'`, `cmd /c ...`, `pwsh -Command ...`)."""
    if exe in POSIX_SHELLS:
        for i, t in enumerate(toks[1:], 1):
            if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", t) and i + 1 < len(toks):
                return toks[i + 1]
    elif exe == "cmd":
        for i, t in enumerate(toks[1:], 1):
            if t.lower() in ("/c", "/k"):
                return " ".join(toks[i + 1:])
    elif exe in ("pwsh", "powershell"):
        for i, t in enumerate(toks[1:], 1):
            if t.lower() in ("-c", "-command"):
                return " ".join(toks[i + 1:])
    return None


def is_push_command(command: str, _depth: int = 0) -> bool:
    """True when the command runs `git push`, `gh pr create` or `gh pr merge`.

    Handles chained segments, leading env assignments, wrappers (env, command, sudo, ...) and nested
    shells (sh -c, cmd /c, pwsh -Command). This is a best-effort text check; the git pre-push hook
    (af_cli.py install-githook, installed by `on`) is the authoritative boundary.
    """
    if _depth > MAX_DEPTH:
        return False
    for toks in _segments(command):
        while toks:
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", toks[0]):
                toks = toks[1:]
            elif _exe(toks[0]) in WRAPPERS:
                toks = toks[1:]
                while toks and (toks[0].startswith("-") or re.fullmatch(r"\d+[smhd]?", toks[0])
                                or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", toks[0])):
                    toks = toks[1:]
            else:
                break
        if not toks:
            continue
        exe = _exe(toks[0])
        payload = _nested_payload(exe, toks)
        if payload is not None and is_push_command(payload, _depth + 1):
            return True
        if exe == "gh":
            if len(toks) >= 3 and toks[1] == "pr" and toks[2] in ("create", "merge"):
                return True
            continue
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
    return (f"[Agentic_Framework SDLC] sprint '{state.get('title', '')}' (id {state.get('sprint_id') or 'legacy'}; "
            f"every phase artifact must contain the line `Sprint: <id>`) phase {n} {p['name']}. "
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
