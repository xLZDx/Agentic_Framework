"""PM-GPT review and approve step.

`request` sends the exact committed range to PM Bridge (`review.js --final`), accepts only a
correlated, concluding APPROVE, and binds the approval to the git HEAD that was reviewed.
Before sending it validates the structured evidence (tools/af/evidence.py), the sprint artifacts and
the review base, and it pre-computes the exact prompt PM Bridge will send (review.js is
deterministic and has a prompt-dump mode) so the returned `reviewInputHash` can be compared with it.
`verify` is the mechanical push gate: it passes only while HEAD, the artifacts and the approval agree.
The same tool serves Claude and GPT/Codex sessions; the approval is tool-agnostic.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from . import core, evidence

KINDS = ("code", "docs")
DIFF_OPEN = "Diff:\n```diff\n"


def _paths(project: Path, kind: str) -> tuple[Path, Path]:
    sd = core.state_dir(project)
    pm = sd / ".pm-review"
    if kind == "code":
        return pm / "approval.json", sd / core.load_phase_map()["push_gate"]["approval_file"]
    return pm / "approval-docs.json", sd / "docs-approval.md"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
    names = ["verify-evidence.json", "verify-evidence.md", "review-record.md", "test-plan.md",
             "requirements.md", "backlog.md", "design.md"]
    for name in names:
        f = sd / name
        if f.is_file():
            parts.append(f"\n## Evidence file: {name} (sha256 {_sha(f.read_bytes())})\n{f.read_text(encoding='utf-8', errors='replace')}")
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


def _preflight(project: Path, kind: str, base: str, head_sha: str) -> str | None:
    """Reject incomplete evidence, unstamped artifacts and review ranges that do not cover the sprint."""
    if kind == "code":
        problems = evidence.validate(project, head_sha)
        if problems:
            return "verify-evidence.json is not acceptable: " + "; ".join(problems)
        st = core.read_state(project)
        if st:
            if not st.get("sprint_id"):
                return "legacy sprint state without sprint_id; run `af_cli.py migrate` and re-stamp the artifacts"
            for n in range(1, 8):
                miss = core.missing_artifacts(project, n)
                if miss:
                    return f"phase {n} artifacts missing or not stamped with sprint id {st['sprint_id']}: {', '.join(miss)}"
    try:
        base_sha = core.git(project, "rev-parse", "--verify", f"{base}^{{commit}}").strip()
    except RuntimeError as exc:
        return f"base {base!r} does not resolve to a commit: {exc}"
    anc = subprocess.run(["git", "-C", str(project), "merge-base", "--is-ancestor", base_sha, head_sha])
    if anc.returncode != 0:
        return f"base {base_sha[:12]} is not an ancestor of HEAD"
    start = (core.read_state(project) or {}).get("start_head")
    if kind == "code" and start:
        cov = subprocess.run(["git", "-C", str(project), "merge-base", "--is-ancestor", base_sha, start])
        if cov.returncode != 0:
            return (f"base {base_sha[:12]} starts after the sprint baseline {start[:12]}; "
                    "the review range would omit sprint changes")
    if subprocess.run(["git", "-C", str(project), "diff", "--quiet", f"{base_sha}...{head_sha}"]).returncode == 0:
        return "the review range is empty"
    return None


def _git_common_dir(project: Path) -> Path | None:
    try:
        raw = core.git(project, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
        return Path(raw).resolve(strict=True)
    except (RuntimeError, OSError):
        return None


def _review_cmd(node: str, review_js: Path, review_cwd: Path, base: str, head_sha: str,
                packet: Path, project_id: str | None) -> list[str]:
    cmd = [node, str(review_js), "--cwd", str(review_cwd), "--base", base, "--head", head_sha,
           "--final", "--scope-note-file", str(packet)]
    if project_id:
        cmd += ["--project", project_id]
    return cmd


def _expected_prompt(cmd: list[str], dump: Path) -> str | None:
    """Ask review.js for the exact prompt it will send (dump-only mode: no browser, no receipt)."""
    env = dict(os.environ, PM_BRIDGE_DEBUG_DUMP_PROMPT=str(dump), PM_BRIDGE_DEBUG_DUMP_PROMPT_ONLY="1")
    if dump.exists():
        dump.unlink()
    subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, env=env)
    return dump.read_bytes().decode("utf-8") if dump.is_file() else None


def request(project: Path, kind: str, base: str, node: str = "node", project_id: str | None = None,
            review_cwd: Path | None = None) -> int:
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
    review_cwd = Path(review_cwd or project).resolve()
    project_common = _git_common_dir(project)
    review_common = _git_common_dir(review_cwd)
    if project_common is None or review_common is None or project_common != review_common:
        print("REFUSED: --review-cwd must resolve to the same Git repository as the candidate project; "
              "use the registered primary checkout for PM Bridge routing.")
        return 2
    sd = core.state_dir(project)
    problem = _preflight(project, kind, base, head_sha)
    if problem:
        print(f"REFUSED: {problem}")
        return 2
    pm_dir = sd / ".pm-review"
    pm_dir.mkdir(parents=True, exist_ok=True)
    packet = pm_dir / f"packet-{kind}-{head_sha[:12]}.md"
    packet.write_bytes(build_packet(project, kind, base, head_sha).encode("utf-8"))  # LF bytes, no newline translation
    cmd = _review_cmd(node, review_js, review_cwd, base, head_sha, packet, project_id)

    prompt = _expected_prompt(cmd, pm_dir / f"prompt-{kind}-{head_sha[:12]}.txt")
    if prompt is None:
        print("REFUSED: could not pre-compute the review prompt (review.js dump mode unavailable); "
              "the returned input hash could not be bound. No review sent.")
        return 2
    packet_text = packet.read_bytes().decode("utf-8")
    if packet_text.strip() not in prompt or head_sha not in prompt:
        print("REFUSED: the pre-computed prompt does not contain the evidence packet and the exact head.")
        return 2
    expected_hash = _sha(prompt.encode("utf-8"))
    cut = prompt.find(DIFF_OPEN)
    diff_in_prompt = prompt[cut + len(DIFF_OPEN):] if cut >= 0 else ""

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
    if result.get("reviewInputHash") != expected_hash:
        print(f"NOT_APPROVED: reviewInputHash {result.get('reviewInputHash')} does not match the pre-computed "
              f"prompt hash {expected_hash}; the reviewed input is not the one we prepared.")
        return 1
    base_sha = core.git(project, "rev-parse", f"{base}^{{commit}}").strip()
    ev_json = sd / evidence.FILE
    approval = {
        "approval_id": f"PMG-{core.now_iso()[:10].replace('-', '')}-{head_sha[:8]}",
        "kind": kind,
        "head": head_sha,
        "base": base,
        "base_sha": base_sha,
        "verdict": result["verdict"],
        "request_id": result["reviewRequestId"],
        "reply_id": result["replyId"],
        "input_hash": result["reviewInputHash"],
        "expected_input_hash": expected_hash,
        "diff_sha256": _sha(core.git(project, "diff", f"{base_sha}...{head_sha}").encode("utf-8", "replace")),
        "diff_in_prompt_sha256": _sha(diff_in_prompt.encode("utf-8")),
        "evidence_sha256": _sha(ev_json.read_bytes()) if ev_json.is_file() else None,
        "sprint_id": (core.read_state(project) or {}).get("sprint_id"),
        "artifacts": core.artifact_digests(project) if kind == "code" else {},
        "reply_sha256": _sha((result.get("reply") or "").encode("utf-8")),
        "recorded": core.now_iso(),
        "reviewer": "GPT-PM via PM Bridge review.js",
    }
    jpath, mpath = _paths(project, kind)
    jpath.write_text(json.dumps(approval, indent=2) + "\n", encoding="utf-8")
    mpath.write_text(
        "# PM-GPT approval\n\n"
        f"Approval id: {approval['approval_id']}\nHead: {approval['head']}\nKind: {kind}\n"
        f"Verdict: {approval['verdict']}\nRequest id: {approval['request_id']}\nReply id: {approval['reply_id']}\n"
        f"Recorded: {approval['recorded']}\n"
        + (f"Sprint: {approval['sprint_id']}\n" if approval["sprint_id"] else "")
        + "\nGenerated by tools/af_cli.py pm-review. Do not edit by hand.\n",
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
    recorded = a.get("artifacts") or {}
    if recorded:
        now = core.artifact_digests(project)
        changed = sorted(k for k in set(recorded) | set(now) if recorded.get(k) != now.get(k))
        if changed:
            return False, f"artifacts changed after the approval: {', '.join(changed[:5])}"
    dirty = core.tracked_dirty(project)
    if dirty:
        return False, "tracked changes are uncommitted after the approval"
    return True, f"{a['approval_id']} head={cur}"
