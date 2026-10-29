"""Shared helpers for the Agentic_Framework functional tests (stdlib only, deterministic)."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
CLI = TOOLS / "af_cli.py"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from af import core, deploy, hook, pm_review  # noqa: E402,F401

GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
GIT_ENV.pop("AF_PM_REVIEW_JS", None)

# The push/PR block is OFF by default in the product (phase-map push_gate.enabled=false). The gate behaviour
# tests (hook, pre-push, hardening, round tests) need it ON, so the suite enables it explicitly through the
# environment here, for in-process calls (os.environ) and for subprocesses (GIT_ENV). Tests of the DEFAULT
# configuration use `gate_default_env()` / `default_gate()` below to clear it again.
os.environ["AF_PUSH_GATE"] = "on"
GIT_ENV["AF_PUSH_GATE"] = "on"
DEFAULT_GATE_ENV = {"AF_PUSH_GATE": ""}   # pass as run_cli(..., env=DEFAULT_GATE_ENV): empty value = not enabled


import contextlib as _contextlib


@_contextlib.contextmanager
def default_gate():
    """In-process: run with the product default (no AF_PUSH_GATE override)."""
    saved = os.environ.pop("AF_PUSH_GATE", None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ["AF_PUSH_GATE"] = saved

APPROVE = {
    "ok": True, "review_status": "RAN", "verdict": "APPROVE", "final": True, "truncated": False,
    "final_overridden": False, "correlated": True, "replyId": "reply-1", "reviewRequestId": "req-1",
    "reviewInputHash": "hash-1", "reply": "VERDICT: APPROVE\nno findings\n",
}


def _force_rmtree(path: str) -> None:
    def onerr(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onerror=onerr)


def tmpdir(testcase) -> Path:
    d = tempfile.mkdtemp(prefix="aftest-")
    testcase.addCleanup(_force_rmtree, d)
    return Path(d).resolve()


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args],
                       capture_output=True, text=True, check=True, env=GIT_ENV)
    return r.stdout


def make_repo(testcase) -> Path:
    repo = tmpdir(testcase)
    git(repo, "init", "-q")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "init")
    return repo


def commit_file(repo: Path, name: str = "f.txt", content: str = "x\n") -> str:
    (repo / name).write_text(content, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", f"change {name}")
    return git(repo, "rev-parse", "HEAD").strip()


def first_commit(repo: Path) -> str:
    return git(repo, "rev-list", "--max-parents=0", "HEAD").strip()


def run_cli(repo: Path, *args: str, stdin: str | None = None, env: dict | None = None):
    e = dict(GIT_ENV)
    if env:
        e.update(env)
    return subprocess.run([sys.executable, str(CLI), *args], cwd=str(repo), input=stdin,
                          capture_output=True, text=True, env=e, timeout=60)


TEST_SID = "abc123def456"


def set_state(repo: Path, phase: int = 1, mode: str = "hard", paused: bool = False, title: str = "T",
              sid: str | None = TEST_SID) -> None:
    """Write a sprint state. `sid=None` writes a LEGACY state (no sprint_id)."""
    st = {"title": title, "phase": phase, "mode": mode, "paused": paused, "history": []}
    if sid:
        st["sprint_id"] = sid
    core.write_state(repo, st)


def sdlc(repo: Path) -> Path:
    return repo / "docs" / "sdlc"


def sprint_id(repo: Path) -> str | None:
    st = core.read_state(repo)
    return (st or {}).get("sprint_id")


def write_artifact(repo: Path, rel: str, text: str = "x" + chr(10), stamp: bool | str = True) -> None:
    """Write a phase artifact; by default it is stamped with the current sprint id (`stamp=False` or a custom id)."""
    f = sdlc(repo) / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    sid = stamp if isinstance(stamp, str) else (sprint_id(repo) if stamp else None)
    if sid:
        text = text + chr(10) + "Sprint: " + sid + chr(10)
    f.write_text(text, encoding="utf-8")


PHASE_1_7 = ["requirements.md", "backlog.md", "design.md", "test-plan.md", "review-record.md",
             "change-records/c1.md", "verify-evidence.md"]


def stamp_phases_1_7(repo: Path) -> None:
    for rel in PHASE_1_7:
        write_artifact(repo, rel)


def write_evidence(repo: Path, tested_head: str | None = None, **over) -> dict:
    """Write a compliant verify-evidence.json (tested_head defaults to the repo HEAD)."""
    d = {"tested_head": tested_head or core.head(repo),
         "runs": [{"command": "python -m unittest discover -s tests", "total": 10, "passed": 9, "failed": 0,
                   "errors": 0, "skipped": 1}],
         "not_run": [{"item": "real schtasks", "reason": "needs admin"}],
         "findings": {"open_blocker": 0, "open_major": 0},
         "reviewers": [{"role": "code-reviewer", "model": "sonnet", "effort": "medium", "verdict": "APPROVE"}]}
    d.update(over)
    f = sdlc(repo) / "verify-evidence.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return d


def write_approval(repo: Path, kind: str = "code", head: str | None = None, verdict: str = "APPROVE",
                   request_id: str | None = "q1", reply_id: str | None = "r1",
                   md: str | None = "default") -> str:
    """Hand-craft an approval pair (used to probe verify/gate independent of request())."""
    h = head or core.head(repo)
    a = {"approval_id": "PMG-TEST", "kind": kind, "head": h, "verdict": verdict,
         "request_id": request_id, "reply_id": reply_id}
    pm = sdlc(repo) / ".pm-review"
    pm.mkdir(parents=True, exist_ok=True)
    jname, mname = ("approval.json", "gate-approval.md") if kind == "code" else ("approval-docs.json", "docs-approval.md")
    (pm / jname).write_text(json.dumps(a), encoding="utf-8")
    if md is not None:
        text = f"Head: {h}\n" if md == "default" else md
        if sprint_id(repo) and md == "default":
            text += "Sprint: " + sprint_id(repo) + "\n"
        (sdlc(repo) / mname).write_text(text, encoding="utf-8")
    return h


FAKE_REVIEW_JS = r"""
const fs = require('fs'); const cp = require('child_process');
const cfg = JSON.parse(fs.readFileSync(process.env.FAKE_CFG, 'utf8'));
const crypto = require('crypto');
const argv = process.argv.slice(2);
const arg = (n) => { const k = argv.indexOf(n); return k >= 0 ? argv[k + 1] : null; };
const dumpFile = process.env.PM_BRIDGE_DEBUG_DUMP_PROMPT;
const dumpOnly = process.env.PM_BRIDGE_DEBUG_DUMP_PROMPT_ONLY === '1';
const mode = cfg.dump_mode || 'ok';   // ok | empty (dump-only writes nothing) | ignored (env not honoured) | wrong (prompt lacks packet/head)
const log = (what) => { if (cfg.calls_out) fs.appendFileSync(cfg.calls_out, what + '\n'); };
function buildPrompt() {
  const cwd = arg('--cwd'), base = arg('--base');
  const raw = !!cfg.raw_bytes;   // raw_bytes: no newline normalisation (exact bytes), optionally CRLF injected into the diff
  let packet = fs.readFileSync(arg('--scope-note-file'), 'utf8');
  const head = cp.execSync('git -C "' + cwd + '" rev-parse HEAD').toString().trim();
  let diff = cp.execSync('git -C "' + cwd + '" diff ' + base + '...' + head).toString();
  if (!raw) { packet = packet.replace(/\r\n/g, '\n'); diff = diff.replace(/\r\n/g, '\n'); }
  if (cfg.inject_crlf) diff = diff.replace(/\r?\n/g, '\r\n');
  if (mode === 'wrong') return 'REVIEW PROMPT without the packet\n';
  return 'REVIEW PROMPT\n' + packet + '\nHead: ' + head + '\nDiff:\n```diff\n' + diff + '\n```\n';
}
if (dumpFile && dumpOnly && mode !== 'ignored') {
  log('dump');
  fs.writeFileSync(cfg.argv_out, JSON.stringify(argv));
  if (mode !== 'empty') fs.writeFileSync(dumpFile, buildPrompt());
  process.exit(0);
}
log('real');
fs.writeFileSync(cfg.argv_out, JSON.stringify(argv));
const i = argv.indexOf('--scope-note-file');
if (i >= 0) fs.copyFileSync(argv[i + 1], cfg.packet_out);
if (cfg.commit_in) cp.execSync('git -C "' + cfg.commit_in + '" -c user.name=t -c user.email=t@t commit --allow-empty -q -m moved');
if (cfg.raw !== undefined) { process.stdout.write(cfg.raw); process.exit(cfg.exit || 0); }
const result = Object.assign({}, cfg.result);
if (!cfg.keep_hash && mode !== 'ignored') {
  result.reviewInputHash = cfg.bad_hash || crypto.createHash('sha256').update(buildPrompt(), 'utf8').digest('hex');
}
console.log('some log noise before the json line');
console.log(JSON.stringify(result));
"""
