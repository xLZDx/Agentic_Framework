"""Render core/ into deploy/<target>/ (claude, codex). Core stays tool-agnostic; only deploy differs."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from . import core

ROOT = core.FRAMEWORK_ROOT
NL = chr(10)
FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.S)


def parse_agent(path: Path) -> tuple[dict, str]:
    m = FM_RE.match(path.read_text(encoding="utf-8-sig"))
    if not m:
        raise ValueError(f"{path}: missing frontmatter")
    meta: dict = {}
    key = None
    last_scalar = None
    for line in m.group(1).splitlines():
        if line.startswith("- ") and key:
            meta[key].append(line[2:].strip())
        elif line[:1] in (" ", "\t") and last_scalar:
            meta[last_scalar] += " " + line.strip()
        elif ":" in line:
            k, _, val = line.partition(":")
            k, val = k.strip(), val.strip()
            if val.startswith("[") and val.endswith("]"):
                meta[k] = [v.strip().strip("\"'") for v in val[1:-1].split(",") if v.strip()]
                key, last_scalar = None, None
            elif val:
                meta[k] = val
                key, last_scalar = None, k
            else:
                meta[k] = []
                key, last_scalar = k, None
    return meta, m.group(2).lstrip("\n")


def render_claude_agent(meta: dict, body: str, tgt: dict) -> str:
    fm = ["---", f"name: {meta['name']}", f"description: {json.dumps(meta['description'])}"]
    for k in ("tools", "skills"):
        if meta.get(k):
            fm.append(f"{k}:")
            fm += [f"- {v}" for v in meta[k]]
    fm += [f"model: {tgt['model']}", f"maxTurns: {meta.get('maxTurns', '16')}", f"effort: {tgt['effort']}", "---", ""]
    return "\n".join(fm) + "\n" + body


def render_codex_agent(meta: dict, body: str, tgt: dict) -> str:
    q = json.dumps
    return (f"name = {q(meta['name'])}\nmodel = {q(tgt['model'])}\n"
            f"model_reasoning_effort = {q(tgt['effort'])}\n"
            f"description = {q(meta['description'])}\n"
            f"developer_instructions = {q(body.strip())}\n")


def build(clean: bool = True) -> list[str]:
    cfg = json.loads((ROOT / "core" / "framework.json").read_text(encoding="utf-8"))
    written: list[str] = []
    for target, tgt in cfg["targets"].items():
        out = ROOT / "deploy" / target
        if clean and out.exists():
            shutil.rmtree(out)
        (out / tgt["dest_agents"]).mkdir(parents=True, exist_ok=True)
        for name in cfg["bundled_agents"]:
            meta, body = parse_agent(ROOT / "core" / "agents" / f"{name}.md")
            render = render_claude_agent if target == "claude" else render_codex_agent
            f = out / tgt["dest_agents"] / f"{name}.{tgt['agent_ext']}"
            f.write_text(render(meta, body, tgt), encoding="utf-8")
            written.append(str(f.relative_to(ROOT)))
        for name in cfg["bundled_skills"]:
            dst = out / tgt["dest_skills"] / name
            shutil.copytree(ROOT / "core" / "skills" / name, dst)
            written.append(str(dst.relative_to(ROOT)))
        af_cmd = (ROOT / "core" / "commands" / "af.md").read_text(encoding="utf-8")
        desc = "Toggle and inspect the Agentic_Framework SDLC orchestration: on, off, status, next, pm-review, verify."
        if target == "claude":
            d = out / "skills" / "af"
            d.mkdir(parents=True, exist_ok=True)
            head = ["---", "name: af", f"description: {json.dumps(desc)}", "disable-model-invocation: true",
                    "argument-hint: on|off|status|next|verify", "---", ""]
            (d / "SKILL.md").write_text(NL.join(head) + NL + af_cmd, encoding="utf-8")
            written.append("deploy/claude/skills/af")
        else:
            (out / "prompts").mkdir(parents=True, exist_ok=True)
            head = ["---", f"description: {json.dumps(desc)}", "argument-hint: on|off|status|next|verify", "---", ""]
            (out / "prompts" / "af.md").write_text(
                NL.join(head) + NL + af_cmd + NL + "Arguments: $ARGUMENTS" + NL, encoding="utf-8")
            written.append("deploy/codex/prompts/af.md")
        shutil.copy(ROOT / "core" / "orchestration" / "phase-map.json", out / "phase-map.json")
        written.append(str((out / "phase-map.json").relative_to(ROOT)))
        frag = out / ("CLAUDE.fragment.md" if target == "claude" else "AGENTS.fragment.md")
        frag.write_text(routing_fragment(target), encoding="utf-8")
        written.append(str(frag.relative_to(ROOT)))
    if "claude" in cfg["targets"]:
        (ROOT / "deploy" / "claude" / "settings.hooks.json").write_text(
            json.dumps(claude_hooks(), indent=2) + "\n", encoding="utf-8")
        written.append("deploy/claude/settings.hooks.json")
    return written


def routing_fragment(target: str) -> str:
    pm = ("python {fw}/tools/af_cli.py pm-review --kind code --base <sprint base ref>")
    return (
        "## Agentic_Framework SDLC (auto-orchestration)\n\n"
        f"The main {'Claude' if target == 'claude' else 'GPT/Codex'} session is the Scrum Master. "
        "Run `python {fw}/tools/af_cli.py status` from the project, launch the listed roles as real agents "
        "(never role-play in chat), and advance with `af_cli.py next`.\n\n"
        "- Features, bugs and multi-file changes: `af_cli.py start \"<title>\"`. Questions and one-line fixes: answer directly.\n"
        f"- Before push/PR: phase 8 requires PM-GPT review and approval of the exact HEAD: `{pm}`.\n"
        "- Never hand-write `gate-approval.md`. A new commit invalidates the approval.\n"
        "- Replace `{fw}` with the Agentic_Framework checkout path (D:\\Repo\\Agentic_Framework).\n"
    )


def claude_hooks() -> dict:
    cmd = "python {fw}/tools/af_cli.py hook"
    h = lambda extra=None: [dict({"hooks": [{"type": "command", "command": cmd}]}, **(extra or {}))]
    return {"hooks": {
        "SessionStart": h(), "UserPromptSubmit": h(), "PreToolUse": h({"matcher": "Bash"}),
    }}
