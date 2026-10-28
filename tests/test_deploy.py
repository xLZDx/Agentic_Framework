import json
import tomllib
import unittest
from pathlib import Path

import afhelpers as H
from afhelpers import ROOT, deploy

CFG = json.loads((ROOT / "core" / "framework.json").read_text(encoding="utf-8"))
DEPLOY = ROOT / "deploy"


def snapshot(base: Path) -> dict:
    return {str(p.relative_to(base)): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file()}


class ParseAgent(unittest.TestCase):
    def _write(self, text):
        d = H.tmpdir(self)
        f = d / "a.md"
        f.write_bytes(text.encode("utf-8"))
        return f

    def test_folded_multiline_description_is_joined(self):
        meta, body = deploy.parse_agent(ROOT / "core" / "agents" / "functional-test-reviewer.md")
        d = meta["description"]
        self.assertTrue(d.startswith("Behavioral test reviewer and author"))
        self.assertIn("isolation, concurrency/retry cases and integration seams", d)  # continuation line 2
        self.assertTrue(d.endswith("functional tests for each epic."))  # continuation line 3
        self.assertNotIn("\n", d)
        self.assertEqual(meta["name"], "functional-test-reviewer")
        self.assertIn("Read", meta["tools"])
        self.assertTrue(body.strip())

    def test_description_with_colon_keeps_full_value(self):
        f = self._write("---\nname: x\ndescription: Use when: reviewing; note: colons\nmodel: opus\n---\nBODY\n")
        meta, body = deploy.parse_agent(f)
        self.assertEqual(meta["description"], "Use when: reviewing; note: colons")
        self.assertEqual(meta["model"], "opus")
        self.assertEqual(body, "BODY\n")

    def test_lists_bom_and_crlf(self):
        f = self._write("﻿---\r\nname: x\r\ndescription: d\r\ntools:\r\n- A\r\n- B\r\n---\r\nBODY\r\n")
        meta, body = deploy.parse_agent(f)
        self.assertEqual(meta["tools"], ["A", "B"])
        self.assertEqual(meta["name"], "x")
        self.assertIn("BODY", body)

    def test_missing_frontmatter_raises(self):
        with self.assertRaises(ValueError):
            deploy.parse_agent(self._write("no frontmatter here\n"))

    def test_rendering_roundtrips_colon_and_quotes(self):
        tgt = {"model": "sonnet", "effort": "medium"}
        meta = {"name": "x", "description": 'He said "hi": ok; a\\b', "tools": ["Read"]}
        md = deploy.render_claude_agent(meta, "body\n", tgt)
        parsed, _ = deploy.parse_agent(self._write(md))
        self.assertEqual(json.loads(parsed["description"]), meta["description"])
        self.assertEqual(parsed["tools"], ["Read"])
        t = tomllib.loads(deploy.render_codex_agent(meta, "\nbody line\n\n", {"model": "gpt-6-luna", "effort": "medium"}))
        self.assertEqual(t["description"], meta["description"])
        self.assertEqual(t["developer_instructions"], "body line")


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.written = deploy.build()

    def test_every_bundled_agent_claude(self):
        self.assertTrue(CFG["bundled_agents"])
        for name in CFG["bundled_agents"]:
            with self.subTest(agent=name):
                f = DEPLOY / "claude" / "agents" / f"{name}.md"
                self.assertTrue(f.is_file())
                meta, body = deploy.parse_agent(f)
                self.assertEqual(meta["name"], name)
                self.assertEqual(meta["model"], "sonnet")
                self.assertEqual(meta["effort"], "medium")
                self.assertTrue(meta["maxTurns"].isdigit())
                desc = json.loads(meta["description"])  # must be a valid single-line JSON string
                self.assertGreater(len(desc.strip()), 20)
                src_meta, src_body = deploy.parse_agent(ROOT / "core" / "agents" / f"{name}.md")
                self.assertEqual(desc, src_meta["description"])
                self.assertEqual(body.strip(), src_body.strip())
                self.assertEqual(meta.get("tools", []), src_meta.get("tools", []))

    def test_every_bundled_agent_codex(self):
        for name in CFG["bundled_agents"]:
            with self.subTest(agent=name):
                f = DEPLOY / "codex" / "agents" / f"{name}.toml"
                self.assertTrue(f.is_file())
                t = tomllib.loads(f.read_text(encoding="utf-8"))
                self.assertEqual(t["name"], name)
                self.assertEqual(t["model"], "gpt-6-luna")
                self.assertEqual(t["model_reasoning_effort"], "medium")
                src_meta, src_body = deploy.parse_agent(ROOT / "core" / "agents" / f"{name}.md")
                self.assertEqual(t["description"], src_meta["description"])
                self.assertEqual(t["developer_instructions"], src_body.strip())

    def test_no_unlisted_agents_deployed(self):
        for target, ext in (("claude", "md"), ("codex", "toml")):
            got = {p.stem for p in (DEPLOY / target / "agents").glob(f"*.{ext}")}
            self.assertEqual(got, set(CFG["bundled_agents"]), target)

    def test_all_bundled_skills_copied_identically(self):
        for target in ("claude", "codex"):
            for name in CFG["bundled_skills"]:
                with self.subTest(target=target, skill=name):
                    src = ROOT / "core" / "skills" / name
                    dst = DEPLOY / target / "skills" / name
                    self.assertTrue((dst / "SKILL.md").is_file())
                    self.assertEqual(snapshot(src), snapshot(dst))

    def test_phase_map_copied_and_fragments_written(self):
        for target, frag in (("claude", "CLAUDE.fragment.md"), ("codex", "AGENTS.fragment.md")):
            self.assertEqual((DEPLOY / target / "phase-map.json").read_bytes(),
                             (ROOT / "core" / "orchestration" / "phase-map.json").read_bytes())
            text = (DEPLOY / target / frag).read_text(encoding="utf-8")
            self.assertIn("af_cli.py pm-review --kind code", text)
        self.assertIn("Claude", (DEPLOY / "claude" / "CLAUDE.fragment.md").read_text(encoding="utf-8"))
        self.assertIn("GPT/Codex", (DEPLOY / "codex" / "AGENTS.fragment.md").read_text(encoding="utf-8"))

    def test_settings_hooks_json(self):
        data = json.loads((DEPLOY / "claude" / "settings.hooks.json").read_text(encoding="utf-8"))
        hooks = data["hooks"]
        self.assertEqual(set(hooks), {"SessionStart", "UserPromptSubmit", "PreToolUse"})
        for ev, entries in hooks.items():
            cmd = entries[0]["hooks"][0]
            self.assertEqual(cmd["type"], "command")
            self.assertTrue(cmd["command"].endswith("af_cli.py hook"))
        self.assertEqual(hooks["PreToolUse"][0]["matcher"], "Bash")
        self.assertNotIn("matcher", hooks["SessionStart"][0])
        self.assertFalse((DEPLOY / "codex" / "settings.hooks.json").exists())

    def test_build_returns_every_written_path_and_they_exist(self):
        self.assertTrue(self.written)
        for rel in self.written:
            self.assertTrue((ROOT / rel).exists(), rel)
        self.assertIn("deploy/claude/settings.hooks.json", self.written)

    def test_build_is_idempotent_and_cleans_stale_files(self):
        before = snapshot(DEPLOY)
        stale = DEPLOY / "claude" / "agents" / "zz-stale.md"
        stale.write_text("stale", encoding="utf-8")
        deploy.build()
        self.assertFalse(stale.exists())
        self.assertEqual(snapshot(DEPLOY), before)

    def test_cli_deploy_prints_written_paths(self):
        r = H.run_cli(ROOT, "deploy")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.strip().splitlines()
        self.assertEqual(len(lines), len(self.written))
        self.assertIn("deploy/claude/settings.hooks.json", lines)


class CoreConsistency(unittest.TestCase):
    def test_phase_map_roles_and_skills_are_known(self):
        known_a = set(CFG["bundled_agents"]) | set(CFG["external_agents"])
        known_s = set(CFG["bundled_skills"]) | set(CFG["external_skills"])
        for p in H.core.load_phase_map()["phases"]:
            for r in p["roles"]:
                self.assertIn(r, known_a, f"phase {p['n']} role {r}")
            for s in p["skills"]:
                self.assertIn(s, known_s, f"phase {p['n']} skill {s}")

    def test_bundled_sources_exist(self):
        for a in CFG["bundled_agents"]:
            self.assertTrue((ROOT / "core" / "agents" / f"{a}.md").is_file(), a)
        for s in CFG["bundled_skills"]:
            self.assertTrue((ROOT / "core" / "skills" / s / "SKILL.md").is_file(), s)


if __name__ == "__main__":
    unittest.main()
