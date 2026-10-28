#!/usr/bin/env python
"""Autostart for Agentic_Framework: keep the installed copy in sync at Windows logon / VS Code open.

  python tools/af_autostart.py run                 # what the triggers call: deploy + idempotent install + log
  python tools/af_autostart.py register            # Windows Scheduled Task at user logon (no admin)
  python tools/af_autostart.py register-vscode     # VS Code task that runs on folder open (D:\\Repo workspace)
  python tools/af_autostart.py unregister          # remove the Scheduled Task and the VS Code task
  python tools/af_autostart.py status

`run` never enables the framework in a project (that stays `/af on`); it only keeps agents, skills,
the /af command and hooks installed and current. It is quiet, idempotent and fails soft.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

FW = Path(__file__).resolve().parents[1]
PY = sys.executable
TASK = "AgenticFramework-Autostart"
LOG = Path.home() / ".claude" / "af-autostart.log"
VSCODE_TASKS = Path("D:/Repo/.vscode/tasks.json")
VSCODE_LABEL = "Agentic_Framework autostart"
RUN_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "AgenticFrameworkAutostart"


def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def cmd_run(_a) -> int:
    for step, args in (("deploy", [PY, str(FW / "tools" / "af_cli.py"), "deploy"]),
                       ("install", [PY, str(FW / "tools" / "af_install.py")])):
        try:
            r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            tail = (r.stdout.strip().splitlines() or [""])[-1][:120]
            log(f"{step} exit={r.returncode} last={tail!r}")
        except Exception as exc:  # fail soft
            log(f"{step} error={exc}")
    return 0


def _pythonw() -> str:
    w = Path(PY).with_name("pythonw.exe")
    return str(w if w.exists() else PY)


def cmd_register(_a) -> int:
    tr = f'"{_pythonw()}" "{Path(__file__).resolve()}" run'
    r = subprocess.run(["schtasks", "/Create", "/F", "/SC", "ONLOGON", "/TN", TASK, "/TR", tr, "/RL", "LIMITED"],
                       capture_output=True, text=True)
    print((r.stdout or r.stderr).strip())
    if r.returncode != 0:
        # schtasks ONLOGON needs admin; fall back to the per-user Run key (no elevation).
        r = subprocess.run(["reg", "add", RUN_KEY, "/v", RUN_NAME, "/t", "REG_SZ", "/d", tr, "/f"],
                           capture_output=True, text=True)
        print("Run key fallback:", (r.stdout or r.stderr).strip())
    return r.returncode


def _load_tasks() -> dict:
    if VSCODE_TASKS.is_file():
        return json.loads(VSCODE_TASKS.read_text(encoding="utf-8"))
    return {"version": "2.0.0", "tasks": []}


def cmd_register_vscode(_a) -> int:
    data = _load_tasks()
    data["tasks"] = [t for t in data["tasks"] if t.get("label") != VSCODE_LABEL]
    data["tasks"].append({
        "label": VSCODE_LABEL, "type": "process", "command": PY,
        "args": [str(Path(__file__).resolve()), "run"],
        "presentation": {"reveal": "never", "panel": "dedicated", "close": True},
        "runOptions": {"runOn": "folderOpen"}, "problemMatcher": []})
    VSCODE_TASKS.parent.mkdir(parents=True, exist_ok=True)
    VSCODE_TASKS.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {VSCODE_TASKS}. VS Code asks once to allow automatic tasks (or set task.allowAutomaticTasks=on).")
    return 0


def cmd_unregister(_a) -> int:
    r = subprocess.run(["schtasks", "/Delete", "/F", "/TN", TASK], capture_output=True, text=True)
    print((r.stdout or r.stderr).strip())
    r = subprocess.run(["reg", "delete", RUN_KEY, "/v", RUN_NAME, "/f"], capture_output=True, text=True)
    print("Run key:", (r.stdout or r.stderr).strip())
    if VSCODE_TASKS.is_file():
        data = _load_tasks()
        before = len(data["tasks"])
        data["tasks"] = [t for t in data["tasks"] if t.get("label") != VSCODE_LABEL]
        if len(data["tasks"]) != before:
            VSCODE_TASKS.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            print(f"Removed task from {VSCODE_TASKS}")
    return 0


def cmd_status(_a) -> int:
    r = subprocess.run(["schtasks", "/Query", "/TN", TASK], capture_output=True, text=True)
    print("Scheduled task:", "present" if r.returncode == 0 else "absent")
    rk = subprocess.run(["reg", "query", RUN_KEY, "/v", RUN_NAME], capture_output=True, text=True)
    print("Run key:", "present" if rk.returncode == 0 else "absent")
    has = VSCODE_TASKS.is_file() and any(t.get("label") == VSCODE_LABEL for t in _load_tasks()["tasks"])
    print("VS Code task:", "present" if has else "absent")
    print("Last log lines:")
    if LOG.is_file():
        print("\n".join(LOG.read_text(encoding="utf-8").splitlines()[-4:]))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n, fn in (("run", cmd_run), ("register", cmd_register), ("register-vscode", cmd_register_vscode),
                  ("unregister", cmd_unregister), ("status", cmd_status)):
        sub.add_parser(n).set_defaults(fn=fn)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
