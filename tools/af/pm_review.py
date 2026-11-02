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
# PM Bridge's 4 MiB request limit includes a JSON wrapper around this prompt.
MAX_REVIEW_PROMPT_BYTES = 3_800_000
MAX_APPROVAL_CHAIN = 128


def _paths(project: Path, kind: str) -> tuple[Path, Path]:
    sd = core.state_dir(project)
    pm = sd / ".pm-review"
    if kind == "code":
        return pm / "approval.json", sd / core.load_phase_map()["push_gate"]["approval_file"]
    return pm / "approval-docs.json", sd / "docs-approval.md"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _trusted_sprint_start(project: Path, revision: str) -> str | None:
    """Resolve a sprint baseline only when it matches the committed project state."""
    try:
        working_state = core.read_state(project)
        state_path = (core.state_dir(project) / "state.json").relative_to(project).as_posix()
        committed = subprocess.run(
            ["git", "-C", str(project), "show", f"{revision}:{state_path}"],
            capture_output=True, check=False,
        )
        if committed.returncode != 0 or not isinstance(working_state, dict):
            return None
        committed_state = json.loads(committed.stdout)
        if not isinstance(committed_state, dict):
            return None
        start_head = committed_state.get("start_head")
        if (
            not isinstance(working_state, dict)
            or working_state.get("sprint_id") != committed_state.get("sprint_id")
            or working_state.get("start_head") != start_head
        ):
            return None
        if not isinstance(start_head, str) or not start_head:
            return None
        return core.git(project, "rev-parse", "--verify", f"{start_head}^{{commit}}").strip()
    except (OSError, RuntimeError, ValueError):
        return None


def _valid_task_scope(project: Path, scope: dict, candidate_head: str, sprint_base_sha: str) -> bool:
    """Require an exact task base and a range containing only that task plus SDLC evidence."""
    if (
        scope.get("type") != "task"
        or not isinstance(scope.get("id"), str) or not scope["id"].strip()
        or not isinstance(scope.get("predecessor_task"), str) or not scope["predecessor_task"].strip()
        or not all(isinstance(scope.get(key), str) and scope[key].strip() for key in
                   ("base_sha", "task_head"))
        or not isinstance(candidate_head, str) or not candidate_head
        or not isinstance(sprint_base_sha, str) or not sprint_base_sha
    ):
        return False
    try:
        base = core.git(project, "rev-parse", "--verify", f"{scope['base_sha']}^{{commit}}").strip()
        task_head = core.git(project, "rev-parse", "--verify", f"{scope['task_head']}^{{commit}}").strip()
        head = core.git(project, "rev-parse", "--verify", f"{candidate_head}^{{commit}}").strip()
        evidence_data = json.loads((core.state_dir(project) / evidence.FILE).read_text(encoding="utf-8"))
        task_heads = evidence_data.get("task_exact_heads")
        task_record = task_heads.get(scope["id"]) if isinstance(task_heads, dict) else None
        recorded_task_head = task_record.get("head") if isinstance(task_record, dict) else None
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError):
        return False
    if (
        base != scope["base_sha"]
        or task_head != recorded_task_head
        or scope.get("sprint_base_sha") != sprint_base_sha
        or subprocess.run(["git", "-C", str(project), "merge-base", "--is-ancestor", sprint_base_sha, base]).returncode != 0
        or subprocess.run(["git", "-C", str(project), "merge-base", "--is-ancestor", base, task_head]).returncode != 0
        or subprocess.run(["git", "-C", str(project), "merge-base", "--is-ancestor", task_head, head]).returncode != 0
    ):
        return False
    task_paths = set(core.git(project, "diff", "--name-only", f"{base}...{task_head}").splitlines())
    candidate_paths = set(core.git(project, "diff", "--name-only", f"{base}...{head}").splitlines())
    post_task_code_change = subprocess.run(
        ["git", "-C", str(project), "diff", "--quiet", f"{task_head}...{head}", "--", ".", ":(exclude)docs/sdlc/**"]
    ).returncode
    return bool(task_paths) and post_task_code_change == 0 and task_paths.issubset(candidate_paths) and all(
        path in task_paths or path.startswith("docs/sdlc/") for path in candidate_paths
    )


def build_packet(
    project: Path,
    kind: str,
    sprint_base: str,
    review_base: str,
    head_sha: str,
    previous_approval: dict | None = None,
    task_scope: dict | None = None,
) -> str:
    sd = core.state_dir(project)
    parts = [
        f"# PM-GPT {kind} review request",
        f"Project root: {project}",
        f"Sprint baseline: {sprint_base}",
        f"Reviewed range: {review_base}...{head_sha}",
        f"Exact HEAD under review: {head_sha}",
        "Reply format: first line `VERDICT: APPROVE|MINOR|MAJOR|BLOCKER`, then one finding per line as "
        "`SEVERITY | basis | claim | evidence | required change`.",
        "Approve only if the exact head is safe to push. Verify claims against the diff.",
    ]
    if previous_approval:
        chain = previous_approval.get("approval_chain", []) + [previous_approval]
        parts.append(
            "\n## Incremental review provenance\n"
            "The range begins at the exact HEAD of the last correlated GPT-PM approval. "
            "The recorded predecessor approval chain was validated; all changes after the last "
            "approval through the exact HEAD above are included in this review.\n"
            "Validated approval chain (oldest first):\n"
            f"{_approval_chain_lines(chain)}"
        )
    if task_scope:
        parts.append(
            "\n## Explicit task-scoped review\n"
            f"Task: {task_scope['id']}\n"
            f"Task diff base: {task_scope['base_sha']}\n"
            f"Previous task label: {task_scope['predecessor_task']}\n"
            f"Review base: {task_scope['base_sha']} (scope boundary supplied for this task review)\n"
            f"Current task implementation HEAD: {task_scope['task_head']}\n"
            "Review only the concrete task delta from this base through the exact HEAD above. "
            "This request does not claim review or approval of changes outside that range. "
            "The task labels and task-head evidence are scope metadata, not acceptance proof. "
            "This request does not claim that the review base was previously reviewed or accepted. "
            "Treat task_acceptance_records in project evidence as unverified context. "
            + (
                "The task base is the exact configured sprint baseline and roots this approval chain. "
                if task_scope.get("base_anchor") == "sprint-base" else
                "The task base is the exact HEAD of the validated prior PM approval. "
            )
            + "Do not expand the code-review scope to the cumulative sprint diff."
        )
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


def _git_blob_shas(project: Path, revision: str, name: str) -> set[str]:
    repo_path = (core.state_dir(project).relative_to(project) / name).as_posix()
    proc = subprocess.run(
        ["git", "-C", str(project), "show", f"{revision}:{repo_path}"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return set()
    raw = proc.stdout
    variants = {raw, raw.replace(b"\r\n", b"\n"), raw.replace(b"\n", b"\r\n")}
    return {_sha(data) for data in variants}


def _approval_summary(approval: dict) -> dict:
    keys = (
        "approval_id", "head", "request_id", "reply_id", "input_hash", "reply_sha256",
        "approval_markdown_path", "approval_markdown_sha256",
    )
    return {key: approval.get(key) for key in keys}


def _approval_chain_lines(chain: list[dict]) -> str:
    return "\n".join(
        f"- {item.get('approval_id')} | HEAD {item.get('head')} | "
        f"request/reply {item.get('request_id')} / {item.get('reply_id')} | "
        f"markdown sha256 {item.get('approval_markdown_sha256')}"
        for item in chain
    )


def _approval_record(approval: dict) -> dict:
    """Copy one link without recursively embedding its chain."""
    return {
        key: value for key, value in approval.items()
        if key not in ("approval_chain", "_approval_history", "_approval_markdown_bytes")
    }


def _approval_history_path(head: str) -> str:
    return f".pm-review/history/approval-code-{head[:12]}.md"


def _valid_approval_markdown(markdown: bytes, approval: dict) -> bool:
    try:
        text = markdown.decode("utf-8")
    except UnicodeDecodeError:
        return False
    expected = (
        f"Approval id: {approval.get('approval_id')}",
        f"Head: {approval.get('head')}",
        f"Kind: {approval.get('kind')}",
        f"Verdict: {approval.get('verdict')}",
        f"Request id: {approval.get('request_id')}",
        f"Reply id: {approval.get('reply_id')}",
    )
    scope = approval.get("review_scope")
    if isinstance(scope, dict):
        expected += (
            f"Reviewed from: {approval.get('base_sha')}",
            f"Task scope: {scope.get('id')}",
        )
    return all(value and value in text for value in expected)


def _approval_markdown(approval: dict) -> bytes:
    text = (
        "# PM-GPT approval\n\n"
        f"Approval id: {approval['approval_id']}\nHead: {approval['head']}\nKind: {approval['kind']}\n"
        f"Verdict: {approval['verdict']}\nRequest id: {approval['request_id']}\n"
        f"Reply id: {approval['reply_id']}\nRecorded: {approval['recorded']}\n"
        + (f"Sprint: {approval['sprint_id']}\n" if approval.get("sprint_id") else "")
        + (f"Reviewed from: {approval['base_sha']}\nTask scope: {approval['review_scope']['id']}\n"
           if isinstance(approval.get("review_scope"), dict) else "")
        + "\nGenerated by tools/af_cli.py pm-review. Do not edit by hand.\n"
    )
    return text.encode("utf-8")


def _write_immutable_history(
    project: Path,
    path: str,
    content: bytes,
) -> bool:
    target = core.state_dir(project) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            return target.read_bytes() == content
        except OSError:
            return False
    try:
        with target.open("xb") as output:
            output.write(content)
    except FileExistsError:
        try:
            return target.read_bytes() == content
        except OSError:
            return False
    except OSError:
        return False
    return True


def _valid_approval_record(
    project: Path,
    evidence_sources: list[Path],
    approval: dict,
    sprint_base_sha: str,
    sprint_id: str | None,
    current_head: str,
    expected_base_sha: str,
    expected_previous: dict | None,
    expected_chain: list[dict],
    historical: bool,
    allow_current_head: bool = False,
) -> tuple[bool, bytes | None]:
    if not isinstance(approval, dict) or "approval_chain" in approval:
        return False, None
    try:
        head = core.git(project, "rev-parse", "--verify", f"{approval['head']}^{{commit}}").strip()
        base_sha = core.git(project, "rev-parse", "--verify", f"{approval['base_sha']}^{{commit}}").strip()
    except (KeyError, RuntimeError):
        return False, None

    recorded_sprint_base = approval.get("sprint_base_sha")
    if recorded_sprint_base is None and expected_previous is None:
        recorded_sprint_base = approval.get("base_sha")
    previous_link = approval.get("previous_approval")
    expected_link = _approval_summary(expected_previous) if expected_previous else None
    task_scope = approval.get("review_scope")
    if task_scope is not None and (
        not isinstance(task_scope, dict)
        or task_scope.get("base_sha") != base_sha
        or not _valid_task_scope(project, task_scope, head, sprint_base_sha)
        or _trusted_sprint_start(project, head) != sprint_base_sha
        or (
            expected_previous is None
            and (task_scope.get("base_anchor") != "sprint-base" or base_sha != sprint_base_sha)
        )
        or (
            expected_previous is not None
            and (task_scope.get("base_anchor") != "approval" or expected_previous.get("head") != base_sha)
        )
    ):
        return False, None
    if (
        approval.get("kind") != "code"
        or approval.get("verdict") not in core.load_phase_map()["pm_review"]["accepted_verdicts"]
        or not all(isinstance(approval.get(k), str) and approval[k] for k in
                   ("approval_id", "request_id", "reply_id", "input_hash", "reply_sha256"))
        or approval.get("input_hash") != approval.get("expected_input_hash")
        or approval.get("sprint_id") != sprint_id
        or recorded_sprint_base != sprint_base_sha
        or base_sha != expected_base_sha
        or previous_link != expected_link
        or (head == current_head and not allow_current_head)
    ):
        return False, None
    if subprocess.run(["git", "-C", str(project), "merge-base", "--is-ancestor", base_sha, head]).returncode != 0:
        return False, None
    if subprocess.run(["git", "-C", str(project), "merge-base", "--is-ancestor", head, current_head]).returncode != 0:
        return False, None

    prior_diff = core.git(project, "diff", f"{base_sha}...{head}")
    if _sha(prior_diff.encode("utf-8", "replace")) != approval.get("diff_sha256"):
        return False, None

    prompt = None
    result = None
    for source in evidence_sources:
        pm_dir = core.state_dir(source) / ".pm-review"
        prompt_path = pm_dir / f"prompt-code-{head[:12]}.txt"
        result_path = pm_dir / f"result-code-{head[:12]}.json"
        try:
            candidate_prompt = prompt_path.read_bytes()
            candidate_result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(candidate_result, dict):
            prompt, result = candidate_prompt, candidate_result
            break
    if prompt is None or result is None:
        return False, None
    reply = result.get("reply")
    if not isinstance(reply, str):
        return False, None
    if (
        _sha(prompt) != approval.get("input_hash")
        or head.encode() not in prompt
        or result.get("reviewRequestId") != approval.get("request_id")
        or result.get("replyId") != approval.get("reply_id")
        or result.get("reviewInputHash") != approval.get("input_hash")
        or not _accept(result)[0]
        or _sha(reply.encode("utf-8")) != approval.get("reply_sha256")
    ):
        return False, None
    if expected_chain:
        chain_packet = (
            "Validated approval chain (oldest first):\n" + _approval_chain_lines(expected_chain)
        ).encode("utf-8")
        if chain_packet not in prompt:
            return False, None
    diff_start = prompt.find(DIFF_OPEN.encode())
    if diff_start < 0 or _sha(prompt[diff_start + len(DIFF_OPEN.encode()):]) != approval.get("diff_in_prompt_sha256"):
        return False, None

    artifacts = approval.get("artifacts")
    if not isinstance(artifacts, dict) or any(
        not isinstance(name, str) or not name or not isinstance(expected, str) or not expected
        for name, expected in artifacts.items()
    ):
        return False, None
    if any(expected not in _git_blob_shas(project, head, name) for name, expected in artifacts.items()):
        return False, None
    evidence_sha = approval.get("evidence_sha256")
    if evidence_sha is not None and (
        not isinstance(evidence_sha, str)
        or evidence_sha not in _git_blob_shas(project, head, evidence.FILE)
    ):
        return False, None

    markdown_path = approval.get("approval_markdown_path")
    markdown_sha = approval.get("approval_markdown_sha256")
    if historical or markdown_path is not None or markdown_sha is not None:
        if (
            markdown_path != _approval_history_path(head)
            or not isinstance(markdown_sha, str)
            or not markdown_sha
        ):
            return False, None
        for source in evidence_sources:
            path = core.state_dir(source) / markdown_path
            try:
                markdown = path.read_bytes()
            except OSError:
                continue
            if (
                _sha(markdown) == markdown_sha
                and _valid_approval_markdown(markdown, approval)
            ):
                return True, markdown
        return False, None
    return True, None


def _previous_approval_from(
    project: Path,
    approval_source: Path,
    evidence_sources: list[Path],
    sprint_base_sha: str,
    head_sha: str,
    allow_current_head: bool = False,
) -> dict | None:
    """Return the last approval only if its complete chain verifies to the sprint baseline."""
    jpath, mpath = _paths(approval_source, "code")
    try:
        approval = json.loads(jpath.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(approval, dict):
        return None

    chain = approval.get("approval_chain", [])
    if not isinstance(chain, list) or len(chain) >= MAX_APPROVAL_CHAIN:
        return None
    records = chain + [_approval_record(approval)]
    if any(not isinstance(record, dict) or "approval_chain" in record for record in records):
        return None
    heads = [record.get("head") for record in records]
    if any(not isinstance(value, str) or not value for value in heads) or len(set(heads)) != len(heads):
        return None

    sprint_id = (core.read_state(project) or core.read_state(approval_source) or {}).get("sprint_id")
    first_scope = records[0].get("review_scope") if records else None
    expected_base = first_scope.get("base_sha") if isinstance(first_scope, dict) else sprint_base_sha
    previous = None
    history = []
    for index, record in enumerate(records):
        valid, markdown = _valid_approval_record(
            project, evidence_sources, record, sprint_base_sha, sprint_id,
            head_sha, expected_base, previous, records[:index], index < len(records) - 1,
            allow_current_head and index == len(records) - 1,
        )
        if not valid:
            return None
        if markdown is not None:
            history.append({
                "path": record.get("approval_markdown_path") or _approval_history_path(record["head"]),
                "bytes": markdown,
            })
        expected_base = core.git(project, "rev-parse", "--verify", f"{record['head']}^{{commit}}").strip()
        previous = record

    try:
        latest_markdown = mpath.read_bytes()
    except OSError:
        return None
    if not _valid_approval_markdown(latest_markdown, approval):
        return None
    latest_hash = _sha(latest_markdown)
    if approval.get("approval_markdown_sha256") not in (None, latest_hash):
        return None
    if approval.get("approval_markdown_path") not in (None, _approval_history_path(approval["head"])):
        return None
    if not history or history[-1]["path"] != _approval_history_path(approval["head"]):
        history.append({"path": _approval_history_path(approval["head"]), "bytes": latest_markdown})
    approval["approval_markdown_path"] = _approval_history_path(approval["head"])
    approval["approval_markdown_sha256"] = latest_hash
    approval["approval_chain"] = chain
    approval["_approval_history"] = history
    return approval


def _previous_approval(
    project: Path,
    approval_source: Path,
    sprint_base_sha: str,
    head_sha: str,
) -> dict | None:
    """Find valid prior approval evidence in the candidate or registered checkout."""
    sources = [project]
    if approval_source.resolve() != project.resolve():
        sources.append(approval_source)
    for source in sources:
        approval = _previous_approval_from(project, source, sources, sprint_base_sha, head_sha)
        if approval is not None:
            return approval
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
            review_cwd: Path | None = None, task_base: str | None = None,
            task_id: str | None = None, predecessor_task: str | None = None) -> int:
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
    sprint_base_sha = core.git(project, "rev-parse", "--verify", f"{base}^{{commit}}").strip()
    artifact_snapshot = core.artifact_digests(project) if kind == "code" else {}
    state_path = sd / "state.json"
    if kind == "code" and state_path.is_file():
        artifact_snapshot["state.json"] = _sha(state_path.read_bytes())
    uncommitted_artifacts = [
        name for name, expected in artifact_snapshot.items()
        if expected not in _git_blob_shas(project, head_sha, name)
    ]
    if uncommitted_artifacts:
        print("REFUSED: acceptance artifacts are not present in the committed HEAD: "
              + ", ".join(uncommitted_artifacts[:10]))
        return 2
    previous = _previous_approval(project, review_cwd, sprint_base_sha, head_sha) if kind == "code" else None
    task_scope = None
    if task_base:
        if kind != "code" or not task_id or not task_id.strip() or not predecessor_task or not predecessor_task.strip():
            print("REFUSED: --task-base requires --task-id and --predecessor-task for code review.")
            return 2
        try:
            task_base_sha = core.git(project, "rev-parse", "--verify", f"{task_base}^{{commit}}").strip()
        except RuntimeError:
            print(f"REFUSED: task review base {task_base!r} does not resolve to a commit.")
            return 2
        in_sprint = subprocess.run(["git", "-C", str(project), "merge-base", "--is-ancestor", sprint_base_sha, task_base_sha]).returncode == 0
        before_head = subprocess.run(["git", "-C", str(project), "merge-base", "--is-ancestor", task_base_sha, head_sha]).returncode == 0
        if not in_sprint or not before_head:
            print("REFUSED: task review base must be in the sprint ancestry and before HEAD.")
            return 2
        if _trusted_sprint_start(project, head_sha) != sprint_base_sha:
            print("REFUSED: task-scoped review requires --base to match the recorded sprint start HEAD.")
            return 2
        try:
            evidence_data = json.loads((sd / evidence.FILE).read_text(encoding="utf-8"))
            task_record = evidence_data.get("task_exact_heads", {}).get(task_id.strip())
            task_head = core.git(project, "rev-parse", "--verify", f"{task_record['head']}^{{commit}}").strip()
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError):
            print("REFUSED: current task lacks an exact committed-head record in verify-evidence.json.")
            return 2
        task_after_base = subprocess.run(["git", "-C", str(project), "merge-base", "--is-ancestor", task_base_sha, task_head]).returncode == 0
        task_before_head = subprocess.run(["git", "-C", str(project), "merge-base", "--is-ancestor", task_head, head_sha]).returncode == 0
        if not task_after_base or not task_before_head:
            print("REFUSED: recorded implementation HEAD is outside the task-base-to-candidate range.")
            return 2
        task_paths = set(core.git(project, "diff", "--name-only", f"{task_base_sha}...{task_head}").splitlines())
        candidate_paths = set(core.git(project, "diff", "--name-only", f"{task_base_sha}...{head_sha}").splitlines())
        if not task_paths or not task_paths.issubset(candidate_paths) or any(
            path not in task_paths and not path.startswith("docs/sdlc/") for path in candidate_paths
        ):
            print("REFUSED: scoped range has changes outside the recorded task delta and its SDLC evidence.")
            return 2
        if previous is not None and previous["head"] != task_base_sha:
            previous = None
        if previous is None:
            if task_base_sha != sprint_base_sha:
                print("REFUSED: without a valid approval at --task-base, scoped review must start at the configured sprint baseline.")
                return 2
            base_anchor = "sprint-base"
        else:
            base_anchor = "approval"
        review_base = task_base_sha
        task_scope = {
            "type": "task", "id": task_id.strip(), "base_sha": task_base_sha,
            "task_head": task_head, "predecessor_task": predecessor_task.strip(),
            "base_anchor": base_anchor,
        }
    else:
        if task_id or predecessor_task:
            print("REFUSED: --task-id and --predecessor-task require --task-base.")
            return 2
        review_base = previous["head"] if previous else base
    if task_scope:
        task_scope["sprint_base_sha"] = sprint_base_sha
        if not _valid_task_scope(project, task_scope, head_sha, sprint_base_sha):
            print("REFUSED: task-scope evidence or exact path range is not valid at this HEAD.")
            return 2
    pm_dir = sd / ".pm-review"
    pm_dir.mkdir(parents=True, exist_ok=True)
    packet = pm_dir / f"packet-{kind}-{head_sha[:12]}.md"
    packet.write_bytes(
        build_packet(project, kind, base, review_base, head_sha, previous, task_scope).encode("utf-8")
    )  # LF bytes, no newline translation
    cmd = _review_cmd(node, review_js, review_cwd, review_base, head_sha, packet, project_id)

    prompt = _expected_prompt(cmd, pm_dir / f"prompt-{kind}-{head_sha[:12]}.txt")
    if prompt is None:
        print("REFUSED: could not pre-compute the review prompt (review.js dump mode unavailable); "
              "the returned input hash could not be bound. No review sent.")
        return 2
    packet_text = packet.read_bytes().decode("utf-8")
    if packet_text.strip() not in prompt or head_sha not in prompt:
        print("REFUSED: the pre-computed prompt does not contain the evidence packet and the exact head.")
        return 2
    prompt_size = len(prompt.encode("utf-8"))
    if prompt_size > MAX_REVIEW_PROMPT_BYTES:
        print(
            f"REFUSED: prepared PM review prompt is {prompt_size} bytes; the safe limit is "
            f"{MAX_REVIEW_PROMPT_BYTES}. No review was sent and no approval was recorded."
        )
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
    review_base_sha = core.git(project, "rev-parse", f"{review_base}^{{commit}}").strip()
    ev_json = sd / evidence.FILE
    previous_record = None
    approval_chain = []
    if previous:
        previous_record = _approval_summary(previous)
        approval_chain = list(previous.get("approval_chain", [])) + [_approval_record(previous)]
    approval = {
        "approval_id": f"PMG-{core.now_iso()[:10].replace('-', '')}-{head_sha[:8]}",
        "kind": kind,
        "head": head_sha,
        "base": review_base,
        "base_sha": review_base_sha,
        "sprint_base": base,
        "sprint_base_sha": sprint_base_sha,
        "review_scope": task_scope,
        "previous_approval": previous_record,
        "approval_chain": approval_chain,
        "verdict": result["verdict"],
        "request_id": result["reviewRequestId"],
        "reply_id": result["replyId"],
        "input_hash": result["reviewInputHash"],
        "expected_input_hash": expected_hash,
        "diff_sha256": _sha(core.git(project, "diff", f"{review_base_sha}...{head_sha}").encode("utf-8", "replace")),
        "diff_in_prompt_sha256": _sha(diff_in_prompt.encode("utf-8")),
        "evidence_sha256": _sha(ev_json.read_bytes()) if ev_json.is_file() else None,
        "sprint_id": (core.read_state(project) or {}).get("sprint_id"),
        "artifacts": artifact_snapshot,
        "reply_sha256": _sha((result.get("reply") or "").encode("utf-8")),
        "recorded": core.now_iso(),
        "reviewer": "GPT-PM via PM Bridge review.js",
    }
    if kind == "code":
        approval["approval_markdown_path"] = _approval_history_path(head_sha)
    markdown_bytes = _approval_markdown(approval)
    if kind == "code":
        approval["approval_markdown_sha256"] = _sha(markdown_bytes)
        if previous:
            for item in previous.get("_approval_history", []):
                if not _write_immutable_history(project, item["path"], item["bytes"]):
                    print("REFUSED: historical approval Markdown changed or could not be preserved; no approval recorded.")
                    return 2
        if not _write_immutable_history(
            project, approval["approval_markdown_path"], markdown_bytes,
        ):
            print("REFUSED: current approval Markdown history could not be recorded; no approval recorded.")
            return 2
    jpath, mpath = _paths(project, kind)
    jpath.write_text(json.dumps(approval, indent=2) + "\n", encoding="utf-8")
    mpath.write_bytes(markdown_bytes)
    scope_note = f" task={task_scope['id']}" if task_scope else ""
    print(f"APPROVED: {approval['approval_id']} head={head_sha} reviewed_from={review_base_sha}{scope_note}")
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
    task_scope = a.get("review_scope")
    if task_scope is not None:
        try:
            sprint_base_sha = a.get("sprint_base_sha")
            diff = core.git(project, "diff", f"{a['base_sha']}...{a['head']}").encode("utf-8", "replace")
            markdown = mpath.read_bytes()
        except (KeyError, OSError, RuntimeError):
            return False, "task approval range or Markdown receipt is missing"
        if (
            not isinstance(task_scope, dict)
            or not isinstance(sprint_base_sha, str) or not sprint_base_sha
            or not _valid_task_scope(project, task_scope, cur, sprint_base_sha)
            or _sha(diff) != a.get("diff_sha256")
            or not _valid_approval_markdown(markdown, a)
        ):
            return False, "task approval scope does not match its exact task base and Git range"
        chain = _previous_approval_from(
            project, project, [project], sprint_base_sha, cur, allow_current_head=True,
        )
        if chain is None or chain.get("head") != cur:
            return False, "task approval is not the validated exact-head root or tip of its approval chain"
    if not (a.get("request_id") and a.get("reply_id")):
        return False, "approval lacks correlated ids"
    if not mpath.is_file() or a["head"] not in mpath.read_text(encoding="utf-8"):
        return False, f"{mpath.name} missing or does not match approval.json"
    recorded = a.get("artifacts") or {}
    if recorded:
        now = core.artifact_digests(project)
        state_path = core.state_dir(project) / "state.json"
        if state_path.is_file():
            now["state.json"] = _sha(state_path.read_bytes())
        changed = sorted(k for k in set(recorded) | set(now) if recorded.get(k) != now.get(k))
        if changed:
            return False, f"artifacts changed after the approval: {', '.join(changed[:5])}"
    dirty = core.tracked_dirty(project)
    if dirty:
        return False, "tracked changes are uncommitted after the approval"
    return True, f"{a['approval_id']} head={cur}"
