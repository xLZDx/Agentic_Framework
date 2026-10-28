"""Deploy of the 42 bundled/imported agents, bundled skills, and the /af command."""
import json
import re
import tomllib
import unittest
from pathlib import Path

import afhelpers as H
from afhelpers import ROOT, deploy

CFG = json.loads((ROOT / "core" / "framework.json").read_text(encoding="utf-8"))
DEPLOY = ROOT / "deploy"
AGENTS = CFG["bundled_agents"]
SKILLS = CFG["bundled_skills"]


def source_tools(name: str) -> list:
    """Independent parse of the tools field from the raw source (inline list or dash list)."""
    text = (ROOT / "core" / "agents" / f"{name}.md").read_text(encoding="utf-8-sig")
    fm = re.match(r"\A---\r?\n(.*?)\r?\n---", text, re.S).group(1).splitlines()
    for i, line in enumerate(fm):
        if line.startswith("tools:"):
            rest = line[len("tools:"):].strip()
            if rest.startswith("["):
                return [t.strip().strip("\"'") for t in rest.strip("[]").split(",") if t.strip()]
            out = []
            for nxt in fm[i + 1:]:
                if nxt.startswith("- "):
                    out.append(nxt[2:].strip())
                else:
                    break
            return out
    return []


def claude_fm(path: Path) -> dict:
    m = re.match(r"\A---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.S)
    assert m, f"no frontmatter in {path}"
    meta, key = {}, None
    for line in m.group(1).splitlines():
        if line.startswith("- "):
            meta[key].append(line[2:])
        else:
            k, _, v = line.partition(":")
            key = k
            v = v.strip()
            meta[k] = [] if not v else (json.loads(v) if v.startswith('"') else v)
    return meta


class ImportedAgents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        deploy.build()

    def test_counts(self):
        self.assertGreaterEqual(len(AGENTS), 43)
        self.assertIn("implementation-engineer", AGENTS)
        self.assertEqual(len(set(AGENTS)), len(AGENTS))
        self.assertEqual(len(SKILLS), 16)
        self.assertEqual(len(list((DEPLOY / "claude" / "agents").glob("*.md"))), len(AGENTS))
        self.assertEqual(len(list((DEPLOY / "codex" / "agents").glob("*.toml"))), len(AGENTS))

    def test_every_agent_renders_valid_claude_md(self):
        for name in AGENTS:
            with self.subTest(agent=name):
                meta = claude_fm(DEPLOY / "claude" / "agents" / f"{name}.md")
                self.assertEqual(meta["name"], name)
                self.assertTrue(meta["description"].strip())
                self.assertEqual(meta["model"], "sonnet")
                self.assertEqual(meta["effort"], deploy.agent_effort(deploy.parse_agent(ROOT / "core" / "agents" / f"{name}.md")[0], CFG["targets"]["claude"], ("low", "medium", "high")))
                self.assertTrue(meta["maxTurns"].isdigit())
                src = source_tools(name)
                if src:
                    self.assertTrue(meta["tools"])
                    self.assertEqual(meta["tools"], src)
                else:
                    self.assertNotIn("tools", meta)
                body = (DEPLOY / "claude" / "agents" / f"{name}.md").read_text(encoding="utf-8").split("\n---\n", 1)[1]
                self.assertGreater(len(body.strip()), 50)

    def test_every_agent_renders_valid_codex_toml(self):
        for name in AGENTS:
            with self.subTest(agent=name):
                d = tomllib.loads((DEPLOY / "codex" / "agents" / f"{name}.toml").read_text(encoding="utf-8"))
                self.assertEqual(d["name"], name)
                self.assertEqual(d["model"], "gpt-6-luna")
                self.assertEqual(d["model_reasoning_effort"], "medium")
                self.assertTrue(d["description"].strip())
                self.assertGreater(len(d["developer_instructions"]), 50)

    def test_source_model_opus_is_not_leaked(self):
        # architect's source says model: opus; policy forbids automatic Opus
        self.assertEqual(claude_fm(DEPLOY / "claude" / "agents" / "architect.md")["model"], "sonnet")
        for f in (DEPLOY / "claude" / "agents").glob("*.md"):
            self.assertNotIn("model: opus", f.read_text(encoding="utf-8").split("\n---\n", 1)[0], f.name)

    def test_inline_tool_lists_keep_tools(self):
        self.assertEqual(claude_fm(DEPLOY / "claude" / "agents" / "architect.md")["tools"], ["Read", "Grep", "Glob"])
        self.assertEqual(claude_fm(DEPLOY / "claude" / "agents" / "conversation-analyzer.md")["tools"],
                         ["Read", "Grep"])
        # bare (unquoted) inline list with six entries
        six = [n for n in AGENTS if source_tools(n) == ["Read", "Write", "Edit", "Bash", "Grep", "Glob"]]
        self.assertTrue(six)
        for n in six:
            self.assertEqual(claude_fm(DEPLOY / "claude" / "agents" / f"{n}.md")["tools"],
                             ["Read", "Write", "Edit", "Bash", "Grep", "Glob"])

    def test_parse_agent_inline_list_unit(self):
        d = H.tmpdir(self)
        f = d / "a.md"
        f.write_text('---\nname: a\ndescription: x\ntools: [Read, "Grep",  Glob]\nmodel: sonnet\n---\nbody\n',
                     encoding="utf-8")
        meta, body = deploy.parse_agent(f)
        self.assertEqual(meta["tools"], ["Read", "Grep", "Glob"])
        self.assertEqual(meta["model"], "sonnet")  # key after the inline list is not swallowed
        self.assertEqual(body.strip(), "body")

    def test_agent_without_tools_has_no_tools_key(self):
        self.assertEqual(source_tools("ml-engineer"), [])
        self.assertNotIn("tools", claude_fm(DEPLOY / "claude" / "agents" / "ml-engineer.md"))

    def test_policy_file_not_deployed_as_agent(self):
        self.assertTrue((ROOT / "core" / "policies" / "autonomous-completion.md").is_file())
        self.assertNotIn("autonomous-completion", AGENTS)
        for target, ext in (("claude", "md"), ("codex", "toml")):
            self.assertFalse((DEPLOY / target / "agents" / f"autonomous-completion.{ext}").exists())
        for p in DEPLOY.rglob("*"):
            self.assertNotIn("autonomous-completion", p.name)

    def test_no_stray_agents_beyond_bundled(self):
        self.assertEqual({p.stem for p in (DEPLOY / "claude" / "agents").glob("*.md")}, set(AGENTS))
        self.assertEqual({p.stem for p in (DEPLOY / "codex" / "agents").glob("*.toml")}, set(AGENTS))


class SkillsAndCommand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        deploy.build()

    def test_every_bundled_skill_in_both_targets_with_skill_md(self):
        for target in ("claude", "codex"):
            for s in SKILLS:
                with self.subTest(target=target, skill=s):
                    d = DEPLOY / target / "skills" / s
                    self.assertTrue(d.is_dir())
                    self.assertTrue((d / "SKILL.md").is_file())
                    self.assertEqual((d / "SKILL.md").read_bytes(),
                                     (ROOT / "core" / "skills" / s / "SKILL.md").read_bytes())

    def test_claude_af_skill(self):
        f = DEPLOY / "claude" / "skills" / "af" / "SKILL.md"
        text = f.read_text(encoding="utf-8")
        m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
        self.assertTrue(m)
        meta = dict(l.split(": ", 1) for l in m.group(1).splitlines())
        self.assertEqual(meta["name"], "af")
        self.assertEqual(meta["disable-model-invocation"], "true")
        desc = json.loads(meta["description"])
        self.assertGreater(len(desc), 20)
        self.assertIn("Agentic_Framework", desc)
        self.assertIn("{fw}/tools/af_cli.py on", text)  # body from core/commands/af.md is included
        self.assertIn("Toggle and inspect", text)

    def test_af_is_user_only_and_not_in_codex_skills(self):
        self.assertNotIn("af", SKILLS)
        self.assertFalse((DEPLOY / "codex" / "skills" / "af").exists())

    def test_codex_prompt_has_arguments_placeholder(self):
        f = DEPLOY / "codex" / "prompts" / "af.md"
        text = f.read_text(encoding="utf-8")
        self.assertIn("$ARGUMENTS", text)
        m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
        self.assertTrue(m)
        self.assertIn("description:", m.group(1))
        self.assertIn("af_cli.py off", text)
        self.assertNotIn("disable-model-invocation", text)

    def test_written_list_reports_af_artifacts(self):
        w = deploy.build()
        self.assertIn("deploy/claude/skills/af", w)
        self.assertIn("deploy/codex/prompts/af.md", w)


if __name__ == "__main__":
    unittest.main()
