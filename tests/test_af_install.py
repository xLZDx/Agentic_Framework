"""tools/af_install.py against temp homes only (never the real ~/.claude or ~/.codex)."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

import afhelpers as H
from afhelpers import ROOT, deploy

INSTALL = ROOT / "tools" / "af_install.py"
FW_POSIX = ROOT.as_posix()
REAL_HOMES = (Path.home() / ".claude", Path.home() / ".codex")
FOREIGN_HOOK = {"hooks": [{"type": "command", "command": "python other_tool.py"}]}


def run(*args):
    return subprocess.run([sys.executable, str(INSTALL), *map(str, args)], capture_output=True, text=True,
                          timeout=120)


def tree(base: Path) -> dict:
    return {str(p.relative_to(base)): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file()}


def af_hook_cmds(settings: dict) -> list:
    return [h["command"] for ev in settings.get("hooks", {}).values() for e in ev for h in e["hooks"]
            if "af_cli.py hook" in h["command"]]


class InstallBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        deploy.build()

    def setUp(self):
        base = H.tmpdir(self)
        self.ch, self.cx = base / "claude", base / "codex"
        self.ch.mkdir()
        self.cx.mkdir()
        self.base = base

    def go(self, *extra):
        r = run("--claude-home", self.ch, "--codex-home", self.cx, *extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def settings(self):
        return json.loads((self.ch / "settings.json").read_text(encoding="utf-8"))

    def seed_settings(self):
        pre = {"theme": "dark", "hooks": {
            "PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "python guard.py"}]}],
            "Stop": [FOREIGN_HOOK],
        }}
        (self.ch / "settings.json").write_text(json.dumps(pre, indent=2), encoding="utf-8")
        return pre


class FirstInstall(InstallBase):
    def test_writes_agents_skills_prompts(self):
        self.go()
        dep = ROOT / "deploy"
        self.assertEqual({p.name for p in (self.ch / "agents").glob("*.md")},
                         {p.name for p in (dep / "claude" / "agents").glob("*.md")})
        self.assertEqual(len(list((self.ch / "agents").glob("*.md"))), len(json.loads((ROOT / "core" / "framework.json").read_text(encoding="utf-8"))["bundled_agents"]))
        self.assertEqual(len(list((self.cx / "agents").glob("*.toml"))), len(json.loads((ROOT / "core" / "framework.json").read_text(encoding="utf-8"))["bundled_agents"]))
        for s in json.loads((ROOT / "core" / "framework.json").read_text(encoding="utf-8"))["bundled_skills"]:
            self.assertTrue((self.ch / "skills" / s / "SKILL.md").is_file(), s)
            self.assertTrue((self.cx / "skills" / s / "SKILL.md").is_file(), s)
        self.assertTrue((self.ch / "skills" / "af" / "SKILL.md").is_file())
        self.assertTrue((self.cx / "prompts" / "af.md").is_file())
        self.assertIn("$ARGUMENTS", (self.cx / "prompts" / "af.md").read_text(encoding="utf-8"))
        self.assertTrue((self.ch / "af-install-manifest.json").is_file())
        self.assertTrue((self.cx / "af-install-manifest.json").is_file())

    def test_deployed_agent_bytes_equal_source(self):
        self.go()
        # compare modulo line endings: on Windows deploy/ is CRLF while the installer writes LF
        # (reported as a minor product observation)
        norm = lambda b: b.replace(bytes([13, 10]), bytes([10]))
        self.assertEqual(norm((self.ch / "agents" / "architect.md").read_bytes()),
                         norm((ROOT / "deploy" / "claude" / "agents" / "architect.md").read_bytes()))

    def test_manifest_lists_only_files_that_exist_inside_homes(self):
        self.go()
        for home in (self.ch, self.cx):
            m = json.loads((home / "af-install-manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(m)
            for f in m:
                self.assertTrue(Path(f).is_file(), f)
                Path(f).resolve().relative_to(home.resolve())

    def test_merge_into_existing_settings_preserves_foreign_and_backs_up(self):
        pre = self.seed_settings()
        original_bytes = (self.ch / "settings.json").read_bytes()
        self.go()
        s = self.settings()
        self.assertEqual(s["theme"], "dark")
        self.assertIn(pre["hooks"]["PreToolUse"][0], s["hooks"]["PreToolUse"])
        self.assertEqual(s["hooks"]["Stop"], [FOREIGN_HOOK])
        for ev in ("SessionStart", "UserPromptSubmit", "PreToolUse"):
            self.assertTrue(any("af_cli.py hook" in h["command"] for e in s["hooks"][ev] for h in e["hooks"]), ev)
        bak = list(self.ch.glob("settings.json.bak-af-*"))
        self.assertEqual(len(bak), 1)
        self.assertEqual(bak[0].read_bytes(), original_bytes)

    def test_fw_placeholder_replaced_everywhere(self):
        self.seed_settings()
        self.go()
        cmds = af_hook_cmds(self.settings())
        self.assertEqual(len(cmds), 3)
        for c in cmds:
            self.assertEqual(c, f"python {FW_POSIX}/tools/af_cli.py hook")
        for home in (self.ch, self.cx):
            for p in home.rglob("*"):
                if p.is_file() and p.suffix in (".md", ".toml", ".json") and not p.name.startswith("settings.json.bak"):
                    self.assertNotIn("{fw}", p.read_text(encoding="utf-8"), str(p))
        self.assertIn(f"python {FW_POSIX}/tools/af_cli.py on", (self.ch / "skills" / "af" / "SKILL.md").read_text(encoding="utf-8"))

    def test_install_without_preexisting_settings_creates_it(self):
        self.go()
        self.assertEqual(len(af_hook_cmds(self.settings())), 3)
        self.assertEqual(list(self.ch.glob("settings.json.bak-af-*")), [])  # nothing to back up

    def test_rerun_is_idempotent(self):
        self.seed_settings()
        self.go()
        snap_ch, snap_cx = tree(self.ch), tree(self.cx)
        bak_before = set(self.ch.glob("settings.json.bak-af-*"))
        self.go()
        self.assertEqual(len(af_hook_cmds(self.settings())), 3)
        self.assertEqual(set(self.ch.glob("settings.json.bak-af-*")), bak_before)
        self.assertEqual(tree(self.ch), snap_ch)
        self.assertEqual(tree(self.cx), snap_cx)

    def test_only_flag_limits_targets(self):
        self.go("--only", "codex")
        self.assertTrue((self.cx / "agents").is_dir())
        self.assertFalse((self.ch / "agents").exists())
        self.assertFalse((self.ch / "settings.json").exists())

    def test_rerun_updates_files_we_own_but_changed(self):
        self.go()
        f = self.ch / "agents" / "architect.md"
        good = f.read_bytes()
        f.write_bytes(b"locally edited\n")
        r = self.go()
        # owned (in manifest) -> refreshed, not SKIPPED
        self.assertEqual(f.read_bytes(), good)
        self.assertNotIn("SKIPPED", r.stdout)


class ForeignFiles(InstallBase):
    def test_preexisting_differing_agent_not_in_manifest_is_skipped(self):
        (self.ch / "agents").mkdir()
        mine = self.ch / "agents" / "architect.md"
        mine.write_bytes(b"---\nname: architect\n---\nmy own architect\r\n")
        orig = mine.read_bytes()
        r = self.go()
        self.assertEqual(mine.read_bytes(), orig)
        self.assertIn("SKIPPED", r.stdout)
        self.assertIn(str(mine), r.stdout)
        m = json.loads((self.ch / "af-install-manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn(str(mine), m)
        # other agents still installed
        self.assertTrue((self.ch / "agents" / "planner.md").is_file())
        # still skipped on re-run
        self.go()
        self.assertEqual(mine.read_bytes(), orig)

    def test_preexisting_identical_file_is_same_not_skipped(self):
        self.go()
        for p in list(self.ch.glob("af-install-manifest.json")):
            p.unlink()
        r = self.go()
        self.assertNotIn("SKIPPED", r.stdout)


class DryRun(InstallBase):
    def test_dry_run_writes_nothing(self):
        pre = self.seed_settings()
        before = tree(self.base)
        r = self.go("--dry-run")
        self.assertEqual(tree(self.base), before)
        self.assertIn("WRITE", r.stdout)
        self.assertIn("MERGE", r.stdout)
        self.assertFalse((self.ch / "agents").exists())
        self.assertFalse((self.cx / "agents").exists())
        self.assertFalse((self.ch / "af-install-manifest.json").exists())
        self.assertEqual(list(self.ch.glob("settings.json.bak-af-*")), [])
        self.assertEqual(self.settings(), pre)

    def test_dry_run_on_empty_homes_creates_no_files(self):
        self.go("--dry-run")
        self.assertEqual(tree(self.base), {})

    def test_uninstall_dry_run_removes_nothing(self):
        self.seed_settings()
        self.go()
        before = tree(self.base)
        self.go("--uninstall", "--dry-run")
        self.assertEqual(tree(self.base), before)


class Uninstall(InstallBase):
    def test_removes_exactly_manifest_files_and_our_hooks(self):
        pre = self.seed_settings()
        (self.ch / "agents").mkdir(exist_ok=True)
        foreign_differing = self.ch / "agents" / "architect.md"
        foreign_differing.write_bytes(b"mine\n")
        foreign_extra = self.ch / "agents" / "my-own.md"
        foreign_extra.write_bytes(b"custom\n")
        foreign_skill = self.ch / "skills" / "my-skill" / "SKILL.md"
        foreign_skill.parent.mkdir(parents=True)
        foreign_skill.write_bytes(b"skill\n")
        foreign_codex = self.cx / "agents" / "keep.toml"
        foreign_codex.parent.mkdir(parents=True)
        foreign_codex.write_bytes(b'name="keep"\n')
        manifests = {h: json.loads(self.go() and (h / "af-install-manifest.json").read_text(encoding="utf-8"))
                     for h in (self.ch, self.cx)}
        self.go("--uninstall")
        for home, files in manifests.items():
            for f in files:
                self.assertFalse(Path(f).exists(), f)
            self.assertFalse((home / "af-install-manifest.json").exists())
        self.assertEqual(foreign_differing.read_bytes(), b"mine\n")
        self.assertEqual(foreign_extra.read_bytes(), b"custom\n")
        self.assertEqual(foreign_skill.read_bytes(), b"skill\n")
        self.assertEqual(foreign_codex.read_bytes(), b'name="keep"\n')
        s = self.settings()
        self.assertEqual(af_hook_cmds(s), [])
        self.assertEqual(s["theme"], "dark")
        self.assertEqual(s["hooks"]["PreToolUse"], pre["hooks"]["PreToolUse"])
        self.assertEqual(s["hooks"]["Stop"], [FOREIGN_HOOK])
        self.assertNotIn("SessionStart", s["hooks"])
        self.assertNotIn("UserPromptSubmit", s["hooks"])

    def test_uninstall_leaves_no_af_files_when_homes_were_empty(self):
        self.go()
        self.go("--uninstall")
        left = [p for p in tree(self.base) if "settings.json" not in p]
        self.assertEqual(left, [])

    def test_uninstall_without_install_is_noop_success(self):
        (self.ch / "agents").mkdir()
        keep = self.ch / "agents" / "x.md"
        keep.write_bytes(b"x")
        self.go("--uninstall")
        self.assertEqual(keep.read_bytes(), b"x")

    def test_reinstall_after_uninstall_restores(self):
        self.seed_settings()
        self.go()
        self.go("--uninstall")
        self.go()
        self.assertEqual(len(af_hook_cmds(self.settings())), 3)
        self.assertTrue((self.ch / "agents" / "architect.md").is_file())


class NeverTouchesRealHomes(unittest.TestCase):
    def test_install_with_temp_homes_leaves_real_homes_manifest_absent(self):
        # guard for the test-suite itself: no manifest created in the real homes by these tests
        for h in REAL_HOMES:
            m = h / "af-install-manifest.json"
            if m.exists():
                self.skipTest(f"{m} pre-existed (user's own install); not asserting on it")


if __name__ == "__main__":
    unittest.main()
