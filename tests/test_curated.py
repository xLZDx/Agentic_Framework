"""Curated agents/skills import: new skills, agent->skill references, and forbidden tokens in deployed output."""
import json
import re
import sys
import tomllib
import unittest
from pathlib import Path

import afhelpers as H
from afhelpers import ROOT, deploy

CFG = json.loads((ROOT / "core" / "framework.json").read_text(encoding="utf-8"))
NEW_SKILLS = ("backend-engineer", "frontend-engineer")
FORBIDDEN = ("RJ_PROJECT_ROOT", "ADK_ROOT", "Agentic Studio")


def skill_meta(path: Path) -> dict:
    m = re.match(r"\A---\r?\n(.*?)\r?\n---", path.read_text(encoding="utf-8-sig"), re.S)
    assert m, f"no frontmatter in {path}"
    meta = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        if k and not line.startswith(" "):
            meta[k.strip()] = v.strip()
    return meta


class NewSkills(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        deploy.build()

    def test_registered_in_framework_json(self):
        for s in NEW_SKILLS:
            self.assertIn(s, CFG["bundled_skills"])
        self.assertGreaterEqual(len(CFG["bundled_skills"]), 29)

    def test_frontmatter_valid_and_name_matches_folder(self):
        for s in NEW_SKILLS:
            with self.subTest(skill=s):
                f = ROOT / "core" / "skills" / s / "SKILL.md"
                self.assertTrue(f.is_file())
                meta = skill_meta(f)
                self.assertEqual(meta["name"], s)
                self.assertGreater(len(meta["description"]), 40)
                body = f.read_text(encoding="utf-8").split("---", 2)[2]
                self.assertGreater(len(body.strip()), 200)

    def test_deployed_to_claude_and_codex_identically(self):
        for s in NEW_SKILLS:
            for target in ("claude", "codex"):
                with self.subTest(skill=s, target=target):
                    d = ROOT / "deploy" / target / "skills" / s
                    self.assertTrue((d / "SKILL.md").is_file())
                    self.assertEqual((d / "SKILL.md").read_bytes(),
                                     (ROOT / "core" / "skills" / s / "SKILL.md").read_bytes())

    def test_every_bundled_skill_folder_name_matches_its_frontmatter(self):
        for s in CFG["bundled_skills"]:
            with self.subTest(skill=s):
                self.assertEqual(skill_meta(ROOT / "core" / "skills" / s / "SKILL.md")["name"], s)


class AgentSkillReferences(unittest.TestCase):
    def test_skills_referenced_by_agents_are_bundled_or_external(self):
        known = set(CFG["bundled_skills"]) | set(CFG.get("external_skills", []))
        unresolved = {}
        checked = 0
        for name in CFG["bundled_agents"]:
            meta, _ = deploy.parse_agent(ROOT / "core" / "agents" / f"{name}.md")
            for sk in meta.get("skills") or []:
                checked += 1
                if sk not in known:
                    unresolved.setdefault(sk, []).append(name)
        self.assertGreater(checked, 0, "no agent declares skills; the check would be vacuous")
        self.assertEqual(unresolved, {}, "agent skills neither bundled nor in external_skills")

    def test_every_external_skill_is_referenced_somewhere(self):
        used = set()
        for name in CFG["bundled_agents"]:
            meta, _ = deploy.parse_agent(ROOT / "core" / "agents" / f"{name}.md")
            used.update(meta.get("skills") or [])
        pm = json.loads((ROOT / "core" / "orchestration" / "phase-map.json").read_text(encoding="utf-8"))
        used.update(sk for p in pm["phases"] for sk in p["skills"])
        for sk in CFG.get("external_skills", []):
            with self.subTest(skill=sk):
                self.assertIn(sk, used, f"external skill {sk} is referenced nowhere")

    def test_reporting_analyst_uses_state_json_as_authority(self):
        deploy.build()
        paths = [ROOT / "core" / "agents" / "reporting-analyst.md",
                 ROOT / "deploy" / "claude" / "agents" / "reporting-analyst.md",
                 ROOT / "deploy" / "codex" / "agents" / "reporting-analyst.toml"]
        for f in paths:
            with self.subTest(file=str(f.relative_to(ROOT))):
                text = f.read_text(encoding="utf-8")
                if f.suffix == ".toml":
                    text = tomllib.loads(text)["developer_instructions"]
                self.assertIn("state.json", text)
                self.assertRegex(text, r"state\.json`? \(the authority")
                for line in text.splitlines():
                    if "STATE.md" in line:
                        low = line.lower()
                        self.assertIn("state.json", line)
                        self.assertIn("generated view", low)
                        self.assertIn("authority", low)

    def test_external_skills_do_not_overlap_bundled(self):
        self.assertFalse(set(CFG["bundled_skills"]) & set(CFG.get("external_skills", [])))

    def test_agent_frontmatter_curated_fields_survive_deploy(self):
        deploy.build()
        for name in CFG["bundled_agents"]:
            src, _ = deploy.parse_agent(ROOT / "core" / "agents" / f"{name}.md")
            cl, _ = deploy.parse_agent(ROOT / "deploy" / "claude" / "agents" / f"{name}.md")
            with self.subTest(agent=name):
                self.assertEqual(cl.get("skills", []), src.get("skills", []))
                self.assertEqual(cl["maxTurns"], str(src.get("maxTurns", "16")))
                self.assertEqual(cl["model"], "sonnet")


class BundledSkillHygiene(unittest.TestCase):
    PRIVATE = ("koros", "D:" + chr(92) + "Repo", "D:/Repo", "C:" + chr(92) + "Users", "C:/Users", "{{")

    @classmethod
    def setUpClass(cls):
        deploy.build()

    def test_every_bundled_skill_deploys_to_both_targets_with_all_files(self):
        self.assertGreaterEqual(len(CFG["bundled_skills"]), 29)
        for s in CFG["bundled_skills"]:
            src = ROOT / "core" / "skills" / s
            self.assertTrue((src / "SKILL.md").is_file(), s)
            for target in ("claude", "codex"):
                with self.subTest(skill=s, target=target):
                    d = ROOT / "deploy" / target / "skills" / s
                    for f in [p for p in src.rglob("*") if p.is_file()]:
                        out = d / f.relative_to(src)
                        self.assertTrue(out.is_file(), str(out))
                        self.assertEqual(out.read_bytes(), f.read_bytes())

    def test_eleven_added_skills_present(self):
        added = ("a11y-contract", "ci-release-contract", "context-memory-hygiene", "db-change-contract",
                 "git-worktree-ops", "migration-safety", "observability-contract", "performance-testing",
                 "repo-recon", "security-evidence-contract", "ux-design-contract")
        for s in added:
            with self.subTest(skill=s):
                self.assertIn(s, CFG["bundled_skills"])
                self.assertEqual(skill_meta(ROOT / "core" / "skills" / s / "SKILL.md")["name"], s)

    def test_operator_specific_skills_are_external_not_bundled(self):
        for s in ("html-report", "financial-ml-contract"):
            self.assertIn(s, CFG["external_skills"])
            self.assertNotIn(s, CFG["bundled_skills"])
            self.assertFalse((ROOT / "deploy" / "claude" / "skills" / s).exists())

    def test_no_private_paths_or_template_tokens_in_any_bundled_skill(self):
        hits = []
        for s in CFG["bundled_skills"]:
            for f in (ROOT / "core" / "skills" / s).rglob("*"):
                if f.is_file():
                    t = f.read_text(encoding="utf-8", errors="ignore")
                    hits += [(str(f.relative_to(ROOT)), tok) for tok in self.PRIVATE if tok in t]
        self.assertEqual(hits, [])

    def test_no_private_paths_in_deployed_agents(self):
        hits = []
        for f in (ROOT / "deploy").rglob("agents/*"):
            t = f.read_text(encoding="utf-8", errors="ignore")
            hits += [(str(f.relative_to(ROOT)), tok) for tok in self.PRIVATE if tok in t]
        self.assertEqual(hits, [])


class ForbiddenTokens(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        deploy.build()

    def deployed_files(self):
        return [f for f in (ROOT / "deploy").rglob("*") if f.is_file() and f.suffix in (".md", ".toml", ".json")]

    def test_no_template_tokens_in_deployed_output(self):
        hits = [str(f.relative_to(ROOT)) for f in self.deployed_files() if "{{" in f.read_text(encoding="utf-8", errors="ignore")]
        self.assertEqual(hits, [])

    def test_no_foreign_environment_names_in_deployed_output(self):
        hits = []
        for f in self.deployed_files():
            t = f.read_text(encoding="utf-8", errors="ignore")
            hits += [(str(f.relative_to(ROOT)), tok) for tok in FORBIDDEN if tok in t]
        self.assertEqual(hits, [])

    def test_no_foreign_tokens_in_core_agents_and_skills(self):
        hits = []
        for f in list((ROOT / "core" / "agents").glob("*.md")) + list((ROOT / "core" / "skills").rglob("*.md")):
            t = f.read_text(encoding="utf-8", errors="ignore")
            hits += [(str(f.relative_to(ROOT)), tok) for tok in FORBIDDEN + ("{{",) if tok in t]
        self.assertEqual(hits, [])

    def test_codex_agents_still_valid_toml_after_curated_bodies(self):
        for f in (ROOT / "deploy" / "codex" / "agents").glob("*.toml"):
            with self.subTest(agent=f.stem):
                d = tomllib.loads(f.read_text(encoding="utf-8"))
                self.assertEqual(d["name"], f.stem)
                self.assertGreater(len(d["developer_instructions"]), 50)


if __name__ == "__main__":
    unittest.main()
