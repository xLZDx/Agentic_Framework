"""PM-GPT review and approve step.

`request` sends the exact committed range to PM Bridge (`review.js --final`), accepts only a
correlated, concluding APPROVE, and binds the approval to the git HEAD that was reviewed.
`verify` is the mechanical push gate: it passes only while HEAD still equals the approved head.
The same tool serves Claude and GPT/Codex sessions; the approval is tool-agnostic.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from . import core

KINDS = ("code", "docs")


def _paths(project: Path, kind: str) -> tuple[Path, Path]:
    sd = core.state_dir(project)
    pm = sd / ".pm-review"
    if kind == "code":
        return pm / "approval.json", sd / core.load_phase_map()["push_gate"]["approval_file"]
    return pm / "approval-docs.json", sd / "docs-approval.md"


def build_packet(project: Path, kind: str, base: str, head_sha: str) -> str:
    sd = core.state_dir(project)
    parts = [
        f"# PM-GPT {kind} review request",
        f"Project root: {project}",
        f"Reviewed range: {base}...{head_sha}",
        f"Exact HEAD under review: {head_sha}",
        "Reply format: first line `VERDICT: APPROVE|MINOR|MAJOR|BLOCKER`, then one finding per line as "
        "`SEVERITY | basis | claim | evidence | required change`.",
        "Approve only if the exact head is safe to push. Verify claims against the diff.",
    ]
    for name in ("verify-evidence.md", "review-record.md", "test-plan.md", "requirements.md", "backlog.md", "design.md"):
        f = sd / name
        if f.is_file():
            parts.append(f"\n## Evidence file: {name}\n{f.read_text(encoding='utf-8', errors='replace')}")
        elif kind == "code" and name == "verify-evidence.md":
            parts.append("\n## Evidence file: verify-evidence.md\nMISSING (treat all verification as NOT_RUN)")
    return "\n".join(parts)


def _accept(result: dict) -> tuple[bool, str]:
    accepted = core.load_phase_map()["pm_review"]["accepted_verdicts"]
    checks = [
        (result.get("ok") is True, "review did not run (ok=false)"),
        (result.get("review_status") == "RAN", f"review_status={result.get('review_status')}"),
        (result.get("verdict") in accepted, f"verdict={result.get('verdict')}"),
        (result.get("final") is True and not result.get("final_overridden"), "review not concluding"),
        (not result.get("truncated"), "diff truncated"),
        (result.get("correlated") is True, "reply not correlated to the request"),
        (not result.get("verdict_contradiction"), "verdict contradicts findings"),
        (bool(result.get("reviewRequestId")) and bool(result.get("replyId")), "missing request/reply id"),
    ]
    for ok, why in checks:
        if not ok:
            return False, why
    return True, "ok"


EVIDENCE_HEADINGS = ("## Test evidence", "## NOT_RUN")


def _preflight(project: Path, kind: str, base: str, head_sha: str) -> str | None:
    """Reject incomplete evidence and review ranges that do not cover the sprint."""
    if kind == "code":
        ev = core.state_dir(project) / "verify-evidence.md"
        text = ev.read_text(encoding="utf-8", errors="replace") if ev.is_file() else ""
        missing = [h for h in EVIDENCE_HEADINGS if h not in text]
        if missing:
            return f"verify-evidence.md is missing or lacks required sections {missing}; produce the phase-7 evidence first."
    try:
        base_sha = core.git(project, "rev-parse", "--verify", f"{base}^{{commit}}").strip()
    except RuntimeError as exc:
        return f"base {base!r} does not resolve to a commit: {exc}"
    anc = subprocess.run(["git", "-C", str(project), "merge-base", "--is-ancestor", base_sha, head_sha])
    if anc.returncode != 0:
        return f"base {base_sha[:12]} is not an ancestor of HEAD"
    st = core.read_state(project) or {}
    start = st.get("start_head")
    if kind == "code" and start:
        cov = subprocess.run(["git", "-C", str(project), "merge-base", "--is-ancestor", base_sha, start])
        if cov.returncode != 0:
            return (f"base {base_sha[:12]} starts after the sprint baseline {start[:12]}; "
                    "the review range would omit sprint changes")
    if subprocess.run(["git", "-C", str(project), "diff", "--quiet", f"{base_sha}...{head_sha}"]).returncode == 0:
        return "the review range is empty"
    return None


def request(project: Path, kind: str, base: str, node: str = "node", project_id: str | None = None) -> int:
    if kind not in KINDS:
        raise SystemExit(f"kind must be one of {KINDS}")
    review_js = core.find_review_js()
    if review_js is None:
        print("NOT_RUN: PM Bridge review.js not found (set AF_PM_REVIEW_JS). No approval recorded.")
        return 2
    dirty = core.tracked_dirty(project)
    if dirty:
        print("REFUSED: tracked changes are uncommitted; commit first so the approval binds to a real head:\n" + "\n".join(dirty[:10]))
        return 2
    head_sha = core.head(project)
    sd = core.state_dir(project)
    problem = _preflight(project, kind, base, head_sha)
    if problem:
        print(f"REFUSED: {problem}")
        return 2
    pm_dir = sd / ".pm-review"
    pm_dir.mkdir(parents=True, exist_ok=True)
    packet = pm_dir / f"packet-{kind}-{head_sha[:12]}.md"
    packet.write_text(build_packet(project, kind, base, head_sha), encoding="utf-8")
    cmd = [node, str(review_js), "--cwd", str(project), "--base", base, "--final", "--scope-note-file", str(packet)]
    if project_id:
        cmd += ["--project", project_id]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        print(f"NOT_RUN: review.js produced no JSON (exit {proc.returncode}): {proc.stderr.strip()[:500]}")
        return 2
    (pm_dir / f"result-{kind}-{head_sha[:12]}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    ok, why = _accept(result)
    if core.head(project) != head_sha:
        print("REFUSED: HEAD moved during the review; the verdict applies to the old head.")
        return 2
    if not ok:
        print(f"NOT_APPROVED: {why}. Verdict={result.get('verdict')}.\n--- reply ---\n{(result.get('reply') or '')[:6000]}")
        return 1
    approval = {
        "approval_id": f"PMG-{core.now_iso()[:10].replace('-', '')}-{head_sha[:8]}",
        "kind": kind,
        "head": head_sha,
        "base": base,
        "verdict": result["verdict"],
        "request_id": result["reviewRequestId"],
        "reply_id": result["replyId"],
        "input_hash": result.get("reviewInputHash"),
        "base_sha": core.git(project, "rev-parse", f"{base}^{{commit}}").strip(),
        "diff_sha256": hashlib.sha256(core.git(project, "diff", f"{base}...{head_sha}").encode("utf-8", "replace")).hexdigest(),
        "evidence_sha256": hashlib.sha256((core.state_dir(project) / "verify-evidence.md").read_bytes()).hexdigest()
        if (core.state_dir(project) / "verify-evidence.md").is_file() else None,
        "reply_sha256": hashlib.sha256((result.get("reply") or "").encode("utf-8")).hexdigest(),
        "recorded": core.now_iso(),
        "reviewer": "GPT-PM via PM Bridge review.js",
    }
    jpath, mpath = _paths(project, kind)
    jpath.write_text(json.dumps(approval, indent=2) + "\n", encoding="utf-8")
    mpath.write_text(
        "# PM-GPT approval\n\n"
        f"Approval id: {approval['approval_id']}\nHead: {approval['head']}\nKind: {kind}\n"
        f"Verdict: {approval['verdict']}\nRequest id: {approval['request_id']}\nReply id: {approval['reply_id']}\n"
        f"Recorded: {approval['recorded']}\n\nGenerated by tools/af_cli.py pm-review. Do not edit by hand.\n",
        encoding="utf-8",
    )
    print(f"APPROVED: {approval['approval_id']} head={head_sha}")
    return 0


def verify(project: Path, kind: str = "code") -> tuple[bool, str]:
    jpath, mpath = _paths(project, kind)
    if not jpath.is_file():
        return False, f"no {kind} approval recorded ({jpath})"
    a = json.loads(jpath.read_text(encoding="utf-8"))
    cur = core.head(project)
    if a.get("head") != cur:
        return False, f"approval is for {str(a.get('head'))[:12]}, HEAD is {cur[:12]}: a new commit invalidates it"
    if a.get("verdict") not in core.load_phase_map()["pm_review"]["accepted_verdicts"]:
        return False, f"verdict {a.get('verdict')} does not unlock the gate"
    if not (a.get("request_id") and a.get("reply_id")):
        return False, "approval lacks correlated ids"
    if not mpath.is_file() or a["head"] not in mpath.read_text(encoding="utf-8"):
        return False, f"{mpath.name} missing or does not match approval.json"
    dirty = core.tracked_dirty(project)
    if dirty:
        return False, "tracked changes are uncommitted after the approval"
    return True, f"{a['approval_id']} head={cur}"
