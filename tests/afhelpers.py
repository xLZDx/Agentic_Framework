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


def set_state(repo: Path, phase: int = 1, mode: str = "hard", paused: bool = False, title: str = "T") -> None:
    core.write_state(repo, {"title": title, "phase": phase, "mode": mode, "paused": paused, "history": []})


def sdlc(repo: Path) -> Path:
    return repo / "docs" / "sdlc"


def write_artifact(repo: Path, rel: str, text: str = "x\n") -> None:
    f = sdlc(repo) / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")


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
        (sdlc(repo) / mname).write_text(text, encoding="utf-8")
    return h


FAKE_REVIEW_JS = r"""
const fs = require('fs'); const cp = require('child_process');
const cfg = JSON.parse(fs.readFileSync(process.env.FAKE_CFG, 'utf8'));
const argv = process.argv.slice(2);
fs.writeFileSync(cfg.argv_out, JSON.stringify(argv));
const i = argv.indexOf('--scope-note-file');
if (i >= 0) fs.copyFileSync(argv[i + 1], cfg.packet_out);
if (cfg.commit_in) cp.execSync('git -C "' + cfg.commit_in + '" -c user.name=t -c user.email=t@t commit --allow-empty -q -m moved');
if (cfg.raw !== undefined) { process.stdout.write(cfg.raw); process.exit(cfg.exit || 0); }
console.log('some log noise before the json line');
console.log(JSON.stringify(cfg.result));
"""
