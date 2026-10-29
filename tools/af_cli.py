#!/usr/bin/env python
"""Agentic_Framework CLI: SDLC state, phase gating, PM-GPT review and deploy.

  status | start "<title>" | next [--force] | mode hard|soft | pause | resume
  pm-review --kind code|docs --base <ref> | verify [--kind code|docs]
  hook (Claude hook entry, reads stdin) | deploy | install-githook
Run from the project to orchestrate (or pass --project).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from af import core, pm_review  # noqa: E402


def _project(args) -> Path:
    try:
        return core.git_root(Path(args.project or "."))
    except RuntimeError:
        raise SystemExit(f"Not inside a git repository ({Path(args.project or '.').resolve()}). "
                         "Run from the project folder or pass --project <repo>.")


def cmd_status(args) -> int:
    p = _project(args)
    st = core.read_state(p)
    if not st:
        print(f"No sprint in {p}. Start one: af_cli.py start \"<title>\"")
        return 0
    n = st["phase"]
    d = core.phase_def(n)
    print(f"Sprint id: {st.get('sprint_id') or '(legacy: run migrate)'}  (artifacts must contain `Sprint: <id>`)")
    print(f"Sprint: {st.get('title')}  Phase: {n} {d['name']}  Mode: {st.get('mode')}  Paused: {bool(st.get('paused'))}")
    print(f"Roles to launch: {', '.join(d['roles']) or '(PM-GPT via pm-gpt-review)'}")
    print(f"Skills: {', '.join(d['skills'])}")
    print(f"Missing exit artifacts: {', '.join(core.missing_artifacts(p, n)) or 'none'}")
    if n >= 8:
        ok, why = pm_review.verify(p, "code")
        print(f"PM-GPT approval: {'OK' if ok else 'NOT VALID'} - {why}")
    return 0


def _require_gate(args, mode: str) -> bool:
    """Hard mode needs the authoritative git pre-push gate; refuse activation when it cannot be installed."""
    rc = cmd_install_githook(args)
    if rc != 0 and mode == "hard":
        print("Framework NOT enabled in hard mode: the git pre-push gate could not be installed "
              "(a foreign pre-push hook exists). Chain it manually by adding "
              "`python <framework>/tools/af_cli.py --project \"$(git rev-parse --show-toplevel)\" gate-check || exit 1` "
              "to that hook, or use --mode soft.")
        return False
    return True


def cmd_start(args) -> int:
    p = _project(args)
    if core.read_state(p):
        print("A sprint already exists; refusing to overwrite.")
        return 1
    if not _require_gate(args, args.mode):
        return 1
    core.write_state(p, core.new_sprint_state(p, args.title, args.mode))
    print(f"Started '{args.title}' at phase 1 in {p}")
    return 0


def cmd_next(args) -> int:
    p = _project(args)
    st = core.read_state(p)
    if not st:
        print("No sprint.")
        return 1
    if not st.get("sprint_id"):
        print("BLOCKED: legacy sprint state without sprint_id. Run `af_cli.py migrate`, then stamp each artifact "
              "with the printed `Sprint: <id>` line.")
        return 1
    n = st["phase"]
    miss = core.missing_artifacts(p, n)
    if miss and not args.force:
        print(f"BLOCKED: phase {n} is missing {', '.join(miss)}")
        return 1
    pm = core.phase_def(n).get("pm_review")
    if pm and pm["required"]:
        ok, why = pm_review.verify(p, pm["kind"])
        if not ok:  # --force never bypasses a required PM-GPT approval
            print(f"BLOCKED: PM-GPT approval required at phase {n}: {why} (--force does not apply)")
            return 1
    if n >= 10:
        print("Already at the last phase.")
        return 0
    st["history"].append({"phase": n, "left": core.now_iso(), "head": core.head(p), "forced": bool(args.force),
                          "artifacts": core.artifact_digests(p, n)})
    st["phase"] = n + 1
    core.write_state(p, st)
    print(f"Advanced to phase {n + 1} {core.phase_def(n + 1)['name']}")
    return 0


def _set(args, **kv) -> int:
    p = _project(args)
    st = core.read_state(p)
    if not st:
        print("No sprint.")
        return 1
    st.update(kv)
    core.write_state(p, st)
    return 0


def cmd_on(args) -> int:
    from af.hook import context_line

    p = _project(args)
    st = core.read_state(p)
    if st is None:
        if not _require_gate(args, args.mode):  # authoritative push boundary for every tool, not just Claude
            return 1
        core.write_state(p, core.new_sprint_state(p, args.title, args.mode))
        print(f"Framework ON: started '{args.title}' at phase 1 ({args.mode}) in {p}")
        print(context_line(p))
        return 0
    mode = args.mode if args.mode_given else st["mode"]
    if not _require_gate(args, mode):
        return 1
    st["paused"] = False
    st["mode"] = mode
    core.write_state(p, st)
    print(f"Framework ON: resumed at phase {st['phase']} ({st['mode']}) in {p}")
    print(context_line(p))
    return 0


def cmd_migrate(args) -> int:
    p = _project(args)
    st = core.read_state(p)
    if not st:
        print("No sprint.")
        return 1
    if st.get("sprint_id"):
        print(f"Already migrated: Sprint: {st['sprint_id']}")
        return 0
    st["sprint_id"] = core.new_sprint_state(p, st.get("title", ""), st.get("mode", "hard"))["sprint_id"]
    core.write_state(p, st)
    print(f"Migrated. Stamp every phase artifact with the line: Sprint: {st['sprint_id']}")
    return 0


def cmd_off(args) -> int:
    p = _project(args)
    st = core.read_state(p)
    if st is None:
        print("Framework already OFF (no sprint state).")
        return 0
    st["paused"] = True
    core.write_state(p, st)
    print(f"Framework OFF: paused at phase {st['phase']}; no injection, no push gate. State kept.")
    return 0


def cmd_mode(args) -> int:
    if args.value == "hard" and not _require_gate(args, "hard"):
        return 1
    return _set(args, mode=args.value)


def cmd_pm_review(args) -> int:
    return pm_review.request(_project(args), args.kind, args.base, node=args.node, project_id=args.project_id)


def cmd_verify(args) -> int:
    ok, why = pm_review.verify(_project(args), args.kind)
    print(("OK " if ok else "FAIL ") + why)
    return 0 if ok else 1


def cmd_hook(args) -> int:
    from af import hook
    return hook.main()


def cmd_deploy(args) -> int:
    from af import deploy
    for w in deploy.build():
        print(w)
    return 0


def cmd_install_githook(args) -> int:
    p = _project(args)
    hooks = Path(core.git(p, "rev-parse", "--git-path", "hooks").strip())
    hooks = hooks if hooks.is_absolute() else p / hooks
    hooks.mkdir(parents=True, exist_ok=True)
    target = hooks / "pre-push"
    marker = "# agentic-framework pre-push"
    if target.exists() and marker not in target.read_text(encoding="utf-8", errors="replace"):
        print(f"REFUSED: {target} exists and is not ours.")
        return 1
    cli = (Path(__file__).resolve()).as_posix()
    target.write_text(
        f"#!/bin/sh\n{marker}\n"
        f'python "{cli}" --project "$(git rev-parse --show-toplevel)" gate-check || exit 1\n',
        encoding="utf-8")
    print(f"Installed {target}")
    return 0


def cmd_gate_check(args) -> int:
    from af import hook
    p = _project(args)
    reason = hook.gate_decision(p, "git push")
    if reason:
        print(f"push blocked: {reason}", file=sys.stderr)
        return 1
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="af_cli")
    ap.add_argument("--project")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    s = sub.add_parser("start"); s.add_argument("title"); s.add_argument("--mode", default="hard", choices=["hard", "soft"]); s.set_defaults(fn=cmd_start)
    s = sub.add_parser("next"); s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_next)
    s = sub.add_parser("mode"); s.add_argument("value", choices=["hard", "soft"]); s.set_defaults(fn=cmd_mode)
    sub.add_parser("pause").set_defaults(fn=lambda a: _set(a, paused=True))
    sub.add_parser("resume").set_defaults(fn=lambda a: _set(a, paused=False))
    s = sub.add_parser("on"); s.add_argument("--mode", default=None, choices=["hard", "soft"]); s.add_argument("--title", default="Sprint"); s.set_defaults(fn=cmd_on)
    sub.add_parser("off").set_defaults(fn=cmd_off)
    sub.add_parser("migrate").set_defaults(fn=cmd_migrate)
    s = sub.add_parser("pm-review"); s.add_argument("--kind", choices=list(pm_review.KINDS), default="code"); s.add_argument("--base", required=True); s.add_argument("--node", default="node"); s.add_argument("--project-id"); s.set_defaults(fn=cmd_pm_review)
    s = sub.add_parser("verify"); s.add_argument("--kind", choices=list(pm_review.KINDS), default="code"); s.set_defaults(fn=cmd_verify)
    sub.add_parser("hook").set_defaults(fn=cmd_hook)
    sub.add_parser("deploy").set_defaults(fn=cmd_deploy)
    sub.add_parser("install-githook").set_defaults(fn=cmd_install_githook)
    sub.add_parser("gate-check").set_defaults(fn=cmd_gate_check)
    args = ap.parse_args(argv)
    if args.cmd == "on":
        args.mode_given = args.mode is not None
        args.mode = args.mode or "hard"
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
