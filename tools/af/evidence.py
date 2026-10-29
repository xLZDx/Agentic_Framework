"""Structured phase-7 verification evidence (docs/sdlc/verify-evidence.json).

The PM-GPT reviewer stays the judge of sufficiency; this module only refuses evidence that is
missing, malformed, contradictory, red, stale against the code, or has open blocking findings.

Schema (all keys required unless marked optional):
{
  "tested_head": "<git sha the tests ran against>",
  "runs": [{"command": str, "total": int, "passed": int, "failed": int, "errors": int,
            "skipped": int, "log": str (optional)}],
  "not_run": [{"item": str, "reason": str}],
  "findings": {"open_blocker": int, "open_major": int},
  "reviewers": [{"role": str, "model": str, "effort": str, "verdict": str}]   # may be empty
}
"""
from __future__ import annotations

import json
from pathlib import Path

from . import core

FILE = "verify-evidence.json"
# Paths whose changes after the tested head do not invalidate test evidence.
NON_CODE_PREFIXES = ("docs/",)
NON_CODE_FILES = ("core/DECISION_LOG.md", "core/LESSONS_LOG.md", "core/BACKLOG.md")


def _text(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def validate(project: Path, head_sha: str) -> list[str]:
    path = core.state_dir(project) / FILE
    if not path.is_file():
        return [f"{FILE} is missing"]
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"{FILE} is not valid JSON: {exc}"]
    if not isinstance(d, dict):
        return [f"{FILE} must be a JSON object"]
    problems: list[str] = []
    tested = d.get("tested_head")
    if not isinstance(tested, str) or len(tested) < 7:
        problems.append("tested_head is missing")
    else:
        try:
            full = core.git(project, "rev-parse", "--verify", f"{tested}^{{commit}}").strip()
            core.git(project, "merge-base", "--is-ancestor", full, head_sha)
            changed = core.git(project, "diff", "--name-only", f"{full}..{head_sha}").splitlines()
            code = [c for c in changed if not (c.startswith(NON_CODE_PREFIXES) or c in NON_CODE_FILES)]
            if code:
                problems.append(f"code changed after the tested head {full[:12]}: {', '.join(code[:5])}"
                                f"{' ...' if len(code) > 5 else ''}; re-run the tests")
        except RuntimeError:
            problems.append(f"tested_head {tested!r} is not an ancestor commit of HEAD")
    runs = d.get("runs")
    if not isinstance(runs, list) or not runs:
        problems.append("runs must be a non-empty list")
    else:
        for i, r in enumerate(runs):
            if not isinstance(r, dict) or not isinstance(r.get("command"), str) or not r["command"].strip():
                problems.append(f"runs[{i}].command is missing")
                continue
            if not all(_int(r.get(k)) for k in ("total", "passed", "failed", "errors", "skipped")):
                problems.append(f"runs[{i}] needs integer total/passed/failed/errors/skipped")
                continue
            if r["total"] != r["passed"] + r["failed"] + r["errors"] + r["skipped"]:
                problems.append(f"runs[{i}] counts are contradictory (total != passed+failed+errors+skipped)")
            if r["total"] == 0:
                problems.append(f"runs[{i}] ran zero tests")
            if r["failed"] or r["errors"]:
                problems.append(f"runs[{i}] is red ({r['failed']} failed, {r['errors']} errors)")
    nr = d.get("not_run")
    if not isinstance(nr, list):
        problems.append("not_run must be a list (may be empty)")
    else:
        for i, x in enumerate(nr):
            if not (isinstance(x, dict) and _text(x.get("item")) and _text(x.get("reason"))):
                problems.append(f"not_run[{i}] needs item and reason")
    f = d.get("findings")
    if not (isinstance(f, dict) and _int(f.get("open_blocker")) and _int(f.get("open_major"))):
        problems.append("findings needs integer open_blocker and open_major")
    elif f["open_blocker"] or f["open_major"]:
        problems.append(f"open blocking findings: {f['open_blocker']} blocker, {f['open_major']} major")
    rv = d.get("reviewers")
    if not isinstance(rv, list):
        problems.append("reviewers must be a list (may be empty)")
    else:
        for i, x in enumerate(rv):
            if not (isinstance(x, dict) and all(_text(x.get(k)) for k in ("role", "model", "effort", "verdict"))):
                problems.append(f"reviewers[{i}] needs role, model, effort, verdict")
    return problems
